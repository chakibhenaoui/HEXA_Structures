from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.application import ApplicationServices
from core.application.connection_design import (
    CONNECTION_DESIGN_EXTENSION_POINT,
    ConnectionDesignRequest,
    ConnectionDesignResult,
)
from core.application.results import AnalysisRunResult
from core.application.use_cases import (
    BuildAnalysisModel,
    RunConnectionDesign,
    RunAllStaticAnalyses,
    RunModalAnalysis,
    RunStaticAnalysis,
)
from core.adapters.solvers.registry import (
    get_solver_plugin_id_map,
    get_solver_plugin_map,
    get_solver_plugins,
)
from core.model_data import (
    LoadData,
    PlateEdgeSupportData,
    PlateSurfaceLoadData,
    ProjectModel,
)
from core.plate_mesher import GeneratedPlateMesh
from core.plugins import (
    ImportlibPluginLoader,
    ManifestOnlyPluginLoader,
    PluginDescriptor,
    PluginLoadResult,
    PluginManifest,
    PluginRegistry,
    build_manifest_registry,
    default_plugin_roots,
    discover_plugin_manifests,
)
from core.solvers import AnalysisFeature, SolverEngine, SolverManager


class FakeSolver:
    engine_name = "fake"
    supports_diagrams = False

    def __init__(self) -> None:
        self.static_call = None
        self.static_calls = []

    def run_static(
        self,
        load_tag: int | None = None,
        combo_tag: int | None = None,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> tuple[bool, dict]:
        self.static_call = {
            "load_tag": load_tag,
            "combo_tag": combo_tag,
            "max_iter": max_iter,
            "tol": tol,
        }
        self.static_calls.append(self.static_call)
        return True, {"engine": self.engine_name}

    def run_modal(self, num_modes: int = 10) -> tuple[bool, dict]:
        return True, {"num_modes": num_modes}

    def sample_diagram_component(
        self,
        element_tag: int,
        component: str,
        nep: int = 17,
    ) -> None:
        return None


class FakeSolverManager:
    def __init__(self) -> None:
        self.solver = FakeSolver()
        self.create_calls = []

    def create_backend(self, project, requested):
        self.create_calls.append((project, requested))
        return self.solver, SolverEngine.PYNITE

    def resolve_solver_id(self, requested) -> str:
        return "fake.solver"

    def detect_engines(self) -> list:
        return []

    def get_display_info(self) -> list:
        return [{"id": "fake.solver", "engine": "fake", "enabled": True}]

    def get_capabilities_for_solver(self, solver_id: str) -> dict:
        assert solver_id == "fake.solver"
        return {}


class FakePlateMesher:
    def __init__(self) -> None:
        self.calls = []

    def generate_plate_region_mesh(self, source_project, target_project, plate):
        self.calls.append((source_project, target_project, plate))
        surface = target_project.add_surface_element(
            plate.corner_node_tags,
            section_tag=plate.section_tag,
        )
        return GeneratedPlateMesh(
            plate_tag=plate.tag,
            node_tags={
                (0, 0): plate.corner_node_tags[0],
                (1, 0): plate.corner_node_tags[1],
                (1, 1): plate.corner_node_tags[2],
                (0, 1): plate.corner_node_tags[3],
            },
            surface_tags=[surface.tag],
            mesh_nx=1,
            mesh_ny=1,
        )


class FakeLoadablePluginLoader:
    def can_load(self, manifest: PluginManifest) -> bool:
        return manifest.plugin_id == "solver.external"

    def load(self, manifest: PluginManifest) -> PluginLoadResult:
        if not self.can_load(manifest):
            return PluginLoadResult.manifest_only(manifest, "not supported")
        return PluginLoadResult(
            plugin_id=manifest.plugin_id,
            kind=manifest.kind,
            load_state="loaded",
            loaded=True,
            plugin={"id": manifest.plugin_id},
        )


class FakeConnectionPlugin:
    plugin_id = "connections.fake"

    def __init__(self) -> None:
        self.requests = []

    def can_design_connection(self, request: ConnectionDesignRequest) -> bool:
        return request.connection_type == "end_plate"

    def design_connection(self, request: ConnectionDesignRequest) -> dict:
        self.requests.append(request)
        return {
            "success": True,
            "payload": {
                "connection_id": request.connection_id,
                "unity_ratio": 0.73,
            },
            "warnings": ["demo warning"],
        }


class FakeConnectionPluginLoader:
    def __init__(self, plugin=None) -> None:
        self.plugin = plugin or FakeConnectionPlugin()

    def can_load(self, manifest: PluginManifest) -> bool:
        return manifest.provides_extension(CONNECTION_DESIGN_EXTENSION_POINT)

    def load(self, manifest: PluginManifest) -> PluginLoadResult:
        if not self.can_load(manifest):
            return PluginLoadResult.manifest_only(manifest, "not a connection plugin")
        return PluginLoadResult(
            plugin_id=manifest.plugin_id,
            kind=manifest.kind,
            load_state="loaded",
            loaded=True,
            plugin=self.plugin,
        )


def _plate_project_for_architecture_tests() -> ProjectModel:
    project = ProjectModel(name="Architecture plate")
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(1.0, 0.0, 0.0)
    project.add_node(1.0, 1.0, 0.0)
    project.add_node(0.0, 1.0, 0.0)
    project.add_plate_region((1, 2, 3, 4), section_tag=section.tag)
    return project


def test_run_static_analysis_delegates_to_solver_port() -> None:
    solver = FakeSolver()

    success, results = RunStaticAnalysis(solver).execute(
        load_tag=1,
        combo_tag=None,
        max_iter=42,
        tol=1e-5,
    )

    assert success is True
    assert results == {"engine": "fake"}
    assert solver.static_call == {
        "load_tag": 1,
        "combo_tag": None,
        "max_iter": 42,
        "tol": 1e-5,
    }


def test_analysis_run_result_normalizes_legacy_solver_response() -> None:
    result = AnalysisRunResult.from_legacy(
        (False, {"error": "boom"}),
        analysis_type="static",
        solver_id="fake.solver",
    )

    assert result.success is False
    assert result.error == "boom"
    assert result.analysis_type == "static"
    assert result.solver_id == "fake.solver"
    assert result.as_legacy() == (False, {"error": "boom"})


def test_run_static_analysis_can_return_typed_result() -> None:
    result = RunStaticAnalysis(FakeSolver()).execute_result(
        load_tag=1,
        solver_id="fake.solver",
    )

    assert result.success is True
    assert result.payload == {"engine": "fake"}
    assert result.analysis_type == "static"
    assert result.solver_id == "fake.solver"


def test_run_modal_analysis_delegates_to_solver_port() -> None:
    success, results = RunModalAnalysis(FakeSolver()).execute(num_modes=3)

    assert success is True
    assert results == {"num_modes": 3}


def test_run_all_static_analyses_builds_load_and_combo_tasks() -> None:
    solver = FakeSolver()
    project = SimpleNamespace(
        loads={1: SimpleNamespace(name="G")},
        combinations={2: SimpleNamespace(name="ELU")},
    )
    progress = []

    results = RunAllStaticAnalyses(project, solver).execute(
        callback=lambda name, idx, total: progress.append((name, idx, total)),
    )

    assert list(results) == ["G (cas 1)", "ELU (combo 2)"]
    assert solver.static_calls == [
        {"load_tag": 1, "combo_tag": None, "max_iter": 100, "tol": 1e-6},
        {"load_tag": None, "combo_tag": 2, "max_iter": 100, "tol": 1e-6},
    ]
    assert progress == [("G (cas 1)", 0, 2), ("ELU (combo 2)", 1, 2)]


def test_run_all_static_analyses_can_return_typed_results() -> None:
    project = SimpleNamespace(
        loads={1: SimpleNamespace(name="G")},
        combinations={},
    )

    results = RunAllStaticAnalyses(project, FakeSolver()).execute_results(
        solver_id="fake.solver",
    )

    assert results["G (cas 1)"].analysis_type == "static"
    assert results["G (cas 1)"].solver_id == "fake.solver"
    assert results["G (cas 1)"].case_name == "G (cas 1)"


def test_build_analysis_model_uses_injected_mesh_generator() -> None:
    project = _plate_project_for_architecture_tests()
    project.loads[1] = LoadData(tag=1, name="Surface", load_type="live")
    project.plate_surface_loads.append(
        PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-2.0)
    )
    project.plate_edge_supports.append(
        PlateEdgeSupportData(
            plate_tag=1,
            edge="12",
            fixities=(1, 1, 1, 0, 0, 0),
        )
    )
    mesher = FakePlateMesher()

    analysis_model = BuildAnalysisModel(mesher).execute(project)

    assert len(mesher.calls) == 1
    assert len(project.surface_elements) == 0
    assert len(analysis_model.surface_elements) == 1
    assert analysis_model.generated_plate_meshes[1].surface_tags == [1]
    assert len(analysis_model.surface_loads) == 1
    assert analysis_model.surface_loads[0].surface_tag == 1
    assert analysis_model.nodes[1].fixities == (1, 1, 1, 0, 0, 0)
    assert analysis_model.nodes[2].fixities == (1, 1, 1, 0, 0, 0)


