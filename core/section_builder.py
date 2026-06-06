"""Geometry helpers for HEXA custom section builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


Point2D = tuple[float, float]


class SectionBuilderGeometryError(ValueError):
    """Validation error raised by custom section geometry helpers."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PolygonSectionProperties:
    """Geometric properties of a simple closed polygon in local y/z axes."""

    area: float
    perimeter: float
    centroid_y: float
    centroid_z: float
    inertia_y: float
    inertia_z: float
    signed_area: float


def polygon_perimeter(points: Sequence[Point2D]) -> float:
    """Return the perimeter of a closed polygon."""
    if len(points) < 2:
        return 0.0
    perimeter = 0.0
    for idx, (y0, z0) in enumerate(points):
        y1, z1 = points[(idx + 1) % len(points)]
        perimeter += ((y1 - y0) ** 2 + (z1 - z0) ** 2) ** 0.5
    return perimeter


def validate_simple_polygon(points: Sequence[Point2D]) -> None:
    """Raise ValueError when a polygon cannot define one simple section contour."""
    if len(points) < 3:
        raise SectionBuilderGeometryError(
            "polygon_min_points",
            "A section polygon requires at least three points.",
        )

    for idx, point in enumerate(points):
        next_point = points[(idx + 1) % len(points)]
        if _same_point(point, next_point):
            raise SectionBuilderGeometryError(
                "polygon_duplicate_point",
                "The section polygon contains duplicate consecutive points.",
            )

    segment_count = len(points)
    for first_idx in range(segment_count):
        first = (points[first_idx], points[(first_idx + 1) % segment_count])
        for second_idx in range(first_idx + 1, segment_count):
            if _segments_are_adjacent(first_idx, second_idx, segment_count):
                continue
            second = (points[second_idx], points[(second_idx + 1) % segment_count])
            if _segments_intersect(first[0], first[1], second[0], second[1]):
                raise SectionBuilderGeometryError(
                    "polygon_crossing_edges",
                    "The section polygon contains crossing edges.",
                )


def polygon_section_properties(points: Sequence[Point2D]) -> PolygonSectionProperties:
    """Return area, centroid and centroidal inertias for a simple polygon.

    Coordinates are expressed in meters in the local section plane:
    ``y`` is horizontal and ``z`` is vertical.  The returned ``inertia_y`` is
    the second moment about the local y axis, therefore the integral of z^2 dA.
    """
    validate_simple_polygon(points)

    cross_sum = 0.0
    cy_sum = 0.0
    cz_sum = 0.0
    inertia_y_origin_sum = 0.0
    inertia_z_origin_sum = 0.0

    for idx, (y0, z0) in enumerate(points):
        y1, z1 = points[(idx + 1) % len(points)]
        cross = y0 * z1 - y1 * z0
        cross_sum += cross
        cy_sum += (y0 + y1) * cross
        cz_sum += (z0 + z1) * cross
        inertia_y_origin_sum += (z0 * z0 + z0 * z1 + z1 * z1) * cross
        inertia_z_origin_sum += (y0 * y0 + y0 * y1 + y1 * y1) * cross

    signed_area = 0.5 * cross_sum
    if abs(signed_area) <= 1.0e-12:
        raise SectionBuilderGeometryError(
            "polygon_zero_area",
            "The section polygon area is zero.",
        )

    centroid_y = cy_sum / (6.0 * signed_area)
    centroid_z = cz_sum / (6.0 * signed_area)
    sign = 1.0 if signed_area > 0.0 else -1.0
    area = abs(signed_area)
    inertia_y_origin = sign * inertia_y_origin_sum / 12.0
    inertia_z_origin = sign * inertia_z_origin_sum / 12.0
    inertia_y = inertia_y_origin - area * centroid_z * centroid_z
    inertia_z = inertia_z_origin - area * centroid_y * centroid_y

    return PolygonSectionProperties(
        area=area,
        perimeter=polygon_perimeter(points),
        centroid_y=centroid_y,
        centroid_z=centroid_z,
        inertia_y=max(inertia_y, 0.0),
        inertia_z=max(inertia_z, 0.0),
        signed_area=signed_area,
    )


def _same_point(p0: Point2D, p1: Point2D) -> bool:
    return abs(p0[0] - p1[0]) <= 1.0e-12 and abs(p0[1] - p1[1]) <= 1.0e-12


def _segments_are_adjacent(first_idx: int, second_idx: int, segment_count: int) -> bool:
    if first_idx == second_idx:
        return True
    if abs(first_idx - second_idx) == 1:
        return True
    return {first_idx, second_idx} == {0, segment_count - 1}


def _orientation(p0: Point2D, p1: Point2D, p2: Point2D) -> float:
    return (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])


def _point_on_segment(point: Point2D, start: Point2D, end: Point2D) -> bool:
    if abs(_orientation(start, end, point)) > 1.0e-12:
        return False
    return (
        min(start[0], end[0]) - 1.0e-12 <= point[0] <= max(start[0], end[0]) + 1.0e-12
        and min(start[1], end[1]) - 1.0e-12 <= point[1] <= max(start[1], end[1]) + 1.0e-12
    )


def _segments_intersect(a0: Point2D, a1: Point2D, b0: Point2D, b1: Point2D) -> bool:
    o1 = _orientation(a0, a1, b0)
    o2 = _orientation(a0, a1, b1)
    o3 = _orientation(b0, b1, a0)
    o4 = _orientation(b0, b1, a1)

    if o1 * o2 < 0.0 and o3 * o4 < 0.0:
        return True
    if abs(o1) <= 1.0e-12 and _point_on_segment(b0, a0, a1):
        return True
    if abs(o2) <= 1.0e-12 and _point_on_segment(b1, a0, a1):
        return True
    if abs(o3) <= 1.0e-12 and _point_on_segment(a0, b0, b1):
        return True
    return abs(o4) <= 1.0e-12 and _point_on_segment(a1, b0, b1)
