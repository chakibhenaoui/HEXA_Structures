"""Editable node and combination tables."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.model_data import ProjectModel


# ═══════════════════════════════════════════════════════════════════════════
#  Node table
# ═══════════════════════════════════════════════════════════════════════════


class NodeTableWidget(QWidget):
    """Editable node table widget."""

    model_changed = Signal()

    _HEADERS = ["Tag", "X (m)", "Y (m)", "Z (m)",
                "Ux", "Uy", "Uz", "Rx", "Ry", "Rz"]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._project: ProjectModel | None = None
        self._refreshing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        self._table.setColumnCount(len(self._HEADERS))
        self._table.setHorizontalHeaderLabels(self._HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents,
        )
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

    # -- Refresh -------------------------------------------------------------

    def refresh(self, project: ProjectModel) -> None:
        """Handle refresh."""
        self._project = project
        self._refreshing = True
        self._table.setRowCount(0)

        sorted_tags = sorted(project.nodes.keys())
        self._table.setRowCount(len(sorted_tags))

        for row, tag in enumerate(sorted_tags):
            node = project.nodes[tag]

            # Tag (lecture seule)
            item_tag = QTableWidgetItem(f"N{tag}")
            item_tag.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item_tag.setData(Qt.UserRole, tag)
            self._table.setItem(row, 0, item_tag)

            # X, Y, Z coordinates
            for col, val in enumerate((node.x, node.y, node.z), start=1):
                spin = QDoubleSpinBox()
                spin.setRange(-1e6, 1e6)
                spin.setDecimals(3)
                spin.setValue(val)
                spin.setSuffix(" m")
                spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
                axis = col - 1  # 0=x, 1=y, 2=z
                spin.valueChanged.connect(partial(self._on_coord_changed, tag, axis))
                self._table.setCellWidget(row, col, spin)

            # Ux...Rz fixities (centered checkboxes)
            for dof_idx in range(6):
                cb = QCheckBox()
                cb.setChecked(bool(node.fixities[dof_idx]))
                cb.stateChanged.connect(partial(self._on_fixity_changed, tag, dof_idx))
                # Centrer la checkbox
                container = QWidget()
                h = QHBoxLayout(container)
                h.addWidget(cb)
                h.setAlignment(Qt.AlignCenter)
                h.setContentsMargins(0, 0, 0, 0)
                self._table.setCellWidget(row, 4 + dof_idx, container)

        self._refreshing = False

    # -- Editing callbacks --------------------------------------------------

    def _on_coord_changed(self, tag: int, axis: int, value: float) -> None:
        if self._refreshing or self._project is None:
            return
        node = self._project.nodes.get(tag)
        if node is None:
            return
        if axis == 0:
            node.x = value
        elif axis == 1:
            node.y = value
        else:
            node.z = value
        self.model_changed.emit()

    def _on_fixity_changed(self, tag: int, dof_idx: int, _state: int) -> None:
        if self._refreshing or self._project is None:
            return
        node = self._project.nodes.get(tag)
        if node is None:
            return
        fix = list(node.fixities)
        fix[dof_idx] = 1 if _state == Qt.Checked.value else 0
        node.fixities = tuple(fix)
        self.model_changed.emit()


# ═══════════════════════════════════════════════════════════════════════════
#  Tableau des combinaisons
# ═══════════════════════════════════════════════════════════════════════════


class CombinationTableWidget(QWidget):
    """Combination table widget."""

    model_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._project: ProjectModel | None = None
        self._refreshing = False
        self._load_tags: list[int] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Barre de boutons
        btn_bar = QHBoxLayout()
        self._btn_delete = QPushButton("Supprimer la sélection")
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_delete.setEnabled(False)
        btn_bar.addWidget(self._btn_delete)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

    # -- Refresh -------------------------------------------------------------

    def refresh(self, project: ProjectModel) -> None:
        """Handle refresh."""
        self._project = project
        self._refreshing = True
        self._table.blockSignals(True)

        # Dynamic columns by load case
        self._load_tags = sorted(project.loads.keys())
        fixed_cols = ["Tag", "Nom", "Type"]
        load_headers = [
            f"{project.loads[lt].name} (T{lt})" for lt in self._load_tags
        ]
        headers = fixed_cols + load_headers

        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(0)

        sorted_combos = sorted(project.combinations.keys())
        self._table.setRowCount(len(sorted_combos))

        for row, ctag in enumerate(sorted_combos):
            combo = project.combinations[ctag]

            # Tag (lecture seule)
            item_tag = QTableWidgetItem(str(ctag))
            item_tag.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item_tag.setData(Qt.UserRole, ctag)
            self._table.setItem(row, 0, item_tag)

            # Name (editable)
            item_name = QTableWidgetItem(combo.name)
            item_name.setData(Qt.UserRole, ctag)
            self._table.setItem(row, 1, item_name)

            # Type (lecture seule)
            item_type = QTableWidgetItem(combo.combo_type)
            item_type.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._table.setItem(row, 2, item_type)

            # Factors by load case
            for col_offset, lt in enumerate(self._load_tags):
                factor = combo.factors.get(lt, 0.0)
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 99.99)
                spin.setDecimals(2)
                spin.setValue(factor)
                spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
                spin.valueChanged.connect(
                    partial(self._on_factor_changed, ctag, lt)
                )
                self._table.setCellWidget(row, 3 + col_offset, spin)

        # Adjust columns
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents,
        )

        self._table.blockSignals(False)
        self._refreshing = False

    # -- Editing callbacks --------------------------------------------------

    def _on_factor_changed(self, combo_tag: int, load_tag: int, value: float) -> None:
        if self._refreshing or self._project is None:
            return
        combo = self._project.combinations.get(combo_tag)
        if combo is None:
            return
        if value > 0:
            combo.factors[load_tag] = value
        else:
            combo.factors.pop(load_tag, None)
        self.model_changed.emit()

    def _on_cell_changed(self, row: int, col: int) -> None:
        """Handle cell changed."""
        if self._refreshing or self._project is None:
            return
        if col != 1:
            return
        item = self._table.item(row, col)
        if item is None:
            return
        tag_item = self._table.item(row, 0)
        if tag_item is None:
            return
        ctag = tag_item.data(Qt.UserRole)
        combo = self._project.combinations.get(ctag)
        if combo is None:
            return
        new_name = item.text().strip()
        if new_name:
            combo.name = new_name
            self.model_changed.emit()

    def _on_selection_changed(self) -> None:
        """Handle selection changed."""
        self._btn_delete.setEnabled(len(self._table.selectedItems()) > 0)

    def _delete_selected(self) -> None:
        """Delete selected."""
        if self._project is None:
            return

        # Retrieve tags from selected rows
        selected_rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True,
        )
        if not selected_rows:
            return

        tags_to_delete = []
        for row in selected_rows:
            tag_item = self._table.item(row, 0)
            if tag_item is not None:
                tags_to_delete.append(tag_item.data(Qt.UserRole))

        n = len(tags_to_delete)
        reply = QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer {n} combinaison(s) sélectionnée(s) ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for tag in tags_to_delete:
            self._project.combinations.pop(tag, None)

        self.refresh(self._project)
        self.model_changed.emit()
