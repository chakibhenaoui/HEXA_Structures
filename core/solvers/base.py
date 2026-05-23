"""
Types de base pour l'architecture multi-solveur.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SolverEngine(str, Enum):
    """Moteurs de calcul supportes par l'application."""

    PYNITE = "pynite"
    OPENSEES = "opensees"


class AnalysisFeature(str, Enum):
    """Familles d'analyses pilotees par le logiciel."""

    STATIC_LINEAR = "static_linear"
    MODAL = "modal"
    PDELTA = "pdelta"
    RESPONSE_SPECTRUM = "response_spectrum"
    PUSHOVER = "pushover"
    TIME_HISTORY = "time_history"


class CapabilityLevel(str, Enum):
    """Niveau de disponibilité d'une analyse pour un moteur donne."""

    READY = "ready"
    ENGINE_ONLY = "engine_only"
    PLANNED = "planned"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AnalysisCapability:
    """Capacite d'un moteur pour une famille d'analyse."""

    feature: AnalysisFeature
    level: CapabilityLevel
    note: str = ""


@dataclass(frozen=True)
class SolverInfo:
    """état d'un solveur détecté sur la machine."""

    engine: SolverEngine
    label: str
    available: bool
    version: str | None = None
    install_hint: str | None = None
    is_default: bool = False
    solver_id: str | None = None
    plugin_version: str | None = None
    api_version: str | None = None
    source: str = "builtin"
