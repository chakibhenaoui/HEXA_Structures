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


_MATERIAL_TYPES = {
    "concrete": "Béton (EC2)",
    "rebar": "Armatures (EC2)",
    "steel": "Acier de construction (EC3)",
}

_MATERIAL_INFOS = {
    "concrete": "Matériau isotrope base sur une classe de béton Eurocode 2.",
    "rebar": "Matériau isotrope base sur une nuance d'acier d'armature Eurocode 2.",
    "steel": "Matériau isotrope base sur une nuance d'acier de construction Eurocode 3.",
}

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

        self.setWindowTitle("Données matériau")
        self.resize(560, 420)

        self._build_ui()
        self._setup_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        grp_general = QGroupBox("Données generales", self)
        general_form = QFormLayout(grp_general)
        self.edit_name = QLineEdit(grp_general)
        self.combo_type = QComboBox(grp_general)
        self.combo_grade = QComboBox(grp_general)
        self.lbl_info = QLabel(grp_general)
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("color: #666; font-size: 11px;")
        general_form.addRow("Nom :", self.edit_name)
        general_form.addRow("Type :", self.combo_type)
        general_form.addRow("Nuance / classe :", self.combo_grade)
        general_form.addRow("", self.lbl_info)
        root.addWidget(grp_general)

        middle_layout = QGridLayout()
        root.addLayout(middle_layout)

        grp_weight = QGroupBox("Poids et masse", self)
        weight_form = QFormLayout(grp_weight)
        self.spin_unit_weight = self._make_spin(0.0, 0.0, 500.0, 3, 0.5, " kN/m3")
        self.edit_mass_density = QLineEdit(grp_weight)
        self.edit_mass_density.setReadOnly(True)
        weight_form.addRow("Poids volumique :", self.spin_unit_weight)
        weight_form.addRow("Masse volumique :", self.edit_mass_density)
        middle_layout.addWidget(grp_weight, 0, 0)

        grp_units = QGroupBox("Unités", self)
        units_form = QFormLayout(grp_units)
        self.lbl_units = QLabel("kN, m, C", grp_units)
        units_form.addRow("Systeme interne :", self.lbl_units)
        middle_layout.addWidget(grp_units, 0, 1)

        grp_isotropic = QGroupBox("Propriétés isotropes", self)
        isotropic_form = QFormLayout(grp_isotropic)
        self.spin_young = self._make_spin(0.0, 0.0, 1_000_000_000.0, 0, 100_000.0, " kPa")
        self.spin_poisson = self._make_spin(0.0, 0.0, 0.499, 3, 0.01)
        self.edit_shear = QLineEdit(grp_isotropic)
        self.edit_shear.setReadOnly(True)
        isotropic_form.addRow("Module de Young E :", self.spin_young)
        isotropic_form.addRow("Coefficient de Poisson nu :", self.spin_poisson)
        isotropic_form.addRow("Module de cisaillement G :", self.edit_shear)
        root.addWidget(grp_isotropic)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        root.addWidget(self.button_box)

    def _setup_ui(self) -> None:
        self.edit_name.setText(self._init_name)

        for key, label in _MATERIAL_TYPES.items():
            self.combo_type.addItem(label, key)

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
        self.lbl_info.setText(_MATERIAL_INFOS.get(self.material_type(), ""))

    def _auto_name(self) -> None:
        """Suggest an automatic name from the material type and grade."""
        grade = self.grade()
        if not grade:
            return
        prefix = {
            "concrete": "Béton",
            "rebar": "Armature",
            "steel": "Acier",
        }.get(self.material_type(), "Matériau")
        current = self.edit_name.text().strip()
        if not current or any(current.startswith(p) for p in self._AUTO_PREFIXES):
            self.edit_name.setText(f"{prefix} {grade}")

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
