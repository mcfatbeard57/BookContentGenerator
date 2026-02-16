"""NER Extractor - Entity extraction via Ollama LLM

Extracts characters, locations, factions, and timeline events from text
using LLM-based NER with full observability integration.
"""
import hashlib
import json
import re
import time
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
    # Track which chunks each entity appeared in (for connections)
    entity_chunk_map: dict[str, list[str]] = field(default_factory=dict)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks for LLM processing.

    Attempts to split at paragraph or sentence boundaries when possible
    to avoid breaking mid-sentence.

    Args:
        text: The text to split.
        chunk_size: Maximum number of characters per chunk.
        overlap: Number of characters to overlap between consecutive chunks.

    Returns:
        List of text chunks.
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
}


def estimate_tokens(text: str) -> int:
    """Estimate token count using a rough chars-per-token heuristic.

    Args:
        text: Input text.

    Returns:
        Approximate token count (1 token ≈ 4 English characters).
    """
    return len(text) // 4


def call_ollama(
    prompt: str,
    system_prompt: str,
    model: str = NER_MODEL,
    timeout: float = 300.0,
    call_type: str = "ner",
    verbose: bool = True,
) -> str:
    """Call Ollama API for text generation.

    Fully instrumented with tracing, telemetry, and token tracking.

    Args:
        prompt: The user prompt to send.
        system_prompt: System-level instruction prompt.
        model: Ollama model identifier.
        timeout: HTTP request timeout in seconds.
        call_type: Label for telemetry bucketing (e.g. ``"ner"``, ``"summarize"``).
        verbose: If True, print token usage to stdout.

    Returns:
        Raw response text from the model.

    Raises:
        httpx.HTTPStatusError: If the API returns a non-2xx status.
    """
    from src.observability.tracer import log_llm_call, SpanContext
    from src.observability import telemetry

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

    # Telemetry timer
    telemetry.start_timer(f"llm_{call_type}")

    with SpanContext(f"llm_call_{call_type}", model=model) as span:
        start_time = time.monotonic()

        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()

            result = response.json()

        duration_ms = (time.monotonic() - start_time) * 1000
        output_tokens = result.get("eval_count", 0)

        # Telemetry
        telemetry.stop_timer(f"llm_{call_type}")
        telemetry.increment("llm_calls")
        telemetry.increment(f"llm_calls_{call_type}")
        telemetry.increment("tokens_prompt", total_input_tokens)
        telemetry.increment("tokens_completion", output_tokens)
        telemetry.record("llm_call_duration_ms", duration_ms)
        telemetry.record(f"tokens_per_{call_type}_call", output_tokens)

        # Trace — record full prompt/response for replayability
        log_llm_call(
            model_name=model,
            prompt=prompt,
            response=result.get("response", ""),
            duration_ms=duration_ms,
            tokens_prompt=total_input_tokens,
            tokens_completion=output_tokens,
            temperature=OLLAMA_OPTIONS.get("temperature", 0.0),
            seed=OLLAMA_OPTIONS.get("seed"),
        )

        span.attributes["tokens_in"] = total_input_tokens
        span.attributes["tokens_out"] = output_tokens
        span.attributes["call_type"] = call_type

        if verbose and output_tokens:
            total_time = result.get("total_duration", 0) / 1e9
            print(f"→ {output_tokens} output tokens in {total_time:.1f}s")

        return result.get("response", "")


