from __future__ import annotations

import pytest

from core.analysis_model_builder import build_analysis_model
from core.model_data import ProjectModel
from core.plate_mesher import GeneratedPlateMesh


def _plate_project(mesh_nx: int = 4, mesh_ny: int = 4) -> ProjectModel:
    project = ProjectModel(name="Forced plate nodes")
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
        mesh_nx=mesh_nx,
        mesh_ny=mesh_ny,
    )
    return project


def _generated_mesh(analysis_model: ProjectModel, plate_tag: int = 1) -> GeneratedPlateMesh:
    return getattr(analysis_model, "generated_plate_meshes")[plate_tag]


def _nodes_at(
    project: ProjectModel,
    x: float,
    y: float,
    z: float,
    *,
    tol: float = 1e-9,
) -> list[int]:
    return [
        tag
        for tag, node in project.nodes.items()
        if abs(float(node.x) - x) <= tol
        and abs(float(node.y) - y) <= tol
        and abs(float(node.z) - z) <= tol
    ]


def _index_approx(values: tuple[float, ...], target: float) -> int:
    for index, value in enumerate(values):
        if value == pytest.approx(target):
            return index
    raise AssertionError(f"{target} not found in {values!r}")


def test_interior_node_is_reused_by_analysis_mesh() -> None:
    project = _plate_project(mesh_nx=4, mesh_ny=4)
    project.add_node(2.5, 2.5, 0.0)

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)

    assert 5 in set(mesh.node_tags.values())
    assert mesh.u_values == pytest.approx((0.0, 0.25, 0.5, 0.75, 1.0))
    assert mesh.v_values == pytest.approx((0.0, 0.25, 0.5, 0.75, 1.0))
    assert mesh.node_tags[(2, 2)] == 5
    assert all((2, j) in mesh.node_tags for j in range(mesh.mesh_ny + 1))
    assert all((i, 2) in mesh.node_tags for i in range(mesh.mesh_nx + 1))
    assert _nodes_at(analysis_model, 2.5, 2.5, 0.0) == [5]
    assert getattr(analysis_model, "plate_intersection_reports")[1].node_hits[0].node_tag == 5


def test_off_grid_interior_node_forces_new_u_and_v_lines() -> None:
    project = _plate_project(mesh_nx=4, mesh_ny=4)
    project.add_node(2.0, 1.5, 0.0)

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)
    forced_i = _index_approx(mesh.u_values, 0.4)
    forced_j = _index_approx(mesh.v_values, 0.3)

    assert mesh.u_values == pytest.approx((0.0, 0.2, 0.4, 0.7, 1.0))
    assert mesh.v_values == pytest.approx((0.0, 0.3, 0.5333333333, 0.7666666667, 1.0))
    assert mesh.mesh_nx == 4
    assert mesh.mesh_ny == 4
    assert mesh.node_tags[(forced_i, forced_j)] == 5
    assert _nodes_at(analysis_model, 2.0, 1.5, 0.0) == [5]


def test_edge_node_is_reused_by_analysis_mesh() -> None:
    project = _plate_project(mesh_nx=4, mesh_ny=4)
    project.add_node(2.5, 0.0, 0.0)

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)

    assert mesh.node_tags[(2, 0)] == 5
    assert _nodes_at(analysis_model, 2.5, 0.0, 0.0) == [5]


def test_user_project_is_not_polluted_by_generated_mesh_nodes() -> None:
    project = _plate_project(mesh_nx=4, mesh_ny=4)
    project.add_node(2.5, 2.5, 0.0)
    original_node_tags = set(project.nodes)

    analysis_model = build_analysis_model(project)

    assert set(project.nodes) == original_node_tags
    assert len(project.nodes) == 5
    assert len(analysis_model.nodes) == 25
    assert 5 in analysis_model.nodes
    assert set(analysis_model.nodes) - set(project.nodes)


def test_aligned_coplanar_bar_endpoints_force_structured_grid_lines() -> None:
    project = _plate_project(mesh_nx=4, mesh_ny=4)
    project.add_node(1.0, 2.5, 0.0)
    project.add_node(4.0, 2.5, 0.0)
    project.add_element(5, 6, section_tag=2)

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)

    assert mesh.u_values[_index_approx(mesh.u_values, 0.2)] == pytest.approx(0.2)
    assert mesh.u_values[_index_approx(mesh.u_values, 0.8)] == pytest.approx(0.8)
    assert mesh.v_values[_index_approx(mesh.v_values, 0.5)] == pytest.approx(0.5)
    assert 5 in set(mesh.node_tags.values())
    assert 6 in set(mesh.node_tags.values())
    assert _nodes_at(analysis_model, 1.0, 2.5, 0.0) == [5]
    assert _nodes_at(analysis_model, 4.0, 2.5, 0.0) == [6]


def test_forced_bar_line_subdivides_each_span_uniformly() -> None:
    project = ProjectModel(name="Forced spans")
    material = project.add_material("Beton C30", "concrete", "C30/37")
    surface_section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=material.tag,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_section(
        "Poutre",
        "rectangular",
        material_tag=material.tag,
        properties={"b": 0.30, "h": 0.50},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(7.0, 0.0, 0.0)
    project.add_node(7.0, 5.0, 0.0)
    project.add_node(0.0, 5.0, 0.0)
    project.add_plate_region(
        (1, 2, 3, 4),
        section_tag=surface_section.tag,
        mesh_nx=6,
        mesh_ny=2,
    )
    project.add_node(3.0, 0.0, 0.0)
    project.add_node(3.0, 5.0, 0.0)
    project.add_element(5, 6, section_tag=2)

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)
    x_values = [7.0 * value for value in mesh.u_values]

    assert x_values == pytest.approx(
        (0.0, 1.0, 2.0, 3.0, 13.0 / 3.0, 17.0 / 3.0, 7.0)
    )
    assert mesh.mesh_nx == 6
    assert mesh.node_tags[(_index_approx(mesh.u_values, 3.0 / 7.0), 0)] == 5
    assert mesh.node_tags[(_index_approx(mesh.u_values, 3.0 / 7.0), mesh.mesh_ny)] == 6
