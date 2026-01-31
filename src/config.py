"""Book → Canonical Corpus Builder - Configuration"""
from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "Data"
CORPUS_DIR = PROJECT_ROOT / "corpus"

# Corpus subdirectories
CORPUS_METADATA_DIR = CORPUS_DIR / "metadata"
CORPUS_CHARACTERS_DIR = CORPUS_DIR / "characters"
CORPUS_LOCATIONS_DIR = CORPUS_DIR / "locations"
CORPUS_FACTIONS_DIR = CORPUS_DIR / "factions"
CORPUS_TIMELINE_DIR = CORPUS_DIR / "timeline"
CORPUS_RELATIONSHIPS_DIR = CORPUS_DIR / "relationships"
CORPUS_GRAPH_DIR = CORPUS_DIR / "graph"

# Registry files
INGESTION_LOG_PATH = CORPUS_METADATA_DIR / "ingestion_log.json"
WORLD_GRAPH_PATH = CORPUS_GRAPH_DIR / "world_graph.json"
FAISS_INDEX_PATH = CORPUS_GRAPH_DIR / "entity_index.faiss"

# Wiki reference for priority classification
WIKI_JSON_PATH = DATA_DIR / "book1_wiki.json"

# Priority tiers for entity classification
PRIORITY_TIERS = ["canonical", "major", "minor"]

# =============================================================================
# OLLAMA CONFIGURATION
# =============================================================================
OLLAMA_BASE_URL = "http://localhost:11434"

# Models
NER_MODEL = "qwen2.5:7b"  # qwen2.5:7b-instruct if you have it
SUMMARIZER_MODEL = "llama3.1:8b"  # llama3.1:8b-instruct if you have it
EMBEDDING_MODEL = "nomic-embed-text"

# Generation parameters (deterministic)
OLLAMA_OPTIONS = {
    "temperature": 0.0,
    "seed": 42,
    "num_predict": 4096,  # Increased for richer outputs
}

# =============================================================================
# ENTITY TYPES
# =============================================================================
ENTITY_TYPES = [
    "character",
    "location",
    "faction",
    "timeline_event",
]

# Entity type to directory mapping
ENTITY_DIRS = {
    "character": CORPUS_CHARACTERS_DIR,
    "location": CORPUS_LOCATIONS_DIR,
    "faction": CORPUS_FACTIONS_DIR,
    "timeline_event": CORPUS_TIMELINE_DIR,
}

# =============================================================================
# RELATIONSHIP TYPES
# =============================================================================
RELATIONSHIP_TYPES = [
    "APPEARS_IN",      # entity → location
    "MEMBER_OF",       # character → faction
    "KNOWS",           # character → character
    "LOCATED_IN",      # location → location (hierarchy)
    "PARTICIPATES_IN", # character → timeline_event
]

# =============================================================================
# PROCESSING LIMITS
# =============================================================================
# Optimized chunk size for qwen2.5:7b (32K context window):
# - 16000 chars ≈ 4000 tokens = ~12% of context
# - Leaves room for: wiki context (~2K), system prompt (~500), output (~4K)
# - Reduces total LLM calls by ~8x compared to original 2000
CHUNK_SIZE = 24000  # characters per chunk (optimized for 32K context)
CHUNK_OVERLAP = 400  # overlap between chunks (increased for continuity)
MAX_RETRIES = 3  # LLM call retries
FUZZY_MATCH_THRESHOLD = 85  # rapidfuzz threshold for alias matching

# =============================================================================
# CHECKPOINTING
# =============================================================================
CHECKPOINT_INTERVAL = 5  # Save checkpoint every N chapters
CHECKPOINT_FILE = CORPUS_METADATA_DIR / "extraction_checkpoint.json"

# =============================================================================
# DASHBOARD
# =============================================================================
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8080

