"""Entity Cleanup - Clean corpus using wiki JSON as source of truth"""
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from rapidfuzz import fuzz

from src.config import CORPUS_DIR, DATA_DIR


# Patterns that indicate low-quality/generic entity names
NOISE_PATTERNS = [
    r"^a_",              # "a_woman", "a_talking_cat"
    r"^the_",            # "the_man", "the_monster"
    r"^an_",             # "an_orc"
    r"^\d+_",            # "35_years_old_woman"
    r"_level_\d+",       # "goblin_level_2"
    r"^crawler_\d+",     # "crawler_12330671"
    r"^level_\d+",       # "level_7_boss"
    r"^group_of_",       # "group_of_ten..."
    r"^pair_of_",        # "pair_of_small..."
    r"^two_",            # "two_humans"
    r"^three_",          # "three_crawlers"
]

# Minimum quality thresholds
MIN_NAME_LENGTH = 3
MIN_DESCRIPTION_LENGTH = 100


@dataclass
class EntityFile:
    """Represents a corpus entity markdown file.

    Attributes:
        path: Filesystem path to the ``.md`` file.
        name: Filename (including extension).
        entity_type: Entity category.
        content: Raw file content.
        description: First paragraph after frontmatter.
        aliases: Known aliases.
        appearances: Chapters where entity appeared.
        priority: Classification tier.
        wiki_match: Matched wiki canonical name, if any.
        quality_score: Heuristic quality score (0–100).
    """
    path: Path
    name: str
    entity_type: str
    content: str
    
    # Extracted metadata
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    appearances: list[str] = field(default_factory=list)
    
    # Classification
    priority: Literal["canonical", "major", "minor", "noise"] = "noise"
    wiki_match: str | None = None
    quality_score: float = 0.0
    
    def __post_init__(self):
        self._parse_content()
    
    def _parse_content(self):
        """Extract metadata from markdown content"""
        # Extract description (first paragraph after frontmatter)
        lines = self.content.split("\n")
        in_frontmatter = False
        description_lines = []
        
        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                # Parse aliases from frontmatter
                if line.startswith("aliases:"):
                    # Simple YAML list parsing
                    pass
                continue
            if line.strip() and not line.startswith("#"):
                description_lines.append(line.strip())
        
        self.description = " ".join(description_lines[:3])  # First 3 lines


@dataclass
class WikiEntity:
    """Represents a canonical entity from the wiki JSON.

    Attributes:
        name: Canonical entity name.
        description: Brief description text.
        entity_type: Entity category.
    """
    name: str
    description: str
    entity_type: str


def load_wiki_entities(wiki_path: Path) -> list[WikiEntity]:
    """Load canonical entities from the wiki JSON file.

    Args:
        wiki_path: Path to the wiki JSON.

    Returns:
        List of ``WikiEntity`` instances across all categories.
    """
    with open(wiki_path) as f:
        data = json.load(f)
    
    entities = []
    
    # Characters
    for char in data.get("characters", []):
        entities.append(WikiEntity(
            name=char["name"],
            description=char.get("description", ""),
            entity_type="character",
        ))
    
    # Locations
    for loc in data.get("locations_or_places", []):
        entities.append(WikiEntity(
            name=loc["name"],
            description=loc.get("description", ""),
            entity_type="location",
        ))
    
    # Factions
    for faction in data.get("factions", []):
        entities.append(WikiEntity(
            name=faction["name"],
            description=faction.get("description", ""),
            entity_type="faction",
        ))
    
    # Timeline events
    for event in data.get("timeline_events", []):
        entities.append(WikiEntity(
            name=event["event"],
            description=event.get("description", ""),
            entity_type="timeline",
        ))
    
    return entities


def normalize_name(name: str) -> str:
    """Normalize an entity name for comparison.

    Strips ``.md`` extension, replaces underscores with spaces,
    lowercases, and collapses whitespace.

    Args:
        name: Raw entity name or filename.

    Returns:
        Normalized lowercase name string.
    """
    # Remove file extension
    name = name.replace(".md", "")
    # Replace underscores with spaces
    name = name.replace("_", " ")
    # Lowercase
    name = name.lower()
    # Remove extra whitespace
    name = " ".join(name.split())
    return name


def is_noise_name(filename: str) -> bool:
    """Check if a filename matches known noise patterns.

    Args:
        filename: Entity filename to test.

    Returns:
        True if the filename matches any pattern in ``NOISE_PATTERNS``.
    """
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, filename, re.IGNORECASE):
            return True
    return False


