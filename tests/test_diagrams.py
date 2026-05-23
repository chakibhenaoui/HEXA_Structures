"""Helpers for test diagrams."""

import math

import numpy as np
import pytest
pytest.importorskip("matplotlib")

from core.analysis import AnalysisRunner
from core.model_data import CombinationData, ElementLoad, LoadData, ProjectModel
from core.results import ElementResult, interpolate_internal_forces
from core.section_force_convention import (
    PLANE_INDICES as _PLANE_INDICES,
    canonicalize_component_samples as _canonicalize_component_samples,
    choose_file_diagram_side as _choose_file_diagram_side,
    component_display_sign as _component_display_sign,
    display_component_values as _display_component_values,
)
from gui.widgets.diagram_renderer import (
    _format_diagram_value,
    _element_samples,
    _element_samples_from_backend,
    build_figure_2d,
    detect_files,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Utilitaires
# ═══════════════════════════════════════════════════════════════════════════

def assert_close(actual, expected, tol=0.01, msg=""):
    """Handle assert close."""
    if abs(expected) > 1e-6:
        err = abs(actual - expected) / abs(expected)
        assert err < tol, f"{msg}: {actual:.6f} ≠ {expected:.6f} (err={err:.2%})"
    else:
        assert abs(actual - expected) < tol, (
            f"{msg}: {actual:.6f} ≠ {expected:.6f} (abs)"
        )


def test_format_diagram_value_masks_numerical_noise() -> None:
    assert _format_diagram_value(4.52e-16) == "0"
    assert _format_diagram_value(-1.0e-14) == "0"
    assert _format_diagram_value(12.3456) == "+12.35"
    assert _format_diagram_value(-12.3456) == "-12.35"


# ═══════════════════════════════════════════════════════════════════════════
#  Case 1: cantilever beam — point load (engineering convention)
#
#  Beam fixed on the left (x=0), downward load P at x=L.
#  Use the "positive = upward" convention for Vz,
#  and the OpenSees convention for internal force signs.
#
#    Z ↑
#      |███  --------------● -> X      P = 10 kN downward
#      |encastrement       ↓P
#
#  Analytical solutions (positive Vz upward convention):
#    Vz(x) = -P = -10  (constant, points downward)
#    My(x) = -P*(L-x)  (negative = sagging/bottom tension in OpenSees convention)
#
#  But OpenSees eleForce returns the element NODAL forces,
#  not the internal forces directly. Here is the correspondence:
#
#  Node i (fixed):
#    forces[2] = Vz_nodal_i = -(reaction Fz) = -(+P) = -P = -10
#    → vz_i = forces[2] = -10
#    forces[4] = My_nodal_i = -(reaction My)
#    → my_i = forces[4]
#
#  Node j (free):
#    → vz_j = -forces[8]  (inversion signe convention RDM)
#    → my_j = -forces[10]
# ═══════════════════════════════════════════════════════════════════════════


class TestCantileverPointLoad:
    """Tests for cantilever point load."""

    P = 10.0   # kN (magnitude, downward)
    L = 5.0    # m

    def _make_result_engineering(self):
        """Create result engineering."""
        # Constant shear = -P (downward)
        vz_i = -self.P  # = -10
        vz_j = -self.P  # = -10

        # Moment: My(0) = -P*L = -50 (hogging at the fixed end)
        #          My(L) = 0
        my_i = -self.P * self.L  # = -50
        my_j = 0.0

        return ElementResult(
            tag=1,
            vz_i=vz_i, vz_j=vz_j,
            my_i=my_i, my_j=my_j,
        )

    def test_shear_constant(self):
        """Test shear constant."""
        r = self._make_result_engineering()
        result = interpolate_internal_forces(r, self.L, wz=0.0, n_points=21)

        for k, vz in enumerate(result["Vz"]):
            assert_close(vz, -self.P, msg=f"Vz[{k}]")

    def test_moment_linear(self):
        """Test moment linear."""
        r = self._make_result_engineering()
        result = interpolate_internal_forces(r, self.L, wz=0.0, n_points=21)

        for k, (x, my) in enumerate(zip(result["x"], result["My"])):
            expected = -self.P * (self.L - x)
            assert_close(my, expected, msg=f"My[{k}] x={x:.2f}")

    def test_moment_at_fixed_end(self):
        """My(0) = -P*L = -50 kN·m."""
        r = self._make_result_engineering()
        result = interpolate_internal_forces(r, self.L, wz=0.0, n_points=11)
        assert_close(result["My"][0], -50.0, msg="My(0)")

    def test_moment_at_free_end(self):
        """My(L) = 0."""
        r = self._make_result_engineering()
        result = interpolate_internal_forces(r, self.L, wz=0.0, n_points=11)
        assert_close(result["My"][-1], 0.0, tol=0.001, msg="My(L)")

    def test_no_lateral_effects(self):
        """Test no lateral effects."""
        r = self._make_result_engineering()
        result = interpolate_internal_forces(r, self.L, n_points=11)

        for vy in result["Vy"]:
            assert abs(vy) < 1e-10, f"Vy devrait être 0, obtenu {vy}"
        for mz in result["Mz"]:
            assert abs(mz) < 1e-10, f"Mz devrait être 0, obtenu {mz}"


# ═══════════════════════════════════════════════════════════════════════════
#  Case 2: simply supported beam — uniform distributed load
#
#    Z ↑
#      △------------------△ -> X     w = 10 kN/m downward
#      ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
#      x=0               x=L=6m
#
#  Reactions: R = wL/2 = 30 kN (upward)
#
#  Engineering convention (positive upward / sagging):
#    Vz(x) = wL/2 - w*x = 30 - 10x
#    My(x) = wLx/2 - wx²/2 = 30x - 5x²
#    My_max = wL^2/8 = 45 kN*m at x=L/2
#
#  For the Vz(x) = Vz_i - wz*x formula to work:
#    Vz_i = +30, wz = +10  (positive wz = downward in the formula)
# ═══════════════════════════════════════════════════════════════════════════


class TestSimplySupportedUniformLoad:
    """Tests for simply supported uniform load."""

    w = 10.0   # kN/m (magnitude, downward)
    L = 6.0    # m

    def _make_result(self, wz_sign=+1.0):
        """Create result."""
        # Engineering convention: Vz_i = +wL/2, My_i = 0
        vz_i = wz_sign * self.w * self.L / 2   # ±30
        vz_j = -wz_sign * self.w * self.L / 2  # ∓30
        my_i = 0.0
        my_j = 0.0

        return ElementResult(
            tag=1,
            vz_i=vz_i, vz_j=vz_j,
            my_i=my_i, my_j=my_j,
        )

    def test_shear_linear_positive_convention(self):
        """Test shear linear positive convention."""
        r = self._make_result(wz_sign=+1.0)
        result = interpolate_internal_forces(r, self.L, wz=+self.w, n_points=21)

        for x, vz in zip(result["x"], result["Vz"]):
            expected = self.w * self.L / 2 - self.w * x
            assert_close(vz, expected, msg=f"Vz(x={x:.2f})")

    def test_shear_zero_at_midspan(self):
        """Test shear zero at midspan."""
        r = self._make_result(wz_sign=+1.0)
        result = interpolate_internal_forces(r, self.L, wz=+self.w, n_points=21)

        mid_idx = len(result["x"]) // 2
        assert_close(result["Vz"][mid_idx], 0.0, tol=0.001, msg="Vz(L/2)")

    def test_moment_parabolic(self):
        """My(x) = wLx/2 - wx²/2 (parabolique, sagging positif)."""
        r = self._make_result(wz_sign=+1.0)
        result = interpolate_internal_forces(r, self.L, wz=+self.w, n_points=21)

        for x, my in zip(result["x"], result["My"]):
            expected = self.w * self.L * x / 2 - self.w * x**2 / 2
            assert_close(my, expected, msg=f"My(x={x:.2f})")

    def test_moment_max_at_midspan(self):
        """Test moment maximum at midspan."""
        r = self._make_result(wz_sign=+1.0)
        result = interpolate_internal_forces(r, self.L, wz=+self.w, n_points=21)

        mid_idx = len(result["x"]) // 2
        assert_close(result["My"][mid_idx], self.w * self.L**2 / 8,
                      msg="My_max")

    def test_moment_zero_at_supports(self):
        """Test moment zero at supports."""
        r = self._make_result(wz_sign=+1.0)
        result = interpolate_internal_forces(r, self.L, wz=+self.w, n_points=21)

        assert_close(result["My"][0], 0.0, tol=0.001, msg="My(0)")
        assert_close(result["My"][-1], 0.0, tol=0.001, msg="My(L)")

    def test_opensees_sign_convention(self):
        """Test OpenSees sign convention."""
        r = self._make_result(wz_sign=-1.0)
        result = interpolate_internal_forces(r, self.L, wz=-self.w, n_points=21)

        # Vz must be the negative of the engineering convention
        for x, vz in zip(result["x"], result["Vz"]):
            expected = -(self.w * self.L / 2 - self.w * x)
            assert_close(vz, expected, msg=f"Vz_ops(x={x:.2f})")

        # My must be negative too (negative sagging in OpenSees)
        mid_idx = len(result["x"]) // 2
        assert_close(result["My"][mid_idx], -self.w * self.L**2 / 8,
                      msg="My_max_opensees")


# ═══════════════════════════════════════════════════════════════════════════
#  Case 3: fixed-fixed beam — uniform distributed load
#
#    Z ↑
#    ███----------------███ -> X      w = 10 kN/m downward
#      ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
#      x=0             x=L=3m
#
#  Engineering convention (positive = upward / sagging):
#    Reactions: R = wL/2 = 15 kN
#    Moments: My(0) = My(L) = -wL^2/12 = -7.5 kN*m (hogging, negative)
#              My(L/2) = +wL^2/24 = +3.75 kN*m (sagging, positive)
#    Shear: Vz(0) = +15, Vz(L/2) = 0, Vz(L) = -15
# ═══════════════════════════════════════════════════════════════════════════


class TestFixedFixedUniformLoad:
    """Tests for fixed fixed uniform load."""

    w = 10.0   # kN/m
    L = 3.0    # m

    def _make_result(self):
        """Create result."""
        return ElementResult(
            tag=1,
            vz_i=self.w * self.L / 2,        # +15
            vz_j=-self.w * self.L / 2,        # -15
            my_i=-self.w * self.L**2 / 12,    # -7.5 (hogging)
            my_j=-self.w * self.L**2 / 12,    # -7.5 (hogging)
        )

    def test_shear_endpoints(self):
        """Vz(0) = +15, Vz(L) = -15."""
        r = self._make_result()
        result = interpolate_internal_forces(r, self.L, wz=self.w, n_points=11)

        assert_close(result["Vz"][0], +15.0, msg="Vz(0)")
        assert_close(result["Vz"][-1], -15.0, msg="Vz(L)")

    def test_shear_zero_midspan(self):
        """Vz(L/2) = 0."""
        r = self._make_result()
        result = interpolate_internal_forces(r, self.L, wz=self.w, n_points=11)

        mid = len(result["x"]) // 2
        assert_close(result["Vz"][mid], 0.0, tol=0.001, msg="Vz(L/2)")

    def test_moment_at_supports(self):
        """My(0) = My(L) = -wL²/12 = -7.5 kN·m (hogging)."""
        r = self._make_result()
        result = interpolate_internal_forces(r, self.L, wz=self.w, n_points=11)

        expected = -self.w * self.L**2 / 12
        assert_close(result["My"][0], expected, msg="My(0)")
        assert_close(result["My"][-1], expected, msg="My(L)")

    def test_moment_at_midspan(self):
        """My(L/2) = +wL²/24 = +3.75 kN·m (sagging)."""
        r = self._make_result()
        result = interpolate_internal_forces(r, self.L, wz=self.w, n_points=11)

        mid = len(result["x"]) // 2
        expected = self.w * self.L**2 / 24
        assert_close(result["My"][mid], expected, msg="My(L/2)")

    def test_interpolated_my_equals_endpoint(self):
        """Test interpolated my equals endpoint."""
        r = self._make_result()
        result = interpolate_internal_forces(r, self.L, wz=self.w, n_points=21)

        # My computed by the formula at x=L
        my_L = result["My"][-1]
        # Must be = my_j = -7.5
        assert_close(my_L, r.my_j, tol=0.001,
                      msg="My(L) vs my_j")


# ═══════════════════════════════════════════════════════════════════════════
#  Case 4: OpenSees convention / formula convention consistency
#
#  OpenSees with vecxz=(0,0,1): local_z = Z (upward).
#  For a -10 kN/m gravity load:
#    ops.eleLoad(..., "-beamUniform", 0, -10, 0)  → Wz = -10
#    eleForce: forces[2] = -wL/2 (= -15 for L=3)
#    ResultsExtractor : vz_i = forces[2] = -15
#
#  La formule : Vz(x) = vz_i - wz*x = -15 - (-10)*x = -15 + 10x
#    Vz(0) = -15, Vz(1.5) = 0, Vz(3) = +15
#
#  This is the MIRROR of the engineering convention (inverted signs).
#  Physically: Vz<0 = downward internal force = upward reaction
#  at the supports, which is correct (the reaction pushes the node upward).
# ═══════════════════════════════════════════════════════════════════════════


class TestOpenSeesSignConvention:
    """Tests for OpenSees sign convention."""

    w = 10.0   # kN/m
    L = 3.0    # m

    def _make_result_opensees(self):
        """Create result OpenSees."""
        # eleForce at node i : Vz = -wL/2 (element pushes node down)
        vz_i = -self.w * self.L / 2   # = -15
        # eleForce at node j after sign flip: vz_j = -(-forces[8])
        # For symmetric fixed-fixed beam: vz_j = +15
        vz_j = +self.w * self.L / 2   # = +15

        # My at encastrement (OpenSees convention)
        # Hogging → positive My (tension on +Z side = top)
        my_i = +self.w * self.L**2 / 12   # = +7.5
        my_j = +self.w * self.L**2 / 12   # = +7.5

        return ElementResult(
            tag=1,
            vz_i=vz_i, vz_j=vz_j,
            my_i=my_i, my_j=my_j,
        )

    def test_shear_opensees(self):
        """Test shear OpenSees."""
        r = self._make_result_opensees()
        result = interpolate_internal_forces(r, self.L, wz=-self.w, n_points=11)

        # Vz(0) = -15 (negative = downward force on the node)
        assert_close(result["Vz"][0], -15.0, msg="Vz(0)")
        # Vz(L/2) = 0
        mid = len(result["x"]) // 2
        assert_close(result["Vz"][mid], 0.0, tol=0.001, msg="Vz(L/2)")
        # Vz(L) = +15
        assert_close(result["Vz"][-1], +15.0, msg="Vz(L)")

    def test_moment_opensees(self):
        """My avec convention OpenSees."""
        r = self._make_result_opensees()
        result = interpolate_internal_forces(r, self.L, wz=-self.w, n_points=11)

        # My(0) = +7.5 (hogging, positive in OpenSees)
        assert_close(result["My"][0], +7.5, msg="My(0)")

        # My(L/2) = negative (sagging in OpenSees)
        mid = len(result["x"]) // 2
        assert_close(result["My"][mid], -self.w * self.L**2 / 24,
                      msg="My(L/2)")

        # My(L) = +7.5 (symmetric hogging)
        assert_close(result["My"][-1], +7.5, msg="My(L)")

    def test_consistency_magnitude(self):
        """Test consistency magnitude."""
        # Engineering convention
        r_eng = ElementResult(
            tag=1,
            vz_i=+15.0, vz_j=-15.0,
            my_i=-7.5, my_j=-7.5,
        )
        res_eng = interpolate_internal_forces(r_eng, self.L, wz=+self.w, n_points=11)

        # Convention OpenSees
        r_ops = self._make_result_opensees()
        res_ops = interpolate_internal_forces(r_ops, self.L, wz=-self.w, n_points=11)

        # Identical magnitudes at each point
        for k in range(len(res_eng["x"])):
            assert_close(abs(res_eng["Vz"][k]), abs(res_ops["Vz"][k]),
                          msg=f"|Vz|[{k}]")
            assert_close(abs(res_eng["My"][k]), abs(res_ops["My"][k]),
                          msg=f"|My|[{k}]")


# ═══════════════════════════════════════════════════════════════════════════
#  Case 5: diagram_renderer pipeline check
#
#  diagram_renderer reads el.wz and passes it directly to
#  interpolate_internal_forces. Check that this is consistent
#  with OpenSees results.
# ═══════════════════════════════════════════════════════════════════════════


class TestDiagramPipeline:
    """Simule le pipeline complet diagram_renderer."""

    w = 10.0   # kN/m
    L = 6.0    # m

    def test_ss_beam_pipeline(self):
        """Test ss beam pipeline."""
        # OpenSees results (OpenSees convention)
        r = ElementResult(
            tag=1,
            vz_i=-self.w * self.L / 2,   # -30
            vz_j=+self.w * self.L / 2,    # +30
            my_i=0.0,
            my_j=0.0,
        )

        # Le diagram_renderer lit wz = el.wz = -10
        wz_global = -self.w  # = -10

        result = interpolate_internal_forces(r, self.L, wz=wz_global, n_points=21)

        # Check the diagram shape (magnitudes)
        mid = len(result["x"]) // 2

        # Shear: zero at midspan
        assert abs(result["Vz"][mid]) < 0.01, "Vz(L/2) ≠ 0"

        # Moment: maximum absolute value at midspan
        my_mid = result["My"][mid]
        my_expected = -self.w * self.L**2 / 8  # = -45 (negative sagging in OpenSees)
        assert_close(my_mid, my_expected, msg="My(L/2) pipeline")

        # Support moments = 0
        assert abs(result["My"][0]) < 0.01, "My(0) ≠ 0"
        assert abs(result["My"][-1]) < 0.01, "My(L) ≠ 0"

    def test_diagram_wz_sign_sensitivity(self):
        """Test diagram wz sign sensitivity."""
        # OpenSees results
        r = ElementResult(
            tag=1,
            vz_i=-30.0, vz_j=+30.0,
            my_i=0.0, my_j=0.0,
        )

        # CORRECT : wz = -10 (global)
        res_ok = interpolate_internal_forces(r, self.L, wz=-self.w, n_points=11)
        # WRONG: wz = +10 (inverted sign)
        res_bad = interpolate_internal_forces(r, self.L, wz=+self.w, n_points=11)

        mid = len(res_ok["x"]) // 2

        # The correct version has Vz=0 at midspan
        assert abs(res_ok["Vz"][mid]) < 0.01, "Vz correct au milieu"

        # The wrong version has Vz != 0 at midspan
        assert abs(res_bad["Vz"][mid]) > 1.0, (
            "Avec le mauvais signe, Vz n'est PAS zéro au milieu"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  Case 6: cantilever with distributed load (parabolic My)
#
#    Z ↑
#    ███-------------● -> X      w = 5 kN/m downward
#      ↓↓↓↓↓↓↓↓↓↓↓↓↓
#      x=0           x=L=4m
#
#  Engineering convention:
#    Vz(x) = w*(L-x)           → Vz(0)=20, Vz(L)=0
#    My(x) = -w*(L-x)²/2       → My(0)=-40, My(L)=0
# ═══════════════════════════════════════════════════════════════════════════


class TestCantileverUniformLoad:
    """Tests for cantilever uniform load."""

    w = 5.0
    L = 4.0

    def _make_result(self):
        """Create result."""
        return ElementResult(
            tag=1,
            vz_i=self.w * self.L,              # +20
            vz_j=0.0,
            my_i=-self.w * self.L**2 / 2,      # -40
            my_j=0.0,
        )

    def test_shear_linear(self):
        """Test shear linear."""
        r = self._make_result()
        result = interpolate_internal_forces(r, self.L, wz=self.w, n_points=21)

        for x, vz in zip(result["x"], result["Vz"]):
            expected = self.w * (self.L - x)
            assert_close(vz, expected, msg=f"Vz(x={x:.2f})")

    def test_moment_parabolic(self):
        """My(x) = -w*(L-x)²/2, parabolique."""
        r = self._make_result()
        result = interpolate_internal_forces(r, self.L, wz=self.w, n_points=21)

        for x, my in zip(result["x"], result["My"]):
            expected = -self.w * (self.L - x)**2 / 2
            assert_close(my, expected, msg=f"My(x={x:.2f})")


# ═══════════════════════════════════════════════════════════════════════════
#  Case 7: axial force (compression/tension)
# ═══════════════════════════════════════════════════════════════════════════


class TestNormalForce:
    """Effort normal constant (poteau ou tirant)."""

    def test_compression_constant(self):
        """N constant = -100 kN (compression)."""
        r = ElementResult(tag=1, n_i=-100.0, n_j=-100.0)
        result = interpolate_internal_forces(r, length=3.0, n_points=11)

        for n in result["N"]:
            assert_close(n, -100.0, msg="N")

    def test_traction_constant(self):
        """N constant = +50 kN (traction)."""
        r = ElementResult(tag=1, n_i=+50.0, n_j=+50.0)
        result = interpolate_internal_forces(r, length=5.0, n_points=11)

        for n in result["N"]:
            assert_close(n, +50.0, msg="N")

    def test_normal_with_axial_load(self):
        """Test normal with axial load."""
        r = ElementResult(tag=1, n_i=-100.0, n_j=-80.0)
        # wx = 4 kN/m (axial load over L=5m: Delta N = wx*L = 20)
        result = interpolate_internal_forces(r, length=5.0, wx=4.0, n_points=11)

        # N(x) = N_i - wx*x = -100 - 4x
        for x, n in zip(result["x"], result["N"]):
            expected = -100.0 - 4.0 * x
            assert_close(n, expected, msg=f"N(x={x:.2f})")


# ═══════════════════════════════════════════════════════════════════════════
#  Case 8: Vy/Mz cross-check (horizontal plane)
# ═══════════════════════════════════════════════════════════════════════════


class TestLateralBending:
    """Tests for lateral bending."""

    def test_lateral_ss_beam(self):
        """Test lateral ss beam."""
        L = 5.0
        w = 8.0

        r = ElementResult(
            tag=1,
            vy_i=w * L / 2,     # +20
            vy_j=-w * L / 2,    # -20
            mz_i=0.0,
            mz_j=0.0,
        )
        result = interpolate_internal_forces(r, L, wy=w, n_points=21)

        # Mz_max = wL²/8 = 25 kN·m
        mid = len(result["x"]) // 2
        assert_close(result["Mz"][mid], w * L**2 / 8, msg="Mz_max")

        # Vy = 0 at midspan
        assert abs(result["Vy"][mid]) < 0.01, "Vy(L/2)"


# ═══════════════════════════════════════════════════════════════════════════
#  Case 9: zero results with no load
# ═══════════════════════════════════════════════════════════════════════════


class TestNoLoad:
    """Tests for no load."""

    def test_all_zero(self):
        r = ElementResult(tag=1)
        result = interpolate_internal_forces(r, length=5.0, n_points=11)

        for comp in ["N", "Vy", "Vz", "T", "My", "Mz"]:
            for val in result[comp]:
                assert abs(val) < 1e-12, f"{comp} non nul : {val}"


def _make_portal_project() -> ProjectModel:
    project = ProjectModel(name="Diagram portal")
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(0.0, 0.0, 3.0)
    project.add_node(5.0, 0.0, 3.0)
    project.add_node(5.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))

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
    project.add_element(2, 3, section_tag=1)
    project.add_element(3, 4, section_tag=1)

    project.loads[1] = LoadData(tag=1, name="G", load_type="dead")
    project.combinations[1] = CombinationData(
        tag=1,
        name="ELU",
        combo_type="ULS",
        factors={1: 1.35},
    )
    project.element_loads.append(
        ElementLoad(load_tag=1, element_tag=2, wz=-10.0),
    )
    return project


def _make_yz_portal_project() -> ProjectModel:
    project = ProjectModel(name="Diagram portal YZ")
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(0.0, 0.0, 3.0)
    project.add_node(0.0, 5.0, 3.0)
    project.add_node(0.0, 5.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))

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
    project.add_element(2, 3, section_tag=1)
    project.add_element(3, 4, section_tag=1)

    project.loads[1] = LoadData(tag=1, name="G", load_type="dead")
    project.element_loads.append(
        ElementLoad(
            load_tag=1,
            element_tag=2,
            wz=-10.0,
            coordinate_system="global",
        ),
    )
    return project


