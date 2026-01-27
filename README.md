# 📚 Book → Canonical Corpus Builder

An open-source, incremental knowledge extraction pipeline that ingests fantasy books (EPUB) and produces an LLM-ready corpus of characters, locations, factions, and timeline events.

## Features

- **EPUB Ingestion**: Parse EPUB files with chapter extraction and text normalization
- **Entity Extraction**: NER via Ollama (qwen2.5:7b-instruct)
- **Alias Resolution**: Hybrid LLM + fuzzy matching approach
- **Canonical Summarization**: Generate consistent descriptions (llama3.1:8b-instruct)
- **Knowledge Graph**: JSON-based graph with relationship inference
- **RAG Support**: FAISS index with nomic-embed-text embeddings
- **Incremental Processing**: Hash-based tracking, idempotent updates

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai/) running locally with:
  - `qwen2.5:7b-instruct`
  - `llama3.1:8b-instruct`
  - `nomic-embed-text`

```bash
# Install Ollama models
ollama pull qwen2.5:7b-instruct
ollama pull llama3.1:8b-instruct
ollama pull nomic-embed-text
```

## Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

## Usage

### Process a single book

```bash
python -m src.pipeline --input Data/Dungeon_Crawler_Carl_-_Matt_Dinniman.epub
```

### Process all books in Data/

```bash
python -m src.pipeline
```

### Force reprocessing

```bash
python -m src.pipeline --force
```

## Output Structure

```
corpus/
├── metadata/
│   └── ingestion_log.json      # Processing history
├── characters/
│   └── *.md                    # Character files
├── locations/
│   └── *.md                    # Location files
├── factions/
│   └── *.md                    # Faction files
├── timeline/
│   └── *.md                    # Timeline event files
├── relationships/
└── graph/
    ├── world_graph.json        # Knowledge graph
    └── entity_index.faiss      # Embeddings index
```

## Entity File Format

Each entity is stored as Markdown with YAML front-matter:

```markdown
---
entity_type: character
entity_id: char_example
name: Example Character
aliases:
  - Alias One
sources:
  - source_type: book
    source_id: book_id
last_updated: 2026-01-27
---

## Canonical Description

Brief, canonical description of the entity.

## Physical Traits

- Trait 1
- Trait 2
```

## Testing

```bash
pytest tests/ -v
```

## License

MIT