def match_to_wiki(entity: EntityFile, wiki_entities: list[WikiEntity], threshold: int = 80) -> WikiEntity | None:
    """Match a corpus entity to a wiki entity using fuzzy matching.

    Tries exact match first, then falls back to token-ratio scoring.

    Args:
        entity: Corpus entity to match.
        wiki_entities: All wiki entities to search.
        threshold: Minimum fuzzy score (0–100) to accept.

    Returns:
        Matched ``WikiEntity`` or ``None``.
    """
    normalized_name = normalize_name(entity.name)
    
    best_match = None
    best_score = 0
    
    for wiki_entity in wiki_entities:
        if wiki_entity.entity_type != entity.entity_type:
            continue
        
        wiki_normalized = normalize_name(wiki_entity.name)
        
        # Try exact match first
        if normalized_name == wiki_normalized:
            return wiki_entity
        
        # Fuzzy match
        score = fuzz.ratio(normalized_name, wiki_normalized)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = wiki_entity
    
    return best_match


def calculate_quality_score(entity: EntityFile) -> float:
    """Calculate a heuristic quality score for an entity (0–100).

    Scores are based on name quality (30 pts), description length
    (40 pts), and total content length (30 pts).

    Args:
        entity: Entity file to evaluate.

    Returns:
        Quality score between 0 and 100.
    """
    score = 0.0
    
    # Name quality (max 30 points)
    name = entity.name.replace(".md", "").replace("_", " ")
    
    # Proper capitalization suggests named entity
    if name[0].isupper():
        score += 15
    
    # Longer names are often more specific
    if len(name) > 10:
        score += 10
    elif len(name) > 5:
        score += 5
    
    # No noise patterns
    if not is_noise_name(entity.name):
        score += 5
    
    # Description quality (max 40 points)
    desc_len = len(entity.description)
    if desc_len > 500:
        score += 40
    elif desc_len > 200:
        score += 30
    elif desc_len > MIN_DESCRIPTION_LENGTH:
        score += 20
    elif desc_len > 50:
        score += 10
    
    # Content quality (max 30 points)
    content_len = len(entity.content)
    if content_len > 1000:
        score += 30
    elif content_len > 500:
        score += 20
    elif content_len > 200:
        score += 10
    
    return score


def classify_entity(entity: EntityFile, wiki_entities: list[WikiEntity]) -> EntityFile:
    """Classify an entity as canonical, major, minor, or noise.

    Wiki-matched entities are always canonical. Others are scored
    heuristically and binned by quality.

    Args:
        entity: Entity to classify (mutated in place).
        wiki_entities: Wiki entities to match against.

    Returns:
        The same ``EntityFile`` with updated ``priority``,
        ``wiki_match``, and ``quality_score``.
    """
    # Check wiki match first
    wiki_match = match_to_wiki(entity, wiki_entities)
    if wiki_match:
        entity.wiki_match = wiki_match.name
        entity.priority = "canonical"
        entity.quality_score = 100.0
        return entity
    
    # Calculate quality score
    entity.quality_score = calculate_quality_score(entity)
    
    # Classify based on score and patterns
    if is_noise_name(entity.name):
        entity.priority = "noise"
    elif entity.quality_score >= 70:
        entity.priority = "major"
    elif entity.quality_score >= 40:
        entity.priority = "minor"
    else:
        entity.priority = "noise"
    
    return entity


def scan_corpus(corpus_dir: Path) -> list[EntityFile]:
    """Scan corpus directory for all entity markdown files.

    Args:
        corpus_dir: Root corpus directory containing type subdirectories.

    Returns:
        List of ``EntityFile`` instances found under the corpus.
    """
    entities = []
    
    type_dirs = {
        "characters": "character",
        "locations": "location", 
        "factions": "faction",
        "timeline": "timeline",
    }
    
    for dir_name, entity_type in type_dirs.items():
        type_dir = corpus_dir / dir_name
        if not type_dir.exists():
            continue
        
        for md_file in type_dir.glob("*.md"):
            if md_file.name.startswith("_"):
                continue  # Skip index files
            
            try:
                content = md_file.read_text()
                entities.append(EntityFile(
                    path=md_file,
                    name=md_file.name,
                    entity_type=entity_type,
                    content=content,
                ))
            except Exception as e:
                print(f"Warning: Could not read {md_file}: {e}")
    
    return entities


