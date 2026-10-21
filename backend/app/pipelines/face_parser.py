"""
BiSeNet face parser — pixel-level semantic face mask generation.

Used by FaceFusion 3.0 as the primary masking engine for invisible blending.
Replaces the crude rectangular/ellipse crop with a precise semantic mask
that follows the exact contour of skin, lips, nose, eyes — excluding
hair, ears, and background.

Why this matters:
  Without BiSeNet: rectangular crop → visible hard edges, hair bleeding, forehead cuts.
  With BiSeNet:    semantic pixel mask → invisible natural blending at face boundary.

Models (free, downloaded automatically):
  bisenet_resnet_34.onnx (~50 MB) — high quality, recommended
  bisenet_resnet_18.onnx (~25 MB) — faster, slightly lower quality (fallback)

Source: facefusion/models-3.0.0 on HuggingFace (free, open weights)

19 semantic classes:
  0=background, 1=skin, 2=L_eyebrow, 3=R_eyebrow, 4=L_eye, 5=R_eye,
  6=eyeglasses, 7=L_ear, 8=R_ear, 9=earring, 10=nose, 11=mouth,
  12=upper_lip, 13=lower_lip, 14=neck, 15=necklace, 16=cloth, 17=hair, 18=hat
"""

import platform
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from app.core.config import settings
from app.core.logger import get_logger
from app.services.apple_accel import apple_accel

logger = get_logger(__name__)

# ── Semantic region groups ─────────────────────────────────────────────────────
# These define WHICH parts of the face get swapped.
# Tune these to control blending behavior.

FACE_REGIONS = [1, 2, 3, 4, 5, 10, 11, 12, 13]
# skin + eyebrows + eyes + nose + lips — the core face, excludes hair/ears

FULL_FACE_REGIONS = list(range(1, 14))
# Everything except hair(17), hat(18), cloth(16), accessories

SKIN_ONLY = [1]
# Strictest — only skin pixels (sometimes too conservative)

# Default blend parameters (FaceFusion-calibrated)
DEFAULT_BLUR_KSIZE  = 21    # Gaussian feather radius — higher = softer edge
DEFAULT_EROSION_PX  = 5     # Inset mask from boundary — prevents edge artifacts

MODEL_FILENAMES = [
    "bisenet_resnet_34.onnx",   # Primary: highest quality
    "bisenet_resnet_18.onnx",   # Fallback: faster, smaller
]


