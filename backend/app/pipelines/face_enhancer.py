"""
Face enhancer using GFPGAN (optional).

License note:
  GFPGAN — Copyright (c) 2021 TencentARC
  License: Apache-2.0 (commercially usable with attribution)

NOTE: GFPGAN is optional. If it fails to install on Python 3.14,
face swap will still work — just without enhancement.
Enhancement can be disabled from the UI toggle.
"""

from pathlib import Path
import numpy as np

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

GFPGAN_MODEL_URL = (
    "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/"
    "GFPGANv1.4.pth"
)
GFPGAN_FILENAME = "GFPGANv1.4.pth"

# Check at import time if gfpgan is available
_GFPGAN_AVAILABLE = False
try:
    import gfpgan  # noqa: F401
    _GFPGAN_AVAILABLE = True
    logger.info("gfpgan_available")
except ImportError:
    logger.warning(
        "gfpgan_not_installed",
        message="GFPGAN not installed — face enhancement disabled. "
                "Install with: pip3 install --break-system-packages gfpgan",
    )


class FaceEnhancer:
    """
    Optional GFPGAN-based face restoration / enhancement.
    Gracefully disabled if gfpgan is not installed.
    """

    def __init__(self):
        self._enhancer = None
        self._available = _GFPGAN_AVAILABLE

    @property
    def is_available(self) -> bool:
        return self._available

    def _model_path(self) -> Path:
        return settings.model_dir / GFPGAN_FILENAME

    def _ensure_model(self) -> None:
        model_path = self._model_path()
        if not model_path.exists():
            logger.info("downloading_gfpgan_model", url=GFPGAN_MODEL_URL)
            import urllib.request
            settings.model_dir.mkdir(parents=True, exist_ok=True)
            try:
                urllib.request.urlretrieve(GFPGAN_MODEL_URL, str(model_path))
                logger.info("gfpgan_downloaded", path=str(model_path))
            except Exception as e:
                raise RuntimeError(
                    f"Failed to download GFPGAN from {GFPGAN_MODEL_URL}: {e}\n"
                    f"Please manually place GFPGANv1.4.pth in: {settings.model_dir}"
                ) from e

    def _load(self) -> None:
        if self._enhancer is not None:
            return
        if not self._available:
            raise RuntimeError(
                "GFPGAN not installed. "
                "Run: pip3 install --break-system-packages gfpgan\n"
                "Or disable enhancement from the UI toggle."
            )
        self._ensure_model()
        try:
            from gfpgan import GFPGANer
            self._enhancer = GFPGANer(
                model_path=str(self._model_path()),
                upscale=1,
                arch="clean",
                channel_multiplier=2,
                bg_upsampler=None,
            )
            logger.info("gfpgan_loaded")
        except Exception as e:
            self._available = False
            logger.error("gfpgan_load_failed", error=str(e))
            raise RuntimeError(f"Failed to load GFPGAN: {e}") from e

    def enhance(self, frame: np.ndarray) -> np.ndarray:
        """
        Enhance face in a BGR frame.
        Returns enhanced frame, or original frame if enhancement unavailable.
        """
        if not self._available:
            # Silently return original — enhancer not installed
            return frame
        try:
            self._load()
            _, _, enhanced = self._enhancer.enhance(
                frame,
                has_aligned=False,
                only_center_face=False,
                paste_back=True,
            )
            if enhanced is not None:
                return enhanced
        except Exception as e:
            logger.warning("gfpgan_enhance_failed", error=str(e))
        return frame


face_enhancer = FaceEnhancer()
