"""Book Content Pipeline - Simplified

Book → Chunk → LLM → NER → Connections/Clusters → output JSON

Fully instrumented with:
- Progress events (Layer 3)
- Idempotency (Layer 5) 
- Traceability (Layer 7)
- Telemetry
"""
import json
from datetime import datetime
from pathlib import Path

from src.config import CORPUS_METADATA_DIR, OUTPUT_DIR
from src.enrichment.summarizer import summarize_all_entities
from src.extraction.alias_resolver import resolve_entities
from src.extraction.connections import build_connections
from src.extraction.ner_extractor import extract_entities_from_book
from src.ingestion.epub_parser import parse_epub
from src.observability.progress import (
    ProgressStage,
    emit_progress,
    reset_progress,
    save_progress_log,
)
from src.observability.tracer import (
    SpanContext,
    end_trace,
    save_trace,
    start_trace,
)
from src.observability import telemetry


def _query_model_versions() -> dict[str, str]:
    """Query Ollama for exact model digests.

    Used for replayability — records which model version produced
    each result.

    Returns:
        Dict mapping model name to truncated digest string.
    """
    import httpx
    from src.config import NER_MODEL, OLLAMA_BASE_URL, SUMMARIZER_MODEL
    from src.observability.tracer import record_model_version

    versions = {}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                for model in resp.json().get("models", []):
                    name = model.get("name", "")
                    digest = model.get("digest", "")[:12]
                    versions[name] = digest
                    record_model_version(name, digest)
    except Exception:
        pass  # Non-critical: best-effort version recording

    return versions


def run_pipeline(epub_path: str | Path) -> Path:
    """
    Run the simplified content extraction pipeline.
    
    Book → Chunk → LLM → NER → Connections → JSON
    
    Args:
        epub_path: Path to the EPUB file to process
        
    Returns:
        Path to the output JSON file
    """
    epub_path = Path(epub_path)
    
    # Reset state
    reset_progress()
    telemetry.reset_telemetry()
    telemetry.start_timer("pipeline_total")
    
    # Start trace
    trace_id = start_trace(metadata={
        "epub_path": str(epub_path),
        "started_at": datetime.now().isoformat(),
    })

    model_versions = _query_model_versions()

    print(f"\n{'='*60}")
    print(f"📚 Book Content Pipeline")
    print(f"{'='*60}")
    print(f"Input: {epub_path.name}")
    print(f"Trace: {trace_id}")
    print()

    try:
        # ── Step 1: Parse EPUB ─────────────────────────────────────
        emit_progress(
            stage=ProgressStage.LOADING_BOOK,
            current=0, total=6,
            message=f"Loading {epub_path.name}",
        )

        with SpanContext("parse_epub", file=epub_path.name):
            book = parse_epub(str(epub_path))

        emit_progress(
            stage=ProgressStage.ANALYZING_STRUCTURE,
            current=1, total=6,
            message=f"Found {len(book.chapters)} chapters, {book.total_words:,} words",
        )
        print(f"📖 Parsed: {book.title} by {book.author}")
        print(f"   {len(book.chapters)} chapters, {book.total_words:,} words\n")

        # ── Step 2 & 3: Chunk + LLM NER ───────────────────────────
        emit_progress(
            stage=ProgressStage.EXTRACTING_CHARACTERS_AND_ENTITIES,
            current=2, total=6,
            message="Extracting entities via NER",
        )

        with SpanContext("entity_extraction"):
            extraction_result = extract_entities_from_book(book)

        telemetry.increment("chapters_processed", extraction_result.chapters_processed)
        print()

        # ── Step 4: Alias Resolution ───────────────────────────────
        emit_progress(
            stage=ProgressStage.RESOLVING_DUPLICATE_NAMES,
            current=3, total=6,
            message=f"Resolving aliases for {len(extraction_result.entities)} entities",
        )

        with SpanContext("alias_resolution"):
            resolved_entities = resolve_entities(
                extraction_result.entities,
                book.title,
            )

        print(f"\n✅ Resolved to {len(resolved_entities)} unique entities\n")

        # ── Step 5: Summarization ──────────────────────────────────
        emit_progress(
            stage=ProgressStage.GENERATING_DESCRIPTIONS,
            current=4, total=6,
            message=f"Generating descriptions for {len(resolved_entities)} entities",
        )

        with SpanContext("summarization"):
            summarized_entities = summarize_all_entities(
                resolved_entities,
                book.book_id,
            )

        print()

        # ── Step 6: Connection Clustering ──────────────────────────
        emit_progress(
            stage=ProgressStage.BUILDING_CONNECTIONS,
            current=5, total=6,
            message="Building entity connections from co-occurrence",
        )

        with SpanContext("connection_clustering"):
            connections = build_connections(
                extraction_result.entity_chunk_map,
                min_weight=2,  # At least 2 co-occurrences
            )

        print(f"🔗 Built {len(connections)} connections\n")

        # ── Step 7: Output JSON ────────────────────────────────────
        emit_progress(
            stage=ProgressStage.WRITING_OUTPUT,
            current=6, total=6,
            message="Writing output JSON",
        )

        output_path = _write_output_json(
            book=book,
            entities=summarized_entities,
            connections=connections,
            trace_id=trace_id,
            model_versions=model_versions,
        )

        # ── Done ──────────────────────────────────────────────────
        telemetry.stop_timer("pipeline_total")

        emit_progress(
            stage=ProgressStage.COMPLETE,
            current=6, total=6,
            message=f"Output: {output_path.name}",
        )

        # Save observability artifacts
        emit_progress(
            stage=ProgressStage.SAVING_STATE,
            current=6, total=6,
            message="Saving traces and telemetry",
            quiet=True,
        )

        trace = end_trace()
        save_trace(trace)
        save_progress_log(trace_id)
        telemetry.save_telemetry(trace_id)

        _print_summary(output_path, summarized_entities, connections, trace_id)

        return output_path

    except Exception as e:
        telemetry.record_error("pipeline", str(e), fatal=True)
        telemetry.stop_timer("pipeline_total")

        trace = end_trace()
        if trace:
            save_trace(trace)
        save_progress_log(trace_id)
        telemetry.save_telemetry(trace_id)

        raise


