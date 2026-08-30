"""Constrained triangular meshing for planar polygonal plate regions."""

from __future__ import annotations

from importlib import import_module
import math
from typing import Any

import numpy as np

from core.model_data import PlateRegionData, ProjectModel
from core.plate_mesh_settings import polygonal_plate_mesh_recommendation
from core.plate_mesher import GeneratedPlateMesh
from core.surface_geometry import SurfacePolygonGeometry, validate_surface_polygon


MAX_POLYGONAL_MESH_TRIANGLES = 100_000
_ANALYSIS_FORMULATION = "ASDShellT3"


class PolygonalPlateMesherUnavailable(RuntimeError):
    """Raised when the optional constrained triangulation backend is absent."""


class PolygonalPlateMeshError(ValueError):
    """Raised when a valid polygon cannot produce a usable analysis mesh."""


def generate_polygonal_plate_mesh(
    source_project: ProjectModel,
    target_project: ProjectModel,
    plate: PlateRegionData,
) -> GeneratedPlateMesh:
    """Generate an analysis-only constrained triangular mesh for one region."""
    _validate_plate(source_project, target_project, plate)
    boundary_points = [_node_xyz(source_project, tag) for tag in plate.boundary_node_tags]
    geometry = validate_surface_polygon(boundary_points)
    recommendation = polygonal_plate_mesh_recommendation(source_project, plate)
    edge_target_sizes = _shared_edge_target_sizes(
        source_project,
        plate,
        recommendation.target_size,
    )
    vertices, segments, segment_markers = _build_boundary_pslg(
        geometry,
        edge_target_sizes,
    )
    triangulate = _load_triangulate()
    flags = (
        f"pq{recommendation.min_angle_deg:.1f}"
        f"a{recommendation.max_triangle_area:.17g}YzQ"
    )
    try:
        output = triangulate(
            {
                "vertices": vertices,
                "segments": segments,
                "segment_markers": segment_markers,
            },
            flags,
        )
    except Exception as exc:
        raise PolygonalPlateMeshError(
            f"Polygonal plate P{plate.tag} could not be triangulated: {exc}"
        ) from exc

    output_vertices = np.asarray(output.get("vertices", ()), dtype=float)
    output_triangles = np.asarray(output.get("triangles", ()), dtype=int)
    if output_vertices.ndim != 2 or output_vertices.shape[1:] != (2,):
        raise PolygonalPlateMeshError(
            f"Polygonal plate P{plate.tag} returned invalid mesh vertices."
        )
    if output_triangles.ndim != 2 or output_triangles.shape[1:] != (3,):
        raise PolygonalPlateMeshError(
            f"Polygonal plate P{plate.tag} returned invalid triangular cells."
        )
    if len(output_triangles) > MAX_POLYGONAL_MESH_TRIANGLES:
        raise PolygonalPlateMeshError(
            f"Polygonal plate P{plate.tag} generated {len(output_triangles)} triangles; "
            f"the safety limit is {MAX_POLYGONAL_MESH_TRIANGLES}."
        )

    node_lookup = _build_node_lookup(target_project)
    node_tags: dict[object, int] = {}
    for vertex_index, uv in enumerate(output_vertices):
        point = _point_from_uv(geometry, float(uv[0]), float(uv[1]))
        key = _node_key(point)
        node_tag = node_lookup.get(key)
        if node_tag is None:
            node = target_project.add_node(*point)
            node_tag = int(node.tag)
            node_lookup[key] = node_tag
        node_tags[int(vertex_index)] = node_tag

    cell_node_tags: list[tuple[int, ...]] = []
    surface_tags: list[int] = []
    mesh_area = 0.0
    for triangle in output_triangles:
        first, second, third = (int(value) for value in triangle)
        signed_double_area = _orientation_2d(
            output_vertices[first],
            output_vertices[second],
            output_vertices[third],
        )
        if abs(signed_double_area) <= 1e-15:
            raise PolygonalPlateMeshError(
                f"Polygonal plate P{plate.tag} generated a zero-area triangle."
            )
        if signed_double_area < 0.0:
            second, third = third, second
            signed_double_area = -signed_double_area
        mesh_area += 0.5 * signed_double_area
        cell_nodes = (
            node_tags[first],
            node_tags[second],
            node_tags[third],
        )
        surface = target_project.add_surface_element(
            cell_nodes,
            section_tag=plate.section_tag,
            surface_type="shell",
            formulation=_ANALYSIS_FORMULATION,
        )
        cell_node_tags.append(cell_nodes)
        surface_tags.append(int(surface.tag))

    area_tolerance = max(geometry.area * 1e-8, 1e-10)
    if not math.isclose(mesh_area, geometry.area, abs_tol=area_tolerance):
        raise PolygonalPlateMeshError(
            f"Polygonal plate P{plate.tag} mesh area {mesh_area:.12g} does not "
            f"match boundary area {geometry.area:.12g}."
        )

    boundary_node_tags = _output_boundary_node_tags(
        plate,
        output,
        output_vertices,
        node_tags,
        geometry,
    )
    return GeneratedPlateMesh(
        plate_tag=int(plate.tag),
        node_tags=node_tags,
        surface_tags=surface_tags,
        mesh_nx=0,
        mesh_ny=0,
        mesh_kind="constrained_triangular",
        cell_node_tags=tuple(cell_node_tags),
        boundary_node_tags=boundary_node_tags,
        target_size=float(recommendation.target_size),
        local_x_axis=tuple(float(value) for value in geometry.u_axis),
    )


