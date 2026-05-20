from __future__ import annotations

import pytest

import core.ops_builder as ops_builder_module
from core.analysis_model_builder import build_analysis_model
from core.model_data import LoadData, PlateSurfaceLoadData, ProjectModel
from core.ops_builder import OpsBuilder
from core.solvers.opensees_backend import OpenSeesBackend


class _OpsRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name: str):
        def _record(*args):
            self.calls.append((name, args))

        return _record

    def calls_for(self, name: str) -> list[tuple]:
        return [args for call_name, args in self.calls if call_name == name]


def _plate_project(mesh_nx: int = 8, mesh_ny: int = 8) -> ProjectModel:
    project = ProjectModel(name="Plate region OpenSees")
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


def test_analysis_model_feeds_generated_shellmitc4_elements(monkeypatch) -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)
    analysis_model = build_analysis_model(project)
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    OpsBuilder(analysis_model).build()

    section_calls = recorder.calls_for("section")
    shell_calls = [
        args for args in recorder.calls_for("element")
        if args[0] == "ShellMITC4"
    ]
    assert any(args[0] == "ElasticMembranePlateSection" for args in section_calls)
    assert len(shell_calls) == 4
    assert len(project.surface_elements) == 0


def test_plate_surface_loads_are_applied_to_generated_mesh_nodes(monkeypatch) -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)
    project.loads[1] = LoadData(tag=1, name="Surface", load_type="live")
    project.plate_surface_loads.append(
        PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-2.0)
    )
    analysis_model = build_analysis_model(project)
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    builder = OpsBuilder(analysis_model)
    builder.build()
    builder.apply_loads(1)

    load_calls = recorder.calls_for("load")
    assert len(load_calls) == 9
    assert sum(args[3] for args in load_calls) == pytest.approx(-40.0)


def test_default_plate_region_uses_regular_8x8_mesh() -> None:
    project = _plate_project()

    analysis_model = build_analysis_model(project)

    assert len(analysis_model.nodes) == 81
    assert len(analysis_model.surface_elements) == 64


def test_opensees_backend_prepares_enriched_analysis_model() -> None:
    project = _plate_project()
    backend = OpenSeesBackend(project)

    backend._prepare_analysis_model()

    assert len(project.nodes) == 4
    assert len(project.surface_elements) == 0
    assert len(backend.analysis_project.nodes) == 81
    assert len(backend.analysis_project.surface_elements) == 64
    assert backend.builder.project is backend.analysis_project
    assert set(backend.generated_plate_meshes) == {1}


def test_opensees_backend_attaches_analysis_model_to_results() -> None:
    project = _plate_project(mesh_nx=2, mesh_ny=2)
    backend = OpenSeesBackend(project)
    backend._prepare_analysis_model()
    results = {"result_context": {}}

    backend._attach_analysis_context(results)

    assert results["analysis_project"] is backend.analysis_project
    assert set(results["generated_plate_meshes"]) == {1}
    assert results["result_context"]["user_node_count"] == 4
    assert results["result_context"]["analysis_node_count"] == 9
    assert results["result_context"]["user_surface_count"] == 0
    assert results["result_context"]["analysis_surface_count"] == 4
    assert results["result_context"]["plate_region_count"] == 1
    assert results["result_context"]["generated_plate_surface_count"] == 4
    assert results["result_context"]["generated_plate_node_count"] == 9


def test_plate_region_8x8_pipeline_diagnostics_use_generated_mesh() -> None:
    project = _plate_project()
    backend = OpenSeesBackend(project)
    backend._prepare_analysis_model()
    results = {"result_context": {}}

    backend._attach_analysis_context(results)

    context = results["result_context"]
    assert context["user_node_count"] == 4
    assert context["analysis_node_count"] == 81
    assert context["user_surface_count"] == 0
    assert context["analysis_surface_count"] == 64
    assert context["plate_region_count"] == 1
    assert context["generated_plate_surface_count"] == 64
    assert context["generated_plate_node_count"] == 81


def test_explicit_1x1_plate_region_keeps_single_element_mesh() -> None:
    project = _plate_project(mesh_nx=1, mesh_ny=1)

    analysis_model = build_analysis_model(project)

    assert len(analysis_model.nodes) == 4
    assert len(analysis_model.surface_elements) == 1
