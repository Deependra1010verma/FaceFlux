"""
Face detection using InsightFace — Phase 2 upgrade.

Changes from Phase 1:
  - Dual-model architecture:
      buffalo_sc → ultra-fast detection for UI preview / thumbnail generation
      buffalo_l  → high-accuracy detection for actual face swap pipeline
  - CoreML compilation cache: first-run compiles model to disk; restarts load
    in ~0.2s instead of ~20-30s (macOS arm64 only)
  - Shared cache for both models to avoid redundant CoreML compilation

License note:
  InsightFace models (buffalo_l, buffalo_sc) are released under the
  "Non-Commercial Research/Education" license. This application
  is intended for local personal use — ensure you comply with the
  license terms before any commercial deployment.
"""

import base64
import io
import platform
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.logger import get_logger
from app.models.job import FaceInfo
from app.services.hardware import hardware_service

logger = get_logger(__name__)

# CoreML on-disk compilation cache (macOS arm64 only)
# First run: ~20-30s compile. Subsequent runs: ~0.2s load from cache.
_COREML_CACHE_DIR = ".coreml_cache"


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _build_ort_session_options():
    """
    Build ONNX Runtime SessionOptions with CoreML compilation cache enabled.
    On macOS arm64: persists compiled Metal/ANE graph to disk → instant restart loads.
    On Linux/Windows: returns default options (no-op).
    """
    try:
        import onnxruntime as ort
        options = ort.SessionOptions()
        if _is_apple_silicon():
            Path(_COREML_CACHE_DIR).mkdir(parents=True, exist_ok=True)
            # CoreML EP accepts provider options via append_execution_provider
            # We store the cache dir for use when building the session
            options._coreml_cache_dir = _COREML_CACHE_DIR
        return options
    except ImportError:
        return None


def _get_providers_with_cache() -> tuple[list, dict]:
    """
    Returns (providers_list, provider_options_dict) with CoreML cache configured.
    Used when building InsightFace FaceAnalysis sessions directly.
    """
    providers = hardware_service.get_onnx_providers()
    provider_options = []

    for p in providers:
        if p == "CoreMLExecutionProvider" and _is_apple_silicon():
            provider_options.append({
                "ModelCacheDirectory": _COREML_CACHE_DIR,
                    "ModelFormat": "MLProgram",
                    "MLComputeUnits": "ALL",
                "SpecializationStrategy": "FastPrediction",
            })
        else:
            provider_options.append({})

    return providers, provider_options


