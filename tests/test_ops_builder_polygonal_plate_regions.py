from __future__ import annotations

import math

import pytest

pytest.importorskip("cytriangle")

import core.ops_builder as ops_builder_module
from core.analysis import AnalysisRunner
from core.analysis_model_builder import build_analysis_model
from core.material_properties import material_elastic_modulus, material_poisson_ratio
from core.model_data import (
    LoadData,
    PlateEdgeSupportData,
    PlateSurfaceLoadData,
    ProjectModel,
)
from core.ops_builder import OpsBuilder


class _OpsRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name: str):
        def _record(*args):
            self.calls.append((name, args))

        return _record

    def calls_for(self, name: str) -> list[tuple]:
        return [args for call_name, args in self.calls if call_name == name]


def _polygonal_plate_project(*, divisions: int = 5) -> ProjectModel:
    project = ProjectModel(name="Polygonal plate OpenSees")
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    for point in (
        (0.0, 0.0, 0.0),
        (4.0, 0.0, 0.0),
        (4.0, 3.0, 0.0),
        (2.0, 1.5, 0.0),
        (0.0, 3.0, 0.0),
    ):
        project.add_node(*point)
    project.add_plate_region(
        (1, 2, 3, 4, 5),
        section_tag=section.tag,
        mesh_nx=divisions,
        mesh_ny=divisions,
    )
    return project


def test_polygonal_analysis_mesh_propagates_load_and_edge_support() -> None:
    project = _polygonal_plate_project(divisions=4)
    project.loads[1] = LoadData(tag=1, name="Surface", load_type="live")
    project.plate_surface_loads.append(
        PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-2.0)
    )
    fixities = (1, 1, 1, 0, 0, 0)
    project.plate_edge_supports.append(
        PlateEdgeSupportData(plate_tag=1, edge="12", fixities=fixities)
    )

    analysis_model = build_analysis_model(project)
    mesh = analysis_model.generated_plate_meshes[1]

    assert mesh.mesh_kind == "constrained_triangular"
    assert all(
        analysis_model.surface_elements[tag].formulation == "ASDShellT3"
        for tag in mesh.surface_tags
    )
    propagated = [
        load
        for load in analysis_model.surface_loads
        if load.load_tag == 1 and load.surface_tag in mesh.surface_tags
    ]
    assert len(propagated) == len(mesh.surface_tags)
    assert all(load.qz == pytest.approx(-2.0) for load in propagated)
    assert all(
        analysis_model.nodes[tag].fixities == fixities
        for tag in mesh.boundary_node_tags["12"]
    )
    assert project.surface_elements == {}


def test_concave_four_node_region_uses_triangular_mesher() -> None:
    project = ProjectModel(name="Concave quadrilateral")
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    for point in (
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (0.8, 0.7, 0.0),
        (0.0, 2.0, 0.0),
    ):
        project.add_node(*point)
    project.add_plate_region((1, 2, 3, 4), section_tag=section.tag, mesh_nx=4, mesh_ny=4)

    analysis_model = build_analysis_model(project)

    assert analysis_model.generated_plate_meshes[1].mesh_kind == "constrained_triangular"


def test_ops_builder_uses_shared_local_axis_and_full_integration(monkeypatch) -> None:
    analysis_model = build_analysis_model(_polygonal_plate_project(divisions=4))
    mesh = analysis_model.generated_plate_meshes[1]
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    OpsBuilder(analysis_model).build()

    shell_calls = [
        args for args in recorder.calls_for("element") if args[0] == "ASDShellT3"
    ]
    assert len(shell_calls) == len(mesh.surface_tags)
    assert mesh.local_x_axis is not None
    for args in shell_calls:
        assert args[6] == "-local"
        assert args[7:10] == pytest.approx(mesh.local_x_axis)
        assert "-corotational" not in args
        assert "-reducedIntegration" not in args


def test_opensees_polygonal_plate_reaction_balance_if_available() -> None:
    pytest.importorskip("openseespy.opensees")
    project = _polygonal_plate_project(divisions=6)
    project.loads[1] = LoadData(tag=1, name="Surface", load_type="live")
    project.plate_surface_loads.append(
        PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-2.0)
    )
    fixed = (1, 1, 1, 1, 1, 1)
    for edge in ("12", "23", "34", "45", "51"):
        project.plate_edge_supports.append(
            PlateEdgeSupportData(plate_tag=1, edge=edge, fixities=fixed)
        )

    success, results = AnalysisRunner(project, engine="opensees").run_static(load_tag=1)

    assert success is True, results
    plate_result = results["plate_results"][1]
    assert math.isclose(plate_result.fz_reaction_total, 18.0, rel_tol=1e-6, abs_tol=1e-6)
    assert plate_result.resultants_available is False
    assert results["result_context"]["surface_results_available"] is False
    assert results["result_context"]["plate_resultants_available"] is False
    assert results["result_context"]["generated_plate_count"] == 1
    assert results["result_context"]["generated_plate_mesh_sizes"] == {1: (0, 0)}


def test_opensees_polygonal_simply_supported_square_matches_reference() -> None:
    pytest.importorskip("openseespy.opensees")
    project = ProjectModel(name="Polygonal simply supported square")
    material = project.add_material("Beton C30", "concrete", "C30/37")
    thickness = 0.10
    section = project.add_section(
        "Dalle 10 cm",
        "surface",
        material_tag=material.tag,
        properties={"thickness": thickness, "element_formulation": "ShellMITC4"},
    )
    side = 2.0
    for point in (
        (0.0, 0.0, 0.0),
        (side / 2.0, 0.0, 0.0),
        (side, 0.0, 0.0),
        (side, side, 0.0),
        (0.0, side, 0.0),
    ):
        project.add_node(*point)
    project.nodes[1].fixities = (1, 1, 1, 0, 0, 0)
    project.nodes[3].fixities = (0, 1, 1, 0, 0, 0)
    project.add_plate_region(
        (1, 2, 3, 4, 5),
        section_tag=section.tag,
        mesh_nx=12,
        mesh_ny=12,
    )
    project.loads[1] = LoadData(tag=1, name="Surface", load_type="live")
    pressure = 1.0
    project.plate_surface_loads.append(
        PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-pressure)
    )
    vertical_support = (0, 0, 1, 0, 0, 0)
    for edge in ("12", "23", "34", "45", "51"):
        project.plate_edge_supports.append(
            PlateEdgeSupportData(
                plate_tag=1,
                edge=edge,
                fixities=vertical_support,
            )
        )

    success, results = AnalysisRunner(project, engine="opensees").run_static(load_tag=1)

    assert success is True, results
    e_modulus = material_elastic_modulus(material)
    poisson = material_poisson_ratio(material)
    rigidity = e_modulus * thickness**3 / (12.0 * (1.0 - poisson**2))
    reference_deflection = 0.00406235 * pressure * side**4 / rigidity
    computed_deflection = abs(results["plate_results"][1].uz_min)
    assert computed_deflection == pytest.approx(reference_deflection, rel=0.15)
