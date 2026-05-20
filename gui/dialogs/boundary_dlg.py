"""
Dialogue de conditions aux limites (appuis).

Permet de sélectionner un type d'appui prédéfini ou de personnaliser
les 6 DDL individuellement. Affiche un résumé des DDL bloqués.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QWidget

from core.boundary_conditions import (
    BoundaryCondition,
    BoundaryType,
    BOUNDARY_LABELS,
    DOF,
    DOF_SHORT,
    PREDEFINED_FIXITIES,
    SpringStiffness,
    detect_boundary_type,
)
from gui.dialogs import load_dialog_ui


class BoundaryDialog(QDialog):
    """Dialogue de sélection des conditions aux limites."""

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
            self.ui.comboType.addItem(BOUNDARY_LABELS[bc_type], bc_type)

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
        """Met à jour les cases DDL selon le type sélectionné."""
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

    def _on_dof_changed(self) -> None:
        """Met à jour le résumé quand un DDL change."""
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
        """Met à jour le texte de résumé."""
        blocked = []
        for dof in DOF:
            if self._dof_checks[dof].isChecked():
                blocked.append(DOF_SHORT[dof])

        lbl = self.ui.labelSummary
        if not blocked:
            lbl.setText("Nœud libre (aucun blocage)")
            lbl.setStyleSheet("font-weight: bold; color: #888;")
        elif len(blocked) == 6:
            lbl.setText("Encastrement (tout bloqué)")
            lbl.setStyleSheet("font-weight: bold; color: #d32f2f;")
        else:
            lbl.setText(f"Bloqué : {', '.join(blocked)}")
            lbl.setStyleSheet("font-weight: bold; color: #0078d4;")

    # ------------------------------------------------------------------
    # Load / Result
    # ------------------------------------------------------------------

    def _load_from(self, bc: BoundaryCondition) -> None:
        """Charge les valeurs depuis une BoundaryCondition existante."""
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
        """Retourne la condition aux limites configurée."""
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
