"""Grid definition dialog."""

from __future__ import annotations

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.model_data import Grid3DData, GridAxisEntry


class CoordinateItemDelegate(QStyledItemDelegate):
    """Coordinate item delegate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._locale = QLocale(QLocale.French, QLocale.France)

    def createEditor(self, parent, option, index):  # noqa: N802 - Qt API
        editor = QDoubleSpinBox(parent)
        editor.setLocale(self._locale)
        editor.setDecimals(2)
        editor.setRange(-1_000_000_000.0, 1_000_000_000.0)
        editor.setSingleStep(0.05)
        editor.setButtonSymbols(QDoubleSpinBox.NoButtons)
        editor.setAccelerated(True)
        editor.setFrame(False)
        return editor

    def setEditorData(self, editor, index):  # noqa: N802 - Qt API
        if isinstance(editor, QDoubleSpinBox):
            value = str(index.data(Qt.EditRole) or "").strip()
            if value:
                try:
                    number = self._locale.toDouble(value)[0]
                except Exception:
                    number = float(value.replace(",", "."))
            else:
                number = 0.0
            editor.setValue(number)
            editor.selectAll()
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):  # noqa: N802 - Qt API
        if not isinstance(editor, QDoubleSpinBox):
            super().setModelData(editor, model, index)
            return
        model.setData(index, self._locale.toString(editor.value(), "f", 2))


class AxisGridTable(QTableWidget):
    """Axis grid table."""

    _MIN_ROWS = 5
    table_changed = Signal()
    _LOCALE = QLocale(QLocale.French, QLocale.France)

    def __init__(
        self,
        axis_name: str,
        entries: list[GridAxisEntry],
        parent=None,
    ):
        super().__init__(parent)
        self._axis_name = axis_name
        self._build_ui()
        self._populate(entries)

    def _build_ui(self) -> None:
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels([self.tr("Repère"), self.tr("Coordonnées")])
        self.setItemDelegateForColumn(1, CoordinateItemDelegate(self))
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.verticalHeader().setDefaultSectionSize(26)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        self.setMinimumWidth(260)
        self.setMinimumHeight(220)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_context_menu)

    def _populate(self, entries: list[GridAxisEntry]) -> None:
        self.setRowCount(max(len(entries), self._MIN_ROWS))
        for row, entry in enumerate(entries):
            self._set_row(row, entry.marker, self._format_coordinate(entry.coordinate))
        for row in range(len(entries), self.rowCount()):
            self._set_row(row, f"{self._axis_name}{row + 1}", "")

    @classmethod
    def _format_coordinate(cls, value: float) -> str:
        """Format coordinate."""
        return cls._LOCALE.toString(float(value), "f", 2)

    def _set_row(self, row: int, marker: str, coordinate_text: str) -> None:
        marker_item = self.item(row, 0)
        if marker_item is None:
            marker_item = QTableWidgetItem()
            self.setItem(row, 0, marker_item)
        marker_item.setText(marker)

        coordinate_item = self.item(row, 1)
        if coordinate_item is None:
            coordinate_item = QTableWidgetItem()
            self.setItem(row, 1, coordinate_item)
        coordinate_item.setText(coordinate_text)

    def add_empty_row(self) -> int:
        """Add empty row."""
        new_row = self.rowCount()
        self.insertRow(new_row)
        self._set_row(new_row, f"{self._axis_name}{new_row + 1}", "")
        self.table_changed.emit()
        return new_row

    def remove_current_or_selected_row(self) -> bool:
        """Remove current or selected row."""
        row = self.currentRow()
        if row < 0:
            selected = self.selectedIndexes()
            row = selected[0].row() if selected else -1
        if row < 0 or row >= self.rowCount():
            return False

        self.removeRow(row)

        if self.rowCount() > 0:
            self.setCurrentCell(min(row, self.rowCount() - 1), 0)
        self.table_changed.emit()
        return True

    def _open_context_menu(self, position) -> None:
        """Open context menu."""
        row = self.rowAt(position.y())
        if row >= 0:
            self.setCurrentCell(row, 0)

        menu = QMenu(self)
        add_action = menu.addAction(self.tr("Ajouter une ligne"))
        delete_action = menu.addAction(self.tr("Supprimer la ligne"))
        delete_action.setEnabled(row >= 0 or self.currentRow() >= 0)

        action = menu.exec(self.viewport().mapToGlobal(position))
        if action is add_action:
            new_row = self.add_empty_row()
            self.setCurrentCell(new_row, 1)
            self.editItem(self.item(new_row, 1))
        elif action is delete_action:
            self.remove_current_or_selected_row()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Handle mouse press events."""
        super().mousePressEvent(event)

    def axis_entries(self) -> list[GridAxisEntry]:
        """Handle axis entries."""
        entries: list[GridAxisEntry] = []
        for row in range(self.rowCount()):
            marker_item = self.item(row, 0)
            coordinate_item = self.item(row, 1)
            marker = marker_item.text().strip() if marker_item is not None else ""
            coordinate_text = (
                coordinate_item.text().strip() if coordinate_item is not None else ""
            )
            if not coordinate_text:
                continue
            coordinate, ok = self._LOCALE.toDouble(coordinate_text)
            if not ok:
                raise ValueError(
                    self.tr(
                        "Axe {axis}, ligne {row} : coordonnée invalide '{value}'."
                    ).format(
                        axis=self._axis_name,
                        row=row + 1,
                        value=coordinate_text,
                    )
                )
            entries.append(
                GridAxisEntry(
                    marker=marker or f"{self._axis_name}{len(entries) + 1}",
                    coordinate=coordinate,
                )
            )
        return entries

    def valid_coordinate_count(self) -> int:
        """Handle valid coordinate count."""
        count = 0
        for row in range(self.rowCount()):
            coordinate_item = self.item(row, 1)
            coordinate_text = (
                coordinate_item.text().strip() if coordinate_item is not None else ""
            )
            if not coordinate_text:
                continue
            _coordinate, ok = self._LOCALE.toDouble(coordinate_text)
            if not ok:
                continue
            count += 1
        return count


