"""
Constantes normatives des Eurocodes avec annexes nationales françaises.

Couvre EC0 (combinaisons), EC1 (charges), EC2 (béton), EC3 (acier),
EC8 (sismique). Toutes les valeurs sont dans le système interne kN, m, kPa.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════
#  EC0 — NF EN 1990 : Bases de calcul des structures
# ═══════════════════════════════════════════════════════════════════════════

# Coefficients partiels ELU fondamental (§6.4.3.2, tableau A1.2(B))
GAMMA_G_SUP: float = 1.35   # actions permanentes défavorables
GAMMA_G_INF: float = 1.00   # actions permanentes favorables
GAMMA_Q: float = 1.50       # actions variables

# Coefficients ψ (tableau A1.1 — annexe nationale française)
# Format : {catégorie: (ψ₀, ψ₁, ψ₂)}

PSI_COEFFICIENTS: dict[str, tuple[float, float, float]] = {
    # Charges d'exploitation — bâtiments
    "A":  (0.7, 0.5, 0.3),   # habitation, résidentiel
    "B":  (0.7, 0.5, 0.3),   # bureaux
    "C":  (0.7, 0.7, 0.6),   # lieux de réunion
    "D":  (0.7, 0.7, 0.6),   # commerces
    "E":  (1.0, 0.9, 0.8),   # stockage
    "F":  (0.7, 0.7, 0.6),   # zones de trafic véhicules ≤ 30 kN
    "G":  (0.7, 0.5, 0.3),   # zones de trafic véhicules > 30 kN
    "H":  (0.0, 0.0, 0.0),   # toitures
    # Actions climatiques
    "snow":  (0.5, 0.2, 0.0),  # neige (altitude ≤ 1000 m)
    "snow_high": (0.7, 0.5, 0.2),  # neige (altitude > 1000 m)
    "wind":  (0.6, 0.2, 0.0),  # vent
    "temp":  (0.6, 0.5, 0.0),  # température
}

# Coefficients de combinaison ELU accidentel / sismique
GAMMA_G_ACCIDENTAL: float = 1.0
GAMMA_Q_ACCIDENTAL: float = 1.0


# ═══════════════════════════════════════════════════════════════════════════
#  EC1 — NF EN 1991 : Actions sur les structures
# ═══════════════════════════════════════════════════════════════════════════

# --- Charges d'exploitation (EC1-1-1, tableau 6.2 + AN FR) ---
# Valeurs en kPa (kN/m²)

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


# --- Neige — Annexe nationale française (EC1-1-3/NA) ---

class SnowZone(Enum):
    """Zones de neige métropolitaines."""
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    D  = "D"
    E  = "E"

# Charge de neige au sol sk0 (kN/m²) par zone — altitude de référence
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
    """Calcule la charge de neige au sol sk selon l'AN française.

    Formule : sk = sk0 + Δs1 (pour altitude > 200 m).

    Args:
        zone: Zone de neige (A1, A2, B1, B2, C1, C2, D, E).
        altitude: Altitude du site en mètres.

    Returns:
        Charge de neige sk en kN/m².
    """
    sk0 = SNOW_SK0[zone]
    if altitude <= 200:
        return sk0
    # Δs1 selon l'altitude (formule simplifiée AN)
    delta_s = (altitude - 200) / 1000
    if zone in ("D", "E"):
        delta_s *= 2  # majoration zones fortement enneigées
    return sk0 + delta_s


# --- Vent — Annexe nationale française (EC1-1-4/NA) ---

class WindZone(Enum):
    """Zones de vent métropolitaines (AN française)."""
    ZONE_1 = 1
    ZONE_2 = 2
    ZONE_3 = 3
    ZONE_4 = 4

# Vitesse de référence du vent vb,0 (m/s) par zone
WIND_VB0: dict[int, float] = {
    1: 22.0,
    2: 24.0,
    3: 26.0,
    4: 28.0,
}

# Pression dynamique de référence qb = 0.5 * ρ * vb² (kPa)
# ρ_air = 1.225 kg/m³
AIR_DENSITY: float = 1.225  # kg/m³

def wind_qb(zone: int) -> float:
    """Pression dynamique de référence qb en kPa.

    Args:
        zone: Zone de vent (1 à 4).

    Returns:
        qb en kPa.
    """
    vb = WIND_VB0[zone]
    return 0.5 * AIR_DENSITY * vb**2 / 1000  # Pa → kPa


class TerrainCategory(Enum):
    """Catégories de terrain (EC1-1-4, tableau 4.1)."""
    ZERO = 0   # mer, zone côtière
    I    = 1   # lacs, rase campagne
    II   = 2   # campagne avec haies, petits villages
    III  = 3   # zones suburbaines, forêts
    IV   = 4   # zones urbaines (≥ 15% bâti)

# Paramètres de rugosité par catégorie : (z0 en m, zmin en m)
TERRAIN_PARAMS: dict[int, tuple[float, float]] = {
    0: (0.003, 1.0),
    1: (0.01,  1.0),
    2: (0.05,  2.0),
    3: (0.30,  5.0),
    4: (1.00, 10.0),
}


# ═══════════════════════════════════════════════════════════════════════════
#  EC2 — NF EN 1992 : Calcul des structures en béton
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ConcreteGrade:
    """Propriétés d'une classe de béton EC2 (tableau 3.1).

    Toutes les contraintes en kPa, module en kPa.
    """

    name: str
    fck: float       # résistance caractéristique sur cylindre (kPa)
    fck_cube: float  # résistance caractéristique sur cube (kPa)
    fcm: float       # résistance moyenne (kPa)
    fctm: float      # résistance moyenne en traction (kPa)
    fctk_005: float  # fractile 5% traction (kPa)
    fctk_095: float  # fractile 95% traction (kPa)
    ecm: float       # module sécant moyen (kPa)
    eps_c1: float    # déformation au pic (‰)
    eps_cu1: float   # déformation ultime (‰)

    @property
    def fcd(self) -> float:
        """Résistance de calcul fcd = αcc × fck / γc (kPa)."""
        return ALPHA_CC * self.fck / GAMMA_C

    @property
    def fctd(self) -> float:
        """Résistance de calcul en traction fctd = αct × fctk_005 / γc (kPa)."""
        return ALPHA_CT * self.fctk_005 / GAMMA_C


# Coefficients EC2
GAMMA_C: float = 1.5      # coefficient partiel béton
ALPHA_CC: float = 1.0     # coefficient αcc (AN française)
ALPHA_CT: float = 1.0     # coefficient αct (AN française)

# Classes de béton (EC2 tableau 3.1) — valeurs en kPa
CONCRETE_GRADES: dict[str, ConcreteGrade] = {
    "C20/25": ConcreteGrade("C20/25", 20_000, 25_000, 28_000, 2_200, 1_500, 2_900, 30_000_000, 2.0, 3.5),
    "C25/30": ConcreteGrade("C25/30", 25_000, 30_000, 33_000, 2_600, 1_800, 3_300, 31_000_000, 2.1, 3.5),
    "C30/37": ConcreteGrade("C30/37", 30_000, 37_000, 38_000, 2_900, 2_000, 3_800, 33_000_000, 2.2, 3.5),
    "C35/45": ConcreteGrade("C35/45", 35_000, 45_000, 43_000, 3_200, 2_200, 4_200, 34_000_000, 2.25, 3.5),
    "C40/50": ConcreteGrade("C40/50", 40_000, 50_000, 48_000, 3_500, 2_500, 4_600, 35_000_000, 2.3, 3.5),
    "C45/55": ConcreteGrade("C45/55", 45_000, 55_000, 53_000, 3_800, 2_700, 4_900, 36_000_000, 2.4, 3.5),
    "C50/60": ConcreteGrade("C50/60", 50_000, 60_000, 58_000, 4_100, 2_900, 5_300, 37_000_000, 2.45, 3.5),
}


# --- Aciers pour béton armé (EC2 + AN FR) ---

@dataclass(frozen=True)
class RebarGrade:
    """Propriétés d'un acier pour armatures (EC2 annexe C)."""

    name: str
    fyk: float     # limite élastique caractéristique (kPa)
    es: float      # module d'Young (kPa)
    ductility: str # classe de ductilité (A, B ou C)

    @property
    def fyd(self) -> float:
        """Résistance de calcul fyd = fyk / γs (kPa)."""
        return self.fyk / GAMMA_S


