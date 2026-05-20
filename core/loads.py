"""
Gestion des cas de charges et combinaisons EC0.

Génération automatique des combinaisons ELU/ELS selon NF EN 1990 §6.4.3
avec les coefficients ψ de l'annexe nationale française.
"""

from __future__ import annotations

from enum import Enum

from config.eurocodes import (
    GAMMA_G_SUP,
    GAMMA_Q,
    PSI_COEFFICIENTS,
)
from core.model_data import CombinationData, LoadData


class ComboType(Enum):
    """Types de combinaisons selon EC0."""
    ULS_FUNDAMENTAL = "ELU"              # ELU fondamental §6.4.3.2
    ULS_ACCIDENTAL = "ELU acc."          # ELU accidentel §6.4.3.3
    ULS_SEISMIC = "ELU sism."            # ELU sismique §6.4.3.4
    SLS_CHARACTERISTIC = "ELS car."      # ELS caractéristique §6.5.3(a)
    SLS_FREQUENT = "ELS fréq."           # ELS fréquente §6.5.3(b)
    SLS_QUASI_PERMANENT = "ELS QP"       # ELS quasi-permanente §6.5.3(c)


# Descriptions françaises
COMBO_LABELS: dict[ComboType, str] = {
    ComboType.ULS_FUNDAMENTAL:    "ELU fondamental",
    ComboType.ULS_ACCIDENTAL:     "ELU accidentel",
    ComboType.ULS_SEISMIC:        "ELU sismique",
    ComboType.SLS_CHARACTERISTIC: "ELS caractéristique",
    ComboType.SLS_FREQUENT:       "ELS fréquente",
    ComboType.SLS_QUASI_PERMANENT:"ELS quasi-permanente",
}


def get_psi(category: str, load_type: str = "") -> tuple[float, float, float]:
    """Retourne les coefficients ψ₀, ψ₁, ψ₂ pour une catégorie EC1.

    Gère les sous-catégories (C1→C, D2→D, E1→E).
    Si la catégorie est vide, utilise le load_type (snow, wind, etc.).

    Args:
        category: Catégorie EC1 (A, B, C1-C5, D1-D2, E1-E2, H).
        load_type: Type de charge (snow, wind, variable, etc.) comme fallback.

    Returns:
        Tuple (ψ₀, ψ₁, ψ₂).
    """
    key = category or load_type
    # Essai direct
    if key in PSI_COEFFICIENTS:
        return PSI_COEFFICIENTS[key]
    # Sous-catégorie : C1→C, D2→D, E1→E
    if key and key[0].isalpha():
        base = key[0].upper()
        if base in PSI_COEFFICIENTS:
            return PSI_COEFFICIENTS[base]
    return (0.7, 0.5, 0.3)


def generate_uls_fundamental(
    permanent_tags: list[int],
    variable_loads: list[LoadData],
) -> list[dict[int, float]]:
    """Génère les combinaisons ELU fondamental (§6.4.3.2 éq. 6.10).

    Formule : Σ γ_G,j · G_k,j + γ_Q,1 · Q_k,1 + Σ γ_Q,i · ψ₀,i · Q_k,i

    Chaque charge variable est tour à tour la charge dominante Q₁.

    Args:
        permanent_tags: Tags des cas de charges permanentes.
        variable_loads: Liste des LoadData variables.

    Returns:
        Liste de dictionnaires {load_tag: facteur}.
    """
    combos = []

    if not variable_loads:
        # Permanentes seules
        factors = {}
        for tag in permanent_tags:
            factors[tag] = GAMMA_G_SUP
        if factors:
            combos.append(factors)
        return combos

    # Chaque variable est tour à tour la dominante
    for i, dominant in enumerate(variable_loads):
        factors = {}

        # Permanentes
        for tag in permanent_tags:
            factors[tag] = GAMMA_G_SUP

        # Variable dominante (sans ψ₀)
        factors[dominant.tag] = GAMMA_Q

        # Variables d'accompagnement (avec ψ₀)
        for j, companion in enumerate(variable_loads):
            if j == i:
                continue
            psi0, _, _ = get_psi(companion.category, companion.load_type)
            factor = GAMMA_Q * psi0
            if factor > 0.0:
                factors[companion.tag] = factor

        combos.append(factors)

    return combos