def test_application_services_wraps_solver_use_cases() -> None:
    project = SimpleNamespace(loads={}, combinations={})
    manager = FakeSolverManager()
    services = ApplicationServices(
        project,
        solver_request="fake.solver",
        solver_manager=manager,
    )

    success, results = services.run_static(load_tag=1)

    assert success is True
    assert results == {"engine": "fake"}
    assert services.solver_id == "fake.solver"
    assert services.engine == SolverEngine.PYNITE
    assert services.supports_diagrams is False
    assert manager.create_calls == [(project, "fake.solver")]


def test_application_services_exposes_typed_analysis_results() -> None:
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_request="fake.solver",
        solver_manager=FakeSolverManager(),
    )

    result = services.run_static_result(load_tag=1)

    assert result.success is True
    assert result.solver_id == "fake.solver"
    assert result.analysis_type == "static"
    assert services.run_modal_result(num_modes=2).analysis_type == "modal"


def test_application_services_exposes_solver_display_metadata() -> None:
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_roots=(),
    )

    assert services.get_solver_display_info() == [
        {"id": "fake.solver", "engine": "fake", "enabled": True}
    ]
    assert services.get_solver_capabilities("fake.solver") == {}


def test_application_services_appends_unloaded_solver_manifests_to_display(tmp_path) -> None:
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "solver.external",
                "name": "External Solver",
                "kind": "solver",
                "version": "0.2.0",
                "api_version": "1",
                "entry_point": "external_solver:get_plugin",
            }
        ),
        encoding="utf-8",
    )
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_roots=(tmp_path,),
    )

    rows = services.get_solver_display_info()

    assert rows[0] == {"id": "fake.solver", "engine": "fake", "enabled": True}
    assert rows[1]["id"] == "solver.external"
    assert rows[1]["text"] == "External Solver (installe, non charge)"
    assert rows[1]["enabled"] is False
    assert rows[1]["load_state"] == "manifest_only"
    assert "chargeur externe non disponible" in rows[1]["tooltip"]


