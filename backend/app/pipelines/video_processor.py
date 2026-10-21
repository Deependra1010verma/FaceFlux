"""
Video processing pipeline — Stage 2 upgrade: parallel frame processing + face caching.

Performance improvements:
  1. ThreadPoolExecutor: swap + enhancement frames parallel chalte hain
     (multi-core CPUs pe 2x-4x speedup)
  2. Face detection caching: detected bbox linear-extrapolate karo,
     skip redundant SCRFD calls between sample frames
  3. Scene change detection: agar frame static hai, enhancement skip karo
  4. Color correction per frame (Stage 1 from color_correction.py)
  5. GPEN-aware enhancement with face landmarks (Stage 1)

Apple Silicon (M-series) specific:
  6. CoreML ONNX provider → Neural Engine + GPU acceleration (auto via hardware_service)
  7. VideoToolbox hardware encoding → h264_videotoolbox (auto via ffmpeg service)
  8. Configurable small frame batches for 16GB unified memory
  9. Conservative worker ceiling for M5's fanless thermal envelope
"""

import asyncio
import os
import platform
import copy
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

from app.core.config import settings
from app.core.logger import get_logger
from app.core import job_store
from app.models.job import Job, JobStatus, VideoMeta
from app.pipelines.face_detector import face_detector
from app.pipelines.face_swapper import face_swapper
from app.pipelines.face_enhancer import face_enhancer
from app.pipelines.color_correction import correct_face_color
from app.services.ffmpeg import probe_video, extract_audio, RawVideoEncoder
from app.services.apple_accel import apple_accel

logger = get_logger(__name__)


