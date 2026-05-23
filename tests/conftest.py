"""Project-local pytest fixtures."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path() -> Path:
    """Handle tmp path."""
    base_dir = Path(__file__).resolve().parent.parent / ".tmp"
    base_dir.mkdir(exist_ok=True)

    path = base_dir / f"pytest-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
