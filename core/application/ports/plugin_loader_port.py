"""Port for loading plugin manifests into runtime plugins."""

from __future__ import annotations

from typing import Protocol

from core.plugins import PluginLoadResult, PluginManifest


class PluginLoaderPort(Protocol):
    """Contract implemented by safe plugin loaders."""

    def can_load(self, manifest: PluginManifest) -> bool:
        """Return whether the loader can load this manifest."""

    def load(self, manifest: PluginManifest) -> PluginLoadResult:
        """Load a manifest into a runtime plugin, or return a safe failure."""
