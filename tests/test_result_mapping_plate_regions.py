from __future__ import annotations

import pytest

from core.analysis_model_builder import build_analysis_model
from core.model_data import (
    PlateEdgeSupportData,
    ProjectModel,
)
from core.result_mapping import map_analysis_results_to_user_results
from core.results import ElementResult, NodalResult, SurfaceResult


def _plate_project(mesh_nx: int = 2, mesh_ny: int = 2) -> ProjectModel:
    project = ProjectModel(name="Plate result mapping")
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
    project.add_plate_region(
        (1, 2, 3, 4),
        section_tag=section.tag,
        name="P1",
        mesh_nx=mesh_nx,
        mesh_ny=mesh_ny,
    )
    return project


def _surface_result(tag: int, base: float) -> SurfaceResult:
    return SurfaceResult(
        tag=tag,
        mxx=base,
        myy=base + 10.0,
        mxy=-base,
        qx=base * 2.0,
        qy=-base * 2.0,
    )


def _raw_results_for_plate(analysis_model: ProjectModel) -> dict:
    mesh = getattr(analysis_model, "generated_plate_meshes")[1]
    return {
        "displacements": {
            tag: NodalResult(tag=tag, uz=float(tag) * -0.001)
            for tag in analysis_model.nodes
        },
        "reactions": {
            tag: NodalResult(tag=tag, fz_reaction=float(tag))
            for tag in analysis_model.nodes
        },
        "element_forces": {},
        "surface_results": {
            surface_tag: _surface_result(surface_tag, float(index))
            for index, surface_tag in enumerate(mesh.surface_tags, start=1)
        },
        "result_context": {},
    }


def _map_plate_project(project: ProjectModel) -> tuple[ProjectModel, dict]:
    analysis_model = build_analysis_model(project)
    raw_results = _raw_results_for_plate(analysis_model)
    mapped = map_analysis_results_to_user_results(
        user_project=project,
        analysis_project=analysis_model,
        raw_results=raw_results,
        generated_plate_meshes=getattr(analysis_model, "generated_plate_meshes"),
    )
    return analysis_model, mapped


def test_generated_nodes_are_hidden_from_user_displacements() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)

    analysis_model, mapped = _map_plate_project(project)

    assert len(analysis_model.nodes) == 9
    assert set(mapped["displacements"]) == {1, 2, 3, 4}
    assert mapped["internal_results"]["generated_node_count"] == 5


def test_generated_surfaces_are_aggregated_into_plate_result() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)

    _analysis_model, mapped = _map_plate_project(project)
    result = mapped["plate_results"][1]

    assert mapped["surface_results"] == {}
    assert result.mxx_min == pytest.approx(1.0)
    assert result.mxx_max == pytest.approx(4.0)
    assert result.myy_min == pytest.approx(11.0)
    assert result.myy_max == pytest.approx(14.0)
    assert result.mxy_min == pytest.approx(-4.0)
    assert result.mxy_max == pytest.approx(-1.0)
    assert result.qx_min == pytest.approx(2.0)
    assert result.qx_max == pytest.approx(8.0)
    assert result.qy_min == pytest.approx(-8.0)
    assert result.qy_max == pytest.approx(-2.0)
    assert len(result.surface_tags) == 4


