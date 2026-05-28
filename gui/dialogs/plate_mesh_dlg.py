"""Plate mesh settings dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


class PlateMeshDialog(QDialog):
    """Edit macro plate mesh divisions in one dialog."""

    def __init__(
        self,
        parent,
        *,
        mesh_nx: int,
        mesh_ny: int,
        plate_tag: int | None = None,
    ) -> None:
        super().__init__(parent)
        suffix = f" P{plate_tag}" if plate_tag is not None else ""
        self.setWindowTitle(
            self.tr("Maillage plaque{suffix}").format(suffix=suffix)
        )
        self.setMinimumWidth(320)

        root = QVBoxLayout(self)
        note = QLabel(self.tr("Nombre de mailles du maillage structure local."), self)
        note.setWordWrap(True)
        root.addWidget(note)

        form = QFormLayout()
        self.spin_nx = QSpinBox(self)
        self.spin_nx.setRange(1, 200)
        self.spin_nx.setValue(max(1, int(mesh_nx)))
        self.spin_ny = QSpinBox(self)
        self.spin_ny.setRange(1, 200)
        self.spin_ny.setValue(max(1, int(mesh_ny)))
        form.addRow(self.tr("Mailles en X local :"), self.spin_nx)
        form.addRow(self.tr("Mailles en Y local :"), self.spin_ny)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> tuple[int, int]:
        """Return selected mesh divisions."""
        return int(self.spin_nx.value()), int(self.spin_ny.value())