def test_application_services_marks_manifest_loadable_when_loader_supports_it(tmp_path) -> None:
    (tmp_path / "plugin.json").write_text(
        json.dumps({"id": "solver.external", "name": "External", "kind": "solver"}),
        encoding="utf-8",
    )
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_roots=(tmp_path,),
        plugin_loader=FakeLoadablePluginLoader(),
    )

    rows = services.get_solver_display_info()

    assert rows[1]["id"] == "solver.external"
    assert rows[1]["enabled"] is False
    assert rows[1]["load_state"] == "loadable"
    assert "activation non connectee" in rows[1]["tooltip"]


def test_application_services_returns_plugin_load_status_from_loader(tmp_path) -> None:
    manifest = PluginManifest.from_mapping(
        {"id": "solver.external", "name": "External", "kind": "solver"}
    )
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_loader=FakeLoadablePluginLoader(),
    )

    result = services.get_plugin_load_status(manifest)

    assert result.loaded is True
    assert result.plugin == {"id": "solver.external"}
    assert result.load_state == "loaded"


def test_manifest_only_plugin_loader_never_loads_external_code() -> None:
    manifest = PluginManifest.from_mapping(
        {"id": "solver.external", "name": "External", "kind": "solver"}
    )
    loader = ManifestOnlyPluginLoader()

    result = loader.load(manifest)

    assert loader.can_load(manifest) is False
    assert result.loaded is False
    assert result.plugin is None
    assert result.load_state == "manifest_only"