def _make_xy_only_project() -> ProjectModel:
    project = ProjectModel(name="Diagram XY only")
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)

    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "IPE 240",
        "I_profile",
        material_tag=1,
        area=39.1e-4,
        inertia_y=3892e-8,
        inertia_z=324e-8,
    )

    project.add_element(1, 2, section_tag=1)
    project.add_element(2, 3, section_tag=1)
    return project


def _make_spatial_frame_project() -> ProjectModel:
    project = ProjectModel(name="Diagram spatial frame")
    for x in (0.0, 5.0):
        for y in (0.0, 4.0):
            project.add_node(x, y, 0.0, fixities=(1, 1, 1, 1, 1, 1))
            project.add_node(x, y, 3.0)
            project.add_node(x, y, 6.0)

    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "IPE 300",
        "I_profile",
        material_tag=1,
        area=53.8e-4,
        inertia_y=8360e-8,
        inertia_z=603e-8,
    )

    # Columns
    for base in (1, 4, 7, 10):
        project.add_element(base, base + 1, section_tag=1)
        project.add_element(base + 1, base + 2, section_tag=1)

    # Beams along X on both levels, Y = constant planes -> XZ
    project.add_element(2, 8, section_tag=1)
    project.add_element(5, 11, section_tag=1)
    project.add_element(3, 9, section_tag=1)
    project.add_element(6, 12, section_tag=1)

    # Beams along Y on both levels, X = constant planes -> YZ
    project.add_element(2, 5, section_tag=1)
    project.add_element(8, 11, section_tag=1)
    project.add_element(3, 6, section_tag=1)
    project.add_element(9, 12, section_tag=1)
    return project


