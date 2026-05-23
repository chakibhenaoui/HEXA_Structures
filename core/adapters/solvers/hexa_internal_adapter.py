"""Placeholder for the future native HEXA solver adapter."""

from __future__ import annotations


class HexaInternalSolverAdapter:
    """Reserved adapter for a future internal solver plugin."""

    engine_name = "hexa_internal"
    supports_diagrams = False
    capabilities = {}

    def __init__(self, project):
        self.project = project

    def run_static(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> tuple[bool, dict]:
        del load_tag, combo_tag, max_iter, tol
        return False, {"error": "Le solveur interne HEXA n'est pas encore disponible."}

    def run_modal(self, num_modes: int = 10) -> tuple[bool, dict]:
        del num_modes
        return False, {"error": "Le solveur interne HEXA n'est pas encore disponible."}

    def sample_diagram_component(
        self,
        element_tag: int,
        component: str,
        nep: int = 17,
    ) -> None:
        del element_tag, component, nep
        return None
