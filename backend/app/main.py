"""
FaceFlux application factory and lifespan management.

Stage 3 additions:
  - Auto cleanup background task (temp files + old jobs)
  - Graceful shutdown
"""

import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import get_logger
from app.core.directories import ensure_directories
from app.services.hardware import hardware_service
from app.api import health, upload, jobs, system, generate, tryon

logger = get_logger(__name__)

# ── Cleanup background task ────────────────────────────────────────────────────

async def _auto_cleanup_loop() -> None:
    """
    Background task that runs every 6 hours.
    Deletes old job records (>48h) and temp dirs (>24h) automatically.
    Prevents disk from filling up over time.
    """
    # Wait 5 minutes after startup before first cleanup
    await asyncio.sleep(300)

    while True:
        try:
            from app.core.job_store import cleanup_old_jobs, cleanup_temp_files
            jobs_deleted = cleanup_old_jobs(max_age_hours=48.0, delete_files=True)
            dirs_deleted = cleanup_temp_files(max_age_hours=24.0)
            if jobs_deleted > 0 or dirs_deleted > 0:
                logger.info(
                    "auto_cleanup_complete",
                    jobs_deleted=jobs_deleted,
                    temp_dirs_deleted=dirs_deleted,
                )
        except Exception as e:
            logger.warning("auto_cleanup_error", error=str(e))

        # Run every 6 hours
        await asyncio.sleep(6 * 3600)


# ── CORS ──────────────────────────────────────────────────────────────────────

def _get_cors_origins() -> list[str]:
    """
    Read allowed CORS origins from env var CORS_ORIGINS (comma-separated).
    Always includes localhost for local dev.

    Example .env:
      CORS_ORIGINS=https://faceflux.vercel.app,https://your-app.vercel.app
    """
    extra = os.environ.get("CORS_ORIGINS", "*")
    if extra.strip() == "*":
        return ["*"]
    defaults = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    if extra:
        extras = [o.strip() for o in extra.split(",") if o.strip()]
        return list(set(defaults + extras))
    return ["*"]


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("faceflux_starting", version="2.0.0")
    ensure_directories()
    hardware_service.detect()
    logger.info("hardware_detected", info=hardware_service.summary())

    # Start background cleanup task
    cleanup_task = asyncio.create_task(_auto_cleanup_loop())
    logger.info("auto_cleanup_scheduled", interval_hours=6)

    yield

    # Graceful shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("faceflux_stopped")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    application = FastAPI(
        title="FaceFlux API",
        description="Local-first AI face-swap backend — v2.0",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    cors_origins = _get_cors_origins()
    logger.info("cors_configured", origins=cors_origins)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router, tags=["Health"])
    application.include_router(system.router, prefix="/system-info", tags=["System"])
    application.include_router(upload.router, prefix="/upload", tags=["Upload"])
    application.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
    application.include_router(generate.router, prefix="/generate", tags=["Generate"])
    application.include_router(tryon.router, prefix="/tryon", tags=["TryOn"])

    return application
