from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from core.model_data import ProjectModel
from gui.dialogs.plate_section_dlg import PlateSectionDialog
from gui.dialogs.plate_section_manager_dlg import PlateSectionManagerDialog
from gui.dialogs.section_dlg import SectionDialog
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
