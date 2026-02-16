"""Book → Canonical Corpus Builder - Configuration"""
from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "Data"
CORPUS_DIR = PROJECT_ROOT / "corpus"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Corpus subdirectories
CORPUS_METADATA_DIR = CORPUS_DIR / "metadata"

# Registry files
INGESTION_LOG_PATH = CORPUS_METADATA_DIR / "ingestion_log.json"

# Telemetry and traces
TELEMETRY_DIR = CORPUS_METADATA_DIR / "telemetry"
TRACES_DIR = CORPUS_METADATA_DIR / "traces"

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
SUMMARIZER_BATCH_SIZE = 5  # Number of entities to summarize per LLM call

# =============================================================================
# CHECKPOINTING
# =============================================================================
CHECKPOINT_INTERVAL = 5  # Save checkpoint every N chapters
CHECKPOINT_FILE = CORPUS_METADATA_DIR / "extraction_checkpoint.json"
