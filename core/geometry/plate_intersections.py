"""Geometry diagnostics for user plate regions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.model_data import PlateRegionData, ProjectModel


class PlateNodeLocation(str, Enum):
    INSIDE = "inside"
    ON_EDGE = "on_edge"
    ON_CORNER = "on_corner"


class PlateBarIntersectionKind(str, Enum):
    CROSSES_PLANE_AT_POINT = "crosses_plane_at_point"
    LIES_IN_PLATE_PLANE = "lies_in_plate_plane"
    CROSSES_PLATE_EDGE = "crosses_plate_edge"
    ENDPOINT_ON_PLATE = "endpoint_on_plate"
    UNSUPPORTED_SKEW_IN_PLANE = "unsupported_skew_in_plane"


@dataclass(frozen=True)
class PlateNodeHit:
    node_tag: int
    location: PlateNodeLocation
    u: float
    v: float
    distance_to_plane: float


@dataclass(frozen=True)
class PlateBarHit:
    element_tag: int
    kind: PlateBarIntersectionKind
    point: tuple[float, float, float] | None = None
    u: float | None = None
    v: float | None = None
    message: str = ""


@dataclass
class PlateIntersectionReport:
    plate_tag: int
    node_hits: list[PlateNodeHit]
    bar_hits: list[PlateBarHit]
    warnings: list[str]


Point3D = tuple[float, float, float]
Point2D = tuple[float, float]


@dataclass(frozen=True)
class _PlateLocalBasis:
    origin: Point3D
    u_axis: Point3D
    v_axis: Point3D
    normal: Point3D
    corner_uv: tuple[Point2D, Point2D, Point2D, Point2D]
    min_axis_length: float

    def project(self, point: Point3D) -> tuple[float, float, float]:
        return _project_in_basis(
            point,
            self.origin,
            self.u_axis,
            self.v_axis,
            self.normal,
        )

    def point_from_uv(self, u: float, v: float) -> Point3D:
        return _add(
            self.origin,
            _add(_scale(self.u_axis, float(u)), _scale(self.v_axis, float(v))),
        )

    def param_tol(self, tol: float) -> float:
        return max(float(tol), float(tol) / max(self.min_axis_length, tol))


def plate_local_basis(
    project: "ProjectModel",
    plate: "PlateRegionData",
    *,
    tol: float = 1e-6,
) -> _PlateLocalBasis:
    """Build a local parametric basis for a planar four-node plate."""
    if len(plate.corner_node_tags) != 4:
        raise ValueError(f"Plate P{plate.tag} requires exactly 4 corner nodes.")

    missing = [tag for tag in plate.corner_node_tags if int(tag) not in project.nodes]
    if missing:
        raise ValueError(f"Plate P{plate.tag} references missing node(s): {missing}.")

    p1, p2, p3, p4 = [_node_xyz(project, tag) for tag in plate.corner_node_tags]
    u_axis = _sub(p2, p1)
    raw_v_axis = _sub(p4, p1)
    u_length = _norm(u_axis)
    v_length = _norm(raw_v_axis)
    if u_length <= tol or v_length <= tol:
        raise ValueError(f"Plate P{plate.tag} has degenerate corner edges.")

    normal_raw = _cross(u_axis, raw_v_axis)
    normal_length = _norm(normal_raw)
    if normal_length <= tol * max(u_length, v_length):
        raise ValueError(f"Plate P{plate.tag} has nearly collinear corner nodes.")
    normal = _scale(normal_raw, 1.0 / normal_length)

    # Keep the 1->4 direction in the plate plane even if tiny numerical noise exists.
    v_axis = _sub(raw_v_axis, _scale(normal, _dot(raw_v_axis, normal)))
    if _norm(v_axis) <= tol:
        raise ValueError(f"Plate P{plate.tag} has a degenerate local v axis.")

    for index, point in enumerate((p1, p2, p3, p4), start=1):
        distance = _dot(_sub(point, p1), normal)
        if abs(distance) > tol:
            raise ValueError(
                f"Plate P{plate.tag} is not planar: corner {index} is "
                f"{distance:.6g} m from the plate plane."
            )

    corner_uv: tuple[Point2D, Point2D, Point2D, Point2D] = (
        _project_uv_in_basis(p1, p1, u_axis, v_axis, normal),
        _project_uv_in_basis(p2, p1, u_axis, v_axis, normal),
        _project_uv_in_basis(p3, p1, u_axis, v_axis, normal),
        _project_uv_in_basis(p4, p1, u_axis, v_axis, normal),
    )
    return _PlateLocalBasis(
        origin=p1,
        u_axis=u_axis,
        v_axis=v_axis,
        normal=normal,
        corner_uv=corner_uv,
        min_axis_length=min(u_length, v_length),
    )


def detect_plate_node_hits(
    project: "ProjectModel",
    plate: "PlateRegionData",
    *,
    tol: float = 1e-6,
) -> list[PlateNodeHit]:
    """Detect existing user nodes inside or on a plate region."""
    basis = plate_local_basis(project, plate, tol=tol)
    corner_tags = {int(tag) for tag in plate.corner_node_tags}
    param_tol = basis.param_tol(tol)
    hits: list[PlateNodeHit] = []

    for tag, node in sorted(project.nodes.items()):
        node_tag = int(tag)
        if node_tag in corner_tags:
            continue
        u, v, distance = basis.project((float(node.x), float(node.y), float(node.z)))
        if abs(distance) > tol:
            continue

        location = _classify_uv_point((u, v), basis.corner_uv, param_tol)
        if location is None:
            continue
        hits.append(
            PlateNodeHit(
                node_tag=node_tag,
                location=location,
                u=_clean_param(u, param_tol),
                v=_clean_param(v, param_tol),
                distance_to_plane=distance,
            )
        )
    return hits


def detect_plate_bar_hits(
    project: "ProjectModel",
    plate: "PlateRegionData",
    *,
    tol: float = 1e-6,
) -> list[PlateBarHit]:
    """Detect line elements that intersect a plate region."""
    basis = plate_local_basis(project, plate, tol=tol)
    param_tol = basis.param_tol(tol)
    hits: list[PlateBarHit] = []

    for tag, element in sorted(project.elements.items()):
        element_tag = int(tag)
        if (
            int(element.node_i) not in project.nodes
            or int(element.node_j) not in project.nodes
        ):
            continue

        p1 = _node_xyz(project, int(element.node_i))
        p2 = _node_xyz(project, int(element.node_j))
        u1, v1, d1 = basis.project(p1)
        u2, v2, d2 = basis.project(p2)
        uv1 = (u1, v1)
        uv2 = (u2, v2)

        if abs(d1) <= tol and abs(d2) <= tol:
            hit = _coplanar_bar_hit(
                element_tag,
                uv1,
                uv2,
                basis,
                plate.tag,
                param_tol,
            )
            if hit is not None:
                hits.append(hit)
            continue

        endpoint_hits = [
            (p1, u1, v1, d1),
            (p2, u2, v2, d2),
        ]
        endpoint_hit = next(
            (
                (point, u, v)
                for point, u, v, distance in endpoint_hits
                if abs(distance) <= tol
                and _point_in_or_on_polygon((u, v), basis.corner_uv, param_tol)
            ),
            None,
        )
        if endpoint_hit is not None:
            point, u, v = endpoint_hit
            hits.append(
                PlateBarHit(
                    element_tag=element_tag,
                    kind=PlateBarIntersectionKind.ENDPOINT_ON_PLATE,
                    point=_clean_point(point, tol),
                    u=_clean_param(u, param_tol),
                    v=_clean_param(v, param_tol),
                    message=(
                        f"La barre E{element_tag} a une extremite sur la plaque "
                        f"P{plate.tag}."
                    ),
                )
            )
            continue

        if d1 * d2 < 0.0:
            ratio = d1 / (d1 - d2)
            point = _add(p1, _scale(_sub(p2, p1), ratio))
            u, v, distance = basis.project(point)
            if abs(distance) <= tol and _point_in_or_on_polygon(
                (u, v),
                basis.corner_uv,
                param_tol,
            ):
                hits.append(
                    PlateBarHit(
                        element_tag=element_tag,
                        kind=PlateBarIntersectionKind.CROSSES_PLANE_AT_POINT,
                        point=_clean_point(point, tol),
                        u=_clean_param(u, param_tol),
                        v=_clean_param(v, param_tol),
                        message=(
                            f"La barre E{element_tag} traverse la plaque P{plate.tag} "
                            "sans noeud d'intersection."
                        ),
                    )
                )

    return hits


def detect_plate_intersections(
    project: "ProjectModel",
    plate: "PlateRegionData",
    *,
    tol: float = 1e-6,
) -> PlateIntersectionReport:
    """Return all node and bar diagnostics for one plate region."""
    node_hits = detect_plate_node_hits(project, plate, tol=tol)
    bar_hits = detect_plate_bar_hits(project, plate, tol=tol)
    warnings = [
        hit.message
        for hit in bar_hits
        if hit.kind
        in {
            PlateBarIntersectionKind.UNSUPPORTED_SKEW_IN_PLANE,
            PlateBarIntersectionKind.CROSSES_PLANE_AT_POINT,
            PlateBarIntersectionKind.CROSSES_PLATE_EDGE,
        }
        and hit.message
    ]
    return PlateIntersectionReport(
        plate_tag=int(plate.tag),
        node_hits=node_hits,
        bar_hits=bar_hits,
        warnings=warnings,
    )


def _coplanar_bar_hit(
    element_tag: int,
    uv1: Point2D,
    uv2: Point2D,
    basis: _PlateLocalBasis,
    plate_tag: int,
    tol: float,
) -> PlateBarHit | None:
    relation = _segment_polygon_relation(uv1, uv2, basis.corner_uv, tol)
    if not relation["intersects"]:
        return None

    du = uv2[0] - uv1[0]
    dv = uv2[1] - uv1[1]
    if abs(du) <= tol and abs(dv) <= tol:
        return None

    aligned = abs(du) <= tol or abs(dv) <= tol
    midpoint = (
        (_clamp01(uv1[0]) + _clamp01(uv2[0])) / 2.0,
        (_clamp01(uv1[1]) + _clamp01(uv2[1])) / 2.0,
    )

    if not aligned:
        return PlateBarHit(
            element_tag=element_tag,
            kind=PlateBarIntersectionKind.UNSUPPORTED_SKEW_IN_PLANE,
            point=_clean_point(basis.point_from_uv(*midpoint), tol),
            u=_clean_param(midpoint[0], tol),
            v=_clean_param(midpoint[1], tol),
            message=(
                f"La barre E{element_tag} est dans le plan de la plaque P{plate_tag}, "
                "mais elle est oblique. Le maillage structure actuel ne sait pas "
                "encore integrer une ligne diagonale."
            ),
        )

    crosses_edge = bool(relation["crosses_edge"])
    both_inside = bool(relation["endpoint_1_inside"] and relation["endpoint_2_inside"])
    if crosses_edge and not both_inside:
        return PlateBarHit(
            element_tag=element_tag,
            kind=PlateBarIntersectionKind.CROSSES_PLATE_EDGE,
            point=_clean_point(basis.point_from_uv(*midpoint), tol),
            u=_clean_param(midpoint[0], tol),
            v=_clean_param(midpoint[1], tol),
            message=(
                f"La barre E{element_tag} croise le contour de la plaque P{plate_tag}. "
                "Elle est detectee mais n'est pas decoupee automatiquement dans le "
                "modele utilisateur."
            ),
        )

    axis = "u" if abs(dv) <= tol else "v"
    return PlateBarHit(
        element_tag=element_tag,
        kind=PlateBarIntersectionKind.LIES_IN_PLATE_PLANE,
        point=_clean_point(basis.point_from_uv(*midpoint), tol),
        u=_clean_param(midpoint[0], tol),
        v=_clean_param(midpoint[1], tol),
        message=(
            f"La barre E{element_tag} est dans le plan de la plaque P{plate_tag} "
            f"et compatible avec le maillage structure (axe {axis})."
        ),
    )


def _classify_uv_point(
    uv: Point2D,
    polygon: tuple[Point2D, ...],
    tol: float,
) -> PlateNodeLocation | None:
    if any(_distance_2d(uv, corner) <= tol for corner in polygon):
        return PlateNodeLocation.ON_CORNER
    if any(
        _point_on_segment_2d(
            uv,
            polygon[index],
            polygon[(index + 1) % len(polygon)],
            tol,
        )
        for index in range(len(polygon))
    ):
        return PlateNodeLocation.ON_EDGE
    if _point_in_polygon(uv, polygon, tol):
        return PlateNodeLocation.INSIDE
    return None


def _segment_polygon_relation(
    a: Point2D,
    b: Point2D,
    polygon: tuple[Point2D, ...],
    tol: float,
) -> dict[str, bool]:
    endpoint_1_inside = _point_in_or_on_polygon(a, polygon, tol)
    endpoint_2_inside = _point_in_or_on_polygon(b, polygon, tol)
    crosses_edge = any(
        _segments_intersect_2d(
            a,
            b,
            polygon[index],
            polygon[(index + 1) % len(polygon)],
            tol,
        )
        for index in range(len(polygon))
    )
    return {
        "endpoint_1_inside": endpoint_1_inside,
        "endpoint_2_inside": endpoint_2_inside,
        "crosses_edge": crosses_edge,
        "intersects": endpoint_1_inside or endpoint_2_inside or crosses_edge,
    }


def _point_in_or_on_polygon(
    point: Point2D,
    polygon: tuple[Point2D, ...],
    tol: float,
) -> bool:
    return _classify_uv_point(point, polygon, tol) is not None


def _point_in_polygon(
    point: Point2D,
    polygon: tuple[Point2D, ...],
    tol: float,
) -> bool:
    x, y = point
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if _point_on_segment_2d(point, (x1, y1), (x2, y2), tol):
            return True
        if (y1 > y) == (y2 > y):
            continue
        x_at_y = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        if x_at_y >= x - tol:
            inside = not inside
    return inside


def _point_on_segment_2d(
    point: Point2D,
    a: Point2D,
    b: Point2D,
    tol: float,
) -> bool:
    cross = _cross_2d(_sub_2d(point, a), _sub_2d(b, a))
    if abs(cross) > tol:
        return False
    return (
        min(a[0], b[0]) - tol <= point[0] <= max(a[0], b[0]) + tol
        and min(a[1], b[1]) - tol <= point[1] <= max(a[1], b[1]) + tol
    )


def _segments_intersect_2d(
    a: Point2D,
    b: Point2D,
    c: Point2D,
    d: Point2D,
    tol: float,
) -> bool:
    if (
        _point_on_segment_2d(a, c, d, tol)
        or _point_on_segment_2d(b, c, d, tol)
        or _point_on_segment_2d(c, a, b, tol)
        or _point_on_segment_2d(d, a, b, tol)
    ):
        return True

    o1 = _orientation_2d(a, b, c)
    o2 = _orientation_2d(a, b, d)
    o3 = _orientation_2d(c, d, a)
    o4 = _orientation_2d(c, d, b)
    return o1 * o2 < -tol * tol and o3 * o4 < -tol * tol


def _orientation_2d(a: Point2D, b: Point2D, c: Point2D) -> float:
    return _cross_2d(_sub_2d(b, a), _sub_2d(c, a))


def _solve_2d_in_basis(vector: Point3D, u_axis: Point3D, v_axis: Point3D) -> Point2D:
    uu = _dot(u_axis, u_axis)
    uv = _dot(u_axis, v_axis)
    vv = _dot(v_axis, v_axis)
    ru = _dot(vector, u_axis)
    rv = _dot(vector, v_axis)
    determinant = uu * vv - uv * uv
    if abs(determinant) <= 1e-18:
        raise ValueError("Plate local basis is degenerate.")
    u = (ru * vv - rv * uv) / determinant
    v = (rv * uu - ru * uv) / determinant
    return u, v


def _project_in_basis(
    point: Point3D,
    origin: Point3D,
    u_axis: Point3D,
    v_axis: Point3D,
    normal: Point3D,
) -> tuple[float, float, float]:
    relative = _sub(point, origin)
    distance = _dot(relative, normal)
    in_plane = _sub(relative, _scale(normal, distance))
    u, v = _solve_2d_in_basis(in_plane, u_axis, v_axis)
    return u, v, distance


def _project_uv_in_basis(
    point: Point3D,
    origin: Point3D,
    u_axis: Point3D,
    v_axis: Point3D,
    normal: Point3D,
) -> Point2D:
    u, v, _distance = _project_in_basis(point, origin, u_axis, v_axis, normal)
    return u, v


def _node_xyz(project: "ProjectModel", node_tag: int) -> Point3D:
    node = project.nodes[int(node_tag)]
    return float(node.x), float(node.y), float(node.z)


def _clean_param(value: float, tol: float) -> float:
    if abs(value) <= tol:
        return 0.0
    if abs(value - 1.0) <= tol:
        return 1.0
    return float(value)


def _clean_point(point: Point3D, tol: float) -> Point3D:
    return tuple(0.0 if abs(value) <= tol else float(value) for value in point)


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _distance_2d(a: Point2D, b: Point2D) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _sub_2d(a: Point2D, b: Point2D) -> Point2D:
    return a[0] - b[0], a[1] - b[1]


def _cross_2d(a: Point2D, b: Point2D) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _add(a: Point3D, b: Point3D) -> Point3D:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Point3D, b: Point3D) -> Point3D:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _scale(a: Point3D, factor: float) -> Point3D:
    return a[0] * factor, a[1] * factor, a[2] * factor


def _dot(a: Point3D, b: Point3D) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Point3D, b: Point3D) -> Point3D:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Point3D) -> float:
    return math.sqrt(_dot(a, a))
