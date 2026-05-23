"""Local plugin manifest discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.plugins.manifest import PluginManifest
from core.plugins.registry import PluginRegistry


MANIFEST_FILENAMES: tuple[str, ...] = (
    "hexa-plugin.json",
    "plugin.json",
)


@dataclass(frozen=True)
class PluginDiscoveryError:
    """Non-fatal error encountered while reading a plugin manifest."""

    path: Path
    message: str


@dataclass(frozen=True)
class PluginDiscoveryResult:
    """Result of scanning local plugin manifest roots."""

    manifests: tuple[PluginManifest, ...] = field(default_factory=tuple)
    errors: tuple[PluginDiscoveryError, ...] = field(default_factory=tuple)


def discover_plugin_manifests(
    roots: tuple[str | Path, ...] | list[str | Path],
    *,
    strict: bool = False,
) -> PluginDiscoveryResult:
    """Discover plugin manifests under local roots.

    Discovery is metadata-only: it never imports or executes plugin code.
    """
    manifests: list[PluginManifest] = []
    errors: list[PluginDiscoveryError] = []

    for root in roots:
        for manifest_path in _candidate_manifest_paths(Path(root)):
            try:
                manifests.append(PluginManifest.from_file(manifest_path))
            except ValueError as exc:
                if strict:
                    raise
                errors.append(
                    PluginDiscoveryError(
                        path=manifest_path,
                        message=str(exc),
                    )
                )

    return PluginDiscoveryResult(
        manifests=tuple(manifests),
        errors=tuple(errors),
    )


def build_manifest_registry(
    manifests: tuple[PluginManifest, ...] | list[PluginManifest],
) -> PluginRegistry[PluginManifest]:
    """Build a generic plugin registry from discovered manifests."""
    return PluginRegistry(tuple(manifests))


def _candidate_manifest_paths(root: Path) -> tuple[Path, ...]:
    if root.is_file():
        return (root,) if root.name in MANIFEST_FILENAMES else ()
    if not root.exists() or not root.is_dir():
        return ()

    candidates: list[Path] = []
    for filename in MANIFEST_FILENAMES:
        direct = root / filename
        if direct.is_file():
            candidates.append(direct)

    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        for filename in MANIFEST_FILENAMES:
            manifest = child / filename
            if manifest.is_file():
                candidates.append(manifest)
                break

    return tuple(candidates)
