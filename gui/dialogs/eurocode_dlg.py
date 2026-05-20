"""
Dialogue de paramètres Eurocodes (AN française).

Permet à l'utilisateur de visualiser et modifier les coefficients partiels
(gamma), les coefficients psi par catégorie, et les coefficients matériaux.
Toute modification declenche un avertissement.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

import config.eurocodes as ec
from gui.dialogs import load_dialog_ui


# ── Labels lisibles ──

_PSI_LABELS: dict[str, str] = {
    "A": "A — Habitation",
    "B": "B — Bureaux",
    "C": "C — Lieux de reunion",
    "D": "D — Commerces",
    "E": "E — Stockage",
    "F": "F — Trafic vehicules <= 30 kN",
    "G": "G — Trafic vehicules > 30 kN",
    "H": "H — Toitures",
    "snow": "Neige (alt. <= 1000 m)",
    "snow_high": "Neige (alt. > 1000 m)",
    "wind": "Vent",
    "temp": "Temperature",
}


class EurocodeSettingsDialog(QDialog):
    """Dialogue des paramètres Eurocodes (coefficients partiels et psi)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._modified = False

        self.ui = load_dialog_ui(self, "eurocode_dlg.ui")

        # Grab widget references
        self._spn_gamma_g_sup = self.ui.findChild(QDoubleSpinBox, "spn_gamma_g_sup")
        self._spn_gamma_g_inf = self.ui.findChild(QDoubleSpinBox, "spn_gamma_g_inf")
        self._spn_gamma_q = self.ui.findChild(QDoubleSpinBox, "spn_gamma_q")
        self._spn_gamma_g_acc = self.ui.findChild(QDoubleSpinBox, "spn_gamma_g_acc")
        self._spn_gamma_q_acc = self.ui.findChild(QDoubleSpinBox, "spn_gamma_q_acc")

        self._spn_gamma_c = self.ui.findChild(QDoubleSpinBox, "spn_gamma_c")
        self._spn_alpha_cc = self.ui.findChild(QDoubleSpinBox, "spn_alpha_cc")
        self._spn_gamma_s = self.ui.findChild(QDoubleSpinBox, "spn_gamma_s")

        self._spn_gamma_m0 = self.ui.findChild(QDoubleSpinBox, "spn_gamma_m0")
        self._spn_gamma_m1 = self.ui.findChild(QDoubleSpinBox, "spn_gamma_m1")
        self._spn_gamma_m2 = self.ui.findChild(QDoubleSpinBox, "spn_gamma_m2")

        self._tbl_psi = self.ui.findChild(QTableWidget, "tbl_psi")
        btn_reset = self.ui.findChild(QPushButton, "btn_reset")
        buttons = self.ui.findChild(QDialogButtonBox, "buttons")

        # Configure psi table header
        self._tbl_psi.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        for col in range(1, 4):
            self._tbl_psi.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeToContents
            )

        # Populate psi table rows dynamically
        self._populate_psi_table()

        # Connect signals
        btn_reset.clicked.connect(self._reset_defaults)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        # Load current values
        self._load_values()

    # ── Psi table population ──

    def _populate_psi_table(self) -> None:
        """Populate the psi table rows from ec.PSI_COEFFICIENTS."""
        self._tbl_psi.setRowCount(len(ec.PSI_COEFFICIENTS))
        self._psi_keys: list[str] = []

        for row, (key, (p0, p1, p2)) in enumerate(ec.PSI_COEFFICIENTS.items()):
            self._psi_keys.append(key)
            label = _PSI_LABELS.get(key, key)
            item = QTableWidgetItem(label)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._tbl_psi.setItem(row, 0, item)

            for col, val in enumerate([p0, p1, p2], 1):
                spn = self._make_spin(0.0, 1.0, 2)
                spn.setValue(val)
                self._tbl_psi.setCellWidget(row, col, spn)

    # ── Chargement / sauvegarde ──

    def _load_values(self) -> None:
        """Charge les valeurs actuelles depuis config.eurocodes."""
        self._spn_gamma_g_sup.setValue(ec.GAMMA_G_SUP)
        self._spn_gamma_g_inf.setValue(ec.GAMMA_G_INF)
        self._spn_gamma_q.setValue(ec.GAMMA_Q)
        self._spn_gamma_g_acc.setValue(ec.GAMMA_G_ACCIDENTAL)
        self._spn_gamma_q_acc.setValue(ec.GAMMA_Q_ACCIDENTAL)

        self._spn_gamma_c.setValue(ec.GAMMA_C)
        self._spn_alpha_cc.setValue(ec.ALPHA_CC)
        self._spn_gamma_s.setValue(ec.GAMMA_S)

        self._spn_gamma_m0.setValue(ec.GAMMA_M0)
        self._spn_gamma_m1.setValue(ec.GAMMA_M1)
        self._spn_gamma_m2.setValue(ec.GAMMA_M2)

    def _on_accept(self) -> None:
        """Applique les modifications avec avertissement."""
        if self._has_changes():
            reply = QMessageBox.warning(
                self,
                "Modification des coefficients Eurocodes",
                "Vous êtes sur le point de modifier les coefficients normatifs.\n\n"
                "Ces valeurs sont définies par l'Annexe Nationale Française "
                "et ne doivent être modifiées que dans des cas justifiés "
                "(autre pays, recherche, etc.).\n\n"
                "Confirmer la modification ?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._apply_values()
        self.accept()

    def _has_changes(self) -> bool:
        """Verifie si des valeurs ont été modifiées."""
        if abs(self._spn_gamma_g_sup.value() - ec.GAMMA_G_SUP) > 1e-6:
            return True
        if abs(self._spn_gamma_g_inf.value() - ec.GAMMA_G_INF) > 1e-6:
            return True
        if abs(self._spn_gamma_q.value() - ec.GAMMA_Q) > 1e-6:
            return True
        if abs(self._spn_gamma_g_acc.value() - ec.GAMMA_G_ACCIDENTAL) > 1e-6:
            return True
        if abs(self._spn_gamma_q_acc.value() - ec.GAMMA_Q_ACCIDENTAL) > 1e-6:
            return True
        if abs(self._spn_gamma_c.value() - ec.GAMMA_C) > 1e-6:
            return True
        if abs(self._spn_alpha_cc.value() - ec.ALPHA_CC) > 1e-6:
            return True
        if abs(self._spn_gamma_s.value() - ec.GAMMA_S) > 1e-6:
            return True
        if abs(self._spn_gamma_m0.value() - ec.GAMMA_M0) > 1e-6:
            return True
        if abs(self._spn_gamma_m1.value() - ec.GAMMA_M1) > 1e-6:
            return True
        if abs(self._spn_gamma_m2.value() - ec.GAMMA_M2) > 1e-6:
            return True

        # Psi
        for row, key in enumerate(self._psi_keys):
            old = ec.PSI_COEFFICIENTS[key]
            for col in range(3):
                spn = self._tbl_psi.cellWidget(row, col + 1)
                if abs(spn.value() - old[col]) > 1e-6:
                    return True
        return False

    def _apply_values(self) -> None:
        """Ecrit les nouvelles valeurs dans config.eurocodes (en memoire)."""
        ec.GAMMA_G_SUP = self._spn_gamma_g_sup.value()
        ec.GAMMA_G_INF = self._spn_gamma_g_inf.value()
        ec.GAMMA_Q = self._spn_gamma_q.value()
        ec.GAMMA_G_ACCIDENTAL = self._spn_gamma_g_acc.value()
        ec.GAMMA_Q_ACCIDENTAL = self._spn_gamma_q_acc.value()

        ec.GAMMA_C = self._spn_gamma_c.value()
        ec.ALPHA_CC = self._spn_alpha_cc.value()
        ec.GAMMA_S = self._spn_gamma_s.value()

        ec.GAMMA_M0 = self._spn_gamma_m0.value()
        ec.GAMMA_M1 = self._spn_gamma_m1.value()
        ec.GAMMA_M2 = self._spn_gamma_m2.value()

        # Psi
        for row, key in enumerate(self._psi_keys):
            vals = []
            for col in range(3):
                spn = self._tbl_psi.cellWidget(row, col + 1)
                vals.append(spn.value())
            ec.PSI_COEFFICIENTS[key] = tuple(vals)

    def _reset_defaults(self) -> None:
        """Réinitialise toutes les valeurs aux défauts AN française."""
        self._spn_gamma_g_sup.setValue(1.35)
        self._spn_gamma_g_inf.setValue(1.00)
        self._spn_gamma_q.setValue(1.50)
        self._spn_gamma_g_acc.setValue(1.0)
        self._spn_gamma_q_acc.setValue(1.0)

        self._spn_gamma_c.setValue(1.5)
        self._spn_alpha_cc.setValue(1.0)
        self._spn_gamma_s.setValue(1.15)

        self._spn_gamma_m0.setValue(1.0)
        self._spn_gamma_m1.setValue(1.0)
        self._spn_gamma_m2.setValue(1.25)

        defaults = {
            "A": (0.7, 0.5, 0.3), "B": (0.7, 0.5, 0.3),
            "C": (0.7, 0.7, 0.6), "D": (0.7, 0.7, 0.6),
            "E": (1.0, 0.9, 0.8), "F": (0.7, 0.7, 0.6),
            "G": (0.7, 0.5, 0.3), "H": (0.0, 0.0, 0.0),
            "snow": (0.5, 0.2, 0.0), "snow_high": (0.7, 0.5, 0.2),
            "wind": (0.6, 0.2, 0.0), "temp": (0.6, 0.5, 0.0),
        }
        for row, key in enumerate(self._psi_keys):
            vals = defaults.get(key, (0.7, 0.5, 0.3))
            for col in range(3):
                spn = self._tbl_psi.cellWidget(row, col + 1)
                spn.setValue(vals[col])

    # ── Helpers ──

    @staticmethod
    def _make_spin(min_val: float, max_val: float, decimals: int) -> QDoubleSpinBox:
        spn = QDoubleSpinBox()
        spn.setRange(min_val, max_val)
        spn.setDecimals(decimals)
        spn.setSingleStep(0.05)
        spn.setMaximumWidth(100)
        return spn
