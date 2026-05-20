from __future__ import annotations

import importlib.util
import math

import pytest

from core.analysis import AnalysisRunner
from core.model_data import LoadData, NodalLoad, ProjectModel


HAS_PYNITE = importlib.util.find_spec("Pynite") is not None

pytestmark = pytest.mark.skipif(
    not HAS_PYNITE,
    reason="PyNiteFEA non disponible dans l'environnement",
)


def _make_cantilever() -> ProjectModel:
    project = ProjectModel(name="Console PyNite")
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
    project.loads[1] = LoadData(tag=1, name="Charge ponctuelle", load_type="dead")
    project.nodal_loads.append(NodalLoad(load_tag=1, node_tag=2, fz=-10.0))
    return project


def test_pynite_static_cantilever_response() -> None:
    project = _make_cantilever()

    success, results = AnalysisRunner(project, engine="pynite").run_static(load_tag=1)

    assert success is True
    uz = abs(results["displacements"][2].uz)
    fz = results["reactions"][1].fz_reaction
    my = results["reactions"][1].my_reaction

    e_mod = 210_000_000
    inertia = 8360e-8
    delta_th = 10.0 * 5.0**3 / (3 * e_mod * inertia)

    assert math.isclose(uz, delta_th, rel_tol=1e-2)
    assert math.isclose(fz, 10.0, rel_tol=1e-6)
    assert math.isclose(abs(my), 50.0, rel_tol=1e-6)


def test_pynite_modal_returns_frequencies() -> None:
    project = _make_cantilever()

    success, results = AnalysisRunner(project, engine="pynite").run_modal(num_modes=2)

    assert success is True
    assert results["num_modes"] == 2
    assert len(results["frequencies_hz"]) == 2
    assert all(freq > 0 for freq in results["frequencies_hz"])
    assert 1 in results["mode_shapes"]
    assert 2 in results["mode_shapes"]
