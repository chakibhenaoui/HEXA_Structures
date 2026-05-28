"""Boundary condition dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QWidget

from core.boundary_conditions import (
    BoundaryCondition,
    BoundaryType,
    DOF,
    DOF_SHORT,
    PREDEFINED_FIXITIES,
    SpringStiffness,
    detect_boundary_type,
)
from gui.dialogs import load_dialog_ui


class BoundaryDialog(QDialog):
    """Boundary condition dialog."""

    # Mapping DOF enum -> .ui checkbox objectName
    _DOF_WIDGET_NAMES: dict[DOF, str] = {
        DOF.UX: "checkUx",
        DOF.UY: "checkUy",
        DOF.UZ: "checkUz",
        DOF.RX: "checkRx",
        DOF.RY: "checkRy",
        DOF.RZ: "checkRz",
    }

    # Mapping spring key -> .ui spinbox objectName
    _SPRING_WIDGET_NAMES: dict[str, str] = {
        "kx": "spinKx",
        "ky": "spinKy",
        "kz": "spinKz",
        "krx": "spinKrx",
        "kry": "spinKry",
        "krz": "spinKrz",
    }

    def __init__(self, parent: QWidget | None = None,
                 current: BoundaryCondition | None = None):
        super().__init__(parent)

        self.ui = load_dialog_ui(self, "boundary_dlg.ui")

        # --- Build widget references ---
        self._dof_checks: dict[DOF, object] = {
            dof: getattr(self.ui, name)
            for dof, name in self._DOF_WIDGET_NAMES.items()
        }
        self._spring_spins: dict[str, object] = {
            key: getattr(self.ui, name)
            for key, name in self._SPRING_WIDGET_NAMES.items()
        }

        # --- Populate combo box dynamically from enum ---
        self.ui.comboType.setMaxVisibleItems(len(BoundaryType))
        for bc_type in BoundaryType:
            self.ui.comboType.addItem(self._boundary_label(bc_type), bc_type)

        # --- Connect signals ---
        self.ui.comboType.currentIndexChanged.connect(self._on_type_changed)
        for cb in self._dof_checks.values():
            cb.stateChanged.connect(self._on_dof_changed)
        self.ui.buttonBox.accepted.connect(self.accept)
        self.ui.buttonBox.rejected.connect(self.reject)

        self._current = current
        if current:
            self._load_from(current)
        else:
            self._on_type_changed(self.ui.comboType.currentIndex())

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_type_changed(self, index: int) -> None:
        """Handle type changed."""
        bc_type = self.ui.comboType.currentData()
        if bc_type == BoundaryType.CUSTOM:
            for cb in self._dof_checks.values():
                cb.setEnabled(True)
            self._update_summary()
            return

        fixities = PREDEFINED_FIXITIES[bc_type]
        for dof, cb in self._dof_checks.items():
            cb.blockSignals(True)
            cb.setChecked(bool(fixities[dof.value]))
            cb.setEnabled(False)
            cb.blockSignals(False)

        self._update_summary()

    def _boundary_label(self, bc_type: BoundaryType) -> str:
        labels = {
            BoundaryType.FREE: self.tr("Libre"),
            BoundaryType.ENCASTREMENT: self.tr("Encastrement"),
            BoundaryType.ROTULE: self.tr("Rotule (appui simple)"),
            BoundaryType.GLISSANT_X: self.tr("Appui glissant X"),
            BoundaryType.GLISSANT_Y: self.tr("Appui glissant Y"),
            BoundaryType.GLISSANT_Z: self.tr("Appui glissant Z"),
            BoundaryType.APPUI_VERTICAL: self.tr("Appui vertical (Uz)"),
            BoundaryType.APPUI_PLAN_XY: self.tr("Appui plan XY (dalle)"),
            BoundaryType.ROTULE_GLISSIERE: self.tr("Rotule sur glissière (X)"),
            BoundaryType.BLOCAGE_ROTATION: self.tr("Blocage rotation seule"),
            BoundaryType.CUSTOM: self.tr("Personnalisé"),
        }
        return labels.get(bc_type, bc_type.value)

    def _on_dof_changed(self) -> None:
        """Handle DOF changed."""
        bc_type = self.ui.comboType.currentData()
        if bc_type != BoundaryType.CUSTOM:
            current_fix = tuple(
                int(self._dof_checks[dof].isChecked()) for dof in DOF
            )
            expected = PREDEFINED_FIXITIES.get(bc_type, (0,) * 6)
            if current_fix != expected:
                self.ui.comboType.blockSignals(True)
                idx = self.ui.comboType.findData(BoundaryType.CUSTOM)
                self.ui.comboType.setCurrentIndex(idx)
                for cb in self._dof_checks.values():
                    cb.setEnabled(True)
                self.ui.comboType.blockSignals(False)

        self._update_summary()

    def _update_summary(self) -> None:
        """Update summary."""
        blocked = []
        for dof in DOF:
            if self._dof_checks[dof].isChecked():
                blocked.append(DOF_SHORT[dof])

        lbl = self.ui.labelSummary
        if not blocked:
            lbl.setText(self.tr("Nœud libre (aucun blocage)"))
            lbl.setStyleSheet("font-weight: bold; color: #888;")
        elif len(blocked) == 6:
            lbl.setText(self.tr("Encastrement (tout bloqué)"))
            lbl.setStyleSheet("font-weight: bold; color: #d32f2f;")
        else:
            lbl.setText(self.tr("Bloqué : {dof}").format(dof=", ".join(blocked)))
            lbl.setStyleSheet("font-weight: bold; color: #0078d4;")

    # ------------------------------------------------------------------
    # Load / Result
    # ------------------------------------------------------------------

    def _load_from(self, bc: BoundaryCondition) -> None:
        """Load from."""
        idx = self.ui.comboType.findData(bc.bc_type)
        if idx >= 0:
            self.ui.comboType.setCurrentIndex(idx)

        for dof in DOF:
            fix_val = bc.fixities[dof.value] if dof.value < len(bc.fixities) else 0
            self._dof_checks[dof].setChecked(bool(fix_val))

        if bc.springs.has_springs:
            self.ui.groupSpring.setChecked(True)
            s = bc.springs
            self._spring_spins["kx"].setValue(s.kx)
            self._spring_spins["ky"].setValue(s.ky)
            self._spring_spins["kz"].setValue(s.kz)
            self._spring_spins["krx"].setValue(s.krx)
            self._spring_spins["kry"].setValue(s.kry)
            self._spring_spins["krz"].setValue(s.krz)

        self._update_summary()

    def result(self) -> BoundaryCondition:
        """Handle result."""
        bc_type = self.ui.comboType.currentData()
        fixities = tuple(
            int(self._dof_checks[dof].isChecked()) for dof in DOF
        )
        if bc_type != BoundaryType.CUSTOM:
            expected = PREDEFINED_FIXITIES.get(bc_type, (0,) * 6)
            if fixities != expected:
                bc_type = detect_boundary_type(fixities)

        springs = SpringStiffness()
        if self.ui.groupSpring.isChecked():
            springs = SpringStiffness(
                kx=self._spring_spins["kx"].value(),
                ky=self._spring_spins["ky"].value(),
                kz=self._spring_spins["kz"].value(),
                krx=self._spring_spins["krx"].value(),
                kry=self._spring_spins["kry"].value(),
                krz=self._spring_spins["krz"].value(),
            )

        return BoundaryCondition(
            bc_type=bc_type,
            fixities=fixities,
            springs=springs,
        )
