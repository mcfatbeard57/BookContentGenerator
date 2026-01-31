"""Wiki Linker - Link extracted entities to wiki JSON for priority classification"""
import json
from pathlib import Path
from typing import Literal

from rapidfuzz import fuzz

from src.config import (
    CORPUS_CHARACTERS_DIR,
    CORPUS_FACTIONS_DIR,
    CORPUS_LOCATIONS_DIR,
    CORPUS_TIMELINE_DIR,
    FUZZY_MATCH_THRESHOLD,
    WIKI_JSON_PATH,
)


# Mapping from wiki JSON keys to entity types
WIKI_KEY_TO_ENTITY_TYPE = {
    "characters": "character",
    "locations_or_places": "location",
    "factions": "faction",
    "timeline_events": "timeline_event",
}


def load_wiki_entries(wiki_path: Path | None = None) -> dict[str, set[str]]:
    """
    Load wiki JSON and extract canonical entity names by type.
    
    Returns:
        Dict mapping entity_type to set of canonical names
    """
    wiki_path = wiki_path or WIKI_JSON_PATH
    
    if not wiki_path.exists():
        print(f"Warning: Wiki file not found at {wiki_path}")
        return {}
    
    with open(wiki_path, "r") as f:
        wiki_data = json.load(f)
    
    entries: dict[str, set[str]] = {
        "character": set(),
        "location": set(),
        "faction": set(),
        "timeline_event": set(),
    }
    
    # Extract characters (can be string or object with 'name' field)
    for char in wiki_data.get("characters", []):
        if isinstance(char, str):
            entries["character"].add(char.lower())
        elif isinstance(char, dict) and "name" in char:
            entries["character"].add(char["name"].lower())
    
    # Extract locations (can be string or object with 'name' field)
    for loc in wiki_data.get("locations_or_places", []):
        if isinstance(loc, str):
            entries["location"].add(loc.lower())
        elif isinstance(loc, dict) and "name" in loc:
            entries["location"].add(loc["name"].lower())
    
    # Extract factions (can be string or object with 'name' field)
    for faction in wiki_data.get("factions", []):
        if isinstance(faction, str):
            entries["faction"].add(faction.lower())
        elif isinstance(faction, dict) and "name" in faction:
            entries["faction"].add(faction["name"].lower())
    
    # Extract timeline events (object with 'event' field)
    for event in wiki_data.get("timeline_events", []):
        if isinstance(event, dict) and "event" in event:
            entries["timeline_event"].add(event["event"].lower())
    
    return entries


def fuzzy_match_name(name: str, canonical_names: set[str], threshold: int = FUZZY_MATCH_THRESHOLD) -> str | None:
    """
    Find best fuzzy match for a name against canonical names.
    
    Returns the matched canonical name if found, None otherwise.
    """
    name_lower = name.lower()
    
    # Exact match first
    if name_lower in canonical_names:
        return name_lower
    
    # Fuzzy match
    best_match = None
    best_score = 0
    
    for canonical in canonical_names:
        # Try ratio match
        score = fuzz.ratio(name_lower, canonical)
        if score > best_score and score >= threshold:
            best_match = canonical
            best_score = score
        
        # Also try partial match for longer names
        partial_score = fuzz.partial_ratio(name_lower, canonical)
        if partial_score > best_score and partial_score >= threshold:
            best_match = canonical
            best_score = partial_score
    
    return best_match


def classify_entity_priority(
    name: str,
    aliases: list[str],
    entity_type: str,
    occurrence_count: int,
    wiki_names: set[str],
) -> tuple[Literal["canonical", "major", "minor"], str | None]:
    """
    Determine priority classification for an entity.
    
    Returns:
        Tuple of (priority, wiki_entry_name or None)
    """
    # Check for wiki match on primary name
    matched = fuzzy_match_name(name, wiki_names)
    if matched:
        return "canonical", matched
    
    # Check aliases for wiki match
    for alias in aliases:
        matched = fuzzy_match_name(alias, wiki_names)
        if matched:
            return "canonical", matched
    
    # Major: high occurrence count (appears frequently in text)
    if occurrence_count >= 10:
        return "major", None
    
    # Default to minor
    return "minor", None


def get_entity_type_dir(entity_type: str) -> Path:
    """Get corpus directory for entity type"""
    type_to_dir = {
        "character": CORPUS_CHARACTERS_DIR,
        "location": CORPUS_LOCATIONS_DIR,
        "faction": CORPUS_FACTIONS_DIR,
        "timeline_event": CORPUS_TIMELINE_DIR,
    }
    return type_to_dir.get(entity_type, CORPUS_CHARACTERS_DIR)


