"""Plugin loader contracts and safe default implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.plugins.manifest import PluginManifest


@dataclass(frozen=True)
class PluginLoadResult:
    """Result returned by a plugin loader."""

    plugin_id: str
    kind: str
    load_state: str
    loaded: bool = False
    plugin: Any | None = None
    error: str | None = None

    @classmethod
    def manifest_only(
        cls,
        manifest: PluginManifest,
        message: str = "External plugin loading is not enabled yet.",
    ) -> "PluginLoadResult":
        """Return a safe non-loaded result for a discovered manifest."""
        return cls(
            plugin_id=manifest.plugin_id,
            kind=manifest.kind,
            load_state="manifest_only",
            loaded=False,
            plugin=None,
            error=message,
        )


class ManifestOnlyPluginLoader:
    """Safe default loader that never imports or executes external code."""

    def can_load(self, manifest: PluginManifest) -> bool:
        """Return False because manifest discovery is metadata-only for now."""
        return False

    def load(self, manifest: PluginManifest) -> PluginLoadResult:
        """Return a manifest-only result without executing plugin code."""
        return PluginLoadResult.manifest_only(manifest)
