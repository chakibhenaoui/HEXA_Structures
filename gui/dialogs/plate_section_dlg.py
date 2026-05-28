"""Plate section dialog."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from core.material_properties import (
    isotropic_material_properties,
    unit_weight_to_density_kg_m3,
)
from core.model_data import (
    MaterialData,
    SURFACE_FORMULATION_INFOS,
    SURFACE_FORMULATION_TYPES,
    normalize_surface_formulation,
)


_FORMULATION_ROWS: list[tuple[str, str]] = [
    ("ShellMITC4", "Usage général"),
    ("ShellDKGQ", "Dalle mince (h/L < 1/10)"),
    ("ShellNLDKGQ", "Non-linéaire géométrique"),
]


class PlateSectionDialog(QDialog):
    """Plate section dialog."""

    def __init__(
        self,
        parent=None,
        *,
        materials: dict[int, MaterialData] | None = None,
        name: str = "",
        material_tag: int | None = None,
        properties: dict | None = None,
    ):
        super().__init__(parent)
        self._materials = deepcopy(materials or {})
        self._init_name = name
        self._is_edit_mode = bool(name)
        self._init_material_tag = material_tag
        self._init_properties = dict(properties or {})
        self._init_formulation = normalize_surface_formulation(
            self._init_properties.get("element_formulation", "ShellMITC4")
        )

        self.setWindowTitle(
            self.tr("Modifier la section plaque") if name else self.tr("Nouvelle section plaque")
        )
        self.resize(560, 470)

        self._build_ui()
        self._setup_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        grp_general = QGroupBox(self.tr("Nouvelle section plaque"), self)
        general_form = QFormLayout(grp_general)
        self.edit_name = QLineEdit(grp_general)
        general_form.addRow(self.tr("Nom :"), self.edit_name)
        root.addWidget(grp_general)

        grp_formulation = QGroupBox(self.tr("Type d'élément"), self)
        formulation_layout = QVBoxLayout(grp_formulation)
        self.formulation_group = QButtonGroup(self)
        self._radio_by_formulation: dict[str, QRadioButton] = {}
        subtitles = {
            "ShellMITC4": self.tr("Usage général"),
            "ShellDKGQ": self.tr("Dalle mince (h/L < 1/10)"),
            "ShellNLDKGQ": self.tr("Non-linéaire géométrique"),
        }
        for formulation, _subtitle in _FORMULATION_ROWS:
            subtitle = subtitles.get(formulation, "")
            radio = QRadioButton(f"{formulation}   {subtitle}", grp_formulation)
            self.formulation_group.addButton(radio)
            self.formulation_group.setId(radio, len(self._radio_by_formulation))
            self._radio_by_formulation[formulation] = radio
            formulation_layout.addWidget(radio)
        root.addWidget(grp_formulation)

        grp_geometry = QGroupBox(self.tr("Définition"), self)
        geometry_layout = QGridLayout(grp_geometry)
        self.combo_material = QComboBox(grp_geometry)
        self.btn_add_material = QPushButton("+", grp_geometry)
        self.btn_add_material.setFixedWidth(34)
        material_row = QHBoxLayout()
        material_row.addWidget(self.combo_material, 1)
        material_row.addWidget(self.btn_add_material)
        self.spin_thickness = self._make_spin(0.20, 0.001, 10.0, 3, 0.01, " m")
        geometry_layout.addWidget(QLabel(self.tr("Matériau"), grp_geometry), 0, 0)
        geometry_layout.addLayout(material_row, 0, 1)
        geometry_layout.addWidget(QLabel(self.tr("Épaisseur h"), grp_geometry), 1, 0)
        geometry_layout.addWidget(self.spin_thickness, 1, 1)
        root.addWidget(grp_geometry)

        middle_layout = QHBoxLayout()
        root.addLayout(middle_layout)

        grp_material_info = QGroupBox(self.tr("Récapitulatif matériau"), self)
        material_info_form = QFormLayout(grp_material_info)
        self.lbl_material_e = QLabel("-", grp_material_info)
        self.lbl_material_nu = QLabel("-", grp_material_info)
        self.lbl_material_rho = QLabel("-", grp_material_info)
        material_info_form.addRow("E =", self.lbl_material_e)
        material_info_form.addRow("ν =", self.lbl_material_nu)
        material_info_form.addRow("ρ =", self.lbl_material_rho)
        middle_layout.addWidget(grp_material_info, 1)

        grp_element_info = QGroupBox(self.tr("Info élément"), self)
        element_info_layout = QVBoxLayout(grp_element_info)
        self.lbl_formulation_info = QLabel(grp_element_info)
        self.lbl_formulation_info.setWordWrap(True)
        self.lbl_formulation_info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        element_info_layout.addWidget(self.lbl_formulation_info)
        middle_layout.addWidget(grp_element_info, 1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        self.button_box.button(QDialogButtonBox.Ok).setText(self.tr("Créer section"))
        self.button_box.button(QDialogButtonBox.Cancel).setText(self.tr("Annuler"))
        root.addWidget(self.button_box)

    def _setup_ui(self) -> None:
        self.edit_name.setText(self._init_name)
        self.button_box.button(QDialogButtonBox.Ok).setText(
            "OK" if self._is_edit_mode else self.tr("Créer section")
        )
        self._populate_materials(preferred_tag=self._init_material_tag)
        self.spin_thickness.setValue(float(self._init_properties.get("thickness", 0.20)))

        checked = self._radio_by_formulation.get(self._init_formulation)
        if checked is None:
            checked = self._radio_by_formulation["ShellMITC4"]
        checked.setChecked(True)

        self.combo_material.currentIndexChanged.connect(
            lambda *_args: self._update_material_summary()
        )
        self.btn_add_material.clicked.connect(self._add_material)
        self.formulation_group.buttonClicked.connect(
            lambda *_args: self._update_formulation_info()
        )
        self.button_box.accepted.connect(self._validate)
        self.button_box.rejected.connect(self.reject)

        self._update_material_summary()
        self._update_formulation_info()

    def _populate_materials(self, preferred_tag: int | None = None) -> None:
        self.combo_material.blockSignals(True)
        self.combo_material.clear()
        for tag, mat in sorted(self._materials.items()):
            self.combo_material.addItem(f"{mat.name} — {mat.grade}", tag)
        if self.combo_material.count() == 0:
            self.combo_material.addItem(self.tr("(aucun matériau - utilisez +)"), None)
        if preferred_tag is not None:
            idx = self.combo_material.findData(preferred_tag)
            if idx >= 0:
                self.combo_material.setCurrentIndex(idx)
        self.combo_material.blockSignals(False)

    def _selected_formulation(self) -> str:
        for formulation, radio in self._radio_by_formulation.items():
            if radio.isChecked():
                return formulation
        return "ShellMITC4"

    def _update_material_summary(self) -> None:
        material_tag = self.combo_material.currentData()
        material = self._materials.get(material_tag)
        if material is None:
            self.lbl_material_e.setText("-")
            self.lbl_material_nu.setText("-")
            self.lbl_material_rho.setText("-")
            return

        props = isotropic_material_properties(
            material.material_type,
            material.grade,
            material.properties,
        )
        density = unit_weight_to_density_kg_m3(props["unit_weight"])
        self.lbl_material_e.setText(f"{props['young_modulus'] / 1000.0:,.0f} MPa".replace(",", " "))
        self.lbl_material_nu.setText(f"{props['poisson_ratio']:.2f}")
        self.lbl_material_rho.setText(f"{density:,.0f} kg/m³".replace(",", " "))

    def _update_formulation_info(self) -> None:
        formulation = self._selected_formulation()
        generic_type = SURFACE_FORMULATION_TYPES[formulation]
        self.lbl_formulation_info.setText(
            self.tr("{formulation} : {info}\nType générique transmis au solveur : {generic_type}.").format(
                formulation=formulation,
                info=SURFACE_FORMULATION_INFOS[formulation],
                generic_type=generic_type,
            )
        )

    def _add_material(self) -> None:
        from gui.dialogs.material_dlg import MaterialDialog

        dlg = MaterialDialog(self)
        if dlg.exec() != MaterialDialog.Accepted:
            return

        data = dlg.result()
        tag = max(self._materials.keys(), default=0) + 1
        self._materials[tag] = MaterialData(
            tag=tag,
            name=str(data["name"]),
            material_type=str(data["material_type"]),
            grade=str(data["grade"]),
            properties=dict(data["properties"]),
        )
        self._populate_materials(preferred_tag=tag)
        self._update_material_summary()

    def _validate(self) -> None:
        if not self.edit_name.text().strip():
            self.edit_name.setFocus()
            return
        if self.combo_material.currentData() is None:
            QMessageBox.warning(
                self,
                self.tr("Matériau requis"),
                self.tr("Ajoutez ou choisissez d'abord un matériau pour la plaque."),
            )
            return
        self.accept()

    def result(self) -> dict[str, object]:
        return {
            "name": self.edit_name.text().strip(),
            "section_type": "surface",
            "material_tag": int(self.combo_material.currentData()),
            "area": 0.0,
            "inertia_y": 0.0,
            "inertia_z": 0.0,
            "properties": {
                "thickness": float(self.spin_thickness.value()),
                "element_formulation": self._selected_formulation(),
            },
        }

    def result_materials(self) -> dict[int, MaterialData]:
        return deepcopy(self._materials)

    @staticmethod
    def _make_spin(
        value: float,
        vmin: float,
        vmax: float,
        decimals: int,
        step: float,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(vmin, vmax)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin
