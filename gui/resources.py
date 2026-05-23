"""Resource resolution helpers for source and PyInstaller modes."""

from __future__ import annotations

import sys
from pathlib import Path


def app_resource_path(*parts: str) -> str:
    """Handle app resource path."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent.parent
    return str(base_path.joinpath(*parts))