def generate_sls_characteristic(
    permanent_tags: list[int],
    variable_loads: list[LoadData],
) -> list[dict[int, float]]:
    """Génère les combinaisons ELS caractéristique (§6.5.3 éq. 6.14).

    Formule : Σ G_k,j + Q_k,1 + Σ ψ₀,i · Q_k,i

    Returns:
        Liste de dictionnaires {load_tag: facteur}.
    """
    combos = []

    if not variable_loads:
        factors = {tag: 1.0 for tag in permanent_tags}
        if factors:
            combos.append(factors)
        return combos

    for i, dominant in enumerate(variable_loads):
        factors = {tag: 1.0 for tag in permanent_tags}
        factors[dominant.tag] = 1.0

        for j, companion in enumerate(variable_loads):
            if j == i:
                continue
            psi0, _, _ = get_psi(companion.category, companion.load_type)
            if psi0 > 0.0:
                factors[companion.tag] = psi0

        combos.append(factors)

    return combos


def generate_sls_frequent(
    permanent_tags: list[int],
    variable_loads: list[LoadData],
) -> list[dict[int, float]]:
    """Génère les combinaisons ELS fréquente (§6.5.3 éq. 6.15).

    Formule : Σ G_k,j + ψ₁,1 · Q_k,1 + Σ ψ₂,i · Q_k,i

    Returns:
        Liste de dictionnaires {load_tag: facteur}.
    """
    combos = []

    if not variable_loads:
        factors = {tag: 1.0 for tag in permanent_tags}
        if factors:
            combos.append(factors)
        return combos

    for i, dominant in enumerate(variable_loads):
        factors = {tag: 1.0 for tag in permanent_tags}
        _, psi1, _ = get_psi(dominant.category, dominant.load_type)
        factors[dominant.tag] = psi1

        for j, companion in enumerate(variable_loads):
            if j == i:
                continue
            _, _, psi2 = get_psi(companion.category, companion.load_type)
            if psi2 > 0.0:
                factors[companion.tag] = psi2

        combos.append(factors)

    return combos


def generate_sls_quasi_permanent(
    permanent_tags: list[int],
    variable_loads: list[LoadData],
) -> list[dict[int, float]]:
    """Génère la combinaison ELS quasi-permanente (§6.5.3 éq. 6.16).

    Formule : Σ G_k,j + Σ ψ₂,i · Q_k,i

    Returns:
        Liste avec un seul dictionnaire {load_tag: facteur}.
    """
    factors = {tag: 1.0 for tag in permanent_tags}

    for var_load in variable_loads:
        _, _, psi2 = get_psi(var_load.category, var_load.load_type)
        if psi2 > 0.0:
            factors[var_load.tag] = psi2

    return [factors] if factors else []


def generate_uls_seismic(
    permanent_tags: list[int],
    variable_loads: list[LoadData],
    seismic_tag: int,
) -> list[dict[int, float]]:
    """Génère la combinaison ELU sismique (§6.4.3.4 éq. 6.12).

    Formule : Σ G_k,j + A_Ed + Σ ψ₂,i · Q_k,i

    Args:
        permanent_tags: Tags des charges permanentes.
        variable_loads: Charges variables.
        seismic_tag: Tag du cas de charge sismique.

    Returns:
        Liste avec un seul dictionnaire {load_tag: facteur}.
    """
    factors = {tag: 1.0 for tag in permanent_tags}
    factors[seismic_tag] = 1.0

    for var_load in variable_loads:
        _, _, psi2 = get_psi(var_load.category, var_load.load_type)
        if psi2 > 0.0:
            factors[var_load.tag] = psi2

    return [factors]


