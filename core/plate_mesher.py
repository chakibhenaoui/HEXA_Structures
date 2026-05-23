"""Structured quadrilateral meshing for user plates."""

from __future__ import annotations

from dataclasses import dataclass

from core.model_data import (
    PlateRegionData,
    ProjectModel,
    SURFACE_FORMULATION_TYPES,
    normalize_surface_formulation,
    surface_type_from_formulation,
)
from core.plate_mesh_settings import effective_plate_mesh_divisions


@dataclass(frozen=True)
class GeneratedPlateMesh:
    """Generated plate mesh."""

    plate_tag: int
    node_tags: dict[tuple[int, int], int]
    surface_tags: list[int]
    mesh_nx: int
    mesh_ny: int


def generate_plate_region_mesh(
    source_project: ProjectModel,
    target_project: ProjectModel,
    plate: PlateRegionData,
) -> GeneratedPlateMesh:
    """Handle generate plate region mesh."""
    _validate_plate(source_project, target_project, plate)
    corners = [_node_xyz(source_project, tag) for tag in plate.corner_node_tags]
    nx, ny = effective_plate_mesh_divisions(source_project, plate)
    formulation = _effective_plate_formulation(source_project, plate)

    node_tags: dict[tuple[int, int], int] = {}
    node_lookup = _build_node_lookup(target_project)
    corner_map = {
        (0, 0): plate.corner_node_tags[0],
        (nx, 0): plate.corner_node_tags[1],
        (nx, ny): plate.corner_node_tags[2],
        (0, ny): plate.corner_node_tags[3],
    }

    for j in range(ny + 1):
        v = j / float(ny)
        for i in range(nx + 1):
            key = (i, j)
            if key in corner_map:
                tag = int(corner_map[key])
                node_tags[key] = tag
                node_lookup.setdefault(_node_key(_node_xyz(target_project, tag)), tag)
                continue
            u = i / float(nx)
            x, y, z = _bilinear_point(corners, u, v)
            existing_tag = node_lookup.get(_node_key((x, y, z)))
            if existing_tag is not None:
                node_tags[key] = existing_tag
                continue
            node = target_project.add_node(x, y, z)
            node_tags[key] = node.tag
            node_lookup[_node_key((x, y, z))] = node.tag

    surface_tags: list[int] = []
    surface_type = surface_type_from_formulation(formulation)
    for j in range(ny):
        for i in range(nx):
            surface = target_project.add_surface_element(
                (
                    node_tags[(i, j)],
                    node_tags[(i + 1, j)],
                    node_tags[(i + 1, j + 1)],
                    node_tags[(i, j + 1)],
                ),
                section_tag=plate.section_tag,
                surface_type=surface_type,
                formulation=formulation,
            )
            surface_tags.append(surface.tag)

    return GeneratedPlateMesh(
        plate_tag=plate.tag,
        node_tags=node_tags,
        surface_tags=surface_tags,
        mesh_nx=nx,
        mesh_ny=ny,
    )


def _validate_plate(
    source_project: ProjectModel,
    target_project: ProjectModel,
    plate: PlateRegionData,
) -> None:
    if len(plate.corner_node_tags) != 4:
        raise ValueError("A plate region requires exactly 4 corner nodes.")
    if len(set(plate.corner_node_tags)) != 4:
        raise ValueError("Plate region corner nodes must be distinct.")
    for tag in plate.corner_node_tags:
        if tag not in source_project.nodes:
            raise ValueError(f"Plate region P{plate.tag} references missing node N{tag}.")
        if tag not in target_project.nodes:
            raise ValueError(
                f"Target analysis model is missing plate corner node N{tag}."
            )

    if int(plate.mesh_nx) < 1 or int(plate.mesh_ny) < 1:
        raise ValueError("Plate region mesh_nx and mesh_ny must be >= 1.")

    section = target_project.sections.get(int(plate.section_tag))
    if section is None:
        raise ValueError(f"Plate region P{plate.tag} references missing section.")
    if not section.is_surface:
        raise ValueError(
            f"Plate region P{plate.tag} requires a surface section; "
            f"section T{plate.section_tag} is a {section.section_type} section."
        )

    formulation = _effective_plate_formulation(source_project, plate)
    if formulation not in SURFACE_FORMULATION_TYPES:
        raise NotImplementedError(
            f"La formulation plaque {plate.formulation} n'est pas disponible "
            "pour les plaques utilisateur."
        )


def _node_xyz(project: ProjectModel, node_tag: int) -> tuple[float, float, float]:
    node = project.nodes[int(node_tag)]
    return float(node.x), float(node.y), float(node.z)


def _effective_plate_formulation(
    project: ProjectModel,
    plate: PlateRegionData,
) -> str:
    section = project.sections.get(int(plate.section_tag))
    if section is not None and section.is_surface:
        return section.surface_formulation
    return normalize_surface_formulation(plate.formulation)


def _node_key(
    point: tuple[float, float, float],
    ndigits: int = 9,
) -> tuple[float, float, float]:
    return tuple(round(float(value), ndigits) for value in point)


def _build_node_lookup(project: ProjectModel) -> dict[tuple[float, float, float], int]:
    lookup: dict[tuple[float, float, float], int] = {}
    for tag, node in sorted(project.nodes.items()):
        lookup.setdefault(
            _node_key((float(node.x), float(node.y), float(node.z))),
            int(tag),
        )
    return lookup


def _bilinear_point(
    corners: list[tuple[float, float, float]],
    u: float,
    v: float,
) -> tuple[float, float, float]:
    weights = (
        (1.0 - u) * (1.0 - v),
        u * (1.0 - v),
        u * v,
        (1.0 - u) * v,
    )
    return tuple(
        sum(weight * point[index] for weight, point in zip(weights, corners))
        for index in range(3)
    )
