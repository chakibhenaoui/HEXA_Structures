"""Mapping from analysis results to user-facing results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.model_data import ProjectModel
    from core.plate_mesher import GeneratedPlateMesh


@dataclass
class PlateRegionResult:
    """Result data for plate region result."""

    tag: int

    uz_min: float = 0.0
    uz_max: float = 0.0
    uz_min_node: int | None = None
    uz_max_node: int | None = None

    mxx_min: float = 0.0
    mxx_max: float = 0.0
    myy_min: float = 0.0
    myy_max: float = 0.0
    mxy_min: float = 0.0
    mxy_max: float = 0.0

    qx_min: float = 0.0
    qx_max: float = 0.0
    qy_min: float = 0.0
    qy_max: float = 0.0

    fz_reaction_total: float = 0.0

    node_tags: tuple[int, ...] = ()
    surface_tags: tuple[int, ...] = ()


@dataclass
class PlateEdgeReactionResult:
    """Result data for plate edge reaction result."""

    plate_tag: int
    edge: str

    fx: float = 0.0
    fy: float = 0.0
    fz: float = 0.0
    mx: float = 0.0
    my: float = 0.0
    mz: float = 0.0

    node_tags: tuple[int, ...] = ()


def map_analysis_results_to_user_results(
    user_project: "ProjectModel",
    analysis_project: "ProjectModel",
    raw_results: dict,
    generated_plate_meshes: dict[int, "GeneratedPlateMesh"],
) -> dict:
    """Map analysis results to user results."""
    user_node_tags = set(user_project.nodes)
    user_element_tags = set(user_project.elements)
    generated_surface_tags = {
        int(surface_tag)
        for mesh in generated_plate_meshes.values()
        for surface_tag in mesh.surface_tags
    }
    generated_node_tags = {
        int(node_tag)
        for mesh in generated_plate_meshes.values()
        for node_tag in mesh.node_tags.values()
    }

    user_displacements = {
        int(tag): result
        for tag, result in raw_results.get("displacements", {}).items()
        if int(tag) in user_node_tags
    }
    user_reactions = {
        int(tag): result
        for tag, result in raw_results.get("reactions", {}).items()
        if int(tag) in user_node_tags
    }
    user_element_forces = {
        int(tag): result
        for tag, result in raw_results.get("element_forces", {}).items()
        if int(tag) in user_element_tags
    }
    user_surface_results = {
        int(tag): result
        for tag, result in raw_results.get("surface_results", {}).items()
        if int(tag) in user_project.surface_elements
        and int(tag) not in generated_surface_tags
    }

    plate_results = {
        int(plate_tag): _aggregate_plate_result(
            int(plate_tag),
            mesh,
            raw_results,
            analysis_project,
        )
        for plate_tag, mesh in sorted(generated_plate_meshes.items())
        if int(plate_tag) in user_project.plate_regions
    }
    plate_edge_reactions = _aggregate_plate_edge_reactions(
        user_project,
        raw_results,
        generated_plate_meshes,
    )

    context = dict(raw_results.get("result_context", {}) or {})
    context.update(
        {
            "node_count": len(user_project.nodes),
            "element_count": len(user_project.elements),
            "surface_count": len(user_project.surface_elements),
            "visible_node_count": len(user_displacements),
            "visible_reaction_count": len(user_reactions),
            "visible_element_count": len(user_element_forces),
            "visible_surface_count": len(user_surface_results),
            "user_node_count": len(user_project.nodes),
            "analysis_node_count": len(analysis_project.nodes),
            "user_surface_count": len(user_project.surface_elements),
            "analysis_surface_count": len(analysis_project.surface_elements),
            "plate_region_count": len(user_project.plate_regions),
            "plate_result_count": len(plate_results),
            "plate_result_value_location": "nodal_extrapolated",
            "generated_plate_count": len(generated_plate_meshes),
            "generated_plate_surface_count": sum(
                len(mesh.surface_tags) for mesh in generated_plate_meshes.values()
            ),
            "generated_plate_node_count": len(generated_node_tags),
            "generated_plate_mesh_sizes": {
                int(plate_tag): (
                    int(getattr(mesh, "mesh_nx", 0)),
                    int(getattr(mesh, "mesh_ny", 0)),
                )
                for plate_tag, mesh in generated_plate_meshes.items()
            },
            "surface_results_available": bool(user_surface_results or plate_results),
        }
    )

    mapped = dict(raw_results)
    mapped.update(
        {
            "displacements": user_displacements,
            "reactions": user_reactions,
            "element_forces": user_element_forces,
            "surface_results": user_surface_results,
            "plate_results": plate_results,
            "plate_edge_reactions": plate_edge_reactions,
            "internal_results": {
                "available": bool(generated_plate_meshes),
                "raw_available": True,
                "raw_results": raw_results,
                "displacements": raw_results.get("displacements", {}),
                "reactions": raw_results.get("reactions", {}),
                "element_forces": raw_results.get("element_forces", {}),
                "surface_results": raw_results.get("surface_results", {}),
                "generated_node_count": len(generated_node_tags - user_node_tags),
                "generated_surface_count": len(generated_surface_tags),
            },
            "result_context": context,
        }
    )
    return mapped


def _aggregate_plate_result(
    plate_tag: int,
    mesh: "GeneratedPlateMesh",
    raw_results: dict,
    analysis_project: "ProjectModel",
) -> PlateRegionResult:
    displacements = raw_results.get("displacements", {})
    reactions = raw_results.get("reactions", {})
    surface_results = raw_results.get("surface_results", {})

    unique_node_tags = tuple(sorted(set(int(tag) for tag in mesh.node_tags.values())))
    surface_tags = tuple(int(tag) for tag in mesh.surface_tags)

    uz_values = [
        (tag, float(displacements[tag].uz))
        for tag in unique_node_tags
        if tag in displacements
    ]
    surf_results = [
        surface_results[tag]
        for tag in surface_tags
        if tag in surface_results
    ]

    uz_min, uz_max = _min_max(value for _tag, value in uz_values)
    uz_min_node = min(uz_values, key=lambda item: item[1])[0] if uz_values else None
    uz_max_node = max(uz_values, key=lambda item: item[1])[0] if uz_values else None

    mxx_values = _plate_nodal_component_values(
        analysis_project, surface_tags, surface_results, "mxx", 3
    )
    myy_values = _plate_nodal_component_values(
        analysis_project, surface_tags, surface_results, "myy", 4
    )
    mxy_values = _plate_nodal_component_values(
        analysis_project, surface_tags, surface_results, "mxy", 5
    )
    qx_values = _plate_nodal_component_values(
        analysis_project, surface_tags, surface_results, "qx", 6
    )
    qy_values = _plate_nodal_component_values(
        analysis_project, surface_tags, surface_results, "qy", 7
    )

    return PlateRegionResult(
        tag=plate_tag,
        uz_min=uz_min,
        uz_max=uz_max,
        uz_min_node=uz_min_node,
        uz_max_node=uz_max_node,
        mxx_min=_min_value(mxx_values),
        mxx_max=_max_value(mxx_values),
        myy_min=_min_value(myy_values),
        myy_max=_max_value(myy_values),
        mxy_min=_min_value(mxy_values),
        mxy_max=_max_value(mxy_values),
        qx_min=_min_value(qx_values),
        qx_max=_max_value(qx_values),
        qy_min=_min_value(qy_values),
        qy_max=_max_value(qy_values),
        fz_reaction_total=sum(
            float(reactions[tag].fz_reaction)
            for tag in unique_node_tags
            if tag in reactions
        ),
        node_tags=unique_node_tags,
        surface_tags=surface_tags,
    )


def _surface_component_values(
    surface_results: list,
    field_name: str,
    gauss_index: int,
) -> list[float]:
    """Handle surface component values."""
    values: list[float] = []
    for result in surface_results:
        gauss_resultants = getattr(result, "gauss_resultants", ()) or ()
        for gauss_values in gauss_resultants:
            if len(gauss_values) > gauss_index:
                values.append(float(gauss_values[gauss_index]))
        if not gauss_resultants:
            values.append(float(getattr(result, field_name, 0.0)))
    return values


def _plate_nodal_component_values(
    analysis_project: "ProjectModel",
    surface_tags: tuple[int, ...],
    surface_results: dict,
    field_name: str,
    gauss_index: int,
) -> list[float]:
    """Handle plate nodal component values."""
    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    fallback_values: list[float] = []

    for surface_tag in surface_tags:
        surface = analysis_project.surface_elements.get(int(surface_tag))
        result = surface_results.get(int(surface_tag))
        if surface is None or result is None:
            continue

        gauss_resultants = getattr(result, "gauss_resultants", ()) or ()
        if len(surface.node_tags) == 4 and len(gauss_resultants) >= 4:
            gauss_values = [
                float(values[gauss_index])
                for values in gauss_resultants[:4]
                if len(values) > gauss_index
            ]
            if len(gauss_values) == 4:
                for node_tag, value in zip(
                    surface.node_tags,
                    _extrapolate_ip_to_node_quad(gauss_values),
                ):
                    node_tag = int(node_tag)
                    sums[node_tag] = sums.get(node_tag, 0.0) + float(value)
                    counts[node_tag] = counts.get(node_tag, 0) + 1
                continue

        fallback_values.append(float(getattr(result, field_name, 0.0)))

    nodal_values = [
        sums[node_tag] / float(counts[node_tag])
        for node_tag in sorted(sums)
        if counts[node_tag] > 0
    ]
    return nodal_values if nodal_values else fallback_values


def _extrapolate_ip_to_node_quad(values_at_ip: list[float]) -> list[float]:
    """Extrapolate ip to node quad."""
    xep = 0.8660254037844386
    weights = (
        (1.0 + xep, -0.5, 1.0 - xep, -0.5),
        (-0.5, 1.0 + xep, -0.5, 1.0 - xep),
        (1.0 - xep, -0.5, 1.0 + xep, -0.5),
        (-0.5, 1.0 - xep, -0.5, 1.0 + xep),
    )
    return [
        sum(weight * value for weight, value in zip(row, values_at_ip))
        for row in weights
    ]


def _aggregate_plate_edge_reactions(
    user_project: "ProjectModel",
    raw_results: dict,
    generated_plate_meshes: dict[int, "GeneratedPlateMesh"],
) -> dict[int, dict[str, PlateEdgeReactionResult]]:
    edge_results: dict[int, dict[str, PlateEdgeReactionResult]] = {}
    for support in user_project.plate_edge_supports:
        plate_tag = int(support.plate_tag)
        mesh = generated_plate_meshes.get(plate_tag)
        plate = user_project.plate_regions.get(plate_tag)
        if mesh is None or plate is None:
            continue
        node_tags = _edge_node_tags(mesh, support.edge, mesh.mesh_nx, mesh.mesh_ny)
        edge_results.setdefault(plate_tag, {})[str(support.edge)] = (
            _aggregate_edge_reaction(plate_tag, str(support.edge), node_tags, raw_results)
        )
    return edge_results


def _edge_node_tags(
    mesh: "GeneratedPlateMesh",
    edge: str,
    mesh_nx: int,
    mesh_ny: int,
) -> list[int]:
    edge = str(edge).strip()
    if edge == "12":
        return [mesh.node_tags[(i, 0)] for i in range(int(mesh_nx) + 1)]
    if edge == "23":
        return [mesh.node_tags[(int(mesh_nx), j)] for j in range(int(mesh_ny) + 1)]
    if edge == "34":
        return [mesh.node_tags[(i, int(mesh_ny))] for i in range(int(mesh_nx) + 1)]
    if edge == "41":
        return [mesh.node_tags[(0, j)] for j in range(int(mesh_ny) + 1)]
    raise ValueError(f"Bord de plaque inconnu: {edge}")


def _aggregate_edge_reaction(
    plate_tag: int,
    edge: str,
    node_tags: list[int],
    raw_results: dict,
) -> PlateEdgeReactionResult:
    reactions = raw_results.get("reactions", {})
    unique = tuple(sorted(set(int(tag) for tag in node_tags)))

    return PlateEdgeReactionResult(
        plate_tag=plate_tag,
        edge=edge,
        fx=sum(float(reactions[tag].fx_reaction) for tag in unique if tag in reactions),
        fy=sum(float(reactions[tag].fy_reaction) for tag in unique if tag in reactions),
        fz=sum(float(reactions[tag].fz_reaction) for tag in unique if tag in reactions),
        mx=sum(float(reactions[tag].mx_reaction) for tag in unique if tag in reactions),
        my=sum(float(reactions[tag].my_reaction) for tag in unique if tag in reactions),
        mz=sum(float(reactions[tag].mz_reaction) for tag in unique if tag in reactions),
        node_tags=unique,
    )


def _min_max(values) -> tuple[float, float]:
    collected = [float(value) for value in values]
    if not collected:
        return 0.0, 0.0
    return min(collected), max(collected)


def _min_value(values) -> float:
    return _min_max(values)[0]


def _max_value(values) -> float:
    return _min_max(values)[1]
