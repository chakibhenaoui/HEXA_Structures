from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from core.model_data import ProjectModel
from core.sectionproperties_adapter import is_sectionproperties_available
from gui.dialogs.plate_section_dlg import PlateSectionDialog
from gui.dialogs.plate_section_manager_dlg import PlateSectionManagerDialog
from gui.dialogs.section_dlg import (
    SectionDialog,
    _section_geometry_error_code,
    _section_properties,
)
from gui.dialogs.section_builder_dlg import SectionBuilderDialog
from gui.widgets.plane_editor_view import PlaneEditorView
from gui.widgets.property_panel import PropertyPanel


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _surface_project() -> ProjectModel:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    project.add_section("Dalle 20 cm", "surface", 1, properties={"thickness": 0.20})
    project.add_surface_element((1, 2, 3, 4), section_tag=1)
    return project


def test_section_dialog_surface_result() -> None:
    _app()
    project = _surface_project()

    dlg = SectionDialog(
        materials=project.materials,
        name="Dalle 25 cm",
        section_type="surface",
        material_tag=1,
        properties={"thickness": 0.25},
    )

    data = dlg.result()

    assert data["name"] == "Dalle 25 cm"
    assert data["section_type"] == "surface"
    assert data["properties"]["thickness"] == pytest.approx(0.25)
    assert data["area"] == 0.0
    assert data["inertia_y"] == 0.0
    assert data["inertia_z"] == 0.0
    assert "Section surfacique" in dlg._lbl_summary.text()


def test_section_dialog_profile_families_come_from_catalog() -> None:
    _app()
    dlg = SectionDialog(section_type="I_profile")

    families = [
        dlg._combo_family.itemText(index)
        for index in range(dlg._combo_family.count())
    ]

    assert families[:4] == ["IPE", "HEA", "HEB", "HEM"]
    assert {"UPN", "UPE", "CHS", "SHS", "RHS", "L", "L unequal"}.issubset(families)


def test_section_dialog_auto_selects_material_from_section_type() -> None:
    _app()
    project = ProjectModel()
    concrete = project.add_material("Beton C30", "concrete", "C30/37")
    steel = project.add_material("Acier S355", "steel", "S355")

    dlg = SectionDialog(materials=project.materials, section_type="I_profile")

    assert dlg._combo_material.currentData() == steel.tag

    idx_rectangular = dlg._combo_type.findData("rectangular")
    dlg._combo_type.setCurrentIndex(idx_rectangular)

    assert dlg._combo_material.currentData() == concrete.tag

    idx_profile = dlg._combo_type.findData("I_profile")
    dlg._combo_type.setCurrentIndex(idx_profile)

    assert dlg._combo_material.currentData() == steel.tag


def test_section_dialog_offers_parametric_steel_shapes() -> None:
    _app()
    dlg = SectionDialog()

    section_types = {
        dlg._combo_type.itemData(index)
        for index in range(dlg._combo_type.count())
    }

    assert {
        "I",
        "channel",
        "angle",
        "pipe",
        "tube",
        "I_profile",
    }.issubset(section_types)


def test_section_dialog_parametric_shape_result_and_preview() -> None:
    _app()
    project = ProjectModel()
    project.add_material("Beton C30", "concrete", "C30/37")
    steel = project.add_material("Acier S355", "steel", "S355")

    dlg = SectionDialog(materials=project.materials, section_type="angle")

    data = dlg.result()

    assert dlg._combo_material.currentData() == steel.tag
    assert data["section_type"] == "angle"
    assert data["area"] > 0.0
    assert data["inertia_y"] > 0.0
    assert data["inertia_z"] > 0.0
    assert data["properties"]["t"] == pytest.approx(0.008)
    assert len(dlg._preview._outer) == 6

    idx_pipe = dlg._combo_type.findData("pipe")
    dlg._combo_type.setCurrentIndex(idx_pipe)
    assert len(dlg._preview._outer) == 64
    assert len(dlg._preview._inner) == 64


def test_section_dialog_catalog_profile_is_selected_not_parametric() -> None:
    _app()
    dlg = SectionDialog(section_type="I_profile")

    assert "I_profile" not in dlg._shape_spins
    assert dlg._stack.currentIndex() == dlg._page_by_type["I_profile"]
    assert dlg._combo_profile.count() > 0
    assert dlg._preview._outer


