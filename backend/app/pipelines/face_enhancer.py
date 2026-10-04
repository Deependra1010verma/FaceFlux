"""
Face enhancer using GPEN ONNX models.

Why GPEN ONNX (instead of CodeFormer/GFPGAN via basicsr):
  - Pure ONNX — NO PyTorch, NO basicsr, NO torch needed
  - Works on Python 3.14+ (zero legacy dependency issues)
  - Better sharpness: inswapper_128 gives ~128px face → GPEN-512 restores to 512px quality
  - GPEN-BFR-512 is the gold standard for post-swap face restoration
  - Apache-2.0 / MIT compatible

Pipeline:
  inswapper_128 swap → GPEN-BFR-512 enhance → output

Model source (free):
  github.com/harisreedhar/Face-Upscalers-ONNX
  HuggingFace: facefusion/models

License:
  GPEN: MIT (yangxy/GPEN)
  GFPGAN: Apache-2.0
"""

import urllib.request
import numpy as np
import cv2
from pathlib import Path
from typing import Optional, Tuple

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# ── Model registry ─────────────────────────────────────────────────────────────
# Priority order: try GPEN-512 first, then GPEN-256, then GFPGAN
ENHANCER_MODELS = {
    "gpen_512": {
        "filename": "GPEN-BFR-512.onnx",
        "url": "https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/gpen_bfr_512.onnx",
        "input_size": 512,
        "min_size_bytes": 50_000_000,   # ~50 MB
    },
    "gpen_256": {
        "filename": "GPEN-BFR-256.onnx",
        "url": "https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/gpen_bfr_256.onnx",
        "input_size": 256,
        "min_size_bytes": 15_000_000,   # ~15 MB
    },
    "gfpgan": {
        "filename": "GFPGANv1.4.onnx",
        "url": "https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/gfpgan_1.4.onnx",
        "input_size": 512,
        "min_size_bytes": 50_000_000,   # ~50 MB
    },
}

# Face alignment landmarks (InsightFace standard 5-point)
FACE_LANDMARK_5 = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