def _load_triangulate():
    try:
        module = import_module("cytriangle")
    except ImportError as exc:
        raise PolygonalPlateMesherUnavailable(
            "Polygonal analysis meshing requires the optional cytriangle package."
        ) from exc
    return module.triangulate


def _validate_plate(
    source_project: ProjectModel,
    target_project: ProjectModel,
    plate: PlateRegionData,
) -> None:
    if len(plate.boundary_node_tags) < 3:
        raise PolygonalPlateMeshError(
            f"Polygonal plate P{plate.tag} requires at least three boundary nodes."
        )
    for tag in plate.boundary_node_tags:
        if int(tag) not in source_project.nodes:
            raise PolygonalPlateMeshError(
                f"Polygonal plate P{plate.tag} references missing node N{tag}."
            )
        if int(tag) not in target_project.nodes:
            raise PolygonalPlateMeshError(
                f"Target analysis model is missing boundary node N{tag}."
            )
    section = target_project.sections.get(int(plate.section_tag))
    if section is None or not section.is_surface:
        raise PolygonalPlateMeshError(
            f"Polygonal plate P{plate.tag} requires a valid surface section."
        )


def _shared_edge_target_sizes(
    project: ProjectModel,
    plate: PlateRegionData,
    default_target_size: float,
) -> tuple[float, ...]:
    targets: list[float] = []
    boundary = tuple(int(tag) for tag in plate.boundary_node_tags)
    for index, start_tag in enumerate(boundary):
        end_tag = boundary[(index + 1) % len(boundary)]
        edge_key = frozenset((start_tag, end_tag))
        shared_targets = [float(default_target_size)]
        for other in project.plate_regions.values():
            if int(other.tag) == int(plate.tag):
                continue
            other_boundary = tuple(int(tag) for tag in other.boundary_node_tags)
            if any(
                frozenset(
                    (
                        other_boundary[other_index],
                        other_boundary[(other_index + 1) % len(other_boundary)],
                    )
                )
                == edge_key
                for other_index in range(len(other_boundary))
            ):
                shared_targets.append(
                    polygonal_plate_mesh_recommendation(project, other).target_size
                )
        targets.append(min(shared_targets))
    return tuple(targets)


def _build_boundary_pslg(
    geometry: SurfacePolygonGeometry,
    edge_target_sizes: tuple[float, ...],
) -> tuple[list[tuple[float, float]], list[tuple[int, int]], list[int]]:
    polygon = geometry.projected_points
    vertices: list[tuple[float, float]] = [polygon[0]]
    segments: list[tuple[int, int]] = []
    markers: list[int] = []
    current_index = 0

    for edge_index, start in enumerate(polygon):
        end = polygon[(edge_index + 1) % len(polygon)]
        edge_length = math.dist(start, end)
        divisions = max(
            1,
            int(math.ceil(edge_length / max(edge_target_sizes[edge_index], 1e-12))),
        )
        for division in range(1, divisions + 1):
            if edge_index == len(polygon) - 1 and division == divisions:
                next_index = 0
            else:
                ratio = division / float(divisions)
                vertices.append(
                    (
                        start[0] + ratio * (end[0] - start[0]),
                        start[1] + ratio * (end[1] - start[1]),
                    )
                )
                next_index = len(vertices) - 1
            segments.append((current_index, next_index))
            markers.append(edge_index + 1)
            current_index = next_index

    return vertices, segments, markers


def _output_boundary_node_tags(
    plate: PlateRegionData,
    output: dict[str, Any],
    output_vertices: np.ndarray,
    node_tags: dict[object, int],
    geometry: SurfacePolygonGeometry,
) -> dict[str, tuple[int, ...]]:
    output_segments = np.asarray(output.get("segments", ()), dtype=int)
    output_markers = np.asarray(output.get("segment_markers", ()), dtype=int).reshape(-1)
    if len(output_segments) != len(output_markers):
        raise PolygonalPlateMeshError(
            f"Polygonal plate P{plate.tag} returned inconsistent boundary markers."
        )

    result: dict[str, tuple[int, ...]] = {}
    polygon = geometry.projected_points
    for edge_index, start in enumerate(polygon):
        end = polygon[(edge_index + 1) % len(polygon)]
        vertex_indices = {
            int(vertex_index)
            for segment, marker in zip(output_segments, output_markers)
            if int(marker) == edge_index + 1
            for vertex_index in segment
        }
        direction = (end[0] - start[0], end[1] - start[1])
        denominator = max(direction[0] ** 2 + direction[1] ** 2, 1e-18)
        ordered_indices = sorted(
            vertex_indices,
            key=lambda vertex_index: (
                (output_vertices[vertex_index][0] - start[0]) * direction[0]
                + (output_vertices[vertex_index][1] - start[1]) * direction[1]
            )
            / denominator,
        )
        result[_edge_label(edge_index, len(polygon))] = tuple(
            int(node_tags[index]) for index in ordered_indices
        )
    return result


def _edge_label(edge_index: int, edge_count: int) -> str:
    start = edge_index + 1
    end = (edge_index + 1) % edge_count + 1
    return f"{start}{end}" if edge_count < 10 else f"{start}:{end}"


def _point_from_uv(
    geometry: SurfacePolygonGeometry,
    u: float,
    v: float,
) -> tuple[float, float, float]:
    return tuple(
        geometry.origin[index]
        + float(u) * geometry.u_axis[index]
        + float(v) * geometry.v_axis[index]
        for index in range(3)
    )


def _orientation_2d(first, second, third) -> float:
    return float(
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _node_xyz(project: ProjectModel, node_tag: int) -> tuple[float, float, float]:
    node = project.nodes[int(node_tag)]
    return float(node.x), float(node.y), float(node.z)


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
