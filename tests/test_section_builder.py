from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QGraphicsItem

from core.model_data import ProjectModel, SectionData
from core.section_builder import SectionBuilderGeometryError, polygon_section_properties
from core.sections import get_profile, list_profile_families, list_profiles
from core.sectionproperties_adapter import is_sectionproperties_available
from gui.dialogs.section_builder_dlg import (
    SectionCalculationNoteDialog,
    SectionBuilderDialog,
    SectionBuilderView,
    SectionStressDialog,
    StandardProfileImportDialog,
)
from gui.dialogs.library_manager_dlg import _is_section_builder_section


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_polygon_section_properties_rectangle() -> None:
    props = polygon_section_properties(
        [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)]
    )

    assert props.area == pytest.approx(0.06)
    assert props.perimeter == pytest.approx(1.0)
    assert props.centroid_y == pytest.approx(0.10)
    assert props.centroid_z == pytest.approx(0.15)
    assert props.inertia_y == pytest.approx(0.20 * 0.30**3 / 12.0)
    assert props.inertia_z == pytest.approx(0.30 * 0.20**3 / 12.0)


def test_polygon_section_properties_rejects_crossing_edges() -> None:
    with pytest.raises(SectionBuilderGeometryError) as excinfo:
        polygon_section_properties(
            [(0.0, 0.0), (0.20, 0.20), (0.0, 0.20), (0.20, 0.0)]
        )

    assert excinfo.value.code == "polygon_crossing_edges"


def test_section_builder_view_snaps_points_to_grid() -> None:
    _app()
    view = SectionBuilderView()
    view.set_grid_step(0.05)

    view.add_point((0.023, 0.074))

    assert view.points() == [(0.0, 0.05)]


def test_section_builder_view_can_insert_update_and_remove_points() -> None:
    _app()
    view = SectionBuilderView()
    view.set_grid_step(0.05)
    view.set_points([(0.0, 0.0), (0.20, 0.0), (0.20, 0.20)], closed=False)

    inserted = view.insert_point_after(0)
    assert inserted == 1
    assert view.points()[inserted] == (0.10, 0.0)

    assert view.set_point(inserted, (0.126, 0.074)) is True
    assert view.points()[inserted] == (0.15, 0.05)

    assert view.remove_point(inserted) is True
    assert view.points() == [(0.0, 0.0), (0.20, 0.0), (0.20, 0.20)]


def test_section_builder_view_can_create_rectangle_and_circle_tools() -> None:
    _app()
    view = SectionBuilderView()
    view.set_grid_step(0.05)

    assert view.set_rectangle_from_corners((0.0, 0.0), (0.20, 0.30)) is True
    assert view.is_closed() is True
    assert view.points() == [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)]

    assert view.set_circle_from_center_edge((0.0, 0.0), (0.10, 0.0)) is True
    assert view.is_closed() is True
    assert len(view.points()) == 48
    assert view.points()[0] == pytest.approx((0.10, 0.0))


def test_section_builder_view_can_draw_hole_contour() -> None:
    _app()
    view = SectionBuilderView()
    view.set_grid_step(0.05)
    view.set_points(
        [(0.0, 0.0), (0.30, 0.0), (0.30, 0.30), (0.0, 0.30)],
        closed=True,
    )

    hole_index = view.start_hole()
    assert hole_index == 0
    view.add_point((0.10, 0.10))
    view.add_point((0.20, 0.10))
    view.add_point((0.20, 0.20))
    view.add_point((0.10, 0.20))

    assert view.close_contour() is True
    assert view.holes() == [[(0.10, 0.10), (0.20, 0.10), (0.20, 0.20), (0.10, 0.20)]]


