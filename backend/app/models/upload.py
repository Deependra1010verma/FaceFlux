"""Upload-related Pydantic models."""

from pydantic import BaseModel


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    path: str
