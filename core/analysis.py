"""OpenSees analysis orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.application import ApplicationServices
from core.solvers import SolverEngine

if TYPE_CHECKING:
    from core.model_data import ProjectModel


class AnalysisRunner:
    """Analysis runner."""

    def __init__(
        self,
        project: ProjectModel,
        engine: SolverEngine | str | None = None,
    ):
        self.project = project
        self.services = ApplicationServices(project, solver_request=engine)
        self.solver_manager = self.services.solver_manager
        self.backend = self.services.solver
        self.engine = self.services.engine

    def run_all(
        self,
        callback: callable | None = None,
    ) -> dict[str, tuple[bool, dict]]:
        """Run all."""
        return self.services.run_all_static(callback=callback)

    def run_static(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> tuple[bool, dict]:
        """Run static."""
        return self.services.run_static(
            load_tag=load_tag,
            combo_tag=combo_tag,
            max_iter=max_iter,
            tol=tol,
        )

    def run_modal(self, num_modes: int = 10) -> tuple[bool, dict]:
        """Run modal."""
        return self.services.run_modal(num_modes=num_modes)

    @property
    def supports_diagrams(self) -> bool:
        """Return whether diagrams."""
        return self.services.supports_diagrams


# ═══════════════════════════════════════════════════════════════════════════
#  Worker QThread for non-blocking analyses
# ═══════════════════════════════════════════════════════════════════════════

try:
    from PySide6.QtCore import QThread, Signal

    class AnalysisWorker(QThread):
        """Analysis worker."""

        finished = Signal(bool, dict)
        progress = Signal(int)
        message = Signal(str)

        def __init__(
            self,
            project: ProjectModel,
            analysis_type: str = "static",
            load_tag: int | None = None,
            combo_tag: int | None = None,
            num_modes: int = 10,
            engine: SolverEngine | str | None = None,
            parent=None,
        ):
            super().__init__(parent)
            self.project = project
            self.analysis_type = analysis_type
            self.load_tag = load_tag
            self.combo_tag = combo_tag
            self.num_modes = num_modes
            self.engine = engine

        def run(self) -> None:
            """Run the worker task."""
            runner = AnalysisRunner(self.project, engine=self.engine)

            self.message.emit(f"Analyse {self.analysis_type} en cours...")
            self.progress.emit(10)

            try:
                if self.analysis_type == "static":
                    success, results = runner.run_static(
                        load_tag=self.load_tag,
                        combo_tag=self.combo_tag,
                    )
                elif self.analysis_type == "modal":
                    success, results = runner.run_modal(
                        num_modes=self.num_modes,
                    )
                else:
                    success = False
                    results = {"error": f"Type d'analyse inconnu : {self.analysis_type}"}
            except Exception as e:
                success = False
                results = {"error": str(e)}

            self.progress.emit(100)
            status = "terminée" if success else "échouée"
            self.message.emit(f"Analyse {self.analysis_type} {status}.")
            self.finished.emit(success, results)

except ImportError:
    # PySide6 non disponible (ex. tests en CLI)
    pass
