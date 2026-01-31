"""Checkpointing - Safe incremental saves during extraction"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import CHECKPOINT_FILE, CHECKPOINT_INTERVAL


@dataclass
class ExtractionCheckpoint:
    """Checkpoint state for extraction process"""
    
    book_id: str
    book_title: str
    total_chapters: int
    completed_chapters: list[str] = field(default_factory=list)
    entities_extracted: list[dict] = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    errors: list[str] = field(default_factory=list)
    
    @property
    def progress_percent(self) -> float:
        if self.total_chapters == 0:
            return 0.0
        return (len(self.completed_chapters) / self.total_chapters) * 100
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ExtractionCheckpoint":
        return cls(**data)


def load_checkpoint(book_id: str) -> ExtractionCheckpoint | None:
    """Load existing checkpoint for a book"""
    if not CHECKPOINT_FILE.exists():
        return None
    
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            data = json.load(f)
        
        if data.get("book_id") == book_id:
            return ExtractionCheckpoint.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        pass
    
    return None


def save_checkpoint(checkpoint: ExtractionCheckpoint) -> None:
    """Save checkpoint to disk"""
    checkpoint.last_updated = datetime.now().isoformat()
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)
    
    print(f"  💾 Checkpoint saved: {len(checkpoint.completed_chapters)}/{checkpoint.total_chapters} chapters")


def clear_checkpoint() -> None:
    """Clear checkpoint after successful completion"""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("  ✓ Checkpoint cleared")


def should_save_checkpoint(chapters_completed: int) -> bool:
    """Check if we should save a checkpoint"""
    return chapters_completed > 0 and chapters_completed % CHECKPOINT_INTERVAL == 0


class CheckpointManager:
    """
    Context manager for checkpointed extraction.
    
    Usage:
        with CheckpointManager(book_id, book_title, chapters) as mgr:
            for chapter in mgr.pending_chapters():
                entities = extract(chapter)
                mgr.mark_complete(chapter.title, entities)
    """
    
    def __init__(self, book_id: str, book_title: str, total_chapters: int):
        self.book_id = book_id
        self.book_title = book_title
        self.total_chapters = total_chapters
        self.checkpoint: ExtractionCheckpoint | None = None
        self._all_chapters: list[str] = []
    
    def __enter__(self) -> "CheckpointManager":
        # Try to load existing checkpoint
        self.checkpoint = load_checkpoint(self.book_id)
        
        if self.checkpoint:
            completed = len(self.checkpoint.completed_chapters)
            print(f"  📂 Resuming from checkpoint: {completed}/{self.total_chapters} chapters done")
        else:
            self.checkpoint = ExtractionCheckpoint(
                book_id=self.book_id,
                book_title=self.book_title,
                total_chapters=self.total_chapters,
            )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            # Save checkpoint on error for recovery
            self.checkpoint.errors.append(str(exc_val))
            save_checkpoint(self.checkpoint)
            print(f"  ⚠️ Error occurred - checkpoint saved for recovery")
        else:
            # Clear checkpoint on success
            clear_checkpoint()
        
        return False
    
    def is_chapter_done(self, chapter_title: str) -> bool:
        """Check if chapter already processed"""
        return chapter_title in self.checkpoint.completed_chapters
    
    def mark_complete(
        self,
        chapter_title: str,
        entities: list[dict],
    ) -> None:
        """Mark chapter as complete and optionally save checkpoint"""
        self.checkpoint.completed_chapters.append(chapter_title)
        self.checkpoint.entities_extracted.extend(entities)
        
        # Save checkpoint at intervals
        if should_save_checkpoint(len(self.checkpoint.completed_chapters)):
            save_checkpoint(self.checkpoint)
    
    def get_all_entities(self) -> list[dict]:
        """Get all extracted entities"""
        return self.checkpoint.entities_extracted
    
    @property
    def completed_count(self) -> int:
        return len(self.checkpoint.completed_chapters)
