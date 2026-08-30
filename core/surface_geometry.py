"""Geometry helpers for simple planar structural surface polygons."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


Point2D = tuple[float, float]
Point3D = tuple[float, float, float]


class SurfacePolygonGeometryError(ValueError):
    """Raised when a boundary cannot define a simple planar surface."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SurfacePolygonGeometry:
    """Projected geometry of a validated planar surface polygon."""

    origin: Point3D
    u_axis: Point3D
    v_axis: Point3D
    normal: Point3D
    projected_points: tuple[Point2D, ...]
    signed_area: float

    @property
    def area(self) -> float:
        return abs(self.signed_area)


def validate_surface_polygon(
    points: Sequence[Point3D],
    *,
    tolerance: float = 1.0e-9,
) -> SurfacePolygonGeometry:
    """Validate and project a simple coplanar 3D polygon."""
    normalized = tuple(tuple(float(value) for value in point) for point in points)
    if len(normalized) < 3:
        raise SurfacePolygonGeometryError(
            "polygon_min_points",
            "A surface polygon requires at least three points.",
        )
    if any(len(point) != 3 for point in normalized):
        raise SurfacePolygonGeometryError(
            "polygon_invalid_point",
            "Surface polygon points must contain exactly three coordinates.",
        )

    scale = max(
        max(point[axis] for point in normalized)
        - min(point[axis] for point in normalized)
        for axis in range(3)
    )
    distance_tolerance = max(float(tolerance), scale * 1.0e-9)
    for index, point in enumerate(normalized):
        for other in normalized[index + 1 :]:
            if _norm(_sub(point, other)) <= distance_tolerance:
                raise SurfacePolygonGeometryError(
                    "polygon_duplicate_point",
                    "Surface polygon points must be distinct.",
                )

    origin = normalized[0]
    u_axis, normal = _projection_axes(normalized, distance_tolerance)
    v_axis = _normalize(_cross(normal, u_axis))
    for point in normalized:
        distance = abs(_dot(_sub(point, origin), normal))
        if distance > distance_tolerance:
            raise SurfacePolygonGeometryError(
                "polygon_not_coplanar",
                "Surface polygon points must be coplanar.",
            )

    projected = tuple(
        (_dot(_sub(point, origin), u_axis), _dot(_sub(point, origin), v_axis))
        for point in normalized
    )
    coordinate_scale = max(
        max(abs(value) for point in projected for value in point),
        1.0,
    )
    projected_tolerance = max(float(tolerance), coordinate_scale * 1.0e-9)
    _validate_simple_boundary(projected, projected_tolerance)
    signed_area = _signed_area(projected)
    if abs(signed_area) <= projected_tolerance * projected_tolerance:
        raise SurfacePolygonGeometryError(
            "polygon_zero_area",
            "Surface polygon area must be greater than zero.",
        )

    return SurfacePolygonGeometry(
        origin=origin,
        u_axis=u_axis,
        v_axis=v_axis,
        normal=normal,
        projected_points=projected,
        signed_area=signed_area,
    )


def surface_polygon_area(points: Sequence[Point3D]) -> float:
    """Return the area of a valid simple planar polygon."""
    try:
        return validate_surface_polygon(points).area
    except SurfacePolygonGeometryError:
        return 0.0


def is_convex_surface_polygon(points: Sequence[Point3D]) -> bool:
    """Return whether a valid planar polygon is strictly convex."""
    geometry = validate_surface_polygon(points)
    projected = geometry.projected_points
    tolerance = max(float(geometry.area), 1.0) * 1e-12
    orientations = [
        _orientation_2d(
            projected[index - 1],
            projected[index],
            projected[(index + 1) % len(projected)],
        )
        for index in range(len(projected))
    ]
    return all(value > tolerance for value in orientations) or all(
        value < -tolerance for value in orientations
    )


def triangulate_surface_polygon(points: Sequence[Point3D]) -> tuple[tuple[int, int, int], ...]:
    """Triangulate a valid simple polygon while preserving its boundary."""
    geometry = validate_surface_polygon(points)
    projected = geometry.projected_points
    orientation = 1.0 if geometry.signed_area > 0.0 else -1.0
    tolerance = max(geometry.area, 1.0) * 1.0e-12
    remaining = list(range(len(projected)))
    triangles: list[tuple[int, int, int]] = []

    while len(remaining) > 3:
        ear_found = False
        for position, current in enumerate(remaining):
            previous = remaining[position - 1]
            following = remaining[(position + 1) % len(remaining)]
            corner_orientation = _orientation_2d(
                projected[previous],
                projected[current],
                projected[following],
            )
            if orientation * corner_orientation <= tolerance:
                continue
            if any(
                _point_in_triangle(
                    projected[candidate],
                    projected[previous],
                    projected[current],
                    projected[following],
                    orientation,
                    tolerance,
                )
                for candidate in remaining
                if candidate not in {previous, current, following}
            ):
                continue
            triangles.append((previous, current, following))
            del remaining[position]
            ear_found = True
            break
        if not ear_found:
            raise SurfacePolygonGeometryError(
                "polygon_triangulation_failed",
                "Surface polygon could not be triangulated.",
            )

    triangles.append(tuple(remaining))
    return tuple(triangles)


