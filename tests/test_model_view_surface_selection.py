from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF

from core.model_data import ProjectModel

pytest.importorskip("pyvista")
pytest.importorskip("pyvistaqt")

from gui.widgets.model_view import ModelView


def _surface_project() -> ProjectModel:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(2.0, 0.0, 0.0)
    project.add_node(2.0, 2.0, 0.0)
    project.add_node(0.0, 2.0, 0.0)
    project.add_node(3.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 2.0, 0.0)
    project.add_node(3.0, 2.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_surface_element((1, 2, 3, 4), section_tag=section.tag)
    project.add_surface_element((5, 6, 7, 8), section_tag=section.tag)
    return project


def test_surface_mesh_keeps_surface_tags_per_cell() -> None:
    project = _surface_project()
    view = ModelView.__new__(ModelView)
    view._project = project
    view._active_plane = None
    view._active_plane_value = None

    mesh = view._build_surface_elements_mesh(project)

    assert mesh is not None
    assert set(int(tag) for tag in mesh.cell_data["surface_tag"]) == {1, 2}


def test_node_sphere_mesh_keeps_node_tags() -> None:
    mesh = ModelView._build_node_spheres(
        np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype=float),
        0.10,
        np.array([1, 2], dtype=np.int32),
    )

    assert set(int(tag) for tag in mesh.point_data["node_tag"]) == {1, 2}
    assert set(int(tag) for tag in mesh.cell_data["node_tag"]) == {1, 2}


def test_node_tag_from_picked_mesh_reads_point_data() -> None:
    project = _surface_project()
    view = ModelView.__new__(ModelView)
    view._project = project
    mesh = ModelView._build_node_spheres(
        np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype=float),
        0.10,
        np.array([1, 2], dtype=np.int32),
    )
    point_tags = list(int(tag) for tag in mesh.point_data["node_tag"])

    class _Picker:
        def GetPointId(self):  # noqa: N802 - VTK-style API
            return point_tags.index(2)

        def GetCellId(self):  # noqa: N802 - VTK-style API
            return -1

    class _Iren:
        picker = _Picker()

    class _Plotter:
        iren = _Iren()

    class _Mapper:
        def GetInput(self):  # noqa: N802 - VTK-style API
            return mesh

    class _Actor:
        def GetMapper(self):  # noqa: N802 - VTK-style API
            return _Mapper()

    view.plotter = _Plotter()

    assert view._node_tag_from_picked_mesh(_Actor()) == 2


def test_closest_node_to_screen_prefers_frontmost_overlapping_node() -> None:
    view = ModelView.__new__(ModelView)
    view._project = SimpleNamespace(
        nodes={
            1: SimpleNamespace(x=0.0, y=0.0, z=0.0),
            2: SimpleNamespace(x=0.0, y=0.0, z=1.0),
        }
    )
    view._node_on_active_plane = lambda _x, _y, _z: True
    view._project_world_to_display = lambda point: (
        50.0,
        50.0,
        0.2 if point[2] > 0.0 else 0.8,
    )
    view._vtk_to_qt_display = lambda x, y: QPointF(x, y)

    assert view._closest_node_to_screen(QPoint(50, 50)) == (2, 0.0)


def test_pick_visible_object_uses_halved_node_tolerance_for_direct_pick() -> None:
    view = ModelView.__new__(ModelView)
    view._project = SimpleNamespace(
        nodes={1: SimpleNamespace(x=0.0, y=0.0, z=0.0)}
    )
    view._pick_object_at_screen = lambda _pos: ("node", 1)
    view._closest_element_to_screen = lambda _pos: (None, float("inf"))
    view._closest_surface_to_screen = lambda _pos: (None, float("inf"))
    view._node_on_active_plane = lambda _x, _y, _z: True
    view._project_world_to_display = lambda _point: (50.0, 50.0, 0.2)
    view._vtk_to_qt_display = lambda x, y: QPointF(x, y)

    assert view._pick_visible_object(QPoint(59, 50)) == ("node", 1)
    assert view._pick_visible_object(QPoint(60, 50)) is None


def test_closest_surface_to_screen_prefers_frontmost_overlapping_plate() -> None:
    front_surface = object()
    back_surface = object()
    view = ModelView.__new__(ModelView)
    view._project = SimpleNamespace(
        surface_elements={
            1: back_surface,
            2: front_surface,
        }
    )
    polygon = [
        QPointF(0.0, 0.0),
        QPointF(100.0, 0.0),
        QPointF(100.0, 100.0),
        QPointF(0.0, 100.0),
    ]

    def _surface_screen_polygon_data(surface):
        if surface is front_surface:
            return polygon, [0.2, 0.2, 0.2, 0.2]
        return polygon, [0.8, 0.8, 0.8, 0.8]

    view._surface_screen_polygon_data = _surface_screen_polygon_data

    assert view._closest_surface_to_screen(QPoint(50, 50)) == (2, 0.0)


def test_surface_tag_from_picked_cell_reads_mesh_cell_data() -> None:
    project = _surface_project()
    view = ModelView.__new__(ModelView)
    view._project = project
    view._active_plane = None
    view._active_plane_value = None
    mesh = view._build_surface_elements_mesh(project)
    assert mesh is not None

    class _Picker:
        def GetCellId(self):  # noqa: N802 - VTK-style API
            tags = list(int(tag) for tag in mesh.cell_data["surface_tag"])
            return tags.index(2)

    class _Iren:
        picker = _Picker()

    class _Plotter:
        iren = _Iren()

    class _Mapper:
        def GetInput(self):  # noqa: N802 - VTK-style API
            return mesh

    class _Actor:
        def GetMapper(self):  # noqa: N802 - VTK-style API
            return _Mapper()

    view.plotter = _Plotter()

    assert view._surface_tag_from_picked_cell(_Actor()) == 2


def test_point_to_surface_distance_uses_surface_interior_before_centroid() -> None:
    polygon = np.array(
        [
            [0.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
            [4.0, 4.0, 0.0],
            [0.0, 4.0, 0.0],
        ],
        dtype=float,
    )
    point = np.array([3.7, 3.7, 0.05], dtype=float)

    assert ModelView._point_to_surface_distance_world(point, polygon) == pytest.approx(0.05)
