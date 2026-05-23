"""Load combination management dialog."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.loads import (
    ComboType,
    COMBO_LABELS,
    auto_generate_combinations,
    combination_formula,
)
from core.model_data import CombinationData, LoadData
from gui.dialogs import load_dialog_ui


COMBO_TYPES = [
    "ELU",
    "ELS car.",
    "ELS freq.",
    "ELS quasi-perm.",
    "ELU sism.",
    "Manuelle",
]


class CombinationEditDialog(QDialog):
    """Combination edit dialog."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        loads: dict[int, LoadData],
        combo: CombinationData | None = None,
        tag: int | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Modifier la combinaison" if combo else "Nouvelle combinaison")
        self.resize(560, 460)
        self._loads = loads
        self._combo = deepcopy(combo)
        self._tag = combo.tag if combo is not None else int(tag or 1)
        self._factor_spins: dict[int, QDoubleSpinBox] = {}

        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        form = QFormLayout()
        self.edit_name = QLineEdit(self)
        self.combo_type = QComboBox(self)
        for combo_type in COMBO_TYPES:
            self.combo_type.addItem(combo_type, combo_type)
        form.addRow("Nom :", self.edit_name)
        form.addRow("Type :", self.combo_type)
        root.addLayout(form)

        grp = QGroupBox("Facteurs des cas de charge", self)
        grp_lay = QVBoxLayout(grp)
        info = QLabel(
            "Mettre un facteur à 0 pour exclure le cas de charge de la combinaison.",
            grp,
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #607080;")
        grp_lay.addWidget(info)

        scroll = QScrollArea(grp)
        scroll.setWidgetResizable(True)
        container = QWidget(scroll)
        factors_layout = QFormLayout(container)
        for load_tag, load in sorted(self._loads.items()):
            spin = QDoubleSpinBox(container)
            spin.setRange(-99.99, 99.99)
            spin.setDecimals(3)
            spin.setSingleStep(0.05)
            spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
            self._factor_spins[load_tag] = spin
            factors_layout.addRow(f"{load.name} (T{load_tag}) :", spin)
        scroll.setWidget(container)
        grp_lay.addWidget(scroll, 1)
        root.addWidget(grp, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_values(self) -> None:
        """Load values."""
        if self._combo is None:
            self.edit_name.setText(f"Combinaison {self._tag}")
            idx = self.combo_type.findData("Manuelle")
            if idx >= 0:
                self.combo_type.setCurrentIndex(idx)
            return

        self.edit_name.setText(self._combo.name)
        idx = self.combo_type.findData(self._combo.combo_type)
        if idx < 0:
            self.combo_type.addItem(self._combo.combo_type, self._combo.combo_type)
            idx = self.combo_type.findData(self._combo.combo_type)
        if idx >= 0:
            self.combo_type.setCurrentIndex(idx)
        for load_tag, factor in self._combo.factors.items():
            spin = self._factor_spins.get(load_tag)
            if spin is not None:
                spin.setValue(float(factor))

    def _on_accept(self) -> None:
        """Handle accept."""
        name = self.edit_name.text().strip()
        if not name:
            self.edit_name.setFocus()
            return

        factors = {
            load_tag: spin.value()
            for load_tag, spin in self._factor_spins.items()
            if abs(spin.value()) > 1e-12
        }
        if not factors:
            QMessageBox.warning(
                self,
                "Combinaison vide",
                "Ajoutez au moins un facteur non nul.",
            )
            return

        self._combo = CombinationData(
            tag=self._tag,
            name=name,
            combo_type=self.combo_type.currentData(),
            factors=factors,
        )
        self.accept()

    def result(self) -> CombinationData:
        """Handle result."""
        assert self._combo is not None
        return deepcopy(self._combo)


class CombinationManagerDialog(QDialog):
    """Combination manager dialog."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        loads: dict[int, LoadData] | None = None,
        combinations: dict[int, CombinationData] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Définir les combinaisons")
        self.resize(820, 520)
        self._loads = deepcopy(loads or {})
        self._combinations = deepcopy(combinations or {})

        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        grp_list = QGroupBox("Combinaisons", self)
        grp_list_lay = QVBoxLayout(grp_list)
        self.list_items = QListWidget(grp_list)
        self.list_items.currentItemChanged.connect(
            lambda _current, _previous: self._refresh_buttons()
        )
        self.list_items.itemDoubleClicked.connect(
            lambda _item: self._modify_combination()
        )
        grp_list_lay.addWidget(self.list_items)
        content.addWidget(grp_list, 1)

        grp_actions = QGroupBox("Cliquer pour :", self)
        grp_actions_lay = QVBoxLayout(grp_actions)

        self.btn_generate = QPushButton("Generer EC0...", grp_actions)
        self.btn_generate.clicked.connect(self._generate_ec0)
        grp_actions_lay.addWidget(self.btn_generate)

        self.btn_add = QPushButton("Ajouter combinaison...", grp_actions)
        self.btn_add.clicked.connect(self._add_combination)
        grp_actions_lay.addWidget(self.btn_add)

        self.btn_copy = QPushButton("Ajouter copie de combinaison...", grp_actions)
        self.btn_copy.clicked.connect(self._copy_combination)
        grp_actions_lay.addWidget(self.btn_copy)

        self.btn_edit = QPushButton("Modifier / Voir combinaison...", grp_actions)
        self.btn_edit.clicked.connect(self._modify_combination)
        grp_actions_lay.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Supprimer combinaison", grp_actions)
        self.btn_delete.clicked.connect(self._delete_combination)
        grp_actions_lay.addWidget(self.btn_delete)

        self.btn_switch_loads = QPushButton("Aller aux cas de charge...", grp_actions)
        self.btn_switch_loads.clicked.connect(self._switch_to_load_cases)
        grp_actions_lay.addSpacing(8)
        grp_actions_lay.addWidget(self.btn_switch_loads)

        self.lbl_info = QLabel(
            "Les combinaisons peuvent être générées automatiquement selon EC0 "
            "ou saisies manuellement.",
            grp_actions,
        )
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("color: #607080; margin-top: 8px;")
        grp_actions_lay.addWidget(self.lbl_info)
        grp_actions_lay.addStretch(1)
        content.addWidget(grp_actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_list(self) -> None:
        """Refresh list."""
        current_tag = self.current_tag()
        self.list_items.clear()

        for tag, combo in sorted(self._combinations.items()):
            formula = combination_formula(combo, self._loads)
            item = QListWidgetItem(f"{combo.name} (T{tag})\n{combo.combo_type} - {formula}")
            item.setData(Qt.UserRole, tag)
            self.list_items.addItem(item)

        if self.list_items.count():
            target_row = 0
            if current_tag is not None:
                for row in range(self.list_items.count()):
                    if self.list_items.item(row).data(Qt.UserRole) == current_tag:
                        target_row = row
                        break
            self.list_items.setCurrentRow(target_row)

        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        """Refresh buttons."""
        has_loads = bool(self._loads)
        has_selection = self.current_tag() is not None
        self.btn_generate.setEnabled(has_loads)
        self.btn_add.setEnabled(has_loads)
        self.btn_copy.setEnabled(has_selection and has_loads)
        self.btn_edit.setEnabled(has_selection and has_loads)
        self.btn_delete.setEnabled(has_selection)
        self.btn_switch_loads.setEnabled(True)

    def current_tag(self) -> int | None:
        """Return tag."""
        item = self.list_items.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _next_tag(self) -> int:
        """Return the next tag."""
        return max(self._combinations.keys(), default=0) + 1

    def _generate_ec0(self) -> None:
        """Handle generate EC0."""
        if not self._loads:
            return
        dlg = ComboDialog(self, loads=self._loads)
        if dlg.exec() != ComboDialog.Accepted:
            return

        generated = dlg.result()
        if not generated:
            QMessageBox.information(
                self,
                "Generation EC0",
                "Aucune combinaison n'a été générée avec les choix actuels.",
            )
            return

        for combo in generated:
            new_tag = self._next_tag()
            combo.tag = new_tag
            self._combinations[new_tag] = deepcopy(combo)

        self._refresh_list()

    def _add_combination(self) -> None:
        """Add combination."""
        dlg = CombinationEditDialog(
            self,
            loads=self._loads,
            tag=self._next_tag(),
        )
        if dlg.exec() != CombinationEditDialog.Accepted:
            return
        combo = dlg.result()
        self._combinations[combo.tag] = combo
        self._refresh_list()

    def _copy_combination(self) -> None:
        """Copy combination."""
        tag = self.current_tag()
        if tag is None:
            return
        source = self._combinations.get(tag)
        if source is None:
            return

        new_tag = self._next_tag()
        copied = deepcopy(source)
        copied.tag = new_tag
        copied.name = f"{source.name} - Copie"
        self._combinations[new_tag] = copied
        self._refresh_list()

    def _modify_combination(self) -> None:
        """Handle modify combination."""
        tag = self.current_tag()
        if tag is None:
            return
        combo = self._combinations.get(tag)
        if combo is None:
            return

        dlg = CombinationEditDialog(self, loads=self._loads, combo=combo)
        if dlg.exec() != CombinationEditDialog.Accepted:
            return
        updated = dlg.result()
        self._combinations[updated.tag] = updated
        self._refresh_list()

    def _delete_combination(self) -> None:
        """Delete combination."""
        tag = self.current_tag()
        if tag is None:
            return
        combo = self._combinations.get(tag)
        if combo is None:
            return

        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Supprimer la combinaison '{combo.name}' ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        del self._combinations[tag]
        self._refresh_list()

    def _switch_to_load_cases(self) -> None:
        """Handle switch to load cases."""
        self._switch_to_load_cases_requested = True
        self.accept()

    def switch_to_load_cases_requested(self) -> bool:
        """Handle switch to load cases requested."""
        return bool(getattr(self, "_switch_to_load_cases_requested", False))

    def result_combinations(self) -> dict[int, CombinationData]:
        """Return combinations."""
        return deepcopy(self._combinations)


class ComboDialog(QDialog):
    """Combination dialog."""

    def __init__(self, parent: QWidget | None = None,
                 loads: dict[int, LoadData] | None = None):
        super().__init__(parent)

        self.ui = load_dialog_ui(self, "combo_dlg.ui")

        self._loads = loads or {}
        self._generated: list[CombinationData] = []

        self._setup_dynamic_widgets()
        self._connect_signals()
        self._update_preview()

    def _setup_dynamic_widgets(self) -> None:
        """Create dynamic checkboxes from ComboType enum."""
        perm_count = sum(
            1 for lc in self._loads.values()
            if lc.load_type in ("dead", "permanent", "self_weight")
        )
        var_count = sum(
            1 for lc in self._loads.values()
            if lc.load_type in ("live", "snow", "wind", "temperature")
        )
        seis_count = sum(
            1 for lc in self._loads.values()
            if lc.load_type == "seismic"
        )

        # Update info label
        self.ui.lbl_info.setText(
            f"Cas de charges : {perm_count} permanent(s), "
            f"{var_count} variable(s), {seis_count} sismique(s)"
        )

        # Dynamically create checkboxes inside grp_types
        grp_layout = self.ui.grp_types.layout()
        self._combo_checks: dict[ComboType, QCheckBox] = {}
        default_checked = {
            ComboType.ULS_FUNDAMENTAL,
            ComboType.SLS_CHARACTERISTIC,
            ComboType.SLS_FREQUENT,
            ComboType.SLS_QUASI_PERMANENT,
        }
        for ct in ComboType:
            cb = QCheckBox(COMBO_LABELS[ct])
            cb.setChecked(ct in default_checked)
            # Disable seismic/accidental if no seismic load case
            if ct in (ComboType.ULS_SEISMIC, ComboType.ULS_ACCIDENTAL) and seis_count == 0:
                cb.setEnabled(False)
                cb.setChecked(False)
            cb.stateChanged.connect(self._update_preview)
            self._combo_checks[ct] = cb
            grp_layout.addWidget(cb)

    def _connect_signals(self) -> None:
        """Wire up button box signals."""
        self.ui.buttons.accepted.connect(self.accept)
        self.ui.buttons.rejected.connect(self.reject)

    def _update_preview(self) -> None:
        """Update preview."""
        selected = [
            ct for ct, cb in self._combo_checks.items()
            if cb.isChecked()
        ]

        self._generated = auto_generate_combinations(
            self._loads,
            combo_types=selected,
        )

        lines = []
        for combo in self._generated:
            formula = combination_formula(combo, self._loads)
            lines.append(f"{combo.name} : {formula}")

        self.ui.txt_preview.setPlainText("\n".join(lines))
        self.ui.lbl_count.setText(f"{len(self._generated)} combinaison(s) générée(s)")

    def result(self) -> list[CombinationData]:
        """Handle result."""
        return self._generated
