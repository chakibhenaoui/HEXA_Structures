from __future__ import annotations

import pytest

from core.geometry.plate_intersections import (
    PlateBarIntersectionKind,
    PlateNodeLocation,
    detect_plate_intersections,
)
from core.model_data import ProjectModel


def _plate_project() -> ProjectModel:
    project = ProjectModel(name="Plate intersections")
    material = project.add_material("Beton C30", "concrete", "C30/37")
    surface_section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=material.tag,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_section(
        "Poteau 30x30",
        "rectangular",
        material_tag=material.tag,
        properties={"b": 0.30, "h": 0.30},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 5.0, 0.0)
    project.add_node(0.0, 5.0, 0.0)
    project.add_plate_region(
        (1, 2, 3, 4),
        section_tag=surface_section.tag,
        name="P1",
        mesh_nx=4,
        mesh_ny=4,
    )
    return project


def _bar_section_tag(project: ProjectModel) -> int:
    return 2


def _report(project: ProjectModel):
    return detect_plate_intersections(project, project.plate_regions[1])


def test_node_inside_is_detected() -> None:
    project = _plate_project()
    project.add_node(2.5, 2.5, 0.0)

    report = _report(project)

    hit = next(hit for hit in report.node_hits if hit.node_tag == 5)
    assert hit.location is PlateNodeLocation.INSIDE
    assert hit.u == pytest.approx(0.5)
    assert hit.v == pytest.approx(0.5)


def test_node_on_edge_is_detected() -> None:
    project = _plate_project()
    project.add_node(2.5, 0.0, 0.0)

    report = _report(project)

    hit = next(hit for hit in report.node_hits if hit.node_tag == 5)
    assert hit.location is PlateNodeLocation.ON_EDGE
    assert hit.u == pytest.approx(0.5)
    assert hit.v == pytest.approx(0.0)


def test_existing_plate_corner_nodes_are_ignored_explicitly() -> None:
    project = _plate_project()

    report = _report(project)

    assert report.node_hits == []
    assert not any("coin" in warning.lower() for warning in report.warnings)


def test_endpoint_on_plate_bar_is_detected() -> None:
    project = _plate_project()
    project.add_node(2.5, 2.5, -3.0)
    project.add_node(2.5, 2.5, 0.0)
    project.add_element(5, 6, section_tag=_bar_section_tag(project))

    report = _report(project)

    hit = next(hit for hit in report.bar_hits if hit.element_tag == 1)
    assert hit.kind is PlateBarIntersectionKind.ENDPOINT_ON_PLATE
    assert hit.point == pytest.approx((2.5, 2.5, 0.0))
    assert hit.u == pytest.approx(0.5)
    assert hit.v == pytest.approx(0.5)


def test_bar_crossing_plate_plane_at_point_is_detected() -> None:
    project = _plate_project()
    project.add_node(2.5, 2.5, -3.0)
    project.add_node(2.5, 2.5, 3.0)
    project.add_element(5, 6, section_tag=_bar_section_tag(project))

    report = _report(project)

    hit = next(hit for hit in report.bar_hits if hit.element_tag == 1)
    assert hit.kind is PlateBarIntersectionKind.CROSSES_PLANE_AT_POINT
    assert hit.point == pytest.approx((2.5, 2.5, 0.0))
    assert hit.u == pytest.approx(0.5)
    assert hit.v == pytest.approx(0.5)


def test_bar_crossing_plate_plane_outside_polygon_is_ignored() -> None:
    project = _plate_project()
    project.add_node(8.0, 8.0, -3.0)
    project.add_node(8.0, 8.0, 3.0)
    project.add_element(5, 6, section_tag=_bar_section_tag(project))

    report = _report(project)

    assert not any(hit.element_tag == 1 for hit in report.bar_hits)


def test_aligned_coplanar_bar_is_structured_mesh_compatible() -> None:
    project = _plate_project()
    project.add_node(1.0, 2.5, 0.0)
    project.add_node(4.0, 2.5, 0.0)
    project.add_element(5, 6, section_tag=_bar_section_tag(project))

    report = _report(project)

    hit = next(hit for hit in report.bar_hits if hit.element_tag == 1)
    assert hit.kind is PlateBarIntersectionKind.LIES_IN_PLATE_PLANE
    assert "compatible" in hit.message.lower()


def test_diagonal_coplanar_bar_is_reported_as_unsupported_skew() -> None:
    project = _plate_project()
    project.add_node(1.0, 1.0, 0.0)
    project.add_node(4.0, 4.0, 0.0)
    project.add_element(5, 6, section_tag=_bar_section_tag(project))

    report = _report(project)

    hit = next(hit for hit in report.bar_hits if hit.element_tag == 1)
    assert hit.kind is PlateBarIntersectionKind.UNSUPPORTED_SKEW_IN_PLANE
    assert report.warnings


def test_coplanar_bar_crossing_plate_edge_is_detected() -> None:
    project = _plate_project()
    project.add_node(-1.0, 2.5, 0.0)
    project.add_node(6.0, 2.5, 0.0)
    project.add_element(5, 6, section_tag=_bar_section_tag(project))

    report = _report(project)

    hit = next(hit for hit in report.bar_hits if hit.element_tag == 1)
    assert hit.kind is PlateBarIntersectionKind.CROSSES_PLATE_EDGE
    assert report.warnings
