"""
Virtual Try-On API: upload video + clothing photo → get try-on video.

POST /tryon              — Create try-on job
GET  /tryon/{id}         — Job status
GET  /tryon/{id}/stream  — SSE real-time progress
GET  /tryon/{id}/output  — Download result mp4
POST /tryon/{id}/cancel  — Cancel running job
DELETE /tryon/{id}       — Delete finished job
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.models.tryon_job import TryOnJob, TryOnJobCreateRequest, TryOnJobResponse, TryOnStatus
from app.pipelines.outfit_transfer import transfer_outfit

logger = get_logger(__name__)
router = APIRouter()

_tryon_jobs: Dict[str, TryOnJob] = {}
_cancelled_tryon_jobs: set = set()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_response(job: TryOnJob) -> TryOnJobResponse:
    return TryOnJobResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        stage_message=job.stage_message,
        error_message=job.error_message,
        output_ready=job.status == TryOnStatus.COMPLETED and job.output_path is not None,
        total_frames=job.total_frames,
        processed_frames=job.processed_frames,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


def _update(job_id: str, **kwargs) -> None:
    job = _tryon_jobs.get(job_id)
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)


# ── Background task ───────────────────────────────────────────────────────────

async def _run_tryon_job(job: TryOnJob) -> None:
    job_id = job.job_id

    def progress(s: TryOnStatus, pct: int, msg: str, processed: int, total: int) -> None:
        if job_id in _cancelled_tryon_jobs:
            raise InterruptedError("Cancelled by user.")
        _update(
            job_id,
            status=s, progress=pct, stage_message=msg,
            processed_frames=processed, total_frames=total,
        )
        logger.info("tryon_progress", job_id=job_id, pct=pct, msg=msg)

    try:
        output_path = await transfer_outfit(job, progress)
        _update(
            job_id,
            status=TryOnStatus.COMPLETED,
            progress=100,
            stage_message="Try-on complete! Video ready hai.",
            output_path=output_path,
            completed_at=time.time(),
        )
        logger.info("tryon_job_completed", job_id=job_id)

    except InterruptedError:
        _update(
            job_id,
            status=TryOnStatus.CANCELLED,
            progress=0,
            stage_message="Job cancelled.",
            completed_at=time.time(),
        )

    except Exception as e:
        _update(
            job_id,
            status=TryOnStatus.FAILED,
            progress=0,
            stage_message="Try-on failed.",
            error_message=str(e),
            completed_at=time.time(),
        )
        logger.error("tryon_job_failed", job_id=job_id, error=str(e))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=TryOnJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_tryon_job(
    request: TryOnJobCreateRequest,
    background_tasks: BackgroundTasks,
) -> TryOnJobResponse:
    """Create virtual try-on job: video + clothing photo."""
    video_path = Path(request.video_upload_id).resolve()
    clothing_path = Path(request.clothing_upload_id).resolve()

    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video not found: {video_path}")
    if not clothing_path.exists():
        raise HTTPException(status_code=404, detail=f"Clothing image not found: {clothing_path}")

    job_id = uuid.uuid4().hex
    job = TryOnJob(
        job_id=job_id,
        video_path=str(video_path),
        clothing_path=str(clothing_path),
        status=TryOnStatus.QUEUED,
        created_at=time.time(),
        stage_message="Job queued...",
    )
    _tryon_jobs[job_id] = job
    background_tasks.add_task(_run_tryon_job, job)
    logger.info("tryon_job_created", job_id=job_id)
    return _to_response(job)


@router.get("/{job_id}", response_model=TryOnJobResponse)
async def get_tryon_job(job_id: str) -> TryOnJobResponse:
    job = _tryon_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return _to_response(job)


@router.get("/{job_id}/stream")
async def stream_tryon_progress(job_id: str):
    """SSE stream for real-time try-on progress."""
    if job_id not in _tryon_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    async def event_generator() -> AsyncGenerator[str, None]:
        last_pct = -1
        while True:
            job = _tryon_jobs.get(job_id)
            if not job:
                break
            if job.progress != last_pct or job.status in (
                TryOnStatus.COMPLETED, TryOnStatus.FAILED, TryOnStatus.CANCELLED
            ):
                data = {
                    "job_id": job.job_id,
                    "status": job.status.value,
                    "progress": job.progress,
                    "stage_message": job.stage_message,
                    "error_message": job.error_message,
                    "output_ready": job.status == TryOnStatus.COMPLETED,
                    "total_frames": job.total_frames,
                    "processed_frames": job.processed_frames,
                }
                yield f"data: {json.dumps(data)}\n\n"
                last_pct = job.progress

            if job.status in (TryOnStatus.COMPLETED, TryOnStatus.FAILED, TryOnStatus.CANCELLED):
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{job_id}/output")
async def get_tryon_output(job_id: str):
    job = _tryon_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.status != TryOnStatus.COMPLETED or not job.output_path:
        raise HTTPException(status_code=404, detail="Output not ready yet.")
    output = Path(job.output_path)
    if not output.exists():
        raise HTTPException(status_code=404, detail="Output file missing on disk.")
    return FileResponse(
        str(output),
        media_type="video/mp4",
        filename=f"faceflux_tryon_{job_id}.mp4",
    )


@router.post("/{job_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_tryon_job(job_id: str):
    job = _tryon_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.status in (TryOnStatus.COMPLETED, TryOnStatus.FAILED, TryOnStatus.CANCELLED):
        raise HTTPException(status_code=409, detail="Job already finished.")
    _cancelled_tryon_jobs.add(job_id)
    return {"message": "Cancellation requested.", "job_id": job_id}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tryon_job(job_id: str):
    job = _tryon_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.status in (TryOnStatus.QUEUED, TryOnStatus.EXTRACTING,
                      TryOnStatus.PROCESSING, TryOnStatus.ASSEMBLING):
        raise HTTPException(status_code=409, detail="Cannot delete running job. Cancel first.")
    _tryon_jobs.pop(job_id, None)
    _cancelled_tryon_jobs.discard(job_id)