def test_importlib_plugin_loader_loads_manifest_entry_point_from_plugin_folder(
    tmp_path,
) -> None:
    plugin_dir = tmp_path / "demo_solver"
    plugin_dir.mkdir()
    (plugin_dir / "demo_solver_plugin.py").write_text(
        "\n".join(
            [
                "class DemoSolverPlugin:",
                "    def __init__(self, manifest):",
                "        self.plugin_id = manifest.plugin_id",
                "        self.name = manifest.name",
                "",
                "def get_plugin(manifest):",
                "    return DemoSolverPlugin(manifest)",
            ]
        ),
        encoding="utf-8",
    )
    manifest_path = plugin_dir / "plugin.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "solver.demo",
                "name": "Demo Solver",
                "kind": "solver",
                "entry_point": "demo_solver_plugin:get_plugin",
            }
        ),
        encoding="utf-8",
    )
    manifest = PluginManifest.from_file(manifest_path)
    loader = ImportlibPluginLoader()

    result = loader.load(manifest)

    assert loader.can_load(manifest) is True
    assert result.loaded is True
    assert result.load_state == "loaded"
    assert result.plugin.plugin_id == "solver.demo"
    assert result.plugin.name == "Demo Solver"


def test_importlib_plugin_loader_reports_factory_errors(tmp_path) -> None:
    plugin_dir = tmp_path / "bad_solver"
    plugin_dir.mkdir()
    (plugin_dir / "bad_solver_plugin.py").write_text(
        "\n".join(
            [
                "class BadSolverPlugin:",
                "    plugin_id = 'solver.other'",
                "",
                "def get_plugin():",
                "    return BadSolverPlugin()",
            ]
        ),
        encoding="utf-8",
    )
    manifest_path = plugin_dir / "plugin.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "solver.bad",
                "name": "Bad Solver",
                "kind": "solver",
                "entry_point": "bad_solver_plugin:get_plugin",
            }
        ),
        encoding="utf-8",
    )
    manifest = PluginManifest.from_file(manifest_path)

    result = ImportlibPluginLoader().load(manifest)

    assert result.loaded is False
    assert result.load_state == "error"
    assert "Loaded plugin id does not match manifest id" in result.error


def test_importlib_plugin_loader_supports_non_solver_kinds_by_default() -> None:
    manifest = PluginManifest.from_mapping(
        {
            "id": "connections.ec3",
            "name": "Assemblages Eurocode 3",
            "kind": "design_module",
            "entry_point": "connections_plugin:get_plugin",
        }
    )

    assert ImportlibPluginLoader().can_load(manifest) is True
    assert ImportlibPluginLoader(allowed_kinds=("solver",)).can_load(manifest) is False


