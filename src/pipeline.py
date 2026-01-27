"""Pipeline - Main orchestrator for the corpus builder"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from src.config import CORPUS_DIR, DATA_DIR
from src.corpus.graph_builder import build_graph, load_graph, save_graph
from src.corpus.writer import write_all_entities
from src.enrichment.summarizer import summarize_all_entities
from src.extraction.alias_resolver import resolve_entities
from src.extraction.ner_extractor import extract_entities_from_book
from src.ingestion.epub_parser import parse_epub, ParsedBook
from src.ingestion.registry import (
    create_book_record,
    load_registry,
    save_registry,
    IngestionRegistry,
)
from src.rag.index import build_entity_index, load_or_create_index


def process_book(
    book_path: Path,
    registry: IngestionRegistry,
    skip_if_processed: bool = True,
) -> tuple[list, bool]:
    """
    Process a single book through the full pipeline.
    
    Returns:
        Tuple of (entities list, was_processed bool)
    """
    print(f"\n{'=' * 60}")
    print(f"Processing: {book_path.name}")
    print(f"{'=' * 60}")
    
    # Step 1: Parse EPUB
    print("\n[1/6] Parsing EPUB...")
    parsed_book = parse_epub(book_path)
    print(f"  → Title: {parsed_book.title}")
    print(f"  → Author: {parsed_book.author}")
    print(f"  → Chapters: {len(parsed_book.chapters)}")
    print(f"  → Words: {parsed_book.total_words:,}")
    print(f"  → Hash: {parsed_book.content_hash[:16]}...")
    
    # Step 2: Check if already processed
    if skip_if_processed and registry.is_processed(parsed_book.content_hash):
        existing = registry.get_record_by_hash(parsed_book.content_hash)
        print(f"\n  ⏭ Book already processed on {existing.processed_at}")
        print(f"    Entities extracted: {existing.entities_extracted}")
        return [], False
    
    # Step 3: Extract entities
    print("\n[2/6] Extracting entities...")
    extraction_result = extract_entities_from_book(parsed_book)
    print(f"  → Found {len(extraction_result.entities)} raw entities")
    if extraction_result.errors:
        print(f"  → Errors: {len(extraction_result.errors)}")
    
    # Step 4: Resolve aliases
    print("\n[3/6] Resolving aliases...")
    resolved_entities = resolve_entities(
        extraction_result.entities,
        parsed_book.title,
        use_llm=True,
    )
    print(f"  → Resolved to {len(resolved_entities)} unique entities")
    
    # Step 5: Generate canonical summaries
    print("\n[4/6] Generating canonical summaries...")
    canonical_entities = summarize_all_entities(resolved_entities, parsed_book.book_id)
    
    # Step 6: Record in registry
    record = create_book_record(
        book_id=parsed_book.book_id,
        file_path=book_path,
        content_hash=parsed_book.content_hash,
        title=parsed_book.title,
        author=parsed_book.author,
        chapter_count=len(parsed_book.chapters),
        word_count=parsed_book.total_words,
    )
    record.entities_extracted = len(canonical_entities)
    registry.add_record(record)
    
    return canonical_entities, True


def run_pipeline(
    input_paths: list[Path],
    force_reprocess: bool = False,
) -> None:
    """
    Run the full pipeline on input books.
    
    Args:
        input_paths: List of EPUB file paths
        force_reprocess: If True, reprocess even already-processed books
    """
    start_time = datetime.now()
    
    print("\n" + "=" * 60)
    print("📚 Book → Canonical Corpus Builder")
    print("=" * 60)
    print(f"Input files: {len(input_paths)}")
    print(f"Force reprocess: {force_reprocess}")
    
    # Load existing state
    print("\nLoading existing state...")
    registry = load_registry()
    print(f"  → {len(registry.processed_books)} books in registry")
    
    graph = load_graph()
    print(f"  → {len(graph.nodes)} nodes, {len(graph.edges)} edges in graph")
    
    # Process each book
    all_entities = []
    books_processed = 0
    
    for book_path in input_paths:
        if not book_path.exists():
            print(f"\nWarning: File not found: {book_path}")
            continue
        
        entities, was_processed = process_book(
            book_path,
            registry,
            skip_if_processed=not force_reprocess,
        )
        
        if was_processed:
            all_entities.extend(entities)
            books_processed += 1
    
    if not all_entities:
        print("\n✅ No new entities to process.")
        if books_processed == 0:
            print("   All books were already processed. Use --force to reprocess.")
        return
    
    # Write corpus files
    print(f"\n[5/6] Writing corpus files...")
    written_paths = write_all_entities(all_entities)
    
    # Update graph
    print(f"\n[6/6] Updating knowledge graph...")
    for entity in all_entities:
        from src.corpus.graph_builder import add_entity_to_graph
        add_entity_to_graph(graph, entity)
    
    # Infer relationships
    from src.corpus.graph_builder import infer_relationships
    for record in registry.processed_books.values():
        infer_relationships(graph, all_entities, record.book_id)
    
    # Save everything
    print("\nSaving state...")
    save_registry(registry)
    print("  → Registry saved")
    
    save_graph(graph)
    print("  → Graph saved")
    
    # Build/update embeddings index
    print("\nBuilding embeddings index...")
    try:
        entity_index = build_entity_index(all_entities)
        entity_index.save()
        print("  → Index saved")
    except Exception as e:
        print(f"  → Warning: Could not build index: {e}")
    
    # Summary
    elapsed = datetime.now() - start_time
    print("\n" + "=" * 60)
    print("✅ Pipeline Complete")
    print("=" * 60)
    print(f"Books processed: {books_processed}")
    print(f"Entities created: {len(all_entities)}")
    print(f"Files written: {len(written_paths)}")
    print(f"Graph nodes: {len(graph.nodes)}")
    print(f"Graph edges: {len(graph.edges)}")
    print(f"Time elapsed: {elapsed}")
    print(f"\nCorpus location: {CORPUS_DIR}")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Book → Canonical Corpus Builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--input", "-i",
        type=Path,
        nargs="+",
        help="EPUB file(s) to process. If not specified, processes all EPUBs in Data/",
    )
    
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force reprocessing of already-processed books",
    )
    
    args = parser.parse_args()
    
    # Determine input files
    if args.input:
        input_paths = args.input
    else:
        # Default: all EPUBs in Data directory
        input_paths = list(DATA_DIR.glob("*.epub"))
        if not input_paths:
            print(f"No EPUB files found in {DATA_DIR}")
            sys.exit(1)
    
    # Run pipeline
    run_pipeline(input_paths, force_reprocess=args.force)


if __name__ == "__main__":
    main()
