"""Construction robuste des axes locaux 3D des elements lineaires."""

from __future__ import annotations

import math
from dataclasses import dataclass


Vector3 = tuple[float, float, float]

_ZERO_TOL = 1.0e-12
_PARALLEL_LIMIT = 0.95


@dataclass(frozen=True)
class LocalAxes3D:
    """Repere local orthonorme d'une barre 3D.

    Les axes sont exprimes dans le repere global. La matrice de rotation expose
    les axes locaux en colonnes et transforme donc un vecteur local vers le
    repere global.
    """

    x: Vector3
    y: Vector3
    z: Vector3

    @property
    def rotation_matrix(self) -> tuple[Vector3, Vector3, Vector3]:
        """Retourne la matrice local -> global avec les axes locaux en colonnes."""
        return (
            (self.x[0], self.y[0], self.z[0]),
            (self.x[1], self.y[1], self.z[1]),
            (self.x[2], self.y[2], self.z[2]),
        )


def local_axes_from_nodes(
    pi: Vector3,
    pj: Vector3,
    reference_vector: Vector3 | None = None,
    roll_angle_deg: float = 0.0,
) -> LocalAxes3D:
    """Construit le repere local 3D d'une barre entre deux noeuds.

    Convention HEXA :
    - x local va du noeud i vers le noeud j ;
    - z local est la projection du vecteur de reference dans le plan normal a x ;
    - y local vaut z x x ;
    - un roulis positif tourne la section autour de x selon la regle de la main
      droite.

    Args:
        pi: Coordonnees globales du noeud i.
        pj: Coordonnees globales du noeud j.
        reference_vector: Vecteur de reference global optionnel.
        roll_angle_deg: Rotation de section positive autour de x local, en degres.

    Raises:
        ValueError: Si les noeuds sont confondus ou si le vecteur utilisateur est nul.
    """
    x_axis = _normalize(_sub(pj, pi), "Les deux noeuds de la barre sont confondus.")

    user_reference = reference_vector is not None
    if reference_vector is None:
        reference = _choose_reference_vector(x_axis)
    else:
        reference = _normalize(
            reference_vector,
            "Le vecteur de reference d'orientation locale ne peut pas etre nul.",
        )

    z_axis = _project_reference_on_normal_plane(reference, x_axis)
    if z_axis is None:
        fallback = _fallback_reference_vector(x_axis, reference if user_reference else None)
        z_axis = _project_reference_on_normal_plane(fallback, x_axis)

    if z_axis is None:
        raise ValueError(
            "Impossible de construire un axe local z stable pour cette barre."
        )

    y_axis = _normalize(
        _cross(z_axis, x_axis),
        "Impossible de construire un axe local y stable pour cette barre.",
    )
    z_axis = _normalize(
        _cross(x_axis, y_axis),
        "Impossible de construire un axe local z stable pour cette barre.",
    )

    if abs(float(roll_angle_deg)) > 0.0:
        y_axis, z_axis = _rotate_yz_about_x(y_axis, z_axis, float(roll_angle_deg))

    return LocalAxes3D(x=x_axis, y=y_axis, z=z_axis)


def opensees_vecxz_from_axes(axes: LocalAxes3D) -> Vector3:
    """Retourne le vecxz OpenSees coherent avec le repere HEXA."""
    return axes.z


def _choose_reference_vector(x_axis: Vector3) -> Vector3:
    global_z = (0.0, 0.0, 1.0)
    global_x = (1.0, 0.0, 0.0)
    global_y = (0.0, 1.0, 0.0)

    if abs(_dot(x_axis, global_z)) < _PARALLEL_LIMIT:
        return global_z
    if abs(_dot(x_axis, global_x)) < _PARALLEL_LIMIT:
        return global_x
    return global_y


def _fallback_reference_vector(x_axis: Vector3, rejected: Vector3 | None = None) -> Vector3:
    candidates = (
        _choose_reference_vector(x_axis),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
    )
    for candidate in candidates:
        if rejected is not None and _almost_same_direction(candidate, rejected):
            continue
        if _project_reference_on_normal_plane(candidate, x_axis) is not None:
            return candidate
    return _choose_reference_vector(x_axis)


def _project_reference_on_normal_plane(reference: Vector3, x_axis: Vector3) -> Vector3 | None:
    projected = _sub(reference, _scale(x_axis, _dot(reference, x_axis)))
    norm = _norm(projected)
    if norm <= _ZERO_TOL:
        return None
    return _scale(projected, 1.0 / norm)


def _rotate_yz_about_x(
    y_axis: Vector3,
    z_axis: Vector3,
    angle_deg: float,
) -> tuple[Vector3, Vector3]:
    angle = math.radians(angle_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    y_rot = _add(_scale(y_axis, cosine), _scale(z_axis, sine))
    z_rot = _add(_scale(y_axis, -sine), _scale(z_axis, cosine))
    return (
        _normalize(y_rot, "Rotation locale invalide pour l'axe y."),
        _normalize(z_rot, "Rotation locale invalide pour l'axe z."),
    )


def _normalize(vector: Vector3, error_message: str) -> Vector3:
    norm = _norm(vector)
    if norm <= _ZERO_TOL:
        raise ValueError(error_message)
    return _scale(vector, 1.0 / norm)


def _norm(vector: Vector3) -> float:
    return math.sqrt(_dot(vector, vector))


def _dot(a: Vector3, b: Vector3) -> float:
    return float(a[0]) * float(b[0]) + float(a[1]) * float(b[1]) + float(a[2]) * float(b[2])


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        float(a[1]) * float(b[2]) - float(a[2]) * float(b[1]),
        float(a[2]) * float(b[0]) - float(a[0]) * float(b[2]),
        float(a[0]) * float(b[1]) - float(a[1]) * float(b[0]),
    )


def _add(a: Vector3, b: Vector3) -> Vector3:
    return (float(a[0]) + float(b[0]), float(a[1]) + float(b[1]), float(a[2]) + float(b[2]))


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (float(a[0]) - float(b[0]), float(a[1]) - float(b[1]), float(a[2]) - float(b[2]))


def _scale(vector: Vector3, factor: float) -> Vector3:
    return (float(vector[0]) * factor, float(vector[1]) * factor, float(vector[2]) * factor)


def _almost_same_direction(a: Vector3, b: Vector3) -> bool:
    try:
        norm_a = _normalize(a, "")
        norm_b = _normalize(b, "")
    except ValueError:
        return False
    return abs(_dot(norm_a, norm_b)) > 1.0 - 1.0e-10
