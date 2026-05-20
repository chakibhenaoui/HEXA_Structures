"""Rendu 2D opsvis-like des résultats de plaques/shells."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from core.model_data import ProjectModel


_PLANE_INDICES: dict[str, tuple[int, int]] = {
    "XY": (0, 1),
    "XZ": (0, 2),
    "YZ": (1, 2),
}
_PLANE_WHEN_AXIS_CONST = {0: "YZ", 1: "XZ", 2: "XY"}
_AXIS_NAMES = ("X", "Y", "Z")
_LOCAL_PLANE = "LOCAL"

_SURFACE_COMPONENT_SPECS: dict[str, dict[str, object]] = {
    "Nxx": {"index": 0, "title": "Effort membranaire Nxx (kN/m)"},
    "Nyy": {"index": 1, "title": "Effort membranaire Nyy (kN/m)"},
    "Nxy": {"index": 2, "title": "Effort membranaire Nxy (kN/m)"},
    "Mxx": {"index": 3, "title": "Moment plaque Mxx (kN.m/m)"},
    "Myy": {"index": 4, "title": "Moment plaque Myy (kN.m/m)"},
    "Mxy": {"index": 5, "title": "Moment plaque Mxy (kN.m/m)"},
    "Qx": {"index": 6, "title": "Effort tranchant Qx (kN/m)"},
    "Qy": {"index": 7, "title": "Effort tranchant Qy (kN/m)"},
}

SURFACE_RESULT_COMPONENTS: tuple[str, ...] = tuple(_SURFACE_COMPONENT_SPECS)


def _project_node(project: ProjectModel, node_tag: int, plane: str) -> tuple[float, float]:
    node = project.nodes[node_tag]
    coords = (float(node.x), float(node.y), float(node.z))
    i1, i2 = _PLANE_INDICES[plane]
    return coords[i1], coords[i2]


def _normalize(vector: np.ndarray) -> np.ndarray | None:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        return None
    return np.asarray(vector, dtype=float) / norm


def _local_surface_basis(
    coords: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Construit un repere local robuste, meme pour un quad legerement gauchi."""
    if coords.shape[0] < 3:
        return None

    origin = np.asarray(coords[0], dtype=float)
    center = coords.mean(axis=0)
    centered = coords - center
    try:
        _u, _s, vh = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    normal = _normalize(vh[-1])
    if normal is None:
        return None

    u_axis = None
    for point in coords[1:]:
        candidate = np.asarray(point, dtype=float) - origin
        candidate = candidate - np.dot(candidate, normal) * normal
        u_axis = _normalize(candidate)
        if u_axis is not None:
            break
    if u_axis is None:
        u_axis = _normalize(vh[0])
    if u_axis is None:
        return None

    v_axis = _normalize(np.cross(normal, u_axis))
    if v_axis is None:
        return None
    return origin, u_axis, v_axis


def _project_node_local(
    project: ProjectModel,
    node_tag: int,
    file_info: dict,
) -> tuple[float, float]:
    node = project.nodes[node_tag]
    point = np.array([node.x, node.y, node.z], dtype=float)
    origin = np.asarray(file_info["origin"], dtype=float)
    u_axis = np.asarray(file_info["u_axis"], dtype=float)
    v_axis = np.asarray(file_info["v_axis"], dtype=float)
    relative = point - origin
    return float(np.dot(relative, u_axis)), float(np.dot(relative, v_axis))


def _surface_plane(
    project: ProjectModel,
    surface,
    tol: float,
) -> tuple[str | None, int | None, float | None]:
    coords = np.array(
        [
            [project.nodes[tag].x, project.nodes[tag].y, project.nodes[tag].z]
            for tag in surface.node_tags
            if tag in project.nodes
        ],
        dtype=float,
    )
    if coords.shape[0] != len(surface.node_tags):
        return None, None, None

    for axis_idx in range(3):
        values = coords[:, axis_idx]
        if float(values.max() - values.min()) <= tol:
            plane = _PLANE_WHEN_AXIS_CONST[axis_idx]
            value = float(values.mean())
            return plane, axis_idx, value
    return None, None, None


def _generated_plate_surface_tags(project: ProjectModel) -> set[int]:
    meshes = getattr(project, "generated_plate_meshes", {}) or {}
    tags: set[int] = set()
    for mesh in meshes.values():
        tags.update(int(tag) for tag in getattr(mesh, "surface_tags", []) or [])
    return tags


def _plate_region_local_basis(project: ProjectModel, plate) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    coords = np.array(
        [
            [project.nodes[tag].x, project.nodes[tag].y, project.nodes[tag].z]
            for tag in plate.corner_node_tags
            if tag in project.nodes
        ],
        dtype=float,
    )
    if coords.shape[0] != 4:
        return None

    origin = coords[0]
    u_axis = _normalize(coords[1] - origin)
    if u_axis is not None:
        v_candidate = coords[3] - origin
        v_candidate = v_candidate - float(np.dot(v_candidate, u_axis)) * u_axis
        v_axis = _normalize(v_candidate)
        if v_axis is not None:
            return origin, u_axis, v_axis

    return _local_surface_basis(coords)


def detect_plate_result_files(project: ProjectModel) -> list[dict]:
    """Liste les vues de resultats correspondant aux plaques macro maillees."""
    meshes = getattr(project, "generated_plate_meshes", {}) or {}
    if not meshes:
        return []

    files: list[dict] = []
    for plate_tag, mesh in sorted(meshes.items()):
        plate = project.plate_regions.get(int(plate_tag))
        if plate is None:
            continue
        surface_tags = [
            int(tag)
            for tag in getattr(mesh, "surface_tags", []) or []
            if int(tag) in project.surface_elements
        ]
        if not surface_tags:
            continue
        basis = _plate_region_local_basis(project, plate)
        if basis is None:
            continue
        origin, u_axis, v_axis = basis
        name = str(getattr(plate, "name", "") or "").strip()
        label_name = f" - {name}" if name else ""
        files.append(
            {
                "label": (
                    f"Plaque P{int(plate_tag)}{label_name} "
                    f"({int(getattr(mesh, 'mesh_nx', plate.mesh_nx))}"
                    f"x{int(getattr(mesh, 'mesh_ny', plate.mesh_ny))}, "
                    f"{len(surface_tags)} surf.)"
                ),
                "plane": _LOCAL_PLANE,
                "local_surface": True,
                "generated_plate": True,
                "plate_tag": int(plate_tag),
                "surface_tags": surface_tags,
                "origin": tuple(float(value) for value in origin),
                "u_axis": tuple(float(value) for value in u_axis),
                "v_axis": tuple(float(value) for value in v_axis),
            }
        )
    return files


def detect_surface_result_files(
    project: ProjectModel,
    exclude_surface_tags: set[int] | None = None,
) -> list[dict]:
    """Liste les plans coplanaires disponibles pour les cartes de plaques."""
    if not project.nodes or not project.surface_elements:
        return []
    excluded = set(exclude_surface_tags or set())

    all_coords = np.array(
        [[node.x, node.y, node.z] for node in project.nodes.values()],
        dtype=float,
    )
    span = all_coords.max(axis=0) - all_coords.min(axis=0)
    diag = float(np.linalg.norm(span))
    tol = max(1e-6, diag * 1e-4)

    grouped: dict[tuple[str, int, float], list[int]] = {}
    for surface in project.surface_elements.values():
        if int(surface.tag) in excluded:
            continue
        plane, axis_idx, value = _surface_plane(project, surface, tol)
        if plane is None or axis_idx is None or value is None:
            continue
        rounded_value = round(value / tol) * tol
        grouped.setdefault((plane, axis_idx, rounded_value), []).append(surface.tag)

    files: list[dict] = []
    for (plane, axis_idx, value), surface_tags in sorted(
        grouped.items(),
        key=lambda item: (item[0][1], item[0][2]),
    ):
        axis_name = _AXIS_NAMES[axis_idx]
        files.append(
            {
                "label": f"Plan {axis_name} = {value:.3g} m ({len(surface_tags)} surf.)",
                "plane": plane,
                "axis": axis_idx,
                "value": float(value),
                "surface_tags": sorted(surface_tags),
            }
        )

    return files


def detect_surface_result_views(project: ProjectModel) -> list[dict]:
    """Retourne les vues de cartes plaques, macros en premier puis surfaces directes."""
    plate_files = detect_plate_result_files(project)
    excluded = _generated_plate_surface_tags(project) if plate_files else set()
    return plate_files + detect_surface_result_files(
        project,
        exclude_surface_tags=excluded,
    )


def surface_result_file_for_surface(
    project: ProjectModel,
    surface_tag: int,
) -> dict | None:
    """Construit une vue locale pour une plaque precise, meme hors plans globaux."""
    surface = project.surface_elements.get(int(surface_tag))
    if surface is None:
        return None
    coords = np.array(
        [
            [project.nodes[tag].x, project.nodes[tag].y, project.nodes[tag].z]
            for tag in surface.node_tags
            if tag in project.nodes
        ],
        dtype=float,
    )
    if coords.shape[0] != len(surface.node_tags):
        return None
    basis = _local_surface_basis(coords)
    if basis is None:
        return None
    origin, u_axis, v_axis = basis
    return {
        "label": f"Plaque S{int(surface_tag)} (repere local)",
        "plane": _LOCAL_PLANE,
        "local_surface": True,
        "surface_tags": [int(surface_tag)],
        "origin": tuple(float(value) for value in origin),
        "u_axis": tuple(float(value) for value in u_axis),
        "v_axis": tuple(float(value) for value in v_axis),
    }


def _surface_results_for_file(results: dict, file_info: dict) -> dict:
    surface_results = results.get("surface_results", {}) if results else {}
    if surface_results or not file_info.get("generated_plate"):
        return surface_results

    internal_results = results.get("internal_results", {}) if results else {}
    internal_surface_results = internal_results.get("surface_results", {})
    if internal_surface_results:
        return internal_surface_results

    raw_results = internal_results.get("raw_results", {})
    return raw_results.get("surface_results", {}) if raw_results else {}


def _extrapolate_ip_to_node_quad(values_at_ip: np.ndarray) -> np.ndarray:
    """Extrapole 4 valeurs aux points de Gauss vers les 4 nœuds d'un quad."""
    xep = 0.8660254037844386
    weights = np.array(
        [
            [1.0 + xep, -0.5, 1.0 - xep, -0.5],
            [-0.5, 1.0 + xep, -0.5, 1.0 - xep],
            [1.0 - xep, -0.5, 1.0 + xep, -0.5],
            [-0.5, 1.0 - xep, -0.5, 1.0 + xep],
        ],
        dtype=float,
    )
    return weights @ np.asarray(values_at_ip, dtype=float)


def build_surface_component_field(
    project: ProjectModel,
    results: dict,
    file_info: dict,
    component: str,
) -> dict[str, object] | None:
    """Construit un champ nodal moyen pour une composante plaque."""
    spec = _SURFACE_COMPONENT_SPECS.get(component)
    plane = file_info.get("plane")
    surface_tags = list(file_info.get("surface_tags") or [])
    is_local_surface = bool(file_info.get("local_surface")) and plane == _LOCAL_PLANE
    if (
        spec is None
        or (plane not in _PLANE_INDICES and not is_local_surface)
        or not surface_tags
    ):
        return None

    surface_results = _surface_results_for_file(results, file_info)
    effective_surfaces = [
        project.surface_elements[tag]
        for tag in surface_tags
        if tag in project.surface_elements
        and tag in surface_results
        and len(project.surface_elements[tag].node_tags) == 4
    ]
    if not effective_surfaces:
        return None

    node_tags = sorted({tag for surface in effective_surfaces for tag in surface.node_tags})
    node_index = {tag: idx for idx, tag in enumerate(node_tags)}

    coords_2d = np.array(
        [
            _project_node_local(project, node_tag, file_info)
            if is_local_surface
            else _project_node(project, node_tag, plane)
            for node_tag in node_tags
        ],
        dtype=float,
    )
    values = np.zeros(len(node_tags), dtype=float)
    counts = np.zeros(len(node_tags), dtype=int)
    quads = np.zeros((len(effective_surfaces), 4), dtype=int)

    component_idx = int(spec["index"])
    for row, surface in enumerate(effective_surfaces):
        quads[row] = [node_index[tag] for tag in surface.node_tags]
        gauss = np.asarray(
            [
                point[component_idx]
                for point in surface_results[surface.tag].gauss_resultants[:4]
            ],
            dtype=float,
        )
        if gauss.size != 4:
            continue
        nodal_values = _extrapolate_ip_to_node_quad(gauss)
        for local_idx, node_tag in enumerate(surface.node_tags):
            global_idx = node_index[node_tag]
            values[global_idx] += float(nodal_values[local_idx])
            counts[global_idx] += 1

    valid = counts > 0
    if not np.any(valid):
        return None
    values[valid] = values[valid] / counts[valid]

    return {
        "plane": plane,
        "coords_2d": coords_2d,
        "values": values,
        "quads": quads,
        "node_tags": node_tags,
    }


def _quads_to_4tris(
    quads_conn: np.ndarray,
    nds_crd: np.ndarray,
    nds_val: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Subdivise chaque quadrangle en 4 triangles, style opsvis."""
    n_quads, _ = quads_conn.shape
    n_nodes, _ = nds_crd.shape

    nds_c_crd = np.zeros((n_quads, 2), dtype=float)
    nds_c_val = np.zeros(n_quads, dtype=float)
    tris_conn = np.zeros((4 * n_quads, 3), dtype=int)

    for idx, quad_conn in enumerate(quads_conn):
        base = 4 * idx
        n0, n1, n2, n3 = quad_conn
        nds_c_crd[idx] = np.mean(nds_crd[[n0, n1, n2, n3]], axis=0)
        nds_c_val[idx] = float(np.mean(nds_val[[n0, n1, n2, n3]]))
        center_idx = n_nodes + idx
        tris_conn[base + 0] = np.array([n0, n1, center_idx], dtype=int)
        tris_conn[base + 1] = np.array([n1, n2, center_idx], dtype=int)
        tris_conn[base + 2] = np.array([n2, n3, center_idx], dtype=int)
        tris_conn[base + 3] = np.array([n3, n0, center_idx], dtype=int)

    return tris_conn, nds_c_crd, nds_c_val


def _bilinear_quad_point(
    coords: np.ndarray,
    values: np.ndarray,
    s: float,
    t: float,
) -> tuple[np.ndarray, float]:
    """Interpole un point et une valeur dans un quadrangle."""
    weights = np.array(
        [
            (1.0 - s) * (1.0 - t),
            s * (1.0 - t),
            s * t,
            (1.0 - s) * t,
        ],
        dtype=float,
    )
    return weights @ coords, float(weights @ values)


def _refined_quads_to_tris(
    quads_conn: np.ndarray,
    nds_crd: np.ndarray,
    nds_val: np.ndarray,
    subdivisions: int = 8,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Raffine les quads pour obtenir des iso-valeurs plus continues."""
    subdivisions = max(1, int(subdivisions))
    point_index: dict[tuple[float, float], int] = {}
    point_coords: list[np.ndarray] = []
    value_sums: list[float] = []
    value_counts: list[int] = []
    tris: list[tuple[int, int, int]] = []

    def add_point(coord: np.ndarray, value: float) -> int:
        key = (round(float(coord[0]), 12), round(float(coord[1]), 12))
        idx = point_index.get(key)
        if idx is None:
            idx = len(point_coords)
            point_index[key] = idx
            point_coords.append(np.asarray(coord, dtype=float))
            value_sums.append(float(value))
            value_counts.append(1)
            return idx
        value_sums[idx] += float(value)
        value_counts[idx] += 1
        return idx

    for quad in quads_conn:
        quad_coords = nds_crd[quad]
        quad_values = nds_val[quad]
        local_indices = np.zeros((subdivisions + 1, subdivisions + 1), dtype=int)
        for i in range(subdivisions + 1):
            s = i / subdivisions
            for j in range(subdivisions + 1):
                t = j / subdivisions
                coord, value = _bilinear_quad_point(quad_coords, quad_values, s, t)
                local_indices[i, j] = add_point(coord, value)

        for i in range(subdivisions):
            for j in range(subdivisions):
                n00 = int(local_indices[i, j])
                n10 = int(local_indices[i + 1, j])
                n11 = int(local_indices[i + 1, j + 1])
                n01 = int(local_indices[i, j + 1])
                tris.append((n00, n10, n11))
                tris.append((n00, n11, n01))

    coords = np.vstack(point_coords) if point_coords else np.empty((0, 2))
    values = np.array(
        [
            value_sums[idx] / max(value_counts[idx], 1)
            for idx in range(len(value_sums))
        ],
        dtype=float,
    )
    return np.asarray(tris, dtype=int), coords, values


def _surface_contour_levels(values: np.ndarray, count: int = 15) -> np.ndarray:
    """Construit des niveaux d'iso-valeurs stables."""
    finite = np.asarray(values[np.isfinite(values)], dtype=float)
    if finite.size == 0:
        return np.array([], dtype=float)
    min_value = float(np.min(finite))
    max_value = float(np.max(finite))
    if abs(max_value - min_value) <= max(1e-12, abs(max_value) * 1e-9):
        return np.array([min_value], dtype=float)
    return np.linspace(min_value, max_value, max(2, int(count)))


def _plot_mesh_outline(ax, nds_crd: np.ndarray, quads_conn: np.ndarray) -> None:
    """Trace le contour du maillage d'origine sans le trianguler visuellement."""
    for quad in quads_conn:
        poly = nds_crd[np.r_[quad, quad[0]]]
        ax.plot(
            poly[:, 0],
            poly[:, 1],
            color="#2f3e46",
            linewidth=0.8,
            alpha=0.7,
        )


def build_surface_result_figure(
    component: str,
    file_info: dict | None,
    project: ProjectModel,
    results: dict,
):
    """Construit une figure matplotlib de contours pour une composante plaque."""
    if file_info is None:
        files = detect_surface_result_views(project)
        if not files:
            file_info = None
        else:
            file_info = files[0]

    try:
        from matplotlib.figure import Figure
        import matplotlib.tri as mtri
    except ImportError as exc:  # pragma: no cover - depend de l'environnement
        raise ImportError(
            "matplotlib n'est pas installé. Les cartes de résultats plaques ne sont pas disponibles."
        ) from exc

    fig = Figure(figsize=(11, 7))
    ax = fig.add_subplot(111)

    if file_info is None:
        ax.text(
            0.5,
            0.5,
            "Aucune plaque coplanaire compatible n'est disponible.",
            ha="center",
            va="center",
            fontsize=11,
        )
        ax.axis("off")
        return fig

    field = build_surface_component_field(project, results, file_info, component)
    if field is None:
        ax.text(
            0.5,
            0.5,
            "Aucun résultat plaque exploitable n'est disponible pour cette vue.",
            ha="center",
            va="center",
            fontsize=11,
        )
        ax.axis("off")
        return fig

    coords_2d = np.asarray(field["coords_2d"], dtype=float)
    values = np.asarray(field["values"], dtype=float)
    quads = np.asarray(field["quads"], dtype=int)
    tris_conn, nds_crd_all, nds_val_all = _refined_quads_to_tris(
        quads,
        coords_2d,
        values,
        subdivisions=10,
    )
    if tris_conn.size == 0 or nds_crd_all.size == 0:
        tris_conn, nds_c_crd, nds_c_val = _quads_to_4tris(quads, coords_2d, values)
        nds_crd_all = np.vstack((coords_2d, nds_c_crd))
        nds_val_all = np.hstack((values, nds_c_val))

    triangulation = mtri.Triangulation(
        nds_crd_all[:, 0],
        nds_crd_all[:, 1],
        tris_conn,
    )
    filled_levels = _surface_contour_levels(nds_val_all, count=50)
    line_levels = _surface_contour_levels(nds_val_all, count=14)
    if filled_levels.size <= 1:
        filled_levels = 50
    contour = ax.tricontourf(
        triangulation,
        nds_val_all,
        levels=filled_levels,
        cmap="turbo",
    )
    if line_levels.size > 1:
        isolines = ax.tricontour(
            triangulation,
            nds_val_all,
            levels=line_levels,
            colors="#1f2933",
            linewidths=0.55,
            alpha=0.78,
        )
        ax.clabel(
            isolines,
            inline=True,
            fontsize=7,
            fmt="%.3g",
            colors="#1f2933",
        )
    _plot_mesh_outline(ax, coords_2d, quads)
    fig.colorbar(contour, ax=ax, shrink=0.92)

    plane = str(field["plane"])
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(False)
    if plane == _LOCAL_PLANE:
        ax.set_xlabel("u local (m)")
        ax.set_ylabel("v local (m)")
    else:
        ax.set_xlabel(f"{plane[0]} (m)")
        ax.set_ylabel(f"{plane[1]} (m)")
    title = str(_SURFACE_COMPONENT_SPECS[component]["title"])
    label = file_info.get("label", "")
    if label:
        title = f"{title} - {label}"
    ax.set_title(title, fontsize=12)
    ax.margins(0.08, 0.08)
    fig.tight_layout()
    return fig