def test_section_builder_dialog_returns_custom_polygon_section() -> None:
    _app()
    project = ProjectModel()
    material = project.add_material("Beton C30", "concrete", "C30/37")
    dlg = SectionBuilderDialog(materials=project.materials)

    dlg._view.set_points(
        [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)],
        closed=True,
    )

    assert dlg._analyze(show_errors=False) is True
    data = dlg.result()

    assert data["section_type"] == "custom_polygon"
    assert data["material_tag"] == material.tag
    assert data["area"] == pytest.approx(0.06)
    assert data["inertia_y"] == pytest.approx(0.20 * 0.30**3 / 12.0)
    assert data["inertia_z"] == pytest.approx(0.30 * 0.20**3 / 12.0)
    assert data["properties"]["source"] == "section_builder"
    assert data["properties"]["source_tool"] == "section_builder"
    assert data["properties"]["editable_with"] == "section_builder"
    assert data["properties"]["perimeter"] == pytest.approx(1.0)
    assert data["properties"]["points"][0] == (0.0, 0.0)
    assert dlg._view._centroid == pytest.approx((0.10, 0.15))


def test_section_builder_dialog_exposes_fused_sectionproperties_menu() -> None:
    _app()
    dlg = SectionBuilderDialog()

    menu_titles = [action.text() for action in dlg._menu_bar.actions()]
    assert menu_titles == ["Fichier", "sectionproperties"]
    tab_titles = [
        dlg._side_tabs.tabText(index)
        for index in range(dlg._side_tabs.count())
    ]
    assert tab_titles == ["Général", "Contour", "Calcul"]

    file_actions = [
        action.text()
        for action in dlg._menu_bar.actions()[0].menu().actions()
        if not action.isSeparator()
    ]
    assert file_actions == [
        "Nouveau",
        "Ouvrir...",
        "Importer profil standard...",
        "Enregistrer",
        "Enregistrer sous...",
        "Note de calcul...",
        "Imprimer le rapport",
        "Quitter",
    ]
    assert file_actions.index("Note de calcul...") < file_actions.index("Imprimer le rapport")
    assert dlg.act_calculation_note.isEnabled() is False
    assert dlg.act_print_report.isEnabled() is False
    assert "sections utilisateur" in dlg._lbl_builder_info.text()

    sectionproperties_actions = [
        action.text()
        for action in dlg._menu_bar.actions()[1].menu().actions()
        if not action.isSeparator()
    ]
    assert sectionproperties_actions == [
        "Calculer",
        "Résultats",
        "Afficher contrainte",
    ]
    assert dlg._btn_insert_shape.text() == "Appliquer la forme"
    assert dlg._btn_add_to_user_library.text() == "Ajouter à la bibliothèque standard"
    assert {"select", "polygon", "rectangle", "circle", "hole", "move", "delete"}.issubset(
        dlg._tool_actions
    )
    circle_index = dlg._combo_tool.findData("circle")
    assert circle_index >= 0
    dlg._combo_tool.setCurrentIndex(circle_index)
    assert dlg._view.tool_mode() == "circle"
    dlg._tool_actions["rectangle"].trigger()
    assert dlg._view.tool_mode() == "rectangle"
    assert dlg._combo_tool.currentData() == "rectangle"
    assert dlg.act_sp_show_stress.isEnabled() is is_sectionproperties_available()


def test_section_builder_dialog_generates_calculation_note() -> None:
    _app()
    dlg = SectionBuilderDialog()
    dlg._chk_use_sectionproperties.setChecked(False)
    dlg._view.set_points(
        [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)],
        closed=True,
    )

    assert dlg._calculation_note_text(show_errors=False) == ""
    assert dlg.act_calculation_note.isEnabled() is False
    assert dlg._analyze(show_errors=False) is True
    assert dlg.act_calculation_note.isEnabled() is True
    assert dlg.act_print_report.isEnabled() is True

    note = dlg._calculation_note_text(show_errors=False)

    assert "Note de calcul - Section Builder HEXA" in note
    assert "Rapport de section utilisateur" in note
    assert "Aire A" in note
    assert "6.000000e-02 m2" in note
    assert "Figure 1" in note
    if is_sectionproperties_available():
        assert "Figure 2" in note
        assert "Sigma zz totale" in note
    assert "Contraintes de référence" in note
    assert "Mxx" in note
    assert "Points extérieurs : 4" in note
    assert "vérification réglementaire" in note


