"""
Système d'unités SI pour le calcul de structures.

Unités internes : kN, m, kPa (système génie civil courant).
Ce module centralise toutes les conversions entre les unités
d'affichage (mm, cm, MPa, cm², cm⁴…) et les unités internes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


# ---------------------------------------------------------------------------
#  Facteurs de conversion vers les unités internes (kN, m, kPa)
# ---------------------------------------------------------------------------

# Longueur → mètre
MM_TO_M: float = 1e-3
CM_TO_M: float = 1e-2
M_TO_M: float = 1.0

# Surface → m²
MM2_TO_M2: float = 1e-6
CM2_TO_M2: float = 1e-4
M2_TO_M2: float = 1.0

# Inertie → m⁴
MM4_TO_M4: float = 1e-12
CM4_TO_M4: float = 1e-8
M4_TO_M4: float = 1.0

# Force → kN
N_TO_KN: float = 1e-3
KN_TO_KN: float = 1.0
MN_TO_KN: float = 1e3

# Contrainte → kPa
PA_TO_KPA: float = 1e-3
KPA_TO_KPA: float = 1.0
MPA_TO_KPA: float = 1e3
GPA_TO_KPA: float = 1e6

# Charge linéique → kN/m
N_M_TO_KN_M: float = 1e-3
KN_M_TO_KN_M: float = 1.0

# Moment → kN·m
NM_TO_KNM: float = 1e-3
KNM_TO_KNM: float = 1.0

# Masse → kg
KG_TO_KG: float = 1.0
T_TO_KG: float = 1e3

# Masse volumique → kg/m³
KG_M3_TO_KG_M3: float = 1.0

# Accélération → m/s²
G_STANDARD: float = 9.80665  # accélération gravitationnelle standard


# ---------------------------------------------------------------------------
#  Enum des grandeurs physiques
# ---------------------------------------------------------------------------

class Quantity(Enum):
    """Grandeurs physiques gérées par le système d'unités."""

    LENGTH = "length"
    AREA = "area"
    INERTIA = "inertia"
    FORCE = "force"
    STRESS = "stress"
    LINE_LOAD = "line_load"
    MOMENT = "moment"
    MASS = "mass"
    DENSITY = "density"
    ACCELERATION = "acceleration"


# ---------------------------------------------------------------------------
#  Définition des unités
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UnitDef:
    """Définition d'une unité avec son facteur de conversion vers l'unité interne."""

    symbol: str
    label_fr: str
    to_internal: float
    quantity: Quantity

    def convert_to_internal(self, value: float) -> float:
        """Convertit une valeur de cette unité vers l'unité interne."""
        return value * self.to_internal

    def convert_from_internal(self, value: float) -> float:
        """Convertit une valeur de l'unité interne vers cette unité."""
        return value / self.to_internal


# --- Longueur ---
MM = UnitDef("mm", "millimètre", MM_TO_M, Quantity.LENGTH)
CM = UnitDef("cm", "centimètre", CM_TO_M, Quantity.LENGTH)
M = UnitDef("m", "mètre", M_TO_M, Quantity.LENGTH)

# --- Surface ---
MM2 = UnitDef("mm²", "millimètre carré", MM2_TO_M2, Quantity.AREA)
CM2 = UnitDef("cm²", "centimètre carré", CM2_TO_M2, Quantity.AREA)
M2 = UnitDef("m²", "mètre carré", M2_TO_M2, Quantity.AREA)

# --- Inertie ---
MM4 = UnitDef("mm⁴", "millimètre puissance 4", MM4_TO_M4, Quantity.INERTIA)
CM4 = UnitDef("cm⁴", "centimètre puissance 4", CM4_TO_M4, Quantity.INERTIA)
M4 = UnitDef("m⁴", "mètre puissance 4", M4_TO_M4, Quantity.INERTIA)

# --- Force ---
N = UnitDef("N", "newton", N_TO_KN, Quantity.FORCE)
KN = UnitDef("kN", "kilonewton", KN_TO_KN, Quantity.FORCE)
MN = UnitDef("MN", "méganewton", MN_TO_KN, Quantity.FORCE)

