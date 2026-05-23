"""Node creation and editing dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)


class NodeDialog(QDialog):
    """Node dialog."""

    def __init__(
        self,
        parent=None,
        *,
        node_tag: int,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        allow_tag_edit: bool = False,
        edit_existing: bool = False,
        forbidden_tags: set[int] | None = None,
    ) -> None:
        super().__init__(parent)
        self._allow_tag_edit = allow_tag_edit
        self._forbidden_tags = set(forbidden_tags or set())

        self.setWindowTitle(
            "Modifier le nœud sélectionné" if edit_existing else "Ajouter un nœud"
        )

        layout = QVBoxLayout(self)

        info = QLabel(
            "Le numéro du nœud est verrouillé à l'ajout."
            if not allow_tag_edit
            else "Le numéro du nœud peut être changé s'il n'existe pas déjà."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        layout.addLayout(form)

        self._spn_tag = QSpinBox(self)
        self._spn_tag.setRange(1, 1_000_000)
        self._spn_tag.setValue(int(node_tag))
        self._spn_tag.setEnabled(allow_tag_edit)
        form.addRow("Nœud", self._spn_tag)

        self._spn_x = self._make_coord_spin(x)
        self._spn_y = self._make_coord_spin(y)
        self._spn_z = self._make_coord_spin(z)
        form.addRow("X (m)", self._spn_x)
        form.addRow("Y (m)", self._spn_y)
        form.addRow("Z (m)", self._spn_z)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        self._buttons.button(QDialogButtonBox.Ok).setText(
            "Appliquer" if edit_existing else "Ajouter"
        )
        self._buttons.accepted.connect(self._validate)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    @staticmethod
    def _make_coord_spin(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(6)
        spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        spin.setSingleStep(0.1)
        spin.setValue(float(value))
        return spin

    def _validate(self) -> None:
        tag = int(self._spn_tag.value())
        if self._allow_tag_edit and tag in self._forbidden_tags:
            QMessageBox.warning(
                self,
                "Nœud existant",
                f"Le numéro N{tag} existe déjà. Choisissez un autre numéro.",
            )
            self._spn_tag.setFocus()
            self._spn_tag.selectAll()
            return
        self.accept()

    def result(self) -> dict[str, float | int]:
        """Handle result."""
        return {
            "tag": int(self._spn_tag.value()),
            "x": float(self._spn_x.value()),
            "y": float(self._spn_y.value()),
            "z": float(self._spn_z.value()),
        }
