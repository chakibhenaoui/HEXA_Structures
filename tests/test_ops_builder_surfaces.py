from __future__ import annotations

import pytest

import core.ops_builder as ops_builder_module
from core.material_properties import (
    material_elastic_modulus,
    material_mass_density_kg_m3,
    material_poisson_ratio,
)
from core.model_data import LoadData, ProjectModel, SurfaceElementData, SurfaceLoad
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


def _surface_project(*, formulation: str = "ShellMITC4", with_beam: bool = False) -> ProjectModel:
    project = ProjectModel(name="Surface builder test")
    project.add_material("Béton C30", "concrete", "C30/37")

    if with_beam:
        project.add_section(
            "Poutre 30x50",
            "rectangular",
            material_tag=1,
            area=0.15,
            inertia_y=0.003125,
            inertia_z=0.001125,
        )

    surface_section = project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": formulation},
    )

    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    if with_beam:
        project.add_element(1, 2, section_tag=1)
    project.add_surface_element((1, 2, 3, 4), section_tag=surface_section.tag)
    return project


def test_ops_builder_creates_elastic_membrane_plate_section(monkeypatch) -> None:
    project = _surface_project()
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    builder = OpsBuilder(project)
    builder.build()

    section_calls = recorder.calls_for("section")
    assert len(section_calls) == 1
    args = section_calls[0]
    material = project.materials[1]
    assert args[0] == "ElasticMembranePlateSection"
    assert args[1] == 1
    assert args[2] == pytest.approx(material_elastic_modulus(material))
    assert args[3] == pytest.approx(material_poisson_ratio(material))
    assert args[4] == pytest.approx(0.20)
    assert args[5] == pytest.approx(material_mass_density_kg_m3(material) / 1000.0)

    element_calls = recorder.calls_for("element")
    assert ("ShellMITC4", 1, 1, 2, 3, 4, 1) in element_calls


def test_ops_builder_offsets_surface_tags_from_beam_tags(monkeypatch) -> None:
    project = _surface_project(with_beam=True)
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    builder = OpsBuilder(project)
    builder.build()

    element_calls = recorder.calls_for("element")
    assert any(args[0] == "elasticBeamColumn" and args[1] == 1 for args in element_calls)
    assert any(args[0] == "ShellMITC4" and args[1] == 2 for args in element_calls)


def test_ops_builder_uses_section_torsion_constant_when_available(monkeypatch) -> None:
    project = ProjectModel(name="Torsion builder test")
    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "Poutre J",
        "rectangular",
        material_tag=1,
        area=0.02,
        inertia_y=1.0e-4,
        inertia_z=2.0e-4,
        properties={"torsion_constant": 7.5e-5},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(3.0, 0.0, 0.0)
    project.add_element(1, 2, section_tag=1)
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    OpsBuilder(project).build()

    section_call = next(args for args in recorder.calls_for("section") if args[0] == "Elastic")
    element_calls = recorder.calls_for("element")
    element_call = next(args for args in element_calls if args[0] == "elasticBeamColumn")
    assert section_call[7] == pytest.approx(7.5e-5)
    assert element_call[7] == pytest.approx(7.5e-5)


def test_ops_builder_rejects_unsupported_tri31_surface(monkeypatch) -> None:
    project = ProjectModel(name="Tri31 builder test")
    project.add_material("Béton C30", "concrete", "C30/37")
    section = project.add_section(
        "Plaque libre",
        "surface",
        material_tag=1,
        properties={"thickness": 0.18, "element_formulation": "Tri31"},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(2.5, 4.0, 0.0)
    project.surface_elements[1] = SurfaceElementData(
        tag=1,
        node_tags=(1, 2, 3),
        section_tag=section.tag,
    )

    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    builder = OpsBuilder(project)
    with pytest.raises(NotImplementedError, match="prise en charge"):
        builder.build()


def test_project_model_rejects_new_tri31_surface() -> None:
    project = ProjectModel(name="Tri31 model test")
    project.add_material("BÃ©ton C30", "concrete", "C30/37")
    section = project.add_section(
        "Plaque libre",
        "surface",
        material_tag=1,
        properties={"thickness": 0.18, "element_formulation": "Tri31"},
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(2.5, 4.0, 0.0)

    with pytest.raises(NotImplementedError, match="pas disponible"):
        project.add_surface_element((1, 2, 3), section_tag=section.tag)


def test_ops_builder_converts_uniform_surface_load_to_nodal_loads(monkeypatch) -> None:
    project = _surface_project()
    project.loads[1] = LoadData(tag=1, name="Charge surfacique", load_type="variable")
    project.surface_loads.append(SurfaceLoad(load_tag=1, surface_tag=1, qz=-2.0))

    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    builder = OpsBuilder(project)
    builder.build()
    builder.apply_loads(1)

    load_calls = recorder.calls_for("load")
    assert len(load_calls) == 4
    assert all(args[3] == pytest.approx(-10.0) for args in load_calls)


def test_ops_builder_applies_surface_self_weight_as_nodal_loads(monkeypatch) -> None:
    project = _surface_project()
    load_case = project.ensure_self_weight_load_case()

    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    builder = OpsBuilder(project)
    builder.build()
    builder.apply_loads(load_case.tag)

    load_calls = recorder.calls_for("load")
    assert len(load_calls) == 4
    assert all(args[3] == pytest.approx(-25.0) for args in load_calls)
