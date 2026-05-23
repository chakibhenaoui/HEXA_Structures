"""Use case for running all static load cases and combinations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.application.ports import SolverPort
from core.application.results import AnalysisRunResult
from core.application.use_cases.run_static_analysis import RunStaticAnalysis

if TYPE_CHECKING:
    from core.model_data import ProjectModel


ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True)
class RunAllStaticAnalyses:
    """Run static analysis for every load case and combination in a project."""

    project: "ProjectModel"
    solver: SolverPort

    def execute(
        self,
        callback: ProgressCallback | None = None,
    ) -> dict[str, tuple[bool, dict]]:
        """Return results indexed by user-facing load case names."""
        return {
            name: result.as_legacy()
            for name, result in self.execute_results(callback=callback).items()
        }

    def execute_results(
        self,
        callback: ProgressCallback | None = None,
        solver_id: str | None = None,
    ) -> dict[str, AnalysisRunResult]:
        """Return typed results indexed by user-facing load case names."""
        results: dict[str, AnalysisRunResult] = {}
        tasks: list[tuple[str, int | None, int | None]] = []

        for tag, load_case in self.project.loads.items():
            tasks.append((f"{load_case.name} (cas {tag})", tag, None))

        for tag, combination in self.project.combinations.items():
            tasks.append((f"{combination.name} (combo {tag})", None, tag))

        runner = RunStaticAnalysis(self.solver)
        total = len(tasks)
        for idx, (name, load_tag, combo_tag) in enumerate(tasks):
            if callback is not None:
                callback(name, idx, total)
            results[name] = runner.execute_result(
                load_tag=load_tag,
                combo_tag=combo_tag,
                solver_id=solver_id,
                case_name=name,
            )

        return results
