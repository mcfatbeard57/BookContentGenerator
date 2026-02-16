"""Traceability - Full request tracing for debugging and audit

Layer 7 observability: request-scoped trace IDs, decision logging with
context, prompt/args replayability, and LLM version recording.
"""
import json
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import TRACES_DIR

__all__ = [
    "TracedDecision",
    "TracedLLMCall",
    "TracedSpan",
    "Trace",
    "SpanContext",
    "get_current_trace_id",
    "start_trace",
    "end_trace",
    "get_active_trace",
    "start_span",
    "end_span",
    "log_decision",
    "log_llm_call",
    "record_model_version",
    "save_trace",
    "load_trace",
]


# =============================================================================
# CONTEXT VARIABLE — Propagates trace ID through entire call stack
# =============================================================================

_current_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def get_current_trace_id() -> str | None:
    """Get the active trace ID for the current execution context.

    Returns:
        Hex trace ID string, or ``None`` if no trace is active.
    """
    return _current_trace_id.get()


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class TracedDecision:
    """Record of a decision made during processing.

    Attributes:
        decision_id: Unique hex identifier.
        category: Decision category (e.g. ``alias_resolution``).
        options_considered: All options that were evaluated.
        option_chosen: The selected option.
        reason: Human-readable justification.
        constraints: Constraints that influenced the decision.
        confidence: Confidence level (0–1).
        timestamp: ISO-8601 timestamp.
        metadata: Additional key-value context.
    """
    decision_id: str
    category: str  # e.g., "alias_resolution", "entity_classification"
    options_considered: list[str]
    option_chosen: str
    reason: str
    constraints: list[str] = field(default_factory=list)
    confidence: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "category": self.category,
            "options_considered": self.options_considered,
            "option_chosen": self.option_chosen,
            "reason": self.reason,
            "constraints": self.constraints,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class TracedLLMCall:
    """Record of an LLM call with full prompt/response for replayability.

    Attributes:
        call_id: Unique hex identifier.
        model_name: Ollama model identifier.
        model_version: Model digest, if available.
        prompt: Full prompt text sent to the model.
        response: Full response text received.
        temperature: Sampling temperature used.
        seed: Random seed, if any.
        tokens_prompt: Estimated prompt tokens.
        tokens_completion: Reported completion tokens.
        duration_ms: Wall-clock duration of the call.
        timestamp: ISO-8601 timestamp.
        success: Whether the call succeeded.
        error: Error message, if any.
    """
    call_id: str
    model_name: str
    model_version: str | None = None
    prompt: str = ""
    response: str = ""
    temperature: float = 0.0
    seed: int | None = None
    tokens_prompt: int = 0
    tokens_completion: int = 0
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "prompt_length": len(self.prompt),
            "response_length": len(self.response),
            "prompt": self.prompt[:500] + ("..." if len(self.prompt) > 500 else ""),
            "response": self.response[:500] + ("..." if len(self.response) > 500 else ""),
            "temperature": self.temperature,
            "seed": self.seed,
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class TracedSpan:
    """A timed span within a trace for structured timing.

    Attributes:
        name: Span name describing the operation.
        span_id: Auto-generated hex identifier.
        parent_span_id: Parent span for nested spans.
        start_time: Monotonic start time.
        end_time: Monotonic end time (set by ``finish()``).
        attributes: Arbitrary key-value metadata.
        status: ``"ok"`` or ``"error"``.
        error: Error message, if any.
    """
    name: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None

    def finish(self, status: str = "ok", error: str | None = None) -> None:
        self.end_time = time.monotonic()
        self.status = status
        self.error = error

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "parent_span_id": self.parent_span_id,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "error": self.error,
            "attributes": self.attributes,
        }


# =============================================================================
# TRACE — Collects all data for one pipeline run
# =============================================================================

@dataclass
class Trace:
    """Complete trace for one pipeline run.

    Collects spans, decisions, LLM calls, and model versions.
    """
    trace_id: str
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ended_at: str | None = None
    model_versions: dict[str, str] = field(default_factory=dict)  # model_name -> digest
    spans: list[TracedSpan] = field(default_factory=list)
    decisions: list[TracedDecision] = field(default_factory=list)
    llm_calls: list[TracedLLMCall] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "model_versions": self.model_versions,
            "spans": [s.to_dict() for s in self.spans],
            "decisions": [d.to_dict() for d in self.decisions],
            "llm_calls": [c.to_dict() for c in self.llm_calls],
            "metadata": self.metadata,
        }


# =============================================================================
# GLOBAL TRACE MANAGEMENT
# =============================================================================

_active_trace: Trace | None = None
_span_stack: list[TracedSpan] = []


def start_trace(metadata: dict[str, Any] | None = None) -> str:
    """Start a new trace for a pipeline run.

    Args:
        metadata: Optional metadata to attach to the trace.

    Returns:
        Hex trace ID string.
    """
    global _active_trace, _span_stack
    trace_id = uuid.uuid4().hex[:12]
    _current_trace_id.set(trace_id)
    _active_trace = Trace(trace_id=trace_id, metadata=metadata or {})
    _span_stack = []
    print(f"🔍 Trace started: {trace_id}")
    return trace_id


def end_trace() -> Trace | None:
    """End the active trace and return it.

    Returns:
        The completed ``Trace``, or ``None`` if no trace was active.
    """
    global _active_trace, _span_stack
    if _active_trace is None:
        return None

    _active_trace.ended_at = datetime.now().isoformat()
    trace = _active_trace
    _active_trace = None
    _span_stack = []
    _current_trace_id.set(None)

    print(f"🔍 Trace ended: {trace.trace_id} "
          f"({len(trace.spans)} spans, "
          f"{len(trace.decisions)} decisions, "
          f"{len(trace.llm_calls)} LLM calls)")
    return trace