# --- Contrainte ---
PA = UnitDef("Pa", "pascal", PA_TO_KPA, Quantity.STRESS)
KPA = UnitDef("kPa", "kilopascal", KPA_TO_KPA, Quantity.STRESS)
MPA = UnitDef("MPa", "mégapascal", MPA_TO_KPA, Quantity.STRESS)
GPA = UnitDef("GPa", "gigapascal", GPA_TO_KPA, Quantity.STRESS)

# --- Charge linéique ---
N_PER_M = UnitDef("N/m", "newton par mètre", N_M_TO_KN_M, Quantity.LINE_LOAD)
KN_PER_M = UnitDef("kN/m", "kilonewton par mètre", KN_M_TO_KN_M, Quantity.LINE_LOAD)

# --- Moment ---
NM = UnitDef("N·m", "newton-mètre", NM_TO_KNM, Quantity.MOMENT)
KNM = UnitDef("kN·m", "kilonewton-mètre", KNM_TO_KNM, Quantity.MOMENT)

# --- Masse ---
KG = UnitDef("kg", "kilogramme", KG_TO_KG, Quantity.MASS)
T = UnitDef("t", "tonne", T_TO_KG, Quantity.MASS)

# --- Masse volumique ---
KG_PER_M3 = UnitDef("kg/m³", "kilogramme par mètre cube", KG_M3_TO_KG_M3, Quantity.DENSITY)

# --- Accélération ---
M_PER_S2 = UnitDef("m/s²", "mètre par seconde carrée", 1.0, Quantity.ACCELERATION)


# ---------------------------------------------------------------------------
#  Registre : unités groupées par grandeur
# ---------------------------------------------------------------------------

UNITS_BY_QUANTITY: dict[Quantity, list[UnitDef]] = {
    Quantity.LENGTH: [MM, CM, M],
    Quantity.AREA: [MM2, CM2, M2],
    Quantity.INERTIA: [MM4, CM4, M4],
    Quantity.FORCE: [N, KN, MN],
    Quantity.STRESS: [PA, KPA, MPA, GPA],
    Quantity.LINE_LOAD: [N_PER_M, KN_PER_M],
    Quantity.MOMENT: [NM, KNM],
    Quantity.MASS: [KG, T],
    Quantity.DENSITY: [KG_PER_M3],
    Quantity.ACCELERATION: [M_PER_S2],
}

# Unités internes par défaut (pour affichage)
INTERNAL_UNITS: dict[Quantity, UnitDef] = {
    Quantity.LENGTH: M,
    Quantity.AREA: M2,
    Quantity.INERTIA: M4,
    Quantity.FORCE: KN,
    Quantity.STRESS: KPA,
    Quantity.LINE_LOAD: KN_PER_M,
    Quantity.MOMENT: KNM,
    Quantity.MASS: KG,
    Quantity.DENSITY: KG_PER_M3,
    Quantity.ACCELERATION: M_PER_S2,
}


# ---------------------------------------------------------------------------
#  Fonctions utilitaires
# ---------------------------------------------------------------------------

def convert(value: float, from_unit: UnitDef, to_unit: UnitDef) -> float:
    """Convertit une valeur entre deux unités de même grandeur.

    Args:
        value: Valeur à convertir.
        from_unit: Unité source.
        to_unit: Unité cible.

    Returns:
        Valeur convertie.

    Raises:
        ValueError: Si les unités ne sont pas de la même grandeur.
    """
    if from_unit.quantity != to_unit.quantity:
        raise ValueError(
            f"Conversion impossible : {from_unit.symbol} ({from_unit.quantity.value}) "
            f"→ {to_unit.symbol} ({to_unit.quantity.value})"
        )
    # from → interne → to
    internal = value * from_unit.to_internal
    return internal / to_unit.to_internal


def to_internal(value: float, unit: UnitDef) -> float:
    """Raccourci : convertit vers l'unité interne."""
    return value * unit.to_internal


def from_internal(value: float, unit: UnitDef) -> float:
    """Raccourci : convertit depuis l'unité interne."""
    return value / unit.to_internal


def find_unit(symbol: str) -> UnitDef | None:
    """Recherche une unité par son symbole.

    Args:
        symbol: Symbole de l'unité (ex. "mm", "MPa", "kN/m").

    Returns:
        L'UnitDef correspondante ou None si non trouvée.
    """
    for units in UNITS_BY_QUANTITY.values():
        for u in units:
            if u.symbol == symbol:
                return u
    return None
