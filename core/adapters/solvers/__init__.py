"""Solver adapters."""

__all__ = [
    "HexaInternalSolverAdapter",
    "OpenSeesSolverAdapter",
    "PyNiteSolverAdapter",
    "SolverAdapterPlugin",
    "get_solver_plugin_id_map",
    "get_solver_plugin_map",
    "get_solver_plugin_registry",
    "get_solver_plugins",
]


def __getattr__(name: str):
    """Lazy-load solver adapter exports to avoid backend import cycles."""
    if name == "HexaInternalSolverAdapter":
        from core.adapters.solvers.hexa_internal_adapter import HexaInternalSolverAdapter

        return HexaInternalSolverAdapter
    if name == "OpenSeesSolverAdapter":
        from core.adapters.solvers.opensees_adapter import OpenSeesSolverAdapter

        return OpenSeesSolverAdapter
    if name == "PyNiteSolverAdapter":
        from core.adapters.solvers.pynite_adapter import PyNiteSolverAdapter

        return PyNiteSolverAdapter
    if name in {
        "SolverAdapterPlugin",
        "get_solver_plugin_id_map",
        "get_solver_plugin_map",
        "get_solver_plugin_registry",
        "get_solver_plugins",
    }:
        from core.adapters.solvers import registry

        return getattr(registry, name)
    raise AttributeError(f"module 'core.adapters.solvers' has no attribute {name!r}")
