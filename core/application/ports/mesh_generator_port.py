"""Port for mesh generation adapters."""

from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from core.model_data import PlateRegionData, ProjectModel


class GeneratedPlateMeshPort(Protocol):
    """Minimal mesh data needed by application use cases."""

    plate_tag: int
    node_tags: dict[tuple[int, int], int]
    surface_tags: list[int]
    mesh_nx: int
    mesh_ny: int


class MeshGeneratorPort(Protocol):
    """Contract for generating analysis meshes from user-level regions."""

    def generate_plate_region_mesh(
        self,
        source_project: "ProjectModel",
        target_project: "ProjectModel",
        plate: "PlateRegionData",
    ) -> GeneratedPlateMeshPort:
        """Generate an internal mesh for a user plate region."""
