"""
Video generation pipeline using HuggingFace Spaces (free, no GPU needed locally).

Strategy — tries providers in order until one succeeds:
  1. Wan2.1 I2V via HF Space (best quality)
  2. CogVideoX I2V via HF Space (good quality)
  3. LTX-Video via HF Space (fastest)

All providers are free public HF Spaces using ZeroGPU.
No API key required for basic usage.
"""

import time
import tempfile
import shutil
from pathlib import Path
from typing import Callable, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.models.gen_job import GenJob, GenStatus

logger = get_logger(__name__)

ProgressCallback = Callable[[GenStatus, int, str], None]


# ── HF Space Providers (tried in order) ───────────────────────────────────────

PROVIDERS = [
    {
        "name": "Wan2.1-I2V",
        "space": "Wan-AI/Wan2.1-I2V-14B-720P",
        "api_name": "/generate",
    },
    {
        "name": "CogVideoX-I2V",
        "space": "THUDM/CogVideoX-5B-I2V",
        "api_name": "/generate_video",
    },
    {
        "name": "LTX-Video",
        "space": "Lightricks/LTX-Video",
        "api_name": "/generate",
    },
]


def _check_gradio_client() -> bool:
    try:
        import gradio_client  # noqa: F401
        return True
    except ImportError:
        return False


