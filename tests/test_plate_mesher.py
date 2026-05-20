from __future__ import annotations

import pytest

from core.analysis_model_builder import build_analysis_model
from core.model_data import (
    LoadData,
    PlateEdgeSupportData,
    PlateSurfaceLoadData,
    ProjectModel,
)
from core.plate_mesh_settings import effective_plate_mesh_divisions
from core.plate_mesher import GeneratedPlateMesh
from core.self_weight import surface_area_m2


def _plate_project(mesh_nx: int = 2, mesh_ny: int = 2) -> ProjectModel:
    project = ProjectModel(name="Plate mesher")
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_plate_region(
        (1, 2, 3, 4),
        section_tag=section.tag,
        name="Dalle P1",
        mesh_nx=mesh_nx,
        mesh_ny=mesh_ny,
    )
    return project


def _generated_mesh(analysis_model: ProjectModel, plate_tag: int = 1) -> GeneratedPlateMesh:
    meshes = getattr(analysis_model, "generated_plate_meshes")
    return meshes[plate_tag]


def test_plate_1x1_reuses_four_corner_nodes_and_creates_one_surface() -> None:
    project = _plate_project(mesh_nx=1, mesh_ny=1)

    analysis_model = build_analysis_model(project)

    assert len(analysis_model.nodes) == 4
    assert len(analysis_model.surface_elements) == 1
    assert len(_generated_mesh(analysis_model).node_tags) == 4
    assert len(_generated_mesh(analysis_model).surface_tags) == 1


def test_plate_2x2_creates_nine_nodes_and_four_surfaces() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)

    analysis_model = build_analysis_model(project)

    assert len(analysis_model.nodes) == 9
    assert len(analysis_model.surface_elements) == 4


def test_plate_4x3_creates_twenty_nodes_and_twelve_surfaces() -> None:
    project = _plate_project(mesh_nx=4, mesh_ny=3)

    analysis_model = build_analysis_model(project)

    assert len(analysis_model.nodes) == 20
    assert len(analysis_model.surface_elements) == 12


def test_plate_mesh_preserves_user_corner_nodes() -> None:
    project = _plate_project(mesh_nx=4, mesh_ny=3)

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)

    assert mesh.node_tags[(0, 0)] == 1
    assert mesh.node_tags[(4, 0)] == 2
    assert mesh.node_tags[(4, 3)] == 3
    assert mesh.node_tags[(0, 3)] == 4
    assert analysis_model.nodes[mesh.node_tags[(4, 3)]].x == pytest.approx(5.0)
    assert analysis_model.nodes[mesh.node_tags[(4, 3)]].y == pytest.approx(4.0)


def test_plate_mesh_element_node_order_is_counterclockwise_grid_order() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)
    first_surface = analysis_model.surface_elements[mesh.surface_tags[0]]

    assert first_surface.node_tags == (
        mesh.node_tags[(0, 0)],
        mesh.node_tags[(1, 0)],
        mesh.node_tags[(1, 1)],
        mesh.node_tags[(0, 1)],
    )


def test_build_analysis_model_does_not_pollute_user_project() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)

    analysis_model = build_analysis_model(project)

    assert len(project.nodes) == 4
    assert len(project.surface_elements) == 0
    assert len(analysis_model.nodes) == 9
    assert len(analysis_model.surface_elements) == 4


def test_auto_mesh_uses_eight_divisions_for_thin_dkgq_plate() -> None:
    project = ProjectModel(name="Auto DKGQ")
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle mince",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellDKGQ"},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 5.0, 0.0)
    project.add_node(0.0, 5.0, 0.0)
    plate = project.add_plate_region((1, 2, 3, 4), section.tag)

    assert plate.mesh_mode == "auto"
    assert effective_plate_mesh_divisions(project, plate) == (8, 8)
    assert len(build_analysis_model(project).surface_elements) == 64


