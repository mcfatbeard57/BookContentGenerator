"""Pipeline Runner - State machine for pipeline control with pause/resume/stop"""
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from src.config import DATA_DIR, CORPUS_DIR, CHECKPOINT_FILE
from src.observability.checkpoint import load_checkpoint, ExtractionCheckpoint
from src.observability.progress import (
    ProgressEvent,
    ProgressStage,
    add_progress_listener,
    request_interrupt,
    check_interrupt,
    clear_interrupt,
)


class PipelineState(Enum):
    """Current state of the pipeline runner"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class RunStatus:
    """Current run status for API responses"""
    state: PipelineState = PipelineState.IDLE
    current_stage: str = ""
    progress_percent: float = 0.0
    current_item: int = 0
    total_items: int = 0
    message: str = ""
    started_at: datetime | None = None
    files_processing: list[str] = field(default_factory=list)
    error: str | None = None
    
    def to_dict(self) -> dict:
        # Get token stats from tracker
        from src.observability.token_tracker import tracker
        token_stats = tracker.get_session_stats()
        
        return {
            "state": self.state.value,
            "current_stage": self.current_stage,
            "progress_percent": round(self.progress_percent, 1),
            "current_item": self.current_item,
            "total_items": self.total_items,
            "message": self.message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "files_processing": self.files_processing,
            "error": self.error,
            "tokens": token_stats,
        }


class PipelineRunner:
    """
    Manages pipeline execution with pause/resume/stop controls.
    
    Usage:
        runner = PipelineRunner()
        runner.add_progress_callback(my_callback)
        runner.start([Path("book.epub")], force=False)
        runner.pause()
        runner.resume()
        runner.stop()
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern - only one runner at a time"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._status = RunStatus()
        self._thread: threading.Thread | None = None
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._stop_requested = False
        self._progress_callbacks: list[Callable[[ProgressEvent], None]] = []
        
        # Register with the existing progress system
        add_progress_listener(self._on_progress_event)
        
        self._initialized = True
    
    @property
    def status(self) -> RunStatus:
        return self._status
    
    def add_progress_callback(self, callback: Callable[[ProgressEvent], None]) -> None:
        """Add callback to receive progress events"""
        self._progress_callbacks.append(callback)
    
    def remove_progress_callback(self, callback: Callable[[ProgressEvent], None]) -> None:
        """Remove a progress callback"""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    def _on_progress_event(self, event: ProgressEvent) -> None:
        """Handle progress events from the pipeline"""
        self._status.current_stage = event.stage.value
        self._status.progress_percent = event.percentage
        self._status.current_item = event.current
        self._status.total_items = event.total
        self._status.message = event.message or ""
        
        # Forward to registered callbacks
        for callback in self._progress_callbacks:
            try:
                callback(event)
            except Exception:
                pass
        
        # Check for pause/stop between operations
        if not event.can_interrupt:
            return
        
        # Handle pause
        while not self._pause_event.is_set():
            if self._stop_requested:
                break
            time.sleep(0.1)
        
        # Handle stop
        if self._stop_requested:
            request_interrupt()
    
    def start(self, files: list[Path], force: bool = False) -> bool:
        """
        Start pipeline processing in background thread.
        
        Args:
            files: List of EPUB file paths to process
            force: If True, reprocess already-processed books
            
        Returns:
            True if started, False if already running
        """
        if self._status.state == PipelineState.RUNNING:
            return False
        
        if self._status.state == PipelineState.PAUSED:
            return False
        
        # Reset state
        self._stop_requested = False
        self._pause_event.set()
        clear_interrupt()
        
        self._status = RunStatus(
            state=PipelineState.RUNNING,
            started_at=datetime.now(),
            files_processing=[f.name for f in files],
        )
        
        # Start pipeline in background thread
        self._thread = threading.Thread(
            target=self._run_pipeline,
            args=(files, force),
            daemon=True,
        )
        self._thread.start()
        
        return True
    
    def _run_pipeline(self, files: list[Path], force: bool) -> None:
        """Run the pipeline in a background thread"""
        try:
            from src.pipeline import run_pipeline
            run_pipeline(files, force_reprocess=force)
            
            if self._stop_requested:
                self._status.state = PipelineState.IDLE
                self._status.message = "Stopped by user"
            else:
                self._status.state = PipelineState.COMPLETED
                self._status.message = "Pipeline completed successfully"
                self._status.progress_percent = 100.0
                
        except Exception as e:
            self._status.state = PipelineState.ERROR
            self._status.error = str(e)
            self._status.message = f"Error: {e}"
        
        finally:
            self._stop_requested = False
            clear_interrupt()
    
    def pause(self) -> bool:
        """Pause the running pipeline at next checkpoint"""
        if self._status.state != PipelineState.RUNNING:
            return False
        
        self._pause_event.clear()
        self._status.state = PipelineState.PAUSED
        self._status.message = "Paused - waiting at next safe point"
        return True
    
    def resume(self) -> bool:
        """Resume a paused pipeline"""
        if self._status.state != PipelineState.PAUSED:
            return False
        
        self._pause_event.set()
        self._status.state = PipelineState.RUNNING
        self._status.message = "Resumed"
        return True
    
    def stop(self) -> bool:
        """Stop the pipeline gracefully"""
        if self._status.state not in (PipelineState.RUNNING, PipelineState.PAUSED):
            return False
        
        self._stop_requested = True
        self._pause_event.set()  # Unblock if paused
        self._status.state = PipelineState.STOPPING
        self._status.message = "Stopping at next safe point..."
        
        request_interrupt()
        return True
    
    def reset(self) -> bool:
        """Reset runner to idle state after completion/error"""
        if self._status.state in (PipelineState.RUNNING, PipelineState.PAUSED, PipelineState.STOPPING):
            return False
        
        self._status = RunStatus()
        return True


