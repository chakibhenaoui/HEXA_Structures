"""Use case for building the temporary analysis model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.application.ports import GeneratedPlateMeshPort, MeshGeneratorPort
from core.model_data import NodeData, PlateEdgeSupportData, SurfaceLoad

if TYPE_CHECKING:
    from core.model_data import ProjectModel


@dataclass(frozen=True)
class BuildAnalysisModel:
    """Build an analysis model through an injected mesh generator."""

    mesh_generator: MeshGeneratorPort

    def execute(self, project: "ProjectModel") -> "ProjectModel":
        """Return a calculation-ready copy of the user project."""
        analysis_project = deepcopy(project)
        generated_meshes: dict[int, GeneratedPlateMeshPort] = {}

        for plate in project.plate_regions.values():
            mesh = self.mesh_generator.generate_plate_region_mesh(
                project,
                analysis_project,
                plate,
            )
            generated_meshes[plate.tag] = mesh
            _propagate_plate_surface_loads(project, analysis_project, mesh)
            _propagate_plate_edge_supports(project, analysis_project, mesh)

        setattr(analysis_project, "generated_plate_meshes", generated_meshes)
        return analysis_project


def _propagate_plate_surface_loads(
    source_project: "ProjectModel",
    target_project: "ProjectModel",
    mesh: GeneratedPlateMeshPort,
) -> None:
    for load in source_project.plate_surface_loads:
        if int(load.plate_tag) != int(mesh.plate_tag):
            continue
        for surface_tag in mesh.surface_tags:
            target_project.surface_loads.append(
                SurfaceLoad(
                    load_tag=load.load_tag,
                    surface_tag=surface_tag,
                    qx=load.qx,
                    qy=load.qy,
                    qz=load.qz,
                )
            )


def _propagate_plate_edge_supports(
    source_project: "ProjectModel",
    target_project: "ProjectModel",
    mesh: GeneratedPlateMeshPort,
) -> None:
    for support in source_project.plate_edge_supports:
        if int(support.plate_tag) != int(mesh.plate_tag):
            continue
        for node_tag in _edge_node_tags(mesh, support, mesh.mesh_nx, mesh.mesh_ny):
            node = target_project.nodes[int(node_tag)]
            _merge_node_fixities(node, support.fixities)


def _edge_node_tags(
    mesh: GeneratedPlateMeshPort,
    support: PlateEdgeSupportData,
    mesh_nx: int,
    mesh_ny: int,
) -> list[int]:
    edge = str(support.edge).strip()
    if edge == "12":
        return [mesh.node_tags[(i, 0)] for i in range(mesh_nx + 1)]
    if edge == "23":
        return [mesh.node_tags[(mesh_nx, j)] for j in range(mesh_ny + 1)]
    if edge == "34":
        return [mesh.node_tags[(i, mesh_ny)] for i in range(mesh_nx + 1)]
    if edge == "41":
        return [mesh.node_tags[(0, j)] for j in range(mesh_ny + 1)]
    raise ValueError(f"Bord de plaque inconnu: {support.edge}")


def _merge_node_fixities(
    node: NodeData,
    fixities: tuple[int, int, int, int, int, int],
) -> None:
    if len(fixities) != 6:
        raise ValueError("Plate edge support fixities must contain 6 values.")
    existing = tuple(int(value) for value in node.fixities[:6])
    incoming = tuple(int(value) for value in fixities)
    node.fixities = tuple(
        1 if existing[index] or incoming[index] else 0
        for index in range(6)
    )
