import math

import pytest

import core.ops_builder as ops_builder_module
from core.model_data import ProjectModel
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


def _make_beam_project(end: tuple[float, float, float]) -> ProjectModel:
    project = ProjectModel(name="OpenSees local axes")
    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "Test",
        "rectangular",
        material_tag=1,
        area=0.01,
        inertia_y=1.0e-4,
        inertia_z=2.0e-4,
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(*end)
    project.add_element(1, 2, section_tag=1)
    return project


def _geom_vec(args: tuple) -> tuple[float, float, float]:
    return (float(args[2]), float(args[3]), float(args[4]))


def _dot(a, b) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _norm(v) -> float:
    return math.sqrt(_dot(v, v))


def test_horizontal_beam_receives_global_z_vecxz(monkeypatch) -> None:
    project = _make_beam_project((5.0, 0.0, 0.0))
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    OpsBuilder(project).build()

    geom_calls = recorder.calls_for("geomTransf")
    element_call = next(
        args for args in recorder.calls_for("element")
        if args[0] == "elasticBeamColumn"
    )
    assert len(geom_calls) == 1
    assert _geom_vec(geom_calls[0]) == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
    assert element_call[-1] == geom_calls[0][1]


def test_vertical_beam_receives_vecxz_not_parallel_to_member(monkeypatch) -> None:
    project = _make_beam_project((0.0, 0.0, 3.0))
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    OpsBuilder(project).build()

    vecxz = _geom_vec(recorder.calls_for("geomTransf")[0])
    assert vecxz == pytest.approx((1.0, 0.0, 0.0), abs=1e-12)
    assert _dot(vecxz, (0.0, 0.0, 1.0)) == pytest.approx(0.0, abs=1e-12)


def test_inclined_3d_beam_receives_valid_vecxz(monkeypatch) -> None:
    end = (3.0, 4.0, 5.0)
    project = _make_beam_project(end)
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    OpsBuilder(project).build()

    vecxz = _geom_vec(recorder.calls_for("geomTransf")[0])
    length = _norm(end)
    x_axis = tuple(value / length for value in end)
    assert _norm(vecxz) == pytest.approx(1.0, abs=1e-12)
    assert _dot(vecxz, x_axis) == pytest.approx(0.0, abs=1e-12)
    assert all(math.isfinite(value) for value in vecxz)


def test_geom_transforms_are_created_before_beam_elements(monkeypatch) -> None:
    project = _make_beam_project((3.0, 4.0, 5.0))
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    OpsBuilder(project).build()

    first_geom = next(index for index, call in enumerate(recorder.calls) if call[0] == "geomTransf")
    first_beam = next(
        index
        for index, call in enumerate(recorder.calls)
        if call[0] == "element" and call[1][0] == "elasticBeamColumn"
    )
    assert first_geom < first_beam


def test_equal_vecxz_reuses_same_transform_tag(monkeypatch) -> None:
    project = _make_beam_project((5.0, 0.0, 0.0))
    project.add_node(10.0, 0.0, 0.0)
    project.add_element(2, 3, section_tag=1)
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    OpsBuilder(project).build()

    geom_calls = recorder.calls_for("geomTransf")
    beam_calls = [args for args in recorder.calls_for("element") if args[0] == "elasticBeamColumn"]
    assert len(geom_calls) == 1
    assert {call[-1] for call in beam_calls} == {geom_calls[0][1]}


def test_2d_build_keeps_single_2d_transform(monkeypatch) -> None:
    project = _make_beam_project((5.0, 0.0, 0.0))
    recorder = _OpsRecorder()
    monkeypatch.setattr(ops_builder_module, "ops", recorder)

    OpsBuilder(project).build(ndm=2, ndf=3)

    assert recorder.calls_for("geomTransf") == [("Linear", 1)]
    element_call = next(
        args for args in recorder.calls_for("element")
        if args[0] == "elasticBeamColumn"
    )
    assert element_call[-1] == 1
