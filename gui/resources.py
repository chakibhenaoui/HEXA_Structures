"""Helpers de resolution de ressources pour mode source et PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path


def app_resource_path(*parts: str) -> str:
    """Retourne le chemin absolu d'une ressource embarquee.

    En mode source, les ressources sont lues depuis la racine du projet.
    En mode PyInstaller, elles sont lues depuis ``sys._MEIPASS``.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent.parent
    return str(base_path.joinpath(*parts))
