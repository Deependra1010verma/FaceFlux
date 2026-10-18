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
import platform
import urllib.request
import numpy as np
import cv2

from app.core.config import settings
from app.core.logger import get_logger
from app.services.hardware import hardware_service

logger = get_logger(__name__)

# CoreML compiled model cache for inswapper_128.
# On first Mac run, CoreML compiles the 529MB model (~3-4 min).
# Cached blob reused on all subsequent runs — instant load.
_COREML_CACHE_DIR = str(Path(".coreml_cache") / "swapper")


def _is_apple_silicon() -> bool:
    """True when running natively on Apple Silicon (arm64 macOS)."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"

INSWAPPER_URL = (
    "https://github.com/deepinsight/insightface/releases/download/model-zoo/inswapper_128.onnx"
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
        # Check both existence and valid file size (> 1MB)
        if not model_path.exists() or model_path.stat().st_size < 1_000_000:
            logger.info("downloading_inswapper_model", url=INSWAPPER_URL)
            settings.model_dir.mkdir(parents=True, exist_ok=True)
            if model_path.exists():
                model_path.unlink(missing_ok=True)
            try:
                urllib.request.urlretrieve(INSWAPPER_URL, str(model_path))
                logger.info("model_downloaded", path=str(model_path))
            except Exception as e:
                raise RuntimeError(
                    f"Failed to download inswapper model from {INSWAPPER_URL}: {e}\n"
                    f"Please run 'bash scripts/download-models.sh' to download it."
                ) from e

    def _load(self) -> None:
        if self._swapper is not None:
            return
        self._ensure_model()
        try:
            import insightface
            model_path = self._model_path()

            if _is_apple_silicon():
                # ── Apple Silicon: CoreML with compiled model cache ─────────────
                # InsightFace's get_model() accepts provider_options as a list
                # parallel to providers — index 0 options → index 0 provider.
                # CoreML compiles inswapper_128 to Metal on first run (~3-4 min)
                # then caches the blob so subsequent restarts are instant.
                Path(_COREML_CACHE_DIR).mkdir(parents=True, exist_ok=True)
                providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
                provider_options = [
                    {
                        "ModelCacheDirectory": _COREML_CACHE_DIR,
                        "MLComputeUnits": "0",  # 0 = ALL (ANE + GPU + CPU)
                    },
                    {},  # no options for CPU fallback
                ]
                self._swapper = insightface.model_zoo.get_model(
                    str(model_path),
                    providers=providers,
                    provider_options=provider_options,
                )
                logger.info(
                    "face_swapper_loaded",
                    provider="CoreMLExecutionProvider",
                    cache_dir=_COREML_CACHE_DIR,
                )
            else:
                # ── Linux / Windows: hardware_service auto-selects CUDA / CPU ──
                providers = hardware_service.get_onnx_providers()
                self._swapper = insightface.model_zoo.get_model(
                    str(model_path),
                    providers=providers,
                )
                logger.info("face_swapper_loaded", provider=providers[0])

        except Exception as e:
            raise RuntimeError(f"Failed to load FaceSwapper: {e}") from e

    def fuse_source_faces(self, source_faces: list):
        """
        Takes a list of detected Face objects from multiple reference photos
        (e.g. front, left, right, angled) and computes a normalized average embedding vector.
        This provides high-fidelity 3D facial structure coverage across any video angle.
        """
        if not source_faces:
            return None
        if len(source_faces) == 1:
            return source_faces[0]

        embeddings = []
        weights = []
        for f in source_faces:
            if hasattr(f, "embedding") and f.embedding is not None:
                embeddings.append(f.embedding)
                # Use detection confidence score as weight — higher score = sharper, frontal photo
                weights.append(float(getattr(f, "det_score", 1.0)))

        if not embeddings:
            return source_faces[0]

        import copy
        # Score-weighted average: low-confidence photos (blurry/angled) get less weight
        weights_arr = np.array(weights, dtype=np.float32)
        weight_sum = float(weights_arr.sum())
        if weight_sum <= 0:
            weights_arr = np.ones(len(embeddings), dtype=np.float32) / len(embeddings)
        else:
            weights_arr = weights_arr / weight_sum

        mean_emb = np.average(np.stack(embeddings), axis=0, weights=weights_arr)
        norm = np.linalg.norm(mean_emb)
        fused_emb = mean_emb / norm if norm > 0 else mean_emb

        fused_face = copy.copy(source_faces[0])
        fused_face.embedding = fused_emb

        logger.info("source_faces_fused", count=len(embeddings),
                    weights=[round(w, 3) for w in weights_arr.tolist()])
        return fused_face

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
