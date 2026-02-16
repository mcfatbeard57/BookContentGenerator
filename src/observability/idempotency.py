"""Idempotency - Safe retry and deduplication for pipeline operations

Layer 5 observability: content-hash keying, atomic writes, double-run
safety, result caching, and staleness detection.

"If this runs twice, what breaks?" — Nothing, by design.
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from src.config import CORPUS_METADATA_DIR


IDEMPOTENCY_FILE = CORPUS_METADATA_DIR / "idempotency_state.json"

__all__ = [
    "generate_idempotency_key",
    "generate_content_hash",
    "is_processed",
    "get_cached_result",
    "is_stale",
    "mark_complete",
    "safe_mark_complete",
    "clear_all",
    "get_stats",
    "invalidate_for_model",
]


# =============================================================================
# STATE MANAGEMENT (atomic read/write)
# =============================================================================

def _load_state() -> dict:
    """Load idempotency state from disk.

    Returns:
        State dict with ``processed`` entries, or empty state
        if the file is missing or corrupt.
    """
    if IDEMPOTENCY_FILE.exists():
        try:
            with open(IDEMPOTENCY_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"processed": {}, "version": 1}


def _save_state_atomic(state: dict) -> None:
    """Save idempotency state with an atomic write.

    Uses temp-file + rename for crash safety.

    Args:
        state: Full state dict to persist.
    """
    IDEMPOTENCY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file first, then rename for crash safety
    fd, tmp_path = tempfile.mkstemp(
        dir=str(IDEMPOTENCY_FILE.parent),
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, str(IDEMPOTENCY_FILE))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# =============================================================================
# KEY GENERATION — Content-hash based for true deduplication
# =============================================================================

def generate_idempotency_key(
    book_id: str,
    chapter_title: str,
    chunk_idx: int,
    operation: str = "extraction",
    content_hash: str | None = None,
) -> str:
    """Generate a unique key for a chunk operation.

    Prefers content-hash-based keys for true deduplication;
    falls back to positional keys when no hash is provided.

    Args:
        book_id: Deterministic book slug.
        chapter_title: Title of the chapter.
        chunk_idx: Zero-based chunk index.
        operation: Pipeline operation name.
        content_hash: Optional SHA-256 hex digest of the chunk text.

    Returns:
        Truncated SHA-256 hex key (16 chars).
    """
    if content_hash:
        key_parts = f"{book_id}:{operation}:{content_hash}"
    else:
        key_parts = f"{book_id}:{chapter_title}:{chunk_idx}:{operation}"
    return hashlib.sha256(key_parts.encode()).hexdigest()[:16]


def generate_content_hash(content: str) -> str:
    """Generate a truncated SHA-256 hash of text content.

    Args:
        content: Text to hash.

    Returns:
        First 16 hex characters of the SHA-256 digest.
    """
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# =============================================================================
# PROCESSING CHECKS
# =============================================================================

def is_processed(key: str) -> bool:
    """Check whether an operation has already been completed.

    Args:
        key: Idempotency key.

    Returns:
        True if the key exists in the state file.
    """
    state = _load_state()
    return key in state["processed"]


def get_cached_result(key: str) -> dict | None:
    """Retrieve a cached result for a previously completed operation.

    Args:
        key: Idempotency key.

    Returns:
        The cached result dict, or ``None`` if not found.
    """
    state = _load_state()
    entry = state["processed"].get(key)
    return entry.get("result") if entry else None


def is_stale(
    key: str,
    model_name: str | None = None,
    prompt_hash: str | None = None,
) -> bool:
    """Check if a cached result is stale.

    A result is considered stale if the model or prompt has changed
    since it was cached.

    Args:
        key: Idempotency key.
        model_name: Current model identifier.
        prompt_hash: Current prompt hash.

    Returns:
        True if the result should be recomputed.
    """
    state = _load_state()
    entry = state["processed"].get(key)
    if not entry:
        return True  # Not cached = stale

    if model_name and entry.get("model_name") != model_name:
        return True

    if prompt_hash and entry.get("prompt_hash") != prompt_hash:
        return True

    return False


# =============================================================================
# MARKING COMPLETION
# =============================================================================

def mark_complete(
    key: str,
    result: dict | None = None,
    model_name: str | None = None,
    prompt_hash: str | None = None,
) -> None:
    """Mark an operation as completed with an atomic write.

    Args:
        key: Idempotency key.
        result: Extraction result to cache.
        model_name: Model identifier for staleness checks.
        prompt_hash: Prompt hash for staleness checks.
    """
    state = _load_state()
    state["processed"][key] = {
        "completed_at": datetime.now().isoformat(),
        "result": result,
        "model_name": model_name,
        "prompt_hash": prompt_hash,
    }
    _save_state_atomic(state)


def safe_mark_complete(
    key: str,
    result: dict | None = None,
    model_name: str | None = None,
    prompt_hash: str | None = None,
) -> None:
    """Mark complete with double-run safety check.

    If the key already exists with a different result hash, logs a
    non-determinism warning but still updates the entry.

    Args:
        key: Idempotency key.
        result: Extraction result to cache.
        model_name: Model identifier.
        prompt_hash: Prompt hash.
    """
    state = _load_state()
    existing = state["processed"].get(key)

    if existing and result is not None:
        existing_result_hash = hashlib.sha256(
            json.dumps(existing.get("result"), sort_keys=True).encode()
        ).hexdigest()[:12]
        new_result_hash = hashlib.sha256(
            json.dumps(result, sort_keys=True).encode()
        ).hexdigest()[:12]

        if existing_result_hash != new_result_hash:
            print(
                f"  ⚠️ Non-determinism detected for key {key[:8]}...: "
                f"existing={existing_result_hash}, new={new_result_hash}"
            )

    # Update regardless
    state["processed"][key] = {
        "completed_at": datetime.now().isoformat(),
        "result": result,
        "model_name": model_name,
        "prompt_hash": prompt_hash,
    }
    _save_state_atomic(state)


# =============================================================================
# MANAGEMENT
# =============================================================================

def clear_all() -> None:
    """Delete all idempotency state from disk."""
    if IDEMPOTENCY_FILE.exists():
        IDEMPOTENCY_FILE.unlink()
    print("🗑️ Cleared idempotency state")


def get_stats() -> dict:
    """Return processing statistics.

    Returns:
        Dict with ``total_processed`` and ``stale_entries`` counts.
    """
    state = _load_state()
    processed = state.get("processed", {})
    
    stale_count = sum(
        1 for entry in processed.values()
        if entry.get("model_name") is None  # Old entries without model tracking
    )
    
    return {
        "total_processed": len(processed),
        "stale_entries": stale_count,
    }


def invalidate_for_model(model_name: str) -> int:
    """Invalidate all cached results produced by a specific model.

    Useful when upgrading models to force re-extraction.

    Args:
        model_name: Ollama model identifier to invalidate.

    Returns:
        Number of entries removed.
    """
    state = _load_state()
    to_remove = [
        key for key, entry in state["processed"].items()
        if entry.get("model_name") == model_name
    ]
    
    for key in to_remove:
        del state["processed"][key]
    
    if to_remove:
        _save_state_atomic(state)
        print(f"🗑️ Invalidated {len(to_remove)} entries for model {model_name}")
    
    return len(to_remove)