def test_application_services_can_hide_unloaded_solver_manifests(tmp_path) -> None:
    (tmp_path / "plugin.json").write_text(
        json.dumps({"id": "solver.external", "name": "External", "kind": "solver"}),
        encoding="utf-8",
    )
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_roots=(tmp_path,),
    )

    assert services.get_solver_display_info(include_installed_plugins=False) == [
        {"id": "fake.solver", "engine": "fake", "enabled": True}
    ]


def test_application_services_skips_display_manifest_duplicates(tmp_path) -> None:
    (tmp_path / "plugin.json").write_text(
        json.dumps({"id": "fake.solver", "name": "Duplicate", "kind": "solver"}),
        encoding="utf-8",
    )
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_roots=(tmp_path,),
    )

    assert services.get_solver_display_info() == [
        {"id": "fake.solver", "engine": "fake", "enabled": True}
    ]


def test_application_services_exposes_plugin_discovery_errors(tmp_path) -> None:
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad_manifest = bad_dir / "plugin.json"
    bad_manifest.write_text("{not-json", encoding="utf-8")
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_roots=(tmp_path,),
    )

    errors = services.get_plugin_discovery_errors()

    assert len(errors) == 1
    assert errors[0].path == bad_manifest


def test_application_services_discovers_installed_plugin_manifests(tmp_path) -> None:
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "solver.external",
                "name": "External Solver",
                "kind": "solver",
            }
        ),
        encoding="utf-8",
    )
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_roots=(tmp_path,),
    )

    result = services.discover_plugins()

    assert [manifest.plugin_id for manifest in result.manifests] == [
        "solver.external"
    ]
    assert result.errors == ()


def test_application_services_filters_installed_plugins_by_kind(tmp_path) -> None:
    solver_dir = tmp_path / "solver"
    tool_dir = tmp_path / "tool"
    solver_dir.mkdir()
    tool_dir.mkdir()
    (solver_dir / "plugin.json").write_text(
        json.dumps({"id": "solver.external", "name": "Solver", "kind": "solver"}),
        encoding="utf-8",
    )
    (tool_dir / "plugin.json").write_text(
        json.dumps({"id": "tool.external", "name": "Tool", "kind": "tool"}),
        encoding="utf-8",
    )
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_roots=(tmp_path,),
    )

    manifests = services.get_installed_plugin_manifests(kind="solver")
    registry = services.get_installed_plugin_registry(kind="solver")

    assert [manifest.plugin_id for manifest in manifests] == ["solver.external"]
    assert registry.ids() == ("solver.external",)


def test_plugin_manifest_supports_generic_extension_metadata() -> None:
    manifest = PluginManifest.from_mapping(
        {
            "id": "connections.ec3",
            "name": "Assemblages Eurocode 3",
            "kind": "design_module",
            "extension_points": ["connections.design", "reports.detailing"],
            "capabilities": ["steel_connections", "bolted_end_plate"],
            "tags": ["assemblages", "eurocode3"],
        }
    )

    assert manifest.kind == "design_module"
    assert manifest.extension_points == ("connections.design", "reports.detailing")
    assert manifest.capabilities == ("steel_connections", "bolted_end_plate")
    assert manifest.tags == ("assemblages", "eurocode3")
    assert manifest.provides_extension("CONNECTIONS.DESIGN")
    assert manifest.has_capability("Steel_Connections")
    assert manifest.has_tag("assemblages")