def get_active_trace() -> Trace | None:
    """Get the currently active trace, if any."""
    return _active_trace


# =============================================================================
# SPAN MANAGEMENT
# =============================================================================

def start_span(name: str, **attributes: Any) -> TracedSpan:
    """Start a new span within the active trace.

    Args:
        name: Descriptive name for this span.
        **attributes: Arbitrary key-value metadata.

    Returns:
        The started ``TracedSpan``.
    """
    parent_id = _span_stack[-1].span_id if _span_stack else None
    span = TracedSpan(name=name, parent_span_id=parent_id, attributes=attributes)
    _span_stack.append(span)
    if _active_trace:
        _active_trace.spans.append(span)
    return span


def end_span(span: TracedSpan, status: str = "ok", error: str | None = None) -> None:
    """End a span and pop it from the stack.

    Args:
        span: The span to finish.
        status: ``"ok"`` or ``"error"``.
        error: Error message, if applicable.
    """
    span.finish(status=status, error=error)
    if _span_stack and _span_stack[-1] is span:
        _span_stack.pop()


class SpanContext:
    """Context manager for automatic span management"""

    def __init__(self, name: str, **attributes: Any):
        self.name = name
        self.attributes = attributes
        self.span: TracedSpan | None = None

    def __enter__(self) -> TracedSpan:
        self.span = start_span(self.name, **self.attributes)
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.span:
            status = "error" if exc_type else "ok"
            error = str(exc_val) if exc_val else None
            end_span(self.span, status=status, error=error)


# =============================================================================
# DECISION LOGGING
# =============================================================================

def log_decision(
    category: str,
    options_considered: list[str],
    option_chosen: str,
    reason: str,
    constraints: list[str] | None = None,
    confidence: float = 1.0,
    **metadata: Any,
) -> TracedDecision:
    """Log a decision made during processing.

    Args:
        category: Decision category (e.g. ``alias_resolution``).
        options_considered: All options evaluated.
        option_chosen: The option selected.
        reason: Human-readable justification.
        constraints: Constraints that influenced the choice.
        confidence: Confidence in the decision (0–1).
        **metadata: Additional context key-value pairs.

    Returns:
        The recorded ``TracedDecision``.
    """
    decision = TracedDecision(
        decision_id=uuid.uuid4().hex[:8],
        category=category,
        options_considered=options_considered,
        option_chosen=option_chosen,
        reason=reason,
        constraints=constraints or [],
        confidence=confidence,
        metadata=metadata,
    )
    if _active_trace:
        _active_trace.decisions.append(decision)
    return decision


# =============================================================================
# LLM CALL LOGGING
# =============================================================================

def log_llm_call(
    model_name: str,
    prompt: str,
    response: str,
    duration_ms: float = 0.0,
    tokens_prompt: int = 0,
    tokens_completion: int = 0,
    temperature: float = 0.0,
    seed: int | None = None,
    model_version: str | None = None,
    success: bool = True,
    error: str | None = None,
) -> TracedLLMCall:
    """Log an LLM call with full prompt/response for replayability.

    Args:
        model_name: Ollama model identifier.
        prompt: Full prompt text.
        response: Full response text.
        duration_ms: Wall-clock call duration in milliseconds.
        tokens_prompt: Estimated prompt token count.
        tokens_completion: Completion token count.
        temperature: Sampling temperature.
        seed: Random seed, if used.
        model_version: Model digest string.
        success: Whether the call succeeded.
        error: Error message, if applicable.

    Returns:
        The recorded ``TracedLLMCall``.
    """
    call = TracedLLMCall(
        call_id=uuid.uuid4().hex[:8],
        model_name=model_name,
        model_version=model_version,
        prompt=prompt,
        response=response,
        duration_ms=duration_ms,
        tokens_prompt=tokens_prompt,
        tokens_completion=tokens_completion,
        temperature=temperature,
        seed=seed,
        success=success,
        error=error,
    )
    if _active_trace:
        _active_trace.llm_calls.append(call)
    return call


def record_model_version(model_name: str, digest: str) -> None:
    """Record the exact model digest for replayability.

    Args:
        model_name: Ollama model identifier.
        digest: Truncated model digest string.
    """
    if _active_trace:
        _active_trace.model_versions[model_name] = digest


# =============================================================================
# TRACE PERSISTENCE
# =============================================================================

def save_trace(trace: Trace | None = None) -> Path | None:
    """Save a trace to disk as JSON.

    Args:
        trace: Trace to save. Defaults to the active trace.

    Returns:
        Path to the saved file, or ``None`` if no trace was provided.
    """
    trace = trace or _active_trace
    if trace is None:
        return None

    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    trace_path = TRACES_DIR / f"{trace.trace_id}.json"

    with open(trace_path, "w") as f:
        json.dump(trace.to_dict(), f, indent=2, default=str)

    print(f"💾 Trace saved: {trace_path}")
    return trace_path


def load_trace(trace_id: str) -> Trace | None:
    """Load a trace from disk for inspection.

    Args:
        trace_id: Hex trace ID to load.

    Returns:
        Reconstituted ``Trace``, or ``None`` if not found.
    """
    trace_path = TRACES_DIR / f"{trace_id}.json"
    if not trace_path.exists():
        return None

    with open(trace_path, "r") as f:
        data = json.load(f)

    return Trace(
        trace_id=data["trace_id"],
        started_at=data["started_at"],
        ended_at=data.get("ended_at"),
        model_versions=data.get("model_versions", {}),
        metadata=data.get("metadata", {}),
        # Note: spans/decisions/llm_calls reconstructed as dicts in metadata
    )