GAMMA_S: float = 1.15  # coefficient partiel acier armatures

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
    """Propriétés d'un acier de construction (EC3 tableau 3.1)."""

    name: str
    fy: float      # limite élastique (kPa) — épaisseur ≤ 40 mm
    fu: float      # résistance à la traction (kPa)
    es: float      # module d'Young (kPa)

    @property
    def fyd(self) -> float:
        """Résistance de calcul fyd = fy / γM0 (kPa)."""
        return self.fy / GAMMA_M0


GAMMA_M0: float = 1.0   # coefficient partiel résistance sections
GAMMA_M1: float = 1.0   # coefficient partiel instabilités
GAMMA_M2: float = 1.25  # coefficient partiel sections nettes / boulons

STEEL_GRADES: dict[str, SteelGrade] = {
    "S235": SteelGrade("S235", 235_000, 360_000, 210_000_000),
    "S275": SteelGrade("S275", 275_000, 430_000, 210_000_000),
    "S355": SteelGrade("S355", 355_000, 510_000, 210_000_000),
    "S460": SteelGrade("S460", 460_000, 540_000, 210_000_000),
}


# ═══════════════════════════════════════════════════════════════════════════
#  EC8 — NF EN 1998 : Calcul des structures pour la résistance aux séismes
# ═══════════════════════════════════════════════════════════════════════════

