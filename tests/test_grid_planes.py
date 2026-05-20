import pytest

from core.model_data import Grid3DData

pytest.importorskip("pyvista")

from gui.widgets.model_view import ModelView


def test_plane_values_and_labels():
    grid = Grid3DData(
        x_items=[("A", 1.0), ("B", 6.0), ("C", 11.0)],
        y_items=[("1", 2.0), ("2", 6.0)],
        z_items=[("N0", 3.0), ("N1", 5.5), ("N2", 8.0), ("N3", 10.5)],
    )

    assert ModelView.plane_axis_label("XY") == "Z"
    assert ModelView.plane_axis_label("XZ") == "Y"
    assert ModelView.plane_axis_label("YZ") == "X"

    assert ModelView.plane_values(grid, "XY") == [3.0, 5.5, 8.0, 10.5]
    assert ModelView.plane_values(grid, "XZ") == [2.0, 6.0]
    assert ModelView.plane_values(grid, "YZ") == [1.0, 6.0, 11.0]


def test_grid_annotations_include_axis_bubbles_in_xy_view():
    grid = Grid3DData(
        x_items=[("A", 0.0), ("B", 5.0)],
        y_items=[("1", 0.0), ("2", 4.0), ("3", 8.0)],
        z_items=[("N0", 0.0), ("N1", 3.0)],
    )

    ext_points, ext_lines, label_points, label_texts = ModelView._build_grid_annotations(
        grid,
        plane="XY",
        value=0.0,
    )

    assert ext_points.shape == (10, 3)
    assert len(ext_lines) == 15
    assert label_points.shape == (5, 3)
    assert label_texts == ["A", "B", "1", "2", "3"]
    assert label_points[0, 1] > 8.0
    assert label_points[-1, 0] > 5.0


def test_grid_annotations_hide_levels_in_3d_view():
    grid = Grid3DData(
        x_items=[("A", 0.0), ("B", 5.0)],
        y_items=[("1", 0.0), ("2", 4.0)],
        z_items=[("N0", 0.0), ("R+1", 3.2), ("R+2", 6.4)],
    )

    _ext_points, ext_lines, label_points, label_texts = ModelView._build_grid_annotations(
        grid,
        plane=None,
        value=None,
    )

    assert len(ext_lines) == 12
    assert label_points.shape == (4, 3)
    assert label_texts == ["A", "B", "1", "2"]
    assert label_points[0, 1] > 4.0
    assert label_points[-1, 0] > 5.0
