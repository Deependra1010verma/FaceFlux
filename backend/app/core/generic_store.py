"""
Generic SQLite-backed store for Generate and TryOn jobs.

Uses the same jobs.db file as the main job store but with separate tables,
so all job history survives server restarts.

Design:
  - Generic: works with any Pydantic model that has job_id, status, created_at fields
  - Thread-safe via threading.Lock
  - JSON blob storage (same pattern as main job_store)
  - Zero extra dependencies — pure Python sqlite3
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Generic, List, Optional, Set, Type, TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

_lock = threading.Lock()


def _db_path() -> Path:
    db_dir = settings.log_dir
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "jobs.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class GenericJobStore(Generic[T]):
    """
    SQLite-backed store for a single job type.
    Drop-in replacement for Dict[str, T] + Set[str] cancellation pattern.
    """

    def __init__(self, table_name: str, model_cls: Type[T]) -> None:
        self._table = table_name
        self._model_cls = model_cls
        self._cancelled: Set[str] = set()  # ephemeral — intentional
        self._ensure_table()

    def _ensure_table(self) -> None:
        with _lock:
            with _get_conn() as conn:
                conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._table} (
                        job_id      TEXT PRIMARY KEY,
                        data        TEXT NOT NULL,
                        status      TEXT NOT NULL,
                        created_at  REAL NOT NULL,
                        updated_at  REAL NOT NULL
                    )
                """)
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{self._table}_status "
                    f"ON {self._table}(status)"
                )
                conn.commit()
        logger.info("generic_store_initialized", table=self._table)

    # ── Write ─────────────────────────────────────────────────────────────────

    def save(self, job: T) -> None:
        data = job.model_dump_json()
        status = str(getattr(job, "status", "UNKNOWN"))
        if hasattr(status, "value"):
            status = status.value
        created_at = float(getattr(job, "created_at", time.time()))
        job_id = str(job.job_id)  # type: ignore[attr-defined]

        with _lock:
            with _get_conn() as conn:
                conn.execute(
                    f"INSERT OR REPLACE INTO {self._table} "
                    "(job_id, data, status, created_at, updated_at) VALUES (?,?,?,?,?)",
                    (job_id, data, status, created_at, time.time()),
                )
                conn.commit()

    def update(self, job_id: str, **kwargs) -> Optional[T]:
        job = self.get(job_id)
        if job is None:
            return None
        for k, v in kwargs.items():
            setattr(job, k, v)
        self.save(job)
        return job

    def delete(self, job_id: str) -> bool:
        with _lock:
            with _get_conn() as conn:
                rows = conn.execute(
                    f"DELETE FROM {self._table} WHERE job_id = ?", (job_id,)
                ).rowcount
                conn.commit()
        return rows > 0

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, job_id: str) -> Optional[T]:
        with _get_conn() as conn:
            row = conn.execute(
                f"SELECT data FROM {self._table} WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return self._model_cls.model_validate_json(row["data"])
        except Exception as e:
            logger.error("generic_store_deserialize_failed", table=self._table, error=str(e))
            return None

    def list_all(self) -> List[T]:
        with _get_conn() as conn:
            rows = conn.execute(
                f"SELECT data FROM {self._table} ORDER BY created_at DESC"
            ).fetchall()
        results = []
        for row in rows:
            try:
                results.append(self._model_cls.model_validate_json(row["data"]))
            except Exception:
                pass
        return results

    def exists(self, job_id: str) -> bool:
        with _get_conn() as conn:
            row = conn.execute(
                f"SELECT 1 FROM {self._table} WHERE job_id = ?", (job_id,)
            ).fetchone()
        return row is not None

    # ── Cancellation (in-memory, ephemeral) ───────────────────────────────────

    def mark_cancelled(self, job_id: str) -> None:
        self._cancelled.add(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancelled

    def unmark_cancelled(self, job_id: str) -> None:
        self._cancelled.discard(job_id)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup_old(self, max_age_hours: float = 48.0, delete_files: bool = True) -> int:
        """Delete completed/failed jobs older than max_age_hours."""
        cutoff = time.time() - (max_age_hours * 3600)
        terminal_statuses = {"COMPLETED", "FAILED", "CANCELLED"}

        with _get_conn() as conn:
            rows = conn.execute(
                f"SELECT job_id, data FROM {self._table} WHERE created_at < ?",
                (cutoff,),
            ).fetchall()

        deleted = 0
        for row in rows:
            try:
                job = self._model_cls.model_validate_json(row["data"])
                status_val = str(getattr(job, "status", ""))
                if hasattr(status_val, "value"):
                    status_val = status_val.value
                if status_val not in terminal_statuses:
                    continue

                # Optionally delete output file
                if delete_files:
                    out = getattr(job, "output_path", None)
                    if out:
                        try:
                            p = Path(out)
                            if p.exists():
                                p.unlink()
                        except Exception:
                            pass

                self.delete(row["job_id"])
                deleted += 1
            except Exception:
                pass

        if deleted > 0:
            logger.info("generic_store_cleaned", table=self._table, deleted=deleted)
        return deleted
