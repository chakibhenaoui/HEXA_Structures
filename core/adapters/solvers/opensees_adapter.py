"""OpenSees adapter for the solver application port."""

from __future__ import annotations

from core.solvers.opensees_backend import OpenSeesBackend


class OpenSeesSolverAdapter(OpenSeesBackend):
    """Adapter exposing the existing OpenSees backend as a solver port."""