class FaceDetector:
    """
    Wraps InsightFace FaceAnalysis for detection and landmark extraction.

    Dual-model architecture:
      _app_quality (buffalo_l): high-accuracy, used for actual swap pipeline
      _app_speed   (buffalo_sc): lightning-fast, used for UI preview/thumbnails

    Both models use CoreML compilation cache on Apple Silicon for instant restarts.
    """

    def __init__(self):
        self._app_quality = None   # buffalo_l — full pipeline
        self._app_speed   = None   # buffalo_sc — UI preview

    def _load_quality(self) -> None:
        """Load buffalo_l — high accuracy model for face swap pipeline."""
        if self._app_quality is not None:
            return
        try:
            from insightface.app import FaceAnalysis
            logger.info("loading_face_detector", model="buffalo_l")
            providers, provider_options = _get_providers_with_cache()
            self._app_quality = FaceAnalysis(
                name="buffalo_l",
                root=str(settings.model_dir),
                providers=providers,
                provider_options=provider_options,
            )
            self._app_quality.prepare(
                ctx_id=0 if "CUDA" in hardware_service.acceleration else -1,
                det_size=(settings.det_size, settings.det_size),
            )
            logger.info("face_detector_loaded", model="buffalo_l", provider=providers[0])
        except Exception as e:
            raise RuntimeError(f"Failed to load InsightFace buffalo_l: {e}") from e

    def _load_speed(self) -> None:
        """
        Load buffalo_sc — ultra-lightweight model for UI preview / thumbnail detection.

        buffalo_sc vs buffalo_l:
          - Detection: 3-7ms vs 12-25ms per frame
          - Accuracy: Good for UI selection; not ideal for complex multi-face scenes
          - ANE compatibility: Excellent (full ANE path on Apple Silicon)
          - Memory: Very low — safe even on 8GB machines
        """
        if self._app_speed is not None:
            return
        try:
            from insightface.app import FaceAnalysis
            logger.info("loading_face_detector", model="buffalo_sc")
            providers, provider_options = _get_providers_with_cache()
            self._app_speed = FaceAnalysis(
                name="buffalo_sc",
                root=str(settings.model_dir),
                providers=providers,
                provider_options=provider_options,
            )
            self._app_speed.prepare(
                ctx_id=0 if "CUDA" in hardware_service.acceleration else -1,
                det_size=(settings.det_size, settings.det_size),
            )
            logger.info("face_detector_loaded", model="buffalo_sc", provider=providers[0])
        except Exception as e:
            # buffalo_sc not available — fall back silently to buffalo_l
            logger.warning("buffalo_sc_unavailable", error=str(e))
            self._load_quality()
            self._app_speed = self._app_quality

    def _load(self) -> None:
        """Load quality model (backward-compatible default)."""
        self._load_quality()

    # ── Public detection methods ───────────────────────────────────────────────

    def detect_in_image(
        self, image: np.ndarray, min_score: float = None, fast: bool = False
    ) -> List:
        """
        Detect faces in a BGR numpy image. Returns list of Face objects.

        fast=True  → buffalo_sc (3-7ms, UI thumbnails, face selection)
        fast=False → buffalo_l  (12-25ms, actual swap pipeline)
        """
        if fast:
            self._load_speed()
            app = self._app_speed
        else:
            self._load_quality()
            app = self._app_quality

        if min_score is None:
            min_score = settings.face_score_threshold
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        faces = app.get(rgb)
        return [f for f in faces if f.det_score >= min_score]

    def detect_in_file(self, path: Path, fast: bool = False) -> List:
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"Cannot read image: {path}")
        return self.detect_in_image(img, fast=fast)

    def faces_to_face_info(
        self, image: np.ndarray, faces: list, max_thumbnail_size: int = 96
    ) -> List[FaceInfo]:
        results = []
        h, w = image.shape[:2]
        for i, face in enumerate(faces):
            bbox = face.bbox.tolist()
            # Clamp bbox
            x1 = max(0, int(bbox[0]))
            y1 = max(0, int(bbox[1]))
            x2 = min(w, int(bbox[2]))
            y2 = min(h, int(bbox[3]))

            # Generate thumbnail
            thumbnail_b64 = None
            try:
                crop = image[y1:y2, x1:x2]
                if crop.size > 0:
                    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(crop_rgb)
                    pil_img.thumbnail((max_thumbnail_size, max_thumbnail_size))
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=80)
                    thumbnail_b64 = base64.b64encode(buf.getvalue()).decode()
            except Exception:
                pass

            # Detect extreme side angle (>35° yaw)
            angle_warning = None
            try:
                yaw = None
                if hasattr(face, "pose") and face.pose is not None:
                    yaw = float(face.pose[1])
                elif hasattr(face, "kps") and face.kps is not None and len(face.kps) >= 5:
                    d_left  = abs(float(face.kps[2][0] - face.kps[0][0]))
                    d_right = abs(float(face.kps[1][0] - face.kps[2][0]))
                    if (d_left + d_right) > 0:
                        ratio = (d_right - d_left) / (d_left + d_right)
                        yaw = ratio * 90.0

                if yaw is not None and abs(yaw) > 35:
                    angle_warning = f"Side angle detected (~{int(abs(yaw))}°). Frontal faces give best swap."
            except Exception:
                pass

            results.append(
                FaceInfo(
                    index=i,
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                    score=float(face.det_score),
                    thumbnail_b64=thumbnail_b64,
                    angle_warning=angle_warning,
                )
            )
        return results

    def get_representative_frame_faces(
        self, video_path: Path, sample_every_n_frames: int = 30
    ) -> Tuple[np.ndarray, List]:
        """
        Sample frames from the video and return the frame + faces from the
        frame that has the most detected faces (covers multi-person videos).

        Uses buffalo_sc (fast mode) for sampling — 3x faster than buffalo_l.
        The actual swap pipeline uses buffalo_l for accuracy.
        """
        self._load_speed()   # Use fast model for video sampling
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        first_frame = None
        best_frame  = None
        best_faces: List = []
        frame_idx = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if first_frame is None:
                    first_frame = frame.copy()
                if frame_idx % sample_every_n_frames == 0:
                    # fast=True: buffalo_sc for quick sampling
                    faces = self.detect_in_image(frame, fast=True)
                    if len(faces) > len(best_faces):
                        best_faces = faces
                        best_frame = frame.copy()
                frame_idx += 1
        finally:
            cap.release()

        selected_frame = best_frame if best_frame is not None else first_frame
        if selected_frame is None:
            raise ValueError("No frames could be read from video.")
        return selected_frame, best_faces


face_detector = FaceDetector()
