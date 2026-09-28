"""
Virtual Try-On pipeline using HuggingFace Spaces (free, no GPU needed locally).

Flow:
  1. Video se representative frames extract karo (FFmpeg)
  2. Har frame pe IDM-VTON / CatVTON HF Space se outfit transfer karo
  3. Processed frames ko FFmpeg se video mein assemble karo + original audio mux karo

Providers tried in order:
  1. IDM-VTON (best garment fidelity)
  2. CatVTON (faster, lighter)
  3. OOTDiffusion (fallback)
"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.models.tryon_job import TryOnJob, TryOnStatus
from app.services.ffmpeg import extract_audio, probe_video

logger = get_logger(__name__)

ProgressCallback = Callable[[TryOnStatus, int, str, int, int], None]

# Sample every Nth frame — balances quality vs speed
FRAME_SAMPLE_RATE = 8   # process every 8th frame, interpolate rest


def _run_ffmpeg(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _extract_frames(video_path: Path, out_dir: Path, sample_rate: int) -> list[Path]:
    """Extract sampled frames from video using FFmpeg. Returns sorted list of frame paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Extract every Nth frame
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"select=not(mod(n\\,{sample_rate}))",
        "-vsync", "vfr",
        "-q:v", "2",
        str(out_dir / "frame_%06d.jpg"),
    ])
    frames = sorted(out_dir.glob("frame_*.jpg"))
    logger.info("frames_extracted", count=len(frames), sample_rate=sample_rate)
    return frames


def _try_idmvton(frame_path: str, clothing_path: str) -> Optional[str]:
    """Try IDM-VTON HF Space for one frame."""
    try:
        from gradio_client import Client, handle_file
        client = Client("yisol/IDM-VTON", verbose=False)
        result = client.predict(
            dict={"background": handle_file(frame_path), "layers": [], "composite": None},
            garm_img=handle_file(clothing_path),
            garment_des="clothing",
            is_checked=True,
            is_checked_crop=False,
            denoise_steps=30,
            seed=42,
            api_name="/tryon",
        )
        # result is typically (output_img, masked_img) tuple
        if isinstance(result, (list, tuple)):
            result = result[0]
        return str(result) if result else None
    except Exception as e:
        logger.warning("idmvton_frame_failed", error=str(e)[:120])
        return None


def _try_catvton(frame_path: str, clothing_path: str) -> Optional[str]:
    """Try CatVTON HF Space for one frame."""
    try:
        from gradio_client import Client, handle_file
        client = Client("zhengchong/CatVTON", verbose=False)
        result = client.predict(
            image=handle_file(frame_path),
            condition_image=handle_file(clothing_path),
            mask_image=None,
            num_inference_steps=50,
            guidance_scale=2.5,
            seed=42,
            show_type="result only",
            api_name="/submit_function",
        )
        if isinstance(result, (list, tuple)):
            result = result[0]
        return str(result) if result else None
    except Exception as e:
        logger.warning("catvton_frame_failed", error=str(e)[:120])
        return None


def _try_ootd(frame_path: str, clothing_path: str) -> Optional[str]:
    """Try OOTDiffusion HF Space as fallback."""
    try:
        from gradio_client import Client, handle_file
        client = Client("levihsu/OOTDiffusion", verbose=False)
        result = client.predict(
            vton_img=handle_file(frame_path),
            garm_img=handle_file(clothing_path),
            n_samples=1,
            n_steps=20,
            image_scale=2.0,
            seed=-1,
            api_name="/process_dc",
        )
        if isinstance(result, (list, tuple)):
            result = result[0]
        if isinstance(result, dict):
            result = result.get("image", "")
        return str(result) if result else None
    except Exception as e:
        logger.warning("ootd_frame_failed", error=str(e)[:120])
        return None


def _process_frame(frame_path: str, clothing_path: str) -> Optional[str]:
    """Try all providers for a single frame, return result path or None."""
    for fn in [_try_idmvton, _try_catvton, _try_ootd]:
        result = fn(frame_path, clothing_path)
        if result and Path(result).exists():
            return result
    return None


