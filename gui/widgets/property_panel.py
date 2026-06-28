"""Editable property panel for selected objects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config.eurocodes import CONCRETE_GRADES, REBAR_GRADES, STEEL_GRADES
from core.material_properties import (
    build_material_properties,
    compute_shear_modulus,
    isotropic_material_properties,
    unit_weight_to_density_kg_m3,
)
from core.model_data import (
    PLATE_MESH_MODE_AUTO,
    PLATE_MESH_MODE_USER,
    SURFACE_FORMULATION_INFOS,
    SURFACE_FORMULATION_TYPES,
    normalize_surface_formulation,
    normalize_plate_mesh_mode,
    surface_expected_node_count,
    surface_type_from_formulation,
)
from core.plate_mesh_settings import effective_plate_mesh_divisions
from core.loads import ComboType
from gui.i18n.display_labels import combo_type_label, load_name_label, load_type_label

# Load types with French labels (consistent with load_dlg.py)


def _is_section_builder_section(section) -> bool:
    """Return whether a section must be edited in Section Builder."""
    properties = getattr(section, "properties", {})
    if not isinstance(properties, dict):
        properties = {}
    return (
        getattr(section, "section_type", "") == "sectionproperties"
        or properties.get("source") == "section_builder"
        or properties.get("source_tool") == "section_builder"
        or properties.get("editable_with") == "section_builder"
    )
_LOAD_TYPES = {
    "permanent": "Permanente (G)",
    "variable": "Exploitation (Q)",
    "snow": "Neige (S)",
    "wind": "Vent (W)",
    "seismic": "Sismique (E)",
}

if TYPE_CHECKING:
    from core.model_data import ProjectModel, SurfaceElementData

# Grades by material type
_GRADES_BY_TYPE: dict[str, list[str]] = {
    "concrete": list(CONCRETE_GRADES.keys()),
    "rebar": list(REBAR_GRADES.keys()),
    "steel": list(STEEL_GRADES.keys()),
}

class PropertyPanel(QScrollArea):
    """Editable property panel."""

    node_modified = Signal(int)
    element_modified = Signal(int)
    surface_modified = Signal(int)
    material_modified = Signal(int)
    section_modified = Signal(int)
    model_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: ProjectModel | None = None
        self._current_kind: str = ""
        self._current_tag: int = -1
        self._plate_editing_enabled: bool = True
        self._plate_editing_reason: str = ""

        self.setWidgetResizable(True)
        self.setMinimumWidth(220)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignTop)
        self.setWidget(self._container)

        # Placeholder
        self._placeholder = QLabel(
            self.tr("Sélectionnez un élément\npour voir ses propriétés.")
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; font-size: 12px;")
        self._layout.addWidget(self._placeholder)

    def set_project(self, project: ProjectModel) -> None:
        """Set project."""
        self._project = project

    def retranslate_ui(self) -> None:
        """Refresh persistent labels after a language change."""
        self._placeholder.setText(
            self.tr("Sélectionnez un élément\npour voir ses propriétés.")
        )

    def set_plate_editing_enabled(self, enabled: bool, reason: str = "") -> None:
        """Set plate editing enabled."""
        changed = (
            self._plate_editing_enabled != enabled
            or self._plate_editing_reason != reason
        )
        self._plate_editing_enabled = enabled
        self._plate_editing_reason = reason
        if not changed or self._project is None:
            return
        if (
            self._current_kind == "surface"
            and (
                self._current_tag in self._project.surface_elements
                or self._current_tag in self._project.plate_regions
            )
        ):
            self.show_surface(self._current_tag)
        elif self._current_kind == "section":
            sec = self._project.sections.get(self._current_tag)
            if sec is not None and sec.is_surface:
                self.show_section(self._current_tag)

    def clear_display(self) -> None:
        """Clear display."""
        self._clear_form()
        self._placeholder.setVisible(True)
        self._current_kind = ""
        self._current_tag = -1

    # -- Display by object type -----------------------------------------------

    def show_node(self, tag: int) -> None:
        """Show node."""
        if self._project is None or tag not in self._project.nodes:
            return
        self._current_kind = "node"
        self._current_tag = tag
        node = self._project.nodes[tag]
        self._clear_form()

        group = QGroupBox(self.tr("Nœud N{tag}").format(tag=tag))
        form = QFormLayout(group)

        # Coordinates
        self._spin_x = self._make_spin(node.x, -1e6, 1e6, " m")
        self._spin_y = self._make_spin(node.y, -1e6, 1e6, " m")
        self._spin_z = self._make_spin(node.z, -1e6, 1e6, " m")
        form.addRow(self.tr("X :"), self._spin_x)
        form.addRow(self.tr("Y :"), self._spin_y)
        form.addRow(self.tr("Z :"), self._spin_z)

        # Support conditions (6 DOF)
        dof_labels = (
            self.tr("Ux (translation X)"),
            self.tr("Uy (translation Y)"),
            self.tr("Uz (translation Z)"),
            self.tr("Rx (rotation X)"),
            self.tr("Ry (rotation Y)"),
            self.tr("Rz (rotation Z)"),
        )
        self._chk_fixities: list[QCheckBox] = []
        for i, label in enumerate(dof_labels):
            cb = QCheckBox(self.tr("Bloqué {label}").format(label=label))
            cb.setChecked(bool(node.fixities[i]) if i < len(node.fixities) else False)
            self._chk_fixities.append(cb)
            form.addRow(cb)

        form.addRow(self._make_buttons(self._apply_node))

        self._layout.addWidget(group)

    def show_element(self, tag: int) -> None:
        """Show element."""
        if self._project is None or tag not in self._project.elements:
            return
        self._current_kind = "element"
        self._current_tag = tag
        elem = self._project.elements[tag]
        self._clear_form()

        group = QGroupBox(self.tr("Élément E{tag}").format(tag=tag))
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        # Nodes (editable through combobox)
        self._combo_node_i = QComboBox()
        self._combo_node_j = QComboBox()
        self._combo_node_i.setMaximumWidth(170)
        self._combo_node_j.setMaximumWidth(170)
        for ntag in sorted(self._project.nodes.keys()):
            label = f"N{ntag}"
            self._combo_node_i.addItem(label, ntag)
            self._combo_node_j.addItem(label, ntag)
        idx_i = self._combo_node_i.findData(elem.node_i)
        idx_j = self._combo_node_j.findData(elem.node_j)
        if idx_i >= 0:
            self._combo_node_i.setCurrentIndex(idx_i)
        if idx_j >= 0:
            self._combo_node_j.setCurrentIndex(idx_j)
        form.addRow(self.tr("Nœud I :"), self._combo_node_i)
        form.addRow(self.tr("Nœud J :"), self._combo_node_j)

        # Section (editable through combobox)
        self._combo_section = QComboBox()
        self._combo_section.setMaximumWidth(170)
        for stag, sec in self._project.sections.items():
            if sec.is_surface:
                continue
            self._combo_section.addItem(f"{sec.name} (T{stag})", stag)
            if stag == elem.section_tag:
                self._combo_section.setCurrentIndex(self._combo_section.count() - 1)
        form.addRow(self.tr("Section :"), self._combo_section)

        # Type (editable)
        self._combo_elem_type = QComboBox()
        self._combo_elem_type.setMaximumWidth(170)
        elem_types = ["elasticBeamColumn", "forceBeamColumn", "truss", "corotTruss"]
        self._combo_elem_type.addItems(elem_types)
        idx_t = self._combo_elem_type.findText(elem.element_type)
        if idx_t >= 0:
            self._combo_elem_type.setCurrentIndex(idx_t)
        form.addRow(self.tr("Type :"), self._combo_elem_type)

        self._spin_roll_angle = self._make_spin(
            float(getattr(elem, "roll_angle_deg", 0.0) or 0.0),
            -360.0,
            360.0,
        )
        self._spin_roll_angle.setDecimals(1)
        self._spin_roll_angle.setSingleStep(15.0)
        self._spin_roll_angle.setMaximumWidth(120)
        self._spin_roll_angle.setToolTip(
            self.tr("Rotation de la section autour de l'axe local x.")
        )
        form.addRow(self.tr("Rotation x local :"), self._spin_roll_angle)

        orientation_vector = getattr(elem, "orientation_vector", None)
        orientation_text = (
            "{:.3g} / {:.3g} / {:.3g}".format(*orientation_vector)
            if orientation_vector is not None
            else self.tr("Automatique")
        )
        form.addRow(self.tr("Orientation :"), QLabel(orientation_text))

        # Longueur (lecture seule)
        ni = self._project.nodes.get(elem.node_i)
        nj = self._project.nodes.get(elem.node_j)
        if ni and nj:
            length = ((nj.x - ni.x)**2 + (nj.y - ni.y)**2 + (nj.z - ni.z)**2) ** 0.5
            form.addRow(self.tr("Longueur :"), QLabel(f"{length:.3f} m"))

        form.addRow(self._make_buttons(self._apply_element))

        self._layout.addWidget(group)

    def show_surface(self, tag: int) -> None:
        """Show surface."""
        if self._project is None:
            return
        if tag in self._project.plate_regions:
            self._show_plate_region(tag)
            return
        if tag not in self._project.surface_elements:
            return
        self._current_kind = "surface"
        self._current_tag = tag
        surface = self._project.surface_elements[tag]
        self._clear_form()

        group = QGroupBox(self.tr("Surface S{tag}").format(tag=tag))
        form = QFormLayout(group)

        form.addRow(
            self.tr("Nœuds :"),
            QLabel(", ".join(f"N{node_tag}" for node_tag in surface.node_tags)),
        )

        self._combo_surface_section = QComboBox()
        for stag, sec in self._project.sections.items():
            if not sec.is_surface:
                continue
            self._combo_surface_section.addItem(f"{sec.name} (T{stag})", stag)
            if stag == surface.section_tag:
                self._combo_surface_section.setCurrentIndex(
                    self._combo_surface_section.count() - 1
                )
        self._combo_surface_section.currentIndexChanged.connect(
            self._update_surface_section_summary
        )
        form.addRow(self.tr("Section :"), self._combo_surface_section)

        self._lbl_surface_formulation = QLabel()
        self._lbl_surface_thickness = QLabel()
        self._lbl_surface_solver_type = QLabel()
        form.addRow(self.tr("Formulation :"), self._lbl_surface_formulation)
        form.addRow(self.tr("Épaisseur :"), self._lbl_surface_thickness)
        form.addRow(self.tr("Type solveur :"), self._lbl_surface_solver_type)

        form.addRow(
            self.tr("Aire :"),
            QLabel(f"{self._surface_area(surface):.3f} m²"),
        )

        if not self._plate_editing_enabled:
            info = QLabel(self._plate_editing_reason or self.tr("Édition plaque indisponible."))
            info.setWordWrap(True)
            info.setStyleSheet("color: #8a5a00; font-size: 11px;")
            form.addRow(self.tr("Info :"), info)
            self._combo_surface_section.setEnabled(False)

        self._update_surface_section_summary()
        form.addRow(
            self._make_buttons(self._apply_surface, enabled=self._plate_editing_enabled)
        )
        self._layout.addWidget(group)

    def _show_plate_region(self, tag: int) -> None:
        """Show plate region."""
        if self._project is None or tag not in self._project.plate_regions:
            return
        self._current_kind = "surface"
        self._current_tag = tag
        plate = self._project.plate_regions[tag]
        self._clear_form()

        group = QGroupBox(self.tr("Plaque P{tag}").format(tag=tag))
        form = QFormLayout(group)
        form.addRow(
            self.tr("Nœuds :"),
            QLabel(", ".join(f"N{node_tag}" for node_tag in plate.corner_node_tags)),
        )
        section = self._project.sections.get(plate.section_tag)
        section_text = (
            f"{section.name} (T{plate.section_tag})"
            if section is not None else f"T{plate.section_tag}"
        )
        form.addRow(self.tr("Section :"), QLabel(section_text))
        form.addRow(self.tr("Formulation :"), QLabel(str(plate.formulation)))
        effective_nx, effective_ny = effective_plate_mesh_divisions(self._project, plate)
        self._combo_plate_mesh_mode = QComboBox()
        self._combo_plate_mesh_mode.addItem(self.tr("Automatique"), PLATE_MESH_MODE_AUTO)
        self._combo_plate_mesh_mode.addItem(self.tr("Utilisateur"), PLATE_MESH_MODE_USER)
        mode = normalize_plate_mesh_mode(getattr(plate, "mesh_mode", None))
        idx = self._combo_plate_mesh_mode.findData(mode)
        if idx >= 0:
            self._combo_plate_mesh_mode.setCurrentIndex(idx)
        self._spin_plate_mesh_nx = QSpinBox()
        self._spin_plate_mesh_nx.setRange(1, 200)
        self._spin_plate_mesh_nx.setValue(int(plate.mesh_nx))
        self._spin_plate_mesh_nx.setFixedWidth(64)
        self._spin_plate_mesh_ny = QSpinBox()
        self._spin_plate_mesh_ny.setRange(1, 200)
        self._spin_plate_mesh_ny.setValue(int(plate.mesh_ny))
        self._spin_plate_mesh_ny.setFixedWidth(64)
        mesh_row = QWidget()
        mesh_layout = QHBoxLayout(mesh_row)
        mesh_layout.setContentsMargins(0, 0, 0, 0)
        mesh_layout.setSpacing(6)
        mesh_layout.addWidget(QLabel("X"))
        mesh_layout.addWidget(self._spin_plate_mesh_nx)
        mesh_layout.addWidget(QLabel("Y"))
        mesh_layout.addWidget(self._spin_plate_mesh_ny)
        mesh_layout.addStretch(1)
        form.addRow(self.tr("Mode :"), self._combo_plate_mesh_mode)
        form.addRow(self.tr("Utilisateur :"), mesh_row)
        form.addRow(self.tr("Calcul :"), QLabel(f"{effective_nx} x {effective_ny}"))
        self._combo_plate_mesh_mode.currentIndexChanged.connect(
            lambda *_args: self._update_plate_mesh_edit_state()
        )
        self._update_plate_mesh_edit_state()
        if not self._plate_editing_enabled:
            self._combo_plate_mesh_mode.setEnabled(False)
            self._spin_plate_mesh_nx.setEnabled(False)
            self._spin_plate_mesh_ny.setEnabled(False)
        form.addRow(
            self._make_buttons(
                self._apply_plate_region,
                enabled=self._plate_editing_enabled,
            )
        )
        self._layout.addWidget(group)

    def show_material(self, tag: int) -> None:
        """Show material."""
        if self._project is None or tag not in self._project.materials:
            return
        self._current_kind = "material"
        self._current_tag = tag
        mat = self._project.materials[tag]
        self._clear_form()

        group = QGroupBox(self.tr("Matériau — {name}").format(name=mat.name))
        layout = QVBoxLayout(group)

        general_group = QGroupBox(self.tr("Données générales"))
        general_form = QFormLayout(general_group)
        self._edit_mat_name = QLineEdit(mat.name)
        self._combo_mat_type = QComboBox()
        for key, label in [
            ("concrete", self.tr("Béton (EC2)")),
            ("rebar", self.tr("Armatures (EC2)")),
            ("steel", self.tr("Acier de construction (EC3)")),
        ]:
            self._combo_mat_type.addItem(label, key)
        self._combo_mat_grade = QComboBox()
        self._lbl_mat_info = QLabel()
        self._lbl_mat_info.setWordWrap(True)
        self._lbl_mat_info.setStyleSheet("color: #666; font-size: 11px;")
        general_form.addRow(self.tr("Nom :"), self._edit_mat_name)
        general_form.addRow(self.tr("Type :"), self._combo_mat_type)
        general_form.addRow(self.tr("Nuance / classe :"), self._combo_mat_grade)
        general_form.addRow("", self._lbl_mat_info)
        layout.addWidget(general_group)

        props = isotropic_material_properties(mat.material_type, mat.grade, mat.properties)

        weight_group = QGroupBox(self.tr("Poids et masse"))
        weight_form = QFormLayout(weight_group)
        self._spin_mat_unit_weight = self._make_spin(props["unit_weight"], 0.0, 500.0, " kN/m3")
        self._spin_mat_unit_weight.setDecimals(3)
        self._spin_mat_unit_weight.setSingleStep(0.5)
        self._edit_mat_mass_density = QLineEdit()
        self._edit_mat_mass_density.setReadOnly(True)
        weight_form.addRow(self.tr("Poids volumique :"), self._spin_mat_unit_weight)
        weight_form.addRow(self.tr("Masse volumique :"), self._edit_mat_mass_density)
        layout.addWidget(weight_group)

        isotropic_group = QGroupBox(self.tr("Propriétés isotropes"))
        isotropic_form = QFormLayout(isotropic_group)
        self._spin_mat_young = self._make_spin(props["young_modulus"], 0.0, 1e9, " kPa")
        self._spin_mat_young.setDecimals(0)
        self._spin_mat_young.setSingleStep(100000.0)
        self._spin_mat_poisson = self._make_spin(props["poisson_ratio"], 0.0, 0.499)
        self._spin_mat_poisson.setDecimals(3)
        self._spin_mat_poisson.setSingleStep(0.01)
        self._edit_mat_shear = QLineEdit()
        self._edit_mat_shear.setReadOnly(True)
        isotropic_form.addRow(self.tr("Module de Young E :"), self._spin_mat_young)
        isotropic_form.addRow(self.tr("Coefficient de Poisson nu :"), self._spin_mat_poisson)
        isotropic_form.addRow(self.tr("Module de cisaillement G :"), self._edit_mat_shear)
        layout.addWidget(isotropic_group)

        self._material_form_syncing = True
        try:
            idx = self._combo_mat_type.findData(mat.material_type)
            if idx >= 0:
                self._combo_mat_type.setCurrentIndex(idx)
            self._update_material_grade_choices(preferred_grade=mat.grade)
        finally:
            self._material_form_syncing = False

        self._combo_mat_type.currentIndexChanged.connect(self._on_mat_type_changed)
        self._combo_mat_grade.currentIndexChanged.connect(self._on_mat_grade_changed)
        self._spin_mat_unit_weight.valueChanged.connect(self._update_material_derived_fields)
        self._spin_mat_young.valueChanged.connect(self._update_material_derived_fields)
        self._spin_mat_poisson.valueChanged.connect(self._update_material_derived_fields)
        self._update_material_info()
        self._update_material_derived_fields()

        layout.addWidget(self._make_buttons(self._apply_material))

        self._layout.addWidget(group)

    def show_section(self, tag: int) -> None:
        """Show section."""
        if self._project is None or tag not in self._project.sections:
            return
        self._current_kind = "section"
        self._current_tag = tag
        sec = self._project.sections[tag]
        is_section_builder_section = _is_section_builder_section(sec)
        self._clear_form()

        group = QGroupBox(self.tr("Section — {name}").format(name=sec.name))
        form = QFormLayout(group)

        self._edit_sec_name = QLineEdit(sec.name)
        form.addRow(self.tr("Nom :"), self._edit_sec_name)

        # Type (editable)
        self._combo_sec_type = QComboBox()
        sec_types = [
            ("rectangular", self.tr("Rectangulaire")),
            ("T", self.tr("Section en T")),
            ("I", self.tr("I / H parametrique")),
            ("channel", self.tr("U / Channel parametrique")),
            ("angle", self.tr("Corniere L parametrique")),
            ("pipe", self.tr("Tube circulaire")),
            ("tube", self.tr("Tube rectangulaire")),
            ("I_profile", self.tr("Profilé acier")),
            ("custom_polygon", self.tr("Section personnalisée")),
            ("sectionproperties", self.tr("Section utilisateur calculee")),
        ]
        if sec.is_surface or self._plate_editing_enabled:
            sec_types.append(("surface", self.tr("Section surfacique")))
        for key, label in sec_types:
            self._combo_sec_type.addItem(label, key)
        idx = self._combo_sec_type.findData(sec.section_type)
        if idx >= 0:
            self._combo_sec_type.setCurrentIndex(idx)
        form.addRow(self.tr("Type :"), self._combo_sec_type)

        # Associated material (editable)
        self._combo_sec_material = QComboBox()
        for mtag, mat in self._project.materials.items():
            self._combo_sec_material.addItem(f"{mat.name} ({mat.grade})", mtag)
            if mtag == sec.material_tag:
                self._combo_sec_material.setCurrentIndex(
                    self._combo_sec_material.count() - 1
                )
        form.addRow(self.tr("Matériau :"), self._combo_sec_material)

        self._spin_sec_thickness = self._make_spin(
            sec.thickness or 0.20,
            0.001,
            10.0,
            " m",
        )
        self._spin_sec_thickness.setSingleStep(0.01)
        form.addRow(self.tr("Épaisseur :"), self._spin_sec_thickness)

        self._combo_sec_surface_formulation = QComboBox()
        for formulation in SURFACE_FORMULATION_TYPES:
            self._combo_sec_surface_formulation.addItem(formulation, formulation)
        idx_formulation = self._combo_sec_surface_formulation.findData(
            sec.surface_formulation or "ShellMITC4"
        )
        if idx_formulation >= 0:
            self._combo_sec_surface_formulation.setCurrentIndex(idx_formulation)
        form.addRow(self.tr("Formulation :"), self._combo_sec_surface_formulation)

        # Geometric properties (editable)
        self._spin_area = self._make_spin(sec.area * 1e4, 0, 1e6)
        self._spin_area.setSuffix(" cm²")
        form.addRow(self.tr("Aire :"), self._spin_area)

        self._spin_iy = self._make_spin(sec.inertia_y * 1e8, 0, 1e12)
        self._spin_iy.setSuffix(" cm⁴")
        form.addRow(self.tr("Iy :"), self._spin_iy)

        self._spin_iz = self._make_spin(sec.inertia_z * 1e8, 0, 1e12)
        self._spin_iz.setSuffix(" cm⁴")
        form.addRow(self.tr("Iz :"), self._spin_iz)

        self._combo_sec_type.currentIndexChanged.connect(self._on_section_type_changed)
        self._on_section_type_changed()
        if is_section_builder_section:
            info = QLabel(
                self.tr(
                    "Cette section utilisateur se modifie uniquement avec le Section Builder."
                )
            )
            info.setWordWrap(True)
            info.setStyleSheet("color: #5f6368; font-size: 11px;")
            form.addRow(self.tr("Info :"), info)
            self._edit_sec_name.setEnabled(False)
            self._combo_sec_type.setEnabled(False)
            self._combo_sec_material.setEnabled(False)
            self._spin_sec_thickness.setEnabled(False)
            self._combo_sec_surface_formulation.setEnabled(False)
            self._spin_area.setEnabled(False)
            self._spin_iy.setEnabled(False)
            self._spin_iz.setEnabled(False)
        if sec.is_surface and not self._plate_editing_enabled:
            info = QLabel(self._plate_editing_reason or self.tr("Édition plaque indisponible."))
            info.setWordWrap(True)
            info.setStyleSheet("color: #8a5a00; font-size: 11px;")
            form.addRow(self.tr("Info :"), info)
            self._edit_sec_name.setEnabled(False)
            self._combo_sec_type.setEnabled(False)
            self._combo_sec_material.setEnabled(False)
            self._spin_sec_thickness.setEnabled(False)
            self._combo_sec_surface_formulation.setEnabled(False)
        form.addRow(
            self._make_buttons(
                self._apply_section,
                enabled=not (
                    is_section_builder_section
                    or (sec.is_surface and not self._plate_editing_enabled)
                ),
            )
        )

        self._layout.addWidget(group)

    def show_load(self, tag: int) -> None:
        """Show load."""
        if self._project is None or tag not in self._project.loads:
            return
        self._current_kind = "load"
        self._current_tag = tag
        lc = self._project.loads[tag]
        self._clear_form()

        group = QGroupBox(
            self.tr("Cas de charge — {name}").format(name=load_name_label(lc))
        )
        form = QFormLayout(group)

        self._edit_load_name = QLineEdit(lc.name)
        form.addRow(self.tr("Nom :"), self._edit_load_name)

        self._combo_load_type = QComboBox()
        for key, label in _LOAD_TYPES.items():
            self._combo_load_type.addItem(load_type_label(key), key)
        idx = self._combo_load_type.findData(lc.load_type)
        if idx >= 0:
            self._combo_load_type.setCurrentIndex(idx)
        form.addRow(self.tr("Type :"), self._combo_load_type)

        self._edit_load_category = QLineEdit(lc.category or "")
        self._edit_load_category.setPlaceholderText(self.tr("Ex : A, B, C, neige, vent..."))
        form.addRow(self.tr("Catégorie :"), self._edit_load_category)

        form.addRow(self._make_buttons(self._apply_load))

        # List nodal loads for this case
        nodal = [nl for nl in self._project.nodal_loads if nl.load_tag == tag]
        if nodal:
            form.addRow(QLabel(self.tr("— {count} charge(s) nodale(s) —").format(count=len(nodal))))
            for nl in nodal:
                parts = []
                for attr, label in [("fx", "Fx"), ("fy", "Fy"), ("fz", "Fz"),
                                    ("mx", "Mx"), ("my", "My"), ("mz", "Mz")]:
                    val = getattr(nl, attr, 0.0)
                    if val != 0:
                        unit = "kN" if attr.startswith("f") else "kN·m"
                        parts.append(f"{label}={val:.1f} {unit}")
                form.addRow(f"  N{nl.node_tag} :", QLabel(", ".join(parts) if parts else "0"))

        # Distributed loads
        elem_loads = [el for el in self._project.element_loads if el.load_tag == tag]
        if elem_loads:
            form.addRow(QLabel(self.tr("— {count} charge(s) répartie(s) —").format(count=len(elem_loads))))
            for el in elem_loads:
                parts = []
                for attr, label in [("wx", "wx"), ("wy", "wy"), ("wz", "wz")]:
                    val = getattr(el, attr, 0.0)
                    if val != 0:
                        parts.append(f"{label}={val:.1f}")
                form.addRow(f"  E{el.element_tag} :", QLabel(
                    (", ".join(parts) + " kN/m") if parts else "0 kN/m"
                ))

        self._layout.addWidget(group)

    def show_combination(self, tag: int) -> None:
        """Show combination."""
        if self._project is None or tag not in self._project.combinations:
            return
        self._current_kind = "combination"
        self._current_tag = tag
        combo = self._project.combinations[tag]
        self._clear_form()

        group = QGroupBox(self.tr("Combinaison — {name}").format(name=combo.name))
        form = QFormLayout(group)

        self._edit_combo_name = QLineEdit(combo.name)
        form.addRow(self.tr("Nom :"), self._edit_combo_name)

        self._combo_combo_type = QComboBox()
        for ct in ComboType:
            self._combo_combo_type.addItem(combo_type_label(ct.value), ct.value)
        idx = self._combo_combo_type.findData(combo.combo_type)
        if idx >= 0:
            self._combo_combo_type.setCurrentIndex(idx)
        form.addRow(self.tr("Type :"), self._combo_combo_type)

        # Editable factors
        self._combo_factor_spins: dict[int, QDoubleSpinBox] = {}
        if self._project.loads:
            form.addRow(QLabel(self.tr("— Facteurs —")))
            for ltag in sorted(self._project.loads.keys()):
                lc = self._project.loads[ltag]
                factor = combo.factors.get(ltag, 0.0)
                spin = self._make_spin(factor, 0.0, 99.99)
                spin.setDecimals(2)
                self._combo_factor_spins[ltag] = spin
                form.addRow(
                    self.tr("  {name} :").format(name=load_name_label(lc)),
                    spin,
                )

        form.addRow(self._make_buttons(self._apply_combination))

        self._layout.addWidget(group)

    # ── Application des modifications ─────────────────────────────────────

    def _apply_node(self) -> None:
        """Apply node."""
        if self._project is None or self._current_tag not in self._project.nodes:
            return
        node = self._project.nodes[self._current_tag]
        node.x = self._spin_x.value()
        node.y = self._spin_y.value()
        node.z = self._spin_z.value()
        node.fixities = tuple(
            int(cb.isChecked()) for cb in self._chk_fixities
        )
        self.node_modified.emit(self._current_tag)
        self.model_changed.emit()

    def _apply_element(self) -> None:
        """Apply element."""
        if self._project is None or self._current_tag not in self._project.elements:
            return
        elem = self._project.elements[self._current_tag]
        elem.node_i = self._combo_node_i.currentData()
        elem.node_j = self._combo_node_j.currentData()
        section_tag = self._combo_section.currentData()
        section = self._project.sections.get(section_tag)
        if section is None or section.is_surface:
            QMessageBox.warning(
                self,
                self.tr("Section barre requise"),
                self.tr("Un élément filaire doit utiliser une section de barre, pas une section plaque."),
            )
            return
        elem.section_tag = section_tag
        elem.element_type = self._combo_elem_type.currentText()
        elem.roll_angle_deg = float(self._spin_roll_angle.value())
        self.element_modified.emit(self._current_tag)
        self.model_changed.emit()

    def _apply_surface(self) -> None:
        """Apply surface."""
        if self._project is None or self._current_tag not in self._project.surface_elements:
            return
        surface = self._project.surface_elements[self._current_tag]
        section_tag = self._combo_surface_section.currentData()
        if section_tag in self._project.sections:
            expected_count = surface_expected_node_count(
                self._project.sections[section_tag].surface_formulation
            )
            actual_count = len(surface.node_tags)
            if actual_count != expected_count:
                QMessageBox.warning(
                    self,
                    self.tr("Formulation incompatible"),
                    self.tr(
                        "La section sélectionnée attend {expected_count} nœud(s), "
                        "mais la surface S{tag} en a {actual_count}."
                    ).format(
                        expected_count=expected_count,
                        tag=self._current_tag,
                        actual_count=actual_count,
                    ),
                )
                return
            surface.section_tag = section_tag
            surface.surface_type = surface_type_from_formulation(
                self._project.sections[section_tag].surface_formulation
            )
        self.surface_modified.emit(self._current_tag)
        self.model_changed.emit()

    def _apply_plate_region(self) -> None:
        """Apply plate region."""
        if self._project is None or self._current_tag not in self._project.plate_regions:
            return
        plate = self._project.plate_regions[self._current_tag]
        plate.mesh_mode = normalize_plate_mesh_mode(self._combo_plate_mesh_mode.currentData())
        plate.mesh_nx = int(self._spin_plate_mesh_nx.value())
        plate.mesh_ny = int(self._spin_plate_mesh_ny.value())
        self.surface_modified.emit(self._current_tag)
        self.model_changed.emit()
        self.show_surface(self._current_tag)

    def _apply_material(self) -> None:
        """Apply material."""
        if self._project is None or self._current_tag not in self._project.materials:
            return
        mat = self._project.materials[self._current_tag]
        mat.name = self._edit_mat_name.text().strip() or mat.name
        mat.material_type = self._combo_mat_type.currentData()
        mat.grade = self._combo_mat_grade.currentText() or mat.grade
        mat.properties = build_material_properties(
            unit_weight=self._spin_mat_unit_weight.value(),
            young_modulus=self._spin_mat_young.value(),
            poisson_ratio=self._spin_mat_poisson.value(),
            base_properties=mat.properties,
        )
        self.material_modified.emit(self._current_tag)
        self.model_changed.emit()

    def _apply_section(self) -> None:
        """Apply section."""
        if self._project is None or self._current_tag not in self._project.sections:
            return
        sec = self._project.sections[self._current_tag]
        if _is_section_builder_section(sec):
            return
        section_type = self._combo_sec_type.currentData()
        if sec.is_surface and section_type != "surface":
            used_by_surfaces = [
                surface.tag
                for surface in self._project.surface_elements.values()
                if surface.section_tag == self._current_tag
            ]
            if used_by_surfaces:
                QMessageBox.warning(
                    self,
                    self.tr("Section utilisée"),
                    self.tr(
                        "Cette section est encore affectée à une ou plusieurs surfaces. "
                        "Conservez un type de section plaque."
                    ),
                )
                return

        if section_type == "surface":
            new_formulation = normalize_surface_formulation(
                self._combo_sec_surface_formulation.currentData()
            )
            expected_count = surface_expected_node_count(new_formulation)
            incompatible_surfaces = [
                surface.tag
                for surface in self._project.surface_elements.values()
                if surface.section_tag == self._current_tag
                and len(surface.node_tags) != expected_count
            ]
            if incompatible_surfaces:
                actual_count = len(
                    self._project.surface_elements[incompatible_surfaces[0]].node_tags
                )
                QMessageBox.warning(
                    self,
                    self.tr("Formulation incompatible"),
                    self.tr(
                        "La formulation {formulation} attend {expected_count} nœud(s), "
                        "mais la surface S{tag} en a {actual_count}."
                    ).format(
                        formulation=new_formulation,
                        expected_count=expected_count,
                        tag=incompatible_surfaces[0],
                        actual_count=actual_count,
                    ),
                )
                return

        sec.name = self._edit_sec_name.text().strip() or sec.name
        sec.section_type = section_type
        sec.material_tag = self._combo_sec_material.currentData()
        if sec.section_type == "surface":
            sec.properties = {
                "thickness": self._spin_sec_thickness.value(),
                "element_formulation": new_formulation,
            }
            sec.area = 0.0
            sec.inertia_y = 0.0
            sec.inertia_z = 0.0
        else:
            sec.properties = {
                key: value
                for key, value in sec.properties.items()
                if key not in {"thickness", "element_formulation"}
            }
            sec.area = self._spin_area.value() * 1e-4       # cm² → m²
            sec.inertia_y = self._spin_iy.value() * 1e-8    # cm⁴ → m⁴
            sec.inertia_z = self._spin_iz.value() * 1e-8    # cm⁴ → m⁴
        self.section_modified.emit(self._current_tag)
        self.model_changed.emit()

    def _on_section_type_changed(self) -> None:
        """Handle section type changed."""
        is_surface = self._combo_sec_type.currentData() == "surface"
        if hasattr(self, "_spin_sec_thickness"):
            self._spin_sec_thickness.setEnabled(is_surface)
        if hasattr(self, "_combo_sec_surface_formulation"):
            self._combo_sec_surface_formulation.setEnabled(is_surface)
        for attr in ("_spin_area", "_spin_iy", "_spin_iz"):
            if hasattr(self, attr):
                getattr(self, attr).setEnabled(not is_surface)

    def _update_surface_section_summary(self) -> None:
        """Update surface section summary."""
        if self._project is None or not hasattr(self, "_combo_surface_section"):
            return
        section_tag = self._combo_surface_section.currentData()
        sec = self._project.sections.get(section_tag)
        if sec is None:
            self._lbl_surface_formulation.setText("-")
            self._lbl_surface_thickness.setText("-")
            self._lbl_surface_solver_type.setText("-")
            return

        formulation = sec.surface_formulation or "ShellMITC4"
        info = SURFACE_FORMULATION_INFOS.get(formulation, "")
        self._lbl_surface_formulation.setText(
            formulation if not info else f"{formulation} — {info}"
        )
        self._lbl_surface_thickness.setText(f"{sec.thickness:.3f} m")
        self._lbl_surface_solver_type.setText(
            surface_type_from_formulation(formulation)
        )

    def _surface_area(self, surface: "SurfaceElementData") -> float:
        """Handle surface area."""
        if self._project is None:
            return 0.0
        points = []
        for node_tag in surface.node_tags:
            node = self._project.nodes.get(node_tag)
            if node is None:
                return 0.0
            points.append((float(node.x), float(node.y), float(node.z)))
        if len(points) < 3:
            return 0.0

        area = 0.0
        origin = points[0]
        for idx in range(1, len(points) - 1):
            ux = points[idx][0] - origin[0]
            uy = points[idx][1] - origin[1]
            uz = points[idx][2] - origin[2]
            vx = points[idx + 1][0] - origin[0]
            vy = points[idx + 1][1] - origin[1]
            vz = points[idx + 1][2] - origin[2]
            cx = uy * vz - uz * vy
            cy = uz * vx - ux * vz
            cz = ux * vy - uy * vx
            area += (cx * cx + cy * cy + cz * cz) ** 0.5 * 0.5
        return area

    def _on_mat_type_changed(self) -> None:
        """Handle mat type changed."""
        if getattr(self, "_material_form_syncing", False):
            return
        self._update_material_grade_choices()
        self._apply_material_defaults_from_grade()

    def _on_mat_grade_changed(self) -> None:
        """Handle mat grade changed."""
        if getattr(self, "_material_form_syncing", False):
            return
        self._apply_material_defaults_from_grade()

    def _update_material_grade_choices(self, preferred_grade: str = "") -> None:
        """Update material grade choices."""
        mat_type = self._combo_mat_type.currentData()
        grades = _GRADES_BY_TYPE.get(mat_type, [])
        target_grade = preferred_grade if preferred_grade in grades else (grades[0] if grades else "")
        self._combo_mat_grade.blockSignals(True)
        self._combo_mat_grade.clear()
        self._combo_mat_grade.addItems(grades)
        idx = self._combo_mat_grade.findText(target_grade)
        if idx >= 0:
            self._combo_mat_grade.setCurrentIndex(idx)
        self._combo_mat_grade.blockSignals(False)

    def _apply_material_defaults_from_grade(self) -> None:
        """Apply the isotropic preset for the current material type and grade."""
        props = isotropic_material_properties(
            self._combo_mat_type.currentData(),
            self._combo_mat_grade.currentText(),
            {},
        )
        self._spin_mat_unit_weight.setValue(props["unit_weight"])
        self._spin_mat_young.setValue(props["young_modulus"])
        self._spin_mat_poisson.setValue(props["poisson_ratio"])
        self._update_material_info()
        self._update_material_derived_fields()

    def _update_material_info(self) -> None:
        """Update material info."""
        if hasattr(self, "_lbl_mat_info"):
            self._lbl_mat_info.setText(
                {
                    "concrete": self.tr("Matériau isotrope basé sur une classe de béton Eurocode 2."),
                    "rebar": self.tr("Matériau isotrope basé sur une nuance d'acier d'armature Eurocode 2."),
                    "steel": self.tr("Matériau isotrope basé sur une nuance d'acier de construction Eurocode 3."),
                }.get(self._combo_mat_type.currentData(), "")
            )

    def _update_material_derived_fields(self) -> None:
        """Update material derived fields."""
        if not hasattr(self, "_edit_mat_mass_density"):
            return
        density = unit_weight_to_density_kg_m3(self._spin_mat_unit_weight.value())
        shear = compute_shear_modulus(
            self._spin_mat_young.value(),
            self._spin_mat_poisson.value(),
        )
        self._edit_mat_mass_density.setText(f"{density:.1f} kg/m3")
        self._edit_mat_shear.setText(f"{shear:.0f} kPa")

    def _apply_load(self) -> None:
        """Apply load."""
        if self._project is None or self._current_tag not in self._project.loads:
            return
        lc = self._project.loads[self._current_tag]
        lc.name = self._edit_load_name.text().strip() or lc.name
        lc.load_type = self._combo_load_type.currentData() or lc.load_type
        lc.category = self._edit_load_category.text().strip() or None
        self.model_changed.emit()

    def _apply_combination(self) -> None:
        """Apply combination."""
        if self._project is None or self._current_tag not in self._project.combinations:
            return
        combo = self._project.combinations[self._current_tag]
        combo.name = self._edit_combo_name.text().strip() or combo.name
        combo.combo_type = self._combo_combo_type.currentData() or combo.combo_type
        # Update factors
        combo.factors.clear()
        for ltag, spin in self._combo_factor_spins.items():
            val = spin.value()
            if val > 0:
                combo.factors[ltag] = val
        self.model_changed.emit()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _update_plate_mesh_edit_state(self) -> None:
        """Update plate mesh edit state."""
        if not hasattr(self, "_combo_plate_mesh_mode"):
            return
        is_user = (
            normalize_plate_mesh_mode(self._combo_plate_mesh_mode.currentData())
            == PLATE_MESH_MODE_USER
        )
        self._spin_plate_mesh_nx.setEnabled(is_user and self._plate_editing_enabled)
        self._spin_plate_mesh_ny.setEnabled(is_user and self._plate_editing_enabled)

    def _make_buttons(self, apply_slot, *, enabled: bool = True) -> QWidget:
        """Create buttons."""
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        btn_apply = QPushButton(self.tr("Appliquer"))
        btn_apply.clicked.connect(apply_slot)
        btn_apply.setEnabled(enabled)
        btn_close = QPushButton(self.tr("Fermer"))
        btn_close.clicked.connect(self.clear_display)
        h.addWidget(btn_apply)
        h.addWidget(btn_close)
        return container

    def _clear_form(self) -> None:
        """Clear form."""
        self._placeholder.setVisible(False)
        while self._layout.count() > 1:
            child = self._layout.takeAt(1)
            widget = child.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _make_spin(self, value: float, vmin: float, vmax: float,
                   suffix: str = "") -> QDoubleSpinBox:
        """Create spin."""
        spin = QDoubleSpinBox()
        spin.setRange(vmin, vmax)
        spin.setDecimals(3)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setSingleStep(0.1)
        return spin
