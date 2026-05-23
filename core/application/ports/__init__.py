"""Application ports.

Ports describe what the application needs from external adapters without
depending on GUI, persistence engines, or solver implementations.
"""

from core.application.ports.connection_design_port import ConnectionDesignPort
from core.application.ports.mesh_generator_port import (
    GeneratedPlateMeshPort,
    MeshGeneratorPort,
)
from core.application.ports.plugin_loader_port import PluginLoaderPort
from core.application.ports.project_repository_port import ProjectRepositoryPort
from core.application.ports.solver_plugin_port import SolverPluginPort
from core.application.ports.solver_port import SolverPort

__all__ = [
    "ConnectionDesignPort",
    "MeshGeneratorPort",
    "GeneratedPlateMeshPort",
    "PluginLoaderPort",
    "ProjectRepositoryPort",
    "SolverPluginPort",
    "SolverPort",
]