def test_section_builder_report_preview_is_editable() -> None:
    _app()
    dlg = SectionBuilderDialog()
    dlg._chk_use_sectionproperties.setChecked(False)
    dlg._view.set_points(
        [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)],
        closed=True,
    )
    assert dlg._analyze(show_errors=False) is True
    html, resources = dlg._calculation_report(show_errors=False)

    preview = SectionCalculationNoteDialog(dlg, html, resources)

    assert "hexa-report:section-outline" in resources
    if is_sectionproperties_available():
        assert "hexa-report:stress-envelope" in resources
    assert preview._viewer.isReadOnly() is False
    assert preview._viewer.acceptRichText() is True
    assert preview._act_bold.isCheckable() is True
    assert preview._act_italic.isCheckable() is True
    assert preview._act_underline.isCheckable() is True


def test_standard_profile_import_dialog_filters_profiles_by_family() -> None:
    _app()
    dlg = StandardProfileImportDialog()
    families = list_profile_families()

    assert dlg._combo_family.count() == len(families)
    assert dlg._combo_family.currentData() in families
    assert dlg._combo_profile.count() == len(list_profiles(dlg._combo_family.currentData()))

    ipe_index = dlg._combo_family.findData("IPE")
    assert ipe_index >= 0
    dlg._combo_family.setCurrentIndex(ipe_index)

    assert dlg.selected_profile_name() in list_profiles("IPE")


def test_section_builder_dialog_imports_standard_profile_catalog_shape() -> None:
    _app()
    project = ProjectModel()
    project.add_material("Beton C30", "concrete", "C30/37")
    steel = project.add_material("Acier S355", "steel", "S355")
    dlg = SectionBuilderDialog(materials=project.materials)
    profile = get_profile("IPE 300")

    assert dlg._insert_standard_profile(profile.name, show_errors=False) is True
    assert dlg._active_catalog_profile == profile.name
    assert dlg._active_library_shape is None
    assert dlg._combo_material.currentData() == steel.tag
    assert dlg._view.is_closed() is True
    assert len(dlg._view.points()) == 12
    assert dlg._analyze(show_errors=False) is True

    data = dlg.result()
    assert data["name"] == profile.name
    assert data["section_type"] == "I_profile"
    assert data["material_tag"] == steel.tag
    assert data["properties"]["profile"] == profile.name
    assert data["properties"]["source"] == "profile_catalog"
    assert data["properties"]["source_tool"] == "section_builder"
    assert data["properties"]["editable_with"] == "section_builder"
    assert data["area"] == pytest.approx(profile.area)
    assert data["inertia_y"] == pytest.approx(profile.inertia_y)
    assert data["inertia_z"] == pytest.approx(profile.inertia_z)


def test_section_builder_dialog_meshes_imported_standard_profile_when_available() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")
    _app()
    project = ProjectModel()
    project.add_material("Acier S355", "steel", "S355")
    dlg = SectionBuilderDialog(materials=project.materials)

    assert dlg._insert_standard_profile("IPE 300", show_errors=False) is True
    assert dlg._chk_use_sectionproperties.isChecked() is True
    assert dlg._analyze(show_errors=False) is True

    data = dlg.result()
    assert data["section_type"] == "I_profile"
    assert data["properties"]["profile"] == "IPE 300"
    assert data["properties"]["source"] == "profile_catalog"
    assert data["properties"]["analysis_engine"] == "sectionproperties"
    assert data["properties"]["sectionproperties"]["mesh_node_count"] > 0
    assert data["properties"]["sectionproperties"]["mesh_triangle_count"] > 0
    assert dlg._sectionproperties_result is not None
    assert dlg._view._mesh is not None


