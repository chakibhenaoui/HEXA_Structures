"""
Orchestration des analyses OpenSees.

Statique linéaire, modale. Gestion du QThread pour ne pas bloquer la GUI.
Pushover et dynamique NL seront ajoutés dans les sprints suivants.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.solvers import SolverEngine, SolverManager

if TYPE_CHECKING:
    from core.model_data import ProjectModel


class AnalysisRunner:
    """Lance les analyses via le moteur de calcul configuré.

    Usage :
        runner = AnalysisRunner(project)
        success, results = runner.run_static(load_tag=1)

        # Multi-cas :
        all_results = runner.run_all()
        # → {"G (cas 1)": (True, {...}), "ELU 1 (combo 1)": (True, {...}), ...}
    """

    def __init__(
        self,
        project: ProjectModel,
        engine: SolverEngine | str | None = None,
    ):
        self.project = project
        self.solver_manager = SolverManager()
        self.backend, self.engine = self.solver_manager.create_backend(
            project, engine,
        )

    def run_all(
        self,
        callback: callable | None = None,
    ) -> dict[str, tuple[bool, dict]]:
        """Lance l'analyse statique pour TOUS les cas et combinaisons.

        Args:
            callback: Fonction(nom_cas, index, total) appelée après chaque cas.

        Returns:
            Dictionnaire {nom_cas: (succès, résultats)}.
        """
        results: dict[str, tuple[bool, dict]] = {}
        tasks: list[tuple[str, int | None, int | None]] = []

        # Cas de charge simples
        for tag, lc in self.project.loads.items():
            name = f"{lc.name} (cas {tag})"
            tasks.append((name, tag, None))

        # Combinaisons
        for tag, combo in self.project.combinations.items():
            name = f"{combo.name} (combo {tag})"
            tasks.append((name, None, tag))

        total = len(tasks)
        for idx, (name, load_tag, combo_tag) in enumerate(tasks):
            if callback is not None:
                callback(name, idx, total)
            success, res = self.run_static(
                load_tag=load_tag, combo_tag=combo_tag,
            )
            results[name] = (success, res)

        return results

    def run_static(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> tuple[bool, dict]:
        """Analyse statique linéaire.

        Args:
            load_tag: Tag du cas de charge simple (exclusif avec combo_tag).
            combo_tag: Tag de la combinaison (exclusif avec load_tag).
            max_iter: Nombre max d'itérations Newton.
            tol: Tolérance de convergence.

        Returns:
            Tuple (succès, résultats).
        """
        return self.backend.run_static(
            load_tag=load_tag,
            combo_tag=combo_tag,
            max_iter=max_iter,
            tol=tol,
        )

    def run_modal(self, num_modes: int = 10) -> tuple[bool, dict]:
        """Analyse modale (valeurs propres).

        Args:
            num_modes: Nombre de modes à calculer.

        Returns:
            Tuple (succès, résultats).
        """
        return self.backend.run_modal(num_modes=num_modes)

    @property
    def supports_diagrams(self) -> bool:
        """Indique si le backend courant expose les diagrammes OpenSees."""
        return bool(getattr(self.backend, "supports_diagrams", False))


# ═══════════════════════════════════════════════════════════════════════════
#  Worker QThread pour analyses non-bloquantes
# ═══════════════════════════════════════════════════════════════════════════

try:
    from PySide6.QtCore import QThread, Signal

    class AnalysisWorker(QThread):
        """Thread dédié pour lancer une analyse sans bloquer la GUI.

        Signaux :
            finished(bool, dict) : émis en fin d'analyse (succès, résultats).
            progress(int) : progression 0→100 (pour barre de progression).
            message(str) : message d'état pour la console.
        """

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
            """Exécution dans le thread séparé."""
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
