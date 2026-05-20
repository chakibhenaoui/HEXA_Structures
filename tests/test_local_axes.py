import math

import pytest

from core.local_axes import LocalAxes3D, local_axes_from_nodes, opensees_vecxz_from_axes


def _dot(a, b) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _cross(a, b) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v) -> float:
    return math.sqrt(_dot(v, v))


def _assert_vec_close(actual, expected, abs_tol: float = 1e-12) -> None:
    assert actual == pytest.approx(expected, abs=abs_tol)


def _assert_orthonormal_direct(axes: LocalAxes3D) -> None:
    assert _norm(axes.x) == pytest.approx(1.0, abs=1e-12)
    assert _norm(axes.y) == pytest.approx(1.0, abs=1e-12)
    assert _norm(axes.z) == pytest.approx(1.0, abs=1e-12)
    assert _dot(axes.x, axes.y) == pytest.approx(0.0, abs=1e-12)
    assert _dot(axes.y, axes.z) == pytest.approx(0.0, abs=1e-12)
    assert _dot(axes.z, axes.x) == pytest.approx(0.0, abs=1e-12)
    _assert_vec_close(_cross(axes.x, axes.y), axes.z)


def test_horizontal_x_member_uses_global_z_reference() -> None:
    axes = local_axes_from_nodes((0.0, 0.0, 0.0), (5.0, 0.0, 0.0))

    _assert_vec_close(axes.x, (1.0, 0.0, 0.0))
    _assert_vec_close(axes.z, (0.0, 0.0, 1.0))
    _assert_orthonormal_direct(axes)


def test_horizontal_y_member_uses_global_z_reference() -> None:
    axes = local_axes_from_nodes((0.0, 0.0, 0.0), (0.0, 5.0, 0.0))

    _assert_vec_close(axes.x, (0.0, 1.0, 0.0))
    _assert_vec_close(axes.z, (0.0, 0.0, 1.0))
    _assert_orthonormal_direct(axes)


def test_vertical_z_member_uses_stable_fallback_reference() -> None:
    axes = local_axes_from_nodes((0.0, 0.0, 0.0), (0.0, 0.0, 3.0))

    _assert_vec_close(axes.x, (0.0, 0.0, 1.0))
    _assert_vec_close(axes.z, (1.0, 0.0, 0.0))
    assert abs(_dot(axes.x, (0.0, 0.0, 1.0))) == pytest.approx(1.0, abs=1e-12)
    assert _dot(axes.x, axes.z) == pytest.approx(0.0, abs=1e-12)
    _assert_orthonormal_direct(axes)


def test_inclined_3d_member_builds_orthonormal_direct_frame() -> None:
    axes = local_axes_from_nodes((0.0, 0.0, 0.0), (3.0, 4.0, 5.0))

    _assert_orthonormal_direct(axes)


def test_nearly_parallel_user_reference_falls_back_without_nan() -> None:
    axes = local_axes_from_nodes(
        (0.0, 0.0, 0.0),
        (5.0, 0.0, 0.0),
        reference_vector=(1.0, 1e-14, 0.0),
    )

    for axis in (axes.x, axes.y, axes.z):
        assert all(math.isfinite(value) for value in axis)
    _assert_vec_close(axes.z, (0.0, 0.0, 1.0))
    _assert_orthonormal_direct(axes)


def test_zero_length_member_raises_explicit_error() -> None:
    with pytest.raises(ValueError, match="noeuds.*confondus"):
        local_axes_from_nodes((1.0, 2.0, 3.0), (1.0, 2.0, 3.0))


def test_zero_user_reference_raises_explicit_error() -> None:
    with pytest.raises(ValueError, match="reference.*nul"):
        local_axes_from_nodes(
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            reference_vector=(0.0, 0.0, 0.0),
        )


def test_roll_angle_rotates_y_and_z_about_local_x() -> None:
    axes = local_axes_from_nodes(
        (0.0, 0.0, 0.0),
        (5.0, 0.0, 0.0),
        roll_angle_deg=90.0,
    )

    _assert_vec_close(axes.x, (1.0, 0.0, 0.0))
    _assert_vec_close(axes.y, (0.0, 0.0, 1.0))
    _assert_vec_close(axes.z, (0.0, -1.0, 0.0))
    _assert_orthonormal_direct(axes)


def test_opensees_vecxz_is_local_z_axis() -> None:
    axes = local_axes_from_nodes((0.0, 0.0, 0.0), (0.0, 0.0, 3.0))

    assert opensees_vecxz_from_axes(axes) == axes.z
