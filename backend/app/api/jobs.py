"""
Jobs API: create, poll, stream progress via SSE, fetch faces, download output.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.core import job_store
from app.core.config import settings
from app.core.logger import get_logger
from app.models.job import (
    FaceInfo,
    Job,
    JobCreateRequest,
    JobProgressResponse,
    JobStatus,
    VideoMeta,
)
from app.pipelines.face_detector import face_detector
from app.pipelines.video_processor import process_video
from app.pipelines.image_processor import process_image
from app.services.ffmpeg import probe_video

logger = get_logger(__name__)
router = APIRouter()


class DetectFacesRequest(BaseModel):
    video_path: str
    face_path: str


class JobDetailResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int
    stage_message: str
    error_message: Optional[str] = None
    video_meta: Optional[VideoMeta] = None
    detected_faces: List[FaceInfo] = []
    output_ready: bool = False
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


def _job_to_detail(job: Job) -> JobDetailResponse:
    return JobDetailResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        stage_message=job.stage_message,
        error_message=job.error_message,
        video_meta=job.video_meta,
        detected_faces=job.detected_faces,
        output_ready=job.status == JobStatus.COMPLETED and job.output_path is not None,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


async def _run_job(job: Job) -> None:
    """Background coroutine that drives the face-swap pipeline."""
    job_id = job.job_id
    sem = job_store.get_semaphore()

    async with sem:
        job_store.update_job(job_id, started_at=time.time())
        try:
            def _progress(status: JobStatus, pct: int, msg: str):
                job_store.update_job(
                    job_id, status=status, progress=pct, stage_message=msg
                )
                logger.info("job_progress", job_id=job_id, status=status, pct=pct, msg=msg)

            # Run pipeline (Image-to-Image vs Video)
            is_image = Path(job.video_path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            if is_image:
                output_path = await process_image(job, _progress)
            else:
                output_path = await process_video(job, _progress)

            job_store.update_job(
                job_id,
                status=JobStatus.COMPLETED,
                progress=100,
                stage_message="Processing complete!",
                output_path=output_path,
                completed_at=time.time(),
            )
            # Cleanup temp files on success
            import shutil
            job_temp_dir = settings.temp_dir / job_id
            if job_temp_dir.exists():
                shutil.rmtree(job_temp_dir, ignore_errors=True)
                logger.info("temp_cleaned_after_success", job_id=job_id)

            logger.info("job_completed", job_id=job_id, output=output_path)

        except InterruptedError:
            logger.info("job_cancelled", job_id=job_id)
            job_store.update_job(
                job_id,
                status=JobStatus.CANCELLED,
                progress=0,
                stage_message="Job cancelled by user.",
                completed_at=time.time(),
            )
            # Cleanup temp files
            import shutil
            job_temp_dir = settings.temp_dir / job_id
            if job_temp_dir.exists():
                shutil.rmtree(job_temp_dir, ignore_errors=True)
                logger.info("temp_cleaned_after_cancel", job_id=job_id)

        except Exception as e:
            logger.error("job_failed", job_id=job_id, error=str(e))
            job_store.update_job(
                job_id,
                status=JobStatus.FAILED,
                progress=0,
                stage_message="Processing failed.",
                error_message=str(e),
                completed_at=time.time(),
            )
            # Cleanup temp files on failure too
            import shutil
            job_temp_dir = settings.temp_dir / job_id
            if job_temp_dir.exists():
                shutil.rmtree(job_temp_dir, ignore_errors=True)
                logger.info("temp_cleaned_after_failure", job_id=job_id)


@router.post("", response_model=JobDetailResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
) -> JobDetailResponse:
    """
    Create a new face-swap job.
    Expects absolute paths from previous /upload calls.
    """
    video_path = Path(request.video_upload_id)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video file not found: {video_path}")

    # Collect all face paths (multi-angle support)
    raw_face_ids = []
    if request.face_upload_ids:
        raw_face_ids = request.face_upload_ids
    elif request.face_upload_id:
        raw_face_ids = [request.face_upload_id]

    if not raw_face_ids:
        raise HTTPException(status_code=422, detail="Kam se kam ek reference face photo upload karo.")

    valid_face_paths: list[str] = []
    for fid in raw_face_ids:
        p = Path(fid)
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"Face image not found: {p}")
        valid_face_paths.append(str(p))

    primary_face_path = valid_face_paths[0]

    quality = request.quality if request.quality in ("fast", "balanced", "high") else "balanced"
    is_target_image = video_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}

    meta = None
    face_infos = []

    if is_target_image:
        # Static Photo target
        try:
            import cv2
            target_bgr = cv2.imread(str(video_path))
            if target_bgr is not None:
                detected = face_detector.detect_in_image(target_bgr)
                face_infos = face_detector.faces_to_face_info(target_bgr, detected)
        except Exception as e:
            logger.warning("target_image_face_detect_warning", error=str(e))
    else:
        # Video target — probe & sample representative frame
        try:
            meta = probe_video(video_path)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Cannot read video: {e}")

        try:
            rep_frame, video_faces = face_detector.get_representative_frame_faces(video_path)
            face_infos = face_detector.faces_to_face_info(rep_frame, video_faces)
        except Exception as e:
            logger.warning("face_detect_warning", error=str(e))

    if not face_infos:
        logger.warning("no_faces_in_target", job_id="new")

    # Create job with multi-face paths
    job = job_store.create_job(
        video_path=str(video_path),
        face_path=primary_face_path,
        face_paths=valid_face_paths,
        quality=quality,
        enhance=request.enhance,
        target_face_index=request.target_face_index,
    )
    job_store.update_job(
        job.job_id,
        video_meta=meta,
        detected_faces=face_infos,
    )

    # Refresh job reference (update_job returns updated obj)
    job = job_store.get_job(job.job_id)

    # Schedule background processing
    background_tasks.add_task(_run_job, job)

    return _job_to_detail(job)


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: str) -> JobDetailResponse:
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return _job_to_detail(job)


@router.get("/{job_id}/progress", response_model=JobProgressResponse)
async def get_job_progress(job_id: str) -> JobProgressResponse:
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return JobProgressResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        stage_message=job.stage_message,
        error_message=job.error_message,
        output_ready=job.status == JobStatus.COMPLETED and job.output_path is not None,
    )


@router.get("/{job_id}/stream")
async def stream_progress(job_id: str):
    """Server-Sent Events endpoint for real-time progress."""
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    async def event_generator() -> AsyncGenerator[str, None]:
        last_pct = -1
        last_status = None
        while True:
            j = job_store.get_job(job_id)
            if j is None:
                break

            # Send update on any progress % change OR status change
            if j.progress != last_pct or j.status != last_status:
                data = {
                    "job_id": j.job_id,
                    "status": j.status.value,
                    "progress": j.progress,
                    "stage_message": j.stage_message,
                    "error_message": j.error_message,
                    "output_ready": j.status == JobStatus.COMPLETED,
                }
                yield f"data: {json.dumps(data)}\n\n"
                last_pct = j.progress
                last_status = j.status

            if j.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/faces", response_model=List[FaceInfo])
async def get_job_faces(job_id: str) -> List[FaceInfo]:
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job.detected_faces


@router.get("/{job_id}/output")
async def get_job_output(job_id: str):
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.status != JobStatus.COMPLETED or not job.output_path:
        raise HTTPException(status_code=404, detail="Output not ready yet.")
    output = Path(job.output_path)
    if not output.exists():
        raise HTTPException(status_code=404, detail="Output file not found on disk.")
    ext = output.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif ext == ".png":
        media_type = "image/png"
    elif ext == ".webp":
        media_type = "image/webp"
    else:
        media_type = "video/mp4"

    return FileResponse(
        str(output),
        media_type=media_type,
        filename=f"faceflux_{job_id}{ext}",
    )


@router.post("/{job_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_job(job_id: str):
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=409, detail="Job is already finished.")
    job_store.cancel_job(job_id)
    return {"message": "Cancellation requested.", "job_id": job_id}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str):
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.QUEUED, JobStatus.CANCELLED):
        raise HTTPException(status_code=409, detail="Cannot delete a running job.")
    job_store.delete_job(job_id)