def test_application_services_filters_plugins_by_extension_capability_and_tag(
    tmp_path,
) -> None:
    connection_dir = tmp_path / "connections"
    export_dir = tmp_path / "export"
    connection_dir.mkdir()
    export_dir.mkdir()
    (connection_dir / "plugin.json").write_text(
        json.dumps(
            {
                "id": "connections.ec3",
                "name": "Assemblages Eurocode 3",
                "kind": "design_module",
                "extension_points": ["connections.design"],
                "capabilities": ["steel_connections"],
                "tags": ["assemblages", "eurocode3"],
            }
        ),
        encoding="utf-8",
    )
    (export_dir / "plugin.json").write_text(
        json.dumps(
            {
                "id": "export.ifc",
                "name": "IFC Export",
                "kind": "exporter",
                "extension_points": ["project.export"],
                "capabilities": ["ifc"],
                "tags": ["bim"],
            }
        ),
        encoding="utf-8",
    )
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_roots=(tmp_path,),
    )

    manifests = services.get_installed_plugin_manifests(
        extension_point="connections.design",
        capability="steel_connections",
        tag="assemblages",
    )
    rows = services.get_plugin_display_info(extension_point="connections.design")
    registry = services.get_installed_plugin_registry(
        extension_point="connections.design"
    )

    assert [manifest.plugin_id for manifest in manifests] == ["connections.ec3"]
    assert registry.ids() == ("connections.ec3",)
    assert rows[0]["id"] == "connections.ec3"
    assert rows[0]["kind"] == "design_module"
    assert rows[0]["extension_points"] == "connections.design"
    assert rows[0]["capabilities"] == "steel_connections"


def test_run_connection_design_calls_loaded_connection_plugins() -> None:
    manifest = PluginManifest.from_mapping(
        {
            "id": "connections.fake",
            "name": "Fake Connections",
            "kind": "design_module",
            "extension_points": ["connections.design"],
        }
    )
    loader = FakeConnectionPluginLoader()
    request = ConnectionDesignRequest(
        connection_id="J1",
        connection_type="end_plate",
        member_tags=[10, 11],
        design_code="EC3",
    )

    results = RunConnectionDesign(loader, [manifest]).execute(request)

    assert len(results) == 1
    assert results[0].plugin_id == "connections.fake"
    assert results[0].success is True
    assert results[0].payload["connection_id"] == "J1"
    assert results[0].payload["unity_ratio"] == 0.73
    assert results[0].warnings == ("demo warning",)
    assert loader.plugin.requests == [request]
    assert request.member_tags == (10, 11)


def test_run_connection_design_skips_non_applicable_plugin() -> None:
    manifest = PluginManifest.from_mapping(
        {
            "id": "connections.fake",
            "name": "Fake Connections",
            "kind": "design_module",
            "extension_points": ["connections.design"],
        }
    )
    loader = FakeConnectionPluginLoader()

    results = RunConnectionDesign(loader, [manifest]).execute(
        ConnectionDesignRequest(
            connection_id="J2",
            connection_type="base_plate",
        )
    )

    assert results[0].success is False
    assert results[0].status == "skipped"
    assert loader.plugin.requests == []


def test_application_services_design_connection_uses_installed_plugin(tmp_path) -> None:
    plugin_dir = tmp_path / "connections_ec3"
    plugin_dir.mkdir()
    (plugin_dir / "connections_ec3_plugin.py").write_text(
        "\n".join(
            [
                "class ConnectionsEc3Plugin:",
                "    plugin_id = 'connections.ec3'",
                "",
                "    def can_design_connection(self, request):",
                "        return request.design_code == 'EC3'",
                "",
                "    def design_connection(self, request):",
                "        return {",
                "            'success': True,",
                "            'payload': {",
                "                'connection_id': request.connection_id,",
                "                'code': request.design_code,",
                "                'unity_ratio': 0.81,",
                "            },",
                "        }",
                "",
                "def get_plugin(manifest):",
                "    return ConnectionsEc3Plugin()",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "id": "connections.ec3",
                "name": "Assemblages Eurocode 3",
                "kind": "design_module",
                "entry_point": "connections_ec3_plugin:get_plugin",
                "extension_points": ["connections.design"],
                "capabilities": ["steel_connections"],
                "tags": ["assemblages", "eurocode3"],
            }
        ),
        encoding="utf-8",
    )
    services = ApplicationServices(
        SimpleNamespace(loads={}, combinations={}),
        solver_manager=FakeSolverManager(),
        plugin_loader=ImportlibPluginLoader(),
        plugin_roots=(tmp_path,),
    )

    manifests = services.get_connection_design_plugin_manifests()
    results = services.design_connection(
        ConnectionDesignRequest(
            connection_id="J3",
            connection_type="end_plate",
            design_code="EC3",
        )
    )

    assert [manifest.plugin_id for manifest in manifests] == ["connections.ec3"]
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].payload == {
        "connection_id": "J3",
        "code": "EC3",
        "unity_ratio": 0.81,
    }


