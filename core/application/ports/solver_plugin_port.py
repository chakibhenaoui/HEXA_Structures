"""Port for solver plugin descriptors."""

from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from core.application.ports.solver_port import SolverPort
    from core.solvers.base import (
        AnalysisCapability,
        AnalysisFeature,
        SolverEngine,
        SolverInfo,
    )


class SolverPluginPort(Protocol):
    """Descriptor used by the application to discover solver adapters."""

    plugin_id: str
    engine: "SolverEngine"
    label: str
    install_hint: str | None
    is_default: bool
    plugin_version: str
    api_version: str
    source: str
    capabilities: dict["AnalysisFeature", "AnalysisCapability"]

    def detect(self) -> "SolverInfo":
        """Return availability and display metadata for this solver."""

    def create(self, project) -> "SolverPort":
        """Create the solver adapter for a project."""
