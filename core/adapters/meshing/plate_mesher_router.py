"""Route plate regions to the compatible analysis mesher."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.adapters.meshing.constrained_triangular_plate_mesher import (
    ConstrainedTriangularPlateMesher,
)
from core.adapters.meshing.structured_quad_plate_mesher import StructuredQuadPlateMesher
from core.plate_mesh_settings import supports_structured_quad_mesh

if TYPE_CHECKING:
    from core.application.ports import MeshGeneratorPort
    from core.model_data import PlateRegionData, ProjectModel
    from core.plate_mesher import GeneratedPlateMesh


@dataclass
class PlateMesherRouter:
    """Use structured quads for four corners and triangles for polygons."""

    structured_mesher: "MeshGeneratorPort" = field(
        default_factory=StructuredQuadPlateMesher
    )
    polygonal_mesher: "MeshGeneratorPort" = field(
        default_factory=ConstrainedTriangularPlateMesher
    )

    def generate_plate_region_mesh(
        self,
        source_project: "ProjectModel",
        target_project: "ProjectModel",
        plate: "PlateRegionData",
    ) -> "GeneratedPlateMesh":
        """Generate one analysis mesh with the compatible adapter."""
        mesher = (
            self.structured_mesher
            if supports_structured_quad_mesh(source_project, plate)
            else self.polygonal_mesher
        )
        return mesher.generate_plate_region_mesh(
            source_project,
            target_project,
            plate,
        )