def test_run_connection_design_reports_missing_requested_plugin() -> None:
    results = RunConnectionDesign(
        FakeConnectionPluginLoader(),
        [],
    ).execute(
        ConnectionDesignRequest(connection_id="J4"),
        plugin_id="connections.missing",
    )

    assert results[0] == ConnectionDesignResult.failed(
        "connections.missing",
        "No plugin declares connections.design.",
        status="not_found",
    )


def test_default_plugin_roots_include_environment_paths(monkeypatch, tmp_path) -> None:
    custom_a = tmp_path / "a"
    custom_b = tmp_path / "b"
    monkeypatch.setenv(
        "HEXA_STRUCTURES_PLUGIN_PATH",
        f"{custom_a}{os.pathsep}{custom_b}",
    )

    roots = default_plugin_roots()

    assert roots[0] == custom_a
    assert roots[1] == custom_b


def test_solver_manager_instantiates_solver_adapters() -> None:
    backend, _engine = SolverManager().create_backend(ProjectModel(), "pynite")

    assert backend.__class__.__module__.startswith("core.adapters.solvers.")
    assert hasattr(backend, "run_static")


def test_solver_registry_lists_builtin_plugins_in_fallback_order() -> None:
    plugins = get_solver_plugins()

    assert [plugin.plugin_id for plugin in plugins] == ["pynite", "opensees"]
    assert [plugin.engine for plugin in plugins] == [SolverEngine.PYNITE, SolverEngine.OPENSEES]
    assert plugins[0].is_default is True


def test_solver_registry_exposes_adapter_factories() -> None:
    plugin_map = get_solver_plugin_map()
    adapter = plugin_map[SolverEngine.PYNITE].create(ProjectModel())

    assert adapter.engine_name == "pynite"
    assert adapter.__class__.__module__ == "core.adapters.solvers.pynite_adapter"


def test_generic_plugin_registry_rejects_duplicate_ids() -> None:
    descriptor = PluginDescriptor(plugin_id="solver.demo", name="Demo")
    registry = PluginRegistry((descriptor,))

    assert registry.ids() == ("solver.demo",)
    with pytest.raises(ValueError, match="Plugin already registered"):
        registry.register(descriptor)


def test_plugin_manifest_loads_valid_json_metadata(tmp_path) -> None:
    manifest_path = tmp_path / "hexa-plugin.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "vendor.fast_solver",
                "name": "Fast Solver",
                "kind": "solver",
                "version": "0.1.0",
                "api_version": "1",
                "entry_point": "vendor.fast_solver:get_plugin",
                "capabilities": ["static_linear", "modal"],
            }
        ),
        encoding="utf-8",
    )

    manifest = PluginManifest.from_file(manifest_path)

    assert manifest.plugin_id == "vendor.fast_solver"
    assert manifest.name == "Fast Solver"
    assert manifest.kind == "solver"
    assert manifest.entry_point == "vendor.fast_solver:get_plugin"
    assert manifest.capabilities == ("static_linear", "modal")
    assert manifest.path == manifest_path


def test_plugin_manifest_requires_stable_id_name_and_kind() -> None:
    with pytest.raises(ValueError, match="'id' is required"):
        PluginManifest.from_mapping({"name": "Broken", "kind": "solver"})
    with pytest.raises(ValueError, match="'name' is required"):
        PluginManifest.from_mapping({"id": "broken", "kind": "solver"})
    with pytest.raises(ValueError, match="'kind' is required"):
        PluginManifest.from_mapping({"id": "broken", "name": "Broken"})


