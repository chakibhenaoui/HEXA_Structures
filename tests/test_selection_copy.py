import pytest

from core.selection_copy import (
    build_copy_instance_points,
    selection_anchor_point,
    selection_reference_point,
)


def test_selection_reference_point_returns_centroid() -> None:
    point = selection_reference_point(
        [
            (0.0, 0.0, 0.0),
            (6.0, 0.0, 0.0),
            (0.0, 3.0, 9.0),
        ]
    )

    assert point == pytest.approx((2.0, 1.0, 3.0))


def test_build_copy_instance_points_repeats_delta_for_each_copy() -> None:
    instances = build_copy_instance_points(
        {
            1: (0.0, 0.0, 0.0),
            2: (2.0, 0.0, 0.0),
        },
        dx=5.0,
        dy=-1.0,
        dz=2.5,
        copy_count=3,
    )

    assert len(instances) == 3
    assert instances[0][1] == pytest.approx((5.0, -1.0, 2.5))
    assert instances[0][2] == pytest.approx((7.0, -1.0, 2.5))
    assert instances[2][1] == pytest.approx((15.0, -3.0, 7.5))
    assert instances[2][2] == pytest.approx((17.0, -3.0, 7.5))


def test_build_copy_instance_points_requires_positive_copy_count() -> None:
    with pytest.raises(ValueError):
        build_copy_instance_points(
            {1: (0.0, 0.0, 0.0)},
            dx=1.0,
            dy=0.0,
            dz=0.0,
            copy_count=0,
        )


def test_selection_anchor_point_prefers_bottom_then_left_then_front() -> None:
    point = selection_anchor_point(
        [
            (5.0, 2.0, 3.0),
            (2.0, 4.0, 0.0),
            (2.0, 1.0, 0.0),
            (4.0, 0.0, 0.0),
        ]
    )

    assert point == pytest.approx((2.0, 1.0, 0.0))