def _is_apple_silicon() -> bool:
    """True when running natively on Apple Silicon (arm64 macOS)."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"

def _get_safe_workers(enhance: bool) -> int:
    """
    Calculate memory-safe worker count based on available system RAM.

    Why this is critical:
      INSwapper + GPEN-512 neural networks already multithread internally across CPU cores.
      Spawning os.cpu_count() (e.g. 12–24) concurrent GPEN-512 instances consumes
      ~800MB–1GB PER WORKER, causing a sudden 12GB+ RAM spike that crashes 16GB/18GB systems.
      Capping to 2-4 workers keeps memory under control while saturating all CPU cores.

    Apple Silicon M5 (16GB unified):
      - CoreML handles neural math on ANE/GPU, reducing CPU thread pressure per worker.
      - 16GB unified memory with fast 153 GB/s bandwidth = higher safe worker ceiling.
      - M5 10-core CPU: 4 performance + 6 efficiency cores.
    """
    import psutil
    try:
        available_gb = psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        available_gb = 8.0

    apple = _is_apple_silicon()

    configured_limit = max(1, settings.max_frame_workers)

    if enhance:
        if available_gb < 4.0:
            return 1
        elif available_gb < 8.0:
            return min(2, configured_limit)
        elif apple:
            # GPEN + INSwapper are large models. Keep concurrency conservative on
            # 16GB unified memory; CoreML acceleration does not make model copies free.
            return min(2, configured_limit)
        else:
            return min(2, configured_limit)
    else:
        if available_gb < 4.0:
            return 2
        elif apple:
            return min(3, max(1, configured_limit + 1))
        else:
            return min(3, max(1, configured_limit + 1))


QUALITY_SETTINGS = {
    "fast": {
        "crf": 23,
        "preset": "ultrafast",
        "enhance": False,
        "det_sample_rate": 8,      # detect every N frames
        "color_correction": False,  # skip color correction for speed
        "vt_quality": "50",        # VideoToolbox quality (macOS)
        "vt_bitrate": "4M",        # VideoToolbox bitrate cap
    },
    "balanced": {
        "crf": 18,
        "preset": "medium",
        "enhance": True,
        "det_sample_rate": 3,
        "color_correction": True,
        "vt_quality": "60",        # VideoToolbox ≈ CRF 18
        "vt_bitrate": "8M",
    },
    "high": {
        "crf": 15,
        "preset": "slow",
        "enhance": True,
        "det_sample_rate": 1,
        "color_correction": True,
        "vt_quality": "70",        # VideoToolbox ≈ CRF 15 (near-lossless)
        "vt_bitrate": "15M",
    },
}

ProgressCallback = Callable[[JobStatus, int, str], None]



# ── IoU + face tracking helpers ───────────────────────────────────────────────

def _iou(boxA, boxB) -> float:
    """Intersection over Union for bbox tracking."""
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
    """Find face closest to tracked reference bbox using IoU."""
    best_face, best_iou = None, 0.3
    for face in faces:
        b = face.bbox
        iou = _iou(reference_bbox, [b[0], b[1], b[2], b[3]])
        if iou > best_iou:
            best_iou = iou
            best_face = face
    return best_face


def _extrapolate_bbox(
    prev_bboxes: List[list], history: int = 3
) -> Optional[list]:
    """
    Predict next bbox using linear extrapolation from last N frames.
    Used to skip expensive face detection on frames where face hasn't moved much.
    """
    if len(prev_bboxes) < 2:
        return prev_bboxes[-1] if prev_bboxes else None
    recent = prev_bboxes[-min(history, len(prev_bboxes)):]
    arr = np.array(recent, dtype=np.float32)
    # Simple linear extrapolation: last + (last - second_last)
    velocity = arr[-1] - arr[-2]
    predicted = arr[-1] + velocity
    return predicted.tolist()


def _predict_face_geometry(face, old_bbox, new_bbox):
    """Copy a detected face while moving/scaling its geometry to a predicted box.

    InsightFace's swapper and GPEN both consume landmarks, not just the bbox.
    Reusing the original Face object between detector samples causes alignment
    drift, so every extrapolated frame gets transformed landmarks as well.
    """
    if face is None or old_bbox is None or new_bbox is None:
        return face

    predicted = copy.copy(face)
    old = np.asarray(old_bbox, dtype=np.float32)
    new = np.asarray(new_bbox, dtype=np.float32)
    old_w = max(float(old[2] - old[0]), 1.0)
    old_h = max(float(old[3] - old[1]), 1.0)
    sx = float(new[2] - new[0]) / old_w
    sy = float(new[3] - new[1]) / old_h

    def transform_points(points):
        if points is None:
            return None
        arr = np.asarray(points).copy()
        if arr.ndim < 2 or arr.shape[-1] < 2:
            return points
        arr[..., 0] = new[0] + (arr[..., 0] - old[0]) * sx
        arr[..., 1] = new[1] + (arr[..., 1] - old[1]) * sy
        return arr

    if hasattr(predicted, "bbox"):
        predicted.bbox = new.copy()
    for attr in ("kps", "landmark_2d_106"):
        if hasattr(predicted, attr):
            value = getattr(predicted, attr)
            if value is not None:
                setattr(predicted, attr, transform_points(value))
    return predicted


def _scene_changed(frame_a: np.ndarray, frame_b: np.ndarray, threshold: float = 8.0) -> bool:
    """
    Quick scene change detection using mean absolute difference of grayscale.
    If frames are very similar, we can skip expensive enhancement.
    """
    if frame_a is None or frame_b is None:
        return True
    gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray_a, gray_b)
    return float(diff.mean()) > threshold


def _blend_face_temporally(
    current: np.ndarray,
    previous: Optional[np.ndarray],
    face,
    current_weight: float = 0.85,
) -> np.ndarray:
    """Reduce face flicker without ghosting the moving background."""
    if previous is None or face is None or not hasattr(face, "bbox"):
        return current

    h, w = current.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in face.bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 - x1 < 8 or y2 - y1 < 8:
        return current

    mask = np.zeros((h, w), dtype=np.float32)
    center = ((x1 + x2) // 2, (y1 + y2) // 2)
    axes = (max(2, (x2 - x1) // 2), max(2, (y2 - y1) // 2))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(2.0, min(12.0, (x2 - x1) / 10.0)))
    mask = (mask * (1.0 - current_weight))[:, :, None]
    return (current.astype(np.float32) * (1.0 - mask) + previous.astype(np.float32) * mask).astype(np.uint8)


# ── Per-frame processor (runs in thread pool) ─────────────────────────────────

def _process_single_frame(
    frame: np.ndarray,
    target_face,
    source_face,
    do_enhance: bool,
    do_color: bool,
    fidelity: float,
) -> np.ndarray:
    """
    Process one frame: swap → color correct → enhance.
    This runs in a ThreadPoolExecutor worker thread.
    Thread-safe: all operations are CPU/GPU ONNX, no shared mutable state.
    """
    original = frame.copy()
    result = frame.copy()

    try:
        # ── Step 1: Raw face swap (inswapper_128) ─────────────────────────────
        swapped_full = face_swapper.swap(result, target_face, source_face)

        # ── Step 2: BiSeNet semantic blending (Phase 2 quality upgrade) ───────
        # Extract aligned face crop → run BiSeNet → get pixel-level mask →
        # blend swapped face over original with soft semantic boundary.
        # Falls back silently to direct paste if model not available.
        from app.pipelines.face_parser import face_parser

        if face_parser.is_available:
            try:
                # Get face crop from the ORIGINAL frame (pre-swap region)
                bbox = None
                if hasattr(target_face, "bbox") and target_face.bbox is not None:
                    b = target_face.bbox
                    h_fr, w_fr = original.shape[:2]
                    x1 = max(0, int(b[0]))
                    y1 = max(0, int(b[1]))
                    x2 = min(w_fr, int(b[2]))
                    y2 = min(h_fr, int(b[3]))
                    bbox = (x1, y1, x2, y2)

                if bbox and (bbox[2] - bbox[0]) > 10 and (bbox[3] - bbox[1]) > 10:
                    orig_crop    = original[bbox[1]:bbox[3], bbox[0]:bbox[2]]
                    swapped_crop = swapped_full[bbox[1]:bbox[3], bbox[0]:bbox[2]]

                    # Color correct the swapped crop to match original lighting
                    if do_color and settings.color_correction:
                        swapped_crop = correct_face_color(
                            swapped_frame=swapped_full,
                            original_frame=original,
                            face_bbox=list(b),
                            strength=0.5,
                        )[bbox[1]:bbox[3], bbox[0]:bbox[2]]

                    # BiSeNet semantic blend — skin/face pixels only
                    blended_crop = face_parser.blend_with_fallback(
                        original=orig_crop,
                        swapped=swapped_crop,
                        face_crop=orig_crop,
                    )

                    # Paste blended crop back into full frame
                    result = swapped_full.copy()
                    result[bbox[1]:bbox[3], bbox[0]:bbox[2]] = blended_crop
                else:
                    result = swapped_full
            except Exception as bisenet_err:
                logger.debug("bisenet_frame_error", error=str(bisenet_err))
                result = swapped_full
        else:
            # BiSeNet not available — use old path (still good quality)
            result = swapped_full

            # Color correction (old path)
            if do_color and settings.color_correction:
                bbox_list = None
                if hasattr(target_face, "bbox") and target_face.bbox is not None:
                    bbox_list = target_face.bbox.tolist()
                result = correct_face_color(
                    swapped_frame=result,
                    original_frame=original,
                    face_bbox=bbox_list,
                    strength=0.5,
                )

        # ── Step 3: GPEN face enhancement ────────────────────────────────────
        if do_enhance:
            result = face_enhancer.enhance(
                result,
                face=target_face,
                fidelity=fidelity,
            )

    except Exception as e:
        logger.warning("frame_process_error", error=str(e))
        return frame  # return original on error

    return result




# ── Main pipeline ─────────────────────────────────────────────────────────────

async def process_video(job: Job, update_progress: ProgressCallback) -> str:
    """
    Main pipeline coroutine — parallel frame processing.
    Runs blocking work in a thread pool.
    Returns path to output video.
    """
    job_id = job.job_id
    q = QUALITY_SETTINGS.get(job.quality, QUALITY_SETTINGS["balanced"])
    do_enhance = job.enhance and q.get("enhance", True)
    do_color = q.get("color_correction", True)
    num_workers = q.get("workers") or _get_safe_workers(do_enhance)

    def _run_pipeline() -> str:
        logger.info(
            "pipeline_start",
            job_id=job_id,
            quality=job.quality,
            workers=num_workers,
        )

        video_path = Path(job.video_path)
        job_temp_dir = settings.temp_dir / job_id
        job_temp_dir.mkdir(parents=True, exist_ok=True)

        # ── Step 1: Analyze video ─────────────────────────────────────────────
        update_progress(JobStatus.ANALYZING, 2, "Analyzing video...")
        meta: VideoMeta = probe_video(video_path)
        logger.info("video_analyzed", fps=meta.fps, duration=meta.duration)

        # ── Step 2: Extract audio ─────────────────────────────────────────────
        audio_path = job_temp_dir / "audio.aac"
        has_audio = False
        if meta.has_audio:
            has_audio = extract_audio(video_path, audio_path)

        # ── Step 3: Detect & fuse source face(s) ─────────────────────────────
        update_progress(JobStatus.DETECTING, 5, "Detecting faces in reference photos...")
        all_face_paths = job.face_paths if job.face_paths else [job.face_path]
        detected_source_faces = []

        for p_str in all_face_paths:
            try:
                faces = face_detector.detect_in_file(Path(p_str))
                if faces:
                    detected_source_faces.append(faces[0])
                else:
                    logger.warning("no_face_in_reference", path=p_str)
            except Exception as e:
                logger.warning("reference_read_failed", path=p_str, error=str(e))

        if not detected_source_faces:
            raise ValueError(
                "Reference photos mein koi face detect nahi hua.\n"
                "Clear, front-facing, well-lit photo use karo."
            )

        if len(detected_source_faces) > 1:
            update_progress(
                JobStatus.DETECTING, 8,
                f"Fusing 3D structure from {len(detected_source_faces)} angles...",
            )
            source_face = face_swapper.fuse_source_faces(detected_source_faces)
        else:
            source_face = detected_source_faces[0]

        # ── Step 4: Stream frames through a bounded processing buffer ─────────
        update_progress(JobStatus.TRACKING, 10, "Opening video...")
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(
                f"Video file open nahi ho paya: {video_path}\n"
                "MP4, MOV, MKV format try karo."
            )

        total_frames = meta.frame_count or int(meta.fps * meta.duration)
        fps = meta.fps
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = settings.output_dir / f"faceswap_{timestamp}_{job.quality}_{job_id[:8]}.mp4"
        writer = None

        # Seed reference bbox from job's detected faces
        reference_bbox = None
        if job.detected_faces and job.target_face_index < len(job.detected_faces):
            fi = job.detected_faces[job.target_face_index]
            reference_bbox = fi.bbox

        sample_rate = max(
            1,
            settings.det_sample_rate if settings.det_sample_rate > 0 else q["det_sample_rate"],
        )
        enhance_stride = max(1, settings.enhance_frame_stride)
        if job.quality == "high":
            enhance_stride = 1
        fidelity = settings.enhancer_fidelity

        frame_idx = 0
        swapped_count = 0
        last_target_face = None
        last_raw_frame = None      # for scene change detection
        prev_output_frame = None   # for temporal consistency blending
        bbox_history: List[list] = []  # for bbox extrapolation

        # Batch buffer for parallel processing
        BATCH_SIZE = max(1, settings.frame_batch_size)
        frame_buffer: List[Tuple[int, np.ndarray, object]] = []  # (idx, frame, face)
        batch_counter = 0
        pool = ThreadPoolExecutor(max_workers=num_workers)

        writer = RawVideoEncoder(
            output_path=output_path,
            width=width,
            height=height,
            fps=fps,
            audio_path=audio_path if has_audio else None,
            crf=q["crf"],
            preset=q["preset"],
            codec=settings.output_codec,
            vt_quality=q.get("vt_quality", "60"),
            vt_bitrate=q.get("vt_bitrate", "8M"),
            quality=job.quality if settings.temporal_nr else "fast",
        )

        def flush_batch(batch: List[Tuple[int, np.ndarray, object]]):
            """Process a batch of (idx, frame, face) tuples in parallel."""
            nonlocal swapped_count

            if not batch:
                return []

            futures = [
                pool.submit(
                    _process_single_frame,
                    frm,
                    face,
                    source_face,
                    do_enhance and (bidx % enhance_stride == 0),
                    do_color,
                    fidelity,
                )
                for (bidx, frm, face) in batch
            ]
            results = []
            for fut, (bidx, frm, face) in zip(futures, batch):
                try:
                    out = fut.result(timeout=60)
                    swapped_count += 1
                except Exception as e:
                    logger.warning("batch_frame_failed", frame=bidx, error=str(e))
                    out = frm  # fallback to original

                results.append(out)
            return results

        def write_batch(batch: List[Tuple[int, np.ndarray, object]]) -> None:
            """Flush processed frames in input order and apply face-only smoothing."""
            nonlocal prev_output_frame, batch_counter
            if not batch:
                return

            processed = flush_batch(batch)
            for out_frame, (_, _, face) in zip(processed, batch):
                if prev_output_frame is not None:
                    out_frame = _blend_face_temporally(
                        out_frame, prev_output_frame, face
                    )
                prev_output_frame = out_frame
                writer.write(out_frame)
            batch.clear()
            batch_counter += 1
            apple_accel.thermal_pause(batch_counter, every=6, pause_ms=80)

        update_progress(JobStatus.SWAPPING, 12, "Processing frames...")

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Cancellation check
                if job_store.is_cancelled(job_id):
                    logger.info("job_cancelled", frame=frame_idx)
                    raise InterruptedError("Job cancelled by user.")

                # ── Scene change detection ────────────────────────────────────
                if last_raw_frame is not None and _scene_changed(last_raw_frame, frame):
                    # Preserve frame order before resetting tracking state.
                    write_batch(frame_buffer)
                    bbox_history.clear()
                    last_target_face = None
                    reference_bbox = None
                    prev_output_frame = None

                # ── Face detection with caching ───────────────────────────────
                if frame_idx % sample_rate == 0:
                    faces = face_detector.detect_in_image(frame)
                    if faces:
                        if reference_bbox is not None:
                            target_face = _find_target_face(faces, reference_bbox)
                        else:
                            idx = min(job.target_face_index, len(faces) - 1)
                            target_face = faces[idx]

                        if target_face is not None:
                            last_target_face = target_face
                            b = target_face.bbox
                            new_bbox = [b[0], b[1], b[2], b[3]]
                            reference_bbox = new_bbox
                            bbox_history.append(new_bbox)
                            if len(bbox_history) > 10:
                                bbox_history.pop(0)
                    else:
                        # Try extrapolated bbox on intermediate frames
                        if frame_idx % (sample_rate * 5) == 0:
                            last_target_face = None
                else:
                    # Between detection frames: extrapolate bbox for tracking
                    if last_target_face is not None and len(bbox_history) >= 2:
                        old_bbox = list(last_target_face.bbox)
                        predicted = _extrapolate_bbox(bbox_history)
                        if predicted:
                            reference_bbox = predicted
                            last_target_face = _predict_face_geometry(
                                last_target_face, old_bbox, predicted
                            )
                            bbox_history.append(predicted)
                            if len(bbox_history) > 10:
                                bbox_history.pop(0)

                # Queue frame for batch processing (only if we have a face)
                if last_target_face is not None:
                    frame_buffer.append((frame_idx, frame.copy(), last_target_face))
                else:
                    # Write unprocessed frame directly — reset temporal state
                    write_batch(frame_buffer)
                    prev_output_frame = None
                    writer.write(frame)

                # Flush batch when buffer is full
                if len(frame_buffer) >= BATCH_SIZE:
                    write_batch(frame_buffer)

                frame_idx += 1
                last_raw_frame = frame

                # Periodic memory cleanup to prevent RAM accumulation
                if frame_idx % 45 == 0:
                    import gc
                    gc.collect()

                # Progress update every 30 frames
                if frame_idx % 30 == 0 and total_frames > 0:
                    pct = int(12 + (frame_idx / total_frames) * 75)
                    update_progress(
                        JobStatus.SWAPPING,
                        min(pct, 87),
                        f"Processing frame {frame_idx}/{total_frames}...",
                    )

            # Flush remaining frames
            write_batch(frame_buffer)

        finally:
            cap.release()
            if writer is not None:
                writer.release()
            pool.shutdown(wait=True, cancel_futures=True)

        logger.info(
            "swap_complete",
            job_id=job_id,
            total_frames=frame_idx,
            swapped=swapped_count,
            workers=num_workers,
        )

        update_progress(JobStatus.ENCODING, 90, "Finalizing video...")
        logger.info("encoding_complete", job_id=job_id, output=str(output_path), streamed=True)
        return str(output_path)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_pipeline)
    return result
