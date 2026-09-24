"""
Secure filename sanitization and path traversal prevention.
"""

import re
import uuid
from pathlib import Path


_SAFE_PATTERN = re.compile(r"[^\w.\-]")


def safe_filename(original: str) -> str:
    """Return a sanitized version of the filename."""
    name = Path(original).name
    name = _SAFE_PATTERN.sub("_", name)
    # Prevent leading dots
    name = name.lstrip(".")
    if not name:
        name = "file"
    return name


def unique_path(directory: Path, original_name: str) -> Path:
    """Generate a unique, safe file path inside directory."""
    stem = Path(safe_filename(original_name)).stem[:64]
    suffix = Path(original_name).suffix.lower()
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{unique_id}_{stem}{suffix}"
    return directory / filename


def generate_job_id() -> str:
    return uuid.uuid4().hex
