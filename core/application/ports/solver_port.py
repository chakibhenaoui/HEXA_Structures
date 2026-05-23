"""Port for structural solver adapters."""

from __future__ import annotations

from typing import Protocol


class SolverPort(Protocol):
    """Minimal contract exposed by solver adapters to application use cases."""

    engine_name: str
    supports_diagrams: bool

    def run_static(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> tuple[bool, dict]:
        """Run a static analysis and return the legacy result shape."""

    def run_modal(self, num_modes: int = 10) -> tuple[bool, dict]:
        """Run a modal analysis and return the legacy result shape."""

    def sample_diagram_component(
        self,
        element_tag: int,
        component: str,
        nep: int = 17,
    ) -> object | None:
        """Sample an internal force diagram when supported by the adapter."""
