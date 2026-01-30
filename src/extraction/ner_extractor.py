"""NER Extractor - Entity extraction via Ollama LLM"""
import json
import re
from dataclasses import dataclass, field

import httpx

from src.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    MAX_RETRIES,
    NER_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_OPTIONS,
)
from src.extraction.prompts import NER_SYSTEM_PROMPT, NER_USER_PROMPT_TEMPLATE
from src.ingestion.epub_parser import Chapter, ParsedBook


@dataclass
class RawEntity:
    """Raw entity as extracted from text (before resolution)"""
    
    name: str
    aliases: list[str]
    entity_type: str
    context: str
    source_chapter: str
    source_book: str
    occurrence_count: int = 1


@dataclass
class ExtractionResult:
    """Result of entity extraction from a book"""
    
    book_id: str
    entities: list[RawEntity] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    chapters_processed: int = 0


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping chunks for LLM processing.
    
    Attempts to split at paragraph boundaries when possible.
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # If not at the end, try to find a good break point
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + chunk_size // 2:
                end = para_break
            else:
                # Fall back to sentence break
                sentence_break = text.rfind(". ", start, end)
                if sentence_break > start + chunk_size // 2:
                    end = sentence_break + 1
        
        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end
    
    return chunks



# Model context limits (in tokens)
MODEL_CONTEXT_LIMITS = {
    "qwen2.5:7b": 32768,
    "qwen2.5:3b": 32768,
    "llama3.1:8b": 131072,
    "nomic-embed-text": 8192,
}


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough: 1 token ≈ 4 chars for English)"""
    return len(text) // 4


def call_ollama(
    prompt: str,
    system_prompt: str,
    model: str = NER_MODEL,
    timeout: float = 300.0,  # 5 minutes for M2 Mac
    verbose: bool = True,
) -> str:
    """
    Call Ollama API for text generation.
    
    Returns raw response text.
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    
    # Estimate tokens and check limits
    prompt_tokens = estimate_tokens(prompt)
    system_tokens = estimate_tokens(system_prompt)
    total_input_tokens = prompt_tokens + system_tokens
    context_limit = MODEL_CONTEXT_LIMITS.get(model, 32768)
    
    if verbose:
        usage_pct = (total_input_tokens / context_limit) * 100
        print(f"      [Tokens: ~{total_input_tokens:,} / {context_limit:,} ({usage_pct:.1f}%)]", end=" ", flush=True)
    
    if total_input_tokens > context_limit * 0.9:
        print(f"⚠️ WARNING: Approaching context limit!")
    
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "options": OLLAMA_OPTIONS,
    }
    
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        # Log actual token usage from Ollama response if available
        if verbose and "eval_count" in result:
            output_tokens = result.get("eval_count", 0)
            total_time = result.get("total_duration", 0) / 1e9  # ns to seconds
            print(f"→ {output_tokens} output tokens in {total_time:.1f}s")
        
        return result.get("response", "")


def parse_json_response(response: str) -> dict | None:
    """
    Parse JSON from LLM response, handling common formatting issues.
    """
    # Try direct parse first
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code blocks
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON object in response
    json_match = re.search(r"\{[\s\S]*\}", response)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    return None


def extract_entities_from_chunk(
    text: str,
    chapter_title: str,
    book_title: str,
) -> list[RawEntity]:
    """
    Extract entities from a single text chunk.
    """
    prompt = NER_USER_PROMPT_TEMPLATE.format(
        chapter_title=chapter_title,
        book_title=book_title,
        text=text,
    )
    
    for attempt in range(MAX_RETRIES):
        try:
            response = call_ollama(prompt, NER_SYSTEM_PROMPT)
            parsed = parse_json_response(response)
            
            if parsed and "entities" in parsed:
                entities = []
                for entity_data in parsed["entities"]:
                    # Validate required fields
                    if not entity_data.get("name") or not entity_data.get("entity_type"):
                        continue
                    
                    # Validate entity type
                    entity_type = entity_data["entity_type"].lower()
                    if entity_type not in ["character", "location", "faction", "timeline_event"]:
                        continue
                    
                    entities.append(RawEntity(
                        name=entity_data["name"],
                        aliases=entity_data.get("aliases", []),
                        entity_type=entity_type,
                        context=entity_data.get("context", ""),
                        source_chapter=chapter_title,
                        source_book=book_title,
                    ))
                
                return entities
        
        except httpx.HTTPError as e:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Ollama API error after {MAX_RETRIES} attempts: {e}")
        
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                print(f"Warning: Failed to extract entities from chunk: {e}")
                return []
    
    return []


def merge_raw_entities(entities: list[RawEntity]) -> list[RawEntity]:
    """
    Merge duplicate entities by name (case-insensitive).
    
    This is a preliminary merge before alias resolution.
    """
    merged: dict[str, RawEntity] = {}
    
    for entity in entities:
        key = (entity.name.lower(), entity.entity_type)
        
        if key in merged:
            # Merge aliases
            existing = merged[key]
            existing.aliases = list(set(existing.aliases + entity.aliases))
            existing.occurrence_count += 1
            
            # Keep longer context if available
            if len(entity.context) > len(existing.context):
                existing.context = entity.context
        else:
            merged[key] = entity
    
    return list(merged.values())


def extract_entities_from_chapter(
    chapter: Chapter,
    book_title: str,
) -> list[RawEntity]:
    """
    Extract entities from a single chapter, handling chunking.
    """
    chunks = chunk_text(chapter.content)
    all_entities: list[RawEntity] = []
    
    for i, chunk in enumerate(chunks):
        print(f"    Chunk {i + 1}/{len(chunks)}...", end=" ", flush=True)
        entities = extract_entities_from_chunk(chunk, chapter.title, book_title)
        all_entities.extend(entities)
        print(f"found {len(entities)} entities")
    
    # Merge duplicates within chapter
    return merge_raw_entities(all_entities)


def extract_entities_from_book(book: ParsedBook) -> ExtractionResult:
    """
    Extract all entities from a parsed book.
    
    Processes chapters sequentially and merges results.
    """
    result = ExtractionResult(book_id=book.book_id)
    all_entities: list[RawEntity] = []
    
    print(f"Extracting entities from '{book.title}'...")
    
    for i, chapter in enumerate(book.chapters):
        print(f"  Processing chapter {i + 1}/{len(book.chapters)}: {chapter.title}")
        
        try:
            entities = extract_entities_from_chapter(chapter, book.title)
            all_entities.extend(entities)
            result.chapters_processed += 1
        except Exception as e:
            error_msg = f"Error processing chapter '{chapter.title}': {e}"
            print(f"  Warning: {error_msg}")
            result.errors.append(error_msg)
    
    # Merge all duplicates across chapters
    result.entities = merge_raw_entities(all_entities)
    
    print(f"  Extracted {len(result.entities)} unique entities from {result.chapters_processed} chapters")
    
    return result
