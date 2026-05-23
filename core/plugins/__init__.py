"""Lightweight plugin runtime primitives for HEXA Structures."""

from core.plugins.base import PluginDescriptor
from core.plugins.discovery import (
    PluginDiscoveryError,
    PluginDiscoveryResult,
    build_manifest_registry,
    discover_plugin_manifests,
)
from core.plugins.loader import (
    ImportlibPluginLoader,
    ManifestOnlyPluginLoader,
    PluginLoadResult,
)
from core.plugins.manifest import PluginManifest
from core.plugins.paths import default_plugin_roots
from core.plugins.registry import PluginRegistry

__all__ = [
    "PluginDiscoveryError",
    "PluginDiscoveryResult",
    "PluginDescriptor",
    "PluginLoadResult",
    "PluginManifest",
    "PluginRegistry",
    "ImportlibPluginLoader",
    "ManifestOnlyPluginLoader",
    "build_manifest_registry",
    "default_plugin_roots",
    "discover_plugin_manifests",
]
