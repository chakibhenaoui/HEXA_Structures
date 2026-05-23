"""Use case for running a modal analysis through a solver port."""

from __future__ import annotations

from dataclasses import dataclass

from core.application.ports import SolverPort
from core.application.results import AnalysisRunResult


@dataclass(frozen=True)
class RunModalAnalysis:
    """Coordinate modal analysis without knowing the solver implementation."""

    solver: SolverPort

    def execute(self, num_modes: int = 10) -> tuple[bool, dict]:
        """Run modal analysis through the configured solver adapter."""
        return self.execute_result(num_modes=num_modes).as_legacy()

    def execute_result(
        self,
        num_modes: int = 10,
        solver_id: str | None = None,
    ) -> AnalysisRunResult:
        """Run modal analysis and return the typed application result."""
        return AnalysisRunResult.from_legacy(
            self.solver.run_modal(num_modes=num_modes),
            analysis_type="modal",
            solver_id=solver_id,
        )