def test_section_builder_dialog_calculates_and_plots_stress_when_available() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")
    _app()
    dlg = SectionBuilderDialog()
    dlg._view.set_points(
        [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)],
        closed=True,
    )

    result = dlg._calculate_stress_result(
        stress_key="zz",
        actions={"n": 0.0, "vx": 0.0, "vy": 0.0, "mxx": 1.0e3, "myy": 0.0, "mzz": 0.0},
        show_errors=False,
    )

    assert result is not None
    assert result.max_stress > result.min_stress
    assert dlg._sectionproperties_stress_result is result

    stress_dialog = SectionStressDialog(dlg)
    assert stress_dialog._calculate_and_plot(show_errors=False) is True
    assert stress_dialog._stress_result is not None
    stress_dialog._spin_mxx.setValue(2.0)
    assert dlg._sectionproperties_stress_result is not None
    assert dlg._sectionproperties_stress_result.actions["mxx"] == pytest.approx(2.0e3)
    assert dlg._analyze(show_errors=False) is True
    report_text = dlg._calculation_note_text(show_errors=False)
    assert "Mxx" in report_text
    assert "2.000 kN.m" in report_text


def test_section_builder_dialog_inserts_sectionproperties_library_shape() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")
    _app()
    project = ProjectModel()
    concrete = project.add_material("Beton C30", "concrete", "C30/37")
    project.add_material("Acier S355", "steel", "S355")
    dlg = SectionBuilderDialog(materials=project.materials)

    idx_rect = dlg._combo_shape.findData("rectangular")
    dlg._combo_shape.setCurrentIndex(idx_rect)

    assert dlg._insert_library_shape(show_errors=False) is True
    assert dlg._combo_material.currentData() == concrete.tag
    assert dlg._view.is_closed() is True
    assert len(dlg._view.points()) == 4
    ys = [point[0] for point in dlg._view.points()]
    zs = [point[1] for point in dlg._view.points()]
    assert max(ys) - min(ys) == pytest.approx(0.20)
    assert max(zs) - min(zs) == pytest.approx(0.30)
    assert dlg._spin_grid.value() == pytest.approx(0.01)
    assert dlg._view._grid_step == pytest.approx(0.01)
    first_marker = dlg._view._point_items[0]
    assert first_marker.rect().width() == pytest.approx(9.0)
    assert first_marker.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    assert dlg._analyze(show_errors=False) is True

    data = dlg.result()
    assert data["section_type"] == "sectionproperties"
    assert data["properties"]["source"] == "sectionproperties"
    assert data["properties"]["source_tool"] == "section_builder"
    assert data["properties"]["editable_with"] == "section_builder"
    assert data["properties"]["shape"] == "rectangular"
    assert data["area"] == pytest.approx(0.06)


def test_section_builder_dialog_marks_user_library_sections() -> None:
    _app()
    dlg = SectionBuilderDialog()
    dlg._view.set_points(
        [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)],
        closed=True,
    )

    dlg._accept_for_user_library()
    data = dlg.result()

    assert data["properties"]["user_library"] is True
    assert data["properties"]["source_tool"] == "section_builder"
    assert data["properties"]["editable_with"] == "section_builder"


def test_section_manager_detects_builder_sections() -> None:
    builder_section = SectionData(
        tag=1,
        name="IPE utilisateur",
        section_type="I_profile",
        material_tag=1,
        properties={"source_tool": "section_builder"},
    )
    regular_section = SectionData(
        tag=2,
        name="IPE standard",
        section_type="I_profile",
        material_tag=1,
        properties={"profile": "IPE 300"},
    )

    assert _is_section_builder_section(builder_section) is True
    assert _is_section_builder_section(regular_section) is False