class GridDialog(QDialog):
    """Grid definition dialog."""

    def __init__(
        self,
        parent=None,
        *,
        grid: Grid3DData | None = None,
        default_enabled: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Définir la grille 3D"))
        self.resize(920, 430)
        self._grid = grid or Grid3DData()
        self._default_enabled = default_enabled
        self._result_grid = self._grid
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self.chk_enabled = QCheckBox(self.tr("Afficher et utiliser la grille"), self)
        self.chk_enabled.setChecked(self._grid.enabled or self._default_enabled)
        root.addWidget(self.chk_enabled)

        hint = QLabel(
            self.tr(
                "Chaque axe comporte 5 lignes initiales. "
                "Utilisez les boutons pour ajouter ou supprimer une ligne, "
                "ou le clic droit sur une ligne pour la supprimer."
            ),
            self,
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        tables_layout = QHBoxLayout()
        tables_layout.setSpacing(12)
        self.table_x = self._create_axis_group("X", self.tr("Axe X"), self._grid.axis_entries("X"))
        self.table_y = self._create_axis_group("Y", self.tr("Axe Y"), self._grid.axis_entries("Y"))
        self.table_z = self._create_axis_group("Z", self.tr("Axe Z"), self._grid.axis_entries("Z"))
        tables_layout.addWidget(self._group_x, 1)
        tables_layout.addWidget(self._group_y, 1)
        tables_layout.addWidget(self._group_z, 1)
        root.addLayout(tables_layout)

        summary_box = QGroupBox(self.tr("Synthèse"), self)
        summary_layout = QGridLayout(summary_box)
        self.lbl_axes = QLabel(self)
        self.lbl_axes.setWordWrap(True)
        self.lbl_mode = QLabel(self)
        self.lbl_mode.setWordWrap(True)
        summary_layout.addWidget(QLabel(self.tr("Axes :"), self), 0, 0)
        summary_layout.addWidget(self.lbl_axes, 0, 1)
        summary_layout.addWidget(QLabel(self.tr("Mode :"), self), 1, 0)
        summary_layout.addWidget(self.lbl_mode, 1, 1)
        root.addWidget(summary_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        for table in (self.table_x, self.table_y, self.table_z):
            table.itemChanged.connect(self._update_summary)
            table.table_changed.connect(self._update_summary)

        self._update_summary()

    def _create_axis_group(
        self,
        axis_name: str,
        title: str,
        entries: list[GridAxisEntry],
    ) -> AxisGridTable:
        group = QGroupBox(title, self)
        layout = QVBoxLayout(group)
        table = AxisGridTable(axis_name, entries, group)
        layout.addWidget(table)
        actions_layout = QHBoxLayout()
        btn_add = QPushButton(self.tr("Ajouter une ligne"), group)
        btn_add.clicked.connect(
            lambda _checked=False, current_table=table: self._add_row_to_table(current_table)
        )
        actions_layout.addWidget(btn_add)
        btn_delete = QPushButton(self.tr("Supprimer la ligne"), group)
        btn_delete.clicked.connect(
            lambda _checked=False, current_table=table: current_table.remove_current_or_selected_row()
        )
        actions_layout.addWidget(btn_delete)
        actions_layout.addStretch(1)
        layout.addLayout(actions_layout)
        helper = QLabel(self.tr("Colonnes : repère puis coordonnée en mètres."), group)
        helper.setWordWrap(True)
        layout.addWidget(helper)
        if axis_name == "X":
            self._group_x = group
        elif axis_name == "Y":
            self._group_y = group
        else:
            self._group_z = group
        return table

    @staticmethod
    def _add_row_to_table(table: AxisGridTable) -> None:
        """Add row to table."""
        new_row = table.add_empty_row()
        table.setCurrentCell(new_row, 1)
        table.editItem(table.item(new_row, 1))

    def _axis_line_count(self, table: AxisGridTable) -> int:
        return table.valid_coordinate_count()

    def _grid_mode_text(self) -> str:
        """Handle grid mode text."""
        axis_counts = {
            "X": self._axis_line_count(self.table_x),
            "Y": self._axis_line_count(self.table_y),
            "Z": self._axis_line_count(self.table_z),
        }
        if any(count == 0 for count in axis_counts.values()):
            return self.tr("Grille incomplète : chaque axe doit contenir au moins une coordonnée.")

        single_axes = [axis for axis, count in axis_counts.items() if count == 1]
        if len(single_axes) == 0:
            return self.tr("Grille 3D complète.")
        if len(single_axes) == 1:
            axis = single_axes[0]
            plane = {"X": "YZ", "Y": "XZ", "Z": "XY"}[axis]
            return (
                self.tr("Mode 2D détecté : travail conseillé dans le plan {plane} (axe {axis} unique).").format(
                    plane=plane,
                    axis=axis,
                )
            )
        if len(single_axes) == 2:
            return self.tr("Mode 1D détecté : une seule ligne de grille.")
        return self.tr("Mode ponctuel détecté : une seule intersection de grille.")

    def _update_summary(self) -> None:
        """Update summary."""
        axis_counts = {
            "X": self._axis_line_count(self.table_x),
            "Y": self._axis_line_count(self.table_y),
            "Z": self._axis_line_count(self.table_z),
        }
        self.lbl_axes.setText(
            ", ".join(
                self.tr("{axis} : {count} axes").format(axis=axis, count=count)
                for axis, count in axis_counts.items()
            )
        )
        self.lbl_mode.setText(self._grid_mode_text())

    def _collect_result(self) -> Grid3DData:
        x_entries = self.table_x.axis_entries()
        y_entries = self.table_y.axis_entries()
        z_entries = self.table_z.axis_entries()
        if not x_entries or not y_entries or not z_entries:
            raise ValueError(self.tr("Chaque axe doit contenir au moins une coordonnée."))
        return Grid3DData(
            enabled=self.chk_enabled.isChecked(),
            x_items=x_entries,
            y_items=y_entries,
            z_items=z_entries,
        )

    def _accept(self) -> None:
        """Handle accept."""
        try:
            self._result_grid = self._collect_result()
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Grille invalide"), str(exc))
            return
        self.accept()

    def result(self) -> Grid3DData:
        """Handle result."""
        return self._result_grid
