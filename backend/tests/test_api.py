"""
Backend tests.
Run with: cd backend && python -m pytest tests/ -v
"""

import asyncio
import sys
from pathlib import Path
import pytest

# Make sure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Health ────────────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["local"] is True


def test_system_info(client):
    r = client.get("/system-info")
    assert r.status_code == 200
    data = r.json()
    assert "cpu" in data
    assert "ram_gb" in data


# ── Upload validation ─────────────────────────────────────────────────────────
def test_upload_video_invalid_type(client):
    from io import BytesIO
    r = client.post(
        "/upload/video",
        files={"file": ("test.exe", BytesIO(b"fake content"), "application/octet-stream")},
    )
    assert r.status_code == 400


def test_upload_face_invalid_type(client):
    from io import BytesIO
    r = client.post(
        "/upload/face",
        files={"file": ("test.txt", BytesIO(b"not an image"), "text/plain")},
    )
    assert r.status_code == 400


# ── Job creation ──────────────────────────────────────────────────────────────
def test_job_not_found(client):
    r = client.get("/jobs/nonexistent123")
    assert r.status_code == 404


def test_job_create_missing_files(client):
    from app.core.config import settings

    r = client.post(
        "/jobs",
        json={
            "video_upload_id": str(settings.upload_dir / "nonexistent_video.mp4"),
            "face_upload_id": str(settings.upload_dir / "nonexistent_face.jpg"),
        },
    )
    assert r.status_code == 404


def test_job_create_rejects_paths_outside_upload_dir(client):
    r = client.post(
        "/jobs",
        json={
            "video_upload_id": "/tmp/nonexistent_video.mp4",
            "face_upload_id": "/tmp/nonexistent_face.jpg",
        },
    )
    assert r.status_code == 400


def test_job_create_accepts_multiple_reference_photos(client, monkeypatch):
    import sys
    from types import SimpleNamespace

    from app.core.config import settings
    from app.core import job_store
    from app.api import jobs

    async def noop_run_job(job):
        return None

    monkeypatch.setattr(jobs, "_run_job", noop_run_job)
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imread=lambda path: None))
    monkeypatch.setitem(
        sys.modules,
        "app.pipelines.face_detector",
        SimpleNamespace(
            face_detector=SimpleNamespace(
                detect_in_image=lambda image: [],
                faces_to_face_info=lambda image, faces: [],
            )
        ),
    )

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    target = settings.upload_dir / "test_multi_target.jpg"
    refs = [
        settings.upload_dir / "test_multi_ref_front.jpg",
        settings.upload_dir / "test_multi_ref_left.jpg",
        settings.upload_dir / "test_multi_ref_right.jpg",
    ]
    target.write_bytes(b"not-a-real-image")
    for ref in refs:
        ref.write_bytes(b"not-a-real-image")

    r = client.post(
        "/jobs",
        json={
            "video_upload_id": str(target),
            "face_upload_ids": [str(ref) for ref in refs],
            "target_face_index": 0,
            "quality": "balanced",
            "enhance": True,
        },
    )

    assert r.status_code == 202
    created = job_store.get_job(r.json()["job_id"])
    assert created is not None
    assert created.face_path == str(refs[0])
    assert created.face_paths == [str(ref) for ref in refs]


# ── FFmpeg ────────────────────────────────────────────────────────────────────
def test_ffmpeg_probe_invalid():
    from app.services.ffmpeg import probe_video
    with pytest.raises(Exception):
        probe_video(Path("/tmp/definitely_not_a_video.mp4"))


# ── Security utilities ────────────────────────────────────────────────────────
def test_safe_filename():
    from app.core.security import safe_filename
    assert safe_filename("../etc/passwd") == "passwd"
    assert safe_filename("my video (1).mp4") == "my_video__1_.mp4"
    assert safe_filename(".hidden") == "hidden"


def test_generate_job_id():
    from app.core.security import generate_job_id
    id1 = generate_job_id()
    id2 = generate_job_id()
    assert id1 != id2
    assert len(id1) == 32  # UUID hex
