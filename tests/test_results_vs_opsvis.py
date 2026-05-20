"""Comparaison directe entre notre extraction et la référence OpenSees/opsvis.

Ces tests construisent un vrai modèle OpenSees via le `ProjectModel`,
lancent une analyse linéaire, puis comparent :

1. les efforts d'extrémité extraits par `ResultsExtractor`,
2. la distribution interpolée par `interpolate_internal_forces`,
3. la distribution retournée par `opsvis.section_force_distribution_3d`.

L'objectif est de verrouiller la convention locale et de détecter toute
régression d'orientation/signes sur les poutres 3D, en particulier pour
les éléments inclinés ou verticaux.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("matplotlib")
ops = pytest.importorskip("openseespy.opensees")
section_force_distribution_3d = pytest.importorskip(
    "opsvis.secforces"
).section_force_distribution_3d

from core.analysis import AnalysisRunner
from core.model_data import ElementLoad, LoadData, NodalLoad, ProjectModel
from core.results import ElementResult
from core.solvers import SolverEngine
from gui.widgets.diagram_renderer import _element_samples, build_figure_2d

try:
    from opsvis.model import get_Ew_data_from_ops_domain_3d
except Exception:  # pragma: no cover
    get_Ew_data_from_ops_domain_3d = None  # type: ignore[assignment]


_BEAM_PIPELINE_CASES = [
    pytest.param((5.0, 0.0, 0.0), id="horizontal-x"),
    pytest.param((5.0, 0.0, 5.0), id="inclined-xz"),
    pytest.param((0.0, 0.0, 5.0), id="vertical-z"),
    pytest.param((3.0, 4.0, 5.0), id="spatial-3d"),
]


def _make_single_beam_project(
    node_j_xyz: tuple[float, float, float],
    *,
    nodal_load: tuple[float, float, float, float, float, float] = (
        5.0, 7.0, -11.0, 2.0, 13.0, -17.0,
    ),
    element_load: tuple[float, float, float] = (1.2, 3.5, -4.5),
) -> ProjectModel:
    project = ProjectModel(name="test-opensees-opsvis")
    project.seed_default_library()

    n1 = project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    n2 = project.add_node(*node_j_xyz)
    sec_tag = next(iter(project.sections))
    project.add_element(n1.tag, n2.tag, sec_tag)

    load = LoadData(tag=1, name="L1", load_type="variable")
    project.loads[load.tag] = load
    project.nodal_loads.append(
        NodalLoad(
            load_tag=load.tag,
            node_tag=n2.tag,
            fx=nodal_load[0],
            fy=nodal_load[1],
            fz=nodal_load[2],
            mx=nodal_load[3],
            my=nodal_load[4],
            mz=nodal_load[5],
        )
    )
    project.element_loads.append(
        ElementLoad(
            load_tag=load.tag,
            element_tag=1,
            wx=element_load[0],
            wy=element_load[1],
            wz=element_load[2],
        )
    )
    return project


def _run_single_beam(
    node_j_xyz: tuple[float, float, float],
) -> tuple[ProjectModel, dict, np.ndarray]:
    project = _make_single_beam_project(node_j_xyz)
    success, results = AnalysisRunner(
        project,
        engine=SolverEngine.OPENSEES,
    ).run_static(load_tag=1)
    assert success, results
    end = np.array(node_j_xyz, dtype=float)
    length = np.linalg.norm(end)
    assert length > 0.0
    return project, results, end


def _element_result_from_local_force(values: list[float] | tuple[float, ...]) -> ElementResult:
    return ElementResult(
        tag=1,
        n_i=values[0],
        vy_i=values[1],
        vz_i=values[2],
        t_i=values[3],
        my_i=values[4],
        mz_i=values[5],
        n_j=-values[6],
        vy_j=-values[7],
        vz_j=-values[8],
        t_j=-values[9],
        my_j=-values[10],
        mz_j=-values[11],
    )


@pytest.mark.parametrize("node_j_xyz", _BEAM_PIPELINE_CASES)
def test_element_end_forces_match_opensees_local_force(
    node_j_xyz: tuple[float, float, float],
) -> None:
    project, results, _ = _run_single_beam(node_j_xyz)
    actual = results["element_forces"][1]
    local_force = ops.eleResponse(1, "localForce")
    expected = _element_result_from_local_force(local_force)

    for attr in (
        "n_i", "vy_i", "vz_i", "t_i", "my_i", "mz_i",
        "n_j", "vy_j", "vz_j", "t_j", "my_j", "mz_j",
    ):
        assert getattr(actual, attr) == pytest.approx(getattr(expected, attr), abs=1e-9)

    # Le test repose bien sur le domaine OpenSees construit par notre projet.
    assert set(project.elements) == {1}


@pytest.mark.parametrize("node_j_xyz", _BEAM_PIPELINE_CASES)
def test_single_element_local_figure_uses_true_3d_length(
    node_j_xyz: tuple[float, float, float],
) -> None:
    project, results, end = _run_single_beam(node_j_xyz)
    file_info = {
        "label": "E1 seul (repere local)",
        "local_element": True,
        "element_tag": 1,
        "ele_tags": [1],
        "plane": None,
    }

    fig = build_figure_2d("My", file_info, project=project, results=results)
    ax = fig.axes[0]
    axis_line = ax.lines[0]

    assert ax.get_xlabel() == "x local (m)"
    assert ax.get_ylabel() == "My local (kN.m)"
    assert "plan local x-z" in ax.get_title()
    assert float(axis_line.get_xdata()[0]) == pytest.approx(0.0, abs=1e-9)
    assert float(axis_line.get_xdata()[1]) == pytest.approx(
        float(np.linalg.norm(end)),
        rel=1e-9,
    )


@pytest.mark.parametrize("node_j_xyz", _BEAM_PIPELINE_CASES)
def test_renderer_sampling_matches_opsvis_distribution_for_beam_pipeline(
    node_j_xyz: tuple[float, float, float],
) -> None:
    if get_Ew_data_from_ops_domain_3d is None:
        pytest.skip("opsvis.model.get_Ew_data_from_ops_domain_3d indisponible")

    _, _, end = _run_single_beam(node_j_xyz)

    ecrd_3d = np.array([[0.0, 0.0, 0.0], end], dtype=float)
    local_force = ops.eleResponse(1, "localForce")
    eload = get_Ew_data_from_ops_domain_3d().get(1, [["-beamUniform", 0.0, 0.0, 0.0]])
    nep = 17
    s_all, xl, _ = section_force_distribution_3d(ecrd_3d, local_force, nep, eload)

    component_map = {
        "N": 0,
        "Vy": 1,
        "Vz": 2,
        "T": 3,
        "My": 4,
        "Mz": 5,
    }
    for name, idx in component_map.items():
        sampled = _element_samples(1, name, nep)
        assert sampled is not None
        _, sampled_xl, sampled_values, sampled_eload = sampled
        assert np.allclose(sampled_xl, xl, atol=1e-9)
        assert sampled_eload == eload
        assert np.allclose(
            sampled_values,
            s_all[:, idx],
            atol=1e-8,
            rtol=1e-8,
        ), f"Incohérence sur {name}"
