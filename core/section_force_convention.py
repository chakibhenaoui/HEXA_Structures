"""Helpers for section force convention."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.local_axes import local_axes_from_nodes


PLANE_INDICES: dict[str, tuple[int, int]] = {
    "XZ": (0, 2),
    "YZ": (1, 2),
    "XY": (0, 1),
}

PLANE_NORMALS_3D: dict[str, np.ndarray] = {
    "XZ": np.array([0.0, 1.0, 0.0]),
    "YZ": np.array([1.0, 0.0, 0.0]),
    "XY": np.array([0.0, 0.0, 1.0]),
}


@dataclass(frozen=True)
class DiagramConvention:
    """Resolved sign and drawing side for a frame diagram component."""

    sign: float
    direction_2d: np.ndarray


@dataclass(frozen=True)
class DisplayedDiagramSamples:
    """Samples converted to the internal display convention."""

    p1: np.ndarray
    p2: np.ndarray
    x: np.ndarray
    values: np.ndarray
    direction_2d: np.ndarray
    canonical_axes: tuple[np.ndarray, np.ndarray, np.ndarray]


def is_column_like_member(tangent_2d: np.ndarray) -> bool:
    """Return True when the member reads mostly vertical in the current file view."""
    return abs(float(tangent_2d[1])) > abs(float(tangent_2d[0]))


def canonicalize_projected_samples(
    p1: np.ndarray,
    p2: np.ndarray,
    xl: np.ndarray,
    values: np.ndarray,
    length_3d: float,
    component: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Apply a stable projected orientation independent of element draw order."""
    direction = p2 - p1
    axis_idx = int(np.argmax(np.abs(direction)))
    if direction[axis_idx] >= 0:
        return p1, p2, xl, values

    xl_reversed = length_3d - xl[::-1]
    values_reversed = values[::-1]
    if component in {"N", "Vy", "T", "My", "Mz"}:
        values_reversed = -values_reversed
    return p2, p1, xl_reversed, values_reversed


def choose_outward_normal(
    p1: np.ndarray,
    p2: np.ndarray,
    model_centroid: np.ndarray,
) -> np.ndarray | None:
    """Choose a 2D normal pointing away from the model centroid."""
    direction = p2 - p1
    length = float(np.linalg.norm(direction))
    if length < 1e-12:
        return None

    tangent = direction / length
    normal = np.array([-tangent[1], tangent[0]])
    midpoint = 0.5 * (p1 + p2)
    radial = midpoint - model_centroid
    if float(np.dot(normal, radial)) < 0.0:
        normal = -normal
    return normal


def element_local_axes(ecrd_3d: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rebuild the member local axes used by the structural model."""
    x_vec = ecrd_3d[1] - ecrd_3d[0]
    length = float(np.linalg.norm(x_vec))
    if length < 1e-12:
        return (
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        )

    axes = local_axes_from_nodes(
        tuple(float(value) for value in ecrd_3d[0]),
        tuple(float(value) for value in ecrd_3d[1]),
    )
    return _axes_to_arrays(axes)


def build_local_axes_from_x(local_x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build a right-handed local frame from an imposed x axis."""
    norm_x = float(np.linalg.norm(local_x))
    if norm_x < 1e-12:
        return (
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        )

    axes = local_axes_from_nodes(
        (0.0, 0.0, 0.0),
        tuple(float(value) for value in local_x),
    )
    return _axes_to_arrays(axes)


def _axes_to_arrays(axes) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.array(axes.x, dtype=float),
        np.array(axes.y, dtype=float),
        np.array(axes.z, dtype=float),
    )


def canonical_element_local_axes(
    ecrd_3d: np.ndarray,
) -> tuple[tuple[np.ndarray, np.ndarray, np.ndarray], bool]:
    """Build a canonical local frame to stabilize signs across draw directions."""
    x_vec = ecrd_3d[1] - ecrd_3d[0]
    norm_x = float(np.linalg.norm(x_vec))
    if norm_x < 1e-12:
        axes = build_local_axes_from_x(np.array([1.0, 0.0, 0.0]))
        return axes, False

    local_x = x_vec / norm_x
    dominant_idx = int(np.argmax(np.abs(local_x)))
    reverse = float(local_x[dominant_idx]) < 0.0
    if reverse:
        local_x = -local_x
    return build_local_axes_from_x(local_x), reverse