def test_section_builder_dialog_inserts_hollow_library_shape_with_hole() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")
    _app()
    dlg = SectionBuilderDialog()
    idx_chs = dlg._combo_shape.findData("chs")
    dlg._combo_shape.setCurrentIndex(idx_chs)

    assert dlg._insert_library_shape(show_errors=False) is True
    assert len(dlg._view.holes()) == 1
    assert dlg._analyze(show_errors=False) is True

    data = dlg.result()
    assert data["section_type"] == "sectionproperties"
    assert data["properties"]["shape"] == "chs"
    assert data["properties"]["hole_count"] == 1


def test_section_builder_dialog_uses_sectionproperties_when_available() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")
    _app()
    dlg = SectionBuilderDialog()
    dlg._view.set_points(
        [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)],
        closed=True,
    )

    assert dlg._chk_use_sectionproperties.isChecked() is True
    assert dlg._analyze(show_errors=False) is True
    data = dlg.result()

    assert data["properties"]["analysis_engine"] == "sectionproperties"
    assert data["area"] == pytest.approx(0.06)
    assert data["properties"]["sectionproperties"]["mesh_node_count"] > 4
    assert data["properties"]["sectionproperties"]["mesh_triangle_count"] > 1
    assert dlg._sectionproperties_result is not None
    assert dlg._view._mesh is not None


def test_section_builder_dialog_can_use_polygonal_fallback() -> None:
    _app()
    dlg = SectionBuilderDialog()
    dlg._chk_use_sectionproperties.setChecked(False)
    dlg._view.set_points(
        [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)],
        closed=True,
    )

    assert dlg._analyze(show_errors=False) is True
    data = dlg.result()

    assert data["properties"]["analysis_engine"] == "polygonal"
    assert "sectionproperties" not in data["properties"]
    assert dlg._sectionproperties_result is None


def test_section_builder_dialog_saves_section_with_hole() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")
    _app()
    dlg = SectionBuilderDialog()
    dlg._view.set_points(
        [(0.0, 0.0), (0.30, 0.0), (0.30, 0.30), (0.0, 0.30)],
        closed=True,
    )
    dlg._view.start_hole()
    for point in [(0.10, 0.10), (0.20, 0.10), (0.20, 0.20), (0.10, 0.20)]:
        dlg._view.add_point(point)
    assert dlg._view.close_contour() is True

    assert dlg._analyze(show_errors=False) is True
    data = dlg.result()

    assert data["properties"]["analysis_engine"] == "sectionproperties"
    assert data["properties"]["hole_count"] == 1
    assert data["properties"]["holes"][0][0] == (0.10, 0.10)
    assert data["area"] == pytest.approx(0.08, rel=1e-6)
    assert data["properties"]["sectionproperties"]["mesh_triangle_count"] > 1


def test_section_builder_dialog_forces_sectionproperties_for_holes() -> None:
    if not is_sectionproperties_available():
        pytest.skip("sectionproperties is not installed")
    _app()
    dlg = SectionBuilderDialog()
    dlg._chk_use_sectionproperties.setChecked(False)
    dlg._view.set_points(
        [(0.0, 0.0), (0.30, 0.0), (0.30, 0.30), (0.0, 0.30)],
        closed=True,
    )
    dlg._view.start_hole()
    for point in [(0.10, 0.10), (0.20, 0.10), (0.20, 0.20), (0.10, 0.20)]:
        dlg._view.add_point(point)
    dlg._view.close_contour()

    assert dlg._analyze(show_errors=False) is True
    assert dlg.result()["properties"]["analysis_engine"] == "sectionproperties"


def test_section_builder_dialog_edits_points_from_table() -> None:
    _app()
    dlg = SectionBuilderDialog()
    dlg._view.set_points([(0.0, 0.0), (0.20, 0.0), (0.20, 0.20)], closed=False)

    item = dlg._table_points.item(1, 0)
    assert item is not None
    item.setText("0.15")

    assert dlg._view.points()[1] == (0.15, 0.0)
