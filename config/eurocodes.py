"""Eurocode constants and French national annex data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════
#  EC0 — NF EN 1990 : Bases de calcul des structures
# ═══════════════════════════════════════════════════════════════════════════

# Fundamental ULS partial factors (§6.4.3.2, table A1.2(B))
GAMMA_G_SUP: float = 1.35   # unfavorable permanent actions
GAMMA_G_INF: float = 1.00   # favorable permanent actions
GAMMA_Q: float = 1.50       # variable actions

# Psi factors (table A1.1 — French national annex)
# Format: {category: (psi0, psi1, psi2)}

PSI_COEFFICIENTS: dict[str, tuple[float, float, float]] = {
    # Imposed loads — buildings
    "A":  (0.7, 0.5, 0.3),   # housing, residential
    "B":  (0.7, 0.5, 0.3),   # offices
    "C":  (0.7, 0.7, 0.6),   # assembly areas
    "D":  (0.7, 0.7, 0.6),   # commerces
    "E":  (1.0, 0.9, 0.8),   # stockage
    "F":  (0.7, 0.7, 0.6),   # vehicle traffic areas <= 30 kN
    "G":  (0.7, 0.5, 0.3),   # vehicle traffic areas > 30 kN
    "H":  (0.0, 0.0, 0.0),   # roofs
    # Climatic actions
    "snow":  (0.5, 0.2, 0.0),  # snow (altitude <= 1000 m)
    "snow_high": (0.7, 0.5, 0.2),  # snow (altitude > 1000 m)
    "wind":  (0.6, 0.2, 0.0),  # wind
    "temp":  (0.6, 0.5, 0.0),  # temperature
}

# Accidental / seismic ULS combination factors
GAMMA_G_ACCIDENTAL: float = 1.0
GAMMA_Q_ACCIDENTAL: float = 1.0


# ═══════════════════════════════════════════════════════════════════════════
#  EC1 — NF EN 1991: Actions on structures
# ═══════════════════════════════════════════════════════════════════════════

# --- Imposed loads (EC1-1-1, table 6.2 + French NA) ---
# Values in kPa (kN/m2)

LIVE_LOADS: dict[str, tuple[float, str]] = {
    "A":  (1.5, "Habitation, résidentiel"),
    "B":  (2.5, "Bureaux"),
    "C1": (2.5, "Espaces avec tables (restaurants, salles de classe)"),
    "C2": (4.0, "Espaces avec sièges fixes (cinémas, églises)"),
    "C3": (5.0, "Espaces sans obstacles (halls, musées)"),
    "C4": (5.0, "Activités physiques (gymnases, scènes)"),
    "C5": (5.0, "Foules compactes (tribunes, salles de concert)"),
    "D1": (4.0, "Commerces de détail"),
    "D2": (5.0, "Grands magasins"),
    "E1": (7.5, "Stockage (y compris archives)"),
    "H":  (0.8, "Toitures inaccessibles (entretien uniquement)"),
}


# --- Snow — French national annex (EC1-1-3/NA) ---

class SnowZone(Enum):
    """Enumeration of snow zone."""
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    D  = "D"
    E  = "E"

# Ground snow load sk0 (kN/m2) by zone — reference altitude
SNOW_SK0: dict[str, float] = {
    "A1": 0.45,
    "A2": 0.45,
    "B1": 0.55,
    "B2": 0.55,
    "C1": 0.65,
    "C2": 0.65,
    "D":  0.90,
    "E":  1.40,
}


def snow_load_sk(zone: str, altitude: float) -> float:
    """Return the ground snow load."""
    sk0 = SNOW_SK0[zone]
    if altitude <= 200:
        return sk0
    # Delta s1 by altitude (simplified NA formula)
    delta_s = (altitude - 200) / 1000
    if zone in ("D", "E"):
        delta_s *= 2  # increase for heavily snowed zones
    return sk0 + delta_s


# --- Wind — French national annex (EC1-1-4/NA) ---

class WindZone(Enum):
    """Enumeration of wind zone."""
    ZONE_1 = 1
    ZONE_2 = 2
    ZONE_3 = 3
    ZONE_4 = 4

# Reference wind velocity vb,0 (m/s) by zone
WIND_VB0: dict[int, float] = {
    1: 22.0,
    2: 24.0,
    3: 26.0,
    4: 28.0,
}

# Reference dynamic pressure qb = 0.5 * rho * vb^2 (kPa)
# ρ_air = 1.225 kg/m³
AIR_DENSITY: float = 1.225  # kg/m³

def wind_qb(zone: int) -> float:
    """Return the reference wind velocity pressure."""
    vb = WIND_VB0[zone]
    return 0.5 * AIR_DENSITY * vb**2 / 1000  # Pa → kPa


class TerrainCategory(Enum):
    """Terrain category."""
    ZERO = 0   # sea, coastal area
    I    = 1   # lacs, rase campagne
    II   = 2   # countryside with hedges, small villages
    III  = 3   # suburban areas, forests
    IV   = 4   # urban areas (>= 15% built-up)

# Roughness parameters by category: (z0 in m, zmin in m)
TERRAIN_PARAMS: dict[int, tuple[float, float]] = {
    0: (0.003, 1.0),
    1: (0.01,  1.0),
    2: (0.05,  2.0),
    3: (0.30,  5.0),
    4: (1.00, 10.0),
}


# ═══════════════════════════════════════════════════════════════════════════
#  EC2 — NF EN 1992: Design of concrete structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ConcreteGrade:
    """Material grade data for concrete grade."""

    name: str
    fck: float       # characteristic cylinder strength (kPa)
    fck_cube: float  # characteristic cube strength (kPa)
    fcm: float       # mean strength (kPa)
    fctm: float      # mean tensile strength (kPa)
    fctk_005: float  # fractile 5% traction (kPa)
    fctk_095: float  # fractile 95% traction (kPa)
    ecm: float       # mean secant modulus (kPa)
    eps_c1: float    # strain at peak stress (per mille)
    eps_cu1: float   # ultimate strain (per mille)

    @property
    def fcd(self) -> float:
        """Return the concrete design compressive strength."""
        return ALPHA_CC * self.fck / GAMMA_C

    @property
    def fctd(self) -> float:
        """Return the concrete design tensile strength."""
        return ALPHA_CT * self.fctk_005 / GAMMA_C


# EC2 factors
GAMMA_C: float = 1.5      # concrete partial factor
ALPHA_CC: float = 1.0     # alpha_cc factor (French NA)
ALPHA_CT: float = 1.0     # alpha_ct factor (French NA)

# Concrete grades (EC2 table 3.1) — values in kPa
CONCRETE_GRADES: dict[str, ConcreteGrade] = {
    "C20/25": ConcreteGrade("C20/25", 20_000, 25_000, 28_000, 2_200, 1_500, 2_900, 30_000_000, 2.0, 3.5),
    "C25/30": ConcreteGrade("C25/30", 25_000, 30_000, 33_000, 2_600, 1_800, 3_300, 31_000_000, 2.1, 3.5),
    "C30/37": ConcreteGrade("C30/37", 30_000, 37_000, 38_000, 2_900, 2_000, 3_800, 33_000_000, 2.2, 3.5),
    "C35/45": ConcreteGrade("C35/45", 35_000, 45_000, 43_000, 3_200, 2_200, 4_200, 34_000_000, 2.25, 3.5),
    "C40/50": ConcreteGrade("C40/50", 40_000, 50_000, 48_000, 3_500, 2_500, 4_600, 35_000_000, 2.3, 3.5),
    "C45/55": ConcreteGrade("C45/55", 45_000, 55_000, 53_000, 3_800, 2_700, 4_900, 36_000_000, 2.4, 3.5),
    "C50/60": ConcreteGrade("C50/60", 50_000, 60_000, 58_000, 4_100, 2_900, 5_300, 37_000_000, 2.45, 3.5),
}


# --- Reinforcing steels (EC2 + French NA) ---

@dataclass(frozen=True)
class RebarGrade:
    """Material grade data for rebar grade."""

    name: str
    fyk: float     # characteristic yield strength (kPa)
    es: float      # Young's modulus (kPa)
    ductility: str # ductility class (A, B, or C)

    @property
    def fyd(self) -> float:
        """Return the steel design yield strength."""
        return self.fyk / GAMMA_S


GAMMA_S: float = 1.15  # reinforcement steel partial factor

REBAR_GRADES: dict[str, RebarGrade] = {
    "B500A": RebarGrade("B500A", 500_000, 200_000_000, "A"),
    "B500B": RebarGrade("B500B", 500_000, 200_000_000, "B"),
    "B500C": RebarGrade("B500C", 500_000, 200_000_000, "C"),
}


# ═══════════════════════════════════════════════════════════════════════════
#  EC3 — NF EN 1993 : Calcul des structures en acier
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SteelGrade:
    """Material grade data for steel grade."""

    name: str
    fy: float      # yield strength (kPa) — thickness <= 40 mm
    fu: float      # tensile strength (kPa)
    es: float      # Young's modulus (kPa)

    @property
    def fyd(self) -> float:
        """Return the steel design yield strength."""
        return self.fy / GAMMA_M0


GAMMA_M0: float = 1.0   # section resistance partial factor
GAMMA_M1: float = 1.0   # instability partial factor
GAMMA_M2: float = 1.25  # net section / bolt partial factor

STEEL_GRADES: dict[str, SteelGrade] = {
    "S235": SteelGrade("S235", 235_000, 360_000, 210_000_000),
    "S275": SteelGrade("S275", 275_000, 430_000, 210_000_000),
    "S355": SteelGrade("S355", 355_000, 510_000, 210_000_000),
    "S460": SteelGrade("S460", 460_000, 540_000, 210_000_000),
}


# ═══════════════════════════════════════════════════════════════════════════
#  EC8 — NF EN 1998: Design of structures for earthquake resistance
# ═══════════════════════════════════════════════════════════════════════════

class SeismicZone(Enum):
    """Enumeration of seismic zone."""
    ZONE_1 = 1   # very low
    ZONE_2 = 2   # faible
    ZONE_3 = 3   # moderate
    ZONE_4 = 4   # moyenne
    ZONE_5 = 5   # forte (Antilles)

# Reference acceleration agR (m/s2) by seismic zone
SEISMIC_AGR: dict[int, float] = {
    1: 0.4,
    2: 0.7,
    3: 1.1,
    4: 1.6,
    5: 3.0,
}


class ImportanceClass(Enum):
    """Enumeration of importance class."""
    I   = 1   # agricultural buildings, etc.
    II  = 2   # ordinary buildings
    III = 3   # schools, assembly rooms
    IV  = 4   # hospitals, fire stations

# Importance factor gamma_I by class
IMPORTANCE_FACTOR: dict[int, float] = {
    1: 0.8,
    2: 1.0,
    3: 1.2,
    4: 1.4,
}


class SoilClass(Enum):
    """Enumeration of soil class."""
    A = "A"  # rocher
    B = "B"  # stiff deposits
    C = "C"  # deep deposits of dense sand/gravel
    D = "D"  # loose deposits
    E = "E"  # shallow alluvial layer over rock


# Type 1 spectrum parameters (French NA, table 3.2)
# Format: (S, TB, TC, TD) in seconds

SPECTRUM_TYPE1: dict[str, tuple[float, float, float, float]] = {
    "A": (1.0, 0.03, 0.20, 2.5),
    "B": (1.35, 0.05, 0.25, 2.5),
    "C": (1.50, 0.06, 0.40, 2.0),
    "D": (1.60, 0.10, 0.60, 1.5),
    "E": (1.80, 0.08, 0.45, 1.25),
}

# Type 2 spectrum parameters (French NA, table 3.3)
SPECTRUM_TYPE2: dict[str, tuple[float, float, float, float]] = {
    "A": (1.0, 0.03, 0.20, 2.5),
    "B": (1.35, 0.05, 0.25, 2.5),
    "C": (1.50, 0.06, 0.40, 2.0),
    "D": (1.60, 0.10, 0.60, 1.5),
    "E": (1.80, 0.08, 0.45, 1.25),
}

# Factor eta = sqrt(10 / (5 + xi)) >= 0.55 (EC8 §3.2.2.2)
DEFAULT_DAMPING: float = 5.0  # damping % (reinforced concrete)


def damping_correction(xi: float = DEFAULT_DAMPING) -> float:
    """Return the EC8 damping correction factor."""
    eta = (10.0 / (5.0 + xi)) ** 0.5
    return max(eta, 0.55)


def elastic_spectrum(
    T: float,
    zone: int,
    importance: int,
    soil: str,
    spectrum_type: int = 1,
    damping: float = DEFAULT_DAMPING,
) -> float:
    """Return the elastic response spectrum ordinate."""
    agr = SEISMIC_AGR[zone]
    gamma_i = IMPORTANCE_FACTOR[importance]
    ag = agr * gamma_i

    params = SPECTRUM_TYPE1 if spectrum_type == 1 else SPECTRUM_TYPE2
    s, tb, tc, td = params[soil]

    eta = damping_correction(damping)

    if T < 0:
        return 0.0
    elif T <= tb:
        return ag * s * (1 + T / tb * (eta * 2.5 - 1))
    elif T <= tc:
        return ag * s * eta * 2.5
    elif T <= td:
        return ag * s * eta * 2.5 * (tc / T)
    else:
        return ag * s * eta * 2.5 * (tc * td / T**2)


def design_spectrum(
    T: float,
    zone: int,
    importance: int,
    soil: str,
    q: float = 1.5,
    spectrum_type: int = 1,
) -> float:
    """Return the design response spectrum ordinate."""
    agr = SEISMIC_AGR[zone]
    gamma_i = IMPORTANCE_FACTOR[importance]
    ag = agr * gamma_i

    params = SPECTRUM_TYPE1 if spectrum_type == 1 else SPECTRUM_TYPE2
    s, tb, tc, td = params[soil]

    beta = 0.2  # plancher du spectre de calcul (EC8 AN FR)

    if T < 0:
        return 0.0
    elif T <= tb:
        return ag * s * (2 / 3 + T / tb * (2.5 / q - 2 / 3))
    elif T <= tc:
        return ag * s * 2.5 / q
    elif T <= td:
        return max(ag * s * 2.5 / q * (tc / T), beta * ag)
    else:
        return max(ag * s * 2.5 / q * (tc * td / T**2), beta * ag)