def test_auto_mesh_refines_thin_mitc4_plate() -> None:
    project = ProjectModel(name="Auto MITC4")
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle mince",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 5.0, 0.0)
    project.add_node(0.0, 5.0, 0.0)
    plate = project.add_plate_region((1, 2, 3, 4), section.tag)

    assert plate.mesh_mode == "auto"
    assert effective_plate_mesh_divisions(project, plate) == (16, 16)
    assert len(build_analysis_model(project).surface_elements) == 256


def test_user_mesh_mode_preserves_requested_divisions() -> None:
    project = _plate_project(mesh_nx=3, mesh_ny=2)
    plate = project.plate_regions[1]

    assert plate.mesh_mode == "user"
    assert effective_plate_mesh_divisions(project, plate) == (3, 2)
    assert len(build_analysis_model(project).surface_elements) == 6


def test_plate_surface_load_is_expanded_to_generated_surfaces() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)
    project.loads[1] = LoadData(tag=1, name="Surface", load_type="live")
    project.plate_surface_loads.append(
        PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-2.5)
    )

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)
    plate_area = sum(
        surface_area_m2(analysis_model, analysis_model.surface_elements[tag])
        for tag in mesh.surface_tags
    )

    generated_loads = [
        load for load in analysis_model.surface_loads
        if load.surface_tag in mesh.surface_tags
    ]
    assert len(generated_loads) == 4
    assert all(load.qz == pytest.approx(-2.5) for load in generated_loads)
    assert plate_area == pytest.approx(20.0)
    assert sum(load.qz * surface_area_m2(
        analysis_model,
        analysis_model.surface_elements[load.surface_tag],
    ) for load in generated_loads) == pytest.approx(-50.0)


def test_plate_edge_support_is_propagated_to_all_generated_edge_nodes() -> None:
    project = _plate_project(mesh_nx=4, mesh_ny=3)
    fixities = (1, 1, 1, 0, 0, 0)
    project.plate_edge_supports.append(
        PlateEdgeSupportData(plate_tag=1, edge="12", fixities=fixities)
    )

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)
    edge_node_tags = [mesh.node_tags[(i, 0)] for i in range(5)]

    assert len(edge_node_tags) == 5
    assert all(analysis_model.nodes[tag].fixities == fixities for tag in edge_node_tags)
    assert all(project.nodes[tag].fixities == (0, 0, 0, 0, 0, 0) for tag in (1, 2))


def test_adjacent_plate_regions_share_generated_edge_nodes() -> None:
    project = ProjectModel(name="Adjacent plate mesher")
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(2.0, 0.0, 0.0)
    project.add_node(2.0, 2.0, 0.0)
    project.add_node(0.0, 2.0, 0.0)
    project.add_node(4.0, 0.0, 0.0)
    project.add_node(4.0, 2.0, 0.0)
    project.add_plate_region((1, 2, 3, 4), section.tag, mesh_nx=2, mesh_ny=2)
    project.add_plate_region((2, 5, 6, 3), section.tag, mesh_nx=2, mesh_ny=2)

    analysis_model = build_analysis_model(project)
    mesh_1 = _generated_mesh(analysis_model, plate_tag=1)
    mesh_2 = _generated_mesh(analysis_model, plate_tag=2)

    assert mesh_1.node_tags[(2, 1)] == mesh_2.node_tags[(0, 1)]
    assert len(analysis_model.nodes) == 15


def test_generated_plate_uses_surface_section_formulation_when_plate_is_stale() -> None:
    project = ProjectModel(name="Plate formulation sync")
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle DKGQ",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellDKGQ"},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(2.0, 0.0, 0.0)
    project.add_node(2.0, 2.0, 0.0)
    project.add_node(0.0, 2.0, 0.0)
    plate = project.add_plate_region(
        (1, 2, 3, 4),
        section.tag,
        mesh_nx=1,
        mesh_ny=1,
        formulation="ShellMITC4",
    )
    assert plate.formulation == "ShellMITC4"

    analysis_model = build_analysis_model(project)
    mesh = _generated_mesh(analysis_model)
    surface = analysis_model.surface_elements[mesh.surface_tags[0]]

    assert surface.formulation == "ShellDKGQ"
