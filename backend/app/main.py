"""
FaceFlux application factory and lifespan management.

Improvements:
  - Auto cleanup background task (temp files + old jobs)
  - Stuck job recovery on startup (marks SWAPPING/PROCESSING jobs as FAILED)
  - Model preloading in background (zero lag on first request)
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

VERSION = "2.1.0"

# ── Stuck job recovery ─────────────────────────────────────────────────────────

def _recover_stuck_jobs() -> None:
    """
    On startup, any jobs still in processing states were interrupted by a server
    restart. Mark them FAILED so users know to resubmit instead of waiting forever.
    """
    try:
        from app.core.job_store import list_jobs, update_job
        from app.models.job import JobStatus

        stuck_statuses = [
            JobStatus.ANALYZING, JobStatus.DETECTING, JobStatus.TRACKING,
            JobStatus.SWAPPING, JobStatus.ENHANCING, JobStatus.ENCODING,
        ]
        recovered = 0
        for job in list_jobs():
            if job.status in stuck_statuses:
                update_job(
                    job.job_id,
                    status=JobStatus.FAILED,
                    error_message=(
                        "Job was interrupted by server restart. "
                        "Please resubmit your request."
                    ),
                )
                recovered += 1
                logger.warning("stuck_job_recovered", job_id=job.job_id,
                               was_status=job.status.value)
        if recovered > 0:
            logger.info("startup_recovery_complete", recovered=recovered)
    except Exception as e:
        logger.warning("stuck_job_recovery_failed", error=str(e))


# ── Model preloading ───────────────────────────────────────────────────────────

async def _preload_models() -> None:
    """
    Load heavy ONNX models in background so the first real request has zero delay.
    Runs 2 seconds after startup to let the server become ready first.
    """
    await asyncio.sleep(2)
    loop = asyncio.get_running_loop()
    try:
        from app.pipelines.face_detector import face_detector
        await loop.run_in_executor(None, face_detector._load)
        logger.info("model_preloaded", model="face_detector")
    except Exception as e:
        logger.warning("model_preload_failed", model="face_detector", error=str(e))

    try:
        from app.pipelines.face_swapper import face_swapper
        await loop.run_in_executor(None, face_swapper._load)
        logger.info("model_preloaded", model="face_swapper")
    except Exception as e:
        logger.warning("model_preload_failed", model="face_swapper", error=str(e))

    try:
        from app.pipelines.face_enhancer import face_enhancer
        # Only preload if model file exists
        if face_enhancer.is_available:
            await loop.run_in_executor(None, lambda: face_enhancer._load())
            logger.info("model_preloaded", model="face_enhancer_gpen")
    except Exception as e:
        logger.warning("model_preload_failed", model="face_enhancer", error=str(e))


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
            from app.core.job_store import cleanup_old_jobs, cleanup_temp_files, cleanup_upload_files
            from app.core.generic_store import GenericJobStore
            from app.models.gen_job import GenJob
            from app.models.tryon_job import TryOnJob

            jobs_deleted = cleanup_old_jobs(max_age_hours=48.0, delete_files=True)
            dirs_deleted = cleanup_temp_files(max_age_hours=24.0)
            uploads_deleted = cleanup_upload_files(max_age_hours=6.0)

            # Cleanup generate + tryon jobs (reuse existing store instances via import)
            gen_store: GenericJobStore[GenJob] = GenericJobStore("gen_jobs", GenJob)
            tryon_store: GenericJobStore[TryOnJob] = GenericJobStore("tryon_jobs", TryOnJob)
            gen_deleted = gen_store.cleanup_old(max_age_hours=48.0, delete_files=True)
            tryon_deleted = tryon_store.cleanup_old(max_age_hours=48.0, delete_files=True)

            total_deleted = jobs_deleted + gen_deleted + tryon_deleted
            if total_deleted > 0 or dirs_deleted > 0 or uploads_deleted > 0:
                logger.info(
                    "auto_cleanup_complete",
                    face_jobs_deleted=jobs_deleted,
                    gen_jobs_deleted=gen_deleted,
                    tryon_jobs_deleted=tryon_deleted,
                    temp_dirs_deleted=dirs_deleted,
                    uploads_deleted=uploads_deleted,
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
    logger.info("faceflux_starting", version=VERSION)
    ensure_directories()
    hardware_service.detect()
    logger.info("hardware_detected", info=hardware_service.summary())

    # Recover any jobs stuck in processing state from previous run
    _recover_stuck_jobs()

    # Start background tasks
    preload_task = asyncio.create_task(_preload_models())
    cleanup_task = asyncio.create_task(_auto_cleanup_loop())
    logger.info("background_tasks_started", tasks=["model_preload", "auto_cleanup"])

    yield

    # Graceful shutdown
    preload_task.cancel()
    cleanup_task.cancel()
    try:
        await asyncio.gather(preload_task, cleanup_task, return_exceptions=True)
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