def test_plugin_discovery_reads_direct_and_child_manifests(tmp_path) -> None:
    direct = tmp_path / "hexa-plugin.json"
    child_dir = tmp_path / "custom_solver"
    child_dir.mkdir()
    child = child_dir / "plugin.json"
    direct.write_text(
        json.dumps({"id": "direct.plugin", "name": "Direct", "kind": "tool"}),
        encoding="utf-8",
    )
    child.write_text(
        json.dumps({"id": "child.plugin", "name": "Child", "kind": "solver"}),
        encoding="utf-8",
    )

    result = discover_plugin_manifests([tmp_path])

    assert [manifest.plugin_id for manifest in result.manifests] == [
        "direct.plugin",
        "child.plugin",
    ]
    assert result.errors == ()


def test_plugin_discovery_reports_invalid_manifest_without_executing_code(tmp_path) -> None:
    plugin_dir = tmp_path / "bad_plugin"
    plugin_dir.mkdir()
    manifest_path = plugin_dir / "plugin.json"
    marker_path = plugin_dir / "SHOULD_NOT_EXIST.txt"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "bad.plugin",
                "name": "Bad Plugin",
                "kind": "solver",
                "entry_point": (
                    f"pathlib:Path({str(marker_path)!r}).write_text('boom')"
                ),
                "capabilities": "static_linear",
            }
        ),
        encoding="utf-8",
    )

    result = discover_plugin_manifests([tmp_path])

    assert result.manifests == ()
    assert len(result.errors) == 1
    assert result.errors[0].path == manifest_path
    assert not marker_path.exists()


def test_plugin_discovery_strict_mode_raises_on_invalid_manifest(tmp_path) -> None:
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid plugin manifest JSON"):
        discover_plugin_manifests([tmp_path], strict=True)


def test_manifest_registry_indexes_discovered_plugins(tmp_path) -> None:
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text(
        json.dumps({"id": "solver.demo", "name": "Demo Solver", "kind": "solver"}),
        encoding="utf-8",
    )
    manifests = discover_plugin_manifests([tmp_path]).manifests

    registry = build_manifest_registry(manifests)

    assert registry.ids() == ("solver.demo",)
    assert registry.require("solver.demo").kind == "solver"


def test_solver_plugins_expose_stable_ids_and_metadata() -> None:
    plugin_map = get_solver_plugin_id_map()

    assert set(plugin_map) == {"pynite", "opensees"}
    assert plugin_map["pynite"].descriptor.plugin_id == "pynite"
    assert plugin_map["opensees"].descriptor.api_version == "1"


def test_solver_manager_detects_solver_plugin_metadata() -> None:
    infos = SolverManager().detect_engines()

    assert [info.solver_id for info in infos] == ["pynite", "opensees"]
    assert all(info.api_version == "1" for info in infos)
    assert all(info.source == "builtin" for info in infos)


def test_solver_manager_can_create_solver_by_stable_id() -> None:
    solver, solver_id = SolverManager().create_solver(ProjectModel(), "pynite")

    assert solver_id in {"pynite", "opensees"}
    assert solver.__class__.__module__.startswith("core.adapters.solvers.")


def test_solver_manager_returns_capabilities_by_stable_id() -> None:
    caps = SolverManager().get_capabilities_for_solver("pynite")

    assert caps[AnalysisFeature.STATIC_LINEAR].feature == AnalysisFeature.STATIC_LINEAR


def test_application_and_plugins_layers_do_not_import_technical_frameworks() -> None:
    forbidden_tokens = (
        "PySide6",
        "openseespy",
        "Pynite",
        "PyniteFEA",
        "sqlite3",
        "matplotlib",
        "core.solvers.pynite_backend",
        "core.solvers.opensees_backend",
        "core.plate_mesher",
    )
    roots = [
        Path("core/application"),
        Path("core/plugins"),
    ]

    offenders = []
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                if token in text:
                    offenders.append((str(path), token))

    assert offenders == []