def test_section_dialog_limits_pipe_thickness_to_valid_inner_diameter() -> None:
    _app()
    dlg = SectionDialog(section_type="pipe")
    spins = dlg._shape_spins["pipe"]

    spins["d"].setValue(0.050)
    spins["t"].setValue(0.040)

    assert spins["t"].maximum() == pytest.approx(0.024)
    assert spins["t"].value() == pytest.approx(0.024)
    assert _section_geometry_error_code("pipe", dlg._current_section_properties()) is None


def test_section_dialog_limits_i_shape_to_valid_web_and_flanges() -> None:
    _app()
    dlg = SectionDialog(section_type="I")
    spins = dlg._shape_spins["I"]

    spins["b"].setValue(0.050)
    spins["h"].setValue(0.080)
    spins["tw"].setValue(0.080)
    spins["tf"].setValue(0.060)

    assert spins["tw"].maximum() == pytest.approx(0.049)
    assert spins["tf"].maximum() == pytest.approx(0.039)
    assert spins["tw"].value() == pytest.approx(0.049)
    assert spins["tf"].value() == pytest.approx(0.039)
    assert _section_geometry_error_code("I", dlg._current_section_properties()) is None


def test_invalid_parametric_section_properties_return_zero_values() -> None:
    area, iy, iz = _section_properties(
        "tube",
        {"h": 0.20, "b": 0.10, "t": 0.06},
    )

    assert (area, iy, iz) == (0.0, 0.0, 0.0)
    assert _section_geometry_error_code(
        "tube",
        {"h": 0.20, "b": 0.10, "t": 0.06},
    ) == "tube_too_thick"


def test_section_dialog_keeps_explicit_initial_material() -> None:
    _app()
    project = ProjectModel()
    concrete = project.add_material("Beton C30", "concrete", "C30/37")
    project.add_material("Acier S355", "steel", "S355")

    dlg = SectionDialog(
        materials=project.materials,
        section_type="I_profile",
        material_tag=concrete.tag,
    )

    assert dlg._combo_material.currentData() == concrete.tag


def test_section_builder_creates_sectionproperties_user_section() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")
    _app()
    project = ProjectModel()
    concrete = project.add_material("Beton C30", "concrete", "C30/37")
    project.add_material("Acier S355", "steel", "S355")

    dlg = SectionBuilderDialog(materials=project.materials)
    idx_rect = dlg._combo_shape.findData("rectangular")
    dlg._combo_shape.setCurrentIndex(idx_rect)
    dlg._insert_library_shape(show_errors=False)

    assert dlg._combo_material.currentData() == concrete.tag
    assert dlg._analyze(show_errors=False) is True

    data = dlg.result()

    assert data["section_type"] == "sectionproperties"
    assert data["area"] == pytest.approx(0.06)
    assert data["inertia_y"] > 0.0
    assert data["inertia_z"] > 0.0
    assert data["properties"]["source"] == "sectionproperties"
    assert data["properties"]["display_type"] == "rectangular"


def test_section_builder_exposes_sectionproperties_workbench_layout() -> None:
    _app()
    dlg = SectionBuilderDialog()

    menu_titles = [action.text() for action in dlg._menu_bar.actions()]
    assert menu_titles == ["Fichier", "sectionproperties"]
    assert dlg._combo_shape.count() >= 6
    assert dlg._library_params_layout.rowCount() >= 1
    assert "sectionproperties" in dlg._lbl_library_status.text()
    assert dlg.act_print_report.isEnabled() is False
    assert dlg.act_sp_show_stress.isEnabled() is False


def test_plate_section_dialog_result_includes_formulation() -> None:
    _app()
    project = _surface_project()

    dlg = PlateSectionDialog(
        materials=project.materials,
        name="Dalle RDC",
        material_tag=1,
        properties={"thickness": 0.22, "element_formulation": "ShellDKGQ"},
    )

    data = dlg.result()

    assert data["name"] == "Dalle RDC"
    assert data["section_type"] == "surface"
    assert data["material_tag"] == 1
    assert data["properties"]["thickness"] == pytest.approx(0.22)
    assert data["properties"]["element_formulation"] == "ShellDKGQ"
    assert "plate" in dlg.lbl_formulation_info.text().lower()


def test_plate_section_dialog_does_not_offer_tri31() -> None:
    _app()
    project = _surface_project()

    dlg = PlateSectionDialog(materials=project.materials)

    assert "Tri31" not in dlg._radio_by_formulation


