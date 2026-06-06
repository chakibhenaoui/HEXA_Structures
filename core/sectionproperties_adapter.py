"""Optional bridge to the ``sectionproperties`` cross-section library.

The adapter is intentionally GUI-free.  It lets HEXA use sectionproperties for
user-defined sections while keeping the core able to start when the optional
package is not installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from importlib import import_module
from importlib.util import find_spec
from inspect import isfunction
from typing import Mapping

from core.section_builder import Point2D, validate_simple_polygon


class SectionPropertiesUnavailable(RuntimeError):
    """Raised when sectionproperties is required but not installed."""


class SectionPropertiesCalculationError(ValueError):
    """Raised when a sectionproperties calculation cannot be completed."""


@dataclass(frozen=True)
class SectionPropertyShape:
    """Supported sectionproperties shape metadata."""

    key: str
    label: str
    library_function: str
    display_type: str
    default_material_type: str
    fields: tuple[str, ...]
    defaults: Mapping[str, float]


@dataclass(frozen=True)
class SectionPropertiesResult:
    """Computed properties for a user section."""

    area: float
    inertia_y: float
    inertia_z: float
    torsion_constant: float
    ixy: float
    properties: dict
    mesh: "SectionPropertiesMesh | None" = None


@dataclass(frozen=True)
class SectionPropertiesMesh:
    """Finite-element mesh extracted from sectionproperties for GUI display."""

    vertices: tuple[Point2D, ...]
    triangles: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class SectionPropertiesCapability:
    """One sectionproperties capability that HEXA can expose progressively."""

    key: str
    label: str
    module_path: str
    api_name: str
    implemented: bool = False


@dataclass(frozen=True)
class SectionPropertiesBackendInfo:
    """Runtime import status for the optional sectionproperties backend."""

    available: bool
    version: str | None
    modules: tuple[str, ...]
    capabilities: tuple[SectionPropertiesCapability, ...]
    library_functions: tuple[str, ...]
    error: str | None = None


SECTIONPROPERTIES_MODULES = (
    "sectionproperties",
    "sectionproperties.pre",
    "sectionproperties.pre.library",
    "sectionproperties.analysis",
    "sectionproperties.post",
)

SECTIONPROPERTIES_CAPABILITIES = (
    SectionPropertiesCapability(
        "geometry_library",
        "Section library",
        "sectionproperties.pre.library",
        "shape functions",
        implemented=True,
    ),
    SectionPropertiesCapability(
        "mesh",
        "Mesh generation",
        "sectionproperties.pre.geometry",
        "Geometry.create_mesh",
        implemented=True,
    ),
    SectionPropertiesCapability(
        "geometric",
        "Geometric analysis",
        "sectionproperties.analysis",
        "Section.calculate_geometric_properties",
        implemented=True,
    ),
    SectionPropertiesCapability(
        "warping",
        "Warping analysis",
        "sectionproperties.analysis",
        "Section.calculate_warping_properties",
        implemented=True,
    ),
    SectionPropertiesCapability(
        "frame",
        "Frame analysis",
        "sectionproperties.analysis",
        "Section.calculate_frame_properties",
    ),
    SectionPropertiesCapability(
        "plastic",
        "Plastic analysis",
        "sectionproperties.analysis",
        "Section.calculate_plastic_properties",
    ),
    SectionPropertiesCapability(
        "stress",
        "Stress analysis",
        "sectionproperties.analysis",
        "Section.calculate_stress",
    ),
    SectionPropertiesCapability(
        "post",
        "Post-processing",
        "sectionproperties.post",
        "StressPost / plots",
    ),
)


SECTIONPROPERTY_SHAPES: dict[str, SectionPropertyShape] = {
    "rectangular": SectionPropertyShape(
        key="rectangular",
        label="Rectangle",
        library_function="rectangular_section",
        display_type="rectangular",
        default_material_type="concrete",
        fields=("d", "b"),
        defaults={"d": 0.30, "b": 0.20},
    ),
    "circle": SectionPropertyShape(
        key="circle",
        label="Solid circle",
        library_function="circular_section",
        display_type="circle",
        default_material_type="concrete",
        fields=("d",),
        defaults={"d": 0.20},
    ),
    "i": SectionPropertyShape(
        key="i",
        label="I / H",
        library_function="i_section",
        display_type="I",
        default_material_type="steel",
        fields=("d", "b", "t_f", "t_w", "r"),
        defaults={"d": 0.30, "b": 0.15, "t_f": 0.012, "t_w": 0.008, "r": 0.0},
    ),
    "channel": SectionPropertyShape(
        key="channel",
        label="U / Channel",
        library_function="channel_section",
        display_type="channel",
        default_material_type="steel",
        fields=("d", "b", "t_f", "t_w", "r"),
        defaults={"d": 0.20, "b": 0.08, "t_f": 0.010, "t_w": 0.008, "r": 0.0},
    ),
    "tee": SectionPropertyShape(
        key="tee",
        label="Tee",
        library_function="tee_section",
        display_type="T",
        default_material_type="steel",
        fields=("d", "b", "t_f", "t_w", "r"),
        defaults={"d": 0.20, "b": 0.10, "t_f": 0.012, "t_w": 0.006, "r": 0.0},
    ),
    "angle": SectionPropertyShape(
        key="angle",
        label="Angle L",
        library_function="angle_section",
        display_type="angle",
        default_material_type="steel",
        fields=("d", "b", "t", "r_r", "r_t"),
        defaults={"d": 0.10, "b": 0.075, "t": 0.008, "r_r": 0.0, "r_t": 0.0},
    ),
    "chs": SectionPropertyShape(
        key="chs",
        label="CHS",
        library_function="circular_hollow_section",
        display_type="pipe",
        default_material_type="steel",
        fields=("d", "t"),
        defaults={"d": 0.114, "t": 0.005},
    ),
    "rhs": SectionPropertyShape(
        key="rhs",
        label="RHS / SHS",
        library_function="rectangular_hollow_section",
        display_type="tube",
        default_material_type="steel",
        fields=("d", "b", "t", "r_out"),
        defaults={"d": 0.20, "b": 0.10, "t": 0.006, "r_out": 0.0},
    ),
}


def is_sectionproperties_available() -> bool:
    """Return whether the optional sectionproperties package can be imported."""
    return find_spec("sectionproperties") is not None


def sectionproperties_version() -> str | None:
    """Return the installed sectionproperties version, if discoverable."""
    if not is_sectionproperties_available():
        return None
    try:
        return metadata.version("sectionproperties")
    except metadata.PackageNotFoundError:
        return None


def import_sectionproperties_modules() -> dict[str, object]:
    """Import the optional sectionproperties modules needed by HEXA."""
    if not is_sectionproperties_available():
        raise SectionPropertiesUnavailable("sectionproperties is not installed")
    modules: dict[str, object] = {}
    for module_path in SECTIONPROPERTIES_MODULES:
        modules[module_path] = import_module(module_path)
    return modules


def list_sectionproperties_library_functions() -> tuple[str, ...]:
    """Return public builder functions exposed by sectionproperties.pre.library."""
    modules = import_sectionproperties_modules()
    library = modules["sectionproperties.pre.library"]
    names = [
        name
        for name, value in vars(library).items()
        if isfunction(value) and not name.startswith("_")
    ]
    return tuple(sorted(names))


def sectionproperties_backend_info() -> SectionPropertiesBackendInfo:
    """Return import status and discoverable capabilities for the optional backend."""
    if not is_sectionproperties_available():
        return SectionPropertiesBackendInfo(
            available=False,
            version=None,
            modules=(),
            capabilities=SECTIONPROPERTIES_CAPABILITIES,
            library_functions=(),
            error="sectionproperties is not installed",
        )
    try:
        modules = import_sectionproperties_modules()
        library_functions = list_sectionproperties_library_functions()
    except Exception as exc:
        return SectionPropertiesBackendInfo(
            available=False,
            version=sectionproperties_version(),
            modules=(),
            capabilities=SECTIONPROPERTIES_CAPABILITIES,
            library_functions=(),
            error=str(exc),
        )
    return SectionPropertiesBackendInfo(
        available=True,
        version=sectionproperties_version(),
        modules=tuple(modules),
        capabilities=SECTIONPROPERTIES_CAPABILITIES,
        library_functions=library_functions,
    )


def list_sectionproperty_shapes() -> tuple[SectionPropertyShape, ...]:
    """Return supported shape definitions in GUI order."""
    return tuple(SECTIONPROPERTY_SHAPES.values())


def get_sectionproperty_shape(shape_key: str) -> SectionPropertyShape:
    """Return a shape definition by key."""
    try:
        return SECTIONPROPERTY_SHAPES[shape_key]
    except KeyError as exc:
        raise SectionPropertiesCalculationError(
            f"Unsupported sectionproperties shape: {shape_key}"
        ) from exc


def default_dimensions(shape_key: str) -> dict[str, float]:
    """Return editable default dimensions for a supported shape."""
    return dict(get_sectionproperty_shape(shape_key).defaults)


def validate_sectionproperty_dimensions(
    shape_key: str,
    dimensions: Mapping[str, float],
) -> str | None:
    """Return a stable validation code for invalid dimensions, if any."""
    shape = get_sectionproperty_shape(shape_key)
    values = _complete_dimensions(shape, dimensions)
    if any(values[field] <= 0.0 for field in shape.fields if not field.startswith("r")):
        return "positive_dimensions"
    if any(values[field] < 0.0 for field in shape.fields if field.startswith("r")):
        return "positive_radii"

    if shape_key == "i":
        if values["t_w"] >= values["b"]:
            return "web_too_thick"
        if 2.0 * values["t_f"] >= values["d"]:
            return "flange_too_thick"
    elif shape_key == "channel":
        if values["t_w"] >= values["b"]:
            return "web_too_thick"
        if 2.0 * values["t_f"] >= values["d"]:
            return "flange_too_thick"
    elif shape_key == "tee":
        if values["t_w"] >= values["b"]:
            return "web_too_thick"
        if values["t_f"] >= values["d"]:
            return "flange_too_thick"
    elif shape_key == "angle":
        if values["t"] >= min(values["d"], values["b"]):
            return "angle_too_thick"
        if values["r_t"] > values["t"]:
            return "toe_radius_too_large"
    elif shape_key == "chs":
        if 2.0 * values["t"] >= values["d"]:
            return "hollow_too_thick"
    elif shape_key == "rhs":
        if 2.0 * values["t"] >= min(values["d"], values["b"]):
            return "hollow_too_thick"

    return None


def calculate_sectionproperties_section(
    shape_key: str,
    dimensions: Mapping[str, float],
    *,
    mesh_area: float = 1.0e-4,
) -> SectionPropertiesResult:
    """Calculate A, Iy, Iz and J for a supported sectionproperties shape."""
    if not is_sectionproperties_available():
        raise SectionPropertiesUnavailable("sectionproperties is not installed")
    if mesh_area <= 0.0:
        raise SectionPropertiesCalculationError("mesh_area must be positive")

    shape = get_sectionproperty_shape(shape_key)
    values = _complete_dimensions(shape, dimensions)
    error_code = validate_sectionproperty_dimensions(shape_key, values)
    if error_code is not None:
        raise SectionPropertiesCalculationError(error_code)

    try:
        library = import_module("sectionproperties.pre.library")
        section_cls = getattr(import_module("sectionproperties.analysis"), "Section")
        builder = getattr(library, shape.library_function)
        geometry = builder(**_builder_kwargs(shape_key, values))
        geometry.create_mesh(mesh_sizes=[float(mesh_area)])
        section = section_cls(geometry=geometry)
        section.calculate_geometric_properties()
        area = float(section.get_area())
        ixx, iyy, ixy = (float(value) for value in section.get_ic())
        try:
            section.calculate_warping_properties()
            torsion_constant = float(section.get_j())
        except Exception:
            torsion_constant = 0.0
        centroid_x, centroid_y = (float(value) for value in section.get_c())
    except Exception as exc:
        if isinstance(exc, SectionPropertiesCalculationError):
            raise
        raise SectionPropertiesCalculationError(str(exc)) from exc

    display_properties = display_properties_for_shape(shape_key, values)
    mesh = _mesh_from_geometry(geometry)
    properties = {
        "source": "sectionproperties",
        "shape": shape.key,
        "shape_label": shape.label,
        "display_type": shape.display_type,
        "display_properties": display_properties,
        "dimensions": dict(values),
        "mesh_area": float(mesh_area),
        "centroid_local_y": centroid_x,
        "centroid_local_z": centroid_y,
        "ixy": ixy,
    }
    if torsion_constant > 0.0:
        properties["torsion_constant"] = torsion_constant
        properties["torsion_j"] = torsion_constant
        properties["J"] = torsion_constant

    return SectionPropertiesResult(
        area=area,
        inertia_y=ixx,
        inertia_z=iyy,
        torsion_constant=torsion_constant,
        ixy=ixy,
        properties=properties,
        mesh=mesh,
    )


def calculate_polygon_sectionproperties_section(
    points: list[Point2D] | tuple[Point2D, ...],
    *,
    mesh_area: float = 1.0e-4,
) -> SectionPropertiesResult:
    """Calculate a custom simple polygon section with sectionproperties.

    ``points`` are local section coordinates in meters using HEXA's y/z plane.
    The returned inertias follow the same convention as
    :func:`calculate_sectionproperties_section`: ``inertia_y`` is the second
    moment about local y, and ``inertia_z`` about local z.
    """
    if not is_sectionproperties_available():
        raise SectionPropertiesUnavailable("sectionproperties is not installed")
    if mesh_area <= 0.0:
        raise SectionPropertiesCalculationError("mesh_area must be positive")

    normalized_points = _normalize_polygon_points(points)
    validate_simple_polygon(normalized_points)

    try:
        polygon_cls = getattr(import_module("shapely"), "Polygon")
        geometry_cls = getattr(import_module("sectionproperties.pre.geometry"), "Geometry")
        section_cls = getattr(import_module("sectionproperties.analysis"), "Section")
        geometry = geometry_cls(geom=polygon_cls(normalized_points))
        geometry.create_mesh(mesh_sizes=[float(mesh_area)])
        section = section_cls(geometry=geometry)
        section.calculate_geometric_properties()
        area = float(section.get_area())
        ixx, iyy, ixy = (float(value) for value in section.get_ic())
        centroid_y, centroid_z = (float(value) for value in section.get_c())
        try:
            section.calculate_warping_properties()
            torsion_constant = float(section.get_j())
        except Exception:
            torsion_constant = 0.0
    except Exception as exc:
        if isinstance(exc, SectionPropertiesCalculationError):
            raise
        raise SectionPropertiesCalculationError(str(exc)) from exc

    mesh = _mesh_from_geometry(geometry)
    properties = {
        "source": "sectionproperties",
        "shape": "custom_polygon",
        "display_type": "custom_polygon",
        "mesh_area": float(mesh_area),
        "centroid_local_y": centroid_y,
        "centroid_local_z": centroid_z,
        "ixy": ixy,
    }
    if torsion_constant > 0.0:
        properties["torsion_constant"] = torsion_constant
        properties["torsion_j"] = torsion_constant
        properties["J"] = torsion_constant

    return SectionPropertiesResult(
        area=area,
        inertia_y=ixx,
        inertia_z=iyy,
        torsion_constant=torsion_constant,
        ixy=ixy,
        properties=properties,
        mesh=mesh,
    )


def display_properties_for_shape(
    shape_key: str,
    dimensions: Mapping[str, float],
) -> dict[str, float]:
    """Return geometry properties usable by HEXA's existing preview/extrusion code."""
    shape = get_sectionproperty_shape(shape_key)
    values = _complete_dimensions(shape, dimensions)
    if shape.display_type == "rectangular":
        return {"h": values["d"], "b": values["b"]}
    if shape.display_type == "circle":
        return {"d": values["d"]}
    if shape.display_type == "I":
        return {
            "h": values["d"],
            "b": values["b"],
            "tf": values["t_f"],
            "tw": values["t_w"],
        }
    if shape.display_type == "channel":
        return {
            "h": values["d"],
            "b": values["b"],
            "tf": values["t_f"],
            "tw": values["t_w"],
        }
    if shape.display_type == "T":
        return {
            "hw": max(values["d"] - values["t_f"], 0.0),
            "hf": values["t_f"],
            "bf": values["b"],
            "bw": values["t_w"],
        }
    if shape.display_type == "angle":
        return {"h": values["d"], "b": values["b"], "t": values["t"]}
    if shape.display_type == "pipe":
        return {"d": values["d"], "t": values["t"]}
    if shape.display_type == "tube":
        return {"h": values["d"], "b": values["b"], "t": values["t"]}
    return {}


