"""Tracer - Trace ID propagation, decision logging, and replayability"""
import json
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import CORPUS_METADATA_DIR


# Trace storage directory
TRACES_DIR = CORPUS_METADATA_DIR / "traces"


@dataclass
class Span:
    """A span within a trace representing a unit of work"""
    
    span_id: str
    name: str
    started_at: datetime
    ended_at: datetime | None = None
    input_data: dict | None = None
    output_data: dict | None = None
    metadata: dict = field(default_factory=dict)
    error: str | None = None
    
    @property
    def duration_ms(self) -> float | None:
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds() * 1000
        return None
    
    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class Decision:
    """A logged decision point with reasoning"""
    
    decision_type: str
    options: list[str]
    chosen: str
    reason: str
    constraints: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "type": self.decision_type,
            "options": self.options,
            "chosen": self.chosen,
            "reason": self.reason,
            "constraints": self.constraints,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class TraceContext:
    """Context for a single trace (one user request)"""
    
    trace_id: str
    name: str
    started_at: datetime
    metadata: dict = field(default_factory=dict)
    spans: list[Span] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    llm_calls: list[dict] = field(default_factory=list)
    ended_at: datetime | None = None
    
    def add_span(self, span: Span) -> None:
        self.spans.append(span)
    
    def add_decision(self, decision: Decision) -> None:
        self.decisions.append(decision)
    
    def add_llm_call(
        self,
        model: str,
        prompt_tokens: int,
        output_tokens: int,
        duration_s: float,
        success: bool = True,
    ) -> None:
        self.llm_calls.append({
            "model": model,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "duration_s": round(duration_s, 2),
            "success": success,
            "timestamp": datetime.now().isoformat(),
        })
    
    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "metadata": self.metadata,
            "spans": [s.to_dict() for s in self.spans],
            "decisions": [d.to_dict() for d in self.decisions],
            "llm_calls": self.llm_calls,
            "summary": {
                "total_spans": len(self.spans),
                "total_decisions": len(self.decisions),
                "total_llm_calls": len(self.llm_calls),
                "total_prompt_tokens": sum(c["prompt_tokens"] for c in self.llm_calls),
                "total_output_tokens": sum(c["output_tokens"] for c in self.llm_calls),
            },
        }


# Global trace context using contextvars (thread-safe)
_current_trace: ContextVar[TraceContext | None] = ContextVar("current_trace", default=None)
_current_span: ContextVar[Span | None] = ContextVar("current_span", default=None)


def generate_trace_id() -> str:
    """Generate a unique trace ID"""
    return f"tr_{uuid.uuid4().hex[:12]}"


def generate_span_id() -> str:
    """Generate a unique span ID"""
    return f"sp_{uuid.uuid4().hex[:8]}"


def start_trace(name: str, metadata: dict | None = None) -> TraceContext:
    """Start a new trace context"""
    trace = TraceContext(
        trace_id=generate_trace_id(),
        name=name,
        started_at=datetime.now(),
        metadata=metadata or {},
    )
    _current_trace.set(trace)
    print(f"🔍 Trace started: {trace.trace_id} ({name})")
    return trace


def end_trace() -> TraceContext | None:
    """End the current trace and save to disk"""
    trace = _current_trace.get()
    if trace:
        trace.ended_at = datetime.now()
        _save_trace(trace)
        print(f"✅ Trace ended: {trace.trace_id}")
        _current_trace.set(None)
    return trace


def get_current_trace() -> TraceContext | None:
    """Get the current trace context"""
    return _current_trace.get()


def get_trace_id() -> str | None:
    """Get the current trace ID"""
    trace = _current_trace.get()
    return trace.trace_id if trace else None


class TracedSpan:
    """Context manager for creating spans within a trace"""
    
    def __init__(self, name: str, input_data: dict | None = None):
        self.name = name
        self.input_data = input_data
        self.span: Span | None = None
    
    def __enter__(self) -> "TracedSpan":
        self.span = Span(
            span_id=generate_span_id(),
            name=self.name,
            started_at=datetime.now(),
            input_data=self.input_data,
        )
        _current_span.set(self.span)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            self.span.ended_at = datetime.now()
            if exc_val:
                self.span.error = str(exc_val)
            
            trace = _current_trace.get()
            if trace:
                trace.add_span(self.span)
        
        _current_span.set(None)
        return False  # Don't suppress exceptions
    
    def set_output(self, output_data: dict) -> None:
        if self.span:
            self.span.output_data = output_data
    
    def set_metadata(self, key: str, value: Any) -> None:
        if self.span:
            self.span.metadata[key] = value


def log_decision(
    decision_type: str,
    options: list[str],
    chosen: str,
    reason: str,
    constraints: list[str] | None = None,
) -> None:
    """Log a decision point for auditability"""
    trace = _current_trace.get()
    if trace:
        decision = Decision(
            decision_type=decision_type,
            options=options,
            chosen=chosen,
            reason=reason,
            constraints=constraints or [],
        )
        trace.add_decision(decision)
        print(f"  📋 Decision: {decision_type} → {chosen}")


def log_llm_call(
    model: str,
    prompt_tokens: int,
    output_tokens: int,
    duration_s: float,
    success: bool = True,
) -> None:
    """Log an LLM call for token tracking"""
    trace = _current_trace.get()
    if trace:
        trace.add_llm_call(model, prompt_tokens, output_tokens, duration_s, success)


def _save_trace(trace: TraceContext) -> Path:
    """Save trace to JSON file"""
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    
    filename = f"{trace.trace_id}.json"
    filepath = TRACES_DIR / filename
    
    with open(filepath, "w") as f:
        json.dump(trace.to_dict(), f, indent=2)
    
    print(f"  💾 Trace saved: {filepath}")
    return filepath


def load_trace(trace_id: str) -> TraceContext | None:
    """Load a trace from disk for replay/debugging"""
    filepath = TRACES_DIR / f"{trace_id}.json"
    
    if not filepath.exists():
        return None
    
    with open(filepath, "r") as f:
        data = json.load(f)
    
    # Reconstruct trace (simplified - full reconstruction would rebuild all objects)
    trace = TraceContext(
        trace_id=data["trace_id"],
        name=data["name"],
        started_at=datetime.fromisoformat(data["started_at"]),
        metadata=data.get("metadata", {}),
    )
    trace.llm_calls = data.get("llm_calls", [])
    
    return trace
