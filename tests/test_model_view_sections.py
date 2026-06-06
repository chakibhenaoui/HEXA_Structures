from __future__ import annotations

import math
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from core.model_data import ProjectModel
from core.sections import TSection, get_profile

pytest.importorskip("pyvista")
pytest.importorskip("pyvistaqt")

from gui.widgets.model_view import ModelView


def test_rectangular_section_polygon_uses_real_dimensions() -> None:
    polygon = ModelView._section_polygon_points(
        "rectangular",
        {"b": 0.30, "h": 0.50},
    )

    assert polygon is not None
    assert polygon.shape == (4, 2)
    assert math.isclose(float(polygon[:, 0].max() - polygon[:, 0].min()), 0.30)
    assert math.isclose(float(polygon[:, 1].max() - polygon[:, 1].min()), 0.50)


def test_sectionproperties_section_polygon_delegates_to_display_type() -> None:
    polygon = ModelView._section_polygon_points(
        "sectionproperties",
        {
            "display_type": "I",
            "display_properties": {"h": 0.30, "b": 0.15, "tw": 0.008, "tf": 0.012},
        },
    )

    assert polygon is not None
    assert polygon.shape == (12, 2)
    assert math.isclose(float(polygon[:, 0].max() - polygon[:, 0].min()), 0.15)


def test_custom_polygon_section_points_are_used_for_display() -> None:
    polygon = ModelView._section_polygon_points(
        "custom_polygon",
        {"points": [(0.0, 0.0), (0.20, 0.0), (0.20, 0.30), (0.0, 0.30)]},
    )

    assert polygon is not None
    assert polygon.shape == (4, 2)
    assert math.isclose(float(polygon[:, 0].max() - polygon[:, 0].min()), 0.20)
    assert math.isclose(float(polygon[:, 1].max() - polygon[:, 1].min()), 0.30)


def test_t_section_polygon_uses_web_and_flange_dimensions() -> None:
    polygon = ModelView._section_polygon_points(
        "T",
        {"bw": 0.25, "hw": 0.40, "bf": 0.80, "hf": 0.12},
    )

    assert polygon is not None
    t_section = TSection(bw=0.25, hw=0.40, bf=0.80, hf=0.12)
    assert polygon.shape == (8, 2)
    assert math.isclose(float(polygon[:, 0].max() - polygon[:, 0].min()), 0.80)
    assert math.isclose(float(polygon[:, 1].max() - polygon[:, 1].min()), t_section.h)
    assert np.isclose(polygon[:, 1].min(), -t_section.centroid_y)


def test_i_profile_polygon_uses_catalog_dimensions() -> None:
    profile = get_profile("IPE 300")
    polygon = ModelView._section_polygon_points(
        "I_profile",
        {"profile": "IPE 300"},
    )

    assert polygon is not None
    assert polygon.shape == (12, 2)
    assert math.isclose(float(polygon[:, 0].max() - polygon[:, 0].min()), profile.b)
    assert math.isclose(float(polygon[:, 1].max() - polygon[:, 1].min()), profile.h)

    half_web = profile.tw / 2.0
    assert np.isclose(np.abs(polygon[:, 0]), half_web).any()


def test_circular_tube_polygon_uses_catalog_diameter() -> None:
    profile = get_profile("CHS 114.3x5")
    polygon = ModelView._section_polygon_points(
        "I_profile",
        {"profile": "CHS 114.3x5"},
    )

    assert polygon is not None
    assert polygon.shape == (32, 2)
    assert math.isclose(float(polygon[:, 0].max() - polygon[:, 0].min()), profile.h)
    assert math.isclose(float(polygon[:, 1].max() - polygon[:, 1].min()), profile.h)


def test_circular_tube_inner_polygon_uses_catalog_thickness() -> None:
    inner = ModelView._section_inner_polygon_points(
        "I_profile",
        {"profile": "CHS 114.3x5"},
    )

    assert inner is not None
    assert inner.shape == (32, 2)
    assert np.linalg.norm(inner[0]) == pytest.approx((0.1143 - 2 * 0.005) / 2.0)


def test_hollow_section_extrusion_keeps_outer_and_inner_walls() -> None:
    outer = ModelView._section_polygon_points(
        "I_profile",
        {"profile": "CHS 114.3x5"},
    )
    inner = ModelView._section_inner_polygon_points(
        "I_profile",
        {"profile": "CHS 114.3x5"},
    )

    mesh = ModelView._build_hollow_section_extrusion_mesh(outer, inner, 2.0)

    assert mesh is not None
    assert mesh.n_cells == 128
    radii = np.linalg.norm(mesh.points[:, 1:3], axis=1)
    assert radii.max() == pytest.approx(0.1143 / 2.0)
    assert radii.min() == pytest.approx((0.1143 - 2 * 0.005) / 2.0)