def _normalize_polygon_points(points: list[Point2D] | tuple[Point2D, ...]) -> list[Point2D]:
    normalized = [(float(y), float(z)) for y, z in points]
    if len(normalized) >= 2:
        first = normalized[0]
        last = normalized[-1]
        if abs(first[0] - last[0]) <= 1.0e-12 and abs(first[1] - last[1]) <= 1.0e-12:
            normalized.pop()
    return normalized


def _mesh_from_geometry(geometry) -> SectionPropertiesMesh | None:
    mesh = getattr(geometry, "mesh", None)
    if not mesh:
        return None
    vertices = tuple(
        (float(vertex[0]), float(vertex[1]))
        for vertex in mesh.get("vertices", [])
    )
    triangles = tuple(
        (int(triangle[0]), int(triangle[1]), int(triangle[2]))
        for triangle in mesh.get("triangles", [])
        if len(triangle) >= 3
    )
    if not vertices or not triangles:
        return None
    return SectionPropertiesMesh(vertices=vertices, triangles=triangles)


def _complete_dimensions(
    shape: SectionPropertyShape,
    dimensions: Mapping[str, float],
) -> dict[str, float]:
    values: dict[str, float] = {}
    for field in shape.fields:
        try:
            values[field] = float(dimensions.get(field, shape.defaults[field]))
        except (TypeError, ValueError) as exc:
            raise SectionPropertiesCalculationError(
                f"Invalid value for dimension {field}"
            ) from exc
    return values


def _builder_kwargs(shape_key: str, values: Mapping[str, float]) -> dict:
    if shape_key == "rectangular":
        return {"d": values["d"], "b": values["b"]}
    if shape_key == "circle":
        return {"d": values["d"], "n": 64}
    if shape_key in {"i", "channel", "tee"}:
        return {
            "d": values["d"],
            "b": values["b"],
            "t_f": values["t_f"],
            "t_w": values["t_w"],
            "r": values["r"],
            "n_r": 8,
        }
    if shape_key == "angle":
        return {
            "d": values["d"],
            "b": values["b"],
            "t": values["t"],
            "r_r": values["r_r"],
            "r_t": values["r_t"],
            "n_r": 8,
        }
    if shape_key == "chs":
        return {"d": values["d"], "t": values["t"], "n": 64}
    if shape_key == "rhs":
        return {
            "d": values["d"],
            "b": values["b"],
            "t": values["t"],
            "r_out": values["r_out"],
            "n_r": 8,
        }
    raise SectionPropertiesCalculationError(
        f"Unsupported sectionproperties shape: {shape_key}"
    )