def _projection_axes(
    points: tuple[Point3D, ...],
    tolerance: float,
) -> tuple[Point3D, Point3D]:
    origin = points[0]
    for index in range(1, len(points) - 1):
        first = _sub(points[index], origin)
        if _norm(first) <= tolerance:
            continue
        for other_index in range(index + 1, len(points)):
            second = _sub(points[other_index], origin)
            candidate = _cross(first, second)
            if _norm(candidate) > tolerance:
                return _normalize(first), _normalize(candidate)
    raise SurfacePolygonGeometryError(
        "polygon_zero_area",
        "Surface polygon points must not be collinear.",
    )


def _validate_simple_boundary(points: tuple[Point2D, ...], tolerance: float) -> None:
    count = len(points)
    for index in range(count):
        start = points[index]
        end = points[(index + 1) % count]
        if _distance_2d(start, end) <= tolerance:
            raise SurfacePolygonGeometryError(
                "polygon_short_edge",
                "Surface polygon edges must have a non-zero length.",
            )
        for other_index in range(index + 1, count):
            if other_index in {index, (index + 1) % count}:
                continue
            if index == 0 and other_index == count - 1:
                continue
            other_start = points[other_index]
            other_end = points[(other_index + 1) % count]
            if _segments_intersect(start, end, other_start, other_end, tolerance):
                raise SurfacePolygonGeometryError(
                    "polygon_crossing_edges",
                    "Surface polygon edges must not cross.",
                )


def _segments_intersect(
    a: Point2D,
    b: Point2D,
    c: Point2D,
    d: Point2D,
    tolerance: float,
) -> bool:
    o1 = _orientation_2d(a, b, c)
    o2 = _orientation_2d(a, b, d)
    o3 = _orientation_2d(c, d, a)
    o4 = _orientation_2d(c, d, b)
    if ((o1 > tolerance and o2 < -tolerance) or (o1 < -tolerance and o2 > tolerance)) and (
        (o3 > tolerance and o4 < -tolerance) or (o3 < -tolerance and o4 > tolerance)
    ):
        return True
    return any(
        abs(orientation) <= tolerance and _point_on_segment(point, start, end, tolerance)
        for orientation, point, start, end in (
            (o1, c, a, b),
            (o2, d, a, b),
            (o3, a, c, d),
            (o4, b, c, d),
        )
    )


def _orientation_2d(a: Point2D, b: Point2D, c: Point2D) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_in_triangle(
    point: Point2D,
    first: Point2D,
    second: Point2D,
    third: Point2D,
    orientation: float,
    tolerance: float,
) -> bool:
    values = (
        orientation * _orientation_2d(first, second, point),
        orientation * _orientation_2d(second, third, point),
        orientation * _orientation_2d(third, first, point),
    )
    return all(value >= -tolerance for value in values)


def _point_on_segment(
    point: Point2D,
    start: Point2D,
    end: Point2D,
    tolerance: float,
) -> bool:
    return (
        min(start[0], end[0]) - tolerance <= point[0] <= max(start[0], end[0]) + tolerance
        and min(start[1], end[1]) - tolerance <= point[1] <= max(start[1], end[1]) + tolerance
    )


def _signed_area(points: tuple[Point2D, ...]) -> float:
    return 0.5 * sum(
        point[0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * point[1]
        for index, point in enumerate(points)
    )


def _sub(first: Point3D, second: Point3D) -> Point3D:
    return tuple(first[index] - second[index] for index in range(3))


def _dot(first: Point3D, second: Point3D) -> float:
    return sum(first[index] * second[index] for index in range(3))


def _cross(first: Point3D, second: Point3D) -> Point3D:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _norm(vector: Point3D) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalize(vector: Point3D) -> Point3D:
    norm = _norm(vector)
    return tuple(value / norm for value in vector)


def _distance_2d(first: Point2D, second: Point2D) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])