def test_plate_section_dialog_uses_ok_label_in_edit_mode() -> None:
    _app()
    project = _surface_project()

    dlg = PlateSectionDialog(
        materials=project.materials,
        name="Dalle RDC",
        material_tag=1,
        properties={"thickness": 0.22},
    )

    assert dlg.button_box.button(QDialogButtonBox.Ok).text() == "OK"


def test_plate_section_manager_does_not_reuse_line_section_tag() -> None:
    _app()
    project = ProjectModel()
    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "IPE 100",
        "I_profile",
        1,
        properties={"h": 0.10, "b": 0.055, "tw": 0.0041, "tf": 0.0057},
    )

    dlg = PlateSectionManagerDialog(
        sections=project.sections,
        materials=project.materials,
    )

    assert dlg._next_tag() == 2


def test_property_panel_updates_surface_thickness() -> None:
    _app()
    project = _surface_project()
    panel = PropertyPanel()
    panel.set_project(project)
    panel.show_section(1)

    assert panel._combo_sec_type.findData("surface") >= 0
    assert panel._spin_sec_thickness.isEnabled() is True
    assert panel._spin_area.isEnabled() is False

    panel._spin_sec_thickness.setValue(0.28)
    panel._apply_section()

    sec = project.sections[1]
    assert sec.is_surface
    assert sec.thickness == pytest.approx(0.28)
    assert sec.surface_formulation == "ShellMITC4"
    assert sec.area == 0.0
    assert sec.inertia_y == 0.0
    assert sec.inertia_z == 0.0


def test_plane_editor_surface_polygons_follow_active_plane() -> None:
    _app()
    project = _surface_project()
    view = PlaneEditorView()
    view.set_project(project)
    view.set_plane_context("XY", 0.0)

    polygons = view._surface_polygons_on_plane()

    assert polygons == [[(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)]]

    view.set_plane_context("XY", 1.0)
    assert view._surface_polygons_on_plane() == []


def test_property_panel_updates_surface_element_assignment() -> None:
    _app()
    project = _surface_project()
    project.add_section(
        "Voile 25 cm",
        "surface",
        1,
        properties={"thickness": 0.25, "element_formulation": "ShellDKGQ"},
    )
    panel = PropertyPanel()
    panel.set_project(project)
    panel.show_surface(1)

    panel._combo_surface_section.setCurrentIndex(
        panel._combo_surface_section.findData(2)
    )
    panel._apply_surface()

    surface = project.surface_elements[1]
    assert surface.section_tag == 2
    assert surface.surface_type == "plate"
    assert "ShellDKGQ" in panel._lbl_surface_formulation.text()


def test_property_panel_rejects_incompatible_surface_section_assignment(monkeypatch) -> None:
    _app()
    project = _surface_project()
    project.add_section(
        "Triangle libre",
        "surface",
        1,
        properties={"thickness": 0.18, "element_formulation": "Tri31"},
    )
    panel = PropertyPanel()
    panel.set_project(project)
    panel.show_surface(1)

    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(str(args[2])) or QMessageBox.Ok,
    )

    panel._combo_surface_section.setCurrentIndex(
        panel._combo_surface_section.findData(2)
    )
    panel._apply_surface()

    assert project.surface_elements[1].section_tag == 1
    assert warnings
    assert "attend 3 nœud(s)" in warnings[0]


def test_property_panel_does_not_offer_tri31_for_new_surface_formulations() -> None:
    _app()
    project = _surface_project()
    panel = PropertyPanel()
    panel.set_project(project)
    panel.show_section(1)

    assert panel._combo_sec_surface_formulation.findData("Tri31") == -1
    assert project.sections[1].surface_formulation == "ShellMITC4"


def test_property_panel_can_gray_surface_editing() -> None:
    _app()
    project = _surface_project()
    panel = PropertyPanel()
    panel.set_project(project)
    panel.set_plate_editing_enabled(
        False,
        "Les plaques sont disponibles uniquement avec OpenSeesPy.",
    )
    panel.show_surface(1)

    assert panel._combo_surface_section.isEnabled() is False

    panel.show_section(1)
    assert panel._combo_sec_type.isEnabled() is False
    assert panel._combo_sec_surface_formulation.isEnabled() is False