def test_plate_result_extremes_use_nodal_extrapolation_not_surface_averages() -> None:
    project = _plate_project(mesh_nx=1, mesh_ny=1)
    analysis_model = build_analysis_model(project)
    mesh = getattr(analysis_model, "generated_plate_meshes")[1]
    xep = 0.8660254037844386
    raw_results = {
        "displacements": {},
        "reactions": {},
        "element_forces": {},
        "surface_results": {
            mesh.surface_tags[0]: SurfaceResult(
                tag=mesh.surface_tags[0],
                mxx=0.0,
                myy=0.0,
                mxy=0.0,
                qx=0.0,
                qy=0.0,
                gauss_resultants=(
                    (0.0, 0.0, 0.0, 0.0, 1.0, -1.0, 2.0, -2.0),
                    (0.0, 0.0, 0.0, 0.0, 2.0, -2.0, 4.0, -4.0),
                    (0.0, 0.0, 0.0, 10.0, 3.0, -3.0, 6.0, -6.0),
                    (0.0, 0.0, 0.0, 0.0, 4.0, -4.0, 8.0, -8.0),
                ),
            )
        },
    }

    mapped = map_analysis_results_to_user_results(
        user_project=project,
        analysis_project=analysis_model,
        raw_results=raw_results,
        generated_plate_meshes=getattr(analysis_model, "generated_plate_meshes"),
    )
    result = mapped["plate_results"][1]

    assert result.mxx_min == pytest.approx(-5.0)
    assert result.mxx_max == pytest.approx(10.0 * (1.0 + xep))
    assert result.myy_min == pytest.approx(-0.7320508075688772)
    assert result.myy_max == pytest.approx(5.732050807568877)
    assert result.mxy_min == pytest.approx(-5.732050807568877)
    assert result.mxy_max == pytest.approx(0.7320508075688772)
    assert result.qx_min == pytest.approx(-1.4641016151377544)
    assert result.qx_max == pytest.approx(11.464101615137753)
    assert result.qy_min == pytest.approx(-11.464101615137753)
    assert result.qy_max == pytest.approx(1.4641016151377544)


def test_plate_total_reaction_counts_each_generated_node_once() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)

    analysis_model, mapped = _map_plate_project(project)
    unique_nodes = set(getattr(analysis_model, "generated_plate_meshes")[1].node_tags.values())
    expected = sum(float(tag) for tag in unique_nodes)

    assert mapped["plate_results"][1].fz_reaction_total == pytest.approx(expected)


def test_plate_edge_reaction_sums_supported_edge_nodes() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)
    project.plate_edge_supports.append(
        PlateEdgeSupportData(
            plate_tag=1,
            edge="12",
            fixities=(1, 1, 1, 0, 0, 0),
        )
    )

    analysis_model, mapped = _map_plate_project(project)
    mesh = getattr(analysis_model, "generated_plate_meshes")[1]
    edge_nodes = [mesh.node_tags[(i, 0)] for i in range(3)]

    edge_result = mapped["plate_edge_reactions"][1]["12"]
    assert edge_result.node_tags == tuple(sorted(edge_nodes))
    assert edge_result.fz == pytest.approx(sum(float(tag) for tag in edge_nodes))


def test_mapping_without_plate_keeps_legacy_results_unchanged() -> None:
    project = ProjectModel(name="No plate")
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(1.0, 0.0, 0.0)
    project.add_material("Steel", "steel", "S235")
    project.add_section("Bar", "rectangular", 1, properties={"b": 0.2, "h": 0.2})
    project.add_element(1, 2, section_tag=1)
    raw_results = {
        "displacements": {1: NodalResult(tag=1), 2: NodalResult(tag=2)},
        "reactions": {1: NodalResult(tag=1, fz_reaction=5.0)},
        "element_forces": {1: ElementResult(tag=1, n_i=1.0, n_j=-1.0)},
        "surface_results": {},
        "result_context": {},
    }

    mapped = map_analysis_results_to_user_results(
        user_project=project,
        analysis_project=project,
        raw_results=raw_results,
        generated_plate_meshes={},
    )

    assert mapped["displacements"] == raw_results["displacements"]
    assert mapped["reactions"] == raw_results["reactions"]
    assert mapped["element_forces"] == raw_results["element_forces"]
    assert mapped["plate_results"] == {}


def test_mapping_result_context_contains_plate_diagnostics() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)

    analysis_model, mapped = _map_plate_project(project)
    context = mapped["result_context"]

    assert context["visible_node_count"] == 4
    assert context["analysis_node_count"] == len(analysis_model.nodes)
    assert context["generated_plate_count"] == 1
    assert context["generated_plate_surface_count"] == 4
    assert context["generated_plate_node_count"] == 9
    assert context["plate_region_count"] == 1
