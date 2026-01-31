"""Dashboard Server - FastAPI backend with REST API and WebSocket"""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.config import DATA_DIR
from src.dashboard.runner import (
    runner,
    get_available_files,
    get_corpus_stats,
    get_checkpoint_info,
    PipelineState,
)
from src.observability.progress import ProgressEvent


# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections for broadcasting progress"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        
        # Clean up disconnected
        for conn in disconnected:
            self.active_connections.discard(conn)


manager = ConnectionManager()


# Background task to forward progress events
async def progress_forwarder():
    """Forward progress events to WebSocket clients"""
    event_queue: asyncio.Queue = asyncio.Queue()
    
    def on_progress(event: ProgressEvent):
        try:
            asyncio.get_event_loop().call_soon_threadsafe(
                event_queue.put_nowait, event
            )
        except RuntimeError:
            pass  # Event loop not running
    
    runner.add_progress_callback(on_progress)
    
    while True:
        try:
            event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
            await manager.broadcast({
                "type": "progress",
                "data": event.to_dict(),
            })
        except asyncio.TimeoutError:
            # Send heartbeat with current status
            if manager.active_connections:
                await manager.broadcast({
                    "type": "status",
                    "data": runner.status.to_dict(),
                })
        except Exception:
            pass


# Lifespan for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start progress forwarder
    task = asyncio.create_task(progress_forwarder())
    yield
    # Cleanup
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="BookContentPipeline Dashboard",
    description="Admin dashboard for managing corpus pipeline",
    lifespan=lifespan,
)


# Request/Response models
class StartRunRequest(BaseModel):
    files: list[str]  # file paths
    force: bool = False


class RunResponse(BaseModel):
    success: bool
    message: str


# REST API Endpoints
@app.get("/api/files")
async def list_files():
    """List available EPUB files"""
    return get_available_files()


@app.get("/api/corpus/stats")
async def corpus_stats():
    """Get corpus statistics"""
    return get_corpus_stats()


@app.get("/api/checkpoint")
async def checkpoint_info():
    """Get current checkpoint information"""
    info = get_checkpoint_info()
    if info is None:
        return {"exists": False}
    return {"exists": True, **info}


@app.get("/api/run/status")
async def run_status():
    """Get current run status"""
    return runner.status.to_dict()


@app.post("/api/run/start", response_model=RunResponse)
async def start_run(request: StartRunRequest):
    """Start pipeline processing"""
    if not request.files:
        raise HTTPException(status_code=400, detail="No files specified")
    
    # Convert to Path objects
    file_paths = []
    for file_str in request.files:
        path = Path(file_str)
        if not path.exists():
            # Try relative to DATA_DIR
            path = DATA_DIR / file_str
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_str}")
        file_paths.append(path)
    
    success = runner.start(file_paths, force=request.force)
    if success:
        return RunResponse(success=True, message="Pipeline started")
    else:
        return RunResponse(success=False, message="Pipeline already running")


@app.post("/api/run/pause", response_model=RunResponse)
async def pause_run():
    """Pause the running pipeline"""
    success = runner.pause()
    if success:
        return RunResponse(success=True, message="Pipeline paused")
    else:
        return RunResponse(success=False, message="Cannot pause - not running")


@app.post("/api/run/resume", response_model=RunResponse)
async def resume_run():
    """Resume paused pipeline"""
    success = runner.resume()
    if success:
        return RunResponse(success=True, message="Pipeline resumed")
    else:
        return RunResponse(success=False, message="Cannot resume - not paused")


@app.post("/api/run/stop", response_model=RunResponse)
async def stop_run():
    """Stop the pipeline"""
    success = runner.stop()
    if success:
        return RunResponse(success=True, message="Stop requested")
    else:
        return RunResponse(success=False, message="Cannot stop - not running")


@app.post("/api/run/reset", response_model=RunResponse)
async def reset_run():
    """Reset runner state after completion/error"""
    success = runner.reset()
    if success:
        return RunResponse(success=True, message="Runner reset")
    else:
        return RunResponse(success=False, message="Cannot reset while running")


# WebSocket endpoint
@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """WebSocket for real-time progress updates"""
    await manager.connect(websocket)
    
    # Send initial status
    await websocket.send_json({
        "type": "status",
        "data": runner.status.to_dict(),
    })
    
    try:
        while True:
            # Keep connection alive with ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Serve static files
STATIC_DIR = Path(__file__).parent / "static"

# Mount static files if directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serve the dashboard HTML"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Dashboard frontend not found. API is available at /api/"}


def main():
    """Run the dashboard server"""
    import uvicorn
    from src.config import DASHBOARD_HOST, DASHBOARD_PORT
    
    print(f"\n{'='*60}")
    print("📊 BookContentPipeline Dashboard")
    print(f"{'='*60}")
    print(f"Starting server at http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    print("Press Ctrl+C to stop\n")
    
    uvicorn.run(
        "src.dashboard.server:app",
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        reload=False,
        log_level="warning",  # Reduce log noise
    )


if __name__ == "__main__":
    main()
