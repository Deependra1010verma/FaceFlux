"""Ensure required data directories exist at startup."""

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


def ensure_directories() -> None:
    dirs = [
        settings.model_dir,
        settings.upload_dir,
        settings.output_dir,
        settings.temp_dir,
        settings.frames_dir,
        settings.log_dir,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        logger.debug("directory_ready", path=str(d))
