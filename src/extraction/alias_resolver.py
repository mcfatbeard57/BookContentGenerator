"""Alias Resolver - LLM-based primary with fuzzy matching fallback

Instrumented with tracing, decision logging, and telemetry.
"""
import json
import re
from dataclasses import dataclass, field

import httpx
from rapidfuzz import fuzz, process

from src.config import (
    FUZZY_MATCH_THRESHOLD,
    MAX_RETRIES,
    NER_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_OPTIONS,
)
from src.extraction.ner_extractor import RawEntity, call_ollama, parse_json_response
from src.extraction.prompts import (
    ALIAS_RESOLUTION_SYSTEM_PROMPT,
    ALIAS_RESOLUTION_USER_PROMPT_TEMPLATE,
)


@dataclass
class ResolvedEntity:
    """Entity after alias resolution with a single canonical name.

    Attributes:
        canonical_name: The chosen primary name.
        all_names: All known names including canonical and aliases.
        entity_type: Entity category (character, location, etc.).
        contexts: Source text contexts collected from each occurrence.
        source_chapters: Chapters where this entity appeared.
        source_book: Title of the source book.
        total_occurrences: Sum of occurrence counts across all raw entities.
    """
    
    canonical_name: str
    all_names: list[str]  # includes canonical + all aliases
    entity_type: str
    contexts: list[str]  # all source contexts
    source_chapters: list[str]
    source_book: str
    total_occurrences: int = 1


@dataclass
class AliasGroup:
    """Group of names that refer to the same entity.

    Attributes:
        canonical_name: Chosen primary name for the group.
        aliases: Other names in the group.
        confidence: Confidence score (0–1) of the grouping.
    """
    
    canonical_name: str
    aliases: list[str]
    confidence: float


def resolve_aliases_llm(
    names: list[str],
    entity_type: str,
    book_title: str,
) -> list[AliasGroup]:
    """Use LLM to group names that refer to the same entity.

    Primary method for alias resolution. Falls back gracefully on failure.

    Args:
        names: List of entity name strings to group.
        entity_type: The entity category (e.g. ``"character"``).
        book_title: Title of the source book, for LLM context.

    Returns:
        List of ``AliasGroup`` instances. May be empty if the LLM fails.
    """
    if len(names) <= 1:
        return [AliasGroup(canonical_name=names[0], aliases=[], confidence=1.0)] if names else []
    
    names_list = "\n".join(f"- {name}" for name in names)
    
    prompt = ALIAS_RESOLUTION_USER_PROMPT_TEMPLATE.format(
        entity_type=entity_type,
        book_title=book_title,
        names_list=names_list,
    )
    
    for attempt in range(MAX_RETRIES):
        try:
            response = call_ollama(prompt, ALIAS_RESOLUTION_SYSTEM_PROMPT)
            parsed = parse_json_response(response)
            
            if parsed and "groups" in parsed:
                groups = []
                for group_data in parsed["groups"]:
                    if not group_data.get("canonical_name"):
                        continue
                    
                    groups.append(AliasGroup(
                        canonical_name=group_data["canonical_name"],
                        aliases=group_data.get("aliases", []),
                        confidence=group_data.get("confidence", 0.9),
                    ))
                
                return groups
        
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                print(f"Warning: LLM alias resolution failed: {e}")
                return []
    
    return []


def resolve_aliases_fuzzy(names: list[str], threshold: int = FUZZY_MATCH_THRESHOLD) -> list[AliasGroup]:
    """Group similar names using fuzzy string matching.

    Conservative fallback when the LLM method fails or is disabled.
    Uses token-sort ratio from ``rapidfuzz``.

    Args:
        names: List of entity name strings to group.
        threshold: Minimum fuzzy-match score (0–100) to consider a match.

    Returns:
        List of ``AliasGroup`` instances covering all input names.
    """
    if len(names) <= 1:
        return [AliasGroup(canonical_name=names[0], aliases=[], confidence=1.0)] if names else []
    
    groups: list[AliasGroup] = []
    used_names: set[str] = set()
    
    for name in names:
        if name in used_names:
            continue
        
        # Find similar names
        matches = process.extract(
            name,
            [n for n in names if n not in used_names],
            scorer=fuzz.token_sort_ratio,
            limit=10,
        )
        
        # Filter by threshold
        similar = [m[0] for m in matches if m[1] >= threshold and m[0] != name]
        
        if similar:
            # Use longest name as canonical
            all_names = [name] + similar
            canonical = max(all_names, key=len)
            aliases = [n for n in all_names if n != canonical]
            
            groups.append(AliasGroup(
                canonical_name=canonical,
                aliases=aliases,
                confidence=min(m[1] for m in matches if m[0] in similar) / 100.0,
            ))
            
            used_names.update(all_names)
        else:
            groups.append(AliasGroup(
                canonical_name=name,
                aliases=[],
                confidence=1.0,
            ))
            used_names.add(name)
    
    return groups


