"""
Upload endpoints.
Files are saved locally with sanitized names.
No external storage.
"""

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.logger import get_logger
from app.core.security import unique_path
from app.models.upload import UploadResponse

logger = get_logger(__name__)
router = APIRouter()

ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_MIME = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm", "video/x-msvideo", "video/avi"}
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}


ALLOWED_TARGET_EXTS = ALLOWED_VIDEO_EXTS | ALLOWED_IMAGE_EXTS


async def _save_upload(file: UploadFile, directory, allowed_exts: set, max_bytes: int) -> tuple[str, int]:
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' not allowed. Allowed: {sorted(allowed_exts)}",
        )

    dest = unique_path(directory, filename)
    total = 0
    chunk_size = 1024 * 1024  # 1 MB

    async with aiofiles.open(dest, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large. Max size: {max_bytes // (1024*1024)} MB",
                )
            await f.write(chunk)

    logger.info("file_saved", path=str(dest), size_bytes=total)
    return str(dest), total


@router.post("/video", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)) -> UploadResponse:
    path, size = await _save_upload(
        file,
        settings.upload_dir,
        ALLOWED_TARGET_EXTS,
        settings.max_video_size_bytes,
    )
    upload_id = path.rsplit("/", 1)[-1].split("_")[0]
    return UploadResponse(
        upload_id=upload_id,
        filename=file.filename or "video",
        size_bytes=size,
        path=path,
    )


@router.post("/face", response_model=UploadResponse)
async def upload_face(file: UploadFile = File(...)) -> UploadResponse:
    path, size = await _save_upload(
        file,
        settings.upload_dir,
        ALLOWED_IMAGE_EXTS,
        settings.max_image_size_bytes,
    )
    upload_id = path.rsplit("/", 1)[-1].split("_")[0]
    return UploadResponse(
        upload_id=upload_id,
        filename=file.filename or "face",
        size_bytes=size,
        path=path,
    )
