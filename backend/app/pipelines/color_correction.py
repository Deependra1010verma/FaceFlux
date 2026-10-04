"""
Color correction utilities for face swap post-processing.

After swapping a face, the skin tone of the pasted face may differ from
the target video's lighting/color temperature. This module provides
histogram-based color matching to blend seamlessly.

All functions use only OpenCV + NumPy — zero extra dependencies.
"""

import cv2
import numpy as np
from typing import Optional


def match_histogram_color(
    source: np.ndarray,
    target: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Match color histogram of `source` to `target` in LAB color space.

    This is the most effective method for skin tone correction after face swap.
    Matching in LAB keeps luminance (L) and only adjusts color channels (A, B),
    which prevents over-brightening/darkening while correcting hue.

    Args:
        source:  BGR image to be color-corrected (the swapped face region).
        target:  BGR image whose color distribution to match (original frame).
        mask:    Optional binary mask (uint8, 255=face region). If provided,
                 only compute stats from the masked region.

    Returns:
        Color-corrected BGR image (same shape as source).
    """
    if source is None or target is None:
        return source

    # Convert both to LAB
    src_lab = cv2.cvtColor(source.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    tgt_lab = cv2.cvtColor(target.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)

    # Compute stats (mean + std) per channel
    if mask is not None and mask.sum() > 0:
        mask_bool = mask > 127
        src_pixels = src_lab[mask_bool]
        tgt_pixels = tgt_lab[mask_bool]
    else:
        src_pixels = src_lab.reshape(-1, 3)
        tgt_pixels = tgt_lab.reshape(-1, 3)

    result = src_lab.copy()

    for ch in range(3):  # L, A, B channels
        src_mean = src_pixels[:, ch].mean()
        src_std  = src_pixels[:, ch].std() + 1e-6
        tgt_mean = tgt_pixels[:, ch].mean()
        tgt_std  = tgt_pixels[:, ch].std() + 1e-6

        # Scale source channel to match target distribution
        result[:, :, ch] = (
            (src_lab[:, :, ch] - src_mean) * (tgt_std / src_std) + tgt_mean
        )

    # Clip to valid LAB range
    result = np.clip(result, 0, 255).astype(np.uint8)
    corrected = cv2.cvtColor(result, cv2.COLOR_LAB2BGR)
    return corrected


def correct_face_color(
    swapped_frame: np.ndarray,
    original_frame: np.ndarray,
    face_bbox: Optional[list] = None,
    strength: float = 0.6,
) -> np.ndarray:
    """
    Apply color correction to the face region of a swapped frame.

    Matches the color of the swapped face to the surrounding skin tones
    in the original frame, using a soft blend (strength parameter).

    Args:
        swapped_frame:   Full BGR frame after face swap.
        original_frame:  Original BGR frame (before swap) — color reference.
        face_bbox:       [x1, y1, x2, y2] bounding box of the swapped face.
                         If None, corrects the whole frame (less precise).
        strength:        Correction blend weight (0.0 = no correction, 1.0 = full).
                         0.6 is recommended — natural result without over-correction.

    Returns:
        Color-corrected BGR frame.
    """
    if swapped_frame is None:
        return original_frame

    if strength <= 0.0:
        return swapped_frame

    try:
        if face_bbox is not None:
            x1, y1, x2, y2 = [int(v) for v in face_bbox]
            h, w = swapped_frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 - x1 < 8 or y2 - y1 < 8:
                return swapped_frame

            # Expand bbox slightly for context (helps histogram matching)
            pad_x = int((x2 - x1) * 0.1)
            pad_y = int((y2 - y1) * 0.1)
            rx1 = max(0, x1 - pad_x)
            ry1 = max(0, y1 - pad_y)
            rx2 = min(w, x2 + pad_x)
            ry2 = min(h, y2 + pad_y)

            # Extract regions
            src_region = swapped_frame[ry1:ry2, rx1:rx2].copy()
            tgt_region = original_frame[ry1:ry2, rx1:rx2].copy()

            # Color match
            corrected_region = match_histogram_color(src_region, tgt_region)

            # Soft blend back
            blended_region = cv2.addWeighted(
                corrected_region, strength,
                src_region, 1.0 - strength,
                0,
            )

            # Paste back
            result = swapped_frame.copy()
            result[ry1:ry2, rx1:rx2] = blended_region
            return result

        else:
            # Full-frame color correction
            corrected = match_histogram_color(swapped_frame, original_frame)
            return cv2.addWeighted(corrected, strength, swapped_frame, 1.0 - strength, 0)

    except Exception:
        # Never crash — silently return original swap
        return swapped_frame
