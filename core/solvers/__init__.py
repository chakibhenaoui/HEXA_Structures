"""Solver backend package."""

from core.solvers.base import (
    AnalysisCapability,
    AnalysisFeature,
    CapabilityLevel,
    SolverEngine,
    SolverInfo,
)

__all__ = [
    "AnalysisCapability",
    "AnalysisFeature",
    "CapabilityLevel",
    "OpenSeesBackend",
    "PyNiteBackend",
    "SolverEngine",
    "SolverInfo",
    "SolverManager",
]


def __getattr__(name: str):
    """Lazy-load solver implementations to avoid import cycles at startup."""
    if name == "OpenSeesBackend":
        from core.solvers.opensees_backend import OpenSeesBackend

        return OpenSeesBackend
    if name == "PyNiteBackend":
        from core.solvers.pynite_backend import PyNiteBackend

        return PyNiteBackend
    if name == "SolverManager":
        from core.solvers.solver_manager import SolverManager

        return SolverManager
    raise AttributeError(f"module 'core.solvers' has no attribute {name!r}")
