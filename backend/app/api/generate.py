"""
Video Generation API: create, stream progress, download output.

POST /generate          — Create generation job (image + prompt)
GET  /generate/{id}     — Job status
GET  /generate/{id}/stream — SSE real-time progress
GET  /generate/{id}/output — Download result mp4
DELETE /generate/{id}   — Cancel / delete job
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.models.gen_job import GenJob, GenJobCreateRequest, GenJobResponse, GenStatus
from app.pipelines.video_generator import generate_video

logger = get_logger(__name__)
router = APIRouter()

# In-memory store for generation jobs
_gen_jobs: Dict[str, GenJob] = {}
_cancelled_gen_jobs: set = set()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_response(job: GenJob) -> GenJobResponse:
    return GenJobResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        stage_message=job.stage_message,
        error_message=job.error_message,
        output_ready=job.status == GenStatus.COMPLETED and job.output_path is not None,
        provider=job.provider,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


def _update(job_id: str, **kwargs) -> None:
    job = _gen_jobs.get(job_id)
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)


# ── Background task ───────────────────────────────────────────────────────────

async def _run_gen_job(job: GenJob) -> None:
    job_id = job.job_id

    def progress(s: GenStatus, pct: int, msg: str) -> None:
        if job_id in _cancelled_gen_jobs:
            raise InterruptedError("Cancelled by user.")
        _update(job_id, status=s, progress=pct, stage_message=msg)
        logger.info("gen_progress", job_id=job_id, pct=pct, msg=msg)

    try:
        output_path = await generate_video(job, progress)

        # Extract provider from last log (stored in job via pipeline)
        _update(
            job_id,
            status=GenStatus.COMPLETED,
            progress=100,
            stage_message="Video ready! Download karo.",
            output_path=output_path,
            completed_at=time.time(),
        )
        logger.info("gen_job_completed", job_id=job_id, output=output_path)

    except InterruptedError:
        _update(
            job_id,
            status=GenStatus.CANCELLED,
            progress=0,
            stage_message="Generation cancelled.",
            completed_at=time.time(),
        )
        logger.info("gen_job_cancelled", job_id=job_id)

    except Exception as e:
        _update(
            job_id,
            status=GenStatus.FAILED,
            progress=0,
            stage_message="Generation failed.",
            error_message=str(e),
            completed_at=time.time(),
        )
        logger.error("gen_job_failed", job_id=job_id, error=str(e))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=GenJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_gen_job(
    request: GenJobCreateRequest,
    background_tasks: BackgroundTasks,
) -> GenJobResponse:
    """Create a new video generation job from image + prompt."""
    image_path = Path(request.image_upload_id).resolve()
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {image_path}")

    if not request.prompt.strip():
        raise HTTPException(status_code=422, detail="Prompt cannot be empty.")

    duration = max(1, min(request.duration, 10))  # clamp 1–10 seconds

    token = request.hf_token or settings.hf_token or None
    colab = request.colab_url or settings.colab_gpu_url or None

    job_id = uuid.uuid4().hex
    job = GenJob(
        job_id=job_id,
        prompt=request.prompt.strip(),
        image_path=str(image_path),
        duration=duration,
        status=GenStatus.QUEUED,
        created_at=time.time(),
        stage_message="Job queued — waiting to start...",
        provider_mode=request.provider_mode or "hf",
        hf_token=token,
        colab_url=colab,
    )
    _gen_jobs[job_id] = job

    background_tasks.add_task(_run_gen_job, job)
    logger.info("gen_job_created", job_id=job_id, prompt=request.prompt[:60])
    return _to_response(job)


@router.get("/{job_id}", response_model=GenJobResponse)
async def get_gen_job(job_id: str) -> GenJobResponse:
    job = _gen_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return _to_response(job)


@router.get("/{job_id}/stream")
async def stream_gen_progress(job_id: str):
    """SSE real-time progress for generation job."""
    if job_id not in _gen_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    async def event_generator() -> AsyncGenerator[str, None]:
        last_pct = -1
        while True:
            job = _gen_jobs.get(job_id)
            if not job:
                break

            if job.progress != last_pct or job.status in (
                GenStatus.COMPLETED, GenStatus.FAILED, GenStatus.CANCELLED
            ):
                data = {
                    "job_id": job.job_id,
                    "status": job.status.value,
                    "progress": job.progress,
                    "stage_message": job.stage_message,
                    "error_message": job.error_message,
                    "output_ready": job.status == GenStatus.COMPLETED,
                    "provider": job.provider,
                }
                yield f"data: {json.dumps(data)}\n\n"
                last_pct = job.progress

            if job.status in (GenStatus.COMPLETED, GenStatus.FAILED, GenStatus.CANCELLED):
                break

            await asyncio.sleep(0.8)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{job_id}/output")
async def get_gen_output(job_id: str):
    job = _gen_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.status != GenStatus.COMPLETED or not job.output_path:
        raise HTTPException(status_code=404, detail="Output not ready yet.")
    output = Path(job.output_path)
    if not output.exists():
        raise HTTPException(status_code=404, detail="Output file missing on disk.")
    return FileResponse(
        str(output),
        media_type="video/mp4",
        filename=f"faceflux_gen_{job_id}.mp4",
    )


@router.post("/{job_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_gen_job(job_id: str):
    job = _gen_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.status in (GenStatus.COMPLETED, GenStatus.FAILED, GenStatus.CANCELLED):
        raise HTTPException(status_code=409, detail="Job already finished.")
    _cancelled_gen_jobs.add(job_id)
    return {"message": "Cancellation requested.", "job_id": job_id}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gen_job(job_id: str):
    job = _gen_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job.status in (GenStatus.QUEUED, GenStatus.UPLOADING, GenStatus.GENERATING):
        raise HTTPException(status_code=409, detail="Cannot delete a running job. Cancel it first.")
    _gen_jobs.pop(job_id, None)
    _cancelled_gen_jobs.discard(job_id)
