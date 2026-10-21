"""
FFmpeg/ffprobe video metadata extraction and video reconstruction.
All subprocess calls use argument lists — never shell=True with user data.

Platform-aware encoding:
  - macOS arm64:  hevc_videotoolbox (Apple hardware HEVC — ~40% smaller than H.264)
                  Falls back to h264_videotoolbox if explicitly requested.
                  Adds -tag:v hvc1 for QuickTime Player compatibility.
  - Linux/Win:    libx264 (software, existing behaviour)
"""

import asyncio
import json
import platform
import subprocess
from pathlib import Path
from typing import Optional

from app.core.logger import get_logger
from app.models.job import VideoMeta

logger = get_logger(__name__)


def _is_apple_silicon() -> bool:
    """True when running natively on Apple Silicon (arm64 macOS)."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


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


def _build_video_encode_args(
    codec: str,
    crf: int,
    preset: str,
    vt_quality: str = "60",
    vt_bitrate: Optional[str] = None,
) -> list[str]:
    """
    Build FFmpeg video codec arguments.

    Apple Silicon (VideoToolbox):
      - h264_videotoolbox uses VBR with quality scale, not CRF.
      - -q:v 60 ≈ CRF 18 in visual quality (range 1-100, higher=better).
      - -allow_sw 1 lets VideoToolbox fall back to SW for edge cases.
      - Optional -b:v cap prevents bitrate spikes on complex scenes.

    Linux / Windows (libx264):
      - Standard CRF + preset control, unchanged from original.
    """
    if _is_apple_silicon() and codec in ("h264_videotoolbox", "hevc_videotoolbox", "auto"):
        # Resolve codec: "auto" on Mac → hevc_videotoolbox (smaller files, same quality)
        vt_codec = "hevc_videotoolbox" if codec in ("hevc_videotoolbox", "auto") else "h264_videotoolbox"
        args = [
            "-c:v", vt_codec,
            "-q:v", vt_quality,       # quality scale (60 ≈ high quality)
            "-allow_sw", "1",          # software fallback for unsupported profiles
            "-pix_fmt", "yuv420p",
        ]
        # hvc1 tag required for QuickTime Player / iOS / macOS Photos to open HEVC files.
        # Without it, HEVC plays in VLC but QuickTime shows "incompatible file" error.
        if vt_codec == "hevc_videotoolbox":
            args += ["-tag:v", "hvc1"]
        if vt_bitrate:
            args += ["-b:v", vt_bitrate]
        logger.info("videotoolbox_encode", codec=vt_codec, quality=vt_quality)
        return args
    else:
        # libx264 / libx265 path (Linux, Windows, or explicit override)
        sw_codec = codec if codec not in ("h264_videotoolbox", "hevc_videotoolbox", "auto") else "libx264"
        args = [
            "-c:v", sw_codec,
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", "yuv420p",
        ]
        logger.info("software_encode", codec=sw_codec, crf=crf, preset=preset)
        return args


def _build_temporal_nr_args(quality: str) -> list[str]:
    """
    Free FFmpeg temporal noise reduction — replicates DaVinci Resolve Studio's
    Temporal NR + Deflicker features at zero cost.

    Why this matters for face swap:
      - Each swapped frame is processed independently → per-frame variance in
        skin tone, brightness, and edge sharpness causes visible flicker.
      - Temporal filters compare adjacent frames and smooth out these variations.
      - hqdn3d: High-Quality 3D Denoise (spatial + temporal).
      - atadenoise: Adaptive Temporal Denoise — handles fast head motion better.
      - unsharp: Re-sharpens skin detail softened by denoise.

    Tuning:
      hqdn3d=luma_spatial:chroma_spatial:luma_temporal:chroma_temporal
        low spatial values → preserve face texture sharpness
        higher temporal values → reduce frame-to-frame flicker

    fast:     Skip TNR — prioritize processing speed
    balanced: Light TNR — reduce noticeable flicker, keep texture
    high:     Strong TNR — maximum smoothness, slight softening compensated by unsharp
    """
    filters: dict[str, list[str]] = {
        "fast": [],   # No TNR in fast mode — keep it quick
        "balanced": [
            "-vf",
            "atadenoise=0s=0.02:0t=0.03,hqdn3d=2:1.5:4:3,unsharp=5:5:0.3:5:5:0.0",
        ],
        "high": [
            "-vf",
            "atadenoise=0s=0.03:0t=0.05,hqdn3d=3:2:6:5,unsharp=5:5:0.5:5:5:0.0",
        ],
    }
    result = filters.get(quality, filters["balanced"])
    if result:
        logger.info("temporal_nr_enabled", quality=quality, filter=result[1])
    return result


class RawVideoEncoder:
    """Stream processed BGR frames directly into the final video encoder.

    This avoids a large intermediate file, which is important for 5–10 minute
    720p jobs on a 512GB SSD. On Apple Silicon the final encode uses
    VideoToolbox; other platforms fall back to the configured software codec.
    """

    def __init__(
        self,
        output_path: Path,
        width: int,
        height: int,
        fps: float,
        audio_path: Optional[Path] = None,
        crf: int = 18,
        preset: str = "medium",
        codec: str = "libx264",
        vt_quality: str = "60",
        vt_bitrate: Optional[str] = None,
        quality: str = "balanced",
    ):
        video_args = _build_video_encode_args(
            codec, crf, preset, vt_quality, vt_bitrate
        )
        tnr_args = _build_temporal_nr_args(quality)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        ]
        has_audio = audio_path and audio_path.exists() and audio_path.stat().st_size > 0
        if has_audio:
            cmd += ["-i", str(audio_path)]
        cmd += [
            *tnr_args,
            *video_args,
        ]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += ["-movflags", "+faststart", str(output_path)]

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def write(self, frame) -> None:
        if self.proc.stdin is None:
            raise RuntimeError("FFmpeg video encoder is not available")
        try:
            self.proc.stdin.write(frame.tobytes())
        except BrokenPipeError as exc:
            details = self.proc.stderr.read().decode(errors="replace") if self.proc.stderr else ""
            raise RuntimeError(f"FFmpeg video encoder stopped: {details[-500:]}") from exc

    def release(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        rc = self.proc.wait(timeout=600)
        details = self.proc.stderr.read().decode(errors="replace") if self.proc.stderr else ""
        if rc != 0:
            raise RuntimeError(f"FFmpeg streaming encode failed: {details[-500:]}")



def mux_audio_video(
    frames_video: Path,
    audio_path: Optional[Path],
    output_path: Path,
    fps: float,
    crf: int = 18,
    preset: str = "medium",
    codec: str = "libx264",
    vt_quality: str = "60",
    vt_bitrate: Optional[str] = None,
    quality: str = "balanced",
) -> None:
    """
    Combine processed frames video with original audio into final output.

    Auto-selects VideoToolbox on Apple Silicon for hardware-accelerated encoding.
    Applies free FFmpeg temporal noise reduction (hqdn3d + atadenoise + unsharp)
    to reduce face-swap flicker — replicates DaVinci Resolve Studio TNR at zero cost.

    quality: "fast" | "balanced" | "high"
      fast     → No TNR applied (pure speed mode)
      balanced → Light TNR — reduces visible flicker, preserves skin texture
      high     → Strong TNR + unsharp mask — maximum temporal smoothness
    """
    video_args = _build_video_encode_args(codec, crf, preset, vt_quality, vt_bitrate)
    tnr_args   = _build_temporal_nr_args(quality)

    if audio_path and audio_path.exists() and audio_path.stat().st_size > 0:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(frames_video),
            "-i", str(audio_path),
            *tnr_args,                 # temporal NR filter (empty list = no-op in fast mode)
            *video_args,
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
            *tnr_args,
            *video_args,
            "-movflags", "+faststart",
            str(output_path),
        ]

    logger.info("mux_start", output=str(output_path), quality=quality, tnr=bool(tnr_args))
    result = _run(cmd, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mux failed: {result.stderr[-500:]}")
    logger.info("mux_complete", output=str(output_path))


def frames_to_video(
    frames_dir: Path,
    output_path: Path,
    fps: float,
    pattern: str = "frame_%06d.jpg",
    crf: int = 18,
    preset: str = "medium",
    codec: str = "libx264",
    vt_quality: str = "60",
    vt_bitrate: Optional[str] = None,
) -> None:
    """Encode a directory of frame images into a video (no audio)."""
    video_args = _build_video_encode_args(codec, crf, preset, vt_quality, vt_bitrate)
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / pattern),
        *video_args,
        str(output_path),
    ]
    result = _run(cmd, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg encode failed: {result.stderr[-500:]}")
