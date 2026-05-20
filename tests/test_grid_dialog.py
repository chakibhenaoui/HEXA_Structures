from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QApplication, QPushButton, QDoubleSpinBox, QStyleOptionViewItem

from core.model_data import Grid3DData
from gui.dialogs.grid_dlg import GridDialog


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_grid_dialog_can_default_to_enabled_without_showing_grid_in_model() -> None:
    _app()
    dlg = GridDialog(grid=Grid3DData(enabled=False), default_enabled=True)

    assert dlg.chk_enabled.isChecked() is True
    assert dlg.table_x.item(0, 1).text() == "0,00"
    assert dlg.table_y.item(0, 1).text() == "0,00"
    assert dlg.table_z.item(0, 1).text() == "0,00"
    assert dlg.table_x.item(1, 1).text() == ""


def test_grid_dialog_exposes_add_buttons_for_each_axis() -> None:
    _app()
    dlg = GridDialog(grid=Grid3DData(enabled=False))

    labels = [button.text() for button in dlg.findChildren(QPushButton)]
    assert labels.count("Ajouter une ligne") == 3


def test_coordinate_column_rejects_letters() -> None:
    _app()
    dlg = GridDialog(grid=Grid3DData(enabled=False))

    delegate = dlg.table_x.itemDelegateForColumn(1)
    index = dlg.table_x.model().index(0, 1)
    editor = delegate.createEditor(dlg.table_x, QStyleOptionViewItem(), index)
    assert isinstance(editor, QDoubleSpinBox)
    assert editor.decimals() == 2

    assert editor.validate("abc", 0)[0] == QValidator.Invalid
    assert editor.validate("12,5", 0)[0] == QValidator.Acceptable
    assert editor.text() == "0,00"


def test_coordinate_delegate_formats_value_with_two_decimals() -> None:
    _app()
    dlg = GridDialog(grid=Grid3DData(enabled=False))

    delegate = dlg.table_x.itemDelegateForColumn(1)
    index = dlg.table_x.model().index(0, 1)
    editor = delegate.createEditor(dlg.table_x, QStyleOptionViewItem(), index)
    delegate.setEditorData(editor, index)
    editor.setValue(12.5)
    delegate.setModelData(editor, dlg.table_x.model(), index)

    assert dlg.table_x.item(0, 1).text() == "12,50"


def test_axis_table_delete_removes_row_from_initial_block() -> None:
    _app()
    dlg = GridDialog(grid=Grid3DData(enabled=False))

    dlg.table_x.setCurrentCell(0, 0)
    assert dlg.table_x.remove_current_or_selected_row() is True

    assert dlg.table_x.rowCount() == 4
    assert dlg.lbl_axes.text().startswith("X : 0 axes")
    assert "Grille incomplète" in dlg.lbl_mode.text()


def test_axis_table_delete_removes_extra_row_above_minimum() -> None:
    _app()
    dlg = GridDialog(grid=Grid3DData(enabled=False))

    extra_row = dlg.table_z.add_empty_row()
    dlg.table_z.setCurrentCell(extra_row, 0)
    assert dlg.table_z.remove_current_or_selected_row() is True

    assert dlg.table_z.rowCount() == 5
