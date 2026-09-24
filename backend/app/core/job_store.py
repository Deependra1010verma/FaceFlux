from app.core.config import settings
from app.core.logger import get_logger
from app.core.security import generate_job_id
from app.models.job import Job, JobStatus
from typing import Dict, Optional
import asyncio
import time

logger = get_logger(__name__)

_jobs: Dict[str, Job] = {}
_semaphore: Optional[asyncio.Semaphore] = None


def get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
    return _semaphore


def create_job(video_path: str, face_path: str, quality: str, enhance: bool, target_face_index: int = 0) -> Job:
    job_id = generate_job_id()
    job = Job(
        job_id=job_id,
        video_path=video_path,
        face_path=face_path,
        quality=quality,
        enhance=enhance,
        target_face_index=target_face_index,
        status=JobStatus.QUEUED,
        created_at=time.time(),
    )
    _jobs[job_id] = job
    logger.info("job_created", job_id=job_id, quality=quality)
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


def update_job(job_id: str, **kwargs) -> Optional[Job]:
    job = _jobs.get(job_id)
    if job is None:
        return None
    for key, value in kwargs.items():
        setattr(job, key, value)
    return job


def delete_job(job_id: str) -> bool:
    return _jobs.pop(job_id, None) is not None


def list_jobs() -> list[Job]:
    return list(_jobs.values())
