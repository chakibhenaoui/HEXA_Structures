"""2D internal force and load diagram rendering helpers."""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure
from PySide6.QtCore import QCoreApplication

from config.settings import DisplayUnits
from core.optional_imports import ensure_external_module_search_paths
from core import section_force_convention as _force_convention
from gui.i18n.display_labels import tagged_load_label
from utils.units import INTERNAL_UNITS, Quantity, find_unit


try:  # opsvis exposes element load reading through this helper
    from opsvis.model import get_Ew_data_from_ops_domain_3d
except Exception:  # pragma: no cover
    get_Ew_data_from_ops_domain_3d = None  # type: ignore

try:  # pragma: no cover
    from core.model_data import ElementData, ProjectModel
    from core.results import ElementResult, interpolate_internal_forces
    from core.self_weight import (
        element_load_local_components,
        element_self_weight_local_components,
        is_self_weight_load,
    )
except Exception:  # pragma: no cover
    ElementData = None  # type: ignore
    ProjectModel = None  # type: ignore
    ElementResult = None  # type: ignore
    element_load_local_components = None  # type: ignore
    element_self_weight_local_components = None  # type: ignore
    is_self_weight_load = None  # type: ignore


def _require_opensees():
    """Handle require OpenSees."""
    try:
        ensure_external_module_search_paths("openseespy", "openseespywin")
        import openseespy.opensees as _ops
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ImportError(
            "OpenSeesPy n'est pas installé. "
            "Les diagrammes OpenSees ne sont donc pas disponibles."
        ) from exc
    return _ops


class _OpenSeesProxy:
    def __getattr__(self, name: str):
        return getattr(_require_opensees(), name)


ops = _OpenSeesProxy()


def _require_opsvis_section_force_distribution_3d():
    """Handle require opsvis section force distribution 3D."""
    try:
        from opsvis.secforces import section_force_distribution_3d
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ImportError(
            "opsvis n'est pas installé. "
            "Les diagrammes OpenSees détaillés ne sont donc pas disponibles."
        ) from exc
    return section_force_distribution_3d


_COMP_TITLES: dict[str, str] = {
    "N":  "Effort normal N (kN)",
    "Vy": "Effort tranchant Vy (kN)",
    "Vz": "Effort tranchant Vz (kN)",
    "T":  "Moment de torsion T (kN·m)",
    "My": "Moment de flexion My (kN·m)",
    "Mz": "Moment de flexion Mz (kN·m)",
}

_COMP_NOTES: dict[str, str] = {
    "N": "Convention : N > 0 = traction suivant l'axe local x de l'élément.",
    "Vy": "Convention : Vy > 0 = effort tranchant positif suivant l'axe local y.",
    "Vz": "Convention : Vz > 0 = effort tranchant positif suivant l'axe local z.",
    "T": "Convention : T > 0 = torsion positive autour de l'axe local x (main droite).",
    "My": (
        "Convention d'affichage : My > 0 = fibre tendue en bas des poutres "
        "et fibre tendue côté extérieur des poteaux."
    ),
    "Mz": (
        "Convention : Mz > 0 = rotation positive autour de l'axe local z "
        "(main droite). Le diagramme est affiché côté fibre tendue."
    ),
}

_COMP_IDX: dict[str, int] = {
    "N": 0, "Vy": 1, "Vz": 2, "T": 3, "My": 4, "Mz": 5,
}

_PLANE_INDICES = _force_convention.PLANE_INDICES

_PLANE_WHEN_AXIS_CONST = {0: "YZ", 1: "XZ", 2: "XY"}
_AXIS_NAMES = ("X", "Y", "Z")
_SUPPORT_COLORS = {
    "fixed": "#b80fb8",
    "pinned": "#f39c12",
    "partial": "#f1c40f",
}
_LOAD_NODE_COLOR = "b"
_LOAD_ELEMENT_COLOR = "r"
_LOAD_ELEMENT_AXIAL_COLOR = "m"
_LOAD_MOMENT_COLOR = "r"
_DIAGRAM_POSITIVE_COLOR = "#15803d"
_DIAGRAM_NEGATIVE_COLOR = "#d62828"
_DIAGRAM_ZERO_COLOR = "#6b7280"
_DIAGRAM_ZERO_TOL = 1e-9
_AUTO_DIAGRAM_SCALE_RATIO = 0.12
_DIAGRAM_FILL_ALPHA = 0.10
_DIAGRAM_RIB_ALPHA = 0.55
_DIAGRAM_CURVE_ALPHA = 0.82


def _is_supported_diagram_plane(plane: str | None) -> bool:
    """Return whether supported diagram plane."""
    return plane in {"XZ", "YZ"}


def _detect_files_from_project(project: ProjectModel) -> list[dict]:
    """Detect files from project."""
    ele_tags = list(project.elements.keys())
    if not project.nodes or not ele_tags:
        return []

    coords = {
        tag: np.array([node.x, node.y, node.z], dtype=float)
        for tag, node in project.nodes.items()
    }
    all_coords = np.array(list(coords.values()))
    span = all_coords.max(axis=0) - all_coords.min(axis=0)
    diag = float(np.linalg.norm(span))
    tol = max(1e-6, diag * 1e-4)

    if span[1] < tol:
        global_plane = "XZ"
    elif span[0] < tol:
        global_plane = "YZ"
    elif span[2] < tol:
        global_plane = "XY"
    else:
        global_plane = None

    files: list[dict] = []
    if _is_supported_diagram_plane(global_plane):
        files.append({
            "label": QCoreApplication.translate(
                "DiagramRenderer",
                "Ensemble (plan {plane})",
            ).format(plane=global_plane),
            "plane": global_plane,
            "ele_tags": ele_tags,
            "axis": None,
            "value": None,
        })
        return files
    if global_plane is not None:
        return files

    for axis_idx in range(3):
        plane = _PLANE_WHEN_AXIS_CONST[axis_idx]
        if not _is_supported_diagram_plane(plane):
            continue
        vals = sorted({
            round(float(coords[tag][axis_idx]) / tol) * tol
            for tag in project.nodes
        })
        for value in vals:
            ele_in_file: list[int] = []
            for ele_tag, element in project.elements.items():
                c1 = coords[element.node_i]
                c2 = coords[element.node_j]
                if (
                    abs(c1[axis_idx] - value) < tol
                    and abs(c2[axis_idx] - value) < tol
                ):
                    ele_in_file.append(ele_tag)

            if not ele_in_file:
                continue

            files.append({
                "label": (
                    QCoreApplication.translate(
                        "DiagramRenderer",
                        "File {axis} = {value:.3g} m ({count} él.)",
                    ).format(
                        axis=_AXIS_NAMES[axis_idx],
                        value=value,
                        count=len(ele_in_file),
                    )
                ),
                "plane": plane,
                "ele_tags": ele_in_file,
                "axis": axis_idx,
                "value": float(value),
            })

    return files
# ══════════════════════════════════════════════════════════════════════════
#  Grid line detection
# ══════════════════════════════════════════════════════════════════════════

def detect_files(project: ProjectModel | None = None) -> list[dict]:
    """Detect files."""
    if project is not None:
        return _detect_files_from_project(project)

    node_tags = ops.getNodeTags()
    ele_tags = list(ops.getEleTags())
    if not node_tags or not ele_tags:
        return []

    coords = {t: np.array(ops.nodeCoord(t), dtype=float) for t in node_tags}
    all_coords = np.array(list(coords.values()))
    span = all_coords.max(axis=0) - all_coords.min(axis=0)
    diag = float(np.linalg.norm(span))
    tol = max(1e-6, diag * 1e-4)

    # Global plane: detect it when the structure is already planar.
    if span[1] < tol:
        global_plane = "XZ"
    elif span[0] < tol:
        global_plane = "YZ"
    elif span[2] < tol:
        global_plane = "XY"
    else:
        global_plane = None

    files: list[dict] = []
    if _is_supported_diagram_plane(global_plane):
        files.append({
            "label": QCoreApplication.translate(
                "DiagramRenderer",
                "Ensemble (plan {plane})",
            ).format(plane=global_plane),
            "plane": global_plane,
            "ele_tags": ele_tags,
            "axis": None,
            "value": None,
        })
        return files
    if global_plane is not None:
        return files

    # Otherwise, list only compatible vertical planes for each axis.
    for axis_idx in range(3):
        plane = _PLANE_WHEN_AXIS_CONST[axis_idx]
        if not _is_supported_diagram_plane(plane):
            continue
        vals = sorted({
            round(float(coords[t][axis_idx]) / tol) * tol
            for t in node_tags
        })
        for v in vals:
            ele_in_file: list[int] = []
            for et in ele_tags:
                en = ops.eleNodes(et)
                if len(en) != 2:
                    continue
                c1 = coords[en[0]]
                c2 = coords[en[1]]
                if (abs(c1[axis_idx] - v) < tol
                        and abs(c2[axis_idx] - v) < tol):
                    ele_in_file.append(et)

            if len(ele_in_file) < 1:
                continue

            files.append({
                "label": (
                    QCoreApplication.translate(
                        "DiagramRenderer",
                        "File {axis} = {value:.3g} m ({count} él.)",
                    ).format(
                        axis=_AXIS_NAMES[axis_idx],
                        value=v,
                        count=len(ele_in_file),
                    )
                ),
                "plane": plane,
                "ele_tags": ele_in_file,
                "axis": axis_idx,
                "value": float(v),
            })

    return files


