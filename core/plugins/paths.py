"""Default local plugin locations."""

from __future__ import annotations

import os
from pathlib import Path


def default_plugin_roots(
    app_name: str = "HEXA Structures",
) -> tuple[Path, ...]:
    """Return default local plugin roots without creating directories."""
    roots: list[Path] = []

    env_paths = os.environ.get("HEXA_STRUCTURES_PLUGIN_PATH", "")
    for raw_path in env_paths.split(os.pathsep):
        if raw_path.strip():
            roots.append(Path(raw_path).expanduser())

    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / app_name / "plugins")
    else:
        roots.append(Path.home() / ".hexa_structures" / "plugins")

    return tuple(roots)
