"""System information endpoint — hardware, acceleration, directories."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.hardware import hardware_service
from app.core.config import settings

router = APIRouter()


class SystemInfoResponse(BaseModel):
    cpu: str
    cpu_cores: int
    ram_gb: float
    gpu: str
    vram_gb: float
    acceleration: str
    model_dir: str
    output_dir: str
    max_video_size_mb: int
    default_quality: str
    gfpgan_available: bool


@router.get("", response_model=SystemInfoResponse)
async def system_info() -> SystemInfoResponse:
    hw = hardware_service.summary()

    # Check if gfpgan is importable
    try:
        import gfpgan  # noqa: F401
        gfpgan_ok = True
    except ImportError:
        gfpgan_ok = False

    return SystemInfoResponse(
        cpu=hw["cpu"],
        cpu_cores=hw["cpu_cores"],
        ram_gb=hw["ram_gb"],
        gpu=hw["gpu"],
        vram_gb=hw["vram_gb"],
        acceleration=hw["acceleration"],
        model_dir=str(settings.model_dir),
        output_dir=str(settings.output_dir),
        max_video_size_mb=settings.max_video_size_mb,
        default_quality=settings.default_quality,
        gfpgan_available=gfpgan_ok,
    )