def auto_generate_combinations(
    loads: dict[int, LoadData],
    combo_types: list[ComboType] | None = None,
    start_tag: int = 1,
) -> list[CombinationData]:
    """Génère automatiquement toutes les combinaisons EC0.

    Sépare les cas de charge en permanents et variables,
    puis génère les combinaisons demandées.

    Args:
        loads: Dictionnaire des cas de charge du projet.
        combo_types: Types de combinaisons à générer (tous par défaut).
        start_tag: Tag de départ pour les combinaisons.

    Returns:
        Liste de CombinationData prêtes à ajouter au projet.
    """
    if combo_types is None:
        combo_types = [
            ComboType.ULS_FUNDAMENTAL,
            ComboType.SLS_CHARACTERISTIC,
            ComboType.SLS_FREQUENT,
            ComboType.SLS_QUASI_PERMANENT,
        ]

    # Séparer permanents et variables
    _PERMANENT_TYPES = {"dead", "permanent", "self_weight"}
    _VARIABLE_TYPES = {"live", "variable", "snow", "wind", "temperature"}
    _SEISMIC_TYPES = {"seismic"}

    permanent_tags = [
        lc.tag for lc in loads.values()
        if lc.load_type in _PERMANENT_TYPES
    ]
    variable_loads = [
        lc for lc in loads.values()
        if lc.load_type in _VARIABLE_TYPES
    ]
    seismic_loads = [
        lc for lc in loads.values()
        if lc.load_type in _SEISMIC_TYPES
    ]

    results = []
    tag = start_tag

    for combo_type in combo_types:
        if combo_type == ComboType.ULS_FUNDAMENTAL:
            factor_sets = generate_uls_fundamental(permanent_tags, variable_loads)
            for i, factors in enumerate(factor_sets, 1):
                results.append(CombinationData(
                    tag=tag,
                    name=f"ELU {i}",
                    combo_type=combo_type.value,
                    factors=factors,
                ))
                tag += 1

        elif combo_type == ComboType.SLS_CHARACTERISTIC:
            factor_sets = generate_sls_characteristic(permanent_tags, variable_loads)
            for i, factors in enumerate(factor_sets, 1):
                results.append(CombinationData(
                    tag=tag,
                    name=f"ELS car. {i}",
                    combo_type=combo_type.value,
                    factors=factors,
                ))
                tag += 1

        elif combo_type == ComboType.SLS_FREQUENT:
            factor_sets = generate_sls_frequent(permanent_tags, variable_loads)
            for i, factors in enumerate(factor_sets, 1):
                results.append(CombinationData(
                    tag=tag,
                    name=f"ELS fréq. {i}",
                    combo_type=combo_type.value,
                    factors=factors,
                ))
                tag += 1

        elif combo_type == ComboType.SLS_QUASI_PERMANENT:
            factor_sets = generate_sls_quasi_permanent(permanent_tags, variable_loads)
            for i, factors in enumerate(factor_sets, 1):
                results.append(CombinationData(
                    tag=tag,
                    name=f"ELS QP {i}",
                    combo_type=combo_type.value,
                    factors=factors,
                ))
                tag += 1

        elif combo_type == ComboType.ULS_SEISMIC:
            for seismic in seismic_loads:
                factor_sets = generate_uls_seismic(
                    permanent_tags, variable_loads, seismic.tag,
                )
                for i, factors in enumerate(factor_sets, 1):
                    results.append(CombinationData(
                        tag=tag,
                        name=f"ELU sism. {i}",
                        combo_type=combo_type.value,
                        factors=factors,
                    ))
                    tag += 1

    return results


def combination_formula(combo: CombinationData,
                        loads: dict[int, LoadData]) -> str:
    """Retourne la formule textuelle d'une combinaison.

    Ex: "1.35×G1 + 1.50×Q1 + 1.05×S1"

    Args:
        combo: La combinaison.
        loads: Dictionnaire des cas de charge.

    Returns:
        Chaîne de la formule.
    """
    parts = []
    for load_tag, factor in sorted(combo.factors.items()):
        lc = loads.get(load_tag)
        name = lc.name if lc else f"L{load_tag}"
        if factor == 1.0:
            parts.append(name)
        else:
            parts.append(f"{factor:.2f}×{name}")
    return " + ".join(parts)
