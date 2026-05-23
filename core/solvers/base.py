"""Base types for the multi-solver architecture."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SolverEngine(str, Enum):
    """Solver engine."""

    PYNITE = "pynite"
    OPENSEES = "opensees"


class AnalysisFeature(str, Enum):
    """Analysis feature."""

    STATIC_LINEAR = "static_linear"
    MODAL = "modal"
    PDELTA = "pdelta"
    RESPONSE_SPECTRUM = "response_spectrum"
    PUSHOVER = "pushover"
    TIME_HISTORY = "time_history"


class CapabilityLevel(str, Enum):
    """Capability level."""

    READY = "ready"
    ENGINE_ONLY = "engine_only"
    PLANNED = "planned"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AnalysisCapability:
    """Analysis capability."""

    feature: AnalysisFeature
    level: CapabilityLevel
    note: str = ""


@dataclass(frozen=True)
class SolverInfo:
    """Solver info."""

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
