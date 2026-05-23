"""Use case for running a static analysis through a solver port."""

from __future__ import annotations

from dataclasses import dataclass

from core.application.ports import SolverPort
from core.application.results import AnalysisRunResult


@dataclass(frozen=True)
class RunStaticAnalysis:
    """Coordinate static analysis without knowing the solver implementation."""

    solver: SolverPort

    def execute(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> tuple[bool, dict]:
        """Run static analysis through the configured solver adapter."""
        return self.execute_result(
            load_tag=load_tag,
            combo_tag=combo_tag,
            max_iter=max_iter,
            tol=tol,
        ).as_legacy()

    def execute_result(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
        solver_id: str | None = None,
        case_name: str | None = None,
    ) -> AnalysisRunResult:
        """Run static analysis and return the typed application result."""
        result = self.solver.run_static(
            load_tag=load_tag,
            combo_tag=combo_tag,
            max_iter=max_iter,
            tol=tol,
        )
        return AnalysisRunResult.from_legacy(
            result,
            analysis_type="static",
            solver_id=solver_id,
            case_name=case_name,
        )