def _displayed_my_samples_from_opensees(project: ProjectModel, element_tag: int) -> list[float]:
    arr = np.array([(node.x, node.z) for node in project.nodes.values()])
    file_center = arr.mean(axis=0)
    ecrd_3d, xl, ss, _ = _element_samples(element_tag, "My", 5)
    i1, i2 = _PLANE_INDICES["XZ"]
    p1 = np.array([ecrd_3d[0, i1], ecrd_3d[0, i2]])
    p2 = np.array([ecrd_3d[1, i1], ecrd_3d[1, i2]])
    p1, p2, xl, ss, canonical_axes = _canonicalize_component_samples(
        ecrd_3d,
        p1,
        p2,
        xl,
        ss,
        "My",
        apply_component_axis_sign=False,
    )
    normal = _choose_file_diagram_side(p1, p2, file_center, 1e-9)
    tangent = (p2 - p1) / float(np.linalg.norm(p2 - p1))
    local_x, local_y, local_z = canonical_axes
    display_sign = _component_display_sign(
        "My", "XZ", local_x, local_y, local_z, tangent, normal
    )
    displayed = _display_component_values("My", ss * display_sign)
    return [float(v) for v in displayed]


def _displayed_my_samples_from_pynite_backend(
    project: ProjectModel,
    backend,
    element_tag: int,
) -> list[float]:
    arr = np.array([(node.x, node.z) for node in project.nodes.values()])
    file_center = arr.mean(axis=0)
    ecrd_3d, xl, ss, _ = _element_samples_from_backend(
        project,
        backend,
        element_tag,
        "My",
        5,
    )
    i1, i2 = _PLANE_INDICES["XZ"]
    p1 = np.array([ecrd_3d[0, i1], ecrd_3d[0, i2]])
    p2 = np.array([ecrd_3d[1, i1], ecrd_3d[1, i2]])
    p1, p2, xl, ss, canonical_axes = _canonicalize_component_samples(
        ecrd_3d,
        p1,
        p2,
        xl,
        ss,
        "My",
        apply_component_axis_sign=False,
    )
    normal = _choose_file_diagram_side(p1, p2, file_center, 1e-9)
    tangent = (p2 - p1) / float(np.linalg.norm(p2 - p1))
    local_x, local_y, local_z = canonical_axes
    display_sign = _component_display_sign(
        "My", "XZ", local_x, local_y, local_z, tangent, normal
    )
    displayed = _display_component_values("My", ss * display_sign)
    return [float(v) for v in displayed]


