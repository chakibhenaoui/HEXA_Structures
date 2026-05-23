"""Plugin loader contracts and runtime implementations."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from inspect import Parameter, signature
import sys
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

    @classmethod
    def failed(cls, manifest: PluginManifest, message: str) -> "PluginLoadResult":
        """Return a failed load result without raising into the application."""
        return cls(
            plugin_id=manifest.plugin_id,
            kind=manifest.kind,
            load_state="error",
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


class ImportlibPluginLoader:
    """Opt-in loader for importable plugin entry points.

    The manifest-only loader remains the safe default. This loader is intended
    for an explicit plugin-enabled runtime path: it imports ``module:factory``
    entry points and returns the plugin object created by the factory.
    """

    def __init__(
        self,
        *,
        allowed_kinds: tuple[str, ...] | list[str] | None = None,
        include_manifest_dir: bool = True,
    ) -> None:
        self.allowed_kinds = (
            None
            if allowed_kinds is None
            else tuple(kind.strip().lower() for kind in allowed_kinds)
        )
        self.include_manifest_dir = include_manifest_dir

    def can_load(self, manifest: PluginManifest) -> bool:
        """Return whether this manifest declares an importable entry point."""
        kind_allowed = (
            self.allowed_kinds is None
            or manifest.kind in self.allowed_kinds
        )
        return (
            kind_allowed
            and manifest.entry_point is not None
            and ":" in manifest.entry_point
        )

    def load(self, manifest: PluginManifest) -> PluginLoadResult:
        """Import and instantiate a plugin from a manifest entry point."""
        if not self.can_load(manifest):
            return PluginLoadResult.manifest_only(
                manifest,
                "Manifest has no supported importlib entry point.",
            )

        try:
            module_name, factory_name = _parse_entry_point(manifest.entry_point or "")
            manifest_dir = manifest.path.parent if manifest.path is not None else None
            with _temporary_sys_path(manifest_dir, enabled=self.include_manifest_dir):
                module = import_module(module_name)
                factory = getattr(module, factory_name)
                plugin = _call_plugin_factory(factory, manifest)
            _validate_plugin_identity(manifest, plugin)
        except Exception as exc:
            return PluginLoadResult.failed(
                manifest,
                f"{type(exc).__name__}: {exc}",
            )

        return PluginLoadResult(
            plugin_id=manifest.plugin_id,
            kind=manifest.kind,
            load_state="loaded",
            loaded=True,
            plugin=plugin,
            error=None,
        )


def _parse_entry_point(entry_point: str) -> tuple[str, str]:
    module_name, separator, factory_name = entry_point.partition(":")
    if not separator or not module_name.strip() or not factory_name.strip():
        raise ValueError(
            "Plugin entry_point must use the 'module:factory' format."
        )
    return module_name.strip(), factory_name.strip()


class _temporary_sys_path:
    def __init__(self, path, *, enabled: bool) -> None:
        self.path = None if path is None else str(path)
        self.enabled = enabled
        self.inserted = False

    def __enter__(self) -> None:
        if not self.enabled or not self.path or self.path in sys.path:
            return
        sys.path.insert(0, self.path)
        self.inserted = True

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.inserted and self.path in sys.path:
            sys.path.remove(self.path)


def _call_plugin_factory(factory: Any, manifest: PluginManifest) -> Any:
    if not callable(factory):
        raise TypeError("Plugin entry point is not callable.")

    call_with_manifest = True
    try:
        parameters = signature(factory).parameters.values()
    except (TypeError, ValueError):
        parameters = ()

    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (
            Parameter.POSITIONAL_ONLY,
            Parameter.POSITIONAL_OR_KEYWORD,
        )
        and parameter.default is Parameter.empty
    ]
    has_varargs = any(
        parameter.kind is Parameter.VAR_POSITIONAL
        for parameter in parameters
    )
    if not positional and not has_varargs:
        call_with_manifest = False

    return factory(manifest) if call_with_manifest else factory()


def _validate_plugin_identity(manifest: PluginManifest, plugin: Any) -> None:
    plugin_id = getattr(plugin, "plugin_id", None)
    descriptor = getattr(plugin, "descriptor", None)
    if plugin_id is None and descriptor is not None:
        plugin_id = getattr(descriptor, "plugin_id", None)
    if plugin_id is not None and str(plugin_id) != manifest.plugin_id:
        raise ValueError(
            "Loaded plugin id does not match manifest id "
            f"({plugin_id!r} != {manifest.plugin_id!r})."
        )
