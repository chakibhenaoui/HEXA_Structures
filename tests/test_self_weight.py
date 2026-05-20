import math

import numpy as np

from core.analysis import AnalysisRunner
from core.material_properties import material_mass_density_kg_m3
from core.model_data import CombinationData, ElementLoad, LoadData, ProjectModel
from core.section_force_convention import resolve_display_samples
from core.self_weight import (
    GRAVITY,
    SELF_WEIGHT_LOAD_NAME,
    SELF_WEIGHT_LOAD_TYPE,
    element_global_to_local_components,
    element_load_local_components,
    element_self_weight_local_components,
    surface_self_weight_kn_m2,
    total_self_weight_kn,
)


def _make_horizontal_cantilever() -> ProjectModel:
    project = ProjectModel(name="Self weight beam")
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(5.0, 0.0, 0.0)
    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "Test 100cm2",
        "rectangular",
        material_tag=1,
        area=0.01,
        inertia_y=1e-4,
        inertia_z=1e-4,
    )
    project.add_element(1, 2, section_tag=1)
    project.ensure_self_weight_load_case()
    return project


def _make_surface_patch() -> ProjectModel:
    project = ProjectModel(name="Self weight shell")
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_surface_element((1, 2, 3, 4), section_tag=1)
    project.ensure_self_weight_load_case()
    return project


def _make_fixed_sloped_member(*, reverse: bool) -> ProjectModel:
    project = ProjectModel(name="Sloped member")
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(5.0, 0.0, 2.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "Test section",
        "rectangular",
        material_tag=1,
        area=0.02,
        inertia_y=1e-4,
        inertia_z=1e-4,
    )
    if reverse:
        project.add_element(2, 1, section_tag=1)
    else:
        project.add_element(1, 2, section_tag=1)
    project.loads[1] = LoadData(tag=1, name="G", load_type="permanent")
    project.element_loads.append(
        ElementLoad(
            load_tag=1,
            element_tag=1,
            wz=-10.0,
            coordinate_system="global",
        )
    )
    return project


def _backend_displayed_samples(
    project: ProjectModel,
    engine: str,
    component: str,
) -> np.ndarray:
    runner = AnalysisRunner(project, engine=engine)
    success, results = runner.run_static(load_tag=1)
    assert success is True, results
    sample = runner.backend.sample_diagram_component(1, component, 9)
    assert sample is not None
    x, values = sample
    element = project.elements[1]
    coords = np.array(
        [
            [
                project.nodes[element.node_i].x,
                project.nodes[element.node_i].y,
                project.nodes[element.node_i].z,
            ],
            [
                project.nodes[element.node_j].x,
                project.nodes[element.node_j].y,
                project.nodes[element.node_j].z,
            ],
        ],
        dtype=float,
    )
    display = resolve_display_samples(
        ecrd_3d=coords,
        p1=coords[0, [0, 2]],
        p2=coords[1, [0, 2]],
        x=x,
        values=values,
        component=component,
        plane="XZ",
        file_center=np.array([2.5, 1.0], dtype=float),
        apply_component_axis_sign=False,
    )
    assert display is not None
    return display.values


def _pynite_displayed_samples(project: ProjectModel, component: str) -> np.ndarray:
    return _backend_displayed_samples(project, "pynite", component)


def test_self_weight_load_case_is_created_once() -> None:
    project = ProjectModel()

    load_1 = project.ensure_self_weight_load_case()
    load_2 = project.ensure_self_weight_load_case()

    assert load_1.tag == load_2.tag
    assert load_1.name == SELF_WEIGHT_LOAD_NAME
    assert load_1.load_type == SELF_WEIGHT_LOAD_TYPE
    assert len(project.loads) == 1


def test_self_weight_components_for_horizontal_beam() -> None:
    project = _make_horizontal_cantilever()
    element = project.elements[1]

    wx, wy, wz = element_self_weight_local_components(project, element)
    expected = 78.5 * 0.01

    assert abs(wx) < 1e-12
    assert abs(wy) < 1e-12
    assert math.isclose(wz, -expected, rel_tol=1e-12)
    assert math.isclose(total_self_weight_kn(project), expected * 5.0, rel_tol=1e-12)


def test_global_distributed_load_is_projected_to_local_axes() -> None:
    project = _make_horizontal_cantilever()
    element = project.elements[1]

    wx, wy, wz = element_global_to_local_components(project, element, 0.0, 0.0, -10.0)

    assert abs(wx) < 1e-12
    assert abs(wy) < 1e-12
    assert math.isclose(wz, -10.0, rel_tol=1e-12)


