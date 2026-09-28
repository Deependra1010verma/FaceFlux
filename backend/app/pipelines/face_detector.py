"""
Face detection using InsightFace.
Lazy-loads the model on first use so startup stays fast.

License note:
  InsightFace models (buffalo_l etc.) are released under the
  "Non-Commercial Research/Education" license.  This application
  is intended for local personal use — ensure you comply with the
  license terms before any commercial deployment.
"""

import base64
import io
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


class FaceDetector:
    """Wraps InsightFace FaceAnalysis for detection and landmark extraction."""

    def __init__(self):
        self._app = None

    def _load(self) -> None:
        if self._app is not None:
            return
        try:
            import insightface
            from insightface.app import FaceAnalysis

            logger.info("loading_face_detector")
            providers = hardware_service.get_onnx_providers()
            self._app = FaceAnalysis(
                name="buffalo_l",
                root=str(settings.model_dir),
                providers=providers,
            )
            self._app.prepare(
                ctx_id=0 if "CUDA" in hardware_service.acceleration else -1,
                det_size=(settings.det_size, settings.det_size),
            )
            logger.info("face_detector_loaded", provider=providers[0])
        except Exception as e:
            raise RuntimeError(f"Failed to load InsightFace: {e}") from e

    def detect_in_image(
        self, image: np.ndarray, min_score: float = None
    ) -> List:
        """Detect faces in a BGR numpy image. Returns list of Face objects."""
        self._load()
        if min_score is None:
            min_score = settings.face_score_threshold
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        faces = self._app.get(rgb)
        return [f for f in faces if f.det_score >= min_score]

    def detect_in_file(self, path: Path) -> List:
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"Cannot read image: {path}")
        return self.detect_in_image(img)

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

            results.append(
                FaceInfo(
                    index=i,
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                    score=float(face.det_score),
                    thumbnail_b64=thumbnail_b64,
                )
            )
        return results

    def get_representative_frame_faces(
        self, video_path: Path, sample_every_n_frames: int = 30
    ) -> Tuple[np.ndarray, List]:
        """
        Sample frames from the video and return the frame + faces from the
        frame that has the most detected faces (covers multi-person videos).
        """
        self._load()
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        first_frame = None
        best_frame = None
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
                    faces = self.detect_in_image(frame)
                    if len(faces) > len(best_faces):
                        best_faces = faces
                        best_frame = frame.copy()
                frame_idx += 1
        finally:
            cap.release()

        # If faces were found, use that frame; otherwise fallback to first frame read
        selected_frame = best_frame if best_frame is not None else first_frame
        if selected_frame is None:
            raise ValueError("No frames could be read from video.")
        return selected_frame, best_faces


face_detector = FaceDetector()
