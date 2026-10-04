"""
SQLite-backed job store — Stage 3: Reliability upgrade.

Replaces the in-memory dict store with SQLite so jobs survive server restarts.
Uses Python's built-in sqlite3 (zero extra dependencies).

Design decisions:
  - SQLite is perfect for this use case: single-writer, low concurrency, local
  - Jobs serialized as JSON blobs (simple, schema-flexible)
  - Cancellation state kept in-memory (ephemeral — intentional, cancels clear on restart)
  - Thread-safe: uses threading.Lock around all writes
  - Backwards-compatible: same public API as original in-memory store
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.core.security import generate_job_id
from app.models.job import Job, JobStatus

import asyncio

logger = get_logger(__name__)

# ── DB setup ──────────────────────────────────────────────────────────────────

def _db_path() -> Path:
    db_dir = settings.log_dir
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "jobs.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """Create the jobs table if it doesn't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id      TEXT PRIMARY KEY,
                data        TEXT NOT NULL,
                status      TEXT NOT NULL,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at)")
        conn.commit()
    logger.info("job_store_initialized", db=str(_db_path()))


# ── Serialization ─────────────────────────────────────────────────────────────

def _job_to_dict(job: Job) -> dict:
    return job.model_dump()


def _job_from_row(row) -> Optional[Job]:
    try:
        data = json.loads(row["data"])
        return Job(**data)
    except Exception as e:
        logger.error("job_deserialize_failed", error=str(e))
        return None


# ── State ─────────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_semaphore: Optional[asyncio.Semaphore] = None
_cancelled_jobs: set = set()   # ephemeral — intentionally not persisted

# Initialize DB on module import
_init_db()


# ── Public API (same interface as original in-memory store) ───────────────────

def get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
    return _semaphore


def create_job(
    video_path: str,
    face_path: str,
    quality: str,
    enhance: bool,
    target_face_index: int = 0,
    face_paths: list = None,
) -> Job:
    job_id = generate_job_id()
    all_face_paths = face_paths if face_paths else ([face_path] if face_path else [])
    job = Job(
        job_id=job_id,
        video_path=video_path,
        face_path=face_path,
        face_paths=all_face_paths,
        quality=quality,
        enhance=enhance,
        target_face_index=target_face_index,
        status=JobStatus.QUEUED,
        created_at=time.time(),
    )
    _save_job(job)
    logger.info("job_created", job_id=job_id, quality=quality, faces=len(all_face_paths))
    return job


def _save_job(job: Job) -> None:
    """Insert or replace job in SQLite."""
    with _lock:
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs (job_id, data, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    json.dumps(_job_to_dict(job)),
                    job.status.value,
                    job.created_at,
                    time.time(),
                ),
            )
            conn.commit()


def get_job(job_id: str) -> Optional[Job]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return _job_from_row(row)


def update_job(job_id: str, **kwargs) -> Optional[Job]:
    job = get_job(job_id)
    if job is None:
        return None
    for key, value in kwargs.items():
        setattr(job, key, value)
    _save_job(job)
    return job


def delete_job(job_id: str) -> bool:
    _cancelled_jobs.discard(job_id)
    with _lock:
        with _get_conn() as conn:
            cur = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            conn.commit()
            return cur.rowcount > 0


def cancel_job(job_id: str) -> bool:
    job = get_job(job_id)
    if job is None:
        return False
    _cancelled_jobs.add(job_id)
    return True


def is_cancelled(job_id: str) -> bool:
    return job_id in _cancelled_jobs


def list_jobs() -> List[Job]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC"
        ).fetchall()
    jobs = []
    for row in rows:
        job = _job_from_row(row)
        if job:
            jobs.append(job)
    return jobs


def count_active_jobs() -> int:
    """Count jobs currently in progress (not terminal states)."""
    active = {JobStatus.QUEUED, JobStatus.ANALYZING, JobStatus.DETECTING,
              JobStatus.TRACKING, JobStatus.SWAPPING, JobStatus.ENHANCING,
              JobStatus.ENCODING}
    with _get_conn() as conn:
        placeholders = ",".join("?" * len(active))
        row = conn.execute(
            f"SELECT COUNT(*) FROM jobs WHERE status IN ({placeholders})",
            [s.value for s in active],
        ).fetchone()
    return row[0] if row else 0


# ── Cleanup ───────────────────────────────────────────────────────────────────

def cleanup_old_jobs(
    max_age_hours: float = 48.0,
    delete_files: bool = True,
) -> int:
    """
    Delete completed/failed jobs older than max_age_hours.
    Optionally deletes associated output files.
    Returns number of jobs deleted.
    """
    cutoff = time.time() - (max_age_hours * 3600)
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE created_at < ? AND status IN ({})".format(
                ",".join("?" * len(terminal))
            ),
            [cutoff] + [s.value for s in terminal],
        ).fetchall()

    deleted = 0
    for row in rows:
        job = _job_from_row(row)
        if job is None:
            continue

        if delete_files and job.output_path:
            try:
                out = Path(job.output_path)
                if out.exists():
                    out.unlink()
                    logger.info("output_file_deleted", job_id=job.job_id, path=str(out))
            except Exception as e:
                logger.warning("output_delete_failed", job_id=job.job_id, error=str(e))

        delete_job(job.job_id)
        deleted += 1

    if deleted > 0:
        logger.info("jobs_cleaned_up", count=deleted)
    return deleted


def cleanup_temp_files(max_age_hours: float = 24.0) -> int:
    """
    Delete temp directories in data/temp/ older than max_age_hours.
    Each job has its own subdirectory — safe to delete after completion.
    Returns number of directories deleted.
    """
    temp_root = settings.temp_dir
    if not temp_root.exists():
        return 0

    cutoff = time.time() - (max_age_hours * 3600)
    deleted = 0

    for item in temp_root.iterdir():
        if item.is_dir():
            try:
                mtime = item.stat().st_mtime
                if mtime < cutoff:
                    import shutil
                    shutil.rmtree(item, ignore_errors=True)
                    deleted += 1
            except Exception as e:
                logger.warning("temp_cleanup_failed", path=str(item), error=str(e))

    if deleted > 0:
        logger.info("temp_dirs_cleaned", count=deleted)
    return deleted