def test_global_element_load_is_reprojected_after_member_orientation_changes() -> None:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(0.0, 0.0, 3.0)
    element = project.add_element(1, 2, section_tag=1)
    load = ElementLoad(
        load_tag=1,
        element_tag=1,
        wz=-10.0,
        coordinate_system="global",
    )

    forward = element_load_local_components(project, element, load)
    element.node_i, element.node_j = element.node_j, element.node_i
    backward = element_load_local_components(project, element, load)

    assert math.isclose(forward[0], -10.0, rel_tol=1e-12)
    assert math.isclose(backward[0], 10.0, rel_tol=1e-12)
    assert abs(forward[1]) < 1e-12
    assert abs(backward[1]) < 1e-12


def test_local_element_load_keeps_stored_components_after_orientation_changes() -> None:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(0.0, 0.0, 3.0)
    element = project.add_element(1, 2, section_tag=1)
    load = ElementLoad(load_tag=1, element_tag=1, wx=-10.0)

    forward = element_load_local_components(project, element, load)
    element.node_i, element.node_j = element.node_j, element.node_i
    backward = element_load_local_components(project, element, load)

    assert forward == (-10.0, 0.0, 0.0)
    assert backward == (-10.0, 0.0, 0.0)


def test_pynite_sloped_member_display_is_invariant_after_orientation_change() -> None:
    forward = _pynite_displayed_samples(
        _make_fixed_sloped_member(reverse=False),
        "My",
    )
    backward = _pynite_displayed_samples(
        _make_fixed_sloped_member(reverse=True),
        "My",
    )

    assert np.allclose(backward, forward)


def test_pynite_sloped_shear_display_is_invariant_after_orientation_change() -> None:
    forward = _pynite_displayed_samples(
        _make_fixed_sloped_member(reverse=False),
        "Vz",
    )
    backward = _pynite_displayed_samples(
        _make_fixed_sloped_member(reverse=True),
        "Vz",
    )

    assert np.allclose(backward, forward)


def test_opensees_sloped_member_display_is_invariant_after_orientation_change() -> None:
    forward = _backend_displayed_samples(
        _make_fixed_sloped_member(reverse=False),
        "opensees",
        "My",
    )
    backward = _backend_displayed_samples(
        _make_fixed_sloped_member(reverse=True),
        "opensees",
        "My",
    )

    assert np.allclose(backward, forward)


def test_opensees_sloped_shear_display_is_invariant_after_orientation_change() -> None:
    forward = _backend_displayed_samples(
        _make_fixed_sloped_member(reverse=False),
        "opensees",
        "Vz",
    )
    backward = _backend_displayed_samples(
        _make_fixed_sloped_member(reverse=True),
        "opensees",
        "Vz",
    )

    assert np.allclose(backward, forward)


def test_surface_self_weight_is_included_in_total() -> None:
    project = _make_surface_patch()
    surface = project.surface_elements[1]
    section = project.sections[surface.section_tag]
    material = project.materials[section.material_tag]

    expected_q = material_mass_density_kg_m3(material) * 0.20 * GRAVITY / 1000.0
    expected_total = expected_q * 20.0

    assert math.isclose(surface_self_weight_kn_m2(project, surface), expected_q, rel_tol=1e-12)
    assert math.isclose(total_self_weight_kn(project), expected_total, rel_tol=1e-12)


def test_self_weight_static_results_match_between_engines() -> None:
    project = _make_horizontal_cantilever()
    load_tag = project.self_weight_load_tag()
    expected_total = total_self_weight_kn(project)
    expected_moment = expected_total * 5.0 / 2.0

    for engine in ("opensees", "pynite"):
        success, results = AnalysisRunner(project, engine=engine).run_static(
            load_tag=load_tag,
        )
        assert success is True
        reaction = results["reactions"][1]
        element = results["element_forces"][1]
        assert math.isclose(reaction.fz_reaction, expected_total, rel_tol=1e-9)
        assert math.isclose(reaction.my_reaction, -expected_moment, rel_tol=1e-9)
        assert math.isclose(element.vz_i, expected_total, rel_tol=1e-9)
        assert math.isclose(element.my_i, -expected_moment, rel_tol=1e-9)


def test_self_weight_combination_factor_is_applied() -> None:
    project = _make_horizontal_cantilever()
    load_tag = project.self_weight_load_tag()
    project.combinations[1] = CombinationData(
        tag=1,
        name="ELU poids propre",
        combo_type="ULS",
        factors={load_tag: 1.35},
    )
    expected_total = total_self_weight_kn(project) * 1.35

    for engine in ("opensees", "pynite"):
        success, results = AnalysisRunner(project, engine=engine).run_static(
            combo_tag=1,
        )
        assert success is True
        reaction = results["reactions"][1]
        assert math.isclose(reaction.fz_reaction, expected_total, rel_tol=1e-9)
