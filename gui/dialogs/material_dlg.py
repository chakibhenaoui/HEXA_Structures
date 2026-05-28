"""Material creation and editing dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from config.eurocodes import CONCRETE_GRADES, REBAR_GRADES, STEEL_GRADES
from core.material_properties import (
    build_material_properties,
    compute_shear_modulus,
    isotropic_material_properties,
    unit_weight_to_density_kg_m3,
)


_GRADES_BY_TYPE = {
    "concrete": list(CONCRETE_GRADES.keys()),
    "rebar": list(REBAR_GRADES.keys()),
    "steel": list(STEEL_GRADES.keys()),
}


class MaterialDialog(QDialog):
    """Material dialog."""

    _AUTO_PREFIXES = ("Béton", "Armature", "Acier", "Matériau")

    def __init__(
        self,
        parent=None,
        *,
        name: str = "",
        material_type: str = "",
        grade: str = "",
        properties: dict | None = None,
    ):
        super().__init__(parent)
        self._init_name = name
        self._init_type = material_type or "concrete"
        self._init_grade = grade
        self._init_properties = dict(properties or {})
        self._syncing_identity = False

        self.setWindowTitle(self.tr("Données matériau"))
        self.resize(560, 420)

        self._build_ui()
        self._setup_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self.grp_general = QGroupBox(self)
        general_form = QFormLayout(self.grp_general)
        self.edit_name = QLineEdit(self.grp_general)
        self.combo_type = QComboBox(self.grp_general)
        self.combo_grade = QComboBox(self.grp_general)
        self.lbl_info = QLabel(self.grp_general)
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("color: #666; font-size: 11px;")
        self.lbl_name = QLabel(self)
        self.lbl_type = QLabel(self)
        self.lbl_grade = QLabel(self)
        general_form.addRow(self.lbl_name, self.edit_name)
        general_form.addRow(self.lbl_type, self.combo_type)
        general_form.addRow(self.lbl_grade, self.combo_grade)
        general_form.addRow("", self.lbl_info)
        root.addWidget(self.grp_general)

        middle_layout = QGridLayout()
        root.addLayout(middle_layout)

        self.grp_weight = QGroupBox(self)
        weight_form = QFormLayout(self.grp_weight)
        self.spin_unit_weight = self._make_spin(0.0, 0.0, 500.0, 3, 0.5, " kN/m3")
        self.edit_mass_density = QLineEdit(self.grp_weight)
        self.edit_mass_density.setReadOnly(True)
        self.lbl_unit_weight = QLabel(self)
        self.lbl_mass_density = QLabel(self)
        weight_form.addRow(self.lbl_unit_weight, self.spin_unit_weight)
        weight_form.addRow(self.lbl_mass_density, self.edit_mass_density)
        middle_layout.addWidget(self.grp_weight, 0, 0)

        self.grp_units = QGroupBox(self)
        units_form = QFormLayout(self.grp_units)
        self.lbl_units = QLabel("kN, m, C", self.grp_units)
        self.lbl_internal_system = QLabel(self)
        units_form.addRow(self.lbl_internal_system, self.lbl_units)
        middle_layout.addWidget(self.grp_units, 0, 1)

        self.grp_isotropic = QGroupBox(self)
        isotropic_form = QFormLayout(self.grp_isotropic)
        self.spin_young = self._make_spin(0.0, 0.0, 1_000_000_000.0, 0, 100_000.0, " kPa")
        self.spin_poisson = self._make_spin(0.0, 0.0, 0.499, 3, 0.01)
        self.edit_shear = QLineEdit(self.grp_isotropic)
        self.edit_shear.setReadOnly(True)
        self.lbl_young = QLabel(self)
        self.lbl_poisson = QLabel(self)
        self.lbl_shear = QLabel(self)
        isotropic_form.addRow(self.lbl_young, self.spin_young)
        isotropic_form.addRow(self.lbl_poisson, self.spin_poisson)
        isotropic_form.addRow(self.lbl_shear, self.edit_shear)
        root.addWidget(self.grp_isotropic)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        root.addWidget(self.button_box)

    def _setup_ui(self) -> None:
        self.edit_name.setText(self._init_name)

        for key in _GRADES_BY_TYPE:
            self.combo_type.addItem(self._material_type_label(key), key)

        self.button_box.accepted.connect(self._validate)
        self.button_box.rejected.connect(self.reject)
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        self.combo_grade.currentIndexChanged.connect(self._on_grade_changed)
        self.spin_unit_weight.valueChanged.connect(self._update_derived_fields)
        self.spin_young.valueChanged.connect(self._update_derived_fields)
        self.spin_poisson.valueChanged.connect(self._update_derived_fields)

        self._syncing_identity = True
        try:
            idx = self.combo_type.findData(self._init_type)
            self.combo_type.setCurrentIndex(idx if idx >= 0 else 0)
            self._populate_grades(preferred_grade=self._init_grade)
        finally:
            self._syncing_identity = False

        init_props = isotropic_material_properties(
            self.material_type(),
            self.grade(),
            self._init_properties,
        )
        self.spin_unit_weight.setValue(init_props["unit_weight"])
        self.spin_young.setValue(init_props["young_modulus"])
        self.spin_poisson.setValue(init_props["poisson_ratio"])
        self._update_info()
        self._update_derived_fields()
        if not self._init_name:
            self._auto_name()
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Refresh persistent dialog labels after a language change."""
        self.setWindowTitle(self.tr("Données matériau"))
        self.grp_general.setTitle(self.tr("Données générales"))
        self.grp_weight.setTitle(self.tr("Poids et masse"))
        self.grp_units.setTitle(self.tr("Unités"))
        self.grp_isotropic.setTitle(self.tr("Propriétés isotropes"))
        self.lbl_name.setText(self.tr("Nom :"))
        self.lbl_type.setText(self.tr("Type :"))
        self.lbl_grade.setText(self.tr("Nuance / classe :"))
        self.lbl_unit_weight.setText(self.tr("Poids volumique :"))
        self.lbl_mass_density.setText(self.tr("Masse volumique :"))
        self.lbl_internal_system.setText(self.tr("Système interne :"))
        self.lbl_young.setText(self.tr("Module de Young E :"))
        self.lbl_poisson.setText(self.tr("Coefficient de Poisson nu :"))
        self.lbl_shear.setText(self.tr("Module de cisaillement G :"))
        self._refresh_material_type_labels()
        self._update_info()
        self.button_box.button(QDialogButtonBox.Ok).setText(self.tr("OK"))
        self.button_box.button(QDialogButtonBox.Cancel).setText(self.tr("Annuler"))

    def _refresh_material_type_labels(self) -> None:
        """Refresh material type combo labels while preserving stored data."""
        current = self.material_type()
        self.combo_type.blockSignals(True)
        for index in range(self.combo_type.count()):
            key = str(self.combo_type.itemData(index) or "")
            self.combo_type.setItemText(index, self._material_type_label(key))
        idx = self.combo_type.findData(current)
        if idx >= 0:
            self.combo_type.setCurrentIndex(idx)
        self.combo_type.blockSignals(False)

    def _material_type_label(self, material_type: str) -> str:
        labels = {
            "concrete": self.tr("Béton (EC2)"),
            "rebar": self.tr("Armatures (EC2)"),
            "steel": self.tr("Acier de construction (EC3)"),
        }
        return labels.get(material_type, material_type)

    def _material_info(self, material_type: str) -> str:
        labels = {
            "concrete": self.tr(
                "Matériau isotrope basé sur une classe de béton Eurocode 2."
            ),
            "rebar": self.tr(
                "Matériau isotrope basé sur une nuance d'acier d'armature Eurocode 2."
            ),
            "steel": self.tr(
                "Matériau isotrope basé sur une nuance d'acier de construction Eurocode 3."
            ),
        }
        return labels.get(material_type, "")

    def _populate_grades(self, *, preferred_grade: str = "") -> None:
        """Handle populate grades."""
        grades = _GRADES_BY_TYPE.get(self.material_type(), [])
        self.combo_grade.blockSignals(True)
        self.combo_grade.clear()
        self.combo_grade.addItems(grades)
        target_grade = preferred_grade if preferred_grade in grades else (grades[0] if grades else "")
        idx = self.combo_grade.findText(target_grade)
        if idx >= 0:
            self.combo_grade.setCurrentIndex(idx)
        self.combo_grade.blockSignals(False)

    def _on_type_changed(self) -> None:
        """Handle type changed."""
        if self._syncing_identity:
            return
        self._populate_grades()
        self._apply_grade_defaults()

    def _on_grade_changed(self) -> None:
        """Handle grade changed."""
        if self._syncing_identity:
            return
        self._apply_grade_defaults()

    def _apply_grade_defaults(self) -> None:
        """Apply grade defaults."""
        defaults = isotropic_material_properties(self.material_type(), self.grade(), {})
        self.spin_unit_weight.setValue(defaults["unit_weight"])
        self.spin_young.setValue(defaults["young_modulus"])
        self.spin_poisson.setValue(defaults["poisson_ratio"])
        self._update_info()
        self._auto_name()
        self._update_derived_fields()

    def _update_info(self) -> None:
        """Update info."""
        self.lbl_info.setText(self._material_info(self.material_type()))

    def _auto_name(self) -> None:
        """Suggest an automatic name from the material type and grade."""
        grade = self.grade()
        if not grade:
            return
        prefix = {
            "concrete": self.tr("Béton"),
            "rebar": self.tr("Armature"),
            "steel": self.tr("Acier"),
        }.get(self.material_type(), self.tr("Matériau"))
        current = self.edit_name.text().strip()
        if not current or any(current.startswith(p) for p in self._auto_prefixes()):
            self.edit_name.setText(f"{prefix} {grade}")

    def _auto_prefixes(self) -> tuple[str, ...]:
        return self._AUTO_PREFIXES + (
            self.tr("Béton"),
            self.tr("Armature"),
            self.tr("Acier"),
            self.tr("Matériau"),
        )

    def _update_derived_fields(self) -> None:
        """Update derived fields."""
        density = unit_weight_to_density_kg_m3(self.spin_unit_weight.value())
        shear = compute_shear_modulus(
            self.spin_young.value(),
            self.spin_poisson.value(),
        )
        self.edit_mass_density.setText(f"{density:.1f} kg/m3")
        self.edit_shear.setText(f"{shear:.0f} kPa")

    def _validate(self) -> None:
        """Handle validate."""
        if not self.edit_name.text().strip():
            self.edit_name.setFocus()
            return
        if not self.grade():
            self.combo_grade.setFocus()
            return
        self.accept()

    def material_type(self) -> str:
        """Handle material type."""
        return str(self.combo_type.currentData() or "")

    def grade(self) -> str:
        """Handle grade."""
        return self.combo_grade.currentText().strip()

    def result(self) -> dict[str, object]:
        """Handle result."""
        return {
            "name": self.edit_name.text().strip(),
            "material_type": self.material_type(),
            "grade": self.grade(),
            "properties": build_material_properties(
                unit_weight=self.spin_unit_weight.value(),
                young_modulus=self.spin_young.value(),
                poisson_ratio=self.spin_poisson.value(),
                base_properties=self._init_properties,
            ),
        }

    @staticmethod
    def _make_spin(
        value: float,
        vmin: float,
        vmax: float,
        decimals: int,
        step: float,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        """Create spin."""
        spin = QDoubleSpinBox()
        spin.setRange(vmin, vmax)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin
