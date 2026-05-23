"""OpenSees reference model for a 5x5 portal frame."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import openseespy.opensees as ops
except ImportError as exc:  # pragma: no cover - depends on local install
    raise SystemExit(
        "OpenSeesPy is not installed. Install it with: pip install openseespy"
    ) from exc


E_CONCRETE = 33_000_000.0
NU_CONCRETE = 0.20
UNIT_WEIGHT_CONCRETE = 25.0
GRAVITY = 9.81

COLUMN_AREA = 0.30 * 0.30
COLUMN_IY = 0.30 * 0.30**3 / 12.0
COLUMN_IZ = COLUMN_IY
COLUMN_J = COLUMN_IY + COLUMN_IZ

SLAB_THICKNESS = 0.20
SLAB_QZ = -UNIT_WEIGHT_CONCRETE * SLAB_THICKNESS

SURFACE_COMPONENTS = ("Nxx", "Nyy", "Nxy", "Mxx", "Myy", "Mxy", "Qx", "Qy")
MOMENT_COMPONENTS = {"Mxx": 3, "Myy": 4, "Mxy": 5, "Qx": 6, "Qy": 7}


@dataclass(frozen=True)
class ShellElementInfo:
    plate_tag: int
    surface_tag: int
    ops_tag: int
    node_tags: tuple[int, int, int, int]


@dataclass(frozen=True)
class PlateMeshInfo:
    plate_tag: int
    node_tags: dict[tuple[int, int], int]
    shell_elements: list[ShellElementInfo]


def main() -> None:
    args = _parse_args()
    formulation = args.formulation
    nx = int(args.mesh)
    ny = int(args.mesh)

    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)

    node_coords = _build_user_nodes()
    for tag, (x, y, z) in node_coords.items():
        ops.node(tag, x, y, z)
        if z == 0.0:
            ops.fix(tag, 1, 1, 1, 1, 1, 1)

    shell_section_tag = 2
    _build_sections(shell_section_tag)
    _build_columns()

    next_node_tag = max(node_coords) + 1
    next_surface_tag = 1
    coord_to_node = {_node_key(point): tag for tag, point in node_coords.items()}

    plate_1, next_node_tag, next_surface_tag = _build_plate_mesh(
        plate_tag=1,
        corners=(2, 8, 6, 4),
        nx=nx,
        ny=ny,
        node_coords=node_coords,
        coord_to_node=coord_to_node,
        next_node_tag=next_node_tag,
        next_surface_tag=next_surface_tag,
        shell_section_tag=shell_section_tag,
        formulation=formulation,
    )
    plate_2, next_node_tag, next_surface_tag = _build_plate_mesh(
        plate_tag=2,
        corners=(8, 12, 10, 6),
        nx=nx,
        ny=ny,
        node_coords=node_coords,
        coord_to_node=coord_to_node,
        next_node_tag=next_node_tag,
        next_surface_tag=next_surface_tag,
        shell_section_tag=shell_section_tag,
        formulation=formulation,
    )
    plates = {1: plate_1, 2: plate_2}

    _apply_self_weight(plates)
    success = _run_static_analysis()
    if not success:
        raise SystemExit("OpenSees analysis did not converge.")

    reaction_sum = _sum_vertical_reactions()
    print(f"Formulation: {formulation}")
    print(f"Mesh per panel: {nx} x {ny}")
    print(f"Nodes: {len(node_coords)}")
    print(f"Shell elements: {sum(len(p.shell_elements) for p in plates.values())}")
    print(f"Sum Fz reactions: {reaction_sum:.6f} kN")

    rows = []
    for plate_tag, plate in plates.items():
        raw_stats = _plate_gauss_stats(plate)
        nodal_stats = _plate_extrapolated_nodal_stats(plate)
        print(f"\nPlate P{plate_tag}")
        print("  Gauss values:")
        _print_stats(raw_stats)
        print("  Nodal extrapolated values:")
        _print_stats(nodal_stats)
        rows.extend(_stats_to_rows(plate_tag, "gauss", raw_stats))
        rows.extend(_stats_to_rows(plate_tag, "nodal_extrapolated", nodal_stats))

    if args.csv:
        _write_csv(Path(args.csv), rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Direct OpenSeesPy reference model for the HEXA/SAP 5x5 slab portal."
    )
    parser.add_argument(
        "--formulation",
        choices=("ShellDKGQ", "ShellMITC4", "ShellNLDKGQ"),
        default="ShellDKGQ",
        help="OpenSees shell element formulation.",
    )
    parser.add_argument(
        "--mesh",
        type=int,
        default=8,
        help="Number of elements per panel direction.",
    )
    parser.add_argument(
        "--csv",
        default="",
        help="Optional CSV output path for extrema.",
    )
    return parser.parse_args()


def _build_user_nodes() -> dict[int, tuple[float, float, float]]:
    return {
        1: (0.0, 0.0, 0.0),
        2: (0.0, 0.0, 3.0),
        3: (0.0, 5.0, 0.0),
        4: (0.0, 5.0, 3.0),
        5: (5.0, 5.0, 0.0),
        6: (5.0, 5.0, 3.0),
        7: (5.0, 0.0, 0.0),
        8: (5.0, 0.0, 3.0),
        9: (10.0, 5.0, 0.0),
        10: (10.0, 5.0, 3.0),
        11: (10.0, 0.0, 0.0),
        12: (10.0, 0.0, 3.0),
    }


def _build_sections(shell_section_tag: int) -> None:
    rho_mass = UNIT_WEIGHT_CONCRETE / GRAVITY
    ops.section(
        "ElasticMembranePlateSection",
        shell_section_tag,
        E_CONCRETE,
        NU_CONCRETE,
        SLAB_THICKNESS,
        rho_mass,
    )


def _build_columns() -> None:
    g_mod = E_CONCRETE / (2.0 * (1.0 + NU_CONCRETE))
    ops.geomTransf("Linear", 1, 1.0, 0.0, 0.0)
    for tag, node_i, node_j in (
        (1, 1, 2),
        (2, 3, 4),
        (3, 5, 6),
        (4, 7, 8),
        (5, 9, 10),
        (6, 11, 12),
    ):
        ops.element(
            "elasticBeamColumn",
            tag,
            node_i,
            node_j,
            COLUMN_AREA,
            E_CONCRETE,
            g_mod,
            COLUMN_J,
            COLUMN_IY,
            COLUMN_IZ,
            1,
        )


def _build_plate_mesh(
    *,
    plate_tag: int,
    corners: tuple[int, int, int, int],
    nx: int,
    ny: int,
    node_coords: dict[int, tuple[float, float, float]],
    coord_to_node: dict[tuple[float, float, float], int],
    next_node_tag: int,
    next_surface_tag: int,
    shell_section_tag: int,
    formulation: str,
) -> tuple[PlateMeshInfo, int, int]:
    corner_points = [node_coords[tag] for tag in corners]
    node_tags: dict[tuple[int, int], int] = {}
    corner_map = {
        (0, 0): corners[0],
        (nx, 0): corners[1],
        (nx, ny): corners[2],
        (0, ny): corners[3],
    }

    for j in range(ny + 1):
        v = j / float(ny)
        for i in range(nx + 1):
            grid_key = (i, j)
            if grid_key in corner_map:
                node_tags[grid_key] = corner_map[grid_key]
                continue
            u = i / float(nx)
            point = _bilinear_point(corner_points, u, v)
            coord_key = _node_key(point)
            existing_tag = coord_to_node.get(coord_key)
            if existing_tag is not None:
                node_tags[grid_key] = existing_tag
                continue
            tag = next_node_tag
            next_node_tag += 1
            node_coords[tag] = point
            coord_to_node[coord_key] = tag
            node_tags[grid_key] = tag
            ops.node(tag, *point)

    shell_elements: list[ShellElementInfo] = []
    for j in range(ny):
        for i in range(nx):
            surface_tag = next_surface_tag
            next_surface_tag += 1
            ops_tag = 6 + surface_tag
            conn = (
                node_tags[(i, j)],
                node_tags[(i + 1, j)],
                node_tags[(i + 1, j + 1)],
                node_tags[(i, j + 1)],
            )
            ops.element(formulation, ops_tag, *conn, shell_section_tag)
            shell_elements.append(
                ShellElementInfo(
                    plate_tag=plate_tag,
                    surface_tag=surface_tag,
                    ops_tag=ops_tag,
                    node_tags=conn,
                )
            )

    return PlateMeshInfo(plate_tag, node_tags, shell_elements), next_node_tag, next_surface_tag


def _apply_self_weight(plates: dict[int, PlateMeshInfo]) -> None:
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)

    # Column self-weight: global -Z is local axial -X for vertical columns.
    column_weight = -UNIT_WEIGHT_CONCRETE * COLUMN_AREA
    for element_tag in range(1, 7):
        ops.eleLoad("-ele", element_tag, "-type", "-beamUniform", 0.0, 0.0, column_weight)

    # Shell self-weight: match HEXA by converting qz to equivalent nodal loads.
    nodal_loads: dict[int, list[float]] = defaultdict(lambda: [0.0] * 6)
    for plate in plates.values():
        for shell in plate.shell_elements:
            area = _quad_area([ops.nodeCoord(tag) for tag in shell.node_tags])
            fz = SLAB_QZ * area / 4.0
            for node_tag in shell.node_tags:
                nodal_loads[node_tag][2] += fz

    for node_tag, load in sorted(nodal_loads.items()):
        ops.load(node_tag, *load)


def _run_static_analysis() -> bool:
    ops.constraints("Transformation")
    ops.numberer("Plain")
    try:
        ops.system("UmfPack")
    except Exception:
        ops.system("BandGeneral")
    ops.test("NormDispIncr", 1e-6, 100)
    ops.algorithm("Newton")
    ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")
    return ops.analyze(1) == 0


def _sum_vertical_reactions() -> float:
    ops.reactions()
    total = 0.0
    for tag in (1, 3, 5, 7, 9, 11):
        reaction = ops.nodeReaction(tag)
        total += float(reaction[2])
    return total


def _plate_gauss_stats(plate: PlateMeshInfo) -> dict[str, tuple[float, float]]:
    values_by_component: dict[str, list[float]] = {name: [] for name in MOMENT_COMPONENTS}
    for shell in plate.shell_elements:
        gauss_values = _shell_gauss_values(shell.ops_tag)
        for component, index in MOMENT_COMPONENTS.items():
            values_by_component[component].extend(row[index] for row in gauss_values)
    return {
        component: (min(values), max(values))
        for component, values in values_by_component.items()
        if values
    }


def _plate_extrapolated_nodal_stats(
    plate: PlateMeshInfo,
) -> dict[str, tuple[float, float]]:
    values_by_component: dict[str, list[float]] = {}
    for component, index in MOMENT_COMPONENTS.items():
        sums: dict[int, float] = defaultdict(float)
        counts: dict[int, int] = defaultdict(int)
        for shell in plate.shell_elements:
            gauss_values = [row[index] for row in _shell_gauss_values(shell.ops_tag)]
            if len(gauss_values) != 4:
                continue
            nodal_values = _extrapolate_ip_to_node_quad(gauss_values)
            for node_tag, value in zip(shell.node_tags, nodal_values):
                sums[node_tag] += float(value)
                counts[node_tag] += 1
        values_by_component[component] = [
            sums[node_tag] / counts[node_tag]
            for node_tag in sorted(sums)
            if counts[node_tag] > 0
        ]
    return {
        component: (min(values), max(values))
        for component, values in values_by_component.items()
        if values
    }


def _shell_gauss_values(ops_tag: int) -> list[tuple[float, ...]]:
    response = ops.eleResponse(ops_tag, "stresses")
    if response is None:
        return []
    values = [float(value) for value in response]
    width = len(SURFACE_COMPONENTS)
    if len(values) % width != 0:
        return []
    return [
        tuple(values[index : index + width])
        for index in range(0, len(values), width)
    ]


def _print_stats(stats: dict[str, tuple[float, float]]) -> None:
    for component in ("Mxx", "Myy", "Mxy", "Qx", "Qy"):
        min_value, max_value = stats.get(component, (0.0, 0.0))
        abs_value = max(abs(min_value), abs(max_value))
        print(
            f"    {component}: min={min_value: .4f}, "
            f"max={max_value: .4f}, absmax={abs_value: .4f}"
        )


def _stats_to_rows(
    plate_tag: int,
    location: str,
    stats: dict[str, tuple[float, float]],
) -> list[dict[str, object]]:
    rows = []
    for component, (min_value, max_value) in stats.items():
        rows.append(
            {
                "plate": plate_tag,
                "location": location,
                "component": component,
                "min": min_value,
                "max": max_value,
                "absmax": max(abs(min_value), abs(max_value)),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("plate", "location", "component", "min", "max", "absmax"),
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV written to: {path}")


def _bilinear_point(
    corners: list[tuple[float, float, float]],
    u: float,
    v: float,
) -> tuple[float, float, float]:
    weights = (
        (1.0 - u) * (1.0 - v),
        u * (1.0 - v),
        u * v,
        (1.0 - u) * v,
    )
    return tuple(
        sum(weight * point[index] for weight, point in zip(weights, corners))
        for index in range(3)
    )


def _node_key(point: Iterable[float], ndigits: int = 9) -> tuple[float, float, float]:
    return tuple(round(float(value), ndigits) for value in point)


def _quad_area(points: list[Iterable[float]]) -> float:
    p = [tuple(float(value) for value in point) for point in points]
    return 0.5 * _norm(_cross(_sub(p[1], p[0]), _sub(p[2], p[0]))) + 0.5 * _norm(
        _cross(_sub(p[2], p[0]), _sub(p[3], p[0]))
    )


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _extrapolate_ip_to_node_quad(values_at_ip: list[float]) -> list[float]:
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


if __name__ == "__main__":
    main()