def merge_entities_by_alias_groups(
    entities: list[RawEntity],
    groups: list[AliasGroup],
) -> list[ResolvedEntity]:
    """Merge raw entities into resolved entities based on alias groups.

    Args:
        entities: Raw entities to merge.
        groups: Alias groups mapping names to canonical names.

    Returns:
        List of ``ResolvedEntity`` with merged aliases, contexts,
        and aggregated occurrence counts.
    """
    # Build lookup: name -> canonical name
    name_to_canonical: dict[str, str] = {}
    for group in groups:
        name_to_canonical[group.canonical_name.lower()] = group.canonical_name
        for alias in group.aliases:
            name_to_canonical[alias.lower()] = group.canonical_name
    
    # Group entities by canonical name
    merged: dict[str, ResolvedEntity] = {}
    
    for entity in entities:
        # Find canonical name (or use original)
        canonical = name_to_canonical.get(entity.name.lower(), entity.name)
        key = (canonical.lower(), entity.entity_type)
        
        if key in merged:
            resolved = merged[key]
            
            # Add names
            if entity.name not in resolved.all_names:
                resolved.all_names.append(entity.name)
            for alias in entity.aliases:
                if alias not in resolved.all_names:
                    resolved.all_names.append(alias)
            
            # Add context
            if entity.context and entity.context not in resolved.contexts:
                resolved.contexts.append(entity.context)
            
            # Add source chapters
            if entity.source_chapter not in resolved.source_chapters:
                resolved.source_chapters.append(entity.source_chapter)
            
            resolved.total_occurrences += entity.occurrence_count
        else:
            all_names = [entity.name] + entity.aliases
            # Use canonical name if different
            if canonical not in all_names:
                all_names.insert(0, canonical)
            
            merged[key] = ResolvedEntity(
                canonical_name=canonical,
                all_names=list(set(all_names)),
                entity_type=entity.entity_type,
                contexts=[entity.context] if entity.context else [],
                source_chapters=[entity.source_chapter],
                source_book=entity.source_book,
                total_occurrences=entity.occurrence_count,
            )
    
    return list(merged.values())


def resolve_entities(
    entities: list[RawEntity],
    book_title: str,
    use_llm: bool = True,
) -> list[ResolvedEntity]:
    """Resolve entity aliases using a hybrid approach.

    1. Primary: LLM-based alias grouping per entity type.
    2. Fallback: Fuzzy string matching for any unresolved names.

    Instrumented with tracing and decision logging.

    Args:
        entities: All raw entities extracted from the book.
        book_title: Title of the source book (passed to the LLM).
        use_llm: If True, try LLM resolution first.

    Returns:
        Fully resolved entities with canonical names and merged metadata.
    """
    from src.observability.tracer import SpanContext, log_decision
    from src.observability import telemetry

    with SpanContext("alias_resolution", entity_count=len(entities)):
        # Group entities by type
        by_type: dict[str, list[RawEntity]] = {}
        for entity in entities:
            if entity.entity_type not in by_type:
                by_type[entity.entity_type] = []
            by_type[entity.entity_type].append(entity)

        all_resolved: list[ResolvedEntity] = []

        for entity_type, type_entities in by_type.items():
            print(f"  Resolving aliases for {len(type_entities)} {entity_type} entities...")

            # Get all names
            all_names = set()
            for entity in type_entities:
                all_names.add(entity.name)
                all_names.update(entity.aliases)

            names_list = list(all_names)

            # Primary: LLM resolution
            groups: list[AliasGroup] = []
            method_used = "none"
            if use_llm and len(names_list) > 1:
                groups = resolve_aliases_llm(names_list, entity_type, book_title)
                method_used = "llm" if groups else "fuzzy_fallback"

            # Track which names are resolved
            resolved_names = set()
            for group in groups:
                resolved_names.add(group.canonical_name)
                resolved_names.update(group.aliases)

            # Fallback: Fuzzy matching for unresolved names
            unresolved = [n for n in names_list if n not in resolved_names]
            if unresolved:
                fuzzy_groups = resolve_aliases_fuzzy(unresolved)
                groups.extend(fuzzy_groups)
                if not use_llm or method_used == "fuzzy_fallback":
                    method_used = "fuzzy"

            # Log the resolution method decision
            log_decision(
                category="alias_resolution",
                options_considered=["llm", "fuzzy", "none"],
                option_chosen=method_used,
                reason=f"{len(names_list)} names for {entity_type}, "
                       f"{len(groups)} groups formed, "
                       f"{len(unresolved)} fell through to fuzzy",
                constraints=[f"use_llm={use_llm}"],
                entity_type=entity_type,
                names_count=len(names_list),
                groups_count=len(groups),
            )

            # Merge entities
            resolved = merge_entities_by_alias_groups(type_entities, groups)
            all_resolved.extend(resolved)

            telemetry.increment("entities_resolved", len(resolved))
            print(f"    → {len(resolved)} resolved entities after alias merging")

        return all_resolved