def get_available_files() -> list[dict]:
    """Get list of available EPUB files in Data directory"""
    files = []
    for epub_path in DATA_DIR.glob("*.epub"):
        files.append({
            "name": epub_path.name,
            "path": str(epub_path),
            "size_mb": round(epub_path.stat().st_size / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(epub_path.stat().st_mtime).isoformat(),
        })
    return sorted(files, key=lambda x: x["name"])


def get_corpus_stats() -> dict:
    """Get corpus statistics"""
    from src.corpus.graph_builder import load_graph
    from src.ingestion.registry import load_registry
    
    stats = {
        "entities": {
            "characters": 0,
            "locations": 0,
            "factions": 0,
            "timeline_events": 0,
        },
        "graph": {
            "nodes": 0,
            "edges": 0,
        },
        "books_processed": 0,
    }
    
    # Count entity files
    for entity_type in ["characters", "locations", "factions", "timeline"]:
        entity_dir = CORPUS_DIR / entity_type
        if entity_dir.exists():
            # Count all .md files recursively (handles priority subdirs)
            count = len(list(entity_dir.rglob("*.md")))
            key = entity_type if entity_type != "timeline" else "timeline_events"
            stats["entities"][key] = count
    
    # Graph stats
    try:
        graph = load_graph()
        stats["graph"]["nodes"] = len(graph.nodes)
        stats["graph"]["edges"] = len(graph.edges)
    except Exception:
        pass
    
    # Books processed
    try:
        registry = load_registry()
        stats["books_processed"] = len(registry.processed_books)
    except Exception:
        pass
    
    return stats


def get_checkpoint_info() -> dict | None:
    """Get current checkpoint information"""
    if not CHECKPOINT_FILE.exists():
        return None
    
    try:
        checkpoint = load_checkpoint("")  # Will return None if book_id doesn't match
        # Load raw checkpoint file
        import json
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
        return {
            "book_id": data.get("book_id"),
            "book_title": data.get("book_title"),
            "completed_chapters": len(data.get("completed_chapters", [])),
            "total_chapters": data.get("total_chapters", 0),
            "entities_extracted": len(data.get("entities_extracted", [])),
            "last_updated": data.get("last_updated"),
            "errors": data.get("errors", []),
        }
    except Exception:
        return None


# Singleton instance
runner = PipelineRunner()
