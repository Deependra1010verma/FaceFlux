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

    # Check if GPEN face enhancer model is available
    try:
        from app.pipelines.face_enhancer import face_enhancer
        enhancer_ok = face_enhancer.is_available
    except Exception:
        # Direct file check fallback
        enhancer_ok = (
            (settings.model_dir / "GPEN-BFR-512.onnx").exists()
            or (settings.model_dir / "GPEN-BFR-256.onnx").exists()
        )

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
        gfpgan_available=enhancer_ok,
    )