def detect_load_files(project: ProjectModel) -> list[dict]:
    """Detect load files."""
    if not project.nodes:
        return []

    coords = {
        tag: np.array([node.x, node.y, node.z], dtype=float)
        for tag, node in project.nodes.items()
    }
    all_coords = np.array(list(coords.values()))
    span = all_coords.max(axis=0) - all_coords.min(axis=0)
    diag = float(np.linalg.norm(span))
    tol = max(1e-6, diag * 1e-4)

    if span[1] < tol:
        global_plane = "XZ"
    elif span[0] < tol:
        global_plane = "YZ"
    elif span[2] < tol:
        global_plane = "XY"
    else:
        global_plane = None

    all_node_tags = sorted(project.nodes.keys())
    all_ele_tags = sorted(project.elements.keys())
    if global_plane is not None:
        return [{
            "label": QCoreApplication.translate(
                "DiagramRenderer",
                "Ensemble (plan {plane})",
            ).format(plane=global_plane),
            "plane": global_plane,
            "ele_tags": all_ele_tags,
            "node_tags": all_node_tags,
            "axis": None,
            "value": None,
        }]

    files: list[dict] = []
    for axis_idx, axis_name in enumerate(_AXIS_NAMES):
        plane = _PLANE_WHEN_AXIS_CONST[axis_idx]
        values = sorted({
            round(float(coords[tag][axis_idx]) / tol) * tol
            for tag in project.nodes
        })
        for value in values:
            node_tags = [
                tag for tag, point in coords.items()
                if abs(point[axis_idx] - value) < tol
            ]
            ele_tags: list[int] = []
            for ele_tag, element in project.elements.items():
                c1 = coords[element.node_i]
                c2 = coords[element.node_j]
                if (
                    abs(c1[axis_idx] - value) < tol
                    and abs(c2[axis_idx] - value) < tol
                ):
                    ele_tags.append(ele_tag)

            if not node_tags and not ele_tags:
                continue

            files.append({
                "label": (
                    QCoreApplication.translate(
                        "DiagramRenderer",
                        "Plan {axis} = {value:.3g} m ({elements} él., {nodes} nd.)",
                    ).format(
                        axis=axis_name,
                        value=value,
                        elements=len(ele_tags),
                        nodes=len(node_tags),
                    )
                ),
                "plane": plane,
                "ele_tags": sorted(ele_tags),
                "node_tags": sorted(node_tags),
                "axis": axis_idx,
                "value": float(value),
            })

    return files


# ══════════════════════════════════════════════════════════════════════════
#  Sampled internal force calculation
# ══════════════════════════════════════════════════════════════════════════

