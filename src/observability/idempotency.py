"""Idempotency - Safe retry and deduplication for pipeline operations"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from src.config import CORPUS_METADATA_DIR


IDEMPOTENCY_FILE = CORPUS_METADATA_DIR / "idempotency_state.json"


def _load_state() -> dict:
    """Load idempotency state"""
    if IDEMPOTENCY_FILE.exists():
        with open(IDEMPOTENCY_FILE, "r") as f:
            return json.load(f)
    return {"processed": {}}


def _save_state(state: dict) -> None:
    """Save idempotency state"""
    IDEMPOTENCY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(IDEMPOTENCY_FILE, "w") as f:
        json.dump(state, f, indent=2)


def generate_idempotency_key(
    book_id: str,
    chapter_title: str,
    chunk_idx: int,
    operation: str = "extraction",
) -> str:
    """Generate unique key for a chunk operation"""
    key_parts = f"{book_id}:{chapter_title}:{chunk_idx}:{operation}"
    return hashlib.sha256(key_parts.encode()).hexdigest()[:16]


def is_processed(key: str) -> bool:
    """Check if operation already completed"""
    state = _load_state()
    return key in state["processed"]


def get_cached_result(key: str) -> dict | None:
    """Get cached result for processed operation"""
    state = _load_state()
    entry = state["processed"].get(key)
    return entry.get("result") if entry else None


def mark_complete(key: str, result: dict | None = None) -> None:
    """Mark operation as completed"""
    state = _load_state()
    state["processed"][key] = {
        "completed_at": datetime.now().isoformat(),
        "result": result,
    }
    _save_state(state)


def clear_all() -> None:
    """Clear all idempotency state"""
    if IDEMPOTENCY_FILE.exists():
        IDEMPOTENCY_FILE.unlink()
    print("🗑️ Cleared idempotency state")


def get_stats() -> dict:
    """Get processing stats"""
    state = _load_state()
    return {"total_processed": len(state.get("processed", {}))}
