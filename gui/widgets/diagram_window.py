"""Diagram viewer window."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class DiagramWindow(QMainWindow):
    """Diagram viewer window."""

    file_index_changed = Signal(int)
    component_changed = Signal(str)
    case_changed = Signal(str)

    def __init__(
        self,
        parent=None,
        *,
        width: int = 1100,
        height: int = 760,
        window_title: str = "Diagrammes",
        case_label: str = "Cas / combinaison :",
        component_label: str = "Diagramme :",
        file_label: str = "File / plan :",
        export_basename: str = "diagramme",
    ):
        super().__init__(parent)
        self._window_title = window_title
        self._export_basename = export_basename
        self.setWindowTitle(window_title)
        self.resize(width, height)
        self._current_component = "N"
        self._current_case_name: str | None = None
        self._current_file_label: str | None = None
        self._current_figure = None

        root = QWidget(self)
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(8, 8, 8, 8)
        root_lay.setSpacing(6)

        top = QWidget(root)
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(8)

        top_lay.addWidget(QLabel(case_label, top))

        self.case_combo = QComboBox(top)
        self.case_combo.setMinimumWidth(260)
        self.case_combo.currentTextChanged.connect(self._on_case_changed)
        top_lay.addWidget(self.case_combo)

        top_lay.addWidget(QLabel(component_label, top))

        self.component_combo = QComboBox(top)
        self.component_combo.setMinimumWidth(120)
        self.component_combo.currentTextChanged.connect(
            self._on_component_changed
        )
        top_lay.addWidget(self.component_combo)

        top_lay.addWidget(QLabel(file_label, top))

        self.file_combo = QComboBox(top)
        self.file_combo.setMinimumWidth(280)
        self.file_combo.currentIndexChanged.connect(self.file_index_changed.emit)
        top_lay.addWidget(self.file_combo)

        self.btn_export_png = QPushButton("Exporter PNG", top)
        self.btn_export_png.clicked.connect(lambda: self._export_current_figure("png"))
        top_lay.addWidget(self.btn_export_png)

        self.btn_export_pdf = QPushButton("Exporter PDF", top)
        self.btn_export_pdf.clicked.connect(lambda: self._export_current_figure("pdf"))
        top_lay.addWidget(self.btn_export_pdf)

        top_lay.addStretch(1)
        root_lay.addWidget(top)

        self.canvas_holder = QWidget(root)
        holder_lay = QVBoxLayout(self.canvas_holder)
        holder_lay.setContentsMargins(0, 0, 0, 0)
        holder_lay.setSpacing(0)
        self.canvas_holder.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        root_lay.addWidget(self.canvas_holder, 1)

        self.setCentralWidget(root)
        self._setup_toolbar()

    def _setup_toolbar(self) -> None:
        """Set up toolbar."""
        toolbar = self.addToolBar(self._window_title)
        toolbar.setMovable(False)

        act_export_png = QAction("Exporter PNG", self)
        act_export_png.triggered.connect(lambda: self._export_current_figure("png"))
        toolbar.addAction(act_export_png)

        act_export_pdf = QAction("Exporter PDF", self)
        act_export_pdf.triggered.connect(lambda: self._export_current_figure("pdf"))
        toolbar.addAction(act_export_pdf)

    def set_cases(self, cases: list[str], current_case: str | None) -> None:
        """Set cases."""
        self.case_combo.blockSignals(True)
        self.case_combo.clear()
        for case_name in cases:
            self.case_combo.addItem(case_name)
        if cases:
            target = current_case if current_case in cases else cases[0]
            idx = max(0, self.case_combo.findText(target))
            self.case_combo.setCurrentIndex(idx)
            self._current_case_name = self.case_combo.currentText()
        else:
            self._current_case_name = None
        self.case_combo.blockSignals(False)
        self._update_title()

    def set_components(self, components: list[str], current_component: str) -> None:
        """Set components."""
        self.component_combo.blockSignals(True)
        self.component_combo.clear()
        for component in components:
            self.component_combo.addItem(component)
        if components:
            idx = max(0, self.component_combo.findText(current_component))
            self.component_combo.setCurrentIndex(idx)
            self._current_component = self.component_combo.currentText()
        self.component_combo.blockSignals(False)
        self._update_title()

    def set_files(self, files: list[dict], current_idx: int) -> None:
        """Set files."""
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for file_info in files:
            self.file_combo.addItem(file_info["label"])
        if files:
            idx = max(0, min(current_idx, len(files) - 1))
            self.file_combo.setCurrentIndex(idx)
            self._current_file_label = files[idx]["label"]
        else:
            self._current_file_label = None
        self.file_combo.blockSignals(False)
        self._update_title()

    def set_figure(
        self,
        figure,
        *,
        component: str,
        case_name: str | None,
        file_label: str | None,
    ) -> None:
        """Set figure."""
        from matplotlib.backends.backend_qtagg import (
            FigureCanvasQTAgg,
            NavigationToolbar2QT,
        )

        canvas = FigureCanvasQTAgg(figure)
        toolbar = NavigationToolbar2QT(canvas, self)

        holder_layout = self.canvas_holder.layout()
        while holder_layout.count():
            item = holder_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        holder_layout.addWidget(toolbar)
        holder_layout.addWidget(canvas, 1)

        self._current_figure = figure
        self._current_component = component
        self._current_case_name = case_name
        self._current_file_label = file_label
        self._update_title()

    def _on_component_changed(self, component: str) -> None:
        """Handle component changed."""
        self._current_component = component
        self._update_title()
        if component:
            self.component_changed.emit(component)

    def _on_case_changed(self, case_name: str) -> None:
        """Handle case changed."""
        self._current_case_name = case_name
        self._update_title()
        if case_name:
            self.case_changed.emit(case_name)

    def _default_export_name(self, extension: str) -> str:
        """Return the default export name."""
        parts = [
            self._export_basename,
            self._current_component or "resultat",
        ]
        if self._current_case_name:
            parts.append(self._sanitize_filename(self._current_case_name))
        if self._current_file_label:
            parts.append(self._sanitize_filename(self._current_file_label))
        return "_".join(parts) + f".{extension}"

    def _export_current_figure(self, extension: str) -> None:
        """Export the current figure as an image or PDF."""
        if self._current_figure is None:
            QMessageBox.information(
                self,
                "Diagrammes",
                "Aucun diagramme n'est disponible pour l'export.",
            )
            return

        filters = {
            "png": "Image PNG (*.png)",
            "pdf": "Document PDF (*.pdf)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter le diagramme",
            self._default_export_name(extension),
            filters[extension],
        )
        if not path:
            return
        if not path.lower().endswith(f".{extension}"):
            path += f".{extension}"

        try:
            self._current_figure.savefig(path, dpi=200, bbox_inches="tight")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Export impossible",
                f"L'export du diagramme a échoué :\n{exc}",
            )
            return

        self.statusBar().showMessage(f"Diagramme exporte : {path}", 5000)

    def _update_title(self) -> None:
        """Update title."""
        case_label = self._current_case_name or "sans cas"
        file_label = self._current_file_label or "sans file"
        self.setWindowTitle(
            f"{self._window_title} - {self._current_component} - {case_label} - {file_label}"
        )

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        """Handle sanitize filename."""
        cleaned = "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in value.strip()
        )
        return cleaned.strip("_") or "resultat"
