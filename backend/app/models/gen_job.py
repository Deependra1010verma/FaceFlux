"""Pydantic models for video generation jobs."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class GenStatus(str, Enum):
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class GenJob(BaseModel):
    job_id: str
    prompt: str
    image_path: str
    duration: int = 5           # seconds
    status: GenStatus = GenStatus.QUEUED
    progress: int = 0
    stage_message: str = "Waiting..."
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    created_at: float = 0.0
    completed_at: Optional[float] = None
    provider: Optional[str] = None  # which HF Space or Colab was used
    provider_mode: Optional[str] = "hf"  # "hf" or "colab"
    hf_token: Optional[str] = None
    colab_url: Optional[str] = None


class GenJobCreateRequest(BaseModel):
    prompt: str
    image_upload_id: str
    duration: int = 5
    provider_mode: Optional[str] = "hf"
    hf_token: Optional[str] = None
    colab_url: Optional[str] = None


class GenJobResponse(BaseModel):
    job_id: str
    status: GenStatus
    progress: int
    stage_message: str
    error_message: Optional[str] = None
    output_ready: bool = False
    provider: Optional[str] = None
    created_at: float = 0.0
    completed_at: Optional[float] = None
