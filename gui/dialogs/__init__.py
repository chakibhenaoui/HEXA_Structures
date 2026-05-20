"""Utilitaires partagés par les dialogues GUI."""

from __future__ import annotations

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QWidget
from gui.resources import app_resource_path


def load_dialog_ui(dialog: QDialog, ui_filename: str) -> QWidget:
    """Charge un .ui et transfère son layout sur ``dialog``.

    Le .ui est chargé comme un QWidget top-level puis son layout (et donc
    tous ses enfants) est réattribué au ``dialog`` appelant. Cela évite
    le piège du ``QDialog`` imbriqué (sizeHint (0,0)) tout en conservant
    l'accès aux widgets nommés via ``self.ui.<objectName>``.

    Args:
        dialog: Instance de QDialog qui recevra le layout.
        ui_filename: Nom du fichier .ui (relatif à gui/ui/).

    Returns:
        Le widget chargé par QUiLoader (pour accéder aux enfants par nom
        via ``ui.<objectName>``).
    """
    ui_path = app_resource_path("gui", "ui", ui_filename)
    loader = QUiLoader()
    file = QFile(ui_path)
    if not file.open(QIODevice.ReadOnly):
        raise RuntimeError(f"Unable to open/read ui device: {ui_path}")
    ui = loader.load(file)
    file.close()

    dialog.setWindowTitle(ui.windowTitle())

    # Propager les contraintes de taille (utile pour min/maxWidth définis
    # dans le .ui).
    hint = ui.sizeHint()
    min_hint = ui.minimumSizeHint()
    if min_hint.isValid() and not min_hint.isEmpty():
        dialog.setMinimumSize(min_hint)
    if hint.isValid() and not hint.isEmpty():
        dialog.resize(hint)

    layout = ui.layout()
    if layout is not None:
        dialog.setLayout(layout)
        # Après le transfert, les widgets sont enfants du ``dialog`` dans
        # l'arbre Qt ; ``ui.findChild`` ne les trouve plus. On délègue donc
        # les recherches à ``dialog`` tout en conservant l'accès via
        # ``ui.<objectName>`` (attributs Python posés par QUiLoader).
        ui.findChild = dialog.findChild  # type: ignore[assignment]
        ui.findChildren = dialog.findChildren  # type: ignore[assignment]

    return ui
