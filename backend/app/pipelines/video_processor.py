"""
Video processing pipeline: orchestrates the full face-swap workflow.
Processes frames in batches, updates job progress, writes output video.
"""

import asyncio
import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from app.core.config import settings
from app.core.logger import get_logger
from app.models.job import Job, JobStatus, VideoMeta
from app.pipelines.face_detector import face_detector
from app.pipelines.face_swapper import face_swapper
from app.pipelines.face_enhancer import face_enhancer
from app.services.ffmpeg import probe_video, extract_audio, mux_audio_video

logger = get_logger(__name__)

QUALITY_SETTINGS = {
    "fast": {
        "crf": 23,
        "preset": "ultrafast",
        "enhance": False,
        "det_sample_rate": 6,   # detect every N frames
    },
    "balanced": {
        "crf": 18,
        "preset": "medium",
        "enhance": True,
        "det_sample_rate": 3,
    },
    "high": {
        "crf": 15,
        "preset": "slow",
        "enhance": True,
        "det_sample_rate": 1,
    },
}


ProgressCallback = Callable[[JobStatus, int, str], None]


def _iou(boxA, boxB):
    """Intersection over union for bbox tracking."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    if inter == 0:
        return 0.0
    areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return inter / float(areaA + areaB - inter)


def _find_target_face(faces, reference_bbox):
    """Find the face in current frame closest to the tracked reference bbox."""
    best_face = None
    best_iou = 0.3  # minimum IoU threshold

    for face in faces:
        b = face.bbox
        iou = _iou(reference_bbox, [b[0], b[1], b[2], b[3]])
        if iou > best_iou:
            best_iou = iou
            best_face = face

    return best_face


async def process_video(job: Job, update_progress: ProgressCallback) -> str:
    """
    Main pipeline coroutine. Runs blocking work in a thread pool.
    Returns path to output video.
    """
    job_id = job.job_id
    q = QUALITY_SETTINGS.get(job.quality, QUALITY_SETTINGS["balanced"])
    do_enhance = job.enhance and q["enhance"]

    def _run_pipeline() -> str:
        logger.info("pipeline_start", job_id=job_id)

        video_path = Path(job.video_path)
        face_path = Path(job.face_path)
        job_temp_dir = settings.temp_dir / job_id
        job_temp_dir.mkdir(parents=True, exist_ok=True)

        # ── Step 1: Analyze video ─────────────────────────────────────────
        update_progress(JobStatus.ANALYZING, 2, "Analyzing video metadata...")
        meta: VideoMeta = probe_video(video_path)
        logger.info("video_analyzed", job_id=job_id, fps=meta.fps, duration=meta.duration)

        # ── Step 2: Extract audio ─────────────────────────────────────────
        audio_path = job_temp_dir / "audio.aac"
        has_audio = False
        if meta.has_audio:
            has_audio = extract_audio(video_path, audio_path)

        # ── Step 3: Detect source face ────────────────────────────────────
        update_progress(JobStatus.DETECTING, 5, "Detecting faces in reference photo...")
        source_faces = face_detector.detect_in_file(face_path)
        if not source_faces:
            raise ValueError("No face detected in the reference photo.")
        source_face = source_faces[0]
        logger.info("source_face_detected", job_id=job_id)

        # ── Step 4: Open video and process frames ─────────────────────────
        update_progress(JobStatus.TRACKING, 10, "Opening video and tracking target face...")
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {video_path}")

        total_frames = meta.frame_count or int(meta.fps * meta.duration)
        fps = meta.fps
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Output video writer (temporary, no audio)
        raw_output = job_temp_dir / "raw_swapped.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(raw_output), fourcc, fps, (width, height))

        # Seed target face bbox from job's detected faces
        reference_bbox = None
        if job.detected_faces and job.target_face_index < len(job.detected_faces):
            fi = job.detected_faces[job.target_face_index]
            reference_bbox = fi.bbox  # [x1, y1, x2, y2]

        sample_rate = max(1, q["det_sample_rate"])
        frame_idx = 0
        swapped_count = 0
        last_target_face = None

        update_progress(JobStatus.SWAPPING, 12, "Swapping faces...")

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                output_frame = frame.copy()

                # Detect faces periodically or every frame
                if frame_idx % sample_rate == 0:
                    faces = face_detector.detect_in_image(frame)
                    if faces:
                        if reference_bbox is not None:
                            target_face = _find_target_face(faces, reference_bbox)
                        else:
                            # Fallback: use face at target_face_index
                            idx = min(job.target_face_index, len(faces) - 1)
                            target_face = faces[idx]

                        if target_face is not None:
                            last_target_face = target_face
                            b = target_face.bbox
                            reference_bbox = [b[0], b[1], b[2], b[3]]
                    else:
                        # No faces detected — clear last target
                        if frame_idx % (sample_rate * 5) == 0:
                            last_target_face = None

                # Perform swap if we have a target face
                if last_target_face is not None:
                    try:
                        output_frame = face_swapper.swap(output_frame, last_target_face, source_face)
                        swapped_count += 1
                    except Exception as e:
                        logger.warning("swap_frame_failed", job_id=job_id, frame=frame_idx, error=str(e))

                # Enhancement
                if do_enhance and last_target_face is not None:
                    try:
                        output_frame = face_enhancer.enhance(output_frame)
                    except Exception as e:
                        logger.warning("enhance_frame_failed", job_id=job_id, frame=frame_idx, error=str(e))

                writer.write(output_frame)
                frame_idx += 1

                # Progress update every 25 frames
                if frame_idx % 25 == 0 and total_frames > 0:
                    pct = int(12 + (frame_idx / total_frames) * 75)
                    pct = min(pct, 87)
                    update_progress(
                        JobStatus.SWAPPING,
                        pct,
                        f"Swapping frame {frame_idx}/{total_frames}...",
                    )
        finally:
            cap.release()
            writer.release()

        logger.info("swap_complete", job_id=job_id, frames=frame_idx, swapped=swapped_count)

        # ── Step 5: Encode final output ───────────────────────────────────
        update_progress(JobStatus.ENCODING, 90, "Encoding final video...")
        output_path = settings.output_dir / f"{job_id}_output.mp4"

        mux_audio_video(
            frames_video=raw_output,
            audio_path=audio_path if has_audio else None,
            output_path=output_path,
            fps=fps,
            crf=q["crf"],
            preset=q["preset"],
            codec=settings.output_codec,
        )

        logger.info("encoding_complete", job_id=job_id, output=str(output_path))
        return str(output_path)

    # Run blocking pipeline in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_pipeline)
    return result
