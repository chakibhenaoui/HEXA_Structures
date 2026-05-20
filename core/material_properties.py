"""Helpers partages pour les propriétés isotropes des matériaux."""

from __future__ import annotations

from typing import Any, Mapping

from config.eurocodes import CONCRETE_GRADES, REBAR_GRADES, STEEL_GRADES

GRAVITY_ACCELERATION = 9.81

_DEFAULT_POISSON_RATIOS: dict[str, float] = {
    "concrete": 0.20,
    "rebar": 0.30,
    "steel": 0.30,
}

_DEFAULT_UNIT_WEIGHTS: dict[str, float] = {
    "concrete": 25.0,
    "rebar": 78.5,
    "steel": 78.5,
}


def density_kg_m3_to_unit_weight(density_kg_m3: float) -> float:
    """Convertit une masse volumique (kg/m3) en poids volumique (kN/m3)."""
    return float(density_kg_m3) * GRAVITY_ACCELERATION / 1000.0


def unit_weight_to_density_kg_m3(unit_weight: float) -> float:
    """Convertit un poids volumique (kN/m3) en masse volumique (kg/m3)."""
    return float(unit_weight) * 1000.0 / GRAVITY_ACCELERATION


def default_material_unit_weight(material_type: str) -> float:
    """Retourne le poids volumique par défaut pour le type de matériau."""
    return _DEFAULT_UNIT_WEIGHTS.get(material_type, 78.5)


def default_material_young_modulus(material_type: str, grade: str) -> float:
    """Retourne le module d'Young par défaut à partir de la nuance."""
    if material_type == "concrete" and grade in CONCRETE_GRADES:
        return CONCRETE_GRADES[grade].ecm
    if material_type == "rebar" and grade in REBAR_GRADES:
        return REBAR_GRADES[grade].es
    if material_type == "steel" and grade in STEEL_GRADES:
        return STEEL_GRADES[grade].es
    return 30_000_000.0 if material_type == "concrete" else 210_000_000.0


def default_material_poisson_ratio(material_type: str) -> float:
    """Retourne le coefficient de Poisson par défaut."""
    return _DEFAULT_POISSON_RATIOS.get(material_type, 0.30)


def compute_shear_modulus(young_modulus: float, poisson_ratio: float) -> float:
    """Calcule le module de cisaillement isotrope G."""
    denominator = 2.0 * (1.0 + float(poisson_ratio))
    if denominator <= 1e-12:
        return 0.0
    return float(young_modulus) / denominator


def _normalize_density_kg_m3(raw_density: Any) -> float | None:
    """Normalise une masse volumique legacy en kg/m3."""
    if raw_density is None:
        return None
    density = float(raw_density)
    if density < 100.0:
        return density * 1000.0
    return density


def isotropic_material_properties(
    material_type: str,
    grade: str,
    properties: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Retourne les propriétés isotropes normalisees d'un matériau."""
    props = dict(properties or {})

    unit_weight = props.get("unit_weight")
    if unit_weight is None:
        legacy_density = _normalize_density_kg_m3(props.get("rho"))
        if legacy_density is not None:
            unit_weight = density_kg_m3_to_unit_weight(legacy_density)
        else:
            unit_weight = default_material_unit_weight(material_type)

    young_modulus = props.get("young_modulus")
    if young_modulus is None:
        young_modulus = props.get("E")
    if young_modulus is None:
        young_modulus = default_material_young_modulus(material_type, grade)

    poisson_ratio = props.get("poisson_ratio")
    if poisson_ratio is None:
        poisson_ratio = props.get("nu")
    if poisson_ratio is None:
        poisson_ratio = default_material_poisson_ratio(material_type)

    return {
        "unit_weight": float(unit_weight),
        "young_modulus": float(young_modulus),
        "poisson_ratio": float(poisson_ratio),
    }


def build_material_properties(
    *,
    unit_weight: float,
    young_modulus: float,
    poisson_ratio: float,
    base_properties: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit le dictionnaire de propriétés isotropes a sauvegarder."""
    props = dict(base_properties or {})
    props.pop("rho", None)
    props.pop("E", None)
    props.pop("nu", None)
    props["unit_weight"] = float(unit_weight)
    props["young_modulus"] = float(young_modulus)
    props["poisson_ratio"] = float(poisson_ratio)
    return props


def material_mass_density_kg_m3(material) -> float:
    """Retourne la masse volumique d'un objet matériau en kg/m3."""
    if material is None:
        return 0.0
    props = isotropic_material_properties(
        getattr(material, "material_type", ""),
        getattr(material, "grade", ""),
        getattr(material, "properties", {}),
    )
    return unit_weight_to_density_kg_m3(props["unit_weight"])


def material_elastic_modulus(material) -> float:
    """Retourne le module d'Young d'un objet matériau en kPa."""
    if material is None:
        return default_material_young_modulus("steel", "")
    return isotropic_material_properties(
        getattr(material, "material_type", ""),
        getattr(material, "grade", ""),
        getattr(material, "properties", {}),
    )["young_modulus"]


def material_poisson_ratio(material) -> float:
    """Retourne le coefficient de Poisson d'un objet matériau."""
    if material is None:
        return default_material_poisson_ratio("steel")
    return isotropic_material_properties(
        getattr(material, "material_type", ""),
        getattr(material, "grade", ""),
        getattr(material, "properties", {}),
    )["poisson_ratio"]


def material_shear_modulus(material) -> float:
    """Retourne le module de cisaillement d'un objet matériau en kPa."""
    young_modulus = material_elastic_modulus(material)
    poisson_ratio = material_poisson_ratio(material)
    return compute_shear_modulus(young_modulus, poisson_ratio)
