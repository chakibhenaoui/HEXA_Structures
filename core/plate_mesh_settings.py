"""Regles de maillage des plaques utilisateur."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.model_data import (
    PLATE_MESH_MODE_AUTO,
    PLATE_MESH_MODE_USER,
    normalize_plate_mesh_mode,
    normalize_surface_formulation,
)

if TYPE_CHECKING:
    from core.model_data import PlateRegionData, ProjectModel


MIN_AUTO_PLATE_MESH_DIVISIONS = 4
MAX_AUTO_PLATE_MESH_DIVISIONS = 32
THIN_PLATE_SLENDERNESS_LIMIT = 12.0


@dataclass(frozen=True)
class PlateMeshRecommendation:
    """Maillage effectif retenu pour une plaque macro."""

    mesh_nx: int
    mesh_ny: int
    mode: str
    target_size: float
    u_length: float
    v_length: float
    min_divisions: int
    max_divisions: int = MAX_AUTO_PLATE_MESH_DIVISIONS


def effective_plate_mesh_divisions(
    project: "ProjectModel",
    plate: "PlateRegionData",
) -> tuple[int, int]:
    """Retourne les divisions effectivement transmises au modele de calcul."""
    mode = normalize_plate_mesh_mode(getattr(plate, "mesh_mode", None))
    if mode == PLATE_MESH_MODE_USER:
        return max(1, int(plate.mesh_nx)), max(1, int(plate.mesh_ny))
    recommendation = automatic_plate_mesh_recommendation(project, plate)
    return recommendation.mesh_nx, recommendation.mesh_ny


def automatic_plate_mesh_recommendation(
    project: "ProjectModel",
    plate: "PlateRegionData",
) -> PlateMeshRecommendation:
    """Calcule un maillage automatique robuste pour une plaque quadrangulaire.

    La methode utilise une taille maximale d'element derivee de la plus petite
    portee de la plaque, de l'epaisseur et de la formulation. Elle reste
    deterministe pour que les resultats soient reproductibles.
    """
    u_length, v_length = _plate_axis_lengths(project, plate)
    short_length = max(min(u_length, v_length), 1e-9)
    thickness = _plate_thickness(project, plate)
    formulation = _effective_formulation(project, plate)

    min_divisions = _auto_min_divisions(formulation, short_length, thickness)
    span_target = short_length / float(min_divisions)
    thickness_target = _thickness_target(formulation, short_length, thickness)
    target_size = min(span_target, thickness_target) if thickness_target else span_target
    target_size = max(target_size, 1e-9)

    nx = _clamped_divisions(u_length, target_size)
    ny = _clamped_divisions(v_length, target_size)
    return PlateMeshRecommendation(
        mesh_nx=nx,
        mesh_ny=ny,
        mode=PLATE_MESH_MODE_AUTO,
        target_size=target_size,
        u_length=u_length,
        v_length=v_length,
        min_divisions=min_divisions,
    )


def _plate_axis_lengths(
    project: "ProjectModel",
    plate: "PlateRegionData",
) -> tuple[float, float]:
    p1, p2, p3, p4 = [_node_xyz(project, tag) for tag in plate.corner_node_tags]
    u_length = 0.5 * (_distance(p1, p2) + _distance(p4, p3))
    v_length = 0.5 * (_distance(p2, p3) + _distance(p1, p4))
    return max(u_length, 0.0), max(v_length, 0.0)


def _node_xyz(project: "ProjectModel", node_tag: int) -> tuple[float, float, float]:
    node = project.nodes[int(node_tag)]
    return float(node.x), float(node.y), float(node.z)


def _distance(
    pi: tuple[float, float, float],
    pj: tuple[float, float, float],
) -> float:
    return math.dist(pi, pj)


def _plate_thickness(project: "ProjectModel", plate: "PlateRegionData") -> float:
    section = project.sections.get(int(plate.section_tag))
    if section is None:
        return 0.0
    try:
        return max(0.0, float(section.thickness))
    except (TypeError, ValueError):
        return 0.0


def _effective_formulation(project: "ProjectModel", plate: "PlateRegionData") -> str:
    section = project.sections.get(int(plate.section_tag))
    if section is not None and section.is_surface:
        return section.surface_formulation
    return normalize_surface_formulation(getattr(plate, "formulation", None))


def _auto_min_divisions(
    formulation: str,
    short_length: float,
    thickness: float,
) -> int:
    if thickness > 0.0:
        slenderness = short_length / thickness
    else:
        slenderness = float("inf")

    if formulation == "ShellMITC4" and slenderness >= THIN_PLATE_SLENDERNESS_LIMIT:
        return 16
    return 8


def _thickness_target(
    formulation: str,
    short_length: float,
    thickness: float,
) -> float | None:
    if thickness <= 0.0:
        return None
    slenderness = short_length / thickness
    if formulation == "ShellMITC4" and slenderness >= THIN_PLATE_SLENDERNESS_LIMIT:
        return 2.5 * thickness
    return 4.0 * thickness


def _clamped_divisions(length: float, target_size: float) -> int:
    divisions = int(math.ceil(max(length, 0.0) / max(target_size, 1e-9)))
    return max(
        MIN_AUTO_PLATE_MESH_DIVISIONS,
        min(MAX_AUTO_PLATE_MESH_DIVISIONS, divisions),
    )
