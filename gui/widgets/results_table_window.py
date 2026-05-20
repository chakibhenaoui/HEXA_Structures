"""
Detached window dedicated to results tables.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow

from gui.widgets.results_panel import ResultsPanel


class ResultsTableWindow(QMainWindow):
    """Modèless window used to browse results tables comfortably."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Tableaux de résultats")
        self.resize(1180, 720)
        self.panel = ResultsPanel(self)
        self.setCentralWidget(self.panel)

    def set_all_results(self, all_results: dict[str, dict]) -> None:
        self.panel.set_all_results(all_results)

    def set_envelopes(self, envelopes: dict) -> None:
        self.panel.set_envelopes(envelopes)

    def clear_results(self) -> None:
        self.panel.clear_results()

    def set_current_case(self, case_name: str, *, emit_signal: bool = False) -> None:
        self.panel.set_current_case(case_name, emit_signal=emit_signal)

    def current_case(self) -> str | None:
        return self.panel.current_case()

    def show_result_type(self, result_type: str) -> None:
        self.panel.show_result_type(result_type)

