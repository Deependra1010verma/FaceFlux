"""Pydantic models for virtual try-on jobs."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class TryOnStatus(str, Enum):
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"     # Video se frames extract ho rahe hain
    PROCESSING = "PROCESSING"     # HF Space se try-on ho raha hai
    ASSEMBLING = "ASSEMBLING"     # Frames se video ban raha hai
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TryOnJob(BaseModel):
    job_id: str
    video_path: str
    clothing_path: str            # Photo jisme clothes hain
    status: TryOnStatus = TryOnStatus.QUEUED
    progress: int = 0
    stage_message: str = "Waiting..."
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    total_frames: int = 0
    processed_frames: int = 0
    created_at: float = 0.0
    completed_at: Optional[float] = None


class TryOnJobCreateRequest(BaseModel):
    video_upload_id: str
    clothing_upload_id: str       # Face upload endpoint reuse karenge


class TryOnJobResponse(BaseModel):
    job_id: str
    status: TryOnStatus
    progress: int
    stage_message: str
    error_message: Optional[str] = None
    output_ready: bool = False
    total_frames: int = 0
    processed_frames: int = 0
    created_at: float = 0.0
    completed_at: Optional[float] = None
