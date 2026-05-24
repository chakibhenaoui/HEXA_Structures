"""Structured quadrilateral meshing for user plates."""

from __future__ import annotations

from dataclasses import dataclass
import math

from core.geometry.plate_intersections import (
    PlateBarIntersectionKind,
    PlateIntersectionReport,
    PlateNodeLocation,
    detect_plate_intersections,
    plate_local_basis,
)
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
    u_values: tuple[float, ...] = ()
    v_values: tuple[float, ...] = ()


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
    report = _plate_intersection_report(source_project, target_project, plate)
    u_values, v_values = _grid_values_from_report(
        source_project,
        plate,
        report,
        nx,
        ny,
    )
    mesh_nx = len(u_values) - 1
    mesh_ny = len(v_values) - 1

    node_tags: dict[tuple[int, int], int] = {}
    node_lookup = _build_node_lookup(target_project)
    corner_map = {
        (0, 0): plate.corner_node_tags[0],
        (mesh_nx, 0): plate.corner_node_tags[1],
        (mesh_nx, mesh_ny): plate.corner_node_tags[2],
        (0, mesh_ny): plate.corner_node_tags[3],
    }

    for j, v in enumerate(v_values):
        for i, u in enumerate(u_values):
            key = (i, j)
            if key in corner_map:
                tag = int(corner_map[key])
                node_tags[key] = tag
                node_lookup.setdefault(_node_key(_node_xyz(target_project, tag)), tag)
                continue
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
    for j in range(mesh_ny):
        for i in range(mesh_nx):
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
        mesh_nx=mesh_nx,
        mesh_ny=mesh_ny,
        u_values=tuple(u_values),
        v_values=tuple(v_values),
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


def _plate_intersection_report(
    source_project: ProjectModel,
    target_project: ProjectModel,
    plate: PlateRegionData,
) -> PlateIntersectionReport:
    reports = getattr(target_project, "plate_intersection_reports", {}) or {}
    report = reports.get(int(plate.tag))
    if report is not None:
        return report
    return detect_plate_intersections(source_project, plate)


def _grid_values_from_report(
    project: ProjectModel,
    plate: PlateRegionData,
    report: PlateIntersectionReport,
    mesh_nx: int,
    mesh_ny: int,
    *,
    tol: float = 1e-6,
) -> tuple[list[float], list[float]]:
    forced_u_values: list[float] = []
    forced_v_values: list[float] = []

    for hit in report.node_hits:
        if hit.location in {
            PlateNodeLocation.INSIDE,
            PlateNodeLocation.ON_EDGE,
            PlateNodeLocation.ON_CORNER,
        }:
            forced_u_values.append(float(hit.u))
            forced_v_values.append(float(hit.v))

    _add_forced_values_from_aligned_bars(
        project,
        plate,
        report,
        forced_u_values,
        forced_v_values,
        tol=tol,
    )

    u_boundaries = _merge_param_values([0.0, *forced_u_values, 1.0], tol=tol)
    v_boundaries = _merge_param_values([0.0, *forced_v_values, 1.0], tol=tol)

    return (
        _subdivide_param_spans(u_boundaries, mesh_nx, tol=tol),
        _subdivide_param_spans(v_boundaries, mesh_ny, tol=tol),
    )


def _add_forced_values_from_aligned_bars(
    project: ProjectModel,
    plate: PlateRegionData,
    report: PlateIntersectionReport,
    forced_u_values: list[float],
    forced_v_values: list[float],
    *,
    tol: float,
) -> None:
    basis = plate_local_basis(project, plate, tol=tol)
    param_tol = basis.param_tol(tol)
    compatible_bar_hits = {
        PlateBarIntersectionKind.LIES_IN_PLATE_PLANE,
        PlateBarIntersectionKind.CROSSES_PLATE_EDGE,
    }
    for hit in report.bar_hits:
        if hit.kind not in compatible_bar_hits:
            continue
        element = project.elements.get(int(hit.element_tag))
        if element is None:
            continue
        first = project.nodes.get(int(element.node_i))
        second = project.nodes.get(int(element.node_j))
        if first is None or second is None:
            continue
        u1, v1, _d1 = basis.project(
            (float(first.x), float(first.y), float(first.z))
        )
        u2, v2, _d2 = basis.project(
            (float(second.x), float(second.y), float(second.z))
        )
        if abs(v2 - v1) <= param_tol:
            forced_v_values.append((v1 + v2) / 2.0)
            forced_u_values.extend([u1, u2])
        elif abs(u2 - u1) <= param_tol:
            forced_u_values.append((u1 + u2) / 2.0)
            forced_v_values.extend([v1, v2])


def _merge_param_values(values: list[float], *, tol: float) -> list[float]:
    clamped = sorted(_clamp_param(value, tol) for value in values)
    merged: list[float] = []
    for value in clamped:
        if value < -tol or value > 1.0 + tol:
            continue
        if not merged or abs(value - merged[-1]) > tol:
            merged.append(value)
            continue
        if abs(value) <= tol or abs(value - 1.0) <= tol:
            merged[-1] = _clamp_param(value, tol)
    if not merged or abs(merged[0]) > tol:
        merged.insert(0, 0.0)
    else:
        merged[0] = 0.0
    if abs(merged[-1] - 1.0) > tol:
        merged.append(1.0)
    else:
        merged[-1] = 1.0
    return merged


def _subdivide_param_spans(
    boundaries: list[float],
    nominal_divisions: int,
    *,
    tol: float,
) -> list[float]:
    if nominal_divisions < 1:
        raise ValueError("nominal_divisions must be >= 1.")
    clean_boundaries = _merge_param_values(boundaries, tol=tol)
    target_step = 1.0 / float(nominal_divisions)
    values = [clean_boundaries[0]]
    for start, end in zip(clean_boundaries, clean_boundaries[1:]):
        span = float(end) - float(start)
        if span <= tol:
            continue
        divisions = max(1, int(math.floor(span / target_step + 0.5)))
        for index in range(1, divisions + 1):
            ratio = index / float(divisions)
            value = start + span * ratio
            values.append(_clamp_param(value, tol))
    return _merge_param_values(values, tol=tol)


def _clamp_param(value: float, tol: float) -> float:
    value = float(value)
    if abs(value) <= tol:
        return 0.0
    if abs(value - 1.0) <= tol:
        return 1.0
    return value


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
