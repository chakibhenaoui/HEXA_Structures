"""Translated GUI labels for domain values kept in the core layer."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

from core.self_weight import is_self_weight_load

if TYPE_CHECKING:
    from core.model_data import CombinationData, LoadData


_CASE_NAME_RE = re.compile(r"^(?:cas|case)\s+(\d+)$", re.IGNORECASE)


def load_name_label(load: "LoadData | None") -> str:
    """Return a translated display name for common generated load cases."""
    if load is None:
        return ""
    name = str(getattr(load, "name", "") or "").strip()
    if is_self_weight_load(load) or name.casefold() in {"poids propre", "self weight"}:
        return QCoreApplication.translate("DomainLabels", "Poids propre")
    match = _CASE_NAME_RE.fullmatch(name)
    if match:
        return QCoreApplication.translate("DomainLabels", "Cas {number}").format(
            number=match.group(1),
        )
    return name


def load_type_label(load_type: str) -> str:
    """Return a translated label for a load type code."""
    labels = {
        "dead": QCoreApplication.translate("DomainLabels", "Permanente (G)"),
        "permanent": QCoreApplication.translate("DomainLabels", "Permanente (G)"),
        "live": QCoreApplication.translate("DomainLabels", "Exploitation (Q)"),
        "variable": QCoreApplication.translate("DomainLabels", "Exploitation (Q)"),
        "snow": QCoreApplication.translate("DomainLabels", "Neige (S)"),
        "wind": QCoreApplication.translate("DomainLabels", "Vent (W)"),
        "seismic": QCoreApplication.translate("DomainLabels", "Sismique (E)"),
        "temperature": QCoreApplication.translate("DomainLabels", "Température (T)"),
        "self_weight": QCoreApplication.translate("DomainLabels", "Poids propre"),
    }
    return labels.get(str(load_type or ""), str(load_type or ""))


def combo_type_label(combo_type: str) -> str:
    """Return a translated label for a combination type code."""
    labels = {
        "ELU": QCoreApplication.translate("DomainLabels", "ELU fondamental"),
        "ELU acc.": QCoreApplication.translate("DomainLabels", "ELU accidentel"),
        "ELU sism.": QCoreApplication.translate("DomainLabels", "ELU sismique"),
        "ELS car.": QCoreApplication.translate("DomainLabels", "ELS caractéristique"),
        "ELS freq.": QCoreApplication.translate("DomainLabels", "ELS fréquente"),
        "ELS fréq.": QCoreApplication.translate("DomainLabels", "ELS fréquente"),
        "ELS QP": QCoreApplication.translate("DomainLabels", "ELS quasi-permanente"),
        "ELS quasi-perm.": QCoreApplication.translate(
            "DomainLabels",
            "ELS quasi-permanente",
        ),
        "ULS": QCoreApplication.translate("DomainLabels", "ELU fondamental"),
        "SLS_char": QCoreApplication.translate("DomainLabels", "ELS caractéristique"),
        "SLS_freq": QCoreApplication.translate("DomainLabels", "ELS fréquente"),
        "SLS_perm": QCoreApplication.translate(
            "DomainLabels",
            "ELS quasi-permanente",
        ),
        "seismic": QCoreApplication.translate("DomainLabels", "ELU sismique"),
        "Manuelle": QCoreApplication.translate("DomainLabels", "Manuelle"),
        "Manual": QCoreApplication.translate("DomainLabels", "Manuelle"),
    }
    return labels.get(str(combo_type or ""), str(combo_type or ""))


def tagged_load_label(load: "LoadData | None", tag: int) -> str:
    """Return a translated load label with its model tag."""
    name = load_name_label(load) if load is not None else f"T{tag}"
    return QCoreApplication.translate("DomainLabels", "{name} (T{tag})").format(
        name=name,
        tag=tag,
    )


def analysis_load_case_label(load: "LoadData", tag: int) -> str:
    """Return the GUI label used for a solved load case."""
    return QCoreApplication.translate("DomainLabels", "{name} (cas {tag})").format(
        name=load_name_label(load),
        tag=tag,
    )


def analysis_combination_label(combo: "CombinationData", tag: int) -> str:
    """Return the GUI label used for a solved combination."""
    return QCoreApplication.translate("DomainLabels", "{name} (combo {tag})").format(
        name=combo.name,
        tag=tag,
    )


def combination_formula_label(
    combo: "CombinationData",
    loads: dict[int, "LoadData"],
) -> str:
    """Return a translated combination formula for GUI previews."""
    parts: list[str] = []
    for load_tag, factor in sorted(combo.factors.items()):
        load = loads.get(load_tag)
        name = load_name_label(load) if load is not None else f"L{load_tag}"
        if factor == 1.0:
            parts.append(name)
        else:
            parts.append(
                QCoreApplication.translate("DomainLabels", "{factor}×{name}").format(
                    factor=f"{factor:.2f}",
                    name=name,
                )
            )
    return " + ".join(parts)

