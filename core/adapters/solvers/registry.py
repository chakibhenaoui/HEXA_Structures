"""Catalog of solver adapter plugins.

The registry is deliberately small and explicit. It gives HEXA Structures a
plugin-shaped extension point without forcing a broad refactor of the existing
solver backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

from core.adapters.solvers.opensees_adapter import OpenSeesSolverAdapter
from core.adapters.solvers.pynite_adapter import PyNiteSolverAdapter
from core.optional_imports import ensure_external_module_search_paths
from core.plugins import PluginDescriptor, PluginRegistry
from core.solvers.base import (
    AnalysisCapability,
    AnalysisFeature,
    SolverEngine,
    SolverInfo,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from core.application.ports import SolverPort


@dataclass(frozen=True)
class SolverAdapterPlugin:
    """Metadata and factory for one solver adapter."""

    plugin_id: str
    engine: SolverEngine
    label: str
    adapter_cls: type[SolverPort]
    module_names: tuple[str, ...]
    package_names: tuple[str, ...]
    install_hint: str | None = None
    is_default: bool = False
    plugin_version: str = "builtin"
    api_version: str = "1"
    source: str = "builtin"

    @property
    def descriptor(self) -> PluginDescriptor:
        """Return generic plugin metadata for this solver plugin."""
        return PluginDescriptor(
            plugin_id=self.plugin_id,
            name=self.label,
            version=self.plugin_version,
            api_version=self.api_version,
            source=self.source,
        )

    @property
    def capabilities(self) -> dict[AnalysisFeature, AnalysisCapability]:
        """Return the adapter capabilities as a plain mutable copy."""
        return dict(getattr(self.adapter_cls, "capabilities", {}))

    def detect(self) -> SolverInfo:
        """Detect whether this solver adapter can run in the current environment."""
        return SolverInfo(
            engine=self.engine,
            label=self.label,
            available=has_any_module(*self.module_names),
            version=package_version(*self.package_names),
            install_hint=self.install_hint,
            is_default=self.is_default,
            solver_id=self.plugin_id,
            plugin_version=self.plugin_version,
            api_version=self.api_version,
            source=self.source,
        )

    def create(self, project) -> SolverPort:
        """Instantiate the adapter for the project."""
        return self.adapter_cls(project)


_SOLVER_PLUGINS: tuple[SolverAdapterPlugin, ...] = (
    SolverAdapterPlugin(
        plugin_id="pynite",
        engine=SolverEngine.PYNITE,
        label="PyNite",
        adapter_cls=PyNiteSolverAdapter,
        module_names=("Pynite", "PyniteFEA"),
        package_names=("PyNiteFEA", "pynitefea"),
        install_hint="pip install PyNiteFEA",
        is_default=True,
    ),
    SolverAdapterPlugin(
        plugin_id="opensees",
        engine=SolverEngine.OPENSEES,
        label="OpenSeesPy",
        adapter_cls=OpenSeesSolverAdapter,
        module_names=("openseespy",),
        package_names=("openseespy",),
        install_hint="pip install openseespy",
        is_default=False,
    ),
)

_SOLVER_PLUGIN_REGISTRY = PluginRegistry(_SOLVER_PLUGINS)


def get_solver_plugins() -> tuple[SolverAdapterPlugin, ...]:
    """Return registered solver adapter plugins in display/fallback order."""
    return _SOLVER_PLUGIN_REGISTRY.all()


def get_solver_plugin_registry() -> PluginRegistry[SolverAdapterPlugin]:
    """Return the solver plugin registry."""
    return _SOLVER_PLUGIN_REGISTRY


def get_solver_plugin_map(
    plugins: "Iterable[SolverAdapterPlugin] | None" = None,
) -> dict[SolverEngine, SolverAdapterPlugin]:
    """Return plugins indexed by engine."""
    return {plugin.engine: plugin for plugin in (plugins or get_solver_plugins())}


def get_solver_plugin_id_map(
    plugins: "Iterable[SolverAdapterPlugin] | None" = None,
) -> dict[str, SolverAdapterPlugin]:
    """Return plugins indexed by stable plugin id."""
    return {plugin.plugin_id: plugin for plugin in (plugins or get_solver_plugins())}


def has_any_module(*module_names: str) -> bool:
    """Return whether at least one import name can be resolved."""
    return ensure_external_module_search_paths(*module_names)


def package_version(*package_names: str) -> str | None:
    """Return the first available package version."""
    for package_name in package_names:
        try:
            return version(package_name)
        except PackageNotFoundError:
            continue
    return None