def parse_entity_frontmatter(file_path: Path) -> dict | None:
    """Parse YAML frontmatter from entity file"""
    try:
        content = file_path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None
        
        # Find end of frontmatter
        end_idx = content.find("---", 3)
        if end_idx == -1:
            return None
        
        frontmatter_str = content[3:end_idx].strip()
        
        # Use ruamel.yaml for parsing (already installed)
        from ruamel.yaml import YAML
        import io
        
        ruamel_yaml = YAML()
        return ruamel_yaml.load(io.StringIO(frontmatter_str))
    except Exception as e:
        print(f"Warning: Failed to parse {file_path}: {e}")
        return None


def classify_corpus_entities(
    wiki_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, dict[str, int]]:
    """
    Classify all corpus entities by priority based on wiki matching.
    
    Args:
        wiki_path: Path to wiki JSON file
        dry_run: If True, don't modify files, just report
    
    Returns:
        Stats dict with counts by entity type and priority
    """
    wiki_entries = load_wiki_entries(wiki_path)
    
    stats: dict[str, dict[str, int]] = {}
    
    for entity_type, wiki_names in wiki_entries.items():
        corpus_dir = get_entity_type_dir(entity_type)
        
        if not corpus_dir.exists():
            continue
        
        stats[entity_type] = {"canonical": 0, "major": 0, "minor": 0, "total": 0}
        
        for entity_file in corpus_dir.glob("*.md"):
            if entity_file.name.startswith("_"):
                continue  # Skip index files
            
            frontmatter = parse_entity_frontmatter(entity_file)
            if not frontmatter:
                continue
            
            name = frontmatter.get("name", "")
            aliases = frontmatter.get("aliases", [])
            occurrence_count = frontmatter.get("occurrence_count", 0)
            
            priority, wiki_entry = classify_entity_priority(
                name=name,
                aliases=aliases,
                entity_type=entity_type,
                occurrence_count=occurrence_count,
                wiki_names=wiki_names,
            )
            
            stats[entity_type][priority] += 1
            stats[entity_type]["total"] += 1
            
            if not dry_run:
                # Update the entity file with priority
                update_entity_priority(
                    file_path=entity_file,
                    priority=priority,
                    wiki_entry_name=wiki_entry,
                )
    
    return stats


def update_entity_priority(
    file_path: Path,
    priority: Literal["canonical", "major", "minor"],
    wiki_entry_name: str | None,
) -> None:
    """Update an entity file with priority metadata"""
    content = file_path.read_text(encoding="utf-8")
    
    if not content.startswith("---"):
        return
    
    # Find end of frontmatter
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return
    
    frontmatter_str = content[3:end_idx]
    body = content[end_idx + 3:]
    
    # Parse existing frontmatter with ruamel.yaml
    from ruamel.yaml import YAML
    import io
    
    parse_yaml = YAML()
    frontmatter = parse_yaml.load(io.StringIO(frontmatter_str))
    
    # Update priority fields
    frontmatter["priority"] = priority
    frontmatter["is_wiki_linked"] = wiki_entry_name is not None
    if wiki_entry_name:
        frontmatter["wiki_entry_name"] = wiki_entry_name
    
    # Rewrite file
    from ruamel.yaml import YAML
    import io
    
    ruamel_yaml = YAML()
    ruamel_yaml.default_flow_style = False
    ruamel_yaml.preserve_quotes = True
    ruamel_yaml.indent(mapping=2, sequence=4, offset=2)
    
    stream = io.StringIO()
    ruamel_yaml.dump(frontmatter, stream)
    new_frontmatter = stream.getvalue()
    
    new_content = f"---\n{new_frontmatter}---{body}"
    file_path.write_text(new_content, encoding="utf-8")


def print_classification_stats(stats: dict[str, dict[str, int]]) -> None:
    """Print classification statistics in a readable format"""
    print("\n" + "=" * 60)
    print("Entity Classification Summary")
    print("=" * 60)
    
    total_canonical = 0
    total_major = 0
    total_minor = 0
    total_all = 0
    
    for entity_type, counts in stats.items():
        print(f"\n{entity_type.upper()}")
        print(f"  Canonical: {counts['canonical']:4d}")
        print(f"  Major:     {counts['major']:4d}")
        print(f"  Minor:     {counts['minor']:4d}")
        print(f"  Total:     {counts['total']:4d}")
        
        total_canonical += counts["canonical"]
        total_major += counts["major"]
        total_minor += counts["minor"]
        total_all += counts["total"]
    
    print("\n" + "-" * 60)
    print("TOTALS")
    print(f"  Canonical: {total_canonical:4d}")
    print(f"  Major:     {total_major:4d}")
    print(f"  Minor:     {total_minor:4d}")
    print(f"  Total:     {total_all:4d}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Classify corpus entities by priority")
    parser.add_argument("--dry-run", action="store_true", help="Preview without modifying files")
    args = parser.parse_args()
    
    print("Classifying entities based on wiki...")
    stats = classify_corpus_entities(dry_run=args.dry_run)
    print_classification_stats(stats)
    
    if args.dry_run:
        print("\n[DRY RUN] No files were modified. Run without --dry-run to apply changes.")
