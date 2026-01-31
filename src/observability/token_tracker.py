"""Token Tracker - Track LLM token usage across pipeline runs"""
import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.config import CORPUS_METADATA_DIR


# Token tracking file
TOKEN_STATS_FILE = CORPUS_METADATA_DIR / "token_stats.json"


@dataclass
class TokenUsage:
    """Token usage for a single LLM call"""
    model: str
    prompt_tokens: int
    output_tokens: int
    duration_seconds: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SessionStats:
    """Token statistics for current session"""
    total_prompt_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0
    total_duration_seconds: float = 0.0
    session_started: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "total_tokens": self.total_prompt_tokens + self.total_output_tokens,
            "avg_tokens_per_call": (self.total_prompt_tokens + self.total_output_tokens) / max(1, self.total_calls),
            "avg_duration_per_call": self.total_duration_seconds / max(1, self.total_calls),
        }


class TokenTracker:
    """
    Singleton class to track token usage across LLM calls.
    
    Usage:
        from src.observability.token_tracker import tracker
        tracker.record(model="qwen2.5:7b", prompt_tokens=100, output_tokens=50, duration=1.5)
        stats = tracker.get_session_stats()
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._session_stats = SessionStats()
        self._callbacks: list[Callable[[TokenUsage], None]] = []
        self._initialized = True
    
    def record(
        self,
        model: str,
        prompt_tokens: int,
        output_tokens: int,
        duration_seconds: float
    ) -> TokenUsage:
        """Record a token usage event and notify callbacks"""
        usage = TokenUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
        )
        
        # Update session stats
        self._session_stats.total_prompt_tokens += prompt_tokens
        self._session_stats.total_output_tokens += output_tokens
        self._session_stats.total_calls += 1
        self._session_stats.total_duration_seconds += duration_seconds
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(usage)
            except Exception:
                pass
        
        return usage
    
    def add_callback(self, callback: Callable[[TokenUsage], None]) -> None:
        """Add a callback to be notified on each token usage"""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[TokenUsage], None]) -> None:
        """Remove a callback"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def get_session_stats(self) -> dict:
        """Get current session statistics"""
        return self._session_stats.to_dict()
    
    def reset_session(self) -> None:
        """Reset session statistics"""
        self._session_stats = SessionStats()
    
    def save_stats(self) -> None:
        """Save current stats to disk"""
        TOKEN_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing or create new cumulative stats
        cumulative = {"total_prompt_tokens": 0, "total_output_tokens": 0, "total_calls": 0}
        if TOKEN_STATS_FILE.exists():
            try:
                with open(TOKEN_STATS_FILE) as f:
                    cumulative = json.load(f)
            except Exception:
                pass
        
        # Add session stats
        cumulative["total_prompt_tokens"] += self._session_stats.total_prompt_tokens
        cumulative["total_output_tokens"] += self._session_stats.total_output_tokens
        cumulative["total_calls"] += self._session_stats.total_calls
        cumulative["last_updated"] = datetime.now().isoformat()
        
        with open(TOKEN_STATS_FILE, "w") as f:
            json.dump(cumulative, f, indent=2)
    
    @staticmethod
    def load_cumulative_stats() -> dict:
        """Load cumulative stats from disk"""
        if not TOKEN_STATS_FILE.exists():
            return {"total_prompt_tokens": 0, "total_output_tokens": 0, "total_calls": 0}
        
        try:
            with open(TOKEN_STATS_FILE) as f:
                return json.load(f)
        except Exception:
            return {"total_prompt_tokens": 0, "total_output_tokens": 0, "total_calls": 0}


# Singleton instance
tracker = TokenTracker()
