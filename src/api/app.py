"""
InterView AI - FastAPI Application.

Main FastAPI app that serves the API and static frontend files.
Includes background task for periodic session cleanup.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.core.config import configure_logging
from src.api.routes import router as api_router, cleanup_stale_sessions, session_repo

# Configure logging
configure_logging()
logger = logging.getLogger(__name__)

# Background cleanup task reference
_cleanup_task: asyncio.Task | None = None


async def background_cleanup_task():
    """
    Background task to clean up stale sessions periodically.
    
    Runs every 30 minutes to:
    - Remove in-memory sessions older than SESSION_TIMEOUT_HOURS
    - Clean up persisted session files older than 24 hours
    """
    logger.info("🧹 Background cleanup task started")
    
    while True:
        try:
            # Wait 30 minutes between cleanup runs
            await asyncio.sleep(30 * 60)
            
            # Clean up in-memory stale sessions
            memory_count = cleanup_stale_sessions()
            
            # Clean up old session files from disk
            disk_count = session_repo.cleanup_old_sessions(max_age_hours=24)
            
            if memory_count > 0 or disk_count > 0:
                logger.info(
                    f"🧹 Cleanup complete: {memory_count} memory sessions, "
                    f"{disk_count} disk files removed"
                )
                
        except asyncio.CancelledError:
            logger.info("🧹 Background cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"🧹 Cleanup task error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown events:
    - Startup: Start background cleanup task, load Whisper asynchronously
    - Shutdown: Cancel cleanup task gracefully
    """
    global _cleanup_task
    
    # Startup
    logger.info("🚀 InterView AI API starting...")
    
    # Start background cleanup task
    try:
        _cleanup_task = asyncio.create_task(background_cleanup_task())
    except Exception as e:
        logger.error(f"Failed to start cleanup task: {e}")
    
    # Warm up Whisper model asynchronously (non-blocking)
    logger.info("🔥 Pre-loading Whisper STT model (background)...")
    try:
        def load_whisper_safe():
            """Load Whisper with comprehensive error handling."""
            try:
                from src.infra.speech.stt import WhisperSTT
                stt = WhisperSTT()
                logger.info("✅ Whisper model loaded successfully")
                return True
            except Exception as e:
                logger.warning(f"⚠️ Whisper model warmup failed (will retry on first use): {e}")
                return False
        
        # Run in thread pool to avoid blocking startup
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(None, load_whisper_safe)
        # Don't await - let it load in background
        logger.info("📦 Whisper model loading started in background (server will be ready immediately)")
    except Exception as e:
        logger.error(f"⚠️ Failed to start Whisper loading task: {e}")
    
    yield
    
    # Shutdown
    logger.info("👋 InterView AI API shutting down...")
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="InterView AI",
        description="Real-Time AI Career Coach API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )
    
    # Rate limiting
    from slowapi.middleware import SlowAPIMiddleware
    from src.api.routes import limiter
    
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    
    # CORS middleware for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict this
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    app.include_router(api_router)
    
    # Serve static frontend files
    frontend_path = Path(__file__).parent.parent.parent / "frontend"
    if frontend_path.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")
    
    # Serve index.html at root
    @app.get("/")
    async def serve_frontend():
        index_path = frontend_path / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "InterView AI API is running. Frontend not found."}
    
    return app


# Create app instance
app = create_app()