def archive_entities(entities: list[EntityFile], archive_dir: Path, dry_run: bool = True) -> int:
    """Move noise entities to a dated archive folder.

    Args:
        entities: All classified entities (only ``noise`` are moved).
        archive_dir: Root directory for archived entities.
        dry_run: If True, preview only — do not move files.

    Returns:
        Number of entities archived (or that would be archived).
    """
    if not entities:
        return 0
    
    # Create dated archive folder
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / date_str
    
    archived_count = 0
    
    for entity in entities:
        if entity.priority != "noise":
            continue
        
        # Determine archive subfolder
        type_folder = archive_path / f"{entity.entity_type}s"
        dest_path = type_folder / entity.name
        
        if dry_run:
            print(f"  [DRY-RUN] Would archive: {entity.path.name}")
        else:
            type_folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entity.path), str(dest_path))
        
        archived_count += 1
    
    return archived_count


def run_cleanup(
    corpus_dir: Path = CORPUS_DIR,
    wiki_path: Path = DATA_DIR / "book1_wiki.json",
    dry_run: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Run the entity cleanup process.
    
    Args:
        corpus_dir: Path to corpus directory
        wiki_path: Path to wiki JSON file
        dry_run: If True, only preview changes
        verbose: If True, print detailed output
    
    Returns:
        Summary statistics
    """
    print(f"\n{'='*60}")
    print("🧹 Entity Cleanup")
    print(f"{'='*60}")
    print(f"Corpus: {corpus_dir}")
    print(f"Wiki: {wiki_path}")
    print(f"Mode: {'DRY-RUN (no changes)' if dry_run else 'LIVE (will move files)'}")
    print()
    
    # Load wiki entities
    wiki_entities = load_wiki_entities(wiki_path)
    print(f"📚 Loaded {len(wiki_entities)} wiki entities")
    
    # Scan corpus
    corpus_entities = scan_corpus(corpus_dir)
    print(f"📁 Found {len(corpus_entities)} corpus entities")
    print()
    
    # Classify all entities
    print("🔍 Classifying entities...")
    for entity in corpus_entities:
        classify_entity(entity, wiki_entities)
    
    # Group by priority
    by_priority = {"canonical": [], "major": [], "minor": [], "noise": []}
    for entity in corpus_entities:
        by_priority[entity.priority].append(entity)
    
    # Print summary
    print(f"\n📊 Classification Results:")
    print(f"  ✅ Canonical (wiki match): {len(by_priority['canonical'])}")
    print(f"  ⭐ Major (high quality):   {len(by_priority['major'])}")
    print(f"  📄 Minor (medium quality): {len(by_priority['minor'])}")
    print(f"  🗑️  Noise (will archive):  {len(by_priority['noise'])}")
    
    if verbose and by_priority['canonical']:
        print(f"\n  Wiki matches found:")
        for e in by_priority['canonical'][:10]:
            print(f"    - {e.name} → {e.wiki_match}")
    
    if verbose and by_priority['noise']:
        print(f"\n  Sample noise entities (first 20):")
        for e in sorted(by_priority['noise'], key=lambda x: x.quality_score)[:20]:
            print(f"    - {e.name} (score: {e.quality_score:.0f})")
    
    # Archive noise entities
    archive_dir = corpus_dir / "archive"
    archived = archive_entities(corpus_entities, archive_dir, dry_run=dry_run)
    
    print(f"\n{'✅ Complete' if not dry_run else '👀 Preview complete'}")
    print(f"  Archived: {archived} entities")
    
    if dry_run:
        print(f"\n💡 Run with --execute to apply changes")
    
    return {
        "total": len(corpus_entities),
        "canonical": len(by_priority["canonical"]),
        "major": len(by_priority["major"]),
        "minor": len(by_priority["minor"]),
        "noise": len(by_priority["noise"]),
        "archived": archived,
    }


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean up entity corpus")
    parser.add_argument("--execute", action="store_true", help="Actually move files (default is dry-run)")
    parser.add_argument("--quiet", action="store_true", help="Less verbose output")
    parser.add_argument("--wiki", type=Path, default=DATA_DIR / "book1_wiki.json", help="Path to wiki JSON")
    parser.add_argument("--corpus", type=Path, default=CORPUS_DIR, help="Path to corpus directory")
    
    args = parser.parse_args()
    
    run_cleanup(
        corpus_dir=args.corpus,
        wiki_path=args.wiki,
        dry_run=not args.execute,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
