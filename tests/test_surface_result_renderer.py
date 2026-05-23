from __future__ import annotations

import numpy as np
import pytest

from core.analysis import AnalysisRunner
from core.analysis_model_builder import build_analysis_model
from core.model_data import LoadData, NodalLoad, ProjectModel, SurfaceLoad
from core.results import SurfaceResult
from core.solvers import SolverEngine
from gui.widgets.surface_result_renderer import (
    build_surface_component_field,
    build_surface_result_figure,
    detect_plate_result_files,
    detect_surface_result_files,
    detect_surface_result_views,
    surface_result_file_for_surface,
    _refined_quads_to_tris,
)


def _make_surface_project() -> ProjectModel:
    project = ProjectModel(name="renderer-surfaces")
    project.add_material("Beton", "concrete", "C30/37")
    section = project.add_section(
        "Dalle",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )

    for y in (0.0, 1.0):
        for x in (0.0, 1.0, 2.0):
            project.add_node(x, y, 0.0)

    project.add_surface_element((1, 2, 5, 4), section_tag=section.tag)
    project.add_surface_element((2, 3, 6, 5), section_tag=section.tag)
    return project


def _make_warped_surface_project() -> ProjectModel:
    project = ProjectModel(name="renderer-warped-surface")
    project.add_material("Beton", "concrete", "C30/37")
    section = project.add_section(
        "Dalle inclinee",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    for point in (
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.4),
        (2.0, 1.5, 0.9),
        (0.0, 1.5, 0.2),
    ):
        project.add_node(*point)
    project.add_surface_element((1, 2, 3, 4), section_tag=section.tag)
    return project


def _make_macro_plate_project(mesh_nx: int = 2, mesh_ny: int = 2) -> ProjectModel:
    project = ProjectModel(name="macro-plate-renderer")
    project.add_material("Beton", "concrete", "C30/37")
    section = project.add_section(
        "Dalle macro",
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
        name="Dalle P1",
        mesh_nx=mesh_nx,
        mesh_ny=mesh_ny,
    )
    return project


def _make_square_plate_analysis_project(load_kind: str) -> ProjectModel:
    """Create square plate analysis project."""
    project = ProjectModel(name=f"square-plate-{load_kind}")

    for y in (0.0, 1.0, 2.0):
        for x in (0.0, 1.0, 2.0):
            is_boundary = x in (0.0, 2.0) or y in (0.0, 2.0)
            fixities = (1, 1, 1, 1, 1, 1) if is_boundary else (0, 0, 0, 0, 0, 0)
            project.add_node(x, y, 0.0, fixities=fixities)

    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_surface_element((1, 2, 5, 4), section_tag=section.tag)
    project.add_surface_element((2, 3, 6, 5), section_tag=section.tag)
    project.add_surface_element((4, 5, 8, 7), section_tag=section.tag)
    project.add_surface_element((5, 6, 9, 8), section_tag=section.tag)

    project.loads[1] = LoadData(tag=1, name=f"Charge {load_kind}", load_type="live")
    if load_kind == "point":
        project.nodal_loads.append(NodalLoad(load_tag=1, node_tag=5, fz=-10.0))
    elif load_kind == "surface":
        for surface_tag in project.surface_elements:
            project.surface_loads.append(
                SurfaceLoad(load_tag=1, surface_tag=surface_tag, qz=-5.0)
            )
    else:
        raise ValueError(f"Charge plaque inconnue : {load_kind}")
    return project


def _surface_result(tag: int, mxx: float) -> SurfaceResult:
    gp = tuple((0.0, 0.0, 0.0, mxx, 0.0, 0.0, 0.0, 0.0) for _ in range(4))
    return SurfaceResult(tag=tag, mxx=mxx, gauss_resultants=gp)


def test_detect_surface_result_files_groups_surfaces_by_plane() -> None:
    project = _make_surface_project()

    files = detect_surface_result_files(project)

    assert len(files) == 1
    assert files[0]["plane"] == "XY"
    assert files[0]["surface_tags"] == [1, 2]


def test_single_surface_result_file_projects_warped_plate_locally() -> None:
    project = _make_warped_surface_project()
    results = {"surface_results": {1: _surface_result(1, 12.0)}}

    assert detect_surface_result_files(project) == []

    file_info = surface_result_file_for_surface(project, 1)
    assert file_info is not None
    assert file_info["plane"] == "LOCAL"
    assert file_info["surface_tags"] == [1]

    field = build_surface_component_field(project, results, file_info, "Mxx")

    assert field is not None
    assert np.asarray(field["coords_2d"]).shape == (4, 2)
    assert np.asarray(field["quads"]).shape == (1, 4)

    pytest.importorskip("matplotlib")
    fig = build_surface_result_figure("Mxx", file_info, project, results)
    ax = fig.axes[0]

    assert ax.get_xlabel() == "u local (m)"
    assert ax.get_ylabel() == "v local (m)"
    assert "Plaque S1" in ax.get_title()