def parse_json_response(response: str) -> dict | None:
    """Parse JSON from an LLM response, tolerating common formatting issues.

    Tries direct parsing, markdown code fences, and regex extraction.

    Args:
        response: Raw text response from the LLM.

    Returns:
        Parsed dictionary, or ``None`` if no valid JSON was found.
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
    book_id: str = "",
    chunk_idx: int = 0,
) -> list[RawEntity]:
    """Extract entities from a single text chunk via LLM NER.

    Uses idempotency to skip re-extraction of identical content.

    Args:
        text: The text chunk to process.
        chapter_title: Title of the source chapter.
        book_title: Title of the source book.
        book_id: Deterministic book identifier.
        chunk_idx: Zero-based index of this chunk within the chapter.

    Returns:
        List of extracted ``RawEntity`` instances.

    Raises:
        InterruptedError: If the user requests a stop.
        RuntimeError: If Ollama API fails after all retries.
    """
    from src.observability.progress import check_interrupt
    from src.observability.idempotency import (
        generate_content_hash,
        generate_idempotency_key,
        get_cached_result,
        is_processed,
        safe_mark_complete,
    )
    from src.observability import telemetry

    # Idempotency check — skip if already processed
    content_hash = generate_content_hash(text)
    idem_key = generate_idempotency_key(
        book_id=book_id,
        chapter_title=chapter_title,
        chunk_idx=chunk_idx,
        operation="ner_extraction",
        content_hash=content_hash,
    )

    if is_processed(idem_key):
        cached = get_cached_result(idem_key)
        if cached:
            return [RawEntity(**e) for e in cached]

    prompt = NER_USER_PROMPT_TEMPLATE.format(
        chapter_title=chapter_title,
        book_title=book_title,
        text=text,
    )

    for attempt in range(MAX_RETRIES):
        if check_interrupt():
            print("\n⚠️ Interrupted before LLM call")
            raise InterruptedError("User requested stop")

        try:
            response = call_ollama(prompt, NER_SYSTEM_PROMPT, call_type="ner")
            parsed = parse_json_response(response)

            if parsed and "entities" in parsed:
                entities = []
                for entity_data in parsed["entities"]:
                    if not entity_data.get("name") or not entity_data.get("entity_type"):
                        continue

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

                # Cache result for idempotency
                result_dicts = [
                    {
                        "name": e.name, "aliases": e.aliases,
                        "entity_type": e.entity_type, "context": e.context,
                        "source_chapter": e.source_chapter,
                        "source_book": e.source_book,
                    }
                    for e in entities
                ]
                safe_mark_complete(
                    idem_key,
                    result=result_dicts,
                    model_name=NER_MODEL,
                    prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:12],
                )

                telemetry.increment("chunks_processed")
                telemetry.increment("entities_extracted", len(entities))

                return entities

        except InterruptedError:
            raise

        except httpx.HTTPError as e:
            telemetry.record_error("ner_extraction", str(e))
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Ollama API error after {MAX_RETRIES} attempts: {e}")

        except Exception as e:
            telemetry.record_error("ner_extraction", str(e))
            if attempt == MAX_RETRIES - 1:
                print(f"Warning: Failed to extract entities from chunk: {e}")
                return []

    return []


def merge_raw_entities(entities: list[RawEntity]) -> list[RawEntity]:
    """Merge duplicate entities by name and type (case-insensitive).

    Combines aliases and picks the longest context. This is a preliminary
    merge before full alias resolution.

    Args:
        entities: Flat list of raw entities, possibly with duplicates.

    Returns:
        De-duplicated list with merged aliases and occurrence counts.
    """
    merged: dict[str, RawEntity] = {}

    for entity in entities:
        key = (entity.name.lower(), entity.entity_type)

        if key in merged:
            existing = merged[key]
            existing.aliases = list(set(existing.aliases + entity.aliases))
            existing.occurrence_count += 1
            if len(entity.context) > len(existing.context):
                existing.context = entity.context
        else:
            merged[key] = entity

    return list(merged.values())


def extract_entities_from_chapter(
    chapter: Chapter,
    book_title: str,
    book_id: str = "",
    chapter_index: int = 0,
    total_chapters: int = 1,
) -> tuple[list[RawEntity], dict[str, list[str]]]:
    """Extract entities from a single chapter, handling chunking.

    Splits the chapter into overlapping chunks and runs NER on each.

    Args:
        chapter: The parsed chapter to process.
        book_title: Title of the source book.
        book_id: Deterministic book identifier.
        chapter_index: Zero-based index of this chapter.
        total_chapters: Total number of chapters in the book.

    Returns:
        Tuple of (merged_entities, entity_chunk_map) where
        ``entity_chunk_map`` maps ``"type:name"`` keys to chunk IDs.

    Raises:
        InterruptedError: If the user requests a stop.
    """
    from src.observability.progress import emit_progress, ProgressStage

    chunks = chunk_text(chapter.content)
    all_entities: list[RawEntity] = []
    entity_chunk_map: dict[str, list[str]] = {}

    for i, chunk in enumerate(chunks):
        chunk_id = f"chapter_{chapter_index}:chunk_{i}"
        print(f"    Chunk {i + 1}/{len(chunks)}...", end=" ", flush=True)

        emit_progress(
            stage=ProgressStage.EXTRACTING_CHARACTERS_AND_ENTITIES,
            current=chapter_index,
            total=total_chapters,
            message=f"Chapter {chapter_index + 1}/{total_chapters}: {chapter.title} (chunk {i + 1}/{len(chunks)})",
            sub_current=i + 1,
            sub_total=len(chunks),
        )

        try:
            entities = extract_entities_from_chunk(
                chunk, chapter.title, book_title,
                book_id=book_id, chunk_idx=i,
            )
            all_entities.extend(entities)

            # Track entity → chunk mapping for connections
            for e in entities:
                entity_key = f"{e.entity_type}:{e.name.lower()}"
                if entity_key not in entity_chunk_map:
                    entity_chunk_map[entity_key] = []
                entity_chunk_map[entity_key].append(chunk_id)

            print(f"found {len(entities)} entities")
        except InterruptedError:
            print(f"\n⚠️ Interrupted at chunk {i + 1}/{len(chunks)}")
            raise

    merged = merge_raw_entities(all_entities)
    return merged, entity_chunk_map


def extract_entities_from_book(book: ParsedBook) -> ExtractionResult:
    """Extract all entities from a parsed book.

    Processes chapters sequentially with checkpointing, interrupt
    support, and full observability integration.

    Args:
        book: The fully parsed book to extract entities from.

    Returns:
        ``ExtractionResult`` containing all merged entities, chunk
        mappings, error list, and processing counts.
    """
    from src.observability.progress import check_interrupt, clear_interrupt
    from src.observability.checkpoint import CheckpointManager, save_checkpoint

    result = ExtractionResult(book_id=book.book_id)
    all_entities: list[RawEntity] = []
    all_chunk_maps: dict[str, list[str]] = {}

    print(f"Extracting entities from '{book.title}'...")

    with CheckpointManager(book.book_id, book.title, len(book.chapters)) as mgr:
        for i, chapter in enumerate(book.chapters):
            if check_interrupt():
                print(f"\n  ⚠️ Extraction interrupted by user after {i} chapters")
                save_checkpoint(mgr.checkpoint)
                break

            if mgr.is_chapter_done(chapter.title):
                print(f"  Skipping chapter {i + 1}/{len(book.chapters)}: {chapter.title} (already done)")
                continue

            print(f"  Processing chapter {i + 1}/{len(book.chapters)}: {chapter.title}")

            try:
                entities, chunk_map = extract_entities_from_chapter(
                    chapter,
                    book.title,
                    book_id=book.book_id,
                    chapter_index=i,
                    total_chapters=len(book.chapters),
                )

                entity_dicts = [
                    {"name": e.name, "entity_type": e.entity_type, "context": e.context}
                    for e in entities
                ]
                mgr.mark_complete(chapter.title, entity_dicts)

                all_entities.extend(entities)

                # Merge chunk maps
                for key, chunks in chunk_map.items():
                    if key not in all_chunk_maps:
                        all_chunk_maps[key] = []
                    all_chunk_maps[key].extend(chunks)

                result.chapters_processed += 1

            except InterruptedError:
                print(f"\n  ⚠️ Extraction interrupted during chapter {i + 1}")
                save_checkpoint(mgr.checkpoint)
                break

    result.entities = merge_raw_entities(all_entities)
    result.entity_chunk_map = all_chunk_maps

    print(f"  Extracted {len(result.entities)} unique entities from {result.chapters_processed} chapters")

    clear_interrupt()
    return result
