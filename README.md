# 📚 Book Content Pipeline

An open-source knowledge extraction pipeline that ingests fantasy books (EPUB) and produces structured JSON output containing characters, locations, factions, timeline events, and their connections — fully instrumented with tracing, telemetry, and idempotency.

## Features

- **EPUB Ingestion** — chapter extraction, text normalization, content hashing
- **NER Extraction** — entity extraction via Ollama with chunked processing
- **Alias Resolution** — hybrid LLM + fuzzy matching deduplication
- **Canonical Summarization** — batched LLM summaries for each entity
- **Connection Graph** — co-occurrence-based entity connections
- **Priority Classification** — wiki-linked tiering (canonical / major / minor)
- **Observability** — tracing, telemetry, progress events, checkpointing, idempotency


## Architecture

```
src/
├── config.py                  # All configuration knobs
├── pipeline.py                # Main orchestrator (CLI entry point)
├── ingestion/
│   ├── epub_parser.py         # EPUB → chapters + metadata
│   └── registry.py            # Ingestion log (skip already-processed books)
├── extraction/
│   ├── ner_extractor.py       # Ollama NER (chunked, instrumented)
│   ├── alias_resolver.py      # LLM + fuzzy alias deduplication
│   └── connections.py         # Co-occurrence connection builder
├── enrichment/
│   ├── summarizer.py          # Batched canonical summarization
│   └── wiki_linker.py         # Wiki JSON matching + priority tiers
├── cleanup/
│   └── entity_cleanup.py      # Noise detection + corpus archival
├── models/
│   └── entities.py            # Pydantic models (Character, Location, Faction, TimelineEvent)
└── observability/
    ├── progress.py            # Semantic progress stages + interrupt support
    ├── tracer.py              # Trace/span/decision/LLM-call logging
    ├── telemetry.py           # Counters, histograms, gauges, timers
    ├── checkpoint.py          # Incremental extraction checkpoints
    └── idempotency.py         # Content-hash deduplication + staleness detection
```

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai/) running locally

```bash
# Pull required models
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
```

## Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

## Usage

### Process a book

```bash
python -m src.pipeline Data/Dungeon_Crawler_Carl_-_Matt_Dinniman.epub
```

### Clear idempotency cache and reprocess

```bash
python -m src.pipeline --clear-cache Data/Dungeon_Crawler_Carl_-_Matt_Dinniman.epub
```

## Output

The pipeline produces a single JSON file per book in `output/`:

```json
{
  "metadata": {
    "book_id": "dungeon_crawler_carl",
    "title": "Dungeon Crawler Carl",
    "author": "Matt Dinniman",
    "trace_id": "a1b2c3d4e5f6",
    "model_versions": { "qwen2.5:7b": "abc123" },
    "chapters": 42,
    "word_count": 120000
  },
  "entities": [
    {
      "entity_id": "char_carl",
      "name": "Carl",
      "type": "character",
      "aliases": ["Crawler Carl"],
      "description": "...",
      "occurrence_count": 350,
      "physical_traits": ["..."],
      "personality_traits": ["..."]
    }
  ],
  "connections": [
    {
      "source_id": "char_carl",
      "target_id": "loc_third_floor",
      "weight": 12,
      "co_occurrence_chapters": ["Chapter 1", "Chapter 5"]
    }
  ],
  "telemetry": {
    "duration_s": 180.5,
    "llm_calls": 45,
    "tokens_prompt": 250000,
    "tokens_completion": 30000
  }
}
```

### Observability Artifacts

Each run also saves to `corpus/metadata/`:

| Artifact | Path | Purpose |
|----------|------|---------|
| Traces | `traces/{trace_id}.json` | Full LLM call + decision log |
| Telemetry | `telemetry/telemetry_*.json` | Counters, histograms, timers |
| Progress | `progress_logs/progress_*.json` | Semantic stage timeline |
| Checkpoint | `extraction_checkpoint.json` | Resume interrupted runs |
| Idempotency | `idempotency_state.json` | Skip already-processed chunks |

## Configuration

All knobs are in [`src/config.py`](src/config.py):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `NER_MODEL` | `qwen2.5:7b` | Model for entity extraction |
| `SUMMARIZER_MODEL` | `llama3.1:8b` | Model for summarization |
| `CHUNK_SIZE` | `24000` | Characters per chunk |
| `CHUNK_OVERLAP` | `400` | Overlap between chunks |
| `FUZZY_MATCH_THRESHOLD` | `85` | Alias matching threshold |
| `SUMMARIZER_BATCH_SIZE` | `5` | Entities per summarization call |
| `CHECKPOINT_INTERVAL` | `5` | Save checkpoint every N chapters |

## Entity Types

| Type | Model Class | Key Fields |
|------|-------------|------------|
| `character` | `Character` | physical_traits, personality_traits, abilities, role, species |
| `location` | `Location` | location_type, environment, architecture, atmosphere |
| `faction` | `Faction` | faction_type, goals, traits, base_location_id |
| `timeline_event` | `TimelineEvent` | event_type, temporal_marker, participants, consequences |

## Testing

```bash
pytest tests/ -v
```

## License

MIT
