"""Langfuse Integration - Optional LLM observability (no OTel dependency)"""
import os
from typing import Any


# Langfuse config from environment
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

_client = None
_enabled = False


def is_configured() -> bool:
    """Check if Langfuse credentials are set"""
    return bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)


def init() -> bool:
    """Initialize Langfuse client"""
    global _client, _enabled
    
    if not is_configured():
        print("ℹ️ Langfuse not configured (set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)")
        return False
    
    try:
        from langfuse import Langfuse
        
        _client = Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
        )
        
        if _client.auth_check():
            _enabled = True
            print("✅ Langfuse connected")
            return True
        else:
            print("⚠️ Langfuse auth failed")
            return False
            
    except ImportError:
        print("ℹ️ Langfuse not installed (pip install langfuse)")
        return False
    except Exception as e:
        print(f"⚠️ Langfuse error: {e}")
        return False


def log_generation(
    name: str,
    model: str,
    input_text: str,
    output_text: str,
    input_tokens: int,
    output_tokens: int,
    duration_s: float,
    metadata: dict | None = None,
) -> None:
    """Log an LLM generation to Langfuse"""
    if not _enabled or not _client:
        return
    
    try:
        _client.generation(
            name=name,
            model=model,
            input=input_text[:2000],  # Truncate
            output=output_text[:2000],
            usage={
                "input": input_tokens,
                "output": output_tokens,
            },
            metadata=metadata or {},
        )
    except Exception:
        pass  # Silent fail for observability


def flush() -> None:
    """Flush pending events"""
    if _client:
        try:
            _client.flush()
        except Exception:
            pass


def shutdown() -> None:
    """Shutdown client"""
    global _client, _enabled
    flush()
    _client = None
    _enabled = False