def _assemble_video(
    original_video: Path,
    processed_frames: list[tuple[int, str]],  # (original_frame_idx, processed_path)
    all_frame_paths: list[Path],
    out_dir: Path,
    output_path: Path,
    fps: float,
    has_audio: bool,
    audio_path: Optional[Path],
) -> None:
    """
    Build final video:
    - processed_frames: sampled frames after try-on
    - For non-sampled frames: copy original frame
    Assemble with FFmpeg, mux audio.
    """
    final_frames_dir = out_dir / "final_frames"
    final_frames_dir.mkdir(exist_ok=True)

    # Build mapping: frame_idx -> processed path
    processed_map = {idx: path for idx, path in processed_frames}

    # Copy all original frames first (as fallback)
    orig_frames_dir = out_dir / "orig_frames"
    orig_frames_dir.mkdir(exist_ok=True)

    # Extract ALL original frames
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", str(original_video),
        "-q:v", "2",
        str(orig_frames_dir / "frame_%06d.jpg"),
    ])
    orig_frames = sorted(orig_frames_dir.glob("frame_*.jpg"))

    # Merge: use processed where available, original elsewhere
    for i, orig_frame in enumerate(orig_frames):
        dest = final_frames_dir / f"frame_{i:06d}.jpg"
        if i in processed_map and Path(processed_map[i]).exists():
            shutil.copy2(processed_map[i], dest)
        else:
            shutil.copy2(str(orig_frame), dest)

    # Assemble frames → raw video
    raw_video = out_dir / "raw_tryon.mp4"
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(final_frames_dir / "frame_%06d.jpg"),
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        str(raw_video),
    ])

    # Mux with audio
    if has_audio and audio_path and audio_path.exists():
        _run_ffmpeg([
            "ffmpeg", "-y",
            "-i", str(raw_video),
            "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac",
            "-shortest",
            str(output_path),
        ])
    else:
        shutil.copy2(str(raw_video), str(output_path))


async def transfer_outfit(job: TryOnJob, update_progress: ProgressCallback) -> str:
    """
    Main try-on pipeline coroutine.
    Returns path to output video.
    """
    import asyncio

    job_id = job.job_id
    video_path = Path(job.video_path)
    clothing_path = job.clothing_path

    logger.info("tryon_start", job_id=job_id)

    def _run_blocking() -> str:
        job_temp_dir = settings.temp_dir / f"tryon_{job_id}"
        job_temp_dir.mkdir(parents=True, exist_ok=True)

        # ── Step 1: Probe video ──────────────────────────────────────────────
        update_progress(TryOnStatus.EXTRACTING, 5, "Video probe ho raha hai...", 0, 0)
        meta = probe_video(video_path)
        fps = meta.fps
        has_audio = meta.has_audio

        # Extract audio
        audio_path = job_temp_dir / "audio.aac"
        if has_audio:
            extract_audio(video_path, audio_path)

        # ── Step 2: Extract sampled frames ──────────────────────────────────
        update_progress(TryOnStatus.EXTRACTING, 10, "Frames extract ho rahe hain...", 0, 0)
        frames_dir = job_temp_dir / "sampled_frames"
        sampled_frames = _extract_frames(video_path, frames_dir, FRAME_SAMPLE_RATE)
        total = len(sampled_frames)

        if total == 0:
            raise ValueError("Video se koi frame extract nahi hua.")

        update_progress(TryOnStatus.PROCESSING, 15, f"{total} frames process honge...", 0, total)

        # ── Step 3: Process each sampled frame ──────────────────────────────
        processed_results: list[tuple[int, str]] = []

        for i, frame_path in enumerate(sampled_frames):
            # original frame index in full video
            orig_frame_idx = i * FRAME_SAMPLE_RATE

            pct = 15 + int((i / total) * 65)
            update_progress(
                TryOnStatus.PROCESSING,
                pct,
                f"Frame {i + 1}/{total} me clothes transfer ho raha hai...",
                i,
                total,
            )

            result = _process_frame(str(frame_path), clothing_path)
            if result:
                processed_results.append((orig_frame_idx, result))
                logger.info("frame_processed", job_id=job_id, frame=i, total=total)
            else:
                logger.warning("frame_skipped", job_id=job_id, frame=i)

        if not processed_results:
            raise RuntimeError(
                "Koi bhi frame process nahi ho paya.\n"
                "HuggingFace Spaces busy ho sakti hain — thodi der baad try karo."
            )

        # ── Step 4: Assemble final video ────────────────────────────────────
        update_progress(TryOnStatus.ASSEMBLING, 82, "Frames se video assemble ho raha hai...", total, total)

        output_path = settings.output_dir / f"{job_id}_tryon.mp4"
        settings.output_dir.mkdir(parents=True, exist_ok=True)

        _assemble_video(
            original_video=video_path,
            processed_frames=processed_results,
            all_frame_paths=sampled_frames,
            out_dir=job_temp_dir,
            output_path=output_path,
            fps=fps,
            has_audio=has_audio,
            audio_path=audio_path if has_audio else None,
        )

        # Cleanup temp
        shutil.rmtree(str(job_temp_dir), ignore_errors=True)
        logger.info("tryon_complete", job_id=job_id, output=str(output_path))
        return str(output_path)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_blocking)
    return result