def test_detect_files_uses_project_geometry_for_planar_portal() -> None:
    project = _make_portal_project()

    files = detect_files(project=project)

    assert len(files) == 1
    assert files[0]["plane"] == "XZ"
    assert files[0]["ele_tags"] == [1, 2, 3]
    assert "plan XZ" in files[0]["label"]


def test_detect_files_filters_out_xy_only_models() -> None:
    project = _make_xy_only_project()

    files = detect_files(project=project)

    assert files == []


def test_detect_files_keeps_only_vertical_frame_planes_for_spatial_model() -> None:
    project = _make_spatial_frame_project()

    files = detect_files(project=project)

    assert files
    assert all(file_info["plane"] in {"XZ", "YZ"} for file_info in files)
    assert all(file_info["plane"] != "XY" for file_info in files)


@pytest.mark.parametrize("engine", ["pynite", "opensees"])
@pytest.mark.parametrize(
    ("load_tag", "combo_tag", "case_label"),
    [(1, None, "G"), (None, 1, "ELU")],
)
def test_build_figure_2d_from_results_supports_all_engines(
    engine: str,
    load_tag: int | None,
    combo_tag: int | None,
    case_label: str,
) -> None:
    project = _make_portal_project()
    runner = AnalysisRunner(project, engine=engine)

    success, results = runner.run_static(load_tag=load_tag, combo_tag=combo_tag)

    assert success is True
    file_info = detect_files(project=project)[0]
    backend = runner.backend if engine == "pynite" else None
    fig = build_figure_2d(
        "My",
        file_info,
        project=project,
        backend=backend,
        results=results,
        load_tag=load_tag,
        combo_tag=combo_tag,
    )
    ax = fig.axes[0]

    assert "Moment de flexion My" in ax.get_title()
    assert "plan XZ" in ax.get_title()
    assert ax.get_xlabel() == "X (m)"
    assert ax.get_ylabel() == "Z (m)"
    assert len(ax.lines) > 10
    assert len(ax.collections) >= 2
    assert case_label in {"G", "ELU"}


