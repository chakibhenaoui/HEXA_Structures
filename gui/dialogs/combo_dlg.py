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
    auto_generate_combinations,
)
from core.model_data import CombinationData, LoadData
from gui.dialogs import load_dialog_ui
from gui.i18n.display_labels import (
    combination_formula_label,
    combo_type_label,
    load_name_label,
)


COMBO_TYPES = [
    "ELU",
    "ELS car.",
    "ELS fréq.",
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
        self.setWindowTitle(
            self.tr("Modifier la combinaison")
            if combo
            else self.tr("Nouvelle combinaison")
        )
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
            self.combo_type.addItem(combo_type_label(combo_type), combo_type)
        form.addRow(self.tr("Nom :"), self.edit_name)
        form.addRow(self.tr("Type :"), self.combo_type)
        root.addLayout(form)

        grp = QGroupBox(self.tr("Facteurs des cas de charge"), self)
        grp_lay = QVBoxLayout(grp)
        info = QLabel(
            self.tr("Mettre un facteur à 0 pour exclure le cas de charge de la combinaison."),
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
            factors_layout.addRow(
                self.tr("{name} (T{tag}) :").format(
                    name=load_name_label(load),
                    tag=load_tag,
                ),
                spin,
            )
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
            self.edit_name.setText(
                self.tr("Combinaison {tag}").format(tag=self._tag)
            )
            idx = self.combo_type.findData("Manuelle")
            if idx >= 0:
                self.combo_type.setCurrentIndex(idx)
            return

        self.edit_name.setText(self._combo.name)
        idx = self.combo_type.findData(self._combo.combo_type)
        if idx < 0:
            self.combo_type.addItem(
                combo_type_label(self._combo.combo_type),
                self._combo.combo_type,
            )
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
                self.tr("Combinaison vide"),
                self.tr("Ajoutez au moins un facteur non nul."),
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
        self.setWindowTitle(self.tr("Définir les combinaisons"))
        self.resize(820, 520)
        self._loads = deepcopy(loads or {})
        self._combinations = deepcopy(combinations or {})

        self._build_ui()
        self.retranslate_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        self.grp_list = QGroupBox(self.tr("Combinaisons"), self)
        grp_list = self.grp_list
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

        self.grp_actions = QGroupBox(self.tr("Cliquer pour :"), self)
        grp_actions = self.grp_actions
        grp_actions_lay = QVBoxLayout(grp_actions)

        self.btn_generate = QPushButton(self.tr("Générer EC0..."), grp_actions)
        self.btn_generate.clicked.connect(self._generate_ec0)
        grp_actions_lay.addWidget(self.btn_generate)

        self.btn_add = QPushButton(self.tr("Ajouter combinaison..."), grp_actions)
        self.btn_add.clicked.connect(self._add_combination)
        grp_actions_lay.addWidget(self.btn_add)

        self.btn_copy = QPushButton(self.tr("Ajouter copie de combinaison..."), grp_actions)
        self.btn_copy.clicked.connect(self._copy_combination)
        grp_actions_lay.addWidget(self.btn_copy)

        self.btn_edit = QPushButton(self.tr("Modifier / Voir combinaison..."), grp_actions)
        self.btn_edit.clicked.connect(self._modify_combination)
        grp_actions_lay.addWidget(self.btn_edit)

        self.btn_delete = QPushButton(self.tr("Supprimer combinaison"), grp_actions)
        self.btn_delete.clicked.connect(self._delete_combination)
        grp_actions_lay.addWidget(self.btn_delete)

        self.btn_switch_loads = QPushButton(self.tr("Aller aux cas de charge..."), grp_actions)
        self.btn_switch_loads.clicked.connect(self._switch_to_load_cases)
        grp_actions_lay.addSpacing(8)
        grp_actions_lay.addWidget(self.btn_switch_loads)

        self.lbl_info = QLabel(
            self.tr(
                "Les combinaisons peuvent être générées automatiquement selon EC0 "
                "ou saisies manuellement."
            ),
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

    def retranslate_ui(self) -> None:
        """Refresh persistent labels after a language change."""
        self.setWindowTitle(self.tr("Définir les combinaisons"))
        self.grp_list.setTitle(self.tr("Combinaisons"))
        self.grp_actions.setTitle(self.tr("Cliquer pour :"))
        self.btn_generate.setText(self.tr("Générer EC0..."))
        self.btn_add.setText(self.tr("Ajouter combinaison..."))
        self.btn_copy.setText(self.tr("Ajouter copie de combinaison..."))
        self.btn_edit.setText(self.tr("Modifier / Voir combinaison..."))
        self.btn_delete.setText(self.tr("Supprimer combinaison"))
        self.btn_switch_loads.setText(self.tr("Aller aux cas de charge..."))
        self.lbl_info.setText(
            self.tr(
                "Les combinaisons peuvent être générées automatiquement selon EC0 "
                "ou saisies manuellement."
            )
        )

    def _refresh_list(self) -> None:
        """Refresh list."""
        current_tag = self.current_tag()
        self.list_items.clear()

        for tag, combo in sorted(self._combinations.items()):
            formula = combination_formula_label(combo, self._loads)
            item = QListWidgetItem(
                self.tr("{name} (T{tag})\n{type} - {formula}").format(
                    name=combo.name,
                    tag=tag,
                    type=combo_type_label(combo.combo_type),
                    formula=formula,
                )
            )
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
                self.tr("Génération EC0"),
                self.tr("Aucune combinaison n'a été générée avec les choix actuels."),
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
        copied.name = self.tr("{name} - Copie").format(name=source.name)
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
            self.tr("Confirmer la suppression"),
            self.tr("Supprimer la combinaison '{name}' ?").format(name=combo.name),
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
            self.tr(
                "Cas de charges : {permanent} permanent(s), "
                "{variable} variable(s), {seismic} sismique(s)"
            ).format(
                permanent=perm_count,
                variable=var_count,
                seismic=seis_count,
            )
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
            cb = QCheckBox(combo_type_label(ct.value))
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
            formula = combination_formula_label(combo, self._loads)
            lines.append(
                self.tr("{name} : {formula}").format(
                    name=combo.name,
                    formula=formula,
                )
            )

        self.ui.txt_preview.setPlainText("\n".join(lines))
        self.ui.lbl_count.setText(
            self.tr("{count} combinaison(s) générée(s)").format(
                count=len(self._generated)
            )
        )

    def result(self) -> list[CombinationData]:
        """Handle result."""
        return self._generated
