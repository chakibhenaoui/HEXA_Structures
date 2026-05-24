from __future__ import annotations

import pytest

from core.analysis_model_builder import build_analysis_model
from core.model_data import ElementLoad, LoadData, ProjectModel
from core.result_mapping import map_analysis_results_to_user_results
from core.results import ElementResult


def _plate_bar_project() -> ProjectModel:
    project = ProjectModel(name="Plate bar analysis mesh")
    material = project.add_material("Beton C30", "concrete", "C30/37")
    surface_section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=material.tag,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    bar_section = project.add_section(
        "Poutre",
        "rectangular",
        material_tag=material.tag,
        properties={"b": 0.30, "h": 0.50},
        area=0.15,
        inertia_y=0.003125,
        inertia_z=0.001125,
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 5.0, 0.0)
    project.add_node(0.0, 5.0, 0.0)
    project.add_plate_region(
        (1, 2, 3, 4),
        section_tag=surface_section.tag,
        mesh_nx=4,
        mesh_ny=4,
    )
    project.add_node(1.25, 2.5, 0.0)
    project.add_node(3.75, 2.5, 0.0)
    project.add_element(5, 6, section_tag=bar_section.tag, element_type="beam")
    return project


def _node_xyz(project: ProjectModel, tag: int) -> tuple[float, float, float]:
    node = project.nodes[int(tag)]
    return float(node.x), float(node.y), float(node.z)


def _bar_mesh_points(project: ProjectModel, node_tags: tuple[int, ...]) -> list[tuple[float, float, float]]:
    return [_node_xyz(project, tag) for tag in node_tags]


def _has_approx(values: tuple[float, ...], target: float) -> bool:
    return any(value == pytest.approx(target) for value in values)


def test_aligned_coplanar_bar_is_split_only_in_analysis_model() -> None:
    project = _plate_bar_project()

    analysis_model = build_analysis_model(project)
    generated_bar_meshes = getattr(analysis_model, "generated_bar_meshes")
    bar_mesh = generated_bar_meshes[1]

    assert set(project.elements) == {1}
    assert 1 not in analysis_model.elements
    assert bar_mesh.source_element_tag == 1
    assert len(bar_mesh.segment_tags) == 2
    assert len(bar_mesh.node_tags) == 3
    assert _node_xyz(analysis_model, bar_mesh.node_tags[0]) == pytest.approx((1.25, 2.5, 0.0))
    assert _node_xyz(analysis_model, bar_mesh.node_tags[1]) == pytest.approx((2.5, 2.5, 0.0))
    assert _node_xyz(analysis_model, bar_mesh.node_tags[2]) == pytest.approx((3.75, 2.5, 0.0))
    assert [analysis_model.elements[tag].node_i for tag in bar_mesh.segment_tags] == [
        bar_mesh.node_tags[0],
        bar_mesh.node_tags[1],
    ]
    assert [analysis_model.elements[tag].node_j for tag in bar_mesh.segment_tags] == [
        bar_mesh.node_tags[1],
        bar_mesh.node_tags[2],
    ]


def test_coplanar_edge_bar_is_split_on_plate_edge_mesh_nodes() -> None:
    project = _plate_bar_project()
    project.elements.clear()
    project.add_element(1, 2, section_tag=2, element_type="beam")

    analysis_model = build_analysis_model(project)
    bar_mesh = getattr(analysis_model, "generated_bar_meshes")[1]

    assert set(project.elements) == {1}
    assert 1 not in analysis_model.elements
    assert len(bar_mesh.segment_tags) == 4
    assert _bar_mesh_points(analysis_model, bar_mesh.node_tags) == pytest.approx(
        [
            (0.0, 0.0, 0.0),
            (1.25, 0.0, 0.0),
            (2.5, 0.0, 0.0),
            (3.75, 0.0, 0.0),
            (5.0, 0.0, 0.0),
        ]
    )


def test_coplanar_bar_crossing_plate_edges_forces_line_and_is_split_in_analysis_model() -> None:
    project = _plate_bar_project()
    plate = project.plate_regions[1]
    plate.mesh_nx = 4
    plate.mesh_ny = 3
    project.nodes[5].x = -1.0
    project.nodes[5].y = 2.5
    project.nodes[6].x = 6.0
    project.nodes[6].y = 2.5

    analysis_model = build_analysis_model(project)
    plate_mesh = getattr(analysis_model, "generated_plate_meshes")[1]
    bar_mesh = getattr(analysis_model, "generated_bar_meshes")[1]

    assert _has_approx(plate_mesh.v_values, 0.5)
    assert set(project.elements) == {1}
    assert 1 not in analysis_model.elements
    assert _bar_mesh_points(analysis_model, bar_mesh.node_tags) == pytest.approx(
        [
            (-1.0, 2.5, 0.0),
            (0.0, 2.5, 0.0),
            (1.25, 2.5, 0.0),
            (2.5, 2.5, 0.0),
            (3.75, 2.5, 0.0),
            (5.0, 2.5, 0.0),
            (6.0, 2.5, 0.0),
        ]
    )


