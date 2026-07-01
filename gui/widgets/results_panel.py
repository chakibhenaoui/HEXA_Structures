"""
Results tables panel with case selector, filtering, and sorting.

Used both inside the bottom dock and inside the detached results window.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QFile, QIODevice, Qt, Signal
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.results import compute_result_summary
from gui.resources import app_resource_path

if TYPE_CHECKING:
    from core.results import ElementEnvelope, ResultSummaryRow, SurfaceResult
    from core.result_mapping import PlateRegionResult


class NumericTableWidgetItem(QTableWidgetItem):
    """Table item that sorts using its numeric payload when available."""

    def __init__(self, text: str, numeric_value: float | None = None) -> None:
        super().__init__(text)
        if numeric_value is not None:
            self.setData(Qt.UserRole, float(numeric_value))

    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(Qt.UserRole)
        right = other.data(Qt.UserRole)
        if left is not None and right is not None:
            try:
                return float(left) < float(right)
            except (TypeError, ValueError):
                pass
        return super().__lt__(other)


class ResultsPanel(QWidget):
    """Results panel with case selector and filterable/sortable tables."""

    case_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._all_results: dict[str, dict] = {}
        self._envelopes: dict[int, ElementEnvelope] = {}
        self._summary_rows: list[ResultSummaryRow] = []

        ui_path = app_resource_path("gui", "ui", "results_panel.ui")
        loader = QUiLoader()
        file = QFile(ui_path)
        if not file.open(QIODevice.ReadOnly):
            raise RuntimeError(f"Unable to open/read ui device: {ui_path}")
        self.ui = loader.load(file, self)
        file.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)

        self._case_label = self.ui.findChild(QLabel, "lbl_case")
        self._tabs = self.ui.findChild(QTabWidget, "tabs")
        self._summary_tab, self._summary_table = self._create_summary_tab()
        self._table_by_result_type = {
            "summary": self._summary_table,
            "displacements": self.ui.tbl_displacements,
            "reactions": self.ui.tbl_reactions,
            "element_forces": self.ui.tbl_forces,
            "surface_results": self.ui.tbl_surface_results,
            "envelopes": self.ui.tbl_envelopes,
        }
        self._tab_by_result_type = {
            "summary": self._summary_tab,
            "displacements": self.ui.tab_displacements,
            "reactions": self.ui.tab_reactions,
            "element_forces": self.ui.tab_forces,
            "surface_results": self.ui.tab_surface_results,
            "envelopes": self.ui.tab_envelopes,
        }

        self._inject_filter_bar()
        self._inject_info_bar()
        self._configure_tables()

        self.ui.case_combo.currentTextChanged.connect(self._on_case_changed)
        if self._tabs is not None:
            self._tabs.currentChanged.connect(lambda _index: self._apply_current_filter())
        self.retranslate_ui()

    # -- Public API -----------------------------------------------------------

    def clear_results(self) -> None:
        """Clear all results and empty all tables."""
        self._all_results.clear()
        self._envelopes.clear()
        self._summary_rows.clear()
        self.ui.case_combo.blockSignals(True)
        self.ui.case_combo.clear()
        self.ui.case_combo.blockSignals(False)
        self._fill_summary([])
        self._fill_tables({})
        self._fill_envelopes({})

    def set_all_results(self, all_results: dict[str, dict]) -> None:
        """Load all per-case results and populate the combo box."""
        self._all_results = all_results
        self._summary_rows = compute_result_summary(all_results)
        self._fill_summary(self._summary_rows)

        self.ui.case_combo.blockSignals(True)
        self.ui.case_combo.clear()
        for name in all_results:
            self.ui.case_combo.addItem(name)
        self.ui.case_combo.blockSignals(False)

        if all_results:
            first = next(iter(all_results))
            self.ui.case_combo.setCurrentText(first)
            self._fill_tables(all_results[first])
        else:
            self._fill_tables({})

    def set_envelopes(self, envelopes: dict[int, ElementEnvelope]) -> None:
        """Populate the envelope table."""
        self._envelopes = envelopes
        self._fill_envelopes(envelopes)

    def set_current_case(self, case_name: str, *, emit_signal: bool = False) -> None:
        """Select the given case without forcing callers to touch the combo box."""
        if not case_name:
            return
        if self.ui.case_combo.currentText() == case_name:
            if emit_signal:
                self.case_changed.emit(case_name)
            return
        self.ui.case_combo.blockSignals(not emit_signal)
        self.ui.case_combo.setCurrentText(case_name)
        self.ui.case_combo.blockSignals(False)
        if not emit_signal:
            results = self._all_results.get(case_name)
            if results is not None:
                self._fill_tables(results)

    def current_case(self) -> str | None:
        """Return the currently selected case name."""
        text = self.ui.case_combo.currentText()
        return text if text else None

    def show_result_type(self, result_type: str) -> None:
        """Switch to the requested results tab."""
        if self._tabs is None:
            return
        tab = self._tab_by_result_type.get(result_type)
        if tab is None:
            return
        idx = self._tabs.indexOf(tab)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
        self._apply_current_filter()

    def export_current_table_csv(
        self,
        path: str | Path,
        *,
        visible_only: bool = True,
        delimiter: str = ";",
    ) -> int:
        """Export the active results table to CSV and return the exported row count."""
        table = self._current_table()
        if table is None:
            return 0
        return self._export_table_csv(
            table,
            Path(path),
            visible_only=visible_only,
            delimiter=delimiter,
        )

    def retranslate_ui(self) -> None:
        """Refresh persistent labels after a language change."""
        if self._case_label is not None:
            self._case_label.setText(self.tr("Cas / Combinaison :"))
        if hasattr(self, "_filter_label"):
            self._filter_label.setText(self.tr("Filtre :"))
        if hasattr(self, "_filter_edit"):
            self._filter_edit.setPlaceholderText(
                self.tr("Texte, nœud, élément, cas...")
            )
        if self._tabs is not None:
            tab_titles = {
                "summary": self.tr("Synthèse"),
                "displacements": self.tr("Déplacements"),
                "reactions": self.tr("Réactions"),
                "element_forces": self.tr("Efforts internes"),
                "surface_results": self.tr("Plaques"),
                "envelopes": self.tr("Enveloppes"),
            }
            for result_type, tab in self._tab_by_result_type.items():
                idx = self._tabs.indexOf(tab)
                if idx >= 0:
                    self._tabs.setTabText(idx, tab_titles[result_type])
        current_case = self.current_case()
        if current_case and current_case in self._all_results:
            self._fill_tables(self._all_results[current_case])
        if self._envelopes:
            self._fill_envelopes(self._envelopes)
        self._fill_summary(self._summary_rows)
        if hasattr(self, "_btn_export_csv"):
            self._btn_export_csv.setText(self.tr("Exporter CSV..."))

    # -- Internal UI setup ----------------------------------------------------

    def _create_summary_tab(self) -> tuple[QWidget, QTableWidget]:
        """Create the summary tab injected before detailed result tables."""
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        table = QTableWidget(tab)
        table.setObjectName("tbl_summary")
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(table)
        if self._tabs is not None:
            self._tabs.insertTab(0, tab, self.tr("Synthèse"))
            self._tabs.setCurrentWidget(tab)
        return tab, table

    def _inject_filter_bar(self) -> None:
        """Add a lightweight filter row next to the case selector."""
        self._filter_label = QLabel(self.tr("Filtre :"), self)
        self._filter_edit = QLineEdit(self)
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.setPlaceholderText(self.tr("Texte, nœud, élément, cas..."))
        self._filter_edit.textChanged.connect(self._apply_current_filter)

        top_bar = self.ui.findChild(QHBoxLayout, "top_bar")
        if top_bar is None and self.ui.layout() is not None and self.ui.layout().count() > 0:
            maybe_layout = self.ui.layout().itemAt(0).layout()
            if isinstance(maybe_layout, QHBoxLayout):
                top_bar = maybe_layout
        if top_bar is None:
            self._filter_label.hide()
            self._filter_edit.hide()
            return

        top_bar.addWidget(self._filter_label)
        top_bar.addWidget(self._filter_edit, 1)

        self._btn_export_csv = QPushButton(self.tr("Exporter CSV..."), self)
        self._btn_export_csv.setIcon(
            self.style().standardIcon(QStyle.SP_DialogSaveButton)
        )
        self._btn_export_csv.clicked.connect(self._export_current_table_csv_interactive)
        top_bar.addWidget(self._btn_export_csv)

    def _inject_info_bar(self) -> None:
        """Add a contextual information label above the results tabs."""
        self._info_label = QLabel(self)
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet(
            "background: #fff6df; border: 1px solid #e5c97a; "
            "border-radius: 4px; color: #6b5200; padding: 6px;"
        )
        self._info_label.hide()

        if self.layout() is not None:
            self.layout().insertWidget(1, self._info_label)

    def _configure_tables(self) -> None:
        """Configure tables."""
        for table in self._table_by_result_type.values():
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setAlternatingRowColors(True)
            table.setSortingEnabled(False)

    # -- Slots ----------------------------------------------------------------

    def _on_case_changed(self, case_name: str) -> None:
        """Refresh tables when the active case changes."""
        results = self._all_results.get(case_name)
        if results is not None:
            self._fill_tables(results)
        self.case_changed.emit(case_name)

    # -- Table filling --------------------------------------------------------

    def _fill_tables(self, results: dict) -> None:
        self._fill_displacements(results.get("displacements", {}))
        self._fill_reactions(results.get("reactions", {}))
        self._fill_forces(results.get("element_forces", {}))
        if results.get("plate_results"):
            self._fill_plate_results(results.get("plate_results", {}))
        else:
            self._fill_surface_results(results.get("surface_results", {}))
        self._update_context_message(results)
        self._apply_current_filter()

    def _fill_summary(self, rows: list["ResultSummaryRow"]) -> None:
        table = self._summary_table
        headers = [
            self.tr("Famille"),
            self.tr("Objet"),
            self.tr("Composante"),
            self.tr("Extrême"),
            self.tr("Valeur"),
            self.tr("Unité"),
            self.tr("Cas / Combinaison"),
        ]
        self._prepare_table(table, headers, len(rows))
        for row_index, row in enumerate(rows):
            table.setItem(row_index, 0, QTableWidgetItem(row.category))
            table.setItem(row_index, 1, QTableWidgetItem(row.target))
            table.setItem(row_index, 2, QTableWidgetItem(row.component))
            table.setItem(row_index, 3, QTableWidgetItem(row.extremum))
            table.setItem(
                row_index,
                4,
                NumericTableWidgetItem(f"{row.value:.6g}", row.value),
            )
            table.setItem(row_index, 5, QTableWidgetItem(row.unit))
            table.setItem(row_index, 6, QTableWidgetItem(row.case_name))
        self._finish_table(table)

    def _fill_displacements(self, disps: dict) -> None:
        table = self.ui.tbl_displacements
        headers = [
            self.tr("Nœud"), "Ux (m)", "Uy (m)", "Uz (m)",
            "Rx (rad)", "Ry (rad)", "Rz (rad)",
        ]
        self._prepare_table(table, headers, len(disps))
        for row, (tag, result) in enumerate(sorted(disps.items())):
            table.setItem(row, 0, QTableWidgetItem(f"N{tag}"))
            for col, value in enumerate(
                [result.ux, result.uy, result.uz, result.rx, result.ry, result.rz],
                1,
            ):
                table.setItem(row, col, NumericTableWidgetItem(f"{value:.6f}", value))
        self._finish_table(table)

    def _fill_reactions(self, reacts: dict) -> None:
        table = self.ui.tbl_reactions
        headers = [
            self.tr("Nœud"), "Fx (kN)", "Fy (kN)", "Fz (kN)",
            "Mx (kN.m)", "My (kN.m)", "Mz (kN.m)",
        ]
        self._prepare_table(table, headers, len(reacts))
        for row, (tag, result) in enumerate(sorted(reacts.items())):
            table.setItem(row, 0, QTableWidgetItem(f"N{tag}"))
            for col, value in enumerate(
                [
                    result.fx_reaction,
                    result.fy_reaction,
                    result.fz_reaction,
                    result.mx_reaction,
                    result.my_reaction,
                    result.mz_reaction,
                ],
                1,
            ):
                table.setItem(row, col, NumericTableWidgetItem(f"{value:.2f}", value))
        self._finish_table(table)

    def _fill_forces(self, forces: dict) -> None:
        table = self.ui.tbl_forces
        headers = [
            self.tr("Élément"), self.tr("Extrémité"), "N (kN)", "Vy (kN)", "Vz (kN)",
            "T (kN.m)", "My (kN.m)", "Mz (kN.m)",
        ]
        self._prepare_table(table, headers, len(forces) * 2)
        row = 0
        for tag, result in sorted(forces.items()):
            row = self._set_force_row(
                table,
                row,
                tag,
                "i",
                [result.n_i, result.vy_i, result.vz_i, result.t_i, result.my_i, result.mz_i],
            )
            row = self._set_force_row(
                table,
                row,
                tag,
                "j",
                [result.n_j, result.vy_j, result.vz_j, result.t_j, result.my_j, result.mz_j],
            )
        self._finish_table(table)

    def _set_force_row(
        self,
        table: QTableWidget,
        row: int,
        tag: int,
        end_label: str,
        values: list[float],
    ) -> int:
        table.setItem(row, 0, QTableWidgetItem(f"E{tag}"))
        table.setItem(row, 1, QTableWidgetItem(end_label))
        for col, value in enumerate(values, 2):
            table.setItem(row, col, NumericTableWidgetItem(f"{value:.2f}", value))
        return row + 1

    def _fill_surface_results(self, surface_results: dict[int, SurfaceResult]) -> None:
        table = self.ui.tbl_surface_results
        headers = [
            self.tr("Surface"),
            "Nxx (kN/m)",
            "Nyy (kN/m)",
            "Nxy (kN/m)",
            "Mxx (kN.m/m)",
            "Myy (kN.m/m)",
            "Mxy (kN.m/m)",
            "Qx (kN/m)",
            "Qy (kN/m)",
        ]
        self._prepare_table(table, headers, len(surface_results))
        for row, (tag, result) in enumerate(sorted(surface_results.items())):
            table.setItem(row, 0, QTableWidgetItem(f"S{tag}"))
            for col, value in enumerate(
                [
                    result.nxx,
                    result.nyy,
                    result.nxy,
                    result.mxx,
                    result.myy,
                    result.mxy,
                    result.qx,
                    result.qy,
                ],
                1,
            ):
                table.setItem(row, col, NumericTableWidgetItem(f"{value:.3f}", value))
        self._finish_table(table)

    def _fill_plate_results(self, plate_results: dict[int, "PlateRegionResult"]) -> None:
        table = self.ui.tbl_surface_results
        headers = [
            self.tr("Plaque"),
            "Uz min (m)",
            "Uz max (m)",
            "Mxx min/max extrap. (kN.m/m)",
            "Myy min/max extrap. (kN.m/m)",
            "Mxy min/max extrap. (kN.m/m)",
            "Qx min/max extrap. (kN/m)",
            "Qy min/max extrap. (kN/m)",
            "Fz appuis plaque (kN)",
        ]
        self._prepare_table(table, headers, len(plate_results))
        for row, (tag, result) in enumerate(sorted(plate_results.items())):
            values = [
                (f"{result.uz_min:.6f}", result.uz_min),
                (f"{result.uz_max:.6f}", result.uz_max),
                (f"{result.mxx_min:.3f} / {result.mxx_max:.3f}", result.mxx_min),
                (f"{result.myy_min:.3f} / {result.myy_max:.3f}", result.myy_min),
                (f"{result.mxy_min:.3f} / {result.mxy_max:.3f}", result.mxy_min),
                (f"{result.qx_min:.3f} / {result.qx_max:.3f}", result.qx_min),
                (f"{result.qy_min:.3f} / {result.qy_max:.3f}", result.qy_min),
                (f"{result.fz_reaction_total:.3f}", result.fz_reaction_total),
            ]
            table.setItem(row, 0, QTableWidgetItem(f"P{tag}"))
            for col, (text, numeric) in enumerate(values, 1):
                table.setItem(row, col, NumericTableWidgetItem(text, numeric))
        self._finish_table(table)

    def _fill_envelopes(self, envelopes: dict[int, ElementEnvelope]) -> None:
        table = self.ui.tbl_envelopes
        components = [
            ("n", "N", "kN"),
            ("vy", "Vy", "kN"),
            ("vz", "Vz", "kN"),
            ("t", "T", "kN.m"),
            ("my", "My", "kN.m"),
            ("mz", "Mz", "kN.m"),
        ]
        headers = [self.tr("Élément")]
        for _prefix, label, unit in components:
            headers.extend(
                [
                    f"{label} min ({unit})",
                    self.tr("Cas"),
                    f"{label} max ({unit})",
                    self.tr("Cas"),
                ]
            )
        self._prepare_table(table, headers, len(envelopes))
        for row, (tag, env) in enumerate(sorted(envelopes.items())):
            col = 0
            table.setItem(row, col, QTableWidgetItem(f"E{tag}"))
            col += 1
            for prefix, _label, _unit in components:
                v_min = getattr(env, f"{prefix}_min")
                c_min = getattr(env, f"{prefix}_min_case")
                v_max = getattr(env, f"{prefix}_max")
                c_max = getattr(env, f"{prefix}_max_case")
                table.setItem(row, col, NumericTableWidgetItem(f"{v_min:.2f}", v_min))
                col += 1
                table.setItem(row, col, QTableWidgetItem(c_min))
                col += 1
                table.setItem(row, col, NumericTableWidgetItem(f"{v_max:.2f}", v_max))
                col += 1
                table.setItem(row, col, QTableWidgetItem(c_max))
                col += 1
        self._finish_table(table)

    # -- Filtering ------------------------------------------------------------

    def _apply_current_filter(self) -> None:
        """Apply the search filter to the currently visible table."""
        table = self._current_table()
        if table is None:
            return
        pattern = self._filter_edit.text().strip().casefold()
        for row in range(table.rowCount()):
            if not pattern:
                table.setRowHidden(row, False)
                continue
            texts = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item is not None:
                    texts.append(item.text().casefold())
            table.setRowHidden(row, pattern not in " ".join(texts))

    def _export_current_table_csv_interactive(self) -> None:
        """Ask for a CSV path and export the currently visible table."""
        table = self._current_table()
        if table is None:
            QMessageBox.information(
                self,
                self.tr("Export CSV"),
                self.tr("Aucun tableau n'est disponible pour l'export."),
            )
            return

        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            self.tr("Exporter le tableau en CSV"),
            self._default_csv_name(),
            self.tr("Fichiers CSV (*.csv)"),
        )
        if not path:
            return

        try:
            count = self.export_current_table_csv(path)
        except OSError as exc:
            QMessageBox.critical(
                self,
                self.tr("Export CSV"),
                self.tr("L'export CSV a échoué :\n{error}").format(error=exc),
            )
            return

        QMessageBox.information(
            self,
            self.tr("Export CSV"),
            self.tr("{count} ligne(s) exportée(s) :\n{path}").format(
                count=count,
                path=path,
            ),
        )

    def _default_csv_name(self) -> str:
        """Return a stable default file name for the active table."""
        result_type = "resultats"
        if self._tabs is not None:
            current = self._tabs.currentWidget()
            for candidate, tab in self._tab_by_result_type.items():
                if tab is current:
                    result_type = candidate
                    break
        case_name = self.current_case() or "multi_cas"
        raw_name = f"hexa_{result_type}_{case_name}.csv"
        safe = "".join(
            char if char.isalnum() or char in {"-", "_", "."} else "_"
            for char in raw_name
        )
        return safe.strip("_") or "hexa_resultats.csv"

    @staticmethod
    def _export_table_csv(
        table: QTableWidget,
        path: Path,
        *,
        visible_only: bool = True,
        delimiter: str = ";",
    ) -> int:
        """Write table headers and rows to a CSV file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = [
            table.horizontalHeaderItem(col).text()
            if table.horizontalHeaderItem(col) is not None
            else ""
            for col in range(table.columnCount())
        ]

        exported_rows = 0
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=delimiter)
            writer.writerow(headers)
            for row in range(table.rowCount()):
                if visible_only and table.isRowHidden(row):
                    continue
                writer.writerow(
                    [
                        table.item(row, col).text()
                        if table.item(row, col) is not None
                        else ""
                        for col in range(table.columnCount())
                    ]
                )
                exported_rows += 1
        return exported_rows

    def _current_table(self) -> QTableWidget | None:
        """Return the table belonging to the active tab."""
        if self._tabs is None:
            return None
        current = self._tabs.currentWidget()
        for result_type, tab in self._tab_by_result_type.items():
            if tab is current:
                return self._table_by_result_type[result_type]
        return None

    def _update_context_message(self, results: dict) -> None:
        """Display contextual notes for cases that need extra explanation."""
        context = results.get("result_context", {}) or {}
        messages: list[str] = []

        surface_count = int(context.get("surface_count", 0) or 0)
        plate_region_count = int(context.get("plate_region_count", 0) or 0)
        surface_results_available = bool(context.get("surface_results_available", False))
        if plate_region_count > 0:
            messages.append(
                self.tr(
                    "Les résultats des plaques utilisateur sont agrégés depuis le "
                    "maillage de calcul interne."
                )
            )
        if surface_count > 0 and not surface_results_available:
            messages.append(
                self.tr(
                    "Les efforts et contraintes de plaques ne sont pas encore affichés "
                    "dans ce panneau."
                )
            )
        elif surface_count > 0:
            messages.append(
                self.tr("Les résultats plaques sont disponibles dans l'onglet Plaques.")
            )
        if surface_count > 0 and bool(context.get("all_nodes_fixed", False)):
            messages.append(
                self.tr(
                    "Tous les nœuds du modèle sont bloqués : les déplacements nodaux "
                    "peuvent donc être nuls, même si les réactions d'appui sont non "
                    "nulles."
                )
            )

        if messages:
            self._info_label.setText(" ".join(messages))
            self._info_label.show()
            return

        self._info_label.clear()
        self._info_label.hide()

    # -- Table helpers --------------------------------------------------------

    @staticmethod
    def _prepare_table(table: QTableWidget, headers: list[str], row_count: int) -> None:
        table.setSortingEnabled(False)
        table.clearContents()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(row_count)

    @staticmethod
    def _finish_table(table: QTableWidget) -> None:
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        table.setSortingEnabled(True)
        table.sortItems(0, Qt.AscendingOrder)
