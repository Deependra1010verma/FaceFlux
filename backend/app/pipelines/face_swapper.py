"""
Face swapper using InsightFace's inswapper_128 model.

License note:
  inswapper_128.onnx is distributed via InsightFace/ONNX model zoo.
  It is licensed for NON-COMMERCIAL use only.
  Do not use this in a commercial product without verifying
  the current InsightFace model license.
  Model download URL: https://huggingface.co/deepinsight/inswapper/
"""

from pathlib import Path
from typing import Optional
import urllib.request
import numpy as np
import cv2

from app.core.config import settings
from app.core.logger import get_logger
from app.services.hardware import hardware_service

logger = get_logger(__name__)

INSWAPPER_URL = (
    "https://huggingface.co/deepinsight/inswapper/resolve/main/inswapper_128.onnx"
)
INSWAPPER_FILENAME = "inswapper_128.onnx"


class FaceSwapper:
    """
    Wraps InsightFace's INSwapper model.
    Lazy-loads the ONNX model on first call.
    """

    def __init__(self):
        self._swapper = None

    def _model_path(self) -> Path:
        return settings.model_dir / INSWAPPER_FILENAME

    def _ensure_model(self) -> None:
        model_path = self._model_path()
        if not model_path.exists():
            logger.info("downloading_inswapper_model", url=INSWAPPER_URL)
            settings.model_dir.mkdir(parents=True, exist_ok=True)
            try:
                urllib.request.urlretrieve(INSWAPPER_URL, str(model_path))
                logger.info("model_downloaded", path=str(model_path))
            except Exception as e:
                raise RuntimeError(
                    f"Failed to download inswapper model from {INSWAPPER_URL}: {e}\n"
                    f"Please manually download inswapper_128.onnx to: {model_path}"
                ) from e

    def _load(self) -> None:
        if self._swapper is not None:
            return
        self._ensure_model()
        try:
            import insightface
            providers = hardware_service.get_onnx_providers()
            self._swapper = insightface.model_zoo.get_model(
                str(self._model_path()),
                providers=providers,
            )
            self._swapper.prepare(ctx_id=0 if "CUDA" in hardware_service.acceleration else -1)
            logger.info("face_swapper_loaded", provider=providers[0])
        except Exception as e:
            raise RuntimeError(f"Failed to load FaceSwapper: {e}") from e

    def swap(
        self,
        frame: np.ndarray,
        target_face,
        source_face,
    ) -> np.ndarray:
        """Apply face swap to a single frame. Returns modified frame (BGR)."""
        self._load()
        result = self._swapper.get(frame, target_face, source_face, paste_back=True)
        return result


face_swapper = FaceSwapper()
