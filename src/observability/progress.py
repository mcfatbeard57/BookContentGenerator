"""Progress Events - Semantic progress stages for visibility and trust

Layer 3 observability: human-meaningful progress tracking with integrity
guarantees and interruptibility support.
"""
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from src.config import CORPUS_METADATA_DIR

__all__ = [
    "ProgressStage",
    "ProgressEvent",
    "ProgressGuard",
    "add_progress_listener",
    "remove_progress_listener",
    "emit_progress",
    "save_progress_log",
    "get_progress_warnings",
    "reset_progress",
    "request_interrupt",
    "check_interrupt",
    "clear_interrupt",
    "set_interactive_mode",
    "gate_unsafe_step",
]


# =============================================================================
# SEMANTIC STAGES — Meaningful to humans, not technical jargon
# =============================================================================

class ProgressStage(Enum):
    """Semantic progress stages meaningful to human observers."""

    # Ingestion
    LOADING_BOOK = "Loading book"
    ANALYZING_STRUCTURE = "Analyzing book structure"

    # Entity Extraction
    EXTRACTING_CHARACTERS_AND_ENTITIES = "Extracting characters and entities"

    # Resolution & Enrichment
    RESOLVING_DUPLICATE_NAMES = "Resolving duplicate names"
    GENERATING_DESCRIPTIONS = "Generating descriptions"

    # Connections
    BUILDING_CONNECTIONS = "Building entity connections"

    # Output
    WRITING_OUTPUT = "Writing output"

    # Finalization
    SAVING_STATE = "Saving state"
    COMPLETE = "Complete"


# =============================================================================
# PROGRESS EVENT
# =============================================================================

@dataclass
class ProgressEvent:
    """A single progress update with integrity guarantees.

    Attributes:
        stage: Current semantic stage.
        current: Current step number.
        total: Total steps expected.
        message: Optional human-readable status message.
        timestamp: When this event was created.
        can_interrupt: Whether it is safe to stop after this event.
        approval_required: If True, human approval needed before proceeding.
        sub_current: Sub-step index (e.g. chunk within chapter).
        sub_total: Total sub-steps.
    """

    stage: ProgressStage
    current: int
    total: int
    message: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    can_interrupt: bool = True
    approval_required: bool = False  # True if human approval needed before next step

    # Sub-step tracking (e.g., chunks within a chapter)
    sub_current: int = 0
    sub_total: int = 0

    @property
    def percentage(self) -> float:
        if self.total == 0:
            return 0.0
        raw_pct = (self.current / self.total) * 100
        # Integrity: never report > 95% until actually at 100%
        if raw_pct > 95.0 and self.current < self.total:
            return 95.0
        return raw_pct

    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "current": self.current,
            "total": self.total,
            "percentage": round(self.percentage, 1),
            "message": self.message,
            "can_interrupt": self.can_interrupt,
            "approval_required": self.approval_required,
            "sub_current": self.sub_current,
            "sub_total": self.sub_total,
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# PROGRESS GUARD — Integrity enforcement
# =============================================================================

class ProgressGuard:
    """
    Validates progress events and detects silent long-running steps.
    
    Raises warnings if:
    - current > total (invalid progress)
    - No progress update in > 60s (silent step)
    """

    def __init__(self, silent_threshold_s: float = 60.0):
        self._last_event_time: float = time.monotonic()
        self._silent_threshold = silent_threshold_s
        self._warnings: list[str] = []

    def validate(self, event: ProgressEvent) -> ProgressEvent:
        """Validate a progress event and log integrity warnings.

        Clamps ``current`` if it exceeds ``total`` and warns about
        long gaps between events.

        Args:
            event: The progress event to validate.

        Returns:
            The (possibly clamped) event.
        """
        now = time.monotonic()

        # Check for invalid progress
        if event.current > event.total and event.total > 0:
            warning = (
                f"Progress overflow: {event.current}/{event.total} "
                f"for stage {event.stage.value}"
            )
            self._warnings.append(warning)
            print(f"  ⚠️ {warning}")
            event.current = event.total  # Clamp

        # Check for silent steps
        elapsed = now - self._last_event_time
        if elapsed > self._silent_threshold:
            warning = (
                f"Silent step detected: {elapsed:.0f}s since last progress "
                f"update (stage: {event.stage.value})"
            )
            self._warnings.append(warning)
            print(f"  ⚠️ {warning}")

        self._last_event_time = now
        return event

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)


# =============================================================================
# GLOBAL STATE
# =============================================================================

# Progress listeners for external consumers
_progress_listeners: list[Callable[[ProgressEvent], None]] = []
_progress_guard = ProgressGuard()
_event_log: list[dict] = []  # In-memory log of all events


