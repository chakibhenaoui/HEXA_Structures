"""Helpers for test OpenSees builder."""

import pytest

from core.materials import (
    concrete_params,
    rebar_params,
    steel_params,
    DENSITIES,
)
from core.sections import (
    RectangularSection,
    TSection,
    get_profile,
    list_profiles,
)
from utils.units import convert, CM2, M2, CM4, M4


class TestMaterials:
    def test_concrete_c30_params(self):
        p = concrete_params(tag=1, grade="C30/37")
        # fpc must be negative (compression)
        assert p.fpc < 0
        # fcd = 30000/1.5 = 20000 → fpc ≈ -20000
        assert abs(p.fpc + 20_000) < 1
        # Negative strain at peak stress
        assert p.epsc0 < 0

    def test_concrete_confined(self):
        p_unconf = concrete_params(tag=1, grade="C30/37", confined=False)
        p_conf = concrete_params(tag=2, grade="C30/37", confined=True)
        # Confined concrete is stronger (in absolute value)
        assert abs(p_conf.fpc) > abs(p_unconf.fpc)

    def test_rebar_b500b(self):
        p = rebar_params(tag=1, grade="B500B")
        # fyd = 500000 / 1.15 ≈ 434783 kPa
        assert abs(p.fy - 500_000 / 1.15) < 1
        assert p.es == 200_000_000

    def test_steel_s355(self):
        p = steel_params(tag=1, grade="S355")
        assert p.fy == 355_000  # γM0 = 1.0
        assert p.es == 210_000_000
        assert p.b == 0.01  # default

    def test_densities(self):
        assert DENSITIES["concrete"] == 2500.0
        assert DENSITIES["steel"] == 7850.0


class TestRectangularSection:
    def test_area(self):
        s = RectangularSection(b=0.30, h=0.50)
        assert abs(s.area - 0.15) < 1e-10

    def test_inertia_y(self):
        s = RectangularSection(b=0.30, h=0.50)
        # Iy = bh³/12 = 0.30 * 0.50³ / 12 = 0.003125
        assert abs(s.inertia_y - 0.003125) < 1e-10

    def test_inertia_z(self):
        s = RectangularSection(b=0.30, h=0.50)
        # Iz = hb³/12 = 0.50 * 0.30³ / 12 = 0.001125
        assert abs(s.inertia_z - 0.001125) < 1e-10


class TestTSection:
    def test_area(self):
        t = TSection(bw=0.20, hw=0.40, bf=0.80, hf=0.15)
        expected = 0.20 * 0.40 + 0.80 * 0.15
        assert abs(t.area - expected) < 1e-10

    def test_height(self):
        t = TSection(bw=0.20, hw=0.40, bf=0.80, hf=0.15)
        assert abs(t.h - 0.55) < 1e-10

    def test_centroid_above_mid(self):
        """Test centroid above mid."""
        t = TSection(bw=0.20, hw=0.40, bf=0.80, hf=0.15)
        assert t.centroid_y > t.h / 2


class TestProfileCatalog:
    def test_ipe300_exists(self):
        p = get_profile("IPE 300")
        assert p.family == "IPE"
        assert abs(p.h - 0.300) < 1e-4

    def test_heb200_exists(self):
        p = get_profile("HEB 200")
        assert p.family == "HEB"

    def test_list_ipe(self):
        names = list_profiles("IPE")
        assert "IPE 200" in names
        assert "IPE 300" in names
        assert all("IPE" in n for n in names)

    def test_list_all(self):
        names = list_profiles()
        assert len(names) > 30  # IPE + HEA + HEB

    def test_unknown_profile_raises(self):
        with pytest.raises(KeyError):
            get_profile("XXX 999")

    def test_ipe300_area_reasonable(self):
        """Test ipe300 area reasonable."""
        p = get_profile("IPE 300")
        area_cm2 = convert(p.area, M2, CM2)
        assert abs(area_cm2 - 53.8) < 0.5

    def test_ipe300_inertia_reasonable(self):
        """Test ipe300 inertia reasonable."""
        p = get_profile("IPE 300")
        iy_cm4 = convert(p.inertia_y, M4, CM4)
        assert abs(iy_cm4 - 8360) < 10
