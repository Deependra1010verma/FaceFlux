"""
Image processing pipeline: fast photo-to-photo face-swap workflow.
Swaps face in a static target photo in 1-2 seconds with multi-angle reference fusion.
"""

import asyncio
from pathlib import Path
from typing import Callable
import cv2

from app.core.config import settings
from app.core.logger import get_logger
from app.models.job import Job, JobStatus
from app.pipelines.face_detector import face_detector
from app.pipelines.face_swapper import face_swapper
from app.pipelines.face_enhancer import face_enhancer

logger = get_logger(__name__)

ProgressCallback = Callable[[JobStatus, int, str], None]


async def process_image(job: Job, update_progress: ProgressCallback) -> str:
    """
    Main image pipeline coroutine. Runs blocking work in a thread pool.
    Returns path to output swapped image.
    """
    job_id = job.job_id

    def _run_pipeline() -> str:
        logger.info("image_pipeline_start", job_id=job_id)
        target_img_path = Path(job.video_path)  # video_path field holds target file path

        update_progress(JobStatus.ANALYZING, 15, "Reading target photo...")
        target_img = cv2.imread(str(target_img_path))
        if target_img is None:
            raise ValueError(f"Target photo open nahi ho payi: {target_img_path}")

        # ── Step 1: Detect target face in photo ──────────────────────────
        update_progress(JobStatus.DETECTING, 30, "Detecting face in target photo...")
        target_faces = face_detector.detect_in_image(target_img)
        if not target_faces:
            raise ValueError("Target photo mein koi chehra detect nahi hua.")

        idx = min(job.target_face_index, len(target_faces) - 1)
        target_face = target_faces[idx]

        # ── Step 2: Detect & fuse source face(s) ─────────────────────────
        update_progress(JobStatus.DETECTING, 50, "Analyzing reference photos...")
        all_face_paths = job.face_paths if job.face_paths else [job.face_path]
        detected_source_faces = []

        for p_str in all_face_paths:
            faces = face_detector.detect_in_file(Path(p_str))
            if faces:
                detected_source_faces.append(faces[0])

        if not detected_source_faces:
            raise ValueError("Uploaded reference photos mein koi face detect nahi hua.")

        if len(detected_source_faces) > 1:
            update_progress(
                JobStatus.DETECTING,
                65,
                f"Fusing 3D facial angles from {len(detected_source_faces)} reference photos...",
            )
            source_face = face_swapper.fuse_source_faces(detected_source_faces)
        else:
            source_face = detected_source_faces[0]

        # ── Step 3: Swap face ───────────────────────────────────────────
        update_progress(JobStatus.SWAPPING, 80, "Swapping face on photo...")
        swapped_img = face_swapper.swap(target_img, target_face, source_face)

        # ── Step 4: Optional Enhancement ────────────────────────────────
        if job.enhance:
            update_progress(JobStatus.ENHANCING, 90, "Enhancing facial details...")
            try:
                swapped_img = face_enhancer.enhance(swapped_img)
            except Exception as e:
                logger.warning("image_enhance_failed", error=str(e))

        # ── Step 5: Save output ─────────────────────────────────────────
        update_progress(JobStatus.ENCODING, 95, "Saving output photo...")
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        ext = target_img_path.suffix.lower() if target_img_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
        output_path = settings.output_dir / f"{job_id}_output{ext}"

        cv2.imwrite(str(output_path), swapped_img)
        logger.info("image_swap_complete", job_id=job_id, output=str(output_path))
        return str(output_path)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_pipeline)
    return result
