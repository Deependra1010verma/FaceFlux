"""Health check endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    local: bool
    message: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        local=True,
        message="FaceFlux is running locally. Your files stay on this device.",
    )
