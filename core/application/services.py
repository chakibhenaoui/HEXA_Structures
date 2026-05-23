"""Application facade for GUI and automation entry points."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from core.application.ports import PluginLoaderPort, SolverPort
from core.application.connection_design import (
    CONNECTION_DESIGN_EXTENSION_POINT,
    ConnectionDesignRequest,
    ConnectionDesignResult,
)
from core.application.results import AnalysisRunResult
from core.application.use_cases import (
    RunAllStaticAnalyses,
    RunConnectionDesign,
    RunModalAnalysis,
    RunStaticAnalysis,
)
from core.plugins import (
    ManifestOnlyPluginLoader,
    PluginDiscoveryResult,
    PluginLoadResult,
    PluginManifest,
    PluginRegistry,
    build_manifest_registry,
    default_plugin_roots,
    discover_plugin_manifests,
)
from core.solvers import AnalysisCapability, AnalysisFeature, SolverEngine, SolverInfo
from core.solvers.solver_manager import SolverManager

if TYPE_CHECKING:
    from core.model_data import ProjectModel


ProgressCallback = Callable[[str, int, int], None]


@dataclass
class ApplicationServices:
    """Small facade that coordinates application use cases.

    The GUI can gradually depend on this facade instead of wiring managers and
    use cases directly. It keeps legacy solver engine compatibility while the
    plugin-oriented solver id path becomes the long-term API.
    """

    project: "ProjectModel"
    solver_request: SolverEngine | str | None = None
    solver_manager: SolverManager = field(default_factory=SolverManager)
    plugin_roots: tuple[str | Path, ...] = field(default_factory=default_plugin_roots)
    plugin_loader: PluginLoaderPort = field(default_factory=ManifestOnlyPluginLoader)

    _solver: SolverPort | None = field(default=None, init=False, repr=False)
    _solver_id: str | None = field(default=None, init=False, repr=False)
    _engine: SolverEngine | None = field(default=None, init=False, repr=False)

    @property
    def solver(self) -> SolverPort:
        """Return the active solver adapter, creating it lazily."""
        self._ensure_solver()
        assert self._solver is not None
        return self._solver

    @property
    def solver_id(self) -> str:
        """Return the stable plugin id of the active solver."""
        self._ensure_solver()
        assert self._solver_id is not None
        return self._solver_id

    @property
    def engine(self) -> SolverEngine:
        """Return the legacy solver engine for compatibility code."""
        self._ensure_solver()
        assert self._engine is not None
        return self._engine

    @property
    def supports_diagrams(self) -> bool:
        """Return whether the active solver exposes internal force diagrams."""
        return bool(getattr(self.solver, "supports_diagrams", False))

    def detect_solvers(self) -> list[SolverInfo]:
        """Return detected solver plugins and their availability."""
        return self.solver_manager.detect_engines()

    def get_solver_display_info(
        self,
        *,
        include_installed_plugins: bool = True,
        plugin_roots: tuple[str | Path, ...] | list[str | Path] | None = None,
        strict: bool = False,
    ) -> list[dict[str, str | bool]]:
        """Return GUI-ready solver rows, including unloaded solver manifests."""
        rows = list(self.solver_manager.get_display_info())
        if not include_installed_plugins:
            return rows

        known_ids = {
            str(row.get("id") or row.get("engine") or "")
            for row in rows
        }
        for manifest in self.get_installed_plugin_manifests(
            plugin_roots,
            kind="solver",
            strict=strict,
        ):
            if manifest.plugin_id in known_ids:
                continue
            rows.append(
                _solver_manifest_display_row(
                    manifest,
                    can_load=self.plugin_loader.can_load(manifest),
                )
            )
            known_ids.add(manifest.plugin_id)
        return rows

    def get_solver_capabilities(
        self,
        solver_id: str | None = None,
    ) -> dict[AnalysisFeature, AnalysisCapability]:
        """Return capabilities for a solver id or the active solver."""
        return self.solver_manager.get_capabilities_for_solver(
            solver_id or self.solver_id,
        )

    def discover_plugins(
        self,
        plugin_roots: tuple[str | Path, ...] | list[str | Path] | None = None,
        *,
        strict: bool = False,
    ) -> PluginDiscoveryResult:
        """Discover installed plugin manifests without importing plugin code."""
        roots = tuple(plugin_roots) if plugin_roots is not None else self.plugin_roots
        return discover_plugin_manifests(roots, strict=strict)

    def get_installed_plugin_manifests(
        self,
        plugin_roots: tuple[str | Path, ...] | list[str | Path] | None = None,
        *,
        kind: str | None = None,
        extension_point: str | None = None,
        capability: str | None = None,
        tag: str | None = None,
        strict: bool = False,
    ) -> tuple[PluginManifest, ...]:
        """Return discovered plugin manifests filtered by generic metadata."""
        result = self.discover_plugins(plugin_roots, strict=strict)
        return tuple(
            manifest
            for manifest in result.manifests
            if _matches_plugin_filters(
                manifest,
                kind=kind,
                extension_point=extension_point,
                capability=capability,
                tag=tag,
            )
        )

    def get_installed_plugin_registry(
        self,
        plugin_roots: tuple[str | Path, ...] | list[str | Path] | None = None,
        *,
        kind: str | None = None,
        extension_point: str | None = None,
        capability: str | None = None,
        tag: str | None = None,
        strict: bool = False,
    ) -> PluginRegistry[PluginManifest]:
        """Return discovered plugin manifests indexed by stable plugin id."""
        return build_manifest_registry(
            self.get_installed_plugin_manifests(
                plugin_roots,
                kind=kind,
                extension_point=extension_point,
                capability=capability,
                tag=tag,
                strict=strict,
            )
        )

    def get_plugin_display_info(
        self,
        plugin_roots: tuple[str | Path, ...] | list[str | Path] | None = None,
        *,
        kind: str | None = None,
        extension_point: str | None = None,
        capability: str | None = None,
        tag: str | None = None,
        strict: bool = False,
    ) -> list[dict[str, str | bool]]:
        """Return GUI/API-ready rows for any installed plugin category."""
        return [
            _plugin_manifest_display_row(
                manifest,
                can_load=self.plugin_loader.can_load(manifest),
            )
            for manifest in self.get_installed_plugin_manifests(
                plugin_roots,
                kind=kind,
                extension_point=extension_point,
                capability=capability,
                tag=tag,
                strict=strict,
            )
        ]

    def get_plugin_discovery_errors(
        self,
        plugin_roots: tuple[str | Path, ...] | list[str | Path] | None = None,
    ):
        """Return non-fatal plugin discovery errors for diagnostics."""
        return self.discover_plugins(plugin_roots).errors

    def get_plugin_load_status(self, manifest: PluginManifest) -> PluginLoadResult:
        """Return load status for a manifest through the configured loader."""
        return self.plugin_loader.load(manifest)

    def get_connection_design_plugin_manifests(
        self,
        plugin_roots: tuple[str | Path, ...] | list[str | Path] | None = None,
        *,
        strict: bool = False,
    ) -> tuple[PluginManifest, ...]:
        """Return plugins contributing to the connection design extension point."""
        return self.get_installed_plugin_manifests(
            plugin_roots,
            extension_point=CONNECTION_DESIGN_EXTENSION_POINT,
            strict=strict,
        )

    def design_connection(
        self,
        request: ConnectionDesignRequest,
        *,
        plugin_id: str | None = None,
        plugin_roots: tuple[str | Path, ...] | list[str | Path] | None = None,
        strict: bool = False,
    ) -> tuple[ConnectionDesignResult, ...]:
        """Run connection design through installed plugin modules."""
        return RunConnectionDesign(
            self.plugin_loader,
            self.get_connection_design_plugin_manifests(
                plugin_roots,
                strict=strict,
            ),
        ).execute(request, plugin_id=plugin_id)

    def run_all_static(
        self,
        callback: ProgressCallback | None = None,
    ) -> dict[str, tuple[bool, dict]]:
        """Run static analysis for all load cases and combinations."""
        return {
            name: result.as_legacy()
            for name, result in self.run_all_static_results(
                callback=callback,
            ).items()
        }

    def run_all_static_results(
        self,
        callback: ProgressCallback | None = None,
    ) -> dict[str, AnalysisRunResult]:
        """Run all static cases and return typed application results."""
        return RunAllStaticAnalyses(self.project, self.solver).execute_results(
            callback=callback,
            solver_id=self.solver_id,
        )

    def run_static(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> tuple[bool, dict]:
        """Run a static analysis through the active solver."""
        return self.run_static_result(
            load_tag=load_tag,
            combo_tag=combo_tag,
            max_iter=max_iter,
            tol=tol,
        ).as_legacy()

    def run_static_result(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> AnalysisRunResult:
        """Run a static analysis and return a typed application result."""
        return RunStaticAnalysis(self.solver).execute_result(
            load_tag=load_tag,
            combo_tag=combo_tag,
            max_iter=max_iter,
            tol=tol,
            solver_id=self.solver_id,
        )

    def run_modal(self, num_modes: int = 10) -> tuple[bool, dict]:
        """Run a modal analysis through the active solver."""
        return self.run_modal_result(num_modes=num_modes).as_legacy()

    def run_modal_result(self, num_modes: int = 10) -> AnalysisRunResult:
        """Run a modal analysis and return a typed application result."""
        return RunModalAnalysis(self.solver).execute_result(
            num_modes=num_modes,
            solver_id=self.solver_id,
        )

    def _ensure_solver(self) -> None:
        if self._solver is not None:
            return
        self._solver, self._engine = self.solver_manager.create_backend(
            self.project,
            self.solver_request,
        )
        self._solver_id = self.solver_manager.resolve_solver_id(self.solver_request)


def _matches_plugin_filters(
    manifest: PluginManifest,
    *,
    kind: str | None = None,
    extension_point: str | None = None,
    capability: str | None = None,
    tag: str | None = None,
) -> bool:
    if kind is not None and manifest.kind != kind.strip().lower():
        return False
    if extension_point is not None and not manifest.provides_extension(extension_point):
        return False
    if capability is not None and not manifest.has_capability(capability):
        return False
    if tag is not None and not manifest.has_tag(tag):
        return False
    return True


def _plugin_manifest_display_row(
    manifest: PluginManifest,
    *,
    can_load: bool = False,
) -> dict[str, str | bool]:
    load_state = "loadable" if can_load else "manifest_only"
    return {
        "id": manifest.plugin_id,
        "kind": manifest.kind,
        "name": manifest.name,
        "text": manifest.name,
        "description": manifest.description,
        "entry_point": manifest.entry_point or "",
        "version": manifest.descriptor.version,
        "api_version": manifest.descriptor.api_version,
        "source": manifest.descriptor.source,
        "capabilities": ", ".join(manifest.capabilities),
        "extension_points": ", ".join(manifest.extension_points),
        "tags": ", ".join(manifest.tags),
        "load_state": load_state,
        "loadable": can_load,
    }


def _solver_manifest_display_row(
    manifest: PluginManifest,
    *,
    can_load: bool = False,
) -> dict[str, str | bool]:
    version = manifest.descriptor.version
    api_version = manifest.descriptor.api_version
    load_state = "loadable" if can_load else "manifest_only"
    loader_message = (
        "chargeur externe disponible, activation non connectee"
        if can_load
        else "chargeur externe non disponible pour l'instant"
    )
    tooltip_parts = [
        f"Plugin installe: {manifest.plugin_id}",
        f"version {version}",
        f"API {api_version}",
        loader_message,
    ]
    if manifest.entry_point:
        tooltip_parts.insert(1, f"entry point: {manifest.entry_point}")
    return {
        "id": manifest.plugin_id,
        "engine": manifest.plugin_id,
        "text": f"{manifest.name} (installe, non charge)",
        "tooltip": " | ".join(tooltip_parts),
        "enabled": False,
        "source": manifest.descriptor.source,
        "kind": manifest.kind,
        "version": version,
        "api_version": api_version,
        "load_state": load_state,
    }
