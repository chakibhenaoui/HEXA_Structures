"""Helpers pour la copie géométrique des sélections."""

from __future__ import annotations

from typing import Iterable, Mapping


def selection_reference_point(
    points: Iterable[tuple[float, float, float]],
) -> tuple[float, float, float]:
    """Retourne le centre moyen d'un ensemble de points 3D."""
    pts = list(points)
    if not pts:
        raise ValueError("At least one point is required to build a copy reference.")

    count = float(len(pts))
    return (
        sum(point[0] for point in pts) / count,
        sum(point[1] for point in pts) / count,
        sum(point[2] for point in pts) / count,
    )


def selection_anchor_point(
    points: Iterable[tuple[float, float, float]],
) -> tuple[float, float, float]:
    """Retourne le point d'ancrage bas-gauche de la sélection.

    La priorite suit l'ordre : Z minimum, puis X minimum, puis Y minimum.
    Cela donne un comportement stable pour les poteaux et portiques copies.
    """
    pts = list(points)
    if not pts:
        raise ValueError("At least one point is required to build a copy anchor.")
    return min(pts, key=lambda point: (point[2], point[0], point[1]))


def build_copy_instance_points(
    source_points: Mapping[int, tuple[float, float, float]],
    *,
    dx: float,
    dy: float,
    dz: float,
    copy_count: int,
) -> list[dict[int, tuple[float, float, float]]]:
    """Construit les positions cible des copies successives."""
    if copy_count < 1:
        raise ValueError("copy_count must be at least 1.")

    instances: list[dict[int, tuple[float, float, float]]] = []
    for copy_index in range(1, copy_count + 1):
        shift_x = dx * copy_index
        shift_y = dy * copy_index
        shift_z = dz * copy_index
        instances.append(
            {
                tag: (
                    point[0] + shift_x,
                    point[1] + shift_y,
                    point[2] + shift_z,
                )
                for tag, point in source_points.items()
            }
        )
    return instances