def test_continuous_coplanar_bar_across_adjacent_plate_regions_is_split_once() -> None:
    project = ProjectModel(name="Adjacent plates")
    material = project.add_material("Beton C30", "concrete", "C30/37")
    surface_section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=material.tag,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    bar_section = project.add_section(
        "Poutre",
        "rectangular",
        material_tag=material.tag,
        properties={"b": 0.30, "h": 0.50},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 5.0, 0.0)
    project.add_node(0.0, 5.0, 0.0)
    project.add_node(10.0, 0.0, 0.0)
    project.add_node(10.0, 5.0, 0.0)
    project.add_plate_region(
        (1, 2, 3, 4),
        section_tag=surface_section.tag,
        mesh_nx=2,
        mesh_ny=3,
    )
    project.add_plate_region(
        (2, 5, 6, 3),
        section_tag=surface_section.tag,
        mesh_nx=2,
        mesh_ny=3,
    )
    project.add_node(0.0, 2.5, 0.0)
    project.add_node(10.0, 2.5, 0.0)
    project.add_element(7, 8, section_tag=bar_section.tag, element_type="beam")

    analysis_model = build_analysis_model(project)
    generated_plate_meshes = getattr(analysis_model, "generated_plate_meshes")
    bar_mesh = getattr(analysis_model, "generated_bar_meshes")[1]

    assert _has_approx(generated_plate_meshes[1].v_values, 0.5)
    assert _has_approx(generated_plate_meshes[2].v_values, 0.5)
    assert len(bar_mesh.segment_tags) == 4
    assert _bar_mesh_points(analysis_model, bar_mesh.node_tags) == pytest.approx(
        [
            (0.0, 2.5, 0.0),
            (2.5, 2.5, 0.0),
            (5.0, 2.5, 0.0),
            (7.5, 2.5, 0.0),
            (10.0, 2.5, 0.0),
        ]
    )
    assert len([tag for tag, node in analysis_model.nodes.items() if node.x == 5.0 and node.y == 2.5]) == 1


def test_aligned_coplanar_bar_load_is_copied_to_generated_segments() -> None:
    project = _plate_bar_project()
    project.loads[1] = LoadData(tag=1, name="Q", load_type="live")
    project.element_loads.append(
        ElementLoad(load_tag=1, element_tag=1, wy=-4.0, coordinate_system="local")
    )

    analysis_model = build_analysis_model(project)
    bar_mesh = getattr(analysis_model, "generated_bar_meshes")[1]
    segment_loads = [
        load
        for load in analysis_model.element_loads
        if int(load.element_tag) in set(bar_mesh.segment_tags)
    ]

    assert not any(int(load.element_tag) == 1 for load in analysis_model.element_loads)
    assert len(segment_loads) == 2
    assert all(load.load_tag == 1 for load in segment_loads)
    assert all(load.wy == pytest.approx(-4.0) for load in segment_loads)
    assert all(load.coordinate_system == "local" for load in segment_loads)


def test_diagonal_coplanar_bar_is_not_split_in_analysis_model() -> None:
    project = _plate_bar_project()
    project.elements.clear()
    project.nodes[5].x = 1.0
    project.nodes[5].y = 1.0
    project.nodes[6].x = 4.0
    project.nodes[6].y = 4.0
    project.add_element(5, 6, section_tag=2, element_type="beam")

    analysis_model = build_analysis_model(project)

    assert set(analysis_model.elements) == {1}
    assert getattr(analysis_model, "generated_bar_meshes") == {}


def test_generated_bar_segment_results_map_back_to_user_bar() -> None:
    project = _plate_bar_project()
    analysis_model = build_analysis_model(project)
    bar_mesh = getattr(analysis_model, "generated_bar_meshes")[1]
    raw_results = {
        "displacements": {},
        "reactions": {},
        "surface_results": {},
        "element_forces": {
            bar_mesh.segment_tags[0]: ElementResult(
                tag=bar_mesh.segment_tags[0],
                n_i=1.0,
                n_j=2.0,
                vy_i=-3.0,
                vy_j=4.0,
                my_i=-5.0,
                my_j=6.0,
            ),
            bar_mesh.segment_tags[1]: ElementResult(
                tag=bar_mesh.segment_tags[1],
                n_i=-7.0,
                n_j=8.0,
                vy_i=-9.0,
                vy_j=10.0,
                my_i=-11.0,
                my_j=12.0,
            ),
        },
        "result_context": {},
    }

    mapped = map_analysis_results_to_user_results(
        user_project=project,
        analysis_project=analysis_model,
        raw_results=raw_results,
        generated_plate_meshes=getattr(analysis_model, "generated_plate_meshes"),
    )

    assert set(mapped["element_forces"]) == {1}
    result = mapped["element_forces"][1]
    assert result.tag == 1
    assert result.n_i == pytest.approx(-7.0)
    assert result.n_j == pytest.approx(8.0)
    assert result.vy_i == pytest.approx(-9.0)
    assert result.vy_j == pytest.approx(10.0)
    assert result.my_i == pytest.approx(-11.0)
    assert result.my_j == pytest.approx(12.0)
    assert mapped["result_context"]["generated_bar_count"] == 1
    assert mapped["result_context"]["generated_bar_segment_count"] == 2
