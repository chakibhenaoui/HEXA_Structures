"""Fixtures pytest locales au projet.

On remplace ici l'usage du plugin interne ``tmpdir`` de pytest, qui pose
des problemes de permissions/cleanup sur cet environnement Windows.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path() -> Path:
    """Cree un repertoire temporaire local au workspace pour un test.

    Cette fixture fournit l'API minimale attendue par les tests actuels
    (un ``Path`` écrivable) sans dépendre du plugin ``tmpdir`` de pytest.
    """
    base_dir = Path(__file__).resolve().parent.parent / ".tmp"
    base_dir.mkdir(exist_ok=True)

    path = base_dir / f"pytest-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
