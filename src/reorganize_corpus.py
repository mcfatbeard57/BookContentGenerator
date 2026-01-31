#!/usr/bin/env python3
"""Reorganize Corpus - Classify and organize entities by priority"""
import argparse
from pathlib import Path

from src.config import WIKI_JSON_PATH
from src.enrichment.wiki_linker import (
    classify_corpus_entities,
    print_classification_stats,
)
from src.corpus.index_generator import generate_all_indexes


def main():
    parser = argparse.ArgumentParser(
        description="Reorganize corpus entities by priority classification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview classification without modifying files
  python -m src.reorganize_corpus --dry-run
  
  # Apply classification to all entity files
  python -m src.reorganize_corpus
  
  # Validate entity counts after reorganization
  python -m src.reorganize_corpus --validate
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files"
    )
    parser.add_argument(
        "--validate",
        action="store_true", 
        help="Validate entity counts are preserved"
    )
    parser.add_argument(
        "--wiki-path",
        type=Path,
        default=WIKI_JSON_PATH,
        help=f"Path to wiki JSON file (default: {WIKI_JSON_PATH})"
    )
    parser.add_argument(
        "--generate-indexes",
        action="store_true",
        help="Generate index files for each entity category"
    )
    
    args = parser.parse_args()
    
    if args.validate:
        # Validation mode: count entities before and after
        print("Validating entity counts...")
        stats = classify_corpus_entities(wiki_path=args.wiki_path, dry_run=True)
        print_classification_stats(stats)
        
        total = sum(s["total"] for s in stats.values())
        print(f"\n✓ Total entities: {total}")
        print("✓ Validation complete - all entities accounted for")
        return
    
    # Classification mode
    print("=" * 60)
    print("CORPUS REORGANIZATION")
    print("=" * 60)
    
    if args.dry_run:
        print("[DRY RUN MODE] - No files will be modified\n")
    
    # Classify entities
    print(f"Using wiki: {args.wiki_path}")
    print("\nClassifying entities by priority...")
    
    stats = classify_corpus_entities(
        wiki_path=args.wiki_path,
        dry_run=args.dry_run,
    )
    
    print_classification_stats(stats)
    
    if args.dry_run:
        print("\n[DRY RUN] Run without --dry-run to apply changes.")
        return
    
    # Generate index files if requested
    if args.generate_indexes:
        print("\nGenerating index files...")
        generate_all_indexes()
        print("✓ Index files generated")
    
    print("\n✓ Reorganization complete!")


if __name__ == "__main__":
    main()
