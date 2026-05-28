"""Selected geometry copy dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class CopySelectionDialog(QDialog):
    """Copy selection dialog."""

    PICK_ORIGIN_CODE = 2

    def __init__(
        self,
        parent=None,
        *,
        base_point: tuple[float, float, float],
        node_count: int,
        element_count: int,
        surface_count: int = 0,
        initial_values: dict[str, float | int | str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._base_point = tuple(float(value) for value in base_point)
        self._syncing_fields = False

        initial = dict(initial_values or {})
        mode = str(initial.get("mode", "coordinates"))
        target_x = float(initial.get("target_x", self._base_point[0]))
        target_y = float(initial.get("target_y", self._base_point[1]))
        target_z = float(initial.get("target_z", self._base_point[2]))
        dx = float(initial.get("dx", target_x - self._base_point[0]))
        dy = float(initial.get("dy", target_y - self._base_point[1]))
        dz = float(initial.get("dz", target_z - self._base_point[2]))
        copies = int(initial.get("copies", 1))

        self.setWindowTitle(self.tr("Copier la sélection"))

        layout = QVBoxLayout(self)

        info = QLabel(
            (
                self.tr(
                    "Sélection à copier : {nodes} nœud(s), {elements} barre(s), "
                    "{surfaces} surface(s).\n\n"
                    "L'origine de référence correspond au point bas-gauche de la sélection "
                    "(Z minimum, puis X minimum, puis Y minimum)."
                ).format(
                    nodes=node_count,
                    elements=element_count,
                    surfaces=surface_count,
                )
            ),
            self,
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        group_base = QGroupBox(self.tr("Origine de référence de la sélection"), self)
        base_form = QFormLayout(group_base)
        base_form.addRow(self.tr("X (m)"), QLabel(f"{self._base_point[0]:.6f}", group_base))
        base_form.addRow(self.tr("Y (m)"), QLabel(f"{self._base_point[1]:.6f}", group_base))
        base_form.addRow(self.tr("Z (m)"), QLabel(f"{self._base_point[2]:.6f}", group_base))
        layout.addWidget(group_base)

        self._tabs = QTabWidget(self)
        layout.addWidget(self._tabs)

        tab_coordinates = QWidget(self)
        coordinates_layout = QVBoxLayout(tab_coordinates)
        coordinates_layout.setContentsMargins(0, 0, 0, 0)
        coordinates_form = QFormLayout()
        self._spn_target_x = self._make_coord_spin(target_x)
        self._spn_target_y = self._make_coord_spin(target_y)
        self._spn_target_z = self._make_coord_spin(target_z)
        coordinates_form.addRow(self.tr("X point d'arrivée (m)"), self._spn_target_x)
        coordinates_form.addRow(self.tr("Y point d'arrivée (m)"), self._spn_target_y)
        coordinates_form.addRow(self.tr("Z point d'arrivée (m)"), self._spn_target_z)
        coordinates_layout.addLayout(coordinates_form)
        pick_row = QHBoxLayout()
        pick_row.addStretch(1)
        self._btn_pick_origin = QPushButton(self.tr("Choisir arrivée"), tab_coordinates)
        self._btn_pick_origin.clicked.connect(self._request_pick_origin)
        pick_row.addWidget(self._btn_pick_origin)
        coordinates_layout.addLayout(pick_row)
        self._tabs.addTab(tab_coordinates, self.tr("Coordonnées"))

        tab_delta = QWidget(self)
        delta_layout = QVBoxLayout(tab_delta)
        delta_layout.setContentsMargins(0, 0, 0, 0)
        delta_form = QFormLayout()
        self._spn_dx = self._make_coord_spin(dx)
        self._spn_dy = self._make_coord_spin(dy)
        self._spn_dz = self._make_coord_spin(dz)
        delta_form.addRow(self.tr("Delta X (m)"), self._spn_dx)
        delta_form.addRow(self.tr("Delta Y (m)"), self._spn_dy)
        delta_form.addRow(self.tr("Delta Z (m)"), self._spn_dz)
        delta_layout.addLayout(delta_form)
        delta_note = QLabel(
            (
                self.tr(
                    "Le delta est appliqué depuis l'origine de référence bas-gauche, "
                    "puis répété entre chaque copie successive."
                )
            ),
            tab_delta,
        )
        delta_note.setWordWrap(True)
        delta_layout.addWidget(delta_note)
        self._tabs.addTab(tab_delta, self.tr("Delta"))

        copies_group = QGroupBox(self.tr("Copies"), self)
        copies_form = QFormLayout(copies_group)
        self._spn_count = QSpinBox(self)
        self._spn_count.setRange(1, 1000)
        self._spn_count.setValue(max(1, copies))
        copies_form.addRow(self.tr("Nombre de copies"), self._spn_count)
        layout.addWidget(copies_group)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        self._buttons.button(QDialogButtonBox.Ok).setText(self.tr("Copier"))
        self._buttons.accepted.connect(self._validate)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._spn_target_x.valueChanged.connect(self._sync_delta_from_target)
        self._spn_target_y.valueChanged.connect(self._sync_delta_from_target)
        self._spn_target_z.valueChanged.connect(self._sync_delta_from_target)
        self._spn_dx.valueChanged.connect(self._sync_target_from_delta)
        self._spn_dy.valueChanged.connect(self._sync_target_from_delta)
        self._spn_dz.valueChanged.connect(self._sync_target_from_delta)

        self._set_mode(mode if mode in {"coordinates", "delta"} else "coordinates")
        if self._mode() == "delta":
            self._sync_target_from_delta()
        else:
            self._sync_delta_from_target()

    @staticmethod
    def _make_coord_spin(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(6)
        spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        spin.setSingleStep(0.1)
        spin.setValue(float(value))
        return spin

    def _set_mode(self, mode: str) -> None:
        self._tabs.setCurrentIndex(0 if mode == "coordinates" else 1)

    def _mode(self) -> str:
        return "coordinates" if self._tabs.currentIndex() == 0 else "delta"

    def _request_pick_origin(self) -> None:
        self.done(self.PICK_ORIGIN_CODE)

    def set_picked_origin(self, point: tuple[float, float, float]) -> None:
        """Set picked origin."""
        self._set_mode("coordinates")
        self._syncing_fields = True
        try:
            self._spn_target_x.setValue(float(point[0]))
            self._spn_target_y.setValue(float(point[1]))
            self._spn_target_z.setValue(float(point[2]))
        finally:
            self._syncing_fields = False
        self._sync_delta_from_target()

    def _sync_delta_from_target(self) -> None:
        """Synchronize delta from target."""
        if self._syncing_fields:
            return
        self._syncing_fields = True
        try:
            self._spn_dx.setValue(self._spn_target_x.value() - self._base_point[0])
            self._spn_dy.setValue(self._spn_target_y.value() - self._base_point[1])
            self._spn_dz.setValue(self._spn_target_z.value() - self._base_point[2])
        finally:
            self._syncing_fields = False

    def _sync_target_from_delta(self) -> None:
        """Synchronize target from delta."""
        if self._syncing_fields:
            return
        self._syncing_fields = True
        try:
            self._spn_target_x.setValue(self._base_point[0] + self._spn_dx.value())
            self._spn_target_y.setValue(self._base_point[1] + self._spn_dy.value())
            self._spn_target_z.setValue(self._base_point[2] + self._spn_dz.value())
        finally:
            self._syncing_fields = False

    def _validate(self) -> None:
        dx = float(self._spn_dx.value())
        dy = float(self._spn_dy.value())
        dz = float(self._spn_dz.value())
        if abs(dx) <= 1e-12 and abs(dy) <= 1e-12 and abs(dz) <= 1e-12:
            if self._mode() == "coordinates":
                message = (
                    self.tr(
                        "Choisissez une origine de copie différente de l'origine "
                        "de référence, ou changez d'onglet vers Delta."
                    )
                )
                self._spn_target_x.setFocus()
                self._spn_target_x.selectAll()
            else:
                message = self.tr("Saisissez un delta différent de zéro.")
                self._spn_dx.setFocus()
                self._spn_dx.selectAll()
            QMessageBox.warning(self, self.tr("Déplacement nul"), message)
            return
        self.accept()

    def values(self) -> dict[str, float | int | str]:
        """Handle values."""
        return {
            "mode": self._mode(),
            "target_x": float(self._spn_target_x.value()),
            "target_y": float(self._spn_target_y.value()),
            "target_z": float(self._spn_target_z.value()),
            "dx": float(self._spn_dx.value()),
            "dy": float(self._spn_dy.value()),
            "dz": float(self._spn_dz.value()),
            "copies": int(self._spn_count.value()),
        }