def test_channel_and_angle_profiles_do_not_use_i_shape_polygon() -> None:
    channel = ModelView._section_polygon_points(
        "I_profile",
        {"profile": "UPN 200"},
    )
    angle = ModelView._section_polygon_points(
        "I_profile",
        {"profile": "L 100x75x8"},
    )

    assert channel is not None
    assert channel.shape == (8, 2)
    assert angle is not None
    assert angle.shape == (6, 2)


@pytest.mark.parametrize(
    ("section_type", "properties", "point_count"),
    [
        ("I", {"h": 0.30, "b": 0.15, "tw": 0.008, "tf": 0.012}, 12),
        ("channel", {"h": 0.20, "b": 0.08, "tw": 0.008, "tf": 0.010}, 8),
        ("angle", {"h": 0.10, "b": 0.075, "t": 0.008}, 6),
        ("pipe", {"d": 0.114, "t": 0.005}, 32),
        ("tube", {"h": 0.20, "b": 0.10, "t": 0.006}, 4),
    ],
)
def test_parametric_steel_section_polygons_are_supported(
    section_type: str,
    properties: dict,
    point_count: int,
) -> None:
    polygon = ModelView._section_polygon_points(section_type, properties)

    assert polygon is not None
    assert polygon.shape == (point_count, 2)


@pytest.mark.parametrize(
    ("section_type", "properties"),
    [
        ("pipe", {"d": 0.114, "t": 0.005}),
        ("tube", {"h": 0.20, "b": 0.10, "t": 0.006}),
    ],
)
def test_parametric_hollow_sections_have_inner_polygons(
    section_type: str,
    properties: dict,
) -> None:
    outer = ModelView._section_polygon_points(section_type, properties)
    inner = ModelView._section_inner_polygon_points(section_type, properties)

    assert outer is not None
    assert inner is not None
    assert inner.shape == outer.shape


def test_representative_parametric_sections_build_extruded_meshes() -> None:
    view = ModelView.__new__(ModelView)
    element = SimpleNamespace(orientation_vector=None, roll_angle_deg=0.0)
    node_i = SimpleNamespace(x=0.0, y=0.0, z=0.0)
    node_j = SimpleNamespace(x=2.0, y=0.0, z=0.0)

    for section_type, properties in (
        ("I", {"h": 0.30, "b": 0.15, "tw": 0.008, "tf": 0.012}),
        ("channel", {"h": 0.20, "b": 0.08, "tw": 0.008, "tf": 0.010}),
        ("angle", {"h": 0.10, "b": 0.075, "t": 0.008}),
        ("pipe", {"d": 0.114, "t": 0.005}),
        ("tube", {"h": 0.20, "b": 0.10, "t": 0.006}),
    ):
        section = SimpleNamespace(section_type=section_type, properties=properties)
        mesh = view._build_single_element_extrusion(section, element, node_i, node_j)
        assert mesh is not None, section_type
        assert mesh.n_cells > 0, section_type


def test_representative_catalog_profiles_build_extruded_meshes() -> None:
    view = ModelView.__new__(ModelView)
    element = SimpleNamespace(orientation_vector=None, roll_angle_deg=0.0)
    node_i = SimpleNamespace(x=0.0, y=0.0, z=0.0)
    node_j = SimpleNamespace(x=2.0, y=0.0, z=0.0)

    for profile_name in (
        "IPE 300",
        "HEA 200",
        "HEB 200",
        "HEM 200",
        "UPN 200",
        "UPE 200",
        "CHS 114.3x5",
        "SHS 100x5",
        "RHS 200x100x6.3",
        "L 100x10",
        "L 100x75x8",
    ):
        section = SimpleNamespace(
            section_type="I_profile",
            properties={"profile": profile_name},
        )
        mesh = view._build_single_element_extrusion(section, element, node_i, node_j)
        assert mesh is not None, profile_name
        assert mesh.n_cells > 0, profile_name


def test_extruded_section_frame_uses_element_roll_angle() -> None:
    frame = ModelView._local_frame_from_element(
        SimpleNamespace(orientation_vector=None, roll_angle_deg=90.0),
        SimpleNamespace(x=0.0, y=0.0, z=0.0),
        SimpleNamespace(x=5.0, y=0.0, z=0.0),
    )

    assert frame is not None
    x_axis, y_axis, z_axis, length = frame
    assert length == pytest.approx(5.0)
    assert x_axis == pytest.approx((1.0, 0.0, 0.0))
    assert y_axis == pytest.approx((0.0, 0.0, 1.0))
    assert z_axis == pytest.approx((0.0, -1.0, 0.0))