def test_yz_file_my_samples_column_in_plane_moment_component() -> None:
    project = _make_yz_portal_project()

    success, results = AnalysisRunner(project, engine="opensees").run_static(load_tag=1)

    assert success is True
    column_my_for_file = _element_samples(1, "My", 5, plane="YZ")
    column_mz_raw = _element_samples(1, "Mz", 5)
    beam_my_for_file = _element_samples(2, "My", 5, plane="YZ")
    beam_my_raw = _element_samples(2, "My", 5)

    assert column_my_for_file is not None
    assert column_mz_raw is not None
    assert beam_my_for_file is not None
    assert beam_my_raw is not None
    assert np.max(np.abs(column_my_for_file[2])) > 1e-6
    assert np.allclose(column_my_for_file[2], column_mz_raw[2])
    assert np.allclose(beam_my_for_file[2], beam_my_raw[2])

    file_info = detect_files(project=project)[0]
    fig = build_figure_2d(
        "My",
        file_info,
        project=project,
        results=results,
        load_tag=1,
    )
    assert "Moment de flexion dans le plan" in fig.axes[0].get_title()


def test_single_element_local_diagram_uses_member_length_not_global_projection() -> None:
    project = ProjectModel(name="Local member diagram")
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(3.0, 4.0, 12.0)
    project.add_material("Acier S355", "steel", "S355")
    project.add_section(
        "IPE 300",
        "I_profile",
        material_tag=1,
        area=53.8e-4,
        inertia_y=8360e-8,
        inertia_z=603e-8,
    )
    element = project.add_element(1, 2, section_tag=1)
    results = {
        "element_forces": {
            element.tag: ElementResult(tag=element.tag, my_i=10.0, my_j=20.0),
        },
    }
    file_info = {
        "label": "E1 seul (repere local)",
        "local_element": True,
        "element_tag": element.tag,
        "ele_tags": [element.tag],
        "plane": None,
    }

    fig = build_figure_2d("My", file_info, project=project, results=results)
    ax = fig.axes[0]
    axis_line = ax.lines[0]

    assert ax.get_xlabel() == "x local (m)"
    assert ax.get_ylabel() == "My local (kN.m)"
    assert "plan local x-z" in ax.get_title()
    assert math.isclose(float(axis_line.get_xdata()[0]), 0.0, abs_tol=1e-9)
    assert math.isclose(float(axis_line.get_xdata()[1]), 13.0, rel_tol=1e-9)