def add_progress_listener(callback: Callable[[ProgressEvent], None]) -> None:
    """Register a callback to receive progress events.

    Args:
        callback: Function that accepts a ``ProgressEvent``.
    """
    _progress_listeners.append(callback)


def remove_progress_listener(callback: Callable[[ProgressEvent], None]) -> None:
    """Remove a previously registered progress listener.

    Args:
        callback: The callback to remove.
    """
    if callback in _progress_listeners:
        _progress_listeners.remove(callback)


def emit_progress(
    stage: ProgressStage,
    current: int,
    total: int,
    message: str | None = None,
    can_interrupt: bool = True,
    approval_required: bool = False,
    sub_current: int = 0,
    sub_total: int = 0,
    quiet: bool = False,
) -> ProgressEvent:
    """Emit a progress event with integrity validation.

    Args:
        stage: Current semantic stage.
        current: Current step number.
        total: Total steps expected.
        message: Optional human-readable message.
        can_interrupt: Whether it is safe to stop now.
        approval_required: If True, gate on human approval.
        sub_current: Sub-step index.
        sub_total: Sub-step total.
        quiet: If True, suppress console output.

    Returns:
        The validated ``ProgressEvent``.
    """
    event = ProgressEvent(
        stage=stage,
        current=current,
        total=total,
        message=message,
        can_interrupt=can_interrupt,
        approval_required=approval_required,
        sub_current=sub_current,
        sub_total=sub_total,
    )

    # Validate through guard
    event = _progress_guard.validate(event)

    # Log event
    _event_log.append(event.to_dict())

    if not quiet:
        marker = "🔒" if not can_interrupt else "○"
        if approval_required:
            marker = "⏸"
        pct = f"{event.percentage:5.1f}%" if total > 0 else ""
        msg_part = f" - {message}" if message else ""
        count_part = f" ({current}/{total})" if total > 0 else ""
        sub_part = ""
        if sub_total > 0:
            sub_part = f" [sub: {sub_current}/{sub_total}]"
        print(f"  {marker} [{pct}] {stage.value}{msg_part}{count_part}{sub_part}")

    # Notify listeners
    for listener in _progress_listeners:
        try:
            listener(event)
        except Exception:
            pass

    return event


def save_progress_log(trace_id: str | None = None) -> Path:
    """Save the in-memory progress event log to disk.

    Args:
        trace_id: Optional trace ID to include in the filename.

    Returns:
        Path to the saved JSON log file.
    """
    log_dir = CORPUS_METADATA_DIR / "progress_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    suffix = f"_{trace_id}" if trace_id else ""
    log_path = log_dir / f"progress{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    log_data = {
        "events": _event_log,
        "warnings": _progress_guard.warnings,
        "saved_at": datetime.now().isoformat(),
    }

    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)

    return log_path


def get_progress_warnings() -> list[str]:
    """Return any integrity warnings detected during tracking."""
    return _progress_guard.warnings


def reset_progress() -> None:
    """Reset all progress state for a new pipeline run."""
    global _progress_guard, _event_log
    _progress_guard = ProgressGuard()
    _event_log = []


# =============================================================================
# INTERRUPT HANDLING
# =============================================================================

_interrupt_requested = False


def request_interrupt() -> None:
    """Request the pipeline to stop at its next safe point."""
    global _interrupt_requested
    _interrupt_requested = True
    print("⚠️ Interrupt requested — will stop at next safe point")


def check_interrupt() -> bool:
    """Check whether an interrupt has been requested.

    Returns:
        True if ``request_interrupt()`` was called.
    """
    return _interrupt_requested


def clear_interrupt() -> None:
    """Clear the interrupt flag after handling."""
    global _interrupt_requested
    _interrupt_requested = False


# =============================================================================
# APPROVAL GATING
# =============================================================================

_interactive_mode = False
_approval_callback: Callable[[str, str], bool] | None = None


def set_interactive_mode(
    enabled: bool,
    approval_callback: Callable[[str, str], bool] | None = None,
) -> None:
    """
    Enable/disable interactive mode for approval gating.
    
    Args:
        enabled: Whether to enable interactive mode
        approval_callback: Function(stage, description) -> bool 
                          that returns True to proceed, False to abort
    """
    global _interactive_mode, _approval_callback
    _interactive_mode = enabled
    _approval_callback = approval_callback


def gate_unsafe_step(stage: str, description: str) -> bool:
    """
    Gate an unsafe step behind human approval (in interactive mode).
    
    In batch mode, always returns True (proceed).
    In interactive mode, calls the approval callback.
    
    Returns:
        True to proceed, False to abort
    """
    if not _interactive_mode:
        return True

    if _approval_callback:
        print(f"  ⏸ Approval required: {description}")
        return _approval_callback(stage, description)

    # Default: proceed if no callback
    return True
