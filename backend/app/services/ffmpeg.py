"""
FFmpeg/ffprobe video metadata extraction and video reconstruction.
All subprocess calls use argument lists — never shell=True with user data.
"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Optional

from app.core.logger import get_logger
from app.models.job import VideoMeta

logger = get_logger(__name__)


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a subprocess safely (no shell=True)."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def probe_video(video_path: Path) -> VideoMeta:
    """Use ffprobe to extract video metadata."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(video_path),
    ]
    result = _run(cmd, timeout=30)
    if result.returncode != 0:
        raise ValueError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video_stream is None:
        raise ValueError("No video stream found in file.")

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    codec = video_stream.get("codec_name", "unknown")

    # FPS
    fps_str = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate", "25/1")
    num, den = fps_str.split("/")
    fps = round(float(num) / float(den), 3) if float(den) > 0 else 25.0

    # Duration
    duration = float(video_stream.get("duration") or fmt.get("duration", 0))

    # Frame count
    nb_frames = video_stream.get("nb_frames")
    frame_count = int(nb_frames) if nb_frames and nb_frames != "N/A" else None
    if frame_count is None and duration > 0 and fps > 0:
        frame_count = int(duration * fps)

    return VideoMeta(
        width=width,
        height=height,
        fps=fps,
        duration=round(duration, 3),
        has_audio=audio_stream is not None,
        codec=codec,
        frame_count=frame_count,
    )


def extract_audio(video_path: Path, audio_path: Path) -> bool:
    """Extract audio track from video. Returns True if audio exists."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "copy",
        str(audio_path),
    ]
    result = _run(cmd, timeout=120)
    if result.returncode != 0:
        logger.warning("audio_extract_failed", stderr=result.stderr[:300])
        return False
    return audio_path.exists() and audio_path.stat().st_size > 0


def mux_audio_video(
    frames_video: Path,
    audio_path: Optional[Path],
    output_path: Path,
    fps: float,
    crf: int = 18,
    preset: str = "medium",
    codec: str = "libx264",
) -> None:
    """Combine processed frames video with original audio into final output."""
    if audio_path and audio_path.exists() and audio_path.stat().st_size > 0:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(frames_video),
            "-i", str(audio_path),
            "-c:v", codec,
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(frames_video),
            "-c:v", codec,
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]
    result = _run(cmd, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mux failed: {result.stderr[-500:]}")


def frames_to_video(
    frames_dir: Path,
    output_path: Path,
    fps: float,
    pattern: str = "frame_%06d.jpg",
    crf: int = 18,
    preset: str = "medium",
    codec: str = "libx264",
) -> None:
    """Encode a directory of frame images into a video (no audio)."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / pattern),
        "-c:v", codec,
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = _run(cmd, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg encode failed: {result.stderr[-500:]}")
