"""Structural material library and OpenSees material parameters."""

from __future__ import annotations

from dataclasses import dataclass

from config.eurocodes import (
    CONCRETE_GRADES,
    REBAR_GRADES,
    STEEL_GRADES,
)


# ═══════════════════════════════════════════════════════════════════════════
#  OpenSees material parameters
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Concrete02Params:
    """Concrete02 params."""

    tag: int
    fpc: float      # peak compressive strength (kPa, negative)
    epsc0: float    # strain at peak stress (negative)
    fpcu: float     # ultimate residual strength (kPa, negative)
    epscu: float    # ultimate strain (negative)
    # Branche de traction
    ft: float       # tensile strength (kPa, positive)
    ets: float      # tension unloading slope (kPa)
    # Confinement parameter
    lam: float = 0.1  # fpcu/fpc ratio


@dataclass
class Steel02Params:
    """Steel02 params."""

    tag: int
    fy: float       # yield strength (kPa)
    es: float       # Young's modulus (kPa)
    b: float        # hardening ratio (post-elastic slope / Es)
    r0: float = 18.0  # transition parameter
    cr1: float = 0.925
    cr2: float = 0.15


# ═══════════════════════════════════════════════════════════════════════════
#  Material creation functions
# ═══════════════════════════════════════════════════════════════════════════

def concrete_params(tag: int, grade: str, confined: bool = False) -> Concrete02Params:
    """Handle concrete params."""
    cg = CONCRETE_GRADES[grade]

    # Design compressive strength
    fpc = -cg.fcd  # negative for OpenSees
    epsc0 = -cg.eps_c1 / 1000  # per mille -> dimensionless, negative

    # Residual strength (20% of fpc for unconfined concrete)
    ratio = 0.4 if confined else 0.2
    fpcu = fpc * ratio
    epscu = -cg.eps_cu1 / 1000  # negative

    # Traction
    ft = cg.fctd  # positif
    ets = cg.ecm / 10  # arbitrary unloading slope

    if confined:
        # Simplified confinement increase (factor 1.3)
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
    """Handle rebar params."""
    rg = REBAR_GRADES[grade]
    return Steel02Params(
        tag=tag,
        fy=rg.fyd,
        es=rg.es,
        b=b,
    )


def steel_params(tag: int, grade: str, b: float = 0.01) -> Steel02Params:
    """Handle steel params."""
    sg = STEEL_GRADES[grade]
    return Steel02Params(
        tag=tag,
        fy=sg.fyd,
        es=sg.es,
        b=b,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Mass densities (kg/m3) for self-weight
# ═══════════════════════════════════════════════════════════════════════════

DENSITIES: dict[str, float] = {
    "concrete": 2500.0,         # reinforced concrete
    "concrete_lightweight": 1800.0,
    "steel": 7850.0,            # acier de construction
    "timber_C24": 420.0,        # C24 softwood
}
