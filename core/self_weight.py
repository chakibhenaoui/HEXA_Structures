"""Automatic self-weight calculations for members and surfaces."""

from __future__ import annotations

import math

import numpy as np

from core.material_properties import material_mass_density_kg_m3
from core.local_axes import local_axes_from_nodes

SELF_WEIGHT_LOAD_NAME = "Poids propre"
SELF_WEIGHT_LOAD_TYPE = "self_weight"
GRAVITY = 9.81


def is_self_weight_load(load) -> bool:
    """Return whether self-weight load."""
    load_type = str(getattr(load, "load_type", "")).strip().lower()
    name = str(getattr(load, "name", "")).strip().lower()
    return load_type == SELF_WEIGHT_LOAD_TYPE or name == SELF_WEIGHT_LOAD_NAME.lower()


def material_density_kg_m3(material) -> float:
    """Handle material density kg m3."""
    return material_mass_density_kg_m3(material)


def element_local_axes(project, element) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Handle element local axes."""
    node_i = project.nodes[element.node_i]
    node_j = project.nodes[element.node_j]
    pi = (node_i.x, node_i.y, node_i.z)
    pj = (node_j.x, node_j.y, node_j.z)
    if math.dist(pi, pj) <= 1e-12:
        return (
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        )

    axes = local_axes_from_nodes(
        pi,
        pj,
        reference_vector=getattr(element, "orientation_vector", None),
        roll_angle_deg=float(getattr(element, "roll_angle_deg", 0.0) or 0.0),
    )
    return (
        np.array(axes.x, dtype=float),
        np.array(axes.y, dtype=float),
        np.array(axes.z, dtype=float),
    )


def element_global_to_local_components(
    project,
    element,
    gx: float,
    gy: float,
    gz: float,
) -> tuple[float, float, float]:
    """Handle element global to local components."""
    local_x, local_y, local_z = element_local_axes(project, element)
    global_load = np.array([gx, gy, gz], dtype=float)
    wx = float(np.dot(global_load, local_x))
    wy = float(np.dot(global_load, local_y))
    wz = float(np.dot(global_load, local_z))
    return wx, wy, wz


def element_load_local_components(project, element, load) -> tuple[float, float, float]:
    """Handle element load local components."""
    values = (
        float(getattr(load, "wx", 0.0)),
        float(getattr(load, "wy", 0.0)),
        float(getattr(load, "wz", 0.0)),
    )
    coordinate_system = str(
        getattr(load, "coordinate_system", "local") or "local",
    ).strip().lower()
    if coordinate_system != "global":
        return values
    return element_global_to_local_components(project, element, *values)


def element_self_weight_kn_m(project, element) -> float:
    """Handle element self-weight kN m."""
    section = project.sections.get(element.section_tag)
    if section is None or section.area <= 0.0:
        return 0.0

    material = project.materials.get(section.material_tag)
    density = material_density_kg_m3(material)
    return density * float(section.area) * GRAVITY / 1000.0


def element_self_weight_local_components(project, element) -> tuple[float, float, float]:
    """Handle element self-weight local components."""
    weight = element_self_weight_kn_m(project, element)
    if abs(weight) <= 1e-12:
        return 0.0, 0.0, 0.0

    return element_global_to_local_components(project, element, 0.0, 0.0, -weight)


def surface_area_m2(project, surface) -> float:
    """Handle surface area m2."""
    points = []
    for node_tag in surface.node_tags:
        node = project.nodes.get(int(node_tag))
        if node is None:
            return 0.0
        points.append(np.array([node.x, node.y, node.z], dtype=float))

    if len(points) < 3:
        return 0.0

    origin = points[0]
    area = 0.0
    for idx in range(1, len(points) - 1):
        vec_1 = points[idx] - origin
        vec_2 = points[idx + 1] - origin
        area += 0.5 * float(np.linalg.norm(np.cross(vec_1, vec_2)))
    return area


def surface_self_weight_kn_m2(project, surface) -> float:
    """Handle surface self-weight kN m2."""
    section = project.sections.get(surface.section_tag)
    if section is None or not section.is_surface or section.thickness <= 0.0:
        return 0.0

    material = project.materials.get(section.material_tag)
    density = material_density_kg_m3(material)
    return density * float(section.thickness) * GRAVITY / 1000.0


def surface_self_weight_global_components(project, surface) -> tuple[float, float, float]:
    """Handle surface self-weight global components."""
    weight = surface_self_weight_kn_m2(project, surface)
    if abs(weight) <= 1e-12:
        return 0.0, 0.0, 0.0
    return 0.0, 0.0, -weight


def total_self_weight_kn(project) -> float:
    """Handle total self-weight kN."""
    total = 0.0
    for element in project.elements.values():
        node_i = project.nodes[element.node_i]
        node_j = project.nodes[element.node_j]
        length = math.dist((node_i.x, node_i.y, node_i.z), (node_j.x, node_j.y, node_j.z))
        total += element_self_weight_kn_m(project, element) * length
    for surface in project.surface_elements.values():
        total += surface_self_weight_kn_m2(project, surface) * surface_area_m2(project, surface)
    return total
