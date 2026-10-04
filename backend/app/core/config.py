"""
Application configuration loaded from environment / .env file.

pydantic-settings available ho toh use karta hai,
warna os.environ + .env file manually parse karta hai.
"""

import os
from pathlib import Path

BASE_DIR = Path(os.environ.get("BASE_DIR", str(Path(__file__).resolve().parents[3])))


def _load_env_file() -> None:
    """Manually parse .env file into os.environ (only if not already set)."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                # Strip inline comments (anything after '  #')
                if "  #" in val:
                    val = val.split("  #")[0].strip()
                # Only set if not already in environment
                if key and key not in os.environ:
                    os.environ[key] = val


# Load .env before anything else
_load_env_file()


def _path(key: str, default: str) -> Path:
    raw = os.environ.get(key, default)
    p = Path(raw)
    if not p.is_absolute():
        p = BASE_DIR / p
    return p


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _str(key: str, default: str) -> str:
    return os.environ.get(key, default)


class Settings:
    """
    Application settings. Reads from os.environ (populated from .env above).
    Works with OR without pydantic-settings installed.
    """

    # Directories
    model_dir:   Path = _path("MODEL_DIR",  "data/models")
    upload_dir:  Path = _path("UPLOAD_DIR", "data/uploads")
    output_dir:  Path = _path("OUTPUT_DIR", "data/outputs")
    temp_dir:    Path = _path("TEMP_DIR",   "data/temp")
    frames_dir:  Path = _path("FRAMES_DIR", "data/frames")
    log_dir:     Path = _path("LOG_DIR",    "data/logs")

    # Upload constraints
    max_video_size_mb: int = _int("MAX_VIDEO_SIZE_MB", 2048)
    max_image_size_mb: int = _int("MAX_IMAGE_SIZE_MB", 50)

    # Processing
    gpu_provider:        str = _str("GPU_PROVIDER",        "auto")
    default_quality:     str = _str("DEFAULT_QUALITY",     "balanced")
    max_concurrent_jobs: int = _int("MAX_CONCURRENT_JOBS", 1)
    frame_batch_size:    int = _int("FRAME_BATCH_SIZE",    32)

    # Output video
    output_codec:  str = _str("OUTPUT_CODEC",  "libx264")
    output_crf:    int = _int("OUTPUT_CRF",    18)
    output_preset: str = _str("OUTPUT_PRESET", "medium")

    # InsightFace
    det_size:             int   = _int("DET_SIZE",              640)
    face_score_threshold: float = _float("FACE_SCORE_THRESHOLD", 0.5)

    # ─── Face Enhancer (GPEN ONNX) ───────────────────────────────────────────
    # Preferred model: "gpen_512" (best quality) | "gpen_256" (faster) | "gfpgan"
    enhancer_model:    str   = _str(  "ENHANCER_MODEL",    "gpen_512")
    # Fidelity: 0.0 = max enhancement, 1.0 = max fidelity to original
    # 0.8 is a good balance — strong sharpening, still looks natural
    enhancer_fidelity: float = _float("ENHANCER_FIDELITY", 0.8)
    # Color correction: match skin tone of swapped face to target
    color_correction:  bool  = os.environ.get("COLOR_CORRECTION", "true").lower() != "false"

    # Cloud & Remote GPU Settings
    hf_token:             str = _str("HF_TOKEN", "")
    colab_gpu_url:        str = _str("COLAB_GPU_URL", "")

    @property
    def max_video_size_bytes(self) -> int:
        return self.max_video_size_mb * 1024 * 1024

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024


settings = Settings()
