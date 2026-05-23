"""Structured quadrilateral plate mesher adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.plate_mesher import generate_plate_region_mesh

if TYPE_CHECKING:
    from core.model_data import PlateRegionData, ProjectModel
    from core.plate_mesher import GeneratedPlateMesh


class StructuredQuadPlateMesher:
    """Adapter exposing the existing plate mesher through a mesh port."""

    def generate_plate_region_mesh(
        self,
        source_project: "ProjectModel",
        target_project: "ProjectModel",
        plate: "PlateRegionData",
    ) -> "GeneratedPlateMesh":
        """Generate an internal structured quad mesh for a plate region."""
        return generate_plate_region_mesh(source_project, target_project, plate)
