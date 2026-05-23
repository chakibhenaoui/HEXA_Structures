"""Helpers for test eurocodes."""



from config.eurocodes import (
    CONCRETE_GRADES,
    REBAR_GRADES,
    STEEL_GRADES,
    PSI_COEFFICIENTS,
    GAMMA_G_SUP,
    GAMMA_Q,
    SNOW_SK0,
    snow_load_sk,
    wind_qb,
    SEISMIC_AGR,
    IMPORTANCE_FACTOR,
    elastic_spectrum,
    design_spectrum,
    damping_correction,
)


class TestEC0:
    def test_gamma_coefficients(self):
        assert GAMMA_G_SUP == 1.35
        assert GAMMA_Q == 1.50

    def test_psi_habitation(self):
        psi = PSI_COEFFICIENTS["A"]
        assert psi == (0.7, 0.5, 0.3)

    def test_psi_wind(self):
        psi = PSI_COEFFICIENTS["wind"]
        assert psi == (0.6, 0.2, 0.0)


class TestEC1:
    def test_snow_zone_a1(self):
        assert SNOW_SK0["A1"] == 0.45

    def test_snow_load_low_altitude(self):
        sk = snow_load_sk("A1", 100)
        assert sk == 0.45  # no increase below 200 m

    def test_snow_load_high_altitude(self):
        sk = snow_load_sk("A1", 700)
        assert sk > 0.45  # increased

    def test_wind_qb_zone1(self):
        qb = wind_qb(1)
        # qb = 0.5 * 1.225 * 22² / 1000
        expected = 0.5 * 1.225 * 22**2 / 1000
        assert abs(qb - expected) < 1e-6


class TestEC2:
    def test_c30_fck(self):
        c30 = CONCRETE_GRADES["C30/37"]
        assert c30.fck == 30_000  # kPa

    def test_c30_fcd(self):
        c30 = CONCRETE_GRADES["C30/37"]
        # fcd = 1.0 * 30000 / 1.5 = 20000
        assert abs(c30.fcd - 20_000) < 1

    def test_c25_fctm(self):
        c25 = CONCRETE_GRADES["C25/30"]
        assert c25.fctm == 2_600

    def test_rebar_b500b(self):
        b500 = REBAR_GRADES["B500B"]
        assert b500.fyk == 500_000
        # fyd = 500000 / 1.15
        assert abs(b500.fyd - 500_000 / 1.15) < 1


class TestEC3:
    def test_s355_fy(self):
        s355 = STEEL_GRADES["S355"]
        assert s355.fy == 355_000

    def test_s355_fyd(self):
        s355 = STEEL_GRADES["S355"]
        # γM0 = 1.0 → fyd = fy
        assert s355.fyd == 355_000

    def test_s235_modulus(self):
        s235 = STEEL_GRADES["S235"]
        assert s235.es == 210_000_000  # 210 GPa en kPa


class TestEC8:
    def test_seismic_zones(self):
        assert SEISMIC_AGR[1] == 0.4
        assert SEISMIC_AGR[5] == 3.0

    def test_importance_factors(self):
        assert IMPORTANCE_FACTOR[2] == 1.0
        assert IMPORTANCE_FACTOR[4] == 1.4

    def test_damping_correction_5pct(self):
        eta = damping_correction(5.0)
        assert abs(eta - 1.0) < 1e-6

    def test_damping_correction_minimum(self):
        # Very high damping -> eta minimum 0.55
        eta = damping_correction(100.0)
        assert eta >= 0.55

    def test_elastic_spectrum_plateau(self):
        """Check the elastic spectrum plateau ordinate."""
        # Zone 3, importance II, soil A, T = 0.1s (between TB=0.03 and TC=0.20)
        se = elastic_spectrum(0.1, zone=3, importance=2, soil="A")
        ag = 1.1 * 1.0  # agR * γI
        expected = ag * 1.0 * 1.0 * 2.5  # S=1, eta=1 for 5%
        assert abs(se - expected) < 0.01

    def test_elastic_spectrum_negative_T(self):
        se = elastic_spectrum(-1.0, zone=3, importance=2, soil="A")
        assert se == 0.0

    def test_design_spectrum_with_q(self):
        """Check that the design spectrum is reduced by q."""
        sd = design_spectrum(0.1, zone=3, importance=2, soil="A", q=2.0)
        ag = 1.1
        expected = ag * 1.0 * 2.5 / 2.0
        assert abs(sd - expected) < 0.01
