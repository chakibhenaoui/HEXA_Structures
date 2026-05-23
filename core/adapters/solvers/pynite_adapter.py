"""PyNite adapter for the solver application port."""

from __future__ import annotations

from core.solvers.pynite_backend import PyNiteBackend


class PyNiteSolverAdapter(PyNiteBackend):
    """Adapter exposing the existing PyNite backend as a solver port."""
