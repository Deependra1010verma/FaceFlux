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
    r = client.post(
        "/jobs",
        json={
            "video_upload_id": "/tmp/nonexistent_video.mp4",
            "face_upload_id": "/tmp/nonexistent_face.jpg",
        },
    )
    assert r.status_code == 404


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