def test_i_profile_guide_points_use_web_flange_corners() -> None:
    profile = get_profile("IPE 300")
    guides = ModelView._section_guide_points(
        "I_profile",
        {"profile": "IPE 300"},
    )

    assert guides.shape == (4, 2)
    assert np.allclose(np.unique(np.abs(guides[:, 0])), [profile.tw / 2.0])
    assert np.allclose(np.unique(np.abs(guides[:, 1])), [profile.h / 2.0 - profile.tf])


def test_i_profile_fillet_guides_are_offset_from_web_knees() -> None:
    profile = get_profile("IPE 300")
    guides = ModelView._section_fillet_guide_points(
        "I_profile",
        {"profile": "IPE 300"},
    )

    assert guides.shape == (4, 2)
    assert np.all(np.abs(guides[:, 0]) > profile.tw / 2.0)
    assert np.all(np.abs(guides[:, 1]) < (profile.h / 2.0 - profile.tf))


def test_non_i_profile_has_no_section_guides() -> None:
    guides = ModelView._section_guide_points(
        "rectangular",
        {"b": 0.30, "h": 0.50},
    )

    assert guides.shape == (0, 2)

    fillet_guides = ModelView._section_fillet_guide_points(
        "rectangular",
        {"b": 0.30, "h": 0.50},
    )

    assert fillet_guides.shape == (0, 2)


def test_hollow_catalog_profiles_have_no_i_profile_guides() -> None:
    guides = ModelView._section_guide_points(
        "I_profile",
        {"profile": "RHS 200x100x6.3"},
    )
    fillet_guides = ModelView._section_fillet_guide_points(
        "I_profile",
        {"profile": "RHS 200x100x6.3"},
    )

    assert guides.shape == (0, 2)
    assert fillet_guides.shape == (0, 2)


def test_section_rgb_scalars_match_merged_cell_count() -> None:
    mesh = SimpleNamespace(n_cells=5, cell_data={})
    colors = [
        np.tile(np.array([10, 20, 30], dtype=np.uint8), (2, 1)),
        np.tile(np.array([40, 50, 60], dtype=np.uint8), (1, 1)),
    ]

    ModelView._ensure_section_rgb_scalars(mesh, colors)

    assert mesh.cell_data["section_rgb"].shape == (5, 3)


def _line_project_with_two_sections() -> ProjectModel:
    project = ProjectModel()
    material = project.add_material("Acier S355", "steel", "S355")
    ipe = get_profile("IPE 300")
    chs = get_profile("CHS 114.3x5")
    project.add_section(
        "IPE 300",
        "I_profile",
        material.tag,
        properties={"profile": ipe.name},
        area=ipe.area,
        inertia_y=ipe.inertia_y,
        inertia_z=ipe.inertia_z,
    )
    project.add_section(
        "CHS 114.3x5",
        "I_profile",
        material.tag,
        properties={"profile": chs.name},
        area=chs.area,
        inertia_y=chs.inertia_y,
        inertia_z=chs.inertia_z,
    )
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(1.0, 0.0, 0.0)
    project.add_node(2.0, 0.0, 0.0)
    project.add_element(1, 2, 1)
    project.add_element(2, 3, 2)
    return project


def test_line_elements_are_colored_by_section() -> None:
    project = _line_project_with_two_sections()
    view = ModelView.__new__(ModelView)
    view._tag_to_idx = {1: 0, 2: 1, 3: 2}
    view._elem_tags = []
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
        ],
        dtype=float,
    )

    mesh = view._build_line_elements_mesh(project, points)

    assert mesh is not None
    colors = np.unique(mesh.cell_data["section_rgb"], axis=0)
    assert colors.shape == (2, 3)
    assert np.array_equal(
        mesh.cell_data["section_rgb"][0],
        ModelView._hex_to_uint8_rgb(ModelView._section_color_for_tag(1)),
    )
    assert np.array_equal(
        mesh.cell_data["section_rgb"][1],
        ModelView._hex_to_uint8_rgb(ModelView._section_color_for_tag(2)),
    )


def test_extruded_elements_are_colored_by_section() -> None:
    project = _line_project_with_two_sections()
    view = ModelView.__new__(ModelView)
    view._active_plane = None
    view._active_plane_value = None
    view._extruded_mesh_cache = {}
    view._extruded_cache_max_entries = 4
    view._elem_tags = []

    mesh = view._build_extruded_elements_mesh(project)

    assert mesh is not None
    colors = np.unique(mesh.cell_data["section_rgb"], axis=0)
    assert colors.shape == (2, 3)
