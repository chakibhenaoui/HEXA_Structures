"""Dialog loading helpers."""

from __future__ import annotations

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QWidget
from gui.resources import app_resource_path


def load_dialog_ui(dialog: QDialog, ui_filename: str) -> QWidget:
    """Load dialog UI."""
    ui_path = app_resource_path("gui", "ui", ui_filename)
    loader = QUiLoader()
    file = QFile(ui_path)
    if not file.open(QIODevice.ReadOnly):
        raise RuntimeError(f"Unable to open/read ui device: {ui_path}")
    ui = loader.load(file)
    file.close()

    dialog.setWindowTitle(ui.windowTitle())

    # Propagate size constraints (useful for min/maxWidth values defined
    # in the .ui file).
    hint = ui.sizeHint()
    min_hint = ui.minimumSizeHint()
    if min_hint.isValid() and not min_hint.isEmpty():
        dialog.setMinimumSize(min_hint)
    if hint.isValid() and not hint.isEmpty():
        dialog.resize(hint)

    layout = ui.layout()
    if layout is not None:
        dialog.setLayout(layout)
        # After transfer, widgets are children of ``dialog`` in
        # the Qt tree; ``ui.findChild`` no longer finds them. Delegate
        # lookups to ``dialog`` while keeping access through
        # ``ui.<objectName>`` (Python attributes set by QUiLoader).
        ui.findChild = dialog.findChild  # type: ignore[assignment]
        ui.findChildren = dialog.findChildren  # type: ignore[assignment]

    return ui
