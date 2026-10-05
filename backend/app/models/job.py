"""Pydantic models for job lifecycle."""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    ANALYZING = "ANALYZING"
    DETECTING = "DETECTING"
    TRACKING = "TRACKING"
    SWAPPING = "SWAPPING"
    ENHANCING = "ENHANCING"
    ENCODING = "ENCODING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FaceInfo(BaseModel):
    index: int
    bbox: List[float]           # [x1, y1, x2, y2]
    score: float
    thumbnail_b64: Optional[str] = None   # base64 JPEG thumbnail
    angle_warning: Optional[str] = None   # Warning if side-profile (>35° yaw)


class VideoMeta(BaseModel):
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool
    codec: str
    frame_count: Optional[int] = None


class Job(BaseModel):
    job_id: str
    video_path: str
    face_path: str
    face_paths: List[str] = []
    quality: str
    enhance: bool
    target_face_index: int = 0
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    stage_message: str = "Waiting in queue..."
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    video_meta: Optional[VideoMeta] = None
    detected_faces: List[FaceInfo] = []


class JobCreateRequest(BaseModel):
    video_upload_id: str
    face_upload_id: Optional[str] = None
    face_upload_ids: Optional[List[str]] = None
    target_face_index: int = 0
    quality: str = "balanced"
    enhance: bool = True


class JobProgressResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int
    stage_message: str
    error_message: Optional[str] = None
    output_ready: bool = False
