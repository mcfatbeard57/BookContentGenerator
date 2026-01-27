"""Canonical Summarizer - Generate LLM-ready descriptions via llama3.1"""
import re
from datetime import date

from src.config import OLLAMA_OPTIONS, SUMMARIZER_MODEL
from src.extraction.alias_resolver import ResolvedEntity
from src.extraction.ner_extractor import call_ollama, parse_json_response
from src.extraction.prompts import SUMMARIZER_SYSTEM_PROMPT, SUMMARIZER_TEMPLATES
from src.models.entities import (
    BaseEntity,
    Character,
    Entity,
    Faction,
    Location,
    SourceReference,
    TimelineEvent,
)


def generate_entity_id(name: str, entity_type: str) -> str:
    """Generate a normalized entity ID from name and type"""
    # Prefix by type
    prefix = {
        "character": "char",
        "location": "loc",
        "faction": "fac",
        "timeline_event": "evt",
    }.get(entity_type, "ent")
    
    # Normalize name
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s]", "", slug)
    slug = re.sub(r"\s+", "_", slug)
    slug = slug[:30].strip("_")
    
    return f"{prefix}_{slug}"


def summarize_entity(
    resolved: ResolvedEntity,
    book_id: str,
) -> Entity | None:
    """
    Generate canonical summary for a resolved entity using LLM.
    
    Returns the appropriate Entity type (Character, Location, etc.)
    """
    entity_type = resolved.entity_type
    template = SUMMARIZER_TEMPLATES.get(entity_type)
    
    if not template:
        print(f"Warning: No summarizer template for entity type: {entity_type}")
        return None
    
    # Build source contexts
    source_contexts = "\n\n".join(
        f"- {ctx}" for ctx in resolved.contexts[:10]  # Limit to avoid context overflow
    )
    
    if not source_contexts:
        source_contexts = "(No context excerpts available)"
    
    # Build prompt
    prompt = template.format(
        name=resolved.canonical_name,
        aliases=", ".join(resolved.all_names[1:]) if len(resolved.all_names) > 1 else "None",
        book_title=resolved.source_book,
        source_contexts=source_contexts,
    )
    
    try:
        # Call LLM with summarizer model
        response = call_ollama(
            prompt=prompt,
            system_prompt=SUMMARIZER_SYSTEM_PROMPT,
            model=SUMMARIZER_MODEL,
        )
        
        parsed = parse_json_response(response)
        
        if not parsed:
            print(f"Warning: Could not parse summarizer response for {resolved.canonical_name}")
            return _create_minimal_entity(resolved, book_id)
        
        return _create_entity_from_summary(resolved, parsed, book_id)
    
    except Exception as e:
        print(f"Warning: Summarization failed for {resolved.canonical_name}: {e}")
        return _create_minimal_entity(resolved, book_id)


def _create_minimal_entity(resolved: ResolvedEntity, book_id: str) -> Entity:
    """Create a minimal entity when summarization fails"""
    entity_id = generate_entity_id(resolved.canonical_name, resolved.entity_type)
    
    source = SourceReference(
        source_type="book",
        source_id=book_id,
        context=resolved.contexts[0] if resolved.contexts else None,
    )
    
    base_kwargs = {
        "entity_id": entity_id,
        "name": resolved.canonical_name,
        "aliases": [n for n in resolved.all_names if n != resolved.canonical_name],
        "sources": [source],
        "first_appearance": resolved.source_chapters[0] if resolved.source_chapters else None,
        "occurrence_count": resolved.total_occurrences,
        "last_updated": date.today(),
        "canonical_description": None,
    }
    
    if resolved.entity_type == "character":
        return Character(**base_kwargs)
    elif resolved.entity_type == "location":
        return Location(**base_kwargs)
    elif resolved.entity_type == "faction":
        return Faction(**base_kwargs)
    elif resolved.entity_type == "timeline_event":
        return TimelineEvent(**base_kwargs)
    else:
        raise ValueError(f"Unknown entity type: {resolved.entity_type}")


def _create_entity_from_summary(
    resolved: ResolvedEntity,
    summary: dict,
    book_id: str,
) -> Entity:
    """Create entity from LLM summary response"""
    entity_id = generate_entity_id(resolved.canonical_name, resolved.entity_type)
    
    source = SourceReference(
        source_type="book",
        source_id=book_id,
        context=resolved.contexts[0] if resolved.contexts else None,
    )
    
    base_kwargs = {
        "entity_id": entity_id,
        "name": resolved.canonical_name,
        "aliases": [n for n in resolved.all_names if n != resolved.canonical_name],
        "sources": [source],
        "first_appearance": resolved.source_chapters[0] if resolved.source_chapters else None,
        "occurrence_count": resolved.total_occurrences,
        "last_updated": date.today(),
        "canonical_description": summary.get("canonical_description"),
    }
    
    if resolved.entity_type == "character":
        return Character(
            **base_kwargs,
            physical_traits=summary.get("physical_traits", []),
            personality_traits=summary.get("personality_traits", []),
            abilities=summary.get("abilities", []),
            role=summary.get("role"),
            species=summary.get("species"),
        )
    
    elif resolved.entity_type == "location":
        return Location(
            **base_kwargs,
            location_type=summary.get("location_type"),
            environment=summary.get("environment", []),
            architecture=summary.get("architecture", []),
            atmosphere=summary.get("atmosphere", []),
        )
    
    elif resolved.entity_type == "faction":
        return Faction(
            **base_kwargs,
            faction_type=summary.get("faction_type"),
            goals=summary.get("goals", []),
            traits=summary.get("traits", []),
        )
    
    elif resolved.entity_type == "timeline_event":
        return TimelineEvent(
            **base_kwargs,
            event_type=summary.get("event_type"),
            temporal_marker=summary.get("temporal_marker"),
            participants=summary.get("participants", []),
            consequences=summary.get("consequences", []),
        )
    
    else:
        raise ValueError(f"Unknown entity type: {resolved.entity_type}")


def summarize_all_entities(
    resolved_entities: list[ResolvedEntity],
    book_id: str,
) -> list[Entity]:
    """
    Generate canonical summaries for all resolved entities.
    """
    entities: list[Entity] = []
    
    print(f"Generating canonical summaries for {len(resolved_entities)} entities...")
    
    for i, resolved in enumerate(resolved_entities):
        print(f"  [{i + 1}/{len(resolved_entities)}] Summarizing: {resolved.canonical_name}")
        
        entity = summarize_entity(resolved, book_id)
        if entity:
            entities.append(entity)
    
    print(f"  → Generated {len(entities)} canonical entities")
    
    return entities
