# 📘 PRD — Part 1: Book → Canonical Corpus Builder

## 1. Objective

Build an **open-source, incremental knowledge extraction pipeline** that ingests fantasy books (EPUB format) and external lore sources to produce a **canonical, LLM-ready corpus** representing characters, locations, environments, architecture, and relationships.

The corpus will act as the **single source of truth** for downstream agents (scene generation, image generation, video creation).

---

## 2. Scope (Version 1)

### In Scope

* Parse one or more fantasy books (EPUB)
* Extract and normalize entities:

  * Characters
  * Locations
  * Environments
  * Architecture
* Augment with external fantasy wiki sources
* Build/update a structured corpus
* Support **incremental ingestion** of new books
* Maintain **canonical consistency**

### Out of Scope (v1)

* Scene generation
* Image or video generation
* Multi-language support
* Automatic contradiction resolution beyond priority rules
* Fine-grained timeline inference

---

## 3. Inputs

### Primary Input

* **Books**

  * Format: `EPUB`
  * One or more books
  * Each book has a unique ID (ISBN, hash, or user-defined)

### Secondary Inputs (Optional but supported)

* Fantasy wiki / fandom URLs
* Manually curated lore sources

---

## 4. Outputs

### Primary Output

A **canonical corpus**, stored as **human-readable, LLM-optimized files**, representing extracted knowledge.

### Output Properties

* Deterministic
* Versionable (Git-friendly)
* Incrementally updatable
* Traceable to source

---

## 5. Functional Requirements

### FR-1: EPUB Ingestion

* System shall:

  * Parse EPUB
  * Extract raw text
  * Preserve:

    * chapter boundaries
    * book metadata

---

### FR-2: Incremental Processing

* When a **new book** is added:

  * Previously ingested books **must not be reprocessed**
  * Only new text is parsed
  * Existing entities are reused
  * Graph nodes are:

    * updated **only if new information is found**
    * never duplicated

📌 **Key constraint:**
Corpus updates must be **idempotent**.

---

### FR-3: Entity Extraction (NER)

* Identify:

  * Characters
  * Locations
  * Factions
  * Objects (basic)
* Detect:

  * Aliases
  * First appearance
  * Frequency of occurrence

---

### FR-4: Canonical Entity Resolution

* Merge entities across:

  * books
  * wiki sources
* Resolve using priority:

  1. Book text
  2. Author-approved wiki
  3. Community wiki

---

### FR-5: External Lore Augmentation

* Crawl provided wiki URLs
* Extract structured descriptions:

  * Physical traits
  * Personality
  * Architecture style
  * Environmental tone
* Attribute all data to source

---

### FR-6: Corpus Generation

* For each entity, generate a **canonical description file**
* Descriptions must be:

  * concise
  * non-speculative
  * consistent across runs

---

## 6. Non-Functional Requirements

### NFR-1: Open Source First

* No proprietary APIs
* Must run locally
* Ollama-compatible models only

---

### NFR-2: Determinism

* Same input → same corpus output
* Randomness disabled in extraction/summarization steps

---

### NFR-3: Extensibility

* New entity types can be added without refactor
* Graph schema must be forward-compatible

---

### NFR-4: Performance

* Acceptable for:

  * 1–10 books
  * Tens of wiki pages
* Batch processing preferred over streaming (v1)

---

## 7. Corpus Design

### Format Choice

**Markdown files with YAML front-matter**

#### Rationale

* LLM-friendly
* Git-diffable
* Human-auditable
* Tool-agnostic

---

### Directory Structure

```text
corpus/
├── metadata/
│   └── ingestion_log.json
├── characters/
│   └── harry_dresden.md
├── locations/
│   └── chicago.md
├── environments/
│   └── urban_night.md
├── architecture/
│   └── victorian_buildings.md
├── relationships/
│   └── harry_murphy.md
└── graph/
    └── world_graph.json
```

---

### Entity File Example

```md
---
entity_type: character
entity_id: char_harry_dresden
aliases:
  - Dresden
  - Wizard Dresden
sources:
  - book: storm_front
  - wiki: dresden_files_fandom
last_updated: 2026-01-27
---

## Canonical Description
Harry Dresden is a tall, lean wizard and private investigator operating in Chicago.

## Physical Traits
- Tall
- Lean
- Leather duster

## Personality
- Sarcastic
- Principled

## Abilities
- Evocation
- Thaumaturgy
```

---

## 8. Graph Representation (v1)

### Purpose

* Enable relationship-aware retrieval
* Prevent duplication
* Support Graph-RAG later

### Storage

* JSON (v1)
* Migratable to Neo4j / RDF later

### Example

```json
{
  "nodes": {
    "char_harry_dresden": { "type": "character" },
    "loc_chicago": { "type": "location" }
  },
  "edges": [
    {
      "from": "char_harry_dresden",
      "to": "loc_chicago",
      "relation": "OPERATES_IN"
    }
  ]
}
```

---

## 9. Incremental Update Strategy (Critical)

### Ingestion Log

Maintain a registry:

```json
{
  "processed_books": {
    "storm_front": {
      "hash": "abc123",
      "processed_at": "2026-01-27"
    }
  }
}
```

### On New Run

1. Compute hash of input EPUB
2. Skip books already processed
3. Extract entities from new book
4. Match against existing entity IDs
5. Update:

   * entity files (append missing info)
   * graph edges
6. Never overwrite canonical fields unless:

   * higher-priority source
   * explicit conflict resolution

---

## 10. Success Metrics

* Zero duplicate entity files
* Re-running pipeline causes no corpus drift
* Adding Book N does not alter Book N-1 entities
* Downstream agents can retrieve:

  * a character in <1 lookup
  * relationships without scanning text

---

## 11. Risks & Mitigations

| Risk                   | Mitigation                |
| ---------------------- | ------------------------- |
| Entity alias explosion | Alias registry per entity |
| Wiki contradictions    | Source priority rules     |
| Context bloat          | Canonical summarization   |
| Over-engineering       | Keep graph lightweight v1 |

---

## 12. Future Extensions (Explicitly Planned)

* Timeline agent
* Scene graph overlays
* Multiverse / alternate canon support
* Multi-series shared worlds
* Full Graph-RAG integration

---