def test_engine_agnostic_diagram_renderer_gives_same_canvas_structure() -> None:
    project = _make_portal_project()
    file_info = detect_files(project=project)[0]

    success_ops, results_ops = AnalysisRunner(project, engine="opensees").run_static(combo_tag=1)
    pyn_runner = AnalysisRunner(project, engine="pynite")
    success_pyn, results_pyn = pyn_runner.run_static(combo_tag=1)

    assert success_ops is True
    assert success_pyn is True

    fig_ops = build_figure_2d(
        "My",
        file_info,
        project=project,
        results=results_ops,
        combo_tag=1,
    )
    fig_pyn = build_figure_2d(
        "My",
        file_info,
        project=project,
        backend=pyn_runner.backend,
        results=results_pyn,
        combo_tag=1,
    )
    ax_ops = fig_ops.axes[0]
    ax_pyn = fig_pyn.axes[0]

    assert ax_ops.get_title() == ax_pyn.get_title()
    assert abs(len(ax_ops.lines) - len(ax_pyn.lines)) <= 2
    assert len(ax_ops.collections) == len(ax_pyn.collections)


def test_pynite_backend_my_display_matches_opensees_reference_on_portal() -> None:
    project = _make_portal_project()

    ops_runner = AnalysisRunner(project, engine="opensees")
    success_ops, _ = ops_runner.run_static(load_tag=1)
    pyn_runner = AnalysisRunner(project, engine="pynite")
    success_pyn, _ = pyn_runner.run_static(load_tag=1)

    assert success_ops is True
    assert success_pyn is True

    for element_tag in (1, 2, 3):
        expected = _displayed_my_samples_from_opensees(project, element_tag)
        actual = _displayed_my_samples_from_pynite_backend(
            project,
            pyn_runner.backend,
            element_tag,
        )
        for got, want in zip(actual, expected):
            assert math.isclose(got, want, rel_tol=1e-6, abs_tol=1e-6)