class SeismicZone(Enum):
    """Zones de sismicité France (décret 2010-1255)."""
    ZONE_1 = 1   # très faible
    ZONE_2 = 2   # faible
    ZONE_3 = 3   # modérée
    ZONE_4 = 4   # moyenne
    ZONE_5 = 5   # forte (Antilles)

# Accélération de référence agR (m/s²) par zone sismique
SEISMIC_AGR: dict[int, float] = {
    1: 0.4,
    2: 0.7,
    3: 1.1,
    4: 1.6,
    5: 3.0,
}


class ImportanceClass(Enum):
    """Classes d'importance des bâtiments (EC8 §4.2.5)."""
    I   = 1   # bâtiments agricoles, etc.
    II  = 2   # bâtiments courants
    III = 3   # écoles, salles de réunion
    IV  = 4   # hôpitaux, casernes de pompiers

# Coefficient d'importance γI par classe
IMPORTANCE_FACTOR: dict[int, float] = {
    1: 0.8,
    2: 1.0,
    3: 1.2,
    4: 1.4,
}


class SoilClass(Enum):
    """Classes de sol (EC8 §3.1.2)."""
    A = "A"  # rocher
    B = "B"  # dépôts raides
    C = "C"  # dépôts profonds de sable/gravier dense
    D = "D"  # dépôts lâches
    E = "E"  # couche superficielle d'alluvions sur rocher


# Paramètres spectre type 1 (AN française, tableau 3.2)
# Format : (S, TB, TC, TD) en secondes

SPECTRUM_TYPE1: dict[str, tuple[float, float, float, float]] = {
    "A": (1.0, 0.03, 0.20, 2.5),
    "B": (1.35, 0.05, 0.25, 2.5),
    "C": (1.50, 0.06, 0.40, 2.0),
    "D": (1.60, 0.10, 0.60, 1.5),
    "E": (1.80, 0.08, 0.45, 1.25),
}

# Paramètres spectre type 2 (AN française, tableau 3.3)
SPECTRUM_TYPE2: dict[str, tuple[float, float, float, float]] = {
    "A": (1.0, 0.03, 0.20, 2.5),
    "B": (1.35, 0.05, 0.25, 2.5),
    "C": (1.50, 0.06, 0.40, 2.0),
    "D": (1.60, 0.10, 0.60, 1.5),
    "E": (1.80, 0.08, 0.45, 1.25),
}

# Coefficient η = √(10 / (5 + ξ)) ≥ 0.55 (EC8 §3.2.2.2)
DEFAULT_DAMPING: float = 5.0  # amortissement % (béton armé)


def damping_correction(xi: float = DEFAULT_DAMPING) -> float:
    """Coefficient de correction d'amortissement η (EC8 §3.2.2.2).

    Args:
        xi: Pourcentage d'amortissement visqueux (5% par défaut).

    Returns:
        Coefficient η.
    """
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
    """Ordonnée du spectre de réponse élastique Se(T) en m/s².

    EC8 §3.2.2.2, expressions (3.2) à (3.5).

    Args:
        T: Période en secondes.
        zone: Zone de sismicité (1 à 5).
        importance: Classe d'importance (1 à 4).
        soil: Classe de sol ('A' à 'E').
        spectrum_type: Type de spectre (1 ou 2).
        damping: Amortissement en % (5% par défaut).

    Returns:
        Accélération spectrale Se(T) en m/s².
    """
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
    """Ordonnée du spectre de calcul Sd(T) en m/s².

    EC8 §3.2.2.5, expressions (3.13) à (3.16).

    Args:
        T: Période en secondes.
        zone: Zone de sismicité (1 à 5).
        importance: Classe d'importance (1 à 4).
        soil: Classe de sol ('A' à 'E').
        q: Coefficient de comportement.
        spectrum_type: Type de spectre (1 ou 2).

    Returns:
        Accélération spectrale Sd(T) en m/s².
    """
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
