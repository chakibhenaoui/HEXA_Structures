"""Helpers for test analysis."""
import importlib.util

import pytest

from core.model_data import LoadData, NodalLoad, ProjectModel, SurfaceLoad

from core.analysis import AnalysisRunner

HAS_OPENSEES = importlib.util.find_spec("openseespy") is not None

pytestmark = pytest.mark.skipif(
    not HAS_OPENSEES,
    reason="OpenSeesPy non disponible sur cette plateforme",
)


def _make_cantilever() -> ProjectModel:
    """Create cantilever."""
    p = ProjectModel(name="Console test")

    # Nodes (6-DOF fixities)
    p.add_node(0, 0, 0, fixities=(1, 1, 1, 1, 1, 1))  # encastrement
    p.add_node(5, 0, 0)  # free end

    # Material
    p.add_material("Acier S355", "steel", "S355")

    # IPE 300 section
    p.add_section(
        "IPE 300", "I_profile", material_tag=1,
        area=53.8e-4,         # 53.8 cm² → m²
        inertia_y=8360e-8,    # 8360 cm⁴ → m⁴
    )

    # Element
    p.add_element(1, 2, section_tag=1)

    # Load case
    p.loads[1] = LoadData(tag=1, name="Charge ponctuelle", load_type="dead")
    p.nodal_loads.append(NodalLoad(load_tag=1, node_tag=2, fy=-10.0))

    return p


def _make_shell_patch() -> ProjectModel:
    """Create shell patch."""
    p = ProjectModel(name="Dalle shell test")

    node_tag = 1
    for y in (0.0, 1.0, 2.0):
        for x in (0.0, 1.0, 2.0):
            is_boundary = x in (0.0, 2.0) or y in (0.0, 2.0)
            fixities = (1, 1, 1, 1, 1, 1) if is_boundary else (0, 0, 0, 0, 0, 0)
            p.add_node(x, y, 0.0, fixities=fixities)
            node_tag += 1

    p.add_material("Béton C30", "concrete", "C30/37")
    p.add_section(
        "Dalle 20 cm",
        "surface",
        material_tag=1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )

    p.add_surface_element((1, 2, 5, 4), section_tag=1)
    p.add_surface_element((2, 3, 6, 5), section_tag=1)
    p.add_surface_element((4, 5, 8, 7), section_tag=1)
    p.add_surface_element((5, 6, 9, 8), section_tag=1)

    p.loads[1] = LoadData(tag=1, name="Charge nodale dalle", load_type="live")
    p.nodal_loads.append(NodalLoad(load_tag=1, node_tag=5, fz=-10.0))
    p.loads[2] = LoadData(tag=2, name="Charge surfacique dalle", load_type="live")
    for surface_tag in p.surface_elements:
        p.surface_loads.append(SurfaceLoad(load_tag=2, surface_tag=surface_tag, qz=-5.0))
    return p


class TestStaticAnalysis:
    def test_cantilever_convergence(self):
        """Test cantilever convergence."""
        p = _make_cantilever()
        runner = AnalysisRunner(p)
        success, results = runner.run_static(load_tag=1)
        assert success is True
        assert "displacements" in results

    def test_cantilever_displacement(self):
        """Test cantilever displacement."""
        p = _make_cantilever()
        runner = AnalysisRunner(p)
        success, results = runner.run_static(load_tag=1)
        assert success

        # Theoretical deflection
        P = 10.0      # kN
        L = 5.0        # m
        E = 210_000_000  # kPa
        inertia = 8360e-8     # m⁴
        delta_th = P * L**3 / (3 * E * inertia)

        # OpenSees deflection (node 2, uy)
        disp = results["displacements"]
        uy = abs(disp[2].uy)

        # 1% tolerance
        assert abs(uy - delta_th) / delta_th < 0.01

    def test_cantilever_reactions(self):
        """Test cantilever reactions."""
        p = _make_cantilever()
        runner = AnalysisRunner(p)
        success, results = runner.run_static(load_tag=1)
        assert success

        reactions = results["reactions"]
        # Vertical reaction = +10 kN (opposite to the load)
        fy = reactions[1].fy_reaction
        assert abs(fy - 10.0) < 0.01

        # Reaction moment = P * L = 10 * 5 = 50 kN*m
        mz = reactions[1].mz_reaction
        assert abs(abs(mz) - 50.0) < 0.1

    def test_cantilever_element_forces(self):
        """Test cantilever element forces."""
        p = _make_cantilever()
        runner = AnalysisRunner(p)
        success, results = runner.run_static(load_tag=1)
        assert success

        forces = results["element_forces"]
        elem = forces[1]
        # Shear force = P = 10 kN (through v_i compatibility property)
        assert abs(abs(elem.v_i) - 10.0) < 0.1

    def test_no_load_fails(self):
        """Test no load fails."""
        p = _make_cantilever()
        runner = AnalysisRunner(p)
        success, results = runner.run_static()
        assert success is False

    def test_shell_patch_convergence_and_reaction_balance(self):
        """Test shell patch convergence and reaction balance."""
        p = _make_shell_patch()
        runner = AnalysisRunner(p, engine="opensees")
        success, results = runner.run_static(load_tag=1)
        assert success is True

        disp = results["displacements"]
        assert disp[5].uz < 0.0

        total_fz = sum(result.fz_reaction for result in results["reactions"].values())
        assert abs(total_fz - 10.0) < 0.05

    def test_shell_patch_uniform_surface_load_reaction_balance(self):
        """Test shell patch uniform surface load reaction balance."""
        p = _make_shell_patch()
        runner = AnalysisRunner(p, engine="opensees")
        success, results = runner.run_static(load_tag=2)
        assert success is True

        disp = results["displacements"]
        assert disp[5].uz < 0.0

        total_fz = sum(result.fz_reaction for result in results["reactions"].values())
        assert abs(total_fz - 20.0) < 0.05

    def test_shell_patch_surface_results_are_extracted(self):
        """Test shell patch surface results are extracted."""
        p = _make_shell_patch()
        runner = AnalysisRunner(p, engine="opensees")
        success, results = runner.run_static(load_tag=2)
        assert success is True

        surface_results = results["surface_results"]
        assert set(surface_results) == {1, 2, 3, 4}
        assert results["result_context"]["surface_results_available"] is True
        assert all(len(result.gauss_resultants) == 4 for result in surface_results.values())

        components = (
            "nxx",
            "nyy",
            "nxy",
            "mxx",
            "myy",
            "mxy",
            "qx",
            "qy",
        )
        assert any(
            abs(getattr(result, component)) > 1e-8
            for result in surface_results.values()
            for component in components
        )