class FaceParserONNX:
    """
    BiSeNet ONNX face parser — natural semantic blending masks for FaceFlux.

    Usage:
        parser = FaceParserONNX()
        mask = parser.get_blend_mask(face_crop_bgr)   # (H, W) float32 [0,1]
        result = parser.seamless_blend(original_crop, swapped_crop, mask)

    The mask is a smooth float alpha map: 1.0 = fully swapped, 0.0 = fully original.
    """

    def __init__(self):
        self._session = None
        self._input_name: Optional[str] = None
        self._available: bool = True   # Set False if model not found (graceful fallback)

    def _find_model(self) -> Optional[Path]:
        for fname in MODEL_FILENAMES:
            p = settings.model_dir / fname
            if p.exists() and p.stat().st_size > 1_000_000:
                return p
        return None

    def _load(self) -> bool:
        """Lazy-load the ONNX session. Returns False if model unavailable."""
        if self._session is not None:
            return True
        if not self._available:
            return False

        model_path = self._find_model()
        if model_path is None:
            logger.warning(
                "bisenet_model_not_found",
                searched=str(settings.model_dir),
                filenames=MODEL_FILENAMES,
                hint="Run: bash scripts/download-models.sh",
            )
            self._available = False
            return False

        try:
            import onnxruntime as ort
            from app.services.hardware import hardware_service

            is_apple = platform.system() == "Darwin" and platform.machine() == "arm64"
            providers = hardware_service.get_onnx_providers()

            if is_apple and "CoreMLExecutionProvider" in providers:
                # CoreML cache: compiled Metal graph survives restarts.
                # Pass via provider_options (parallel list to providers) —
                # index 0 options → index 0 provider (CoreML).
                cache_dir = str(Path(".coreml_cache") / "bisenet")
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
                provider_options = [
                    {
                        "ModelCacheDirectory": cache_dir,
                        "ModelFormat": "MLProgram",
                        "MLComputeUnits": "ALL",
                        "SpecializationStrategy": "FastPrediction",
                        # MLComputeUnits NOT set → CoreML default = ALL
                        # (ANE + GPU + CPU). Apple enum: 0=cpuOnly, 1=cpuAndGPU,
                        # 2=all, 3=cpuAndNeuralEngine — omitting = safest "all".
                    },
                    {},  # no options for CPU fallback
                ]
                session = ort.InferenceSession(
                    str(model_path),
                    providers=providers,
                    provider_options=provider_options,
                )
                logger.info(
                    "bisenet_loaded",
                    model=model_path.name,
                    provider="CoreMLExecutionProvider",
                    cache_dir=cache_dir,
                )
            else:
                session = ort.InferenceSession(str(model_path), providers=providers)
                logger.info("bisenet_loaded", model=model_path.name, provider=providers[0])

            # Common path: store session regardless of which branch created it
            self._session    = session
            self._input_name = session.get_inputs()[0].name
            return True

        except Exception as e:
            logger.warning("bisenet_load_failed", error=str(e))
            self._available = False
            return False

    # ── Core inference ─────────────────────────────────────────────────────────

    def parse(self, face_crop: np.ndarray) -> np.ndarray:
        """
        Run BiSeNet inference on a face crop.

        Input:  BGR face crop (any size — resized internally to 512x512)
        Output: (H, W) uint8 segmentation map with class indices 0-18,
                resized back to input dimensions.
        """
        if not self._load():
            return None

        h, w = face_crop.shape[:2]

        # Preprocess: resize → RGB → normalize to [-1, 1] → BCHW
        inp = apple_accel.gpu_resize(face_crop, (512, 512))
        inp = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB).astype(np.float32)
        inp = (inp / 127.5) - 1.0
        inp = inp.transpose(2, 0, 1)[np.newaxis]          # (1, 3, 512, 512)

        out = self._session.run(None, {self._input_name: inp})[0]
        seg = np.argmax(out[0], axis=0).astype(np.uint8)  # (512, 512) class map

        # Resize segmentation back to original face crop dimensions
        return cv2.resize(seg, (w, h), interpolation=cv2.INTER_NEAREST)

    def get_blend_mask(
        self,
        face_crop: np.ndarray,
        region_ids: List[int] = None,
        blur_ksize: int = DEFAULT_BLUR_KSIZE,
        erosion_px: int = DEFAULT_EROSION_PX,
    ) -> Optional[np.ndarray]:
        """
        Generate a smooth float32 alpha mask [0..1] for blending.

        region_ids: which semantic classes to include in the swap mask.
                    Default: FACE_REGIONS (skin + features, no hair/ears)
        blur_ksize: Gaussian feather kernel size (odd number). Higher = softer edge.
        erosion_px: pixels to inset mask from boundary. Prevents edge artifacts.

        Returns None if BiSeNet model not available (graceful fallback to old blending).
        """
        if not self._load():
            return None

        if region_ids is None:
            region_ids = FACE_REGIONS

        seg = self.parse(face_crop)
        if seg is None:
            return None

        # Build binary mask from selected semantic regions
        mask = np.zeros(seg.shape, dtype=np.uint8)
        for rid in region_ids:
            mask[seg == rid] = 255

        # Erode: inset mask boundary to prevent swapped pixels bleeding to edge
        if erosion_px > 0:
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (erosion_px * 2 + 1, erosion_px * 2 + 1)
            )
            mask = cv2.erode(mask, kernel)

        # Gaussian blur: feather/soften mask edges for invisible blending (Metal GPU)
        if blur_ksize > 0:
            ksize = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1
            mask = apple_accel.gpu_gaussian_blur(mask, (ksize, ksize), 0)

        return mask.astype(np.float32) / 255.0

    # ── Blending ───────────────────────────────────────────────────────────────

    def seamless_blend(
        self,
        original: np.ndarray,
        swapped: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Alpha-blend swapped face over original using the parsed semantic mask.

        mask=1.0 at face pixels → fully shows swapped face
        mask=0.0 at non-face pixels → fully shows original
        Smooth gradient at boundaries → invisible blend

        original, swapped: BGR face crops (same size)
        mask: float32 (H, W) [0..1]
        """
        alpha = mask[:, :, np.newaxis]   # (H, W, 1) broadcast over BGR channels
        result = swapped.astype(np.float32) * alpha + original.astype(np.float32) * (1.0 - alpha)
        return np.clip(result, 0, 255).astype(np.uint8)

    def blend_with_fallback(
        self,
        original: np.ndarray,
        swapped: np.ndarray,
        face_crop: Optional[np.ndarray] = None,
        region_ids: List[int] = None,
    ) -> np.ndarray:
        """
        Try BiSeNet semantic blending; fall back to direct swap if model unavailable.

        This is the safe entry point: always returns a valid result.
        """
        if face_crop is not None and self._available:
            mask = self.get_blend_mask(face_crop, region_ids=region_ids)
            if mask is not None:
                return self.seamless_blend(original, swapped, mask)

        # Fallback: return swapped directly (old behaviour, still works)
        logger.debug("bisenet_fallback_to_direct_swap")
        return swapped

    @property
    def is_available(self) -> bool:
        """True if BiSeNet model is loaded and ready."""
        return self._load()


# Singleton — loaded once, shared across all pipeline calls
face_parser = FaceParserONNX()
