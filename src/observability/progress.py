"""Progress Events - Semantic progress stages for visibility and trust"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable


class ProgressStage(Enum):
    """Semantic progress stages - meaningful to humans"""
    
    # Ingestion
    LOADING_BOOK = "Loading book"
    PARSING_STRUCTURE = "Parsing structure"
    
    # Entity Extraction
    EXTRACTING_ENTITIES = "Extracting entities"
    
    # Resolution & Enrichment
    RESOLVING_ALIASES = "Resolving aliases"
    GENERATING_SUMMARIES = "Generating descriptions"
    
    # Output
    BUILDING_GRAPH = "Building graph"
    WRITING_CORPUS = "Writing files"
    CREATING_INDEX = "Creating index"
    
    # Finalization
    SAVING_STATE = "Saving state"
    COMPLETE = "Complete"


@dataclass
class ProgressEvent:
    """A single progress update"""
    
    stage: ProgressStage
    current: int
    total: int
    message: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    can_interrupt: bool = True
    
    @property
    def percentage(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.current / self.total) * 100
    
    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "current": self.current,
            "total": self.total,
            "percentage": round(self.percentage, 1),
            "message": self.message,
            "can_interrupt": self.can_interrupt,
        }


# Progress listeners for external consumers
_progress_listeners: list[Callable[[ProgressEvent], None]] = []


def add_progress_listener(callback: Callable[[ProgressEvent], None]) -> None:
    """Register a callback to receive progress events"""
    _progress_listeners.append(callback)


def emit_progress(
    stage: ProgressStage,
    current: int,
    total: int,
    message: str | None = None,
    can_interrupt: bool = True,
    quiet: bool = False,
) -> ProgressEvent:
    """Emit a progress event"""
    event = ProgressEvent(
        stage=stage,
        current=current,
        total=total,
        message=message,
        can_interrupt=can_interrupt,
    )
    
    if not quiet:
        marker = "🔒" if not can_interrupt else "○"
        pct = f"{event.percentage:5.1f}%" if total > 0 else ""
        msg_part = f" - {message}" if message else ""
        count_part = f" ({current}/{total})" if total > 0 else ""
        print(f"  {marker} [{pct}] {stage.value}{msg_part}{count_part}")
    
    # Notify listeners
    for listener in _progress_listeners:
        try:
            listener(event)
        except Exception:
            pass
    
    return event


# Interrupt handling
_interrupt_requested = False


def request_interrupt() -> None:
    """Request pipeline to stop at next safe point"""
    global _interrupt_requested
    _interrupt_requested = True
    print("⚠️ Interrupt requested")


def check_interrupt() -> bool:
    """Check if we should stop"""
    return _interrupt_requested


def clear_interrupt() -> None:
    """Clear interrupt flag"""
    global _interrupt_requested
    _interrupt_requested = False