def _make_simple_beam() -> ProjectModel:
    """Create simple beam."""
    p = ProjectModel(name="Poutre simple")

    # Rotule 3D + blocages hors plan
    p.add_node(0, 0, 0, fixities=(1, 1, 1, 1, 1, 0))  # tout sauf Rz
    p.add_node(6, 0, 0, fixities=(0, 1, 1, 1, 1, 0))   # free in X and Rz

    p.add_material("Acier S355", "steel", "S355")
    p.add_section(
        "IPE 300", "I_profile", material_tag=1,
        area=53.8e-4, inertia_y=8360e-8,
    )
    p.add_element(1, 2, section_tag=1)

    return p


class TestSimpleBeam:
    def test_simple_beam_symmetry(self):
        """Test simple beam symmetry."""
        p = _make_simple_beam()

        p.loads[1] = LoadData(tag=1, name="PP", load_type="dead")
        p.nodal_loads.append(NodalLoad(load_tag=1, node_tag=1, fy=-5.0))
        p.nodal_loads.append(NodalLoad(load_tag=1, node_tag=2, fy=-5.0))

        runner = AnalysisRunner(p)
        success, results = runner.run_static(load_tag=1)
        assert success

        reactions = results["reactions"]
        fy1 = reactions[1].fy_reaction
        fy2 = reactions[2].fy_reaction
        assert abs(fy1 - fy2) < 0.01


class TestModalAnalysis:
    def test_modal_cantilever(self):
        """Test modal cantilever."""
        import openseespy.opensees as ops

        # Manually build a modal model with masses
        ops.wipe()
        ops.model("basic", "-ndm", 2, "-ndf", 3)

        # 4 nodes: fixed + 3 free
        ops.node(1, 0, 0)
        ops.node(2, 2, 0)
        ops.node(3, 4, 0)
        ops.node(4, 6, 0)
        ops.fix(1, 1, 1, 1)

        # Masses at free nodes
        mass = 1.0  # tonne
        ops.mass(2, mass, mass, 0.0)
        ops.mass(3, mass, mass, 0.0)
        ops.mass(4, mass, mass, 0.0)

        # Elements
        ops.geomTransf("Linear", 1)
        E = 210_000_000  # kPa
        A = 53.8e-4
        inertia = 8360e-8
        ops.element("elasticBeamColumn", 1, 1, 2, A, E, inertia, 1)
        ops.element("elasticBeamColumn", 2, 2, 3, A, E, inertia, 1)
        ops.element("elasticBeamColumn", 3, 3, 4, A, E, inertia, 1)

        eigenvalues = ops.eigen(2)
        assert len(eigenvalues) == 2
        assert all(ev > 0 for ev in eigenvalues)


class TestRunnerCapabilities:
    def test_opensees_runner_reports_diagram_support(self):
        p = _make_cantilever()
        runner = AnalysisRunner(p, engine="opensees")

        assert runner.supports_diagrams is True

    def test_pynite_runner_reports_diagram_support(self):
        p = _make_cantilever()
        runner = AnalysisRunner(p, engine="pynite")

        assert runner.supports_diagrams is True
