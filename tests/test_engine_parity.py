from __future__ import annotations

import math
import importlib.util

import pytest

from core.analysis import AnalysisRunner
from core.model_data import CombinationData, LoadData, NodalLoad, ProjectModel
from core.results import compute_envelopes


HAS_PYNITE = importlib.util.find_spec("Pynite") is not None
HAS_OPENSEES = importlib.util.find_spec("openseespy") is not None


def _make_cantilever_with_cases() -> ProjectModel:
    project = ProjectModel(name="Parity beam")
    project.add_node(0, 0, 0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(5, 0, 0)
    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "IPE 300",
        "I_profile",
        material_tag=1,
        area=53.8e-4,
        inertia_y=8360e-8,
        inertia_z=603e-8,
    )
    project.add_element(1, 2, section_tag=1)
    project.loads[1] = LoadData(tag=1, name="G", load_type="dead")
    project.loads[2] = LoadData(tag=2, name="Q", load_type="live")
    project.nodal_loads.append(NodalLoad(load_tag=1, node_tag=2, fz=-10.0))
    project.nodal_loads.append(NodalLoad(load_tag=2, node_tag=2, fx=5.0))
    project.combinations[1] = CombinationData(
        tag=1,
        name="ELU",
        combo_type="ULS",
        factors={1: 1.35, 2: 1.5},
    )
    return project


def _make_vertical_column() -> ProjectModel:
    project = ProjectModel(name="Parity column")
    project.add_node(0, 0, 0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(0, 0, 5)
    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "IPE 300",
        "I_profile",
        material_tag=1,
        area=53.8e-4,
        inertia_y=8360e-8,
        inertia_z=603e-8,
    )
    project.add_element(1, 2, section_tag=1)
    project.loads[1] = LoadData(tag=1, name="L", load_type="live")
    project.nodal_loads.append(NodalLoad(load_tag=1, node_tag=2, fy=10.0))
    return project


def _run(project: ProjectModel, engine: str):
    return AnalysisRunner(project, engine=engine)


@pytest.mark.skipif(
    not (HAS_PYNITE and HAS_OPENSEES),
    reason="Comparaison PyNite/OpenSees indisponible",
)
def test_static_results_match_opensees_for_beam_cases() -> None:
    project = _make_cantilever_with_cases()
    opensees = _run(project, "opensees").run_all()
    pynite = _run(project, "pynite").run_all()

    assert opensees.keys() == pynite.keys()

    for case_name in opensees:
        ok_ops, res_ops = opensees[case_name]
        ok_pyn, res_pyn = pynite[case_name]
        assert ok_ops is True
        assert ok_pyn is True

        disp_ops = res_ops["displacements"][2]
        disp_pyn = res_pyn["displacements"][2]
        react_ops = res_ops["reactions"][1]
        react_pyn = res_pyn["reactions"][1]
        elem_ops = res_ops["element_forces"][1]
        elem_pyn = res_pyn["element_forces"][1]

        assert math.isclose(disp_pyn.ux, disp_ops.ux, rel_tol=1e-6, abs_tol=1e-12)
        assert math.isclose(disp_pyn.uz, disp_ops.uz, rel_tol=1e-6, abs_tol=1e-12)
        assert math.isclose(
            react_pyn.fx_reaction, react_ops.fx_reaction, rel_tol=1e-6, abs_tol=1e-12
        )
        assert math.isclose(
            react_pyn.fz_reaction, react_ops.fz_reaction, rel_tol=1e-6, abs_tol=1e-12
        )
        assert math.isclose(
            react_pyn.my_reaction, react_ops.my_reaction, rel_tol=1e-6, abs_tol=1e-12
        )
        assert math.isclose(elem_pyn.n_i, elem_ops.n_i, rel_tol=1e-6, abs_tol=1e-12)
        assert math.isclose(elem_pyn.vz_i, elem_ops.vz_i, rel_tol=1e-6, abs_tol=1e-12)
        assert math.isclose(elem_pyn.my_i, elem_ops.my_i, rel_tol=1e-6, abs_tol=1e-12)


@pytest.mark.skipif(not HAS_PYNITE, reason="PyNiteFEA non disponible")
def test_envelopes_are_compatible_with_pynite_run_all() -> None:
    project = _make_cantilever_with_cases()
    all_results = {
        name: res
        for name, (success, res) in _run(project, "pynite").run_all().items()
        if success
    }

    envelopes = compute_envelopes(all_results, [1])
    envelope = envelopes[1]

    assert envelope.n_min_case == "ELU (combo 1)"
    assert envelope.vz_max_case == "ELU (combo 1)"
    assert envelope.my_min_case == "ELU (combo 1)"


@pytest.mark.skipif(
    not (HAS_PYNITE and HAS_OPENSEES),
    reason="Comparaison PyNite/OpenSees indisponible",
)
def test_vertical_column_mz_matches_opensees_with_pynite() -> None:
    project = _make_vertical_column()
    success_ops, res_ops = _run(project, "opensees").run_static(load_tag=1)
    success_pyn, res_pyn = _run(project, "pynite").run_static(load_tag=1)

    assert success_ops is True
    assert success_pyn is True
    assert math.isclose(
        res_pyn["element_forces"][1].mz_i,
        res_ops["element_forces"][1].mz_i,
        rel_tol=1e-6,
        abs_tol=1e-12,
    )