def test_detect_plate_result_files_groups_generated_plate_mesh() -> None:
    project = _make_macro_plate_project(mesh_nx=2, mesh_ny=2)
    analysis_project = build_analysis_model(project)
    mesh = getattr(analysis_project, "generated_plate_meshes")[1]
    raw_surface_results = {
        tag: _surface_result(tag, float(index))
        for index, tag in enumerate(mesh.surface_tags, start=1)
    }
    results = {
        "surface_results": {},
        "internal_results": {
            "surface_results": raw_surface_results,
        },
        "analysis_project": analysis_project,
    }

    files = detect_plate_result_files(analysis_project)

    assert len(files) == 1
    assert files[0]["generated_plate"] is True
    assert files[0]["plate_tag"] == 1
    assert files[0]["surface_tags"] == mesh.surface_tags
    assert detect_surface_result_views(analysis_project) == files

    field = build_surface_component_field(
        analysis_project,
        results,
        files[0],
        "Mxx",
    )
    assert field is not None
    assert np.asarray(field["coords_2d"]).shape == (9, 2)
    assert np.asarray(field["quads"]).shape == (4, 4)

    pytest.importorskip("matplotlib")
    fig = build_surface_result_figure("Mxx", files[0], analysis_project, results)
    ax = fig.axes[0]
    assert "Plaque P1" in ax.get_title()
    assert len(ax.collections) >= 1


def test_build_surface_component_field_averages_shared_nodes() -> None:
    project = _make_surface_project()
    results = {
        "surface_results": {
            1: _surface_result(1, 10.0),
            2: _surface_result(2, 20.0),
        },
    }
    file_info = detect_surface_result_files(project)[0]

    field = build_surface_component_field(project, results, file_info, "Mxx")

    assert field is not None
    node_tags = field["node_tags"]
    values = field["values"]
    lookup = {node_tag: values[idx] for idx, node_tag in enumerate(node_tags)}

    assert lookup[1] == 10.0
    assert lookup[4] == 10.0
    assert lookup[3] == 20.0
    assert lookup[6] == 20.0
    assert lookup[2] == 15.0
    assert lookup[5] == 15.0
    assert np.asarray(field["quads"]).shape == (2, 4)


def test_refined_quads_to_tris_adds_intermediate_points() -> None:
    coords = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [1.0, 1.0],
            [0.0, 1.0],
        ],
        dtype=float,
    )
    values = np.array([0.0, 1.0, 2.0, 1.0], dtype=float)
    quads = np.array([[0, 1, 2, 3]], dtype=int)

    tris, refined_coords, refined_values = _refined_quads_to_tris(
        quads,
        coords,
        values,
        subdivisions=4,
    )

    assert refined_coords.shape[0] > coords.shape[0]
    assert refined_values.shape[0] == refined_coords.shape[0]
    assert tris.shape == (32, 3)
    center_idx = np.argmin(np.linalg.norm(refined_coords - np.array([0.5, 0.5]), axis=1))
    assert refined_values[center_idx] == 1.0


def test_build_surface_result_figure_draws_isolines() -> None:
    pytest.importorskip("matplotlib")
    project = _make_surface_project()
    gp_left = tuple(
        (0.0, 0.0, 0.0, value, 0.0, 0.0, 0.0, 0.0)
        for value in (0.0, 0.8, 1.2, 0.2)
    )
    gp_right = tuple(
        (0.0, 0.0, 0.0, value, 0.0, 0.0, 0.0, 0.0)
        for value in (0.8, 2.0, 2.4, 1.2)
    )
    results = {
        "surface_results": {
            1: SurfaceResult(tag=1, gauss_resultants=gp_left),
            2: SurfaceResult(tag=2, gauss_resultants=gp_right),
        },
    }
    file_info = detect_surface_result_files(project)[0]

    fig = build_surface_result_figure("Mxx", file_info, project, results)
    ax = fig.axes[0]

    assert len(ax.texts) > 0
    assert len(ax.collections) >= 2


def _first_varying_surface_component(
    project: ProjectModel,
    results: dict,
    file_info: dict,
) -> tuple[str, dict[str, object]]:
    for component in ("Mxx", "Myy", "Mxy", "Qx", "Qy", "Nxx", "Nyy", "Nxy"):
        field = build_surface_component_field(project, results, file_info, component)
        if field is None:
            continue
        values = np.asarray(field["values"], dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size and float(np.ptp(finite)) > 1e-10:
            return component, field
    raise AssertionError("Aucune composante plaque variable a rendre.")


@pytest.mark.parametrize(
    ("load_kind", "expected_reaction_fz"),
    [
        ("point", 10.0),
        ("surface", 20.0),
    ],
)
def test_square_plate_result_to_diagram_render_pipeline(
    load_kind: str,
    expected_reaction_fz: float,
) -> None:
    pytest.importorskip("openseespy.opensees")
    project = _make_square_plate_analysis_project(load_kind)

    success, results = AnalysisRunner(
        project,
        engine=SolverEngine.OPENSEES,
    ).run_static(load_tag=1)

    assert success is True
    assert results["result_context"]["surface_results_available"] is True
    total_fz = sum(result.fz_reaction for result in results["reactions"].values())
    assert total_fz == pytest.approx(expected_reaction_fz, abs=0.05)

    files = detect_surface_result_files(project)
    assert len(files) == 1
    assert files[0]["plane"] == "XY"
    assert files[0]["surface_tags"] == [1, 2, 3, 4]

    component, field = _first_varying_surface_component(project, results, files[0])
    assert np.asarray(field["quads"]).shape == (4, 4)
    assert np.all(np.isfinite(np.asarray(field["values"], dtype=float)))

    fig = build_surface_result_figure(component, files[0], project, results)
    ax = fig.axes[0]

    assert ax.get_xlabel() == "X (m)"
    assert ax.get_ylabel() == "Y (m)"
    assert files[0]["label"] in ax.get_title()
    assert len(ax.collections) >= 2
