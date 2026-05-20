"""
Helpers for optional third-party modules kept outside the PyInstaller bundle.

HEXA Structures does not redistribute every optional solver. In a frozen build,
Python only sees the packaged search paths, so externally installed packages
such as OpenSeesPy need a controlled discovery pass before import.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
import importlib
import importlib.util
import os
from pathlib import Path
import site
import sys
import sysconfig


_EXTERNAL_SITE_PATHS_ADDED: set[str] = set()


def ensure_external_module_search_paths(*module_names: str) -> bool:
    """Expose compatible external site-packages folders for optional modules."""
    requested = tuple(name for name in module_names if name)
    if not requested:
        return False
    if _has_any_module_on_current_path(requested):
        return True

    added = False
    for candidate in external_site_package_candidates():
        if not _candidate_has_any_module(candidate, requested):
            continue
        candidate_text = str(candidate)
        if candidate_text not in sys.path:
            sys.path.append(candidate_text)
            added = True
        _EXTERNAL_SITE_PATHS_ADDED.add(candidate_text)

    if added:
        importlib.invalidate_caches()
    return _has_any_module_on_current_path(requested)


def external_site_package_candidates() -> tuple[Path, ...]:
    """Return existing site-packages candidates outside the bundled app."""
    candidates: list[Path] = []
    candidates.extend(_env_site_packages())
    candidates.extend(_site_module_paths())
    candidates.extend(_sysconfig_paths())
    candidates.extend(_windows_python_paths())
    candidates.extend(_environment_python_paths())
    candidates.extend(_project_virtualenv_paths())
    return tuple(_dedupe_existing_paths(candidates))


def _has_any_module_on_current_path(module_names: Iterable[str]) -> bool:
    return any(importlib.util.find_spec(name) is not None for name in module_names)


def _candidate_has_any_module(candidate: Path, module_names: Iterable[str]) -> bool:
    for module_name in module_names:
        root_name = module_name.split(".", 1)[0]
        if (candidate / root_name).exists() or (candidate / f"{root_name}.py").exists():
            return True
        if any(candidate.glob(f"{root_name}-*.dist-info")):
            return True
        if any(candidate.glob(f"{root_name}-*.egg-info")):
            return True
    return False


def _env_site_packages() -> Iterator[Path]:
    configured = os.environ.get("HEXA_PYTHON_SITE_PACKAGES", "")
    for raw_path in configured.split(os.pathsep):
        if raw_path.strip():
            yield Path(raw_path.strip())


def _site_module_paths() -> Iterator[Path]:
    try:
        user_site = site.getusersitepackages()
    except Exception:
        user_site = None
    if isinstance(user_site, str):
        yield Path(user_site)
    elif user_site:
        for path in user_site:
            yield Path(path)

    try:
        site_packages = site.getsitepackages()
    except Exception:
        site_packages = []
    for path in site_packages:
        yield Path(path)


def _sysconfig_paths() -> Iterator[Path]:
    try:
        paths = sysconfig.get_paths()
    except Exception:
        return
    for key in ("purelib", "platlib"):
        path = paths.get(key)
        if path:
            yield Path(path)


def _windows_python_paths() -> Iterator[Path]:
    version_tag = f"Python{sys.version_info.major}{sys.version_info.minor}"
    local_appdata = os.environ.get("LOCALAPPDATA")
    appdata = os.environ.get("APPDATA")

    if appdata:
        yield Path(appdata) / "Python" / version_tag / "site-packages"

    if local_appdata:
        local_root = Path(local_appdata)
        yield local_root / "Programs" / "Python" / version_tag / "Lib" / "site-packages"
        packages_root = local_root / "Packages"
        if packages_root.exists():
            pattern = f"PythonSoftwareFoundation.Python.{sys.version_info.major}.{sys.version_info.minor}*"
            for package_dir in packages_root.glob(pattern):
                yield (
                    package_dir
                    / "LocalCache"
                    / "local-packages"
                    / version_tag
                    / "site-packages"
                )


def _environment_python_paths() -> Iterator[Path]:
    for env_name in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        root = os.environ.get(env_name)
        if not root:
            continue
        yield Path(root) / "Lib" / "site-packages"
        yield Path(root) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"


def _project_virtualenv_paths() -> Iterator[Path]:
    roots = [Path.cwd()]
    try:
        roots.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass

    for root in roots:
        for candidate_root in _with_limited_parents(root, max_depth=5):
            for venv_name in (".venv", "venv"):
                venv_root = candidate_root / venv_name
                yield venv_root / "Lib" / "site-packages"
                yield (
                    venv_root
                    / "lib"
                    / f"python{sys.version_info.major}.{sys.version_info.minor}"
                    / "site-packages"
                )


def _with_limited_parents(path: Path, max_depth: int) -> Iterator[Path]:
    yield path
    for index, parent in enumerate(path.parents):
        if index >= max_depth:
            break
        yield parent


def _dedupe_existing_paths(paths: Iterable[Path]) -> Iterator[Path]:
    seen: set[str] = set()
    for path in paths:
        try:
            if not path.exists() or not path.is_dir():
                continue
            normalized = str(path.resolve())
        except OSError:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        yield Path(normalized)
