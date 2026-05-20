from __future__ import annotations

import importlib.util
import math

import numpy as np
import pytest

from core.analysis import AnalysisRunner
from core.local_axes import local_axes_from_nodes, opensees_vecxz_from_axes
from core.model_data import ElementLoad, LoadData, NodalLoad, ProjectModel, SurfaceLoad
from core.results import ResultsExtractor
from core.self_weight import element_local_axes


HAS_PYNITE = importlib.util.find_spec("Pynite") is not None


def _add_steel_section(project: ProjectModel, *, tag_name: str = "IPE 300") -> None:
    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        tag_name,
        "I_profile",
        material_tag=1,
        area=53.8e-4,
        inertia_y=8360e-8,
        inertia_z=603e-8,
        properties={"J": 2.0e-6},
    )


@pytest.mark.skipif(not HAS_PYNITE, reason="PyNiteFEA non disponible")
def test_pynite_simply_supported_beam_uniform_load_reactions() -> None:
    project = ProjectModel(name="Regression beam UDL")
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 0, 1))
    project.add_node(6.0, 0.0, 0.0, fixities=(0, 1, 1, 1, 0, 1))
    _add_steel_section(project)
    project.add_element(1, 2, section_tag=1)
    project.loads[1] = LoadData(tag=1, name="UDL", load_type="live")
    project.element_loads.append(
        ElementLoad(load_tag=1, element_tag=1, wz=-5.0, coordinate_system="global")
    )

    success, results = AnalysisRunner(project, engine="pynite").run_static(load_tag=1)

    assert success is True, results
    reactions = results["reactions"]
    assert math.isclose(reactions[1].fz_reaction, 15.0, rel_tol=1e-6, abs_tol=1e-8)
    assert math.isclose(reactions[2].fz_reaction, 15.0, rel_tol=1e-6, abs_tol=1e-8)
    assert abs(reactions[1].my_reaction) < 1e-8
    assert abs(reactions[2].my_reaction) < 1e-8


@pytest.mark.skipif(not HAS_PYNITE, reason="PyNiteFEA non disponible")
def test_pynite_simple_2d_portal_frame_balances_lateral_load() -> None:
    project = ProjectModel(name="Regression portal")
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(0.0, 0.0, 3.0)
    project.add_node(4.0, 0.0, 3.0)
    project.add_node(4.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    _add_steel_section(project)
    project.add_element(1, 2, section_tag=1)
    project.add_element(2, 3, section_tag=1)
    project.add_element(4, 3, section_tag=1)
    project.loads[1] = LoadData(tag=1, name="Wind", load_type="wind")
    project.nodal_loads.append(NodalLoad(load_tag=1, node_tag=2, fx=5.0))
    project.nodal_loads.append(NodalLoad(load_tag=1, node_tag=3, fx=5.0))

    success, results = AnalysisRunner(project, engine="pynite").run_static(load_tag=1)

    assert success is True, results
    total_rx = sum(result.fx_reaction for result in results["reactions"].values())
    assert math.isclose(total_rx, -10.0, rel_tol=1e-6, abs_tol=1e-8)
    assert results["displacements"][2].ux > 0.0
    assert results["displacements"][3].ux > 0.0


@pytest.mark.skipif(not HAS_PYNITE, reason="PyNiteFEA non disponible")
def test_pynite_inclined_3d_member_uses_true_member_length_for_diagram_sampling() -> None:
    project = ProjectModel(name="Regression inclined 3D")
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(3.0, 4.0, 5.0)
    _add_steel_section(project)
    project.add_element(1, 2, section_tag=1)
    project.loads[1] = LoadData(tag=1, name="Tip load", load_type="live")
    project.nodal_loads.append(NodalLoad(load_tag=1, node_tag=2, fx=2.0, fy=-3.0, fz=-4.0))

    runner = AnalysisRunner(project, engine="pynite")
    success, results = runner.run_static(load_tag=1)
    sample = runner.backend.sample_diagram_component(1, "My", 7)

    assert success is True, results
    assert sample is not None
    x, values = sample
    assert math.isclose(float(x[-1]), math.sqrt(50.0), rel_tol=1e-9)
    assert np.any(np.abs(values) > 1e-9)


def test_member_local_axes_are_consistent_for_main_3d_orientations() -> None:
    cases = [
        (5.0, 0.0, 0.0),
        (0.0, 0.0, 5.0),
        (5.0, 0.0, 2.0),
        (3.0, 4.0, 5.0),
    ]
    for end in cases:
        project = ProjectModel(name=f"axes {end}")
        project.add_node(0.0, 0.0, 0.0)
        project.add_node(*end)
        project.add_material("Acier S355", "steel", "S355")
        project.add_section("Test", "rectangular", 1, area=0.01, inertia_y=1e-4, inertia_z=2e-4)
        element = project.add_element(1, 2, section_tag=1)

        axes = element_local_axes(project, element)
        expected = local_axes_from_nodes((0.0, 0.0, 0.0), end)
        rotation = ResultsExtractor(project)._element_rotation(element)
        vecxz = np.array(opensees_vecxz_from_axes(expected), dtype=float)
        local_x = np.array(expected.x, dtype=float)

        assert np.allclose(np.column_stack(axes), expected.rotation_matrix)
        assert np.allclose(rotation, np.column_stack(axes))
        assert np.isclose(float(np.dot(vecxz, local_x)), 0.0, atol=1e-12)


def test_opensees_shellmitc4_quad_plate_reaction_balance_if_available() -> None:
    pytest.importorskip("openseespy.opensees")

    project = ProjectModel(name="Regression ShellMITC4")
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(2.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(2.0, 2.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(0.0, 2.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_material("Beton C30", "concrete", "C30/37")
    project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_surface_element((1, 2, 3, 4), section_tag=1)
    project.loads[1] = LoadData(tag=1, name="Surface", load_type="live")
    project.surface_loads.append(SurfaceLoad(load_tag=1, surface_tag=1, qz=-2.5))

    success, results = AnalysisRunner(project, engine="opensees").run_static(load_tag=1)

    assert success is True, results
    total_fz = sum(result.fz_reaction for result in results["reactions"].values())
    assert math.isclose(total_fz, 10.0, rel_tol=1e-3, abs_tol=1e-3)


def test_project_model_rejects_new_triangular_surface_with_quad_formulation() -> None:
    project = ProjectModel(name="No triangle regression")
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(1.0, 0.0, 0.0)
    project.add_node(0.0, 1.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    project.add_section(
        "Dalle",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )

    with pytest.raises(ValueError, match="attend 4"):
        project.add_surface_element((1, 2, 3), section_tag=1)
