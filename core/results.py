"""OpenSees result extraction and post-processing."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from core.local_axes import local_axes_from_nodes

from core.optional_imports import ensure_external_module_search_paths

if TYPE_CHECKING:
    from core.model_data import ProjectModel


def _require_opensees():
    """Handle require OpenSees."""
    try:
        ensure_external_module_search_paths("openseespy", "openseespywin")
        import openseespy.opensees as _ops
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ImportError(
            "OpenSeesPy n'est pas installé. "
            "Installez-le avec 'pip install openseespy' pour extraire ces résultats."
        ) from exc
    return _ops


class _OpenSeesProxy:
    def __getattr__(self, name: str):
        return getattr(_require_opensees(), name)


ops = _OpenSeesProxy()


@dataclass
class NodalResult:
    """Result data for nodal result."""

    tag: int
    # Displacements
    ux: float = 0.0    # X displacement (m)
    uy: float = 0.0    # Y displacement (m)
    uz: float = 0.0    # Z displacement (m)
    rx: float = 0.0    # rotation autour de X (rad)
    ry: float = 0.0    # rotation autour de Y (rad)
    rz: float = 0.0    # rotation autour de Z (rad)
    # Support reactions
    fx_reaction: float = 0.0  # X reaction (kN)
    fy_reaction: float = 0.0  # Y reaction (kN)
    fz_reaction: float = 0.0  # Z reaction (kN)
    mx_reaction: float = 0.0  # X moment reaction (kN*m)
    my_reaction: float = 0.0  # Y moment reaction (kN*m)
    mz_reaction: float = 0.0  # Z moment reaction (kN*m)


@dataclass
class ElementResult:
    """Result data for element result."""

    tag: int
    # Node i (start)
    n_i: float = 0.0    # effort normal (kN), + = traction
    vy_i: float = 0.0   # effort tranchant local Y — horizontal (kN)
    vz_i: float = 0.0   # local Z shear force — vertical/gravity (kN)
    t_i: float = 0.0    # moment de torsion (kN·m)
    my_i: float = 0.0   # bending moment about Y — gravity (kN*m)
    mz_i: float = 0.0   # bending moment about Z — lateral (kN*m)
    # Node j (end)
    n_j: float = 0.0
    vy_j: float = 0.0
    vz_j: float = 0.0
    t_j: float = 0.0
    my_j: float = 0.0
    mz_j: float = 0.0

    # Compatibility properties for simplified 2D access
    @property
    def v_i(self) -> float:
        return self.vy_i

    @property
    def m_i(self) -> float:
        return self.mz_i

    @property
    def v_j(self) -> float:
        return self.vy_j

    @property
    def m_j(self) -> float:
        return self.mz_j


SURFACE_RESULTANT_COMPONENTS: tuple[str, ...] = (
    "nxx",
    "nyy",
    "nxy",
    "mxx",
    "myy",
    "mxy",
    "qx",
    "qy",
)


@dataclass
class SurfaceResult:
    """Result data for surface result."""

    tag: int
    nxx: float = 0.0
    nyy: float = 0.0
    nxy: float = 0.0
    mxx: float = 0.0
    myy: float = 0.0
    mxy: float = 0.0
    qx: float = 0.0
    qy: float = 0.0
    gauss_resultants: tuple[tuple[float, ...], ...] = field(default_factory=tuple)


class ResultsExtractor:
    """Results extractor."""

    def __init__(self, project: ProjectModel):
        self.project = project

    def get_displacements(self) -> dict[int, NodalResult]:
        """Return displacements."""
        results = {}
        for tag in self.project.nodes:
            disp = ops.nodeDisp(tag)
            n = len(disp)
            results[tag] = NodalResult(
                tag=tag,
                ux=disp[0] if n > 0 else 0.0,
                uy=disp[1] if n > 1 else 0.0,
                uz=disp[2] if n > 2 else 0.0,
                rx=disp[3] if n > 3 else 0.0,
                ry=disp[4] if n > 4 else 0.0,
                rz=disp[5] if n > 5 else 0.0,
            )
        return results

    def get_reactions(self) -> dict[int, NodalResult]:
        """Return reactions."""
        ops.reactions()
        results = {}
        for tag, node in self.project.nodes.items():
            if not node.is_fixed:
                continue
            react = ops.nodeReaction(tag)
            n = len(react)
            results[tag] = NodalResult(
                tag=tag,
                fx_reaction=react[0] if n > 0 else 0.0,
                fy_reaction=react[1] if n > 1 else 0.0,
                fz_reaction=react[2] if n > 2 else 0.0,
                mx_reaction=react[3] if n > 3 else 0.0,
                my_reaction=react[4] if n > 4 else 0.0,
                mz_reaction=react[5] if n > 5 else 0.0,
            )
        return results

    def get_element_forces(self) -> dict[int, ElementResult]:
        """Return element forces."""
        results = {}
        for tag, elem in self.project.elements.items():
            try:
                local_forces = ops.eleResponse(tag, "localForce")
            except Exception:
                local_forces = None

            if local_forces is not None and len(local_forces) >= 12:
                results[tag] = ElementResult(
                    tag=tag,
                    n_i=local_forces[0],
                    vy_i=local_forces[1],
                    vz_i=local_forces[2],
                    t_i=local_forces[3],
                    my_i=local_forces[4],
                    mz_i=local_forces[5],
                    n_j=-local_forces[6],
                    vy_j=-local_forces[7],
                    vz_j=-local_forces[8],
                    t_j=-local_forces[9],
                    my_j=-local_forces[10],
                    mz_j=-local_forces[11],
                )
                continue

            if local_forces is not None and len(local_forces) >= 6:
                # 2D beam: [N_i, V_i, M_i, N_j, V_j, M_j]
                results[tag] = ElementResult(
                    tag=tag,
                    n_i=local_forces[0],
                    vy_i=local_forces[1],
                    mz_i=local_forces[2],
                    n_j=-local_forces[3],
                    vy_j=-local_forces[4],
                    mz_j=-local_forces[5],
                )
                continue

            try:
                forces = ops.eleForce(tag)
            except Exception:
                continue

            n = len(forces)
            if n >= 2:
                # Treillis : [N_i, N_j]
                results[tag] = ElementResult(
                    tag=tag,
                    n_i=forces[0], n_j=-forces[1],
                )
        return results

    def _surface_ops_tag(self, surface_tag: int) -> int:
        """Reproduce the surface tag offset used by `OpsBuilder`."""
        return max(self.project.elements.keys(), default=0) + int(surface_tag)

    def get_surface_results(self) -> dict[int, SurfaceResult]:
        """Return surface results."""
        results: dict[int, SurfaceResult] = {}
        for tag, surface in self.project.surface_elements.items():
            if len(surface.node_tags) != 4:
                continue

            try:
                stress_resultants = ops.eleResponse(
                    self._surface_ops_tag(tag),
                    "stresses",
                )
            except Exception:
                continue

            if stress_resultants is None:
                continue

            values = np.asarray(stress_resultants, dtype=float)
            if (
                values.size < len(SURFACE_RESULTANT_COMPONENTS)
                or values.size % len(SURFACE_RESULTANT_COMPONENTS) != 0
            ):
                continue

            gauss_values = values.reshape((-1, len(SURFACE_RESULTANT_COMPONENTS)))
            average = gauss_values.mean(axis=0)
            results[tag] = SurfaceResult(
                tag=tag,
                nxx=float(average[0]),
                nyy=float(average[1]),
                nxy=float(average[2]),
                mxx=float(average[3]),
                myy=float(average[4]),
                mxy=float(average[5]),
                qx=float(average[6]),
                qy=float(average[7]),
                gauss_resultants=tuple(
                    tuple(float(value) for value in row) for row in gauss_values
                ),
            )

        return results

    def _element_rotation(self, elem) -> np.ndarray:
        """Handle element rotation."""
        ni = self.project.nodes.get(elem.node_i)
        nj = self.project.nodes.get(elem.node_j)
        if ni is None or nj is None:
            return np.eye(3)

        pi = (ni.x, ni.y, ni.z)
        pj = (nj.x, nj.y, nj.z)
        if math.dist(pi, pj) < 1e-12:
            return np.eye(3)

        axes = local_axes_from_nodes(
            pi,
            pj,
            reference_vector=getattr(elem, "orientation_vector", None),
            roll_angle_deg=float(getattr(elem, "roll_angle_deg", 0.0) or 0.0),
        )
        local_x = np.array(axes.x, dtype=float)
        local_y = np.array(axes.y, dtype=float)
        local_z = np.array(axes.z, dtype=float)

        # R: columns = local axes -> transforms local -> global
        # R^T transforme global → local
        return np.column_stack([local_x, local_y, local_z])

    def get_all(self) -> dict:
        """Return all."""
        surface_results = self.get_surface_results()
        all_nodes_fixed = bool(self.project.nodes) and all(
            node.is_fixed for node in self.project.nodes.values()
        )
        return {
            "displacements": self.get_displacements(),
            "reactions": self.get_reactions(),
            "element_forces": self.get_element_forces(),
            "surface_results": surface_results,
            "result_context": {
                "node_count": len(self.project.nodes),
                "element_count": len(self.project.elements),
                "surface_count": len(self.project.surface_elements),
                "all_nodes_fixed": all_nodes_fixed,
                "surface_results_available": bool(surface_results),
            },
        }



# ═══════════════════════════════════════════════════════════════════════════
#  Multi-case envelopes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ElementEnvelope:
    """Element envelope."""

    tag: int
    # Effort normal
    n_min: float = 0.0
    n_max: float = 0.0
    n_min_case: str = ""
    n_max_case: str = ""
    # Y shear force
    vy_min: float = 0.0
    vy_max: float = 0.0
    vy_min_case: str = ""
    vy_max_case: str = ""
    # Z shear force
    vz_min: float = 0.0
    vz_max: float = 0.0
    vz_min_case: str = ""
    vz_max_case: str = ""
    # Torsion
    t_min: float = 0.0
    t_max: float = 0.0
    t_min_case: str = ""
    t_max_case: str = ""
    # Moment Y
    my_min: float = 0.0
    my_max: float = 0.0
    my_min_case: str = ""
    my_max_case: str = ""
    # Moment Z
    mz_min: float = 0.0
    mz_max: float = 0.0
    mz_min_case: str = ""
    mz_max_case: str = ""


def compute_envelopes(
    all_results: dict[str, dict],
    element_tags: list[int],
) -> dict[int, ElementEnvelope]:
    """Compute envelopes."""
    envs: dict[int, ElementEnvelope] = {
        t: ElementEnvelope(tag=t) for t in element_tags
    }

    _COMPS = [
        ("n", "n_i", "n_j"),
        ("vy", "vy_i", "vy_j"),
        ("vz", "vz_i", "vz_j"),
        ("t", "t_i", "t_j"),
        ("my", "my_i", "my_j"),
        ("mz", "mz_i", "mz_j"),
    ]

    first = True
    for case_name, results in all_results.items():
        forces = results.get("element_forces", {})
        for tag in element_tags:
            r = forces.get(tag)
            if r is None:
                continue
            env = envs[tag]
            for prefix, attr_i, attr_j in _COMPS:
                val_i = getattr(r, attr_i, 0.0)
                val_j = getattr(r, attr_j, 0.0)
                v_min = min(val_i, val_j)
                v_max = max(val_i, val_j)

                if first or v_min < getattr(env, f"{prefix}_min"):
                    setattr(env, f"{prefix}_min", v_min)
                    setattr(env, f"{prefix}_min_case", case_name)
                if first or v_max > getattr(env, f"{prefix}_max"):
                    setattr(env, f"{prefix}_max", v_max)
                    setattr(env, f"{prefix}_max_case", case_name)
        first = False

    return envs


# ═══════════════════════════════════════════════════════════════════════════
#  Internal force interpolation along elements
# ═══════════════════════════════════════════════════════════════════════════

def interpolate_internal_forces(
    elem_result: ElementResult,
    length: float,
    wy: float = 0.0,
    wz: float = 0.0,
    wx: float = 0.0,
    n_points: int = 21,
) -> dict[str, np.ndarray]:
    """Interpolate internal forces."""
    x = np.linspace(0.0, length, n_points)
    r = elem_result

    # Effort normal : N(x) = N_i - wx·x
    N = r.n_i - wx * x

    # Horizontal shear: Vy(x) = Vy_i - wy*x
    Vy = r.vy_i - wy * x

    # Vertical shear (gravity): Vz(x) = Vz_i - wz*x
    Vz = r.vz_i - wz * x

    # Moments :
    # rebuild the quadratic law from the two moments
    # end values and the distributed load. This expression is
    # consistent for cases without distributed loads (linear
    # interpolation between nodal moments) and for uniformly loaded cases.
    if length > 1e-12:
        c_my = (r.my_j - r.my_i + wz * length**2 / 2.0) / length
        c_mz = (r.mz_j - r.mz_i + wy * length**2 / 2.0) / length
    else:
        c_my = 0.0
        c_mz = 0.0

    # Moment gravitaire : My(x) = My_i + c·x - wz·x²/2
    My = r.my_i + c_my * x - wz * x**2 / 2.0

    # Lateral moment: Mz(x) = Mz_i + c*x - wy*x^2/2
    Mz = r.mz_i + c_mz * x - wy * x**2 / 2.0

    # Torsion : constante
    T = np.full_like(x, r.t_i)

    return {"x": x, "N": N, "Vy": Vy, "Vz": Vz, "T": T, "My": My, "Mz": Mz}


def hermite_deformed_shape(
    length: float,
    uy_i: float, uy_j: float,
    rz_i: float, rz_j: float,
    uz_i: float, uz_j: float,
    ry_i: float, ry_j: float,
    n_points: int = 11,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Handle hermite deformed shape."""
    xi = np.linspace(0.0, 1.0, n_points)

    # Hermite shape functions (parameter xi = x/L)
    N1 = 1.0 - 3.0 * xi**2 + 2.0 * xi**3
    N2 = length * (xi - 2.0 * xi**2 + xi**3)
    N3 = 3.0 * xi**2 - 2.0 * xi**3
    N4 = length * (-xi**2 + xi**3)

    # Transverse Y displacement (bending in the XY plane)
    dy = N1 * uy_i + N2 * rz_i + N3 * uy_j + N4 * rz_j

    # Transverse Z displacement (bending in the XZ plane)
    # Note: the sign of ry is inverted (right-hand convention)
    dz = N1 * uz_i - N2 * ry_i + N3 * uz_j - N4 * ry_j

    return xi, dy, dz