def _element_samples(
    ele_tag: int,
    component: str,
    nep: int,
    plane: str | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """Handle element samples."""
    en = ops.eleNodes(ele_tag)
    if len(en) != 2:
        return None
    c1 = np.array(ops.nodeCoord(en[0]), dtype=float)
    c2 = np.array(ops.nodeCoord(en[1]), dtype=float)
    if c1.size < 3:
        c1 = np.concatenate([c1, np.zeros(3 - c1.size)])
        c2 = np.concatenate([c2, np.zeros(3 - c2.size)])

    try:
        pl = ops.eleResponse(ele_tag, "localForce")
    except Exception:
        return None
    if len(pl) != 12:
        return None

    Ew = (
        get_Ew_data_from_ops_domain_3d()
        if callable(get_Ew_data_from_ops_domain_3d)
        else {}
    )
    eload = Ew.get(ele_tag, [["-beamUniform", 0.0, 0.0, 0.0]])

    ecrd_3d = np.vstack([c1, c2])
    try:
        section_force_distribution_3d = _require_opsvis_section_force_distribution_3d()
        s_all, xl, _nep = section_force_distribution_3d(
            ecrd_3d, pl, nep, eload,
        )
    except Exception:
        return None

    sample_component = _sample_component_for_display(component, plane, ecrd_3d)
    ss = s_all[:, _COMP_IDX[sample_component]]
    return ecrd_3d, xl, ss, eload


def _element_coords_from_project(
    project: ProjectModel,
    element: ElementData,
) -> np.ndarray | None:
    """Handle element coords from project."""
    node_i = project.nodes.get(element.node_i)
    node_j = project.nodes.get(element.node_j)
    if node_i is None or node_j is None:
        return None
    return np.array(
        [
            [node_i.x, node_i.y, node_i.z],
            [node_j.x, node_j.y, node_j.z],
        ],
        dtype=float,
    )


def _case_distributed_loads(
    project: ProjectModel,
    load_tag: int | None = None,
    combo_tag: int | None = None,
) -> dict[int, tuple[float, float, float]]:
    """Handle case distributed loads."""
    factors: dict[int, float] = {}
    if combo_tag is not None:
        combo = project.combinations.get(combo_tag)
        if combo is not None:
            factors = {
                int(tag): float(factor)
                for tag, factor in combo.factors.items()
            }
    elif load_tag is not None:
        factors = {int(load_tag): 1.0}

    loads: dict[int, list[float]] = {}
    for load in project.element_loads:
        factor = factors.get(load.load_tag, 0.0)
        if abs(factor) <= 1e-12:
            continue
        element = project.elements.get(load.element_tag)
        if element is None:
            continue
        if callable(element_load_local_components):
            wx, wy, wz = element_load_local_components(project, element, load)
        else:
            wx, wy, wz = float(load.wx), float(load.wy), float(load.wz)
        acc = loads.setdefault(load.element_tag, [0.0, 0.0, 0.0])
        acc[0] += factor * float(wx)
        acc[1] += factor * float(wy)
        acc[2] += factor * float(wz)

    return {
        element_tag: (values[0], values[1], values[2])
        for element_tag, values in loads.items()
    }


def _element_samples_from_results(
    project: ProjectModel,
    results: dict,
    element_loads: dict[int, tuple[float, float, float]],
    ele_tag: int,
    component: str,
    nep: int,
    plane: str | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[float, float, float]] | None:
    """Handle element samples from results."""
    element = project.elements.get(ele_tag)
    if element is None:
        return None

    elem_result: ElementResult | None = results.get("element_forces", {}).get(ele_tag)
    if elem_result is None:
        return None

    ecrd_3d = _element_coords_from_project(project, element)
    if ecrd_3d is None:
        return None

    length = float(np.linalg.norm(ecrd_3d[1] - ecrd_3d[0]))
    if length < 1e-12:
        return None

    wx, wy, wz = element_loads.get(ele_tag, (0.0, 0.0, 0.0))
    forces = interpolate_internal_forces(
        elem_result,
        length=length,
        wx=wx,
        wy=wy,
        wz=wz,
        n_points=nep,
    )
    sample_component = _sample_component_for_display(component, plane, ecrd_3d)
    ss = np.asarray(forces[sample_component], dtype=float)
    xl = np.asarray(forces["x"], dtype=float)
    return ecrd_3d, xl, ss, (wx, wy, wz)


def _element_samples_from_backend(
    project: ProjectModel,
    backend,
    ele_tag: int,
    component: str,
    nep: int,
    plane: str | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[float, float, float]] | None:
    """Handle element samples from backend."""
    element = project.elements.get(ele_tag)
    if element is None:
        return None

    ecrd_3d = _element_coords_from_project(project, element)
    if ecrd_3d is None:
        return None

    sampler = getattr(backend, "sample_diagram_component", None)
    if sampler is None:
        return None

    sample_component = _sample_component_for_display(component, plane, ecrd_3d)
    sampled = sampler(ele_tag, sample_component, nep=nep)
    if sampled is None:
        return None

    xl, ss = sampled
    return ecrd_3d, np.asarray(xl, dtype=float), np.asarray(ss, dtype=float), (0.0, 0.0, 0.0)


def _compute_component_range(
    component: str,
    ele_tags: list[int],
    nep: int = 17,
    *,
    plane: str | None = None,
) -> tuple[float, float]:
    """Compute component range."""
    min_val, max_val = np.inf, -np.inf
    for et in ele_tags:
        res = _element_samples(et, component, nep, plane=plane)
        if res is None:
            continue
        ss = res[2]
        if ss.size == 0:
            continue
        min_val = min(min_val, float(np.min(ss)))
        max_val = max(max_val, float(np.max(ss)))
    if not np.isfinite(min_val):
        return 0.0, 0.0
    return min_val, max_val


def _compute_component_range_from_results(
    component: str,
    project: ProjectModel,
    results: dict,
    ele_tags: list[int],
    element_loads: dict[int, tuple[float, float, float]],
    nep: int = 17,
    *,
    plane: str | None = None,
) -> tuple[float, float]:
    """Compute component range from results."""
    min_val, max_val = np.inf, -np.inf
    for ele_tag in ele_tags:
        res = _element_samples_from_results(
            project,
            results,
            element_loads,
            ele_tag,
            component,
            nep,
            plane=plane,
        )
        if res is None:
            continue
        ss = res[2]
        if ss.size == 0:
            continue
        min_val = min(min_val, float(np.min(ss)))
        max_val = max(max_val, float(np.max(ss)))

    if not np.isfinite(min_val):
        return 0.0, 0.0
    return min_val, max_val


def _compute_component_range_from_backend(
    component: str,
    project: ProjectModel,
    backend,
    ele_tags: list[int],
    nep: int = 17,
    *,
    plane: str | None = None,
) -> tuple[float, float]:
    """Compute component range from backend."""
    min_val, max_val = np.inf, -np.inf
    for ele_tag in ele_tags:
        res = _element_samples_from_backend(
            project,
            backend,
            ele_tag,
            component,
            nep,
            plane=plane,
        )
        if res is None:
            continue
        ss = res[2]
        if ss.size == 0:
            continue
        min_val = min(min_val, float(np.min(ss)))
        max_val = max(max_val, float(np.max(ss)))

    if not np.isfinite(min_val):
        return 0.0, 0.0
    return min_val, max_val


_DiagramConvention = _force_convention.DiagramConvention
_canonicalize_projected_samples = _force_convention.canonicalize_projected_samples
_choose_outward_normal = _force_convention.choose_outward_normal
_element_local_axes = _force_convention.element_local_axes
_canonical_element_local_axes = _force_convention.canonical_element_local_axes
_canonicalize_component_samples = _force_convention.canonicalize_component_samples
_component_display_sign = _force_convention.component_display_sign
_diagram_direction_2d = _force_convention.diagram_direction_2d
_bending_reference_side_2d = _force_convention.bending_reference_side_2d
_diagram_convention_for_element = _force_convention.diagram_convention_for_element
_display_component_values = _force_convention.display_component_values
_choose_file_diagram_side = _force_convention.choose_file_diagram_side
_diagram_direction_for_file = _force_convention.diagram_direction_for_file
_resolve_display_samples = _force_convention.resolve_display_samples
_sample_component_for_display = _force_convention.sample_component_for_display


def _value_color(value: float) -> str:
    """Handle value color."""
    if value > _DIAGRAM_ZERO_TOL:
        return _DIAGRAM_POSITIVE_COLOR
    if value < -_DIAGRAM_ZERO_TOL:
        return _DIAGRAM_NEGATIVE_COLOR
    return _DIAGRAM_ZERO_COLOR


def _format_diagram_value(value: float) -> str:
    """Format diagram value."""
    if abs(value) <= _DIAGRAM_ZERO_TOL:
        return "0"
    return f"{value:+.4g}"


def _hatch_sample_indices(count: int, max_ribs: int = 7) -> list[int]:
    """Handle hatch sample indices."""
    if count <= 0:
        return []
    if count <= max_ribs:
        return list(range(count))

    step = max(1, int(np.ceil((count - 1) / max(max_ribs - 1, 1))))
    indices = list(range(0, count, step))
    if indices[-1] != count - 1:
        indices.append(count - 1)
    return indices


def _label_candidate_indices(values: np.ndarray) -> list[int]:
    """Handle label candidate indices."""
    if values.size == 0:
        return []

    max_abs = float(np.max(np.abs(values)))
    significant = max(_DIAGRAM_ZERO_TOL, max_abs * 0.05)
    candidates: list[tuple[int, float, int]] = []

    def add(idx: int, priority: int) -> None:
        if idx < 0 or idx >= len(values):
            return
        magnitude = float(abs(values[idx]))
        if magnitude < significant and candidates:
            return
        candidates.append((priority, -magnitude, idx))

    add(int(np.argmax(np.abs(values))), 0)
    add(0, 1)
    add(len(values) - 1, 1)
    add(int(np.argmax(values)), 2)
    add(int(np.argmin(values)), 2)

    ordered: list[int] = []
    seen: set[int] = set()
    for _, _, idx in sorted(candidates):
        if idx in seen:
            continue
        seen.add(idx)
        ordered.append(idx)
    return ordered


def _find_label_position(
    anchor: np.ndarray,
    diagram_dir: np.ndarray,
    label_offset: float,
    placed_positions: list[np.ndarray],
    min_distance: float,
    *,
    allow_forced: bool = False,
) -> tuple[np.ndarray, bool] | None:
    """Find label position."""
    direction_norm = float(np.linalg.norm(diagram_dir))
    if direction_norm < 1e-12:
        direction = np.array([0.0, 1.0], dtype=float)
    else:
        direction = diagram_dir / direction_norm
    tangent = np.array([-direction[1], direction[0]], dtype=float)

    for radial_scale in (1.0, 1.7, 2.4, 3.1, 3.8):
        for lateral_scale in (0.0, 0.6, -0.6, 1.2, -1.2):
            pos = (
                anchor
                + direction * label_offset * radial_scale
                + tangent * label_offset * lateral_scale
            )
            if any(
                float(np.linalg.norm(pos - other)) < min_distance
                for other in placed_positions
            ):
                continue
            moved = radial_scale > 1.0 or abs(lateral_scale) > 1e-12
            return pos, moved

    if not allow_forced:
        return None

    pos = anchor + direction * label_offset * 4.5
    return pos, True


def _place_diagram_labels(
    ax,
    points_2d: np.ndarray,
    values: np.ndarray,
    diagram_dir: np.ndarray,
    label_offset: float,
    placed_positions: list[np.ndarray],
    *,
    allow_forced: bool = False,
) -> None:
    """Handle place diagram labels."""
    if values.size == 0:
        return

    min_distance = max(label_offset * 2.4, 0.18)
    for idx in _label_candidate_indices(values):
        value = float(values[idx])
        if abs(value) <= _DIAGRAM_ZERO_TOL and placed_positions:
            continue

        anchor = points_2d[idx]
        label_position = _find_label_position(
            anchor,
            diagram_dir,
            label_offset,
            placed_positions,
            min_distance,
            allow_forced=allow_forced,
        )
        if label_position is None:
            continue
        pos, moved = label_position
        label_color = _value_color(value)

        ax.annotate(
            _format_diagram_value(value),
            xy=(anchor[0], anchor[1]),
            xytext=(pos[0], pos[1]),
            textcoords="data",
            fontsize=8,
            color=label_color,
            ha="center",
            va="center",
            zorder=6,
            bbox={
                "boxstyle": "square,pad=0.18",
                "facecolor": "white",
                "edgecolor": label_color,
                "linewidth": 0.8,
                "alpha": 0.88,
            },
            arrowprops=(
                {
                    "arrowstyle": "-",
                    "color": label_color,
                    "linewidth": 0.8,
                    "alpha": 0.65,
                    "shrinkA": 0,
                    "shrinkB": 0,
                }
                if moved
                else None
            ),
        )
        placed_positions.append(pos)


def _signed_diagram_segment_polygons(
    base_p1: np.ndarray,
    base_p2: np.ndarray,
    diag_p1: np.ndarray,
    diag_p2: np.ndarray,
    value_1: float,
    value_2: float,
) -> list[tuple[np.ndarray, float]]:
    """Handle signed diagram segment polygons."""
    if abs(value_1) <= _DIAGRAM_ZERO_TOL and abs(value_2) <= _DIAGRAM_ZERO_TOL:
        return []

    if value_1 == 0.0 or value_2 == 0.0 or value_1 * value_2 > 0.0:
        polygon = np.vstack([base_p1, base_p2, diag_p2, diag_p1])
        ref_value = value_1 if abs(value_1) >= abs(value_2) else value_2
        return [(polygon, ref_value)]

    ratio = abs(value_1) / (abs(value_1) + abs(value_2))
    zero_pt = base_p1 + ratio * (base_p2 - base_p1)
    return [
        (np.vstack([base_p1, zero_pt, diag_p1]), value_1),
        (np.vstack([zero_pt, base_p2, diag_p2]), value_2),
    ]


def _fill_signed_diagram_band(
    ax,
    base_points: np.ndarray,
    diag_points: np.ndarray,
    values: np.ndarray,
) -> None:
    """Handle fill signed diagram band."""
    for idx in range(len(values) - 1):
        polygons = _signed_diagram_segment_polygons(
            base_points[idx],
            base_points[idx + 1],
            diag_points[idx],
            diag_points[idx + 1],
            float(values[idx]),
            float(values[idx + 1]),
        )
        for polygon, ref_value in polygons:
            if abs(ref_value) <= _DIAGRAM_ZERO_TOL:
                continue
            ax.fill(
                polygon[:, 0],
                polygon[:, 1],
                facecolor=_value_color(ref_value),
                edgecolor="none",
                alpha=_DIAGRAM_FILL_ALPHA,
                zorder=1,
            )


def _draw_sampled_diagram_element(
    ax,
    component: str,
    plane: str,
    ecrd_3d: np.ndarray,
    xl: np.ndarray,
    ss: np.ndarray,
    sfac: float,
    file_center: np.ndarray,
    file_tol: float,
    file_boundary_sign: float,
    placed_label_positions: list[np.ndarray],
    label_offset: float,
    apply_component_axis_sign: bool = True,
) -> tuple[float, float] | None:
    """Draw sampled diagram element."""
    if ss.size < 2:
        return None

    i1, i2 = _PLANE_INDICES[plane]
    p1 = np.array([ecrd_3d[0, i1], ecrd_3d[0, i2]], dtype=float)
    p2 = np.array([ecrd_3d[1, i1], ecrd_3d[1, i2]], dtype=float)
    length_2d = float(np.linalg.norm(p2 - p1))
    if length_2d < 1e-12:
        return None

    length_3d = float(np.linalg.norm(ecrd_3d[1] - ecrd_3d[0]))
    if length_3d < 1e-12:
        return None

    sample_component = _sample_component_for_display(component, plane, ecrd_3d)
    display = _resolve_display_samples(
        ecrd_3d=ecrd_3d,
        p1=p1,
        p2=p2,
        x=xl,
        values=ss,
        component=component,
        plane=plane,
        file_center=file_center,
        file_tol=file_tol,
        file_boundary_sign=file_boundary_sign,
        apply_component_axis_sign=apply_component_axis_sign,
        sample_component=sample_component,
    )
    if display is None:
        return None

    p1 = display.p1
    p2 = display.p2
    xl = display.x
    ss = display.values
    diagram_dir = display.direction_2d

    t = xl / length_3d
    s_0 = np.zeros((len(xl), 2))
    s_0[:, 0] = p1[0] + t * (p2[0] - p1[0])
    s_0[:, 1] = p1[1] + t * (p2[1] - p1[1])

    s_p = np.copy(s_0)
    scaled_values = ss * sfac
    s_p[:, 0] += scaled_values * diagram_dir[0]
    s_p[:, 1] += scaled_values * diagram_dir[1]

    _fill_signed_diagram_band(ax, s_0, s_p, ss)

    for idx in _hatch_sample_indices(len(xl)):
        ax.plot(
            [s_0[idx, 0], s_p[idx, 0]],
            [s_0[idx, 1], s_p[idx, 1]],
            color=_value_color(float(ss[idx])),
            linewidth=0.8,
            alpha=_DIAGRAM_RIB_ALPHA,
            zorder=2,
        )

    for idx in range(len(xl) - 1):
        _plot_signed_segment(
            ax,
            s_p[idx],
            s_p[idx + 1],
            float(ss[idx]),
            float(ss[idx + 1]),
        )

    _place_diagram_labels(
        ax,
        s_p,
        ss,
        diagram_dir,
        label_offset,
        placed_label_positions,
    )
    return float(np.min(ss)), float(np.max(ss))


def _draw_sampled_local_diagram_element(
    ax,
    component: str,
    xl: np.ndarray,
    ss: np.ndarray,
    sfac: float,
    placed_label_positions: list[np.ndarray],
    label_offset: float,
) -> tuple[float, float] | None:
    """Draw sampled local diagram element."""
    if ss.size < 2 or xl.size < 2:
        return None

    order = np.argsort(xl)
    xl = np.asarray(xl, dtype=float)[order]
    ss = np.asarray(ss, dtype=float)[order]
    ss = _display_component_values(component, ss)

    s_0 = np.zeros((len(xl), 2), dtype=float)
    s_0[:, 0] = xl
    s_p = np.copy(s_0)
    s_p[:, 1] = ss * sfac
    diagram_dir = np.array([0.0, 1.0], dtype=float)

    _fill_signed_diagram_band(ax, s_0, s_p, ss)

    for idx in _hatch_sample_indices(len(xl)):
        ax.plot(
            [s_0[idx, 0], s_p[idx, 0]],
            [s_0[idx, 1], s_p[idx, 1]],
            color=_value_color(float(ss[idx])),
            linewidth=0.8,
            alpha=_DIAGRAM_RIB_ALPHA,
            zorder=2,
        )

    for idx in range(len(xl) - 1):
        _plot_signed_segment(
            ax,
            s_p[idx],
            s_p[idx + 1],
            float(ss[idx]),
            float(ss[idx + 1]),
        )

    _place_diagram_labels(
        ax,
        s_p,
        ss,
        diagram_dir,
        label_offset,
        placed_label_positions,
    )
    return float(np.min(ss)), float(np.max(ss))


def _plot_signed_segment(ax, p1: np.ndarray, p2: np.ndarray, v1: float, v2: float) -> None:
    """Plot signed segment."""
    if abs(v1) < _DIAGRAM_ZERO_TOL and abs(v2) < _DIAGRAM_ZERO_TOL:
        ax.plot(
            [p1[0], p2[0]], [p1[1], p2[1]],
            color=_DIAGRAM_ZERO_COLOR,
            linewidth=1.8,
            alpha=_DIAGRAM_CURVE_ALPHA,
            zorder=4,
        )
        return

    if v1 == 0.0 or v2 == 0.0 or v1 * v2 > 0.0:
        color = _value_color(v1 if abs(v1) >= abs(v2) else v2)
        ax.plot(
            [p1[0], p2[0]],
            [p1[1], p2[1]],
            color=color,
            linewidth=1.8,
            alpha=_DIAGRAM_CURVE_ALPHA,
            zorder=4,
        )
        return

    ratio = abs(v1) / (abs(v1) + abs(v2))
    pm = p1 + ratio * (p2 - p1)
    ax.plot(
        [p1[0], pm[0]], [p1[1], pm[1]],
        color=_value_color(v1),
        linewidth=1.8,
        alpha=_DIAGRAM_CURVE_ALPHA,
        zorder=4,
    )
    ax.plot(
        [pm[0], p2[0]], [pm[1], p2[1]],
        color=_value_color(v2),
        linewidth=1.8,
        alpha=_DIAGRAM_CURVE_ALPHA,
        zorder=4,
    )


# ══════════════════════════════════════════════════════════════════════════
#  Rendu 2D
# ══════════════════════════════════════════════════════════════════════════

def _plot_model_2d(
    ax,
    ele_tags: list[int],
    plane: str,
    project: ProjectModel | None = None,
) -> None:
    """Plot model 2D."""
    i1, i2 = _PLANE_INDICES[plane]
    for et in ele_tags:
        if project is not None:
            element = project.elements.get(et)
            if element is None:
                continue
            coords = _element_coords_from_project(project, element)
            if coords is None:
                continue
            c1, c2 = coords
        else:
            en = ops.eleNodes(et)
            if len(en) != 2:
                continue
            c1 = np.array(ops.nodeCoord(en[0]), dtype=float)
            c2 = np.array(ops.nodeCoord(en[1]), dtype=float)
        ax.plot(
            [c1[i1], c2[i1]], [c1[i2], c2[i2]],
            color="black", linewidth=1.5, zorder=3,
        )


def _plot_supports_2d(
    ax,
    project: ProjectModel | None,
    ele_tags: list[int],
    plane: str,
    scale: float,
    node_tags: list[int] | None = None,
) -> None:
    """Plot supports 2D."""
    if project is None:
        return

    i1, i2 = _PLANE_INDICES[plane]
    visible_node_tags: set[int] = set(node_tags or [])
    for et in ele_tags:
        element = project.elements.get(et)
        if element is None:
            continue
        visible_node_tags.update((element.node_i, element.node_j))

    for nt in sorted(visible_node_tags):
        node = project.nodes.get(nt)
        if node is None or not node.is_support:
            continue

        pt = np.array([node.x, node.y, node.z], dtype=float)
        p2d = np.array([pt[i1], pt[i2]], dtype=float)
        fix = node.fixities
        n_trans = sum(fix[:3])
        n_rot = sum(fix[3:])
        pos = p2d

        if n_trans == 3 and n_rot == 3:
            ax.scatter(
                [pos[0]], [pos[1]],
                s=150, marker="s", c=_SUPPORT_COLORS["fixed"],
                edgecolors=_SUPPORT_COLORS["fixed"], zorder=7,
            )
        elif n_trans >= 2:
            ax.scatter(
                [pos[0]], [pos[1]],
                s=180, marker="^", c=_SUPPORT_COLORS["pinned"],
                edgecolors=_SUPPORT_COLORS["pinned"], zorder=7,
            )
        else:
            ax.scatter(
                [pos[0]], [pos[1]],
                s=90, marker="o", c=_SUPPORT_COLORS["partial"],
                edgecolors="#6b5d00", linewidths=1.0, zorder=7,
            )


def _plot_nodes_2d(
    ax,
    project: ProjectModel,
    node_tags: list[int],
    plane: str,
) -> None:
    """Plot nodes 2D."""
    i1, i2 = _PLANE_INDICES[plane]
    xs: list[float] = []
    ys: list[float] = []
    for node_tag in node_tags:
        node = project.nodes.get(node_tag)
        if node is None:
            continue
        coords = (node.x, node.y, node.z)
        xs.append(float(coords[i1]))
        ys.append(float(coords[i2]))
    if xs:
        ax.scatter(xs, ys, s=18, c="black", zorder=4)


def _aggregate_case_nodal_loads(
    project: ProjectModel,
    load_tag: int,
) -> dict[int, tuple[float, float, float, float, float, float]]:
    """Aggregate case nodal loads."""
    loads: dict[int, list[float]] = {}
    for load in project.nodal_loads:
        if load.load_tag != load_tag:
            continue
        acc = loads.setdefault(load.node_tag, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        acc[0] += float(load.fx)
        acc[1] += float(load.fy)
        acc[2] += float(load.fz)
        acc[3] += float(load.mx)
        acc[4] += float(load.my)
        acc[5] += float(load.mz)
    return {node_tag: tuple(values) for node_tag, values in loads.items()}


def _aggregate_case_element_loads(
    project: ProjectModel,
    load_tag: int,
) -> dict[int, tuple[float, float, float]]:
    """Aggregate case element loads."""
    loads: dict[int, list[float]] = {}
    for load in project.element_loads:
        if load.load_tag != load_tag:
            continue
        element = project.elements.get(load.element_tag)
        if element is None:
            continue
        if callable(element_load_local_components):
            wx, wy, wz = element_load_local_components(project, element, load)
        else:
            wx, wy, wz = float(load.wx), float(load.wy), float(load.wz)
        acc = loads.setdefault(load.element_tag, [0.0, 0.0, 0.0])
        acc[0] += float(wx)
        acc[1] += float(wy)
        acc[2] += float(wz)

    load_case = project.loads.get(load_tag)
    if (
        load_case is not None
        and callable(is_self_weight_load)
        and is_self_weight_load(load_case)
        and callable(element_self_weight_local_components)
    ):
        for element in project.elements.values():
            wx, wy, wz = element_self_weight_local_components(project, element)
            acc = loads.setdefault(element.tag, [0.0, 0.0, 0.0])
            acc[0] += float(wx)
            acc[1] += float(wy)
            acc[2] += float(wz)

    return {element_tag: tuple(values) for element_tag, values in loads.items()}


def _plane_moment_component(
    values: tuple[float, float, float, float, float, float],
    plane: str,
) -> float:
    """Handle plane moment component."""
    if plane == "XY":
        return float(values[5])
    if plane == "XZ":
        return -float(values[4])
    if plane == "YZ":
        return float(values[3])
    return 0.0


def _opsvis_like_scale(ax) -> float:
    """Handle opsvis like scale."""
    ratio = 0.1
    min_x, max_x = ax.get_xlim()
    min_y, max_y = ax.get_ylim()
    xsfac = ratio * abs(max_x - min_x)
    ysfac = ratio * abs(max_y - min_y)
    sfac = max(xsfac, ysfac)
    return sfac if sfac > 1e-12 else 1.0


def _resolved_unit(symbol: str, quantity: Quantity):
    """Handle resolved unit."""
    unit = find_unit(symbol)
    if unit is None or unit.quantity != quantity:
        return INTERNAL_UNITS[quantity]
    return unit


def _convert_force_display(value: float, display_units: DisplayUnits) -> tuple[float, str]:
    """Convert force display."""
    unit = _resolved_unit(display_units.force, Quantity.FORCE)
    return value / unit.to_internal, unit.symbol


def _convert_moment_display(value: float, display_units: DisplayUnits) -> tuple[float, str]:
    """Convert moment display."""
    unit = _resolved_unit(display_units.moment, Quantity.MOMENT)
    return value / unit.to_internal, unit.symbol


def _convert_line_load_display(
    value: float,
    display_units: DisplayUnits,
) -> tuple[float, str]:
    """Convert line load display."""
    force_unit = _resolved_unit(display_units.force, Quantity.FORCE)
    length_unit = _resolved_unit(display_units.length, Quantity.LENGTH)
    converted = value * length_unit.to_internal / force_unit.to_internal
    return converted, f"{force_unit.symbol}/{length_unit.symbol}"


def _project_element_uniform_load_to_2d(
    coords: np.ndarray,
    values: tuple[float, float, float],
    plane: str,
) -> tuple[float, float]:
    """Project element uniform load to 2D."""
    i1, i2 = _PLANE_INDICES[plane]
    p1 = np.array([coords[0][i1], coords[0][i2]], dtype=float)
    p2 = np.array([coords[1][i1], coords[1][i2]], dtype=float)
    tangent = p2 - p1
    length = float(np.linalg.norm(tangent))
    if length < 1e-12:
        return 0.0, 0.0

    local_x, local_y, local_z = _element_local_axes(coords)
    global_vec = (
        float(values[0]) * local_x
        + float(values[1]) * local_y
        + float(values[2]) * local_z
    )
    projected = np.array([global_vec[i1], global_vec[i2]], dtype=float)
    local_x_2d = tangent / length
    local_y_2d = np.array([-local_x_2d[1], local_x_2d[0]], dtype=float)
    wy = float(np.dot(projected, local_y_2d))
    wx = float(np.dot(projected, local_x_2d))
    return wy, wx


def _draw_nodal_loads_2d(
    ax,
    project: ProjectModel,
    node_tags: list[int],
    plane: str,
    nodal_loads: dict[int, tuple[float, float, float, float, float, float]],
    sfac: float,
    display_units: DisplayUnits,
) -> int:
    """Draw nodal loads 2D."""
    i1, i2 = _PLANE_INDICES[plane]
    count = 0

    for node_tag in node_tags:
        values = nodal_loads.get(node_tag)
        node = project.nodes.get(node_tag)
        if values is None or node is None:
            continue

        coords = (node.x, node.y, node.z)
        point = np.array([coords[i1], coords[i2]], dtype=float)
        force = np.array([values[0], values[1], values[2]], dtype=float)
        projected = force[[i1, i2]]
        moment = _plane_moment_component(values, plane)
        displayed = False

        for kier, value in enumerate(projected):
            if abs(float(value)) <= 1e-12:
                continue
            if kier == 0:
                dx, dy = sfac * np.sign(value), 0.0
            else:
                dx, dy = 0.0, sfac * np.sign(value)

            ax.arrow(
                point[0] - dx,
                point[1] - dy,
                dx,
                dy,
                lw=3,
                head_width=0.1 * sfac,
                head_length=0.2 * sfac,
                fc=_LOAD_NODE_COLOR,
                ec=_LOAD_NODE_COLOR,
                length_includes_head=True,
                shape="full",
                joinstyle="round",
                zorder=6,
            )
            force_value, force_unit = _convert_force_display(
                abs(float(value)),
                display_units,
            )
            ax.text(
                point[0] - dx,
                point[1] - dy,
                f" {force_value:.5g} {force_unit}",
                color=_LOAD_NODE_COLOR,
                zorder=7,
            )
            displayed = True

        if abs(moment) > 1e-12:
            marker_type = r"$\curvearrowleft$" if moment > 0.0 else r"$\curvearrowright$"
            text_align = "right" if moment > 0.0 else "left"
            moment_value, moment_unit = _convert_moment_display(abs(moment), display_units)
            ax.text(
                point[0],
                point[1],
                f"\n  {moment_value:.5g} {moment_unit}",
                color=_LOAD_MOMENT_COLOR,
                va="top",
                ha=text_align,
                zorder=7,
            )
            ax.plot(
                point[0],
                point[1],
                marker=marker_type,
                markersize=30,
                color=_LOAD_MOMENT_COLOR,
                zorder=6,
            )
            displayed = True

        if displayed:
            count += 1

    return count


def _draw_element_loads_2d(
    ax,
    project: ProjectModel,
    ele_tags: list[int],
    plane: str,
    element_loads: dict[int, tuple[float, float, float]],
    sfac: float,
    display_units: DisplayUnits,
    nep: int = 11,
) -> int:
    """Draw element loads 2D."""
    count = 0

    for ele_tag in ele_tags:
        values = element_loads.get(ele_tag)
        element = project.elements.get(ele_tag)
        if values is None or element is None:
            continue

        coords = _element_coords_from_project(project, element)
        if coords is None:
            continue

        i1, i2 = _PLANE_INDICES[plane]
        p1 = np.array([coords[0][i1], coords[0][i2]], dtype=float)
        p2 = np.array([coords[1][i1], coords[1][i2]], dtype=float)
        lxy = p2 - p1
        length = float(np.linalg.norm(lxy))
        if length < 1e-12:
            continue

        wy, wx = _project_element_uniform_load_to_2d(coords, values, plane)
        if abs(wy) <= 1e-12 and abs(wx) <= 1e-12:
            continue

        cosa, cosb = lxy / length
        xl = np.linspace(0.0, length, nep)
        one = np.ones(nep)
        s = sfac * one * np.sign(wy)

        s_0 = np.zeros((nep, 2))
        s_0[0, :] = p1
        s_0[1:, 0] = p1[0] + xl[1:] * cosa
        s_0[1:, 1] = p1[1] + xl[1:] * cosb

        s_p = np.copy(s_0)
        s_p[:, 0] += s * cosb
        s_p[:, 1] -= s * cosa

        for idx in np.arange(nep):
            ax.arrow(
                s_p[idx, 0],
                s_p[idx, 1],
                s_0[idx, 0] - s_p[idx, 0],
                s_0[idx, 1] - s_p[idx, 1],
                lw=1,
                head_width=0.1 * sfac,
                head_length=0.2 * sfac,
                fc=_LOAD_ELEMENT_COLOR,
                ec=_LOAD_ELEMENT_COLOR,
                length_includes_head=True,
                shape="full",
                joinstyle="round",
                zorder=5,
            )

        ax.plot(
            [s_p[0, 0], s_p[-1, 0]],
            [s_p[0, 1], s_p[-1, 1]],
            color=_LOAD_ELEMENT_COLOR,
            lw=1,
            zorder=5,
        )
        wy_value, line_load_unit = _convert_line_load_display(abs(wy), display_units)
        wx_value, _ = _convert_line_load_display(abs(wx), display_units)
        ax.text(
            s_p[int((nep - 1) / 3), 0],
            s_p[int((nep - 1) / 3), 1],
            f"q = {wy_value:.3g}, {wx_value:.3g} {line_load_unit}",
            va="bottom",
            ha="center",
            color=_LOAD_ELEMENT_COLOR,
            zorder=6,
        )

        if abs(wx) > 1e-12:
            dx = s_0[1:, 0] - s_0[:-1, 0]
            dy = s_0[1:, 1] - s_0[:-1, 1]
            if wx < 0.0:
                dx = -dx
                dy = -dy
            ax.quiver(
                s_0[:-1, 0],
                s_0[:-1, 1],
                dx,
                dy,
                scale_units="xy",
                angles="xy",
                scale=0.8,
                color=_LOAD_ELEMENT_AXIAL_COLOR,
                zorder=5,
            )

        count += 1

    return count


def _draw_2d_diagram(
    component: str,
    ele_tags: list[int],
    plane: str,
    ax,
    sfac: float,
    file_center: np.ndarray,
    file_tol: float,
    file_boundary_sign: float,
    label_offset: float,
    nep: int = 17,
) -> tuple[float, float]:
    """Draw the 2D diagram and return the component range."""
    min_val, max_val = np.inf, -np.inf
    placed_label_positions: list[np.ndarray] = []

    for et in ele_tags:
        res = _element_samples(et, component, nep, plane=plane)
        if res is None:
            continue
        ecrd_3d, xl, ss, _ = res
        drawn_range = _draw_sampled_diagram_element(
            ax,
            component,
            plane,
            ecrd_3d,
            xl,
            ss,
            sfac,
            file_center,
            file_tol,
            file_boundary_sign,
            placed_label_positions,
            label_offset,
            apply_component_axis_sign=False,
        )
        if drawn_range is None:
            continue
        element_min, element_max = drawn_range
        min_val = min(min_val, element_min)
        max_val = max(max_val, element_max)

    if not np.isfinite(min_val):
        return 0.0, 0.0
    return min_val, max_val


def _draw_2d_diagram_from_results(
    component: str,
    project: ProjectModel,
    results: dict,
    element_loads: dict[int, tuple[float, float, float]],
    ele_tags: list[int],
    plane: str,
    ax,
    sfac: float,
    file_center: np.ndarray,
    file_tol: float,
    file_boundary_sign: float,
    label_offset: float,
    nep: int = 17,
) -> tuple[float, float]:
    """Draw 2D diagram from results."""
    min_val, max_val = np.inf, -np.inf
    placed_label_positions: list[np.ndarray] = []

    for ele_tag in ele_tags:
        res = _element_samples_from_results(
            project,
            results,
            element_loads,
            ele_tag,
            component,
            nep,
            plane=plane,
        )
        if res is None:
            continue
        ecrd_3d, xl, ss, _ = res
        drawn_range = _draw_sampled_diagram_element(
            ax,
            component,
            plane,
            ecrd_3d,
            xl,
            ss,
            sfac,
            file_center,
            file_tol,
            file_boundary_sign,
            placed_label_positions,
            label_offset,
        )
        if drawn_range is None:
            continue
        element_min, element_max = drawn_range
        min_val = min(min_val, element_min)
        max_val = max(max_val, element_max)

    if not np.isfinite(min_val):
        return 0.0, 0.0
    return min_val, max_val


def _draw_2d_diagram_from_backend(
    component: str,
    project: ProjectModel,
    backend,
    ele_tags: list[int],
    plane: str,
    ax,
    sfac: float,
    file_center: np.ndarray,
    file_tol: float,
    file_boundary_sign: float,
    label_offset: float,
    nep: int = 17,
) -> tuple[float, float]:
    """Draw 2D diagram from backend."""
    min_val, max_val = np.inf, -np.inf
    placed_label_positions: list[np.ndarray] = []

    for ele_tag in ele_tags:
        res = _element_samples_from_backend(
            project,
            backend,
            ele_tag,
            component,
            nep,
            plane=plane,
        )
        if res is None:
            continue
        ecrd_3d, xl, ss, _ = res
        drawn_range = _draw_sampled_diagram_element(
            ax,
            component,
            plane,
            ecrd_3d,
            xl,
            ss,
            sfac,
            file_center,
            file_tol,
            file_boundary_sign,
            placed_label_positions,
            label_offset,
            apply_component_axis_sign=False,
        )
        if drawn_range is None:
            continue
        element_min, element_max = drawn_range
        min_val = min(min_val, element_min)
        max_val = max(max_val, element_max)

    if not np.isfinite(min_val):
        return 0.0, 0.0
    return min_val, max_val


def _single_local_element_sample(
    component: str,
    ele_tag: int,
    *,
    project: ProjectModel | None,
    backend,
    results: dict | None,
    element_loads: dict[int, tuple[float, float, float]],
    nep: int = 17,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[float, float, float]] | None:
    """Handle single local element sample."""
    if (
        project is not None
        and backend is not None
        and getattr(backend, "sample_diagram_component", None) is not None
    ):
        return _element_samples_from_backend(
            project,
            backend,
            ele_tag,
            component,
            nep,
        )
    if project is not None and results is not None:
        return _element_samples_from_results(
            project,
            results,
            element_loads,
            ele_tag,
            component,
            nep,
        )
    return _element_samples(ele_tag, component, nep)


def _component_unit_label(component: str) -> str:
    """Handle component unit label."""
    if component in {"N", "Vy", "Vz"}:
        return "kN"
    if component in {"T", "My", "Mz"}:
        return "kN.m"
    return ""


def _diagram_component_title(component: str, plane: str | None) -> str:
    """Handle diagram component title."""
    if component == "My" and plane == "YZ":
        return QCoreApplication.translate(
            "DiagramRenderer",
            "Moment de flexion dans le plan (kN.m)",
        )
    labels = {
        "N": QCoreApplication.translate("DiagramRenderer", "Effort normal N (kN)"),
        "Vy": QCoreApplication.translate("DiagramRenderer", "Effort tranchant Vy (kN)"),
        "Vz": QCoreApplication.translate("DiagramRenderer", "Effort tranchant Vz (kN)"),
        "T": QCoreApplication.translate("DiagramRenderer", "Moment de torsion T (kN.m)"),
        "My": QCoreApplication.translate("DiagramRenderer", "Moment de flexion My (kN.m)"),
        "Mz": QCoreApplication.translate("DiagramRenderer", "Moment de flexion Mz (kN.m)"),
    }
    return labels.get(component, component)


def _component_local_plane_label(component: str) -> str:
    """Handle component local plane label."""
    if component in {"Vz", "My"}:
        return QCoreApplication.translate("DiagramRenderer", "plan local x-z")
    if component in {"Vy", "Mz"}:
        return QCoreApplication.translate("DiagramRenderer", "plan local x-y")
    return QCoreApplication.translate("DiagramRenderer", "repère local")


def _plot_local_member_axis(
    ax,
    length: float,
    project: ProjectModel | None,
    ele_tag: int,
) -> None:
    """Plot local member axis."""
    ax.plot([0.0, length], [0.0, 0.0], color="black", linewidth=1.8, zorder=3)
    ax.scatter([0.0, length], [0.0, 0.0], s=26, c="black", zorder=4)

    i_label = "i"
    j_label = "j"
    if project is not None:
        element = project.elements.get(ele_tag)
        if element is not None:
            i_label = f"i : N{element.node_i}"
            j_label = f"j : N{element.node_j}"
    offset = max(length * 0.018, 0.06)
    ax.text(0.0, -offset, i_label, ha="center", va="top", fontsize=8, zorder=5)
    ax.text(length, -offset, j_label, ha="center", va="top", fontsize=8, zorder=5)


def _build_single_element_local_figure(
    component: str,
    file_info: dict,
    project: ProjectModel | None = None,
    backend=None,
    results: dict | None = None,
    load_tag: int | None = None,
    combo_tag: int | None = None,
    sfac: float = 0.0,
) -> Figure:
    """Build single element local figure."""
    ele_tags: list[int] = list(file_info.get("ele_tags") or [])
    if not ele_tags and file_info.get("element_tag") is not None:
        ele_tags = [int(file_info["element_tag"])]

    if len(ele_tags) != 1:
        fig = Figure(figsize=(10, 7))
        ax = fig.add_subplot(111)
        ax.text(
            0.5,
            0.5,
            QCoreApplication.translate(
                "DiagramRenderer",
                "Sélectionnez une seule barre pour le diagramme local.",
            ),
            ha="center",
            va="center",
            fontsize=11,
        )
        ax.axis("off")
        return fig

    ele_tag = int(ele_tags[0])
    element_loads = (
        _case_distributed_loads(project, load_tag=load_tag, combo_tag=combo_tag)
        if project is not None and results is not None
        else {}
    )
    sample = _single_local_element_sample(
        component,
        ele_tag,
        project=project,
        backend=backend,
        results=results,
        element_loads=element_loads,
    )
    if sample is None:
        fig = Figure(figsize=(10, 7))
        ax = fig.add_subplot(111)
        ax.text(
            0.5,
            0.5,
            QCoreApplication.translate(
                "DiagramRenderer",
                "Aucun résultat de barre disponible pour ce diagramme.",
            ),
            ha="center",
            va="center",
            fontsize=11,
        )
        ax.axis("off")
        return fig

    ecrd_3d, xl, ss, _ = sample
    length = float(np.linalg.norm(ecrd_3d[1] - ecrd_3d[0]))
    if length < 1e-12:
        length = float(np.max(xl) - np.min(xl)) if xl.size else 1.0
    length = max(length, 1.0)

    max_abs = float(np.max(np.abs(ss))) if ss.size else 0.0
    if sfac <= 0:
        sfac = (_AUTO_DIAGRAM_SCALE_RATIO * length / max_abs) if max_abs > 1e-12 else 1.0
    label_offset = max(length * 0.025, 0.08)

    fig = Figure(figsize=(11, 7))
    ax = fig.add_subplot(111)
    _plot_local_member_axis(ax, length, project, ele_tag)
    _draw_sampled_local_diagram_element(
        ax,
        component,
        xl,
        ss,
        sfac,
        [],
        label_offset,
    )

    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.set_xlabel(QCoreApplication.translate("DiagramRenderer", "x local (m)"))
    unit = _component_unit_label(component)
    unit_suffix = f" ({unit})" if unit else ""
    ax.set_ylabel(f"{component} local{unit_suffix}")

    title = _diagram_component_title(component, None)
    label = file_info.get("label") or f"E{ele_tag}"
    ax.set_title(
        QCoreApplication.translate(
            "DiagramRenderer",
            "{title} - {label} - {plane}",
        ).format(
            title=title,
            label=label,
            plane=_component_local_plane_label(component),
        ),
        fontsize=12,
    )
    ax.margins(0.08, 0.2)
    fig.tight_layout()
    return fig


def build_figure_2d(
    component: str,
    file_info: dict | None,
    project: ProjectModel | None = None,
    backend=None,
    results: dict | None = None,
    load_tag: int | None = None,
    combo_tag: int | None = None,
    sfac: float = 0.0,
) -> Figure:
    """Build figure 2D."""
    if file_info is None:
        files = detect_files(project=project)
        if not files:
            fig = Figure(figsize=(10, 7))
            fig.add_subplot(111).text(
                0.5,
                0.5,
                QCoreApplication.translate("DiagramRenderer", "Aucun élément à afficher."),
                ha="center", va="center",
        )
            return fig
        file_info = files[0]

    if file_info.get("local_element"):
        return _build_single_element_local_figure(
            component,
            file_info,
            project=project,
            backend=backend,
            results=results,
            load_tag=load_tag,
            combo_tag=combo_tag,
            sfac=sfac,
        )

    def _file_boundary_sign() -> float:
        axis_idx = file_info.get("axis")
        value = file_info.get("value")
        if axis_idx is None or value is None:
            return 1.0

        axis_values: list[float] = []
        if project is not None:
            axis_values = [float((node.x, node.y, node.z)[axis_idx]) for node in project.nodes.values()]
        else:
            try:
                axis_values = [
                    float(ops.nodeCoord(tag)[axis_idx])
                    for tag in ops.getNodeTags()
                ]
            except Exception:
                axis_values = []
        if not axis_values:
            return 1.0

        min_value = min(axis_values)
        max_value = max(axis_values)
        tol = max(1e-6, abs(max_value - min_value) * 1e-6)
        if abs(float(value) - min_value) <= tol:
            return -1.0
        if abs(float(value) - max_value) <= tol:
            return 1.0
        return 1.0

    plane = file_info.get("plane")
    ele_tags: list[int] = file_info.get("ele_tags") or []
    file_boundary_sign = _file_boundary_sign()

    # True 3D: no 2D view is possible, so return a message.
    if plane is None:
        fig = Figure(figsize=(10, 7))
        ax = fig.add_subplot(111)
        ax.text(
            0.5, 0.5,
            QCoreApplication.translate(
                "DiagramRenderer",
                "Structure non planaire — sélectionnez une file pour afficher\n"
                "un diagramme 2D.",
            ),
            ha="center", va="center", fontsize=11,
        )
        ax.axis("off")
        return fig

    # Scale calculation
    use_backend_sampling = (
        project is not None
        and backend is not None
        and getattr(backend, "sample_diagram_component", None) is not None
    )
    use_project_results = (
        project is not None and results is not None and not use_backend_sampling
    )
    element_loads = (
        _case_distributed_loads(project, load_tag=load_tag, combo_tag=combo_tag)
        if use_project_results else {}
    )
    if use_backend_sampling:
        min_val, max_val = _compute_component_range_from_backend(
            component,
            project,
            backend,
            ele_tags,
            plane=plane,
        )
    elif use_project_results:
        min_val, max_val = _compute_component_range_from_results(
            component,
            project,
            results,
            ele_tags,
            element_loads,
            plane=plane,
        )
    else:
        min_val, max_val = _compute_component_range(
            component,
            ele_tags,
            plane=plane,
        )
    max_abs = max(abs(min_val), abs(max_val))

    # Diagonale du plan 2D
    i1, i2 = _PLANE_INDICES[plane]
    pts_2d = []
    for et in ele_tags:
        if project is not None:
            element = project.elements.get(et)
            if element is None:
                continue
            for nt in (element.node_i, element.node_j):
                node = project.nodes.get(nt)
                if node is None:
                    continue
                coords = (node.x, node.y, node.z)
                pts_2d.append((coords[i1], coords[i2]))
        else:
            en = ops.eleNodes(et)
            if len(en) != 2:
                continue
            for nt in en:
                c = ops.nodeCoord(nt)
                pts_2d.append((c[i1], c[i2]))
    if pts_2d:
        arr = np.array(pts_2d)
        span_2d = arr.max(axis=0) - arr.min(axis=0)
        diag_2d = float(np.linalg.norm(span_2d))
        file_center = arr.mean(axis=0)
    else:
        diag_2d = 1.0
        file_center = np.array([0.0, 0.0])
    file_tol = max(1e-6, diag_2d * 1e-4)
    label_offset = max(diag_2d * 0.025, 0.08)

    if sfac <= 0:
        if max_abs > 1e-12 and diag_2d > 0:
            sfac = _AUTO_DIAGRAM_SCALE_RATIO * diag_2d / max_abs
        else:
            sfac = 1.0

    fig = Figure(figsize=(11, 7))
    ax = fig.add_subplot(111)

    _plot_model_2d(ax, ele_tags, plane, project=project)
    if use_backend_sampling:
        _draw_2d_diagram_from_backend(
            component,
            project,
            backend,
            ele_tags,
            plane,
            ax,
            sfac,
            file_center,
            file_tol,
            file_boundary_sign,
            label_offset,
        )
    elif use_project_results:
        _draw_2d_diagram_from_results(
            component,
            project,
            results,
            element_loads,
            ele_tags,
            plane,
            ax,
            sfac,
            file_center,
            file_tol,
            file_boundary_sign,
            label_offset,
        )
    else:
        _draw_2d_diagram(
            component,
            ele_tags,
            plane,
            ax,
            sfac,
            file_center,
            file_tol,
            file_boundary_sign,
            label_offset,
        )
    _plot_supports_2d(
        ax, project, ele_tags, plane, max(diag_2d * 0.03, 0.08),
    )

    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.set_xlabel(f"{plane[0]} (m)")
    ax.set_ylabel(f"{plane[1]} (m)")

    title = _diagram_component_title(component, plane)
    label = file_info.get("label", "")
    if label:
        title = QCoreApplication.translate(
            "DiagramRenderer",
            "{title} — {label}",
        ).format(title=title, label=label)
    ax.set_title(title, fontsize=12)

    # Small padding around the data to leave room for labels
    ax.margins(0.1, 0.15)

    fig.tight_layout()
    return fig


def build_load_figure_2d(
    file_info: dict | None,
    project: ProjectModel,
    load_tag: int | None,
    display_units: DisplayUnits | None = None,
) -> Figure:
    """Build load figure 2D."""
    display_units = display_units or DisplayUnits()
    if load_tag is None:
        available_tags = sorted(project.loads.keys())
        load_tag = available_tags[0] if available_tags else None

    if load_tag is None:
        fig = Figure(figsize=(10, 7))
        ax = fig.add_subplot(111)
        ax.text(
            0.5,
            0.5,
            QCoreApplication.translate(
                "DiagramRenderer",
                "Aucun cas de charge n'est disponible.",
            ),
            ha="center",
            va="center",
            fontsize=11,
        )
        ax.axis("off")
        return fig

    if file_info is None:
        files = detect_load_files(project)
        if not files:
            fig = Figure(figsize=(10, 7))
            ax = fig.add_subplot(111)
            ax.text(
                0.5,
                0.5,
                QCoreApplication.translate(
                    "DiagramRenderer",
                    "Aucune vue de charge compatible n'est disponible.",
                ),
                ha="center",
                va="center",
                fontsize=11,
            )
            ax.axis("off")
            return fig
        file_info = files[0]

    plane = file_info.get("plane")
    ele_tags: list[int] = list(file_info.get("ele_tags") or [])
    node_tags: list[int] = list(file_info.get("node_tags") or [])
    if plane is None:
        fig = Figure(figsize=(10, 7))
        ax = fig.add_subplot(111)
        ax.text(
            0.5,
            0.5,
            QCoreApplication.translate(
                "DiagramRenderer",
                "Sélectionnez une file ou un plan pour afficher les charges.",
            ),
            ha="center",
            va="center",
            fontsize=11,
        )
        ax.axis("off")
        return fig

    fig = Figure(figsize=(11, 7))
    ax = fig.add_subplot(111)
    _plot_model_2d(ax, ele_tags, plane, project=project)
    _plot_nodes_2d(ax, project, node_tags, plane)
    sfac = _opsvis_like_scale(ax)

    nodal_loads = _aggregate_case_nodal_loads(project, load_tag)
    element_loads = _aggregate_case_element_loads(project, load_tag)
    nodal_count = _draw_nodal_loads_2d(
        ax,
        project,
        node_tags,
        plane,
        nodal_loads,
        sfac,
        display_units,
    )
    element_count = _draw_element_loads_2d(
        ax,
        project,
        ele_tags,
        plane,
        element_loads,
        sfac,
        display_units,
    )
    _plot_supports_2d(
        ax,
        project,
        ele_tags,
        plane,
        max(sfac * 0.3, 0.08),
        node_tags=node_tags,
    )

    if nodal_count == 0 and element_count == 0:
        ax.text(
            0.5,
            0.5,
            QCoreApplication.translate(
                "DiagramRenderer",
                "Aucune charge affectée dans cette vue.",
            ),
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=10,
            bbox={
                "boxstyle": "round,pad=0.35",
                "facecolor": "white",
                "edgecolor": "#9aa6ac",
                "alpha": 0.9,
            },
        )

    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(False)
    ax.set_xlabel(f"{plane[0]} (m)")
    ax.set_ylabel(f"{plane[1]} (m)")

    load_case = project.loads.get(load_tag)
    title = QCoreApplication.translate("DiagramRenderer", "Charges affectées")
    if load_case is not None:
        title = QCoreApplication.translate(
            "DiagramRenderer",
            "{title} - {load}",
        ).format(
            title=title,
            load=tagged_load_label(load_case, load_tag),
        )
    label = file_info.get("label", "")
    if label:
        title = QCoreApplication.translate(
            "DiagramRenderer",
            "{title} - {label}",
        ).format(title=title, label=label)
    ax.set_title(title, fontsize=12)
    ax.margins(0.12, 0.18)
    fig.tight_layout()
    return fig
