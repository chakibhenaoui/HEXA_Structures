"""Analysis-only subdivision for bars coupled to generated plate meshes."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import TYPE_CHECKING

from core.geometry.plate_intersections import PlateBarIntersectionKind
from core.model_data import ElementData

if TYPE_CHECKING:
    from core.geometry.plate_intersections import PlateIntersectionReport
    from core.model_data import ProjectModel
    from core.plate_mesher import GeneratedPlateMesh


Point3D = tuple[float, float, float]

_COMPATIBLE_COPLANAR_HIT_KINDS = {
    PlateBarIntersectionKind.LIES_IN_PLATE_PLANE,
    PlateBarIntersectionKind.CROSSES_PLATE_EDGE,
}


@dataclass(frozen=True)
class GeneratedBarMesh:
    """Analysis-only mesh generated from one user bar."""

    source_element_tag: int
    segment_tags: tuple[int, ...]
    node_tags: tuple[int, ...]


def generate_coplanar_bar_meshes(
    source_project: "ProjectModel",
    target_project: "ProjectModel",
    generated_plate_meshes: dict[int, "GeneratedPlateMesh"],
    plate_intersection_reports: dict[int, "PlateIntersectionReport"],
    *,
    tol: float = 1e-6,
) -> dict[int, GeneratedBarMesh]:
    """Split compatible coplanar bars on plate mesh nodes in the analysis model."""
    candidate_nodes_by_element: dict[int, set[int]] = {}
    for plate_tag, report in plate_intersection_reports.items():
        mesh = generated_plate_meshes.get(int(plate_tag))
        if mesh is None:
            continue
        mesh_node_tags = {int(tag) for tag in mesh.node_tags.values()}
        for hit in report.bar_hits:
            if hit.kind not in _COMPATIBLE_COPLANAR_HIT_KINDS:
                continue
            element_tag = int(hit.element_tag)
            candidate_nodes_by_element.setdefault(element_tag, set()).update(
                mesh_node_tags
            )

    next_element_tag = max(target_project.elements.keys(), default=0) + 1
    generated: dict[int, GeneratedBarMesh] = {}
    for source_element_tag in sorted(candidate_nodes_by_element):
        source_element = source_project.elements.get(int(source_element_tag))
        analysis_element = target_project.elements.get(int(source_element_tag))
        if source_element is None or analysis_element is None:
            continue

        candidate_tags = set(candidate_nodes_by_element[source_element_tag])
        candidate_tags.update((int(source_element.node_i), int(source_element.node_j)))
        ordered_node_tags = _ordered_node_tags_on_segment(
            target_project,
            int(source_element.node_i),
            int(source_element.node_j),
            candidate_tags,
            tol=tol,
        )
        if len(ordered_node_tags) <= 2:
            continue

        target_project.elements.pop(int(source_element_tag), None)
        source_loads = [
            load
            for load in target_project.element_loads
            if int(load.element_tag) == int(source_element_tag)
        ]
        target_project.element_loads = [
            load
            for load in target_project.element_loads
            if int(load.element_tag) != int(source_element_tag)
        ]

        segment_tags: list[int] = []
        for node_i, node_j in zip(ordered_node_tags, ordered_node_tags[1:]):
            if int(node_i) == int(node_j):
                continue
            tag = next_element_tag
            next_element_tag += 1
            target_project.elements[tag] = ElementData(
                tag=tag,
                node_i=int(node_i),
                node_j=int(node_j),
                section_tag=int(analysis_element.section_tag),
                element_type=analysis_element.element_type,
                orientation_vector=analysis_element.orientation_vector,
                roll_angle_deg=float(analysis_element.roll_angle_deg),
            )
            segment_tags.append(tag)
            for load in source_loads:
                target_project.element_loads.append(replace(load, element_tag=tag))

        if segment_tags:
            generated[int(source_element_tag)] = GeneratedBarMesh(
                source_element_tag=int(source_element_tag),
                segment_tags=tuple(segment_tags),
                node_tags=tuple(ordered_node_tags),
            )

    return generated


def _ordered_node_tags_on_segment(
    project: "ProjectModel",
    node_i: int,
    node_j: int,
    candidate_node_tags: set[int],
    *,
    tol: float,
) -> list[int]:
    p_i = _node_xyz(project, node_i)
    p_j = _node_xyz(project, node_j)
    direction = _sub(p_j, p_i)
    length_sq = _dot(direction, direction)
    if length_sq <= tol * tol:
        return []

    candidates: list[tuple[float, int]] = []
    for tag in sorted(candidate_node_tags):
        if int(tag) not in project.nodes:
            continue
        parameter = _segment_parameter(p_i, direction, length_sq, _node_xyz(project, tag))
        if parameter < -tol or parameter > 1.0 + tol:
            continue
        projected = _add(p_i, _scale(direction, parameter))
        if _distance(projected, _node_xyz(project, tag)) > tol:
            continue
        candidates.append((_clamp01(parameter, tol), int(tag)))

    candidates.sort(key=lambda item: (item[0], item[1]))
    ordered: list[tuple[float, int]] = []
    for parameter, tag in candidates:
        if ordered and abs(parameter - ordered[-1][0]) <= tol:
            if tag in {node_i, node_j}:
                ordered[-1] = (parameter, tag)
            continue
        ordered.append((parameter, tag))

    return [tag for _parameter, tag in ordered]


def _segment_parameter(
    start: Point3D,
    direction: Point3D,
    length_sq: float,
    point: Point3D,
) -> float:
    return _dot(_sub(point, start), direction) / length_sq


def _node_xyz(project: "ProjectModel", node_tag: int) -> Point3D:
    node = project.nodes[int(node_tag)]
    return float(node.x), float(node.y), float(node.z)


def _clamp01(value: float, tol: float) -> float:
    if abs(value) <= tol:
        return 0.0
    if abs(value - 1.0) <= tol:
        return 1.0
    return min(1.0, max(0.0, float(value)))


def _distance(a: Point3D, b: Point3D) -> float:
    return math.sqrt(_dot(_sub(a, b), _sub(a, b)))


def _add(a: Point3D, b: Point3D) -> Point3D:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Point3D, b: Point3D) -> Point3D:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _scale(a: Point3D, factor: float) -> Point3D:
    return a[0] * factor, a[1] * factor, a[2] * factor


def _dot(a: Point3D, b: Point3D) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