def _write_output_json(
    book,
    entities: list,
    connections: list,
    trace_id: str,
    model_versions: dict,
) -> Path:
    """Serialize pipeline results to a JSON file.

    Args:
        book: The parsed book (provides metadata).
        entities: Enriched entity instances.
        connections: Connection objects.
        trace_id: Active trace identifier.
        model_versions: Model name → digest mapping.

    Returns:
        Path to the written JSON file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{book.book_id}_result.json"

    # Build entity dicts
    entity_dicts = [entity.to_output_dict() for entity in entities]

    output_data = {
        "metadata": {
            "book_id": book.book_id,
            "title": book.title,
            "author": book.author,
            "trace_id": trace_id,
            "processed_at": datetime.now().isoformat(),
            "model_versions": model_versions,
            "chapters": len(book.chapters),
            "word_count": book.total_words,
        },
        "entities": entity_dicts,
        "connections": [c.to_dict() for c in connections],
        "telemetry": telemetry.get_summary(),
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"💾 Output: {output_path}")
    return output_path


def _print_summary(
    output_path: Path,
    entities: list,
    connections: list,
    trace_id: str,
) -> None:
    """Print a human-readable pipeline completion summary.

    Args:
        output_path: Path to the output JSON.
        entities: Final entity list.
        connections: Connection list.
        trace_id: Trace identifier.
    """
    summary = telemetry.get_summary()

    print(f"\n{'='*60}")
    print(f"✅ Pipeline Complete")
    print(f"{'='*60}")
    print(f"  Output:      {output_path}")
    print(f"  Entities:    {len(entities)}")
    print(f"  Connections: {len(connections)}")
    print(f"  Duration:    {summary['duration_s']:.1f}s")
    print(f"  LLM Calls:   {summary['llm_calls']}")
    print(f"  Tokens:      {summary['tokens_prompt'] + summary['tokens_completion']:,}")
    print(f"  Errors:      {summary['errors']}")
    print(f"  Trace ID:    {trace_id}")
    print(f"{'='*60}\n")


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Book Content Pipeline: Extract entities and connections from EPUB files"
    )
    parser.add_argument(
        "epub_path",
        type=Path,
        help="Path to the EPUB file to process",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear idempotency cache before running",
    )

    args = parser.parse_args()

    if args.clear_cache:
        from src.observability.idempotency import clear_all
        clear_all()

    if not args.epub_path.exists():
        print(f"Error: File not found: {args.epub_path}")
        return

    output_path = run_pipeline(args.epub_path)
    print(f"Done! Output: {output_path}")


if __name__ == "__main__":
    main()
