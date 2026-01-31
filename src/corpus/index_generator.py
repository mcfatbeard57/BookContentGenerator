"""Index Generator - Create navigable index files for each entity category"""
from pathlib import Path
from collections import defaultdict

from src.config import (
    CORPUS_CHARACTERS_DIR,
    CORPUS_FACTIONS_DIR,
    CORPUS_LOCATIONS_DIR,
    CORPUS_TIMELINE_DIR,
)
from src.enrichment.wiki_linker import parse_entity_frontmatter


def generate_category_index(corpus_dir: Path, category_name: str) -> str:
    """
    Generate a markdown index for a category of entities.
    
    Groups entities by priority and provides links.
    """
    if not corpus_dir.exists():
        return f"# {category_name} Index\n\nNo entities found.\n"
    
    # Group entities by priority
    entities_by_priority: dict[str, list[dict]] = defaultdict(list)
    
    for entity_file in sorted(corpus_dir.glob("*.md")):
        if entity_file.name.startswith("_"):
            continue
        
        frontmatter = parse_entity_frontmatter(entity_file)
        if not frontmatter:
            continue
        
        priority = frontmatter.get("priority", "minor")
        entities_by_priority[priority].append({
            "name": frontmatter.get("name", entity_file.stem),
            "filename": entity_file.name,
            "occurrence_count": frontmatter.get("occurrence_count", 0),
            "is_wiki_linked": frontmatter.get("is_wiki_linked", False),
            "wiki_entry_name": frontmatter.get("wiki_entry_name"),
        })
    
    # Build markdown
    lines = [
        f"# {category_name} Index",
        "",
        f"Total entities: {sum(len(v) for v in entities_by_priority.values())}",
        "",
    ]
    
    # Canonical entities (from wiki)
    canonical = entities_by_priority.get("canonical", [])
    if canonical:
        lines.extend([
            "## 🌟 Canonical (from Wiki)",
            "",
            "These are the major entities from the official wiki.",
            "",
        ])
        for entity in sorted(canonical, key=lambda x: x["name"]):
            wiki_tag = f' *(wiki: {entity["wiki_entry_name"]})*' if entity["wiki_entry_name"] else ""
            lines.append(f"- [{entity['name']}]({entity['filename']}){wiki_tag}")
        lines.append("")
    
    # Major entities
    major = entities_by_priority.get("major", [])
    if major:
        lines.extend([
            "## ⭐ Major Characters",
            "",
            "Frequently mentioned entities (10+ occurrences).",
            "",
        ])
        for entity in sorted(major, key=lambda x: -x["occurrence_count"])[:50]:
            lines.append(f"- [{entity['name']}]({entity['filename']}) ({entity['occurrence_count']} mentions)")
        if len(major) > 50:
            lines.append(f"\n*...and {len(major) - 50} more major entities*")
        lines.append("")
    
    # Minor entities (summarized)
    minor = entities_by_priority.get("minor", [])
    if minor:
        lines.extend([
            "## Minor Entities",
            "",
            f"{len(minor)} minor entities extracted from text.",
            "",
            "<details>",
            "<summary>Click to expand full list</summary>",
            "",
        ])
        for entity in sorted(minor, key=lambda x: x["name"]):
            lines.append(f"- [{entity['name']}]({entity['filename']})")
        lines.extend([
            "",
            "</details>",
            "",
        ])
    
    return "\n".join(lines)


def generate_all_indexes() -> list[Path]:
    """Generate index files for all entity categories"""
    categories = [
        (CORPUS_CHARACTERS_DIR, "Characters"),
        (CORPUS_LOCATIONS_DIR, "Locations"),
        (CORPUS_FACTIONS_DIR, "Factions"),
        (CORPUS_TIMELINE_DIR, "Timeline Events"),
    ]
    
    written_files = []
    
    for corpus_dir, category_name in categories:
        index_content = generate_category_index(corpus_dir, category_name)
        index_path = corpus_dir / "_index.md"
        index_path.write_text(index_content, encoding="utf-8")
        written_files.append(index_path)
        print(f"  → Generated {index_path}")
    
    return written_files


if __name__ == "__main__":
    print("Generating index files...")
    generate_all_indexes()
    print("Done!")
