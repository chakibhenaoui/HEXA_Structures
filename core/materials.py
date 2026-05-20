"""
Bibliothèque de matériaux pour le calcul de structures.

Béton (EC2 : C25/30 → C90/105), Acier (EC3 : S235 → S460).
Fournit les paramètres OpenSees pour Concrete02 et Steel02.
Toutes les valeurs en unités internes : kPa, m.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.eurocodes import (
    CONCRETE_GRADES,
    REBAR_GRADES,
    STEEL_GRADES,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Paramètres OpenSees pour les matériaux
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Concrete02Params:
    """Paramètres pour le matériau uniaxialMaterial Concrete02.

    Modèle béton avec branche de traction linéaire.
    Toutes les contraintes en kPa, déformations sans unité.
    """

    tag: int
    fpc: float      # résistance en compression pic (kPa, négatif)
    epsc0: float    # déformation au pic (négatif)
    fpcu: float     # résistance résiduelle ultime (kPa, négatif)
    epscu: float    # déformation ultime (négatif)
    # Branche de traction
    ft: float       # résistance en traction (kPa, positif)
    ets: float      # pente de déchargement en traction (kPa)
    # Paramètre de confinement
    lam: float = 0.1  # rapport fpcu/fpc


@dataclass
class Steel02Params:
    """Paramètres pour le matériau uniaxialMaterial Steel02.

    Modèle Giuffré-Menegotto-Pinto avec écrouissage isotrope.
    Toutes les contraintes en kPa.
    """

    tag: int
    fy: float       # limite élastique (kPa)
    es: float       # module d'Young (kPa)
    b: float        # rapport d'écrouissage (pente post-élastique / Es)
    r0: float = 18.0  # paramètre de transition
    cr1: float = 0.925
    cr2: float = 0.15


# ═══════════════════════════════════════════════════════════════════════════
#  Fonctions de création de matériaux
# ═══════════════════════════════════════════════════════════════════════════

def concrete_params(tag: int, grade: str, confined: bool = False) -> Concrete02Params:
    """Crée les paramètres Concrete02 à partir d'une classe de béton EC2.

    Args:
        tag: Tag OpenSees du matériau.
        grade: Classe de béton (ex. "C30/37").
        confined: Si True, majore les propriétés pour le béton confiné.

    Returns:
        Paramètres Concrete02 prêts pour OpenSees.
    """
    cg = CONCRETE_GRADES[grade]

    # Résistance de calcul en compression
    fpc = -cg.fcd  # négatif pour OpenSees
    epsc0 = -cg.eps_c1 / 1000  # ‰ → sans unité, négatif

    # Résistance résiduelle (20% de fpc pour béton non confiné)
    ratio = 0.4 if confined else 0.2
    fpcu = fpc * ratio
    epscu = -cg.eps_cu1 / 1000  # négatif

    # Traction
    ft = cg.fctd  # positif
    ets = cg.ecm / 10  # pente de déchargement arbitraire

    if confined:
        # Majoration simplifiée pour confinement (facteur 1.3)
        fpc *= 1.3
        epsc0 *= 1.5
        fpcu *= 1.3
        epscu *= 2.0

    return Concrete02Params(
        tag=tag,
        fpc=fpc,
        epsc0=epsc0,
        fpcu=fpcu,
        epscu=epscu,
        ft=ft,
        ets=ets,
    )


def rebar_params(tag: int, grade: str, b: float = 0.01) -> Steel02Params:
    """Crée les paramètres Steel02 pour un acier d'armature EC2.

    Args:
        tag: Tag OpenSees du matériau.
        grade: Classe d'acier (ex. "B500B").
        b: Rapport d'écrouissage.

    Returns:
        Paramètres Steel02 prêts pour OpenSees.
    """
    rg = REBAR_GRADES[grade]
    return Steel02Params(
        tag=tag,
        fy=rg.fyd,
        es=rg.es,
        b=b,
    )


def steel_params(tag: int, grade: str, b: float = 0.01) -> Steel02Params:
    """Crée les paramètres Steel02 pour un acier de construction EC3.

    Args:
        tag: Tag OpenSees du matériau.
        grade: Classe d'acier (ex. "S355").
        b: Rapport d'écrouissage.

    Returns:
        Paramètres Steel02 prêts pour OpenSees.
    """
    sg = STEEL_GRADES[grade]
    return Steel02Params(
        tag=tag,
        fy=sg.fyd,
        es=sg.es,
        b=b,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Masses volumiques (kg/m³) pour le poids propre
# ═══════════════════════════════════════════════════════════════════════════

DENSITIES: dict[str, float] = {
    "concrete": 2500.0,         # béton armé
    "concrete_lightweight": 1800.0,
    "steel": 7850.0,            # acier de construction
    "timber_C24": 420.0,        # bois résineux C24
}