def _try_colab(
    colab_url: str,
    image_path: str,
    prompt: str,
    duration: int,
    update: ProgressCallback,
) -> Optional[str]:
    """Call the user's free Google Colab GPU backend if provided."""
    import urllib.request
    import json
    try:
        url = colab_url.rstrip("/")
        update(GenStatus.GENERATING, 15, "Connecting to your Google Colab Free GPU...")

        # Encode image in base64
        import base64
        with open(image_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")

        payload = json.dumps({
            "image": b64_img,
            "prompt": prompt,
            "duration": duration,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{url}/generate",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Bypass-Tunnel-Reminder": "true",
                "User-Agent": "FaceFlux/1.0",
            },
        )

        update(GenStatus.GENERATING, 30, "Colab GPU: Rendering video...")
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp_content = resp.read().decode("utf-8")
            data = json.loads(resp_content)
            video_b64 = data.get("video")
            if not video_b64:
                logger.warning("colab_empty_video", resp=resp_content[:150])
                return None

            # Save temp output
            out_temp = Path(tempfile.gettempdir()) / f"colab_out_{int(time.time())}.mp4"
            with open(out_temp, "wb") as f:
                f.write(base64.b64decode(video_b64))
            return str(out_temp)

    except Exception as e:
        logger.warning("colab_gpu_failed", error=str(e), url=colab_url)
        return None


def _try_wan21(
    image_path: str,
    prompt: str,
    duration: int,
    hf_token: Optional[str],
    update: ProgressCallback,
) -> Optional[str]:
    """Try Wan2.1 Image-to-Video HF Space."""
    try:
        from gradio_client import Client, handle_file

        update(GenStatus.GENERATING, 20, "Connecting to Wan2.1...")
        client = Client("Wan-AI/Wan2.1-I2V-14B-720P", hf_token=hf_token, verbose=False)

        update(GenStatus.GENERATING, 35, "Wan2.1: Generating video with GPU...")
        result = client.predict(
            image=handle_file(image_path),
            prompt=prompt,
            num_frames=min(duration * 16, 81),
            api_name="/generate",
        )

        if isinstance(result, (list, tuple)):
            result = result[0]
        return str(result)

    except Exception as e:
        logger.warning("wan21_failed", error=str(e))
        return None


def _try_cogvideox(
    image_path: str,
    prompt: str,
    duration: int,
    hf_token: Optional[str],
    update: ProgressCallback,
) -> Optional[str]:
    """Try CogVideoX Image-to-Video HF Space."""
    try:
        from gradio_client import Client, handle_file

        update(GenStatus.GENERATING, 20, "Connecting to CogVideoX...")
        client = Client("THUDM/CogVideoX-5B-I2V", hf_token=hf_token, verbose=False)

        update(GenStatus.GENERATING, 35, "CogVideoX: Generating video...")
        result = client.predict(
            prompt=prompt,
            image_input=handle_file(image_path),
            num_inference_steps=50,
            guidance_scale=6.0,
            num_videos_per_prompt=1,
            api_name="/generate_video",
        )

        if isinstance(result, (list, tuple)):
            result = result[0]
        if hasattr(result, 'get'):
            result = result.get("video", result.get("url", ""))
        return str(result)

    except Exception as e:
        logger.warning("cogvideox_failed", error=str(e))
        return None


def _try_ltx(
    image_path: str,
    prompt: str,
    duration: int,
    hf_token: Optional[str],
    update: ProgressCallback,
) -> Optional[str]:
    """Try LTX-Video HF Space."""
    try:
        from gradio_client import Client, handle_file

        update(GenStatus.GENERATING, 20, "Connecting to LTX-Video...")
        client = Client("Lightricks/LTX-Video", hf_token=hf_token, verbose=False)

        update(GenStatus.GENERATING, 35, "LTX-Video: Generating video...")
        result = client.predict(
            image=handle_file(image_path),
            prompt=prompt,
            negative_prompt="low quality, worst quality, deformed, distorted",
            num_frames=min(duration * 24, 121),
            frame_rate=24,
            seed=42,
            api_name="/image_to_video",
        )

        if isinstance(result, (list, tuple)):
            result = result[0]
        return str(result)

    except Exception as e:
        logger.warning("ltx_failed", error=str(e))
        return None


async def generate_video(job: GenJob, update_progress: ProgressCallback) -> str:
    """
    Main generation coroutine.
    Tries each HF Space provider in order until one succeeds.
    Returns path to output video (mp4).
    """
    import asyncio

    job_id = job.job_id
    image_path = job.image_path
    prompt = job.prompt
    duration = job.duration

    logger.info("gen_pipeline_start", job_id=job_id, prompt=prompt[:80])

    # Check gradio_client installed
    if not _check_gradio_client():
        raise RuntimeError(
            "gradio_client not installed.\n"
            "Run: pip install gradio_client\n"
            "Then restart the backend."
        )

    def _run_blocking() -> str:
        update_progress(GenStatus.GENERATING, 10, "Finding best available provider...")

        result_path = None
        used_provider = None

        # 1. Mode: Google Colab GPU
        if job.provider_mode == "colab":
            if not job.colab_url:
                raise RuntimeError(
                    "Google Colab URL configure nahi hai.\n"
                    ".env file mein 'COLAB_GPU_URL=https://xxxx.loca.lt' add karo\n"
                    "aur Colab notebook ko Run karo."
                )

            logger.info("trying_colab_gpu", job_id=job_id, url=job.colab_url)
            result_path = _try_colab(job.colab_url, image_path, prompt, duration, update_progress)
            if result_path and Path(result_path).exists():
                used_provider = "Google Colab (Tesla T4 GPU)"
            else:
                raise RuntimeError(
                    "Google Colab server se connect nahi ho paya.\n"
                    "Check karo ki Colab tab mein Cell 2 chal raha hai aur URL sahi hai."
                )

        # 2. Mode: Hugging Face Cloud
        else:
            hf_providers = [
                ("Wan2.1-I2V", _try_wan21),
                ("CogVideoX-I2V", _try_cogvideox),
                ("LTX-Video", _try_ltx),
            ]

            for name, fn in hf_providers:
                logger.info("trying_provider", job_id=job_id, provider=name)
                try:
                    result_path = fn(image_path, prompt, duration, job.hf_token, update_progress)
                    if result_path and Path(result_path).exists():
                        used_provider = name
                        logger.info("provider_succeeded", job_id=job_id, provider=name)
                        break
                    else:
                        logger.warning("provider_no_output", job_id=job_id, provider=name)
                except Exception as e:
                    logger.warning("provider_error", job_id=job_id, provider=name, error=str(e))

            if not result_path or not Path(result_path).exists():
                raise RuntimeError(
                    "Hugging Face Spaces abhi busy hain ya queue full hai.\n"
                    "Google Colab Mode use karo jo 100% Free aur Fast chalta hai!"
                )

        # Copy result to our output directory
        update_progress(GenStatus.GENERATING, 90, f"Saving video ({used_provider})...")
        output_path = settings.output_dir / f"{job_id}_generated.mp4"
        settings.output_dir.mkdir(parents=True, exist_ok=True)

        src = Path(result_path)
        if src.suffix.lower() != ".mp4":
            # Convert to mp4 if needed
            try:
                import subprocess
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(src), "-c:v", "libx264",
                     "-crf", "18", "-preset", "medium", str(output_path)],
                    capture_output=True, check=True
                )
            except Exception:
                shutil.copy2(str(src), str(output_path))
        else:
            shutil.copy2(str(src), str(output_path))

        logger.info("gen_complete", job_id=job_id, output=str(output_path), provider=used_provider)
        return str(output_path)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_blocking)
    return result
