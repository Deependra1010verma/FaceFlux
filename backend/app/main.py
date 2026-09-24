"""
FaceFlux application factory and lifespan management.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import get_logger
from app.core.directories import ensure_directories
from app.services.hardware import hardware_service
from app.api import health, upload, jobs, system

logger = get_logger(__name__)


def _get_cors_origins() -> list[str]:
    """
    Read allowed CORS origins from env var CORS_ORIGINS (comma-separated).
    Always includes localhost for local dev.
    
    Example .env:
      CORS_ORIGINS=https://faceflux.vercel.app,https://your-app.vercel.app
    """
    defaults = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    extra = os.environ.get("CORS_ORIGINS", "")
    if extra:
        extras = [o.strip() for o in extra.split(",") if o.strip()]
        return list(set(defaults + extras))
    return defaults


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("faceflux_starting", version="1.0.0")
    ensure_directories()
    hardware_service.detect()
    logger.info("hardware_detected", info=hardware_service.summary())
    yield
    logger.info("faceflux_stopping")


def create_app() -> FastAPI:
    application = FastAPI(
        title="FaceFlux API",
        description="Local-first AI face-swap backend",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    cors_origins = _get_cors_origins()
    logger.info("cors_origins_configured", origins=cors_origins)

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

    return application
