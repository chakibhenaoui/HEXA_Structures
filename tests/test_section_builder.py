from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core.model_data import ProjectModel
from core.section_builder import SectionBuilderGeometryError, polygon_section_properties
from core.sectionproperties_adapter import is_sectionproperties_available
from gui.dialogs.section_builder_dlg import SectionBuilderDialog, SectionBuilderView


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
    assert data["properties"]["perimeter"] == pytest.approx(1.0)
    assert data["properties"]["points"][0] == (0.0, 0.0)
    assert dlg._view._centroid == pytest.approx((0.10, 0.15))


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
