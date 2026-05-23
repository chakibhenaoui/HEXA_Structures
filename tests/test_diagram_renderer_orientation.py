"""Helpers for test diagram renderer orientation."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("matplotlib")
from matplotlib.figure import Figure

from core.section_force_convention import (
    bending_reference_side_2d as _bending_reference_side_2d,
    canonical_component_sign as _canonical_component_sign,
    canonical_element_local_axes as _canonical_element_local_axes,
    canonicalize_component_samples as _canonicalize_component_samples,
    canonicalize_projected_samples as _canonicalize_projected_samples,
    choose_file_diagram_side as _choose_file_diagram_side,
    component_display_sign as _component_display_sign,
    diagram_convention_for_element as _diagram_convention_for_element,
    diagram_direction_2d as _diagram_direction_2d,
    diagram_direction_for_file as _diagram_direction_for_file,
    display_component_values as _display_component_values,
    element_local_axes as _element_local_axes,
    resolve_display_samples,
    sample_component_for_display as _sample_component_for_display,
)
from gui.widgets.diagram_renderer import (
    _DIAGRAM_NEGATIVE_COLOR,
    _DIAGRAM_POSITIVE_COLOR,
    _find_label_position,
    _label_candidate_indices,
    _place_diagram_labels,
    _signed_diagram_segment_polygons,
    _value_color,
)


def _raw_values_for_reversed_member(
    ecrd_3d: np.ndarray,
    component: str,
    canonical_values: np.ndarray,
) -> np.ndarray:
    actual_axes = _element_local_axes(ecrd_3d)
    canonical_axes, reverse = _canonical_element_local_axes(ecrd_3d)
    assert reverse is True
    sign = _canonical_component_sign(component, actual_axes, canonical_axes)
    return (canonical_values / sign)[::-1]


def test_keep_orientation_when_already_canonical() -> None:
    p1 = np.array([0.0, 0.0])
    p2 = np.array([5.0, 0.0])
    xl = np.array([0.0, 2.5, 5.0])
    ss = np.array([1.0, 2.0, 3.0])

    rp1, rp2, rxl, rss = _canonicalize_projected_samples(
        p1, p2, xl, ss, 5.0, "My",
    )

    assert np.allclose(rp1, p1)
    assert np.allclose(rp2, p2)
    assert np.allclose(rxl, xl)
    assert np.allclose(rss, ss)


def test_reverse_my_when_member_direction_is_inverted() -> None:
    p1 = np.array([5.0, 3.0])
    p2 = np.array([5.0, 0.0])
    xl = np.array([0.0, 1.5, 3.0])
    ss = np.array([-5.0, -3.0, 2.0])

    rp1, rp2, rxl, rss = _canonicalize_projected_samples(
        p1, p2, xl, ss, 3.0, "My",
    )

    assert np.allclose(rp1, p2)
    assert np.allclose(rp2, p1)
    assert np.allclose(rxl, xl)
    assert np.allclose(rss, np.array([-2.0, 3.0, 5.0]))


def test_reverse_vz_keeps_sign_when_member_direction_is_inverted() -> None:
    p1 = np.array([5.0, 3.0])
    p2 = np.array([5.0, 0.0])
    xl = np.array([0.0, 1.5, 3.0])
    ss = np.array([10.0, 0.0, -10.0])

    _, _, rxl, rss = _canonicalize_projected_samples(
        p1, p2, xl, ss, 3.0, "Vz",
    )

    assert np.allclose(rxl, xl)
    assert np.allclose(rss, np.array([-10.0, 0.0, 10.0]))


def test_reverse_n_changes_sign_when_member_direction_is_inverted() -> None:
    p1 = np.array([0.0, 4.0])
    p2 = np.array([0.0, 0.0])
    xl = np.array([0.0, 2.0, 4.0])
    ss = np.array([-100.0, -100.0, -100.0])

    _, _, rxl, rss = _canonicalize_projected_samples(
        p1, p2, xl, ss, 4.0, "N",
    )

    assert np.allclose(rxl, xl)
    assert np.allclose(rss, np.array([100.0, 100.0, 100.0]))


def test_reverse_t_changes_sign_when_member_direction_is_inverted() -> None:
    p1 = np.array([4.0, 0.0])
    p2 = np.array([0.0, 0.0])
    xl = np.array([0.0, 2.0, 4.0])
    ss = np.array([4.0, 4.0, 4.0])

    _, _, rxl, rss = _canonicalize_projected_samples(
        p1, p2, xl, ss, 4.0, "T",
    )

    assert np.allclose(rxl, xl)
    assert np.allclose(rss, np.array([-4.0, -4.0, -4.0]))


def test_display_component_values_does_not_hide_sign_conventions() -> None:
    values = np.array([-10.0, 0.0, 8.0])

    result = _display_component_values("My", values)

    assert np.allclose(result, values)


def test_my_uses_local_z_for_internal_diagram_direction() -> None:
    direction = _diagram_direction_2d(
        "My",
        "XZ",
        local_y=np.array([0.0, 1.0, 0.0]),
        local_z=np.array([0.0, 0.0, 1.0]),
        outward_normal_2d=np.array([0.0, 1.0]),
        tangent_2d=np.array([1.0, 0.0]),
    )

    assert np.allclose(direction, np.array([0.0, -1.0]))


def test_my_column_like_member_uses_outward_side() -> None:
    direction = _diagram_direction_2d(
        "My",
        "XZ",
        local_y=np.array([0.0, -1.0, 0.0]),
        local_z=np.array([1.0, 0.0, 0.0]),
        outward_normal_2d=np.array([1.0, 0.0]),
        tangent_2d=np.array([0.0, 1.0]),
    )

    assert np.allclose(direction, np.array([1.0, 0.0]))


def test_my_display_sign_follows_local_y_against_plane_normal() -> None:
    beam_sign = _component_display_sign(
        "My",
        "XZ",
        local_x=np.array([1.0, 0.0, 0.0]),
        local_y=np.array([0.0, 1.0, 0.0]),
        local_z=np.array([0.0, 0.0, 1.0]),
        tangent_2d=np.array([1.0, 0.0]),
        outward_normal_2d=np.array([0.0, 1.0]),
    )
    column_sign = _component_display_sign(
        "My",
        "XZ",
        local_x=np.array([0.0, 0.0, 1.0]),
        local_y=np.array([0.0, -1.0, 0.0]),
        local_z=np.array([1.0, 0.0, 0.0]),
        tangent_2d=np.array([0.0, 1.0]),
        outward_normal_2d=np.array([1.0, 0.0]),
    )

    assert beam_sign == -1.0
    assert column_sign == 1.0


def test_my_display_sign_for_yz_beam_follows_local_y_against_view_normal() -> None:
    beam_sign = _component_display_sign(
        "My",
        "YZ",
        local_x=np.array([0.0, 1.0, 0.0]),
        local_y=np.array([-1.0, 0.0, 0.0]),
        local_z=np.array([0.0, 0.0, 1.0]),
        tangent_2d=np.array([1.0, 0.0]),
        outward_normal_2d=np.array([0.0, 1.0]),
    )

    assert beam_sign == -1.0


def test_yz_beam_my_sagging_display_matches_xz_beam() -> None:
    x = np.array([0.0, 2.5, 5.0], dtype=float)
    raw_values = np.array([2.0, -1.0, 2.0], dtype=float)

    xz = resolve_display_samples(
        ecrd_3d=np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]], dtype=float),
        p1=np.array([0.0, 0.0], dtype=float),
        p2=np.array([5.0, 0.0], dtype=float),
        x=x,
        values=raw_values,
        component="My",
        plane="XZ",
        file_center=np.array([2.5, 0.0], dtype=float),
        apply_component_axis_sign=False,
    )
    yz = resolve_display_samples(
        ecrd_3d=np.array([[0.0, 0.0, 0.0], [0.0, 5.0, 0.0]], dtype=float),
        p1=np.array([0.0, 0.0], dtype=float),
        p2=np.array([5.0, 0.0], dtype=float),
        x=x,
        values=raw_values,
        component="My",
        plane="YZ",
        file_center=np.array([2.5, 0.0], dtype=float),
        apply_component_axis_sign=False,
    )

    assert xz is not None
    assert yz is not None
    assert np.allclose(xz.values, np.array([-2.0, 1.0, -2.0]))
    assert np.allclose(yz.values, xz.values)


def test_yz_file_my_samples_mz_for_vertical_members() -> None:
    ecrd_3d = np.array(
        [[0.0, 0.0, 0.0], [0.0, 0.0, 3.0]],
        dtype=float,
    )

    assert _sample_component_for_display("My", "YZ", ecrd_3d) == "Mz"


def test_yz_file_my_keeps_my_for_y_beams() -> None:
    ecrd_3d = np.array(
        [[0.0, 0.0, 3.0], [0.0, 5.0, 3.0]],
        dtype=float,
    )

    assert _sample_component_for_display("My", "YZ", ecrd_3d) == "My"


def test_xz_file_my_keeps_my_for_vertical_members() -> None:
    ecrd_3d = np.array(
        [[0.0, 0.0, 0.0], [0.0, 0.0, 3.0]],
        dtype=float,
    )

    assert _sample_component_for_display("My", "XZ", ecrd_3d) == "My"


def test_canonical_element_local_axes_reverse_descending_column() -> None:
    axes, reverse = _canonical_element_local_axes(
        np.array(
            [
                [0.0, 0.0, 3.0],
                [0.0, 0.0, 0.0],
            ],
            dtype=float,
        )
    )

    local_x, local_y, local_z = axes
    assert reverse is True
    assert np.allclose(local_x, np.array([0.0, 0.0, 1.0]))
    assert np.allclose(local_z, np.array([1.0, 0.0, 0.0]))


def test_canonicalize_component_samples_flips_my_for_reversed_member() -> None:
    ecrd_3d = np.array(
        [
            [5.0, 0.0, 3.0],
            [5.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    p1 = np.array([5.0, 3.0], dtype=float)
    p2 = np.array([5.0, 0.0], dtype=float)
    xl = np.array([0.0, 1.5, 3.0], dtype=float)
    ss = np.array([-5.0, -3.0, 2.0], dtype=float)

    rp1, rp2, rxl, rss, _axes = _canonicalize_component_samples(
        ecrd_3d,
        p1,
        p2,
        xl,
        ss,
        "My",
    )

    assert np.allclose(rp1, np.array([5.0, 0.0]))
    assert np.allclose(rp2, np.array([5.0, 3.0]))
    assert np.allclose(rxl, xl)
    assert np.allclose(rss, np.array([-2.0, 3.0, 5.0]))


def test_canonicalize_component_samples_is_stable_when_member_is_drawn_backward() -> None:
    forward_coords = np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]], dtype=float)
    backward_coords = np.array([[5.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=float)
    forward_x = np.array([0.0, 2.5, 5.0], dtype=float)
    backward_x = np.array([0.0, 2.5, 5.0], dtype=float)
    forward_values = np.array([1.0, 2.0, 3.0], dtype=float)
    backward_values = np.array([-3.0, -2.0, -1.0], dtype=float)

    fp1, fp2, fxl, fvalues, _ = _canonicalize_component_samples(
        forward_coords,
        np.array([0.0, 0.0], dtype=float),
        np.array([5.0, 0.0], dtype=float),
        forward_x,
        forward_values,
        "My",
    )
    bp1, bp2, bxl, bvalues, _ = _canonicalize_component_samples(
        backward_coords,
        np.array([5.0, 0.0], dtype=float),
        np.array([0.0, 0.0], dtype=float),
        backward_x,
        backward_values,
        "My",
    )

    assert np.allclose(bp1, fp1)
    assert np.allclose(bp2, fp2)
    assert np.allclose(bxl, fxl)
    assert np.allclose(bvalues, fvalues)


def test_resolve_display_samples_uses_canonical_side_after_reversing_member() -> None:
    forward = resolve_display_samples(
        ecrd_3d=np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 3.0]], dtype=float),
        p1=np.array([0.0, 0.0], dtype=float),
        p2=np.array([0.0, 3.0], dtype=float),
        x=np.array([0.0, 1.5, 3.0], dtype=float),
        values=np.array([1.0, 2.0, 3.0], dtype=float),
        component="My",
        plane="XZ",
        file_center=np.array([2.0, 1.5], dtype=float),
    )
    backward = resolve_display_samples(
        ecrd_3d=np.array([[0.0, 0.0, 3.0], [0.0, 0.0, 0.0]], dtype=float),
        p1=np.array([0.0, 3.0], dtype=float),
        p2=np.array([0.0, 0.0], dtype=float),
        x=np.array([0.0, 1.5, 3.0], dtype=float),
        values=np.array([-3.0, -2.0, -1.0], dtype=float),
        component="My",
        plane="XZ",
        file_center=np.array([2.0, 1.5], dtype=float),
    )

    assert forward is not None
    assert backward is not None
    assert np.allclose(backward.p1, forward.p1)
    assert np.allclose(backward.p2, forward.p2)
    assert np.allclose(backward.x, forward.x)
    assert np.allclose(backward.values, forward.values)
    assert np.allclose(backward.direction_2d, forward.direction_2d)


@pytest.mark.parametrize("component", ["N", "Vy", "Vz", "T", "My", "Mz"])
@pytest.mark.parametrize(
    ("plane", "ecrd_3d", "p1", "p2", "file_center", "file_boundary_sign"),
    [
        (
            "XZ",
            np.array([[0.0, 0.0, 3.0], [5.0, 0.0, 3.0]], dtype=float),
            np.array([0.0, 3.0], dtype=float),
            np.array([5.0, 3.0], dtype=float),
            np.array([2.5, 1.5], dtype=float),
            1.0,
        ),
        (
            "YZ",
            np.array([[0.0, 0.0, 3.0], [0.0, 5.0, 3.0]], dtype=float),
            np.array([0.0, 3.0], dtype=float),
            np.array([5.0, 3.0], dtype=float),
            np.array([2.5, 1.5], dtype=float),
            1.0,
        ),
        (
            "XZ",
            np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 3.0]], dtype=float),
            np.array([0.0, 0.0], dtype=float),
            np.array([0.0, 3.0], dtype=float),
            np.array([2.5, 1.5], dtype=float),
            1.0,
        ),
        (
            "YZ",
            np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 3.0]], dtype=float),
            np.array([0.0, 0.0], dtype=float),
            np.array([0.0, 3.0], dtype=float),
            np.array([2.5, 1.5], dtype=float),
            -1.0,
        ),
        (
            "YZ",
            np.array([[10.0, 5.0, 0.0], [10.0, 5.0, 3.0]], dtype=float),
            np.array([5.0, 0.0], dtype=float),
            np.array([5.0, 3.0], dtype=float),
            np.array([2.5, 1.5], dtype=float),
            1.0,
        ),
    ],
)
def test_resolve_display_samples_is_invariant_to_member_draw_order(
    component: str,
    plane: str,
    ecrd_3d: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    file_center: np.ndarray,
    file_boundary_sign: float,
) -> None:
    length = float(np.linalg.norm(ecrd_3d[1] - ecrd_3d[0]))
    x = np.array([0.0, 0.5 * length, length], dtype=float)
    canonical_values = np.array([1.0, 2.0, 3.0], dtype=float)
    reversed_ecrd = ecrd_3d[::-1].copy()
    reversed_values = _raw_values_for_reversed_member(
        reversed_ecrd,
        component,
        canonical_values,
    )

    forward = resolve_display_samples(
        ecrd_3d=ecrd_3d,
        p1=p1,
        p2=p2,
        x=x,
        values=canonical_values,
        component=component,
        plane=plane,
        file_center=file_center,
        file_boundary_sign=file_boundary_sign,
    )
    backward = resolve_display_samples(
        ecrd_3d=reversed_ecrd,
        p1=p2,
        p2=p1,
        x=x,
        values=reversed_values,
        component=component,
        plane=plane,
        file_center=file_center,
        file_boundary_sign=file_boundary_sign,
    )

    assert forward is not None
    assert backward is not None
    assert np.allclose(backward.p1, forward.p1)
    assert np.allclose(backward.p2, forward.p2)
    assert np.allclose(backward.x, forward.x)
    assert np.allclose(backward.values, forward.values)
    assert np.allclose(backward.direction_2d, forward.direction_2d)


def test_file_side_points_columns_outward_from_frame_center() -> None:
    left = _choose_file_diagram_side(
        np.array([0.0, 0.0]),
        np.array([0.0, 3.0]),
        file_center=np.array([5.0, 2.0]),
        tol=1e-9,
    )
    right = _choose_file_diagram_side(
        np.array([10.0, 0.0]),
        np.array([10.0, 3.0]),
        file_center=np.array([5.0, 2.0]),
        tol=1e-9,
    )

    assert np.allclose(left, np.array([-1.0, 0.0]))
    assert np.allclose(right, np.array([1.0, 0.0]))


def test_file_side_points_beams_upward() -> None:
    side = _choose_file_diagram_side(
        np.array([0.0, 3.0]),
        np.array([5.0, 3.0]),
        file_center=np.array([2.5, 1.5]),
        tol=1e-9,
    )

    assert np.allclose(side, np.array([0.0, 1.0]))


def test_my_direction_for_file_uses_stable_file_side() -> None:
    direction = _diagram_direction_for_file(
        "My",
        "XZ",
        local_y=np.array([0.0, -1.0, 0.0]),
        local_z=np.array([1.0, 0.0, 0.0]),
        file_side_2d=np.array([-1.0, 0.0]),
        tangent_2d=np.array([0.0, 1.0]),
    )

    assert np.allclose(direction, np.array([-1.0, 0.0]))


def test_my_reference_side_is_bottom_for_beams() -> None:
    direction = _bending_reference_side_2d(
        tangent_2d=np.array([1.0, 0.0]),
        file_side_2d=np.array([0.0, 1.0]),
    )

    assert np.allclose(direction, np.array([0.0, -1.0]))


def test_diagram_convention_for_my_beam_is_bottom_tension_positive() -> None:
    convention = _diagram_convention_for_element(
        "My",
        "XZ",
        local_x=np.array([1.0, 0.0, 0.0]),
        local_y=np.array([0.0, 1.0, 0.0]),
        local_z=np.array([0.0, 0.0, 1.0]),
        tangent_2d=np.array([1.0, 0.0]),
        file_side_2d=np.array([0.0, 1.0]),
    )

    assert convention.sign == -1.0
    assert np.allclose(convention.direction_2d, np.array([0.0, -1.0]))


def test_diagram_convention_for_my_yz_beam_is_bottom_tension_positive() -> None:
    convention = _diagram_convention_for_element(
        "My",
        "YZ",
        local_x=np.array([0.0, 1.0, 0.0]),
        local_y=np.array([-1.0, 0.0, 0.0]),
        local_z=np.array([0.0, 0.0, 1.0]),
        tangent_2d=np.array([1.0, 0.0]),
        file_side_2d=np.array([0.0, 1.0]),
    )

    assert convention.sign == -1.0
    assert np.allclose(convention.direction_2d, np.array([0.0, -1.0]))


def test_diagram_convention_for_my_column_is_outward_tension_positive() -> None:
    convention = _diagram_convention_for_element(
        "My",
        "XZ",
        local_x=np.array([0.0, 0.0, 1.0]),
        local_y=np.array([0.0, -1.0, 0.0]),
        local_z=np.array([1.0, 0.0, 0.0]),
        tangent_2d=np.array([0.0, 1.0]),
        file_side_2d=np.array([-1.0, 0.0]),
    )

    assert convention.sign == -1.0
    assert np.allclose(convention.direction_2d, np.array([-1.0, 0.0]))


def test_diagram_convention_for_my_yz_column_depends_on_facade_side() -> None:
    convention_min_x = _diagram_convention_for_element(
        "My",
        "YZ",
        local_x=np.array([0.0, 0.0, 1.0]),
        local_y=np.array([0.0, -1.0, 0.0]),
        local_z=np.array([1.0, 0.0, 0.0]),
        tangent_2d=np.array([0.0, 1.0]),
        file_side_2d=np.array([-1.0, 0.0]),
        file_boundary_sign=-1.0,
    )
    convention_max_x = _diagram_convention_for_element(
        "My",
        "YZ",
        local_x=np.array([0.0, 0.0, 1.0]),
        local_y=np.array([0.0, -1.0, 0.0]),
        local_z=np.array([1.0, 0.0, 0.0]),
        tangent_2d=np.array([0.0, 1.0]),
        file_side_2d=np.array([1.0, 0.0]),
        file_boundary_sign=1.0,
    )

    assert convention_min_x.sign == -1.0
    assert convention_max_x.sign == 1.0


def test_signed_diagram_segment_polygons_keeps_single_quad_when_sign_is_constant() -> None:
    polygons = _signed_diagram_segment_polygons(
        np.array([0.0, 0.0]),
        np.array([1.0, 0.0]),
        np.array([0.0, 2.0]),
        np.array([1.0, 3.0]),
        2.0,
        3.0,
    )

    assert len(polygons) == 1
    polygon, ref_value = polygons[0]
    assert ref_value == 3.0
    assert polygon.shape == (4, 2)


def test_signed_diagram_segment_polygons_splits_at_zero_crossing() -> None:
    polygons = _signed_diagram_segment_polygons(
        np.array([0.0, 0.0]),
        np.array([4.0, 0.0]),
        np.array([0.0, 2.0]),
        np.array([4.0, -2.0]),
        2.0,
        -2.0,
    )

    assert len(polygons) == 2
    first_polygon, first_value = polygons[0]
    second_polygon, second_value = polygons[1]
    assert first_value == 2.0
    assert second_value == -2.0
    assert np.allclose(first_polygon[1], np.array([2.0, 0.0]))
    assert np.allclose(second_polygon[0], np.array([2.0, 0.0]))


def test_label_candidate_indices_keeps_original_extreme_and_endpoint_selection() -> None:
    values = np.array([2.0, 1.0, 3.0, -4.0, 2.5], dtype=float)

    indices = _label_candidate_indices(values)

    assert 0 in indices
    assert len(values) - 1 in indices
    assert int(np.argmax(values)) in indices
    assert int(np.argmin(values)) in indices


def test_diagram_positive_color_is_green_and_negative_is_red() -> None:
    assert _value_color(1.0) == _DIAGRAM_POSITIVE_COLOR
    assert _value_color(-1.0) == _DIAGRAM_NEGATIVE_COLOR
    assert _DIAGRAM_POSITIVE_COLOR == "#15803d"
    assert _DIAGRAM_NEGATIVE_COLOR == "#d62828"


def test_place_diagram_labels_uses_same_style_for_positive_and_negative_values() -> None:
    fig = Figure()
    ax = fig.add_subplot(111)

    _place_diagram_labels(
        ax,
        points_2d=np.array([[0.0, 0.0], [3.0, 0.0], [6.0, 0.0]]),
        values=np.array([-5.0, 1.0, 4.0]),
        diagram_dir=np.array([0.0, 1.0]),
        label_offset=0.5,
        placed_positions=[],
    )

    labels = {text.get_text(): text for text in ax.texts}
    assert labels["-5"].get_fontweight() == "normal"
    assert labels["+4"].get_fontweight() == "normal"
    assert labels["-5"].get_color() == _DIAGRAM_NEGATIVE_COLOR
    assert labels["+4"].get_color() == _DIAGRAM_POSITIVE_COLOR
    assert labels["-5"].get_bbox_patch().get_linewidth() == 0.8
    assert labels["+4"].get_bbox_patch().get_linewidth() == 0.8


def test_find_label_position_keeps_default_when_space_is_available() -> None:
    pos, moved = _find_label_position(
        anchor=np.array([0.0, 0.0]),
        diagram_dir=np.array([0.0, 1.0]),
        label_offset=1.0,
        placed_positions=[],
        min_distance=1.5,
    )

    assert moved is False
    assert np.allclose(pos, np.array([0.0, 1.0]))


def test_find_label_position_pushes_label_outward_when_overlapping() -> None:
    pos, moved = _find_label_position(
        anchor=np.array([0.0, 0.0]),
        diagram_dir=np.array([0.0, 1.0]),
        label_offset=1.0,
        placed_positions=[np.array([0.0, 1.0])],
        min_distance=1.5,
    )

    assert moved is True
    assert pos[1] > 1.0


def test_find_label_position_can_skip_when_no_free_space() -> None:
    placed = [
        np.array([lateral, radial])
        for radial in (1.0, 1.7, 2.4, 3.1, 3.8)
        for lateral in (0.0, 0.6, -0.6, 1.2, -1.2)
    ]

    pos = _find_label_position(
        anchor=np.array([0.0, 0.0]),
        diagram_dir=np.array([0.0, 1.0]),
        label_offset=1.0,
        placed_positions=placed,
        min_distance=0.2,
    )

    assert pos is None