class FaceEnhancer:
    """
    GPEN/GFPGAN ONNX-based face restoration — completely dependency-free.
    Uses only onnxruntime + OpenCV (already installed).

    Gracefully falls back to no-enhancement if models unavailable.
    """

    def __init__(self):
        self._session = None
        self._model_name: Optional[str] = None
        self._input_size: int = 512
        self._available: Optional[bool] = None  # None = not yet checked

    @property
    def is_available(self) -> bool:
        if self._available is None:
            self._available = self._find_available_model() is not None
        return self._available

    def _model_path(self, model_key: str) -> Path:
        return settings.model_dir / ENHANCER_MODELS[model_key]["filename"]

    def _find_available_model(self) -> Optional[str]:
        """Return the best available model key, or None if none found."""
        for key in ENHANCER_MODELS:
            path = self._model_path(key)
            info = ENHANCER_MODELS[key]
            if path.exists() and path.stat().st_size >= info["min_size_bytes"]:
                logger.info("enhancer_model_found", model=key, path=str(path))
                return key
        return None

    def _ensure_model(self, preferred: str = "gpen_512") -> Optional[str]:
        """
        Try to download the preferred model. Returns model key if successful.
        Tries models in priority order if preferred fails.
        """
        order = [preferred] + [k for k in ENHANCER_MODELS if k != preferred]
        for key in order:
            info = ENHANCER_MODELS[key]
            path = self._model_path(key)

            if path.exists() and path.stat().st_size >= info["min_size_bytes"]:
                return key

            # Try to download
            logger.info("downloading_enhancer_model", model=key, url=info["url"])
            settings.model_dir.mkdir(parents=True, exist_ok=True)
            try:
                urllib.request.urlretrieve(info["url"], str(path))
                if path.exists() and path.stat().st_size >= info["min_size_bytes"]:
                    logger.info("enhancer_model_downloaded", model=key, size_mb=path.stat().st_size // 1_000_000)
                    return key
                else:
                    logger.warning("enhancer_download_incomplete", model=key)
                    path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("enhancer_download_failed", model=key, error=str(e))
                path.unlink(missing_ok=True)

        return None

    def _load(self, preferred: str = "gpen_512") -> bool:
        """Load ONNX session. Returns True if loaded successfully."""
        if self._session is not None:
            return True

        model_key = self._find_available_model()
        if model_key is None:
            model_key = self._ensure_model(preferred)

        if model_key is None:
            logger.warning(
                "enhancer_no_model_available",
                message="Run 'bash scripts/download-models.sh' to download GPEN model.",
            )
            self._available = False
            return False

        try:
            import onnxruntime as ort

            path = self._model_path(model_key)
            info = ENHANCER_MODELS[model_key]

            # Use GPU if available, else CPU
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            try:
                sess = ort.InferenceSession(str(path), providers=providers)
            except Exception:
                sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])

            self._session = sess
            self._model_name = model_key
            self._input_size = info["input_size"]
            self._available = True

            used_provider = sess.get_providers()[0]
            logger.info(
                "face_enhancer_loaded",
                model=model_key,
                input_size=self._input_size,
                provider=used_provider,
            )
            return True

        except Exception as e:
            self._available = False
            logger.error("face_enhancer_load_failed", model=model_key, error=str(e))
            return False

    # ── Face warping helpers ───────────────────────────────────────────────────

    def _get_affine_matrix(
        self, landmarks_5pt: np.ndarray, output_size: int
    ) -> np.ndarray:
        """Compute affine transform matrix to align face to GPEN template."""
        scale = output_size / 112.0
        dst = FACE_LANDMARK_5 * scale
        # estimateAffinePartial2D → rotation + scale + translation (4 DoF)
        matrix, _ = cv2.estimateAffinePartial2D(
            landmarks_5pt, dst, method=cv2.RANSAC
        )
        if matrix is None:
            # Fallback: just scale-center
            matrix = np.eye(2, 3, dtype=np.float32)
            matrix[0, 2] = (output_size - landmarks_5pt[:, 0].mean()) * 0.5
            matrix[1, 2] = (output_size - landmarks_5pt[:, 1].mean()) * 0.5
        return matrix

    def _warp_face(
        self,
        frame: np.ndarray,
        landmarks_5pt: np.ndarray,
        output_size: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Warp & crop face region using 5-point landmarks.
        Returns (cropped_face, affine_matrix).
        """
        matrix = self._get_affine_matrix(landmarks_5pt, output_size)
        cropped = cv2.warpAffine(frame, matrix, (output_size, output_size))
        return cropped, matrix

    def _paste_back(
        self,
        frame: np.ndarray,
        enhanced_face: np.ndarray,
        matrix: np.ndarray,
        mask_blur: int = 5,
    ) -> np.ndarray:
        """
        Paste the enhanced face back into the original frame using inverse warp.
        Uses feathered mask blending for smooth, natural edges.
        """
        size = enhanced_face.shape[0]
        h, w = frame.shape[:2]

        # Inverse warp: enhanced_face → frame coordinates
        inv_matrix = cv2.invertAffineTransform(matrix)
        restored = cv2.warpAffine(
            enhanced_face, inv_matrix, (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )

        # Build soft feathered mask in warped space
        face_mask = np.ones((size, size), dtype=np.float32)
        border = max(size // 8, 8)
        face_mask[:border, :] = 0
        face_mask[-border:, :] = 0
        face_mask[:, :border] = 0
        face_mask[:, -border:] = 0

        # Gaussian blur for feathering
        kernel = mask_blur * 2 + 1
        face_mask = cv2.GaussianBlur(face_mask, (kernel, kernel), 0)

        # Warp mask back to frame space
        mask_restored = cv2.warpAffine(
            face_mask, inv_matrix, (w, h),
            flags=cv2.INTER_LINEAR,
        )
        mask_3ch = mask_restored[:, :, np.newaxis]

        # Blend
        blended = (restored * mask_3ch + frame * (1 - mask_3ch)).astype(np.uint8)
        return blended

    # ── ONNX inference ─────────────────────────────────────────────────────────

    def _run_gpen(self, face_crop: np.ndarray) -> np.ndarray:
        """Run GPEN ONNX model on a cropped/aligned face. Returns enhanced face."""
        size = self._input_size

        # Preprocess: BGR → RGB → float32 [-1, 1]
        rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
        inp = cv2.resize(rgb, (size, size)).astype(np.float32)
        inp = (inp - 127.5) / 127.5                  # [-1, 1]
        inp = inp.transpose(2, 0, 1)[np.newaxis]     # (1, 3, H, W)

        # Inference
        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: inp})
        out = outputs[0][0]                          # (3, H, W)

        # Postprocess: [-1,1] → [0,255] → BGR
        out = out.transpose(1, 2, 0)                 # (H, W, 3)
        out = np.clip((out + 1) * 127.5, 0, 255).astype(np.uint8)
        out_bgr = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
        return out_bgr

    # ── Public API ─────────────────────────────────────────────────────────────

    def enhance(
        self,
        frame: np.ndarray,
        face=None,  # InsightFace Face object (optional, for precise alignment)
        fidelity: float = 0.8,
    ) -> np.ndarray:
        """
        Enhance face(s) in a BGR frame using GPEN ONNX.

        Args:
            frame:    BGR numpy array (the full image/frame).
            face:     InsightFace Face object with .kps (5-point landmarks).
                      If None, enhances the whole frame region (less precise).
            fidelity: 0.0 = max enhancement, 1.0 = preserve original more.
                      (Currently blend weight — future: GPEN fidelity param)

        Returns:
            Enhanced BGR frame. Falls back to original on error.
        """
        if not self._load():
            return frame

        try:
            if face is not None and hasattr(face, "kps") and face.kps is not None:
                # Precise mode: warp face using 5-point landmarks
                landmarks = face.kps.astype(np.float32)
                face_crop, matrix = self._warp_face(frame, landmarks, self._input_size)
                enhanced_crop = self._run_gpen(face_crop)

                # Blend with fidelity (1.0 = full enhancement, lower = keep original)
                if fidelity < 1.0:
                    enhanced_crop = cv2.addWeighted(
                        enhanced_crop, fidelity,
                        face_crop, 1.0 - fidelity,
                        0,
                    )

                result = self._paste_back(frame, enhanced_crop, matrix)
            else:
                # Fallback: enhance full frame region (for images without landmarks)
                h, w = frame.shape[:2]
                resized = cv2.resize(frame, (self._input_size, self._input_size))
                enhanced = self._run_gpen(resized)
                enhanced = cv2.resize(enhanced, (w, h))
                result = cv2.addWeighted(enhanced, fidelity, frame, 1.0 - fidelity, 0)

            return result

        except Exception as e:
            logger.warning("face_enhancer_failed", error=str(e))
            return frame

    def enhance_image(self, image: np.ndarray, face=None) -> np.ndarray:
        """Convenience wrapper for image-mode (full enhancement)."""
        return self.enhance(image, face=face, fidelity=settings.enhancer_fidelity)


face_enhancer = FaceEnhancer()