def canonical_component_sign(
    component: str,
    actual_axes: tuple[np.ndarray, np.ndarray, np.ndarray],
    canonical_axes: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> float:
    """Return the sign needed to express a component in the canonical frame."""
    actual_x, actual_y, actual_z = actual_axes
    canonical_x, canonical_y, canonical_z = canonical_axes
    if component in {"N", "T"}:
        return 1.0 if float(np.dot(canonical_x, actual_x)) >= 0.0 else -1.0
    if component in {"Vy", "My"}:
        return 1.0 if float(np.dot(canonical_y, actual_y)) >= 0.0 else -1.0
    return 1.0 if float(np.dot(canonical_z, actual_z)) >= 0.0 else -1.0


def canonicalize_component_samples(
    ecrd_3d: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    xl: np.ndarray,
    values: np.ndarray,
    component: str,
    apply_component_axis_sign: bool = True,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    tuple[np.ndarray, np.ndarray, np.ndarray],
]:
    """Express sampled member values in the canonical local frame."""
    actual_axes = element_local_axes(ecrd_3d)
    canonical_axes, reverse = canonical_element_local_axes(ecrd_3d)
    length_3d = float(np.linalg.norm(ecrd_3d[1] - ecrd_3d[0]))

    if reverse:
        p1, p2 = p2, p1
        xl = length_3d - xl[::-1]
        values = values[::-1]
        if not apply_component_axis_sign and component in {"Vz", "Mz"}:
            values = -values

    if apply_component_axis_sign:
        values = values * canonical_component_sign(component, actual_axes, canonical_axes)
    return p1, p2, xl, values, canonical_axes


def component_display_sign(
    component: str,
    plane: str,
    local_x: np.ndarray,
    local_y: np.ndarray,
    local_z: np.ndarray,
    tangent_2d: np.ndarray,
    outward_normal_2d: np.ndarray,
    file_boundary_sign: float = 1.0,
) -> float:
    """Convert a local component to the internal display convention."""
    i1, i2 = PLANE_INDICES[plane]
    plane_normal = PLANE_NORMALS_3D[plane]

    if component in ("N", "T"):
        axis_2d = np.array([local_x[i1], local_x[i2]])
        return 1.0 if float(np.dot(axis_2d, tangent_2d)) >= 0.0 else -1.0

    if component == "My":
        if is_column_like_member(tangent_2d):
            if plane == "YZ":
                if float(np.dot(local_z, plane_normal)) >= 0.0:
                    return file_boundary_sign
                return -file_boundary_sign
            reference_side = bending_reference_side_2d(tangent_2d, outward_normal_2d)
            projected = project_vector_to_plane(local_z, plane)
            if projected is None:
                return 1.0
            return 1.0 if float(np.dot(projected, reference_side)) >= 0.0 else -1.0

        if abs(float(np.dot(local_y, plane_normal))) >= 1e-9:
            return -1.0
        return 1.0

    if component == "Vy":
        return 1.0 if float(np.dot(local_y, plane_normal)) >= 0.0 else -1.0

    axis_2d = np.array([local_z[i1], local_z[i2]])
    return 1.0 if float(np.dot(axis_2d, outward_normal_2d)) >= 0.0 else -1.0


def project_vector_to_plane(vec_3d: np.ndarray, plane: str) -> np.ndarray | None:
    """Project a 3D vector into the current 2D plane and normalize it."""
    i1, i2 = PLANE_INDICES[plane]
    vec_2d = np.array([vec_3d[i1], vec_3d[i2]], dtype=float)
    norm = float(np.linalg.norm(vec_2d))
    if norm < 1e-12:
        return None
    return vec_2d / norm


def diagram_direction_2d(
    component: str,
    plane: str,
    local_y: np.ndarray,
    local_z: np.ndarray,
    outward_normal_2d: np.ndarray,
    tangent_2d: np.ndarray,
) -> np.ndarray:
    """Choose the 2D drawing direction for a component."""
    if component == "My":
        if is_column_like_member(tangent_2d):
            return outward_normal_2d
        projected = project_vector_to_plane(local_z, plane)
        if projected is not None:
            return -projected
    if component == "Mz":
        projected = project_vector_to_plane(local_y, plane)
        if projected is not None:
            return -projected
    if component == "Vy":
        projected = project_vector_to_plane(local_y, plane)
        if projected is not None:
            return projected
    if component == "Vz":
        projected = project_vector_to_plane(local_z, plane)
        if projected is not None:
            return projected
    return outward_normal_2d


def bending_reference_side_2d(
    tangent_2d: np.ndarray,
    file_side_2d: np.ndarray,
) -> np.ndarray:
    """Return the stable reference side for My in a vertical file view."""
    if is_column_like_member(tangent_2d):
        return file_side_2d
    return np.array([0.0, -1.0], dtype=float)


def diagram_convention_for_element(
    component: str,
    plane: str,
    local_x: np.ndarray,
    local_y: np.ndarray,
    local_z: np.ndarray,
    tangent_2d: np.ndarray,
    file_side_2d: np.ndarray,
    file_boundary_sign: float = 1.0,
) -> DiagramConvention:
    """Resolve both sign and drawing side for a component."""
    if component == "My":
        direction = bending_reference_side_2d(tangent_2d, file_side_2d)
        sign = component_display_sign(
            component,
            plane,
            local_x,
            local_y,
            local_z,
            tangent_2d,
            file_side_2d,
            file_boundary_sign,
        )
        return DiagramConvention(sign=sign, direction_2d=direction)

    sign = component_display_sign(
        component,
        plane,
        local_x,
        local_y,
        local_z,
        tangent_2d,
        file_side_2d,
        file_boundary_sign,
    )
    direction = diagram_direction_2d(
        component,
        plane,
        local_y,
        local_z,
        file_side_2d,
        tangent_2d,
    )
    return DiagramConvention(sign=sign, direction_2d=direction)


def display_component_values(component: str, values: np.ndarray) -> np.ndarray:
    """Final presentation hook; currently preserves already-normalized signs."""
    return values


def choose_file_diagram_side(
    p1: np.ndarray,
    p2: np.ndarray,
    file_center: np.ndarray,
    tol: float,
) -> np.ndarray | None:
    """Choose a stable diagram side in a 2D file view."""
    direction = p2 - p1
    length = float(np.linalg.norm(direction))
    if length < 1e-12:
        return None

    tangent = direction / length
    if is_column_like_member(tangent):
        mid_x = float(0.5 * (p1[0] + p2[0]))
        delta_x = mid_x - float(file_center[0])
        if abs(delta_x) <= tol:
            sign = 1.0
        else:
            sign = 1.0 if delta_x > 0.0 else -1.0
        return np.array([sign, 0.0], dtype=float)

    return np.array([0.0, 1.0], dtype=float)


def diagram_direction_for_file(
    component: str,
    plane: str,
    local_y: np.ndarray,
    local_z: np.ndarray,
    file_side_2d: np.ndarray,
    tangent_2d: np.ndarray,
) -> np.ndarray:
    """Return the component drawing direction for a stable file view."""
    if component == "My":
        return bending_reference_side_2d(tangent_2d, file_side_2d)
    return diagram_direction_2d(
        component,
        plane,
        local_y,
        local_z,
        file_side_2d,
        tangent_2d,
    )


def sample_component_for_display(
    component: str,
    plane: str | None,
    ecrd_3d: np.ndarray,
) -> str:
    """Return the structural component to sample for a file-view diagram."""
    if component != "My" or plane != "YZ":
        return component

    i1, i2 = PLANE_INDICES[plane]
    p1 = np.array([ecrd_3d[0, i1], ecrd_3d[0, i2]], dtype=float)
    p2 = np.array([ecrd_3d[1, i1], ecrd_3d[1, i2]], dtype=float)
    tangent_2d = p2 - p1
    length_2d = float(np.linalg.norm(tangent_2d))
    if length_2d < 1e-12:
        return component

    if is_column_like_member(tangent_2d / length_2d):
        return "Mz"
    return component


def resolve_display_samples(
    *,
    ecrd_3d: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    x: np.ndarray,
    values: np.ndarray,
    component: str,
    plane: str,
    file_side_2d: np.ndarray | None = None,
    file_center: np.ndarray | None = None,
    file_tol: float = 1e-9,
    file_boundary_sign: float = 1.0,
    apply_component_axis_sign: bool = True,
    sample_component: str | None = None,
) -> DisplayedDiagramSamples | None:
    """Normalize member samples for display, independent of draw direction."""
    sample_component = sample_component or component
    p1, p2, x, values, canonical_axes = canonicalize_component_samples(
        ecrd_3d,
        p1,
        p2,
        x,
        values,
        sample_component,
        apply_component_axis_sign=apply_component_axis_sign,
    )

    if file_side_2d is None:
        if file_center is None:
            return None
        file_side_2d = choose_file_diagram_side(p1, p2, file_center, file_tol)
        if file_side_2d is None:
            return None

    tangent_2d = p2 - p1
    length_2d = float(np.linalg.norm(tangent_2d))
    if length_2d < 1e-12:
        return None
    tangent_2d = tangent_2d / length_2d

    local_x, local_y, local_z = canonical_axes
    convention = diagram_convention_for_element(
        component,
        plane,
        local_x,
        local_y,
        local_z,
        tangent_2d,
        file_side_2d,
        file_boundary_sign,
    )
    displayed_values = display_component_values(component, values * convention.sign)
    return DisplayedDiagramSamples(
        p1=p1,
        p2=p2,
        x=x,
        values=displayed_values,
        direction_2d=convention.direction_2d,
        canonical_axes=canonical_axes,
    )
