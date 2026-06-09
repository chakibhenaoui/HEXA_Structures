"""Interactive 2D Section Builder for custom polygon sections."""

from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QFileDialog,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.section_builder import (
    Point2D,
    PolygonSectionProperties,
    SectionBuilderGeometryError,
    polygon_perimeter,
    polygon_section_properties,
)
from core.sections import (
    SteelProfile,
    get_profile,
    get_profile_family_info,
    list_profile_families,
    list_profiles,
)
from core.sectionproperties_adapter import (
    SectionPropertiesCalculationError,
    SectionPropertiesMesh,
    SectionPropertiesResult,
    SectionPropertiesStressResult,
    SectionPropertiesUnavailable,
    calculate_polygon_sectionproperties_section,
    calculate_polygon_sectionproperties_stress,
    calculate_sectionproperties_section,
    default_dimensions,
    display_properties_for_shape,
    get_sectionproperty_shape,
    list_sectionproperty_shapes,
    sectionproperties_backend_info,
    validate_sectionproperty_dimensions,
)
from gui.dialogs.section_dlg import _section_inner_polygon, _section_outer_polygon


class SectionBuilderView(QGraphicsView):
    """QGraphicsView canvas for drawing one closed outer section contour."""

    geometry_changed = Signal()
    closed_changed = Signal(bool)
    tool_changed = Signal(str)
    point_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._grid_step = 0.05
        self._snap_enabled = True
        self._points: list[Point2D] = []
        self._closed = False
        self._holes: list[list[Point2D]] = []
        self._hole_closed: list[bool] = []
        self._active_contour = "outer"
        self._active_hole_index: int | None = None
        self._path_item = QGraphicsPathItem()
        self._mesh_item: QGraphicsPathItem | None = None
        self._polygon_item: QGraphicsPathItem | None = None
        self._centroid_item: QGraphicsEllipseItem | None = None
        self._point_items: list[QGraphicsEllipseItem] = []
        self._grid_items: list[QGraphicsLineItem] = []
        self._centroid: Point2D | None = None
        self._mesh: SectionPropertiesMesh | None = None
        self._mesh_visible = True
        self._tool_mode = "polygon"
        self._selected_point_index: int | None = None
        self._dragging_point = False
        self._shape_start: Point2D | None = None
        self._preview_item: QGraphicsPathItem | None = None

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setSceneRect(-1.5, -1.2, 3.0, 2.4)
        self.setTransform(QTransform().scale(180.0, -180.0))
        self._scene.addItem(self._path_item)
        self._draw_grid()
        self._refresh_items()

    def points(self) -> list[Point2D]:
        """Return current polygon points in local y/z coordinates."""
        return list(self._points)

    def holes(self) -> list[list[Point2D]]:
        """Return closed hole contours."""
        return [
            list(hole)
            for hole, closed in zip(self._holes, self._hole_closed, strict=True)
            if closed
        ]

    def hole_count(self) -> int:
        """Return the number of hole contours, including open ones."""
        return len(self._holes)

    def is_hole_closed(self, index: int) -> bool:
        """Return whether one hole is closed."""
        return 0 <= index < len(self._hole_closed) and self._hole_closed[index]

    def active_contour(self) -> tuple[str, int | None]:
        """Return active contour identifier."""
        return self._active_contour, self._active_hole_index

    def current_points(self) -> list[Point2D]:
        """Return points for the currently selected contour."""
        return list(self._active_points())

    def is_closed(self) -> bool:
        """Return whether the contour is closed."""
        return self._closed

    def current_is_closed(self) -> bool:
        """Return whether the active contour is closed."""
        if self._active_contour == "hole" and self._active_hole_index is not None:
            return self.is_hole_closed(self._active_hole_index)
        return self._closed

    def tool_mode(self) -> str:
        """Return the current canvas tool mode."""
        return self._tool_mode

    def set_tool_mode(self, mode: str) -> None:
        """Set the active canvas editing mode."""
        allowed = {"select", "polygon", "rectangle", "circle", "hole", "move", "delete"}
        if mode not in allowed:
            mode = "polygon"
        self._tool_mode = mode
        if mode != "move":
            self._dragging_point = False
        if mode != "hole":
            self._shape_start = None
        self._clear_preview()
        self.tool_changed.emit(mode)

    def selected_point_index(self) -> int | None:
        """Return the selected point index on the active contour."""
        return self._selected_point_index

    def has_open_holes(self) -> bool:
        """Return whether a hole is still being drawn."""
        return any(not closed for closed in self._hole_closed)

    def select_outer_contour(self) -> None:
        """Select the exterior contour for editing."""
        self._active_contour = "outer"
        self._active_hole_index = None
        self._selected_point_index = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self.current_is_closed())

    def select_hole_contour(self, index: int) -> bool:
        """Select one hole contour for editing."""
        if index < 0 or index >= len(self._holes):
            return False
        self._active_contour = "hole"
        self._active_hole_index = index
        self._selected_point_index = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self.current_is_closed())
        return True

    def start_hole(self) -> int | None:
        """Create and select a new open hole contour."""
        if not self._closed:
            return None
        self._holes.append([])
        self._hole_closed.append(False)
        self._active_contour = "hole"
        self._active_hole_index = len(self._holes) - 1
        self._selected_point_index = None
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(False)
        return self._active_hole_index

    def delete_active_hole(self) -> bool:
        """Delete the selected hole contour."""
        if self._active_contour != "hole" or self._active_hole_index is None:
            return False
        index = self._active_hole_index
        if index < 0 or index >= len(self._holes):
            return False
        self._holes.pop(index)
        self._hole_closed.pop(index)
        self._active_contour = "outer"
        self._active_hole_index = None
        self._selected_point_index = None
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self.current_is_closed())
        return True

    def set_grid_step(self, step: float) -> None:
        """Set grid and snap spacing in meters."""
        self._grid_step = max(float(step), 0.001)
        self._draw_grid()

    def set_snap_enabled(self, enabled: bool) -> None:
        """Enable or disable grid snapping."""
        self._snap_enabled = bool(enabled)

    def set_geometry(
        self,
        points: list[Point2D],
        *,
        holes: list[list[Point2D]] | None = None,
        closed: bool = False,
    ) -> None:
        """Set the full section geometry programmatically."""
        self._points = [(float(y), float(z)) for y, z in points]
        self._closed = bool(closed and len(self._points) >= 3)
        self._holes = [
            [(float(y), float(z)) for y, z in hole]
            for hole in (holes or [])
            if len(hole) >= 3
        ]
        self._hole_closed = [bool(self._closed) for _hole in self._holes]
        self._active_contour = "outer"
        self._active_hole_index = None
        self._selected_point_index = None
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self._closed)

    def set_points(self, points: list[Point2D], *, closed: bool = False) -> None:
        """Set points programmatically, useful for tests and future imports."""
        self.set_geometry(points, closed=closed)

    def set_rectangle_from_corners(self, p0: Point2D, p1: Point2D) -> bool:
        """Replace the active contour with a rectangle from two opposite corners."""
        y0, z0 = self._snap_point(QPointF(p0[0], p0[1]))
        y1, z1 = self._snap_point(QPointF(p1[0], p1[1]))
        if abs(y1 - y0) <= 1.0e-12 or abs(z1 - z0) <= 1.0e-12:
            return False
        points = [(y0, z0), (y1, z0), (y1, z1), (y0, z1)]
        self._set_active_contour_points(points, closed=True)
        return True

    def set_circle_from_center_edge(self, center: Point2D, edge: Point2D) -> bool:
        """Replace the active contour with a polygonal circle."""
        cy, cz = self._snap_point(QPointF(center[0], center[1]))
        ey, ez = self._snap_point(QPointF(edge[0], edge[1]))
        radius = math.hypot(ey - cy, ez - cz)
        if radius <= 1.0e-12:
            return False
        points = [
            (
                round(cy + math.cos(angle) * radius, 12),
                round(cz + math.sin(angle) * radius, 12),
            )
            for angle in (2.0 * math.pi * idx / 48 for idx in range(48))
        ]
        self._set_active_contour_points(points, closed=True)
        return True

    def zoom_in(self) -> None:
        """Zoom into the canvas."""
        self.scale(1.2, 1.2)

    def zoom_out(self) -> None:
        """Zoom out of the canvas."""
        self.scale(1.0 / 1.2, 1.0 / 1.2)

    def fit_section_to_view(self) -> None:
        """Fit the current geometry or full grid into the view."""
        points = list(self._points)
        for hole in self._holes:
            points.extend(hole)
        if not points:
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
            return
        ys = [point[0] for point in points]
        zs = [point[1] for point in points]
        width = max(max(ys) - min(ys), self._grid_step)
        height = max(max(zs) - min(zs), self._grid_step)
        max_extent = max(width, height)
        margin = max(max_extent * 0.10, self._grid_step * 1.5, 0.005)
        rect = QRectF(
            min(ys) - margin,
            min(zs) - margin,
            width + 2.0 * margin,
            height + 2.0 * margin,
        )
        self.fitInView(rect, Qt.KeepAspectRatio)

    def clear_section(self) -> None:
        """Clear the current contour."""
        self._points.clear()
        self._holes.clear()
        self._hole_closed.clear()
        self._active_contour = "outer"
        self._active_hole_index = None
        self._closed = False
        self._selected_point_index = None
        self._shape_start = None
        self._clear_preview()
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(False)

    def remove_last_point(self) -> None:
        """Remove the last drawn point."""
        points = self._active_points()
        if not points:
            return
        points.pop()
        self._set_current_closed(False)
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self.current_is_closed())

    def set_point(self, index: int, point: Point2D) -> bool:
        """Update one existing point."""
        points = self._active_points()
        if index < 0 or index >= len(points):
            return False
        points[index] = self._snap_point(QPointF(point[0], point[1]))
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        return True

    def insert_point_after(self, index: int | None = None) -> int:
        """Insert a point after index and return the inserted row."""
        points = self._active_points()
        current_closed = self.current_is_closed()
        if not points:
            points.append((0.0, 0.0))
            self._set_current_closed(False)
            inserted = 0
        else:
            if index is None or index < 0 or index >= len(points):
                index = len(points) - 1
            y0, z0 = points[index]
            if current_closed or index < len(points) - 1:
                next_index = (index + 1) % len(points)
                y1, z1 = points[next_index]
                point = ((y0 + y1) * 0.5, (z0 + z1) * 0.5)
            else:
                point = (y0 + self._grid_step, z0)
            inserted = index + 1
            points.insert(inserted, self._snap_point(QPointF(point[0], point[1])))
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self.current_is_closed())
        return inserted

    def remove_point(self, index: int) -> bool:
        """Remove one point by index."""
        points = self._active_points()
        if index < 0 or index >= len(points):
            return False
        points.pop(index)
        if len(points) < 3:
            self._set_current_closed(False)
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self.current_is_closed())
        return True

    def set_centroid(self, point: Point2D | None) -> None:
        """Set the displayed centroid marker."""
        self._centroid = point
        self._refresh_items()

    def set_mesh(self, mesh: SectionPropertiesMesh | None) -> None:
        """Set the displayed finite-element mesh overlay."""
        self._mesh = mesh
        self._refresh_items()

    def set_mesh_visible(self, visible: bool) -> None:
        """Toggle finite-element mesh display."""
        self._mesh_visible = bool(visible)
        self._refresh_items()

    def close_contour(self) -> bool:
        """Close the current contour if possible."""
        points = self._active_points()
        if len(points) < 3:
            return False
        self._set_current_closed(True)
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self.current_is_closed())
        return True

    def add_point(self, point: Point2D) -> None:
        """Append one point to the current open contour."""
        if self.current_is_closed():
            return
        self._active_points().append(self._snap_point(QPointF(point[0], point[1])))
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton:
            self.close_contour()
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        point = self._snap_point(self.mapToScene(event.position().toPoint()))
        if self._tool_mode == "select":
            self._select_nearest_point(point)
            return
        if self._tool_mode == "move":
            self._dragging_point = self._select_nearest_point(point)
            return
        if self._tool_mode == "delete":
            index = self._nearest_point_index(point)
            if index is not None:
                self.remove_point(index)
            return
        if self._tool_mode in {"rectangle", "circle"}:
            self._shape_start = point
            self._update_shape_preview(point)
            return
        if self._tool_mode == "hole":
            if self._active_contour != "hole" or self.current_is_closed():
                if self.start_hole() is None:
                    return
            self._append_polygon_point(point)
            return
        if self.current_is_closed():
            super().mousePressEvent(event)
            return

        self._append_polygon_point(point)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = self._snap_point(self.mapToScene(event.position().toPoint()))
        if self._dragging_point and self._selected_point_index is not None:
            self.set_point(self._selected_point_index, point)
            return
        if self._shape_start is not None and self._tool_mode in {"rectangle", "circle"}:
            self._update_shape_preview(point)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        point = self._snap_point(self.mapToScene(event.position().toPoint()))
        if self._dragging_point:
            self._dragging_point = False
            return
        if self._shape_start is not None and self._tool_mode in {"rectangle", "circle"}:
            start = self._shape_start
            self._shape_start = None
            self._clear_preview()
            if self._distance(start, point) <= self._grid_step * 0.25:
                point = (start[0] + self._grid_step * 4.0, start[1] + self._grid_step * 4.0)
            if self._tool_mode == "rectangle":
                self.set_rectangle_from_corners(start, point)
            else:
                self.set_circle_from_center_edge(start, point)
            return
        super().mouseReleaseEvent(event)

    def _append_polygon_point(self, point: Point2D) -> None:
        points = self._active_points()
        if len(points) >= 3 and self._distance(point, points[0]) <= self._grid_step * 0.75:
            self.close_contour()
            return
        points.append(point)
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    def _active_points(self) -> list[Point2D]:
        if self._active_contour == "hole" and self._active_hole_index is not None:
            return self._holes[self._active_hole_index]
        return self._points

    def _set_current_closed(self, closed: bool) -> None:
        if self._active_contour == "hole" and self._active_hole_index is not None:
            if 0 <= self._active_hole_index < len(self._hole_closed):
                self._hole_closed[self._active_hole_index] = bool(
                    closed and len(self._holes[self._active_hole_index]) >= 3
                )
            return
        self._closed = bool(closed and len(self._points) >= 3)

    def _snap_point(self, point: QPointF) -> Point2D:
        if not self._snap_enabled:
            return (float(point.x()), float(point.y()))
        return (
            round(round(float(point.x()) / self._grid_step) * self._grid_step, 12),
            round(round(float(point.y()) / self._grid_step) * self._grid_step, 12),
        )

    @staticmethod
    def _distance(p0: Point2D, p1: Point2D) -> float:
        return math.hypot(p0[0] - p1[0], p0[1] - p1[1])

    def _set_active_contour_points(self, points: list[Point2D], *, closed: bool) -> None:
        if self._active_contour == "hole" and self._active_hole_index is not None:
            self._holes[self._active_hole_index] = list(points)
            self._hole_closed[self._active_hole_index] = bool(closed and len(points) >= 3)
        else:
            self._points = list(points)
            self._closed = bool(closed and len(points) >= 3)
        self._selected_point_index = None
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self.current_is_closed())

    def _nearest_point_index(self, point: Point2D) -> int | None:
        points = self._active_points()
        if not points:
            return None
        distances = [self._distance(point, candidate) for candidate in points]
        index = min(range(len(distances)), key=distances.__getitem__)
        if distances[index] <= max(self._grid_step * 0.75, 0.015):
            return index
        return None

    def _select_nearest_point(self, point: Point2D) -> bool:
        index = self._nearest_point_index(point)
        self._selected_point_index = index
        self._refresh_items()
        self.point_selected.emit(index if index is not None else -1)
        return index is not None

    def _update_shape_preview(self, point: Point2D) -> None:
        if self._shape_start is None:
            return
        self._clear_preview()
        path = QPainterPath()
        if self._tool_mode == "rectangle":
            y0, z0 = self._shape_start
            y1, z1 = point
            path.moveTo(y0, z0)
            path.lineTo(y1, z0)
            path.lineTo(y1, z1)
            path.lineTo(y0, z1)
            path.closeSubpath()
        elif self._tool_mode == "circle":
            cy, cz = self._shape_start
            radius = self._distance(self._shape_start, point)
            if radius <= 1.0e-12:
                return
            first = True
            for idx in range(48):
                angle = 2.0 * math.pi * idx / 48
                candidate = (cy + math.cos(angle) * radius, cz + math.sin(angle) * radius)
                if first:
                    path.moveTo(*candidate)
                    first = False
                else:
                    path.lineTo(*candidate)
            path.closeSubpath()
        preview_pen = QPen(QColor("#6b7280"), 0, Qt.DashLine)
        preview_pen.setCosmetic(True)
        self._preview_item = self._scene.addPath(
            path,
            preview_pen,
            QBrush(QColor(80, 150, 220, 35)),
        )
        self._preview_item.setZValue(6)

    def _clear_preview(self) -> None:
        if self._preview_item is not None:
            self._scene.removeItem(self._preview_item)
            self._preview_item = None

    def _draw_grid(self) -> None:
        for item in self._grid_items:
            self._scene.removeItem(item)
        self._grid_items.clear()
        rect = self.sceneRect()
        minor_pen = QPen(QColor("#dfe5ec"), 0)
        axis_y_pen = QPen(QColor("#2f855a"), 0)
        axis_z_pen = QPen(QColor("#2b6cb0"), 0)
        for pen in (minor_pen, axis_y_pen, axis_z_pen):
            pen.setCosmetic(True)

        start_y = math.floor(rect.left() / self._grid_step) * self._grid_step
        end_y = math.ceil(rect.right() / self._grid_step) * self._grid_step
        start_z = math.floor(rect.top() / self._grid_step) * self._grid_step
        end_z = math.ceil(rect.bottom() / self._grid_step) * self._grid_step

        y = start_y
        while y <= end_y + 1.0e-9:
            item = self._scene.addLine(y, rect.top(), y, rect.bottom(), axis_z_pen if abs(y) < 1e-12 else minor_pen)
            item.setZValue(-10)
            self._grid_items.append(item)
            y += self._grid_step

        z = start_z
        while z <= end_z + 1.0e-9:
            item = self._scene.addLine(rect.left(), z, rect.right(), z, axis_y_pen if abs(z) < 1e-12 else minor_pen)
            item.setZValue(-10)
            self._grid_items.append(item)
            z += self._grid_step

    def _refresh_items(self) -> None:
        if self._polygon_item is not None:
            self._scene.removeItem(self._polygon_item)
            self._polygon_item = None
        if self._mesh_item is not None:
            self._scene.removeItem(self._mesh_item)
            self._mesh_item = None
        if self._centroid_item is not None:
            self._scene.removeItem(self._centroid_item)
            self._centroid_item = None
        for item in self._point_items:
            self._scene.removeItem(item)
        self._point_items.clear()

        path = QPainterPath()
        if self._points:
            path.moveTo(*self._points[0])
            for point in self._points[1:]:
                path.lineTo(*point)
            if self._closed:
                path.closeSubpath()
        for index, hole in enumerate(self._holes):
            if not hole:
                continue
            path.moveTo(*hole[0])
            for point in hole[1:]:
                path.lineTo(*point)
            if self._hole_closed[index]:
                path.closeSubpath()
        pen = QPen(QColor("#1f2933"), 0)
        pen.setCosmetic(True)
        self._path_item.setPen(pen)
        self._path_item.setPath(path)
        self._path_item.setZValue(5)

        if self._closed and len(self._points) >= 3:
            section_path = QPainterPath()
            section_path.setFillRule(Qt.OddEvenFill)
            section_path.moveTo(*self._points[0])
            for point in self._points[1:]:
                section_path.lineTo(*point)
            section_path.closeSubpath()
            for index, hole in enumerate(self._holes):
                if not self._hole_closed[index] or len(hole) < 3:
                    continue
                section_path.moveTo(*hole[0])
                for point in hole[1:]:
                    section_path.lineTo(*point)
                section_path.closeSubpath()
            self._polygon_item = self._scene.addPath(
                section_path,
                pen,
                QBrush(QColor(80, 150, 220, 70)),
            )
            self._polygon_item.setZValue(1)

        if self._mesh_visible and self._mesh is not None:
            mesh_path = QPainterPath()
            for triangle in self._mesh.triangles:
                try:
                    p0 = self._mesh.vertices[triangle[0]]
                    p1 = self._mesh.vertices[triangle[1]]
                    p2 = self._mesh.vertices[triangle[2]]
                except IndexError:
                    continue
                mesh_path.moveTo(*p0)
                mesh_path.lineTo(*p1)
                mesh_path.lineTo(*p2)
                mesh_path.closeSubpath()
            mesh_pen = QPen(QColor("#2b6cb0"), 0)
            mesh_pen.setCosmetic(True)
            self._mesh_item = self._scene.addPath(mesh_path, mesh_pen)
            self._mesh_item.setZValue(3)

        point_pen = QPen(QColor("#1f2933"), 0)
        point_pen.setCosmetic(True)
        marker_radius = 4.5
        contours = [("outer", None, self._points)] + [
            ("hole", index, hole) for index, hole in enumerate(self._holes)
        ]
        for kind, index, contour in contours:
            active = kind == self._active_contour and index == self._active_hole_index
            for row, (y, z) in enumerate(contour):
                if active and row == self._selected_point_index:
                    point_brush = QBrush(QColor("#f97316"))
                else:
                    point_brush = QBrush(QColor("#ffffff") if active else QColor("#dbeafe"))
                item = QGraphicsEllipseItem(
                    -marker_radius,
                    -marker_radius,
                    marker_radius * 2,
                    marker_radius * 2,
                )
                item.setPen(point_pen)
                item.setBrush(point_brush)
                item.setPos(y, z)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                    True,
                )
                self._scene.addItem(item)
                item.setZValue(8)
                self._point_items.append(item)

        if self._centroid is not None:
            y, z = self._centroid
            centroid_pen = QPen(QColor("#c53030"), 0)
            centroid_pen.setCosmetic(True)
            centroid_radius = 5.5
            self._centroid_item = QGraphicsEllipseItem(
                -centroid_radius,
                -centroid_radius,
                centroid_radius * 2,
                centroid_radius * 2,
            )
            self._centroid_item.setPen(centroid_pen)
            self._centroid_item.setBrush(QBrush(QColor("#c53030")))
            self._centroid_item.setPos(y, z)
            self._centroid_item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            self._scene.addItem(self._centroid_item)
            self._centroid_item.setZValue(12)


class StandardProfileImportDialog(QDialog):
    """Small selector for HEXA standard steel profiles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Importer un profil standard"))
        self.setMinimumWidth(360)

        self._combo_family = QComboBox(self)
        self._combo_profile = QComboBox(self)
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self,
        )
        ok_button = self._button_box.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setText(self.tr("OK"))
        cancel_button = self._button_box.button(QDialogButtonBox.Cancel)
        if cancel_button is not None:
            cancel_button.setText(self.tr("Annuler"))

        form = QFormLayout()
        form.addRow(self.tr("Famille :"), self._combo_family)
        form.addRow(self.tr("Profil :"), self._combo_profile)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._button_box)

        self._combo_family.currentIndexChanged.connect(self._populate_profiles)
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        self._populate_families()

    def selected_profile_name(self) -> str:
        """Return the selected catalog profile name."""
        return str(self._combo_profile.currentData() or "").strip()

    def _populate_families(self) -> None:
        self._combo_family.clear()
        families = list_profile_families()
        for family in families:
            info = get_profile_family_info(family)
            label = info.label if info.label and info.label != family else family
            self._combo_family.addItem(label, family)
        if not families:
            self._combo_family.addItem(self.tr("(aucune famille)"), "")
        self._populate_profiles()

    def _populate_profiles(self, *_args) -> None:
        self._combo_profile.clear()
        family = str(self._combo_family.currentData() or "")
        profiles = list_profiles(family) if family else []
        for profile_name in profiles:
            self._combo_profile.addItem(profile_name, profile_name)
        if not profiles:
            self._combo_profile.addItem(self.tr("(aucun profil)"), "")
        ok_button = self._button_box.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setEnabled(bool(profiles))


class SectionStressDialog(QDialog):
    """Display sectionproperties stress contours with Matplotlib."""

    def __init__(self, builder: "SectionBuilderDialog"):
        super().__init__(builder)
        self._builder = builder
        self._stress_result: SectionPropertiesStressResult | None = None
        try:
            from matplotlib.backends.backend_qtagg import (
                FigureCanvasQTAgg,
                NavigationToolbar2QT,
            )
            from matplotlib.figure import Figure
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

        self.setWindowTitle(self.tr("Contraintes sectionproperties"))
        self.resize(980, 680)

        self._combo_stress = QComboBox(self)
        for key, label in self._stress_choices():
            self._combo_stress.addItem(label, key)

        self._spin_n = self._make_action_spin(" kN", 0.0, 10.0)
        self._spin_vx = self._make_action_spin(" kN", 0.0, 10.0)
        self._spin_vy = self._make_action_spin(" kN", 0.0, 10.0)
        self._spin_mxx = self._make_action_spin(" kN.m", 1.0, 1.0)
        self._spin_myy = self._make_action_spin(" kN.m", 0.0, 1.0)
        self._spin_mzz = self._make_action_spin(" kN.m", 0.0, 1.0)
        self._lbl_status = QLabel("", self)
        self._lbl_status.setWordWrap(True)
        self._btn_calculate = QPushButton(self.tr("Calculer"), self)

        self._figure = Figure(figsize=(7.0, 4.8))
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._plot_toolbar = NavigationToolbar2QT(self._canvas, self)

        form = QFormLayout()
        form.addRow(self.tr("Resultat :"), self._combo_stress)
        form.addRow(self.tr("N :"), self._spin_n)
        form.addRow(self.tr("Vx :"), self._spin_vx)
        form.addRow(self.tr("Vy :"), self._spin_vy)
        form.addRow(self.tr("Mxx :"), self._spin_mxx)
        form.addRow(self.tr("Myy :"), self._spin_myy)
        form.addRow(self.tr("Mzz :"), self._spin_mzz)

        actions_group = QGroupBox(self.tr("Efforts de reference"), self)
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.addLayout(form)
        actions_layout.addWidget(self._btn_calculate)
        actions_layout.addWidget(self._lbl_status)

        plot_panel = QWidget(self)
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.addWidget(self._plot_toolbar)
        plot_layout.addWidget(self._canvas, 1)

        body = QHBoxLayout()
        body.addWidget(actions_group)
        body.addWidget(plot_panel, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.Close, self)
        close_button = button_box.button(QDialogButtonBox.Close)
        if close_button is not None:
            close_button.setText(self.tr("Fermer"))

        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(button_box)

        self._btn_calculate.clicked.connect(lambda: self._calculate_and_plot(show_errors=True))
        self._combo_stress.currentIndexChanged.connect(
            lambda _index: self._calculate_and_plot(show_errors=False)
        )
        button_box.rejected.connect(self.reject)
        self._calculate_and_plot(show_errors=False)

    def _make_action_spin(
        self,
        suffix: str,
        value: float,
        step: float,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(-1.0e9, 1.0e9)
        spin.setDecimals(3)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setValue(value)
        return spin

    def _stress_choices(self) -> tuple[tuple[str, str], ...]:
        return (
            ("zz", self.tr("Normale totale sigma_zz")),
            ("mxx_zz", self.tr("Flexion Mxx")),
            ("myy_zz", self.tr("Flexion Myy")),
            ("n_zz", self.tr("Effort normal N")),
            ("zxy", self.tr("Cisaillement total")),
            ("vm", self.tr("Von Mises")),
        )

    def _actions_si(self) -> dict[str, float]:
        return {
            "n": self._spin_n.value() * 1.0e3,
            "vx": self._spin_vx.value() * 1.0e3,
            "vy": self._spin_vy.value() * 1.0e3,
            "mxx": self._spin_mxx.value() * 1.0e3,
            "myy": self._spin_myy.value() * 1.0e3,
            "mzz": self._spin_mzz.value() * 1.0e3,
        }

    def _calculate_and_plot(self, *, show_errors: bool) -> bool:
        stress_key = str(self._combo_stress.currentData() or "zz")
        result = self._builder._calculate_stress_result(
            stress_key=stress_key,
            actions=self._actions_si(),
            show_errors=show_errors,
        )
        if result is None:
            return False
        self._stress_result = result
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        result.stress_post.plot_stress(
            stress_key,
            ax=ax,
            render=False,
            title=self._combo_stress.currentText(),
            colorbar_label=self.tr("Contrainte (Pa)"),
            cmap="coolwarm",
            alpha=0.35,
        )
        ax.set_xlabel("y (m)")
        ax.set_ylabel("z (m)")
        ax.set_aspect("equal", adjustable="box")
        try:
            self._figure.tight_layout()
        except Exception:
            pass
        self._canvas.draw_idle()
        self._lbl_status.setText(
            self.tr("Min : {min:.3f} MPa - Max : {max:.3f} MPa").format(
                min=result.min_stress / 1.0e6,
                max=result.max_stress / 1.0e6,
            )
        )
        return True


class SectionBuilderDialog(QDialog):
    """Dialog used to draw and analyze one custom polygon section."""

    def __init__(
        self,
        parent=None,
        *,
        materials: dict | None = None,
        name: str = "",
        material_tag: int | None = None,
        properties: dict | None = None,
    ):
        super().__init__(parent)
        self._materials = materials or {}
        self._init_properties = properties or {}
        self._properties: PolygonSectionProperties | None = None
        self._sectionproperties_result: SectionPropertiesResult | None = None
        self._sectionproperties_stress_result: SectionPropertiesStressResult | None = None
        self._backend_info = sectionproperties_backend_info()
        self._sectionproperties_available = self._backend_info.available
        self._result: dict | None = None
        self._updating_points_table = False
        self._current_file_path: Path | None = None
        self._loading_library_shape = False
        self._loading_catalog_profile = False
        self._active_library_shape: str | None = None
        self._active_library_dimensions: dict[str, float] | None = None
        self._active_catalog_profile: str | None = None
        self._dimension_spins: dict[str, QDoubleSpinBox] = {}
        self._tool_actions: dict[str, QAction] = {}

        self.setWindowTitle(self.tr("Section Builder HEXA"))
        self.setMinimumSize(1120, 720)
        self.resize(1240, 780)

        self._view = SectionBuilderView(self)
        self._edit_name = QLineEdit(name or self.tr("Section personnalisée"), self)
        self._combo_material = QComboBox(self)
        self._menu_bar = QMenuBar(self)
        self._side_tabs = QTabWidget(self)
        self._side_tabs.setDocumentMode(True)
        self._combo_tool = QComboBox(self)
        self._combo_tool.setMinimumWidth(170)
        self._spin_grid = QDoubleSpinBox(self)
        self._spin_grid.setRange(0.001, 1.0)
        self._spin_grid.setDecimals(3)
        self._spin_grid.setSingleStep(0.01)
        self._spin_grid.setSuffix(" m")
        self._spin_grid.setValue(0.05)
        self._chk_snap = QPushButton(self.tr("Accrochage grille actif"), self)
        self._chk_snap.setCheckable(True)
        self._chk_snap.setChecked(True)
        self._combo_contour = QComboBox(self)
        self._btn_add_hole = QPushButton(self.tr("Nouveau trou"), self)
        self._btn_delete_hole = QPushButton(self.tr("Supprimer trou"), self)
        self._combo_shape = QComboBox(self)
        self._library_params_group = QGroupBox(self.tr("Parametres du profile"), self)
        self._library_params_layout = QFormLayout(self._library_params_group)
        self._lbl_library_status = QLabel("", self)
        self._lbl_library_status.setWordWrap(True)
        self._btn_insert_shape = QPushButton(
            self.tr("Inserer a partir de la bibliotheque"),
            self,
        )
        self._btn_insert_shape.setEnabled(self._sectionproperties_available)
        self._chk_use_sectionproperties = QCheckBox(self.tr("Calculer avec sectionproperties"), self)
        self._chk_use_sectionproperties.setChecked(self._sectionproperties_available)
        self._chk_use_sectionproperties.setEnabled(self._sectionproperties_available)
        self._spin_mesh_area = QDoubleSpinBox(self)
        self._spin_mesh_area.setRange(1.0e-8, 1.0)
        self._spin_mesh_area.setDecimals(8)
        self._spin_mesh_area.setSingleStep(1.0e-5)
        self._spin_mesh_area.setSuffix(" m2")
        self._spin_mesh_area.setValue(1.0e-4)
        self._spin_mesh_area.setEnabled(self._sectionproperties_available)
        self._chk_show_mesh = QCheckBox(self.tr("Afficher le maillage"), self)
        self._chk_show_mesh.setChecked(True)
        self._chk_show_mesh.setEnabled(self._sectionproperties_available)
        self._table_points = QTableWidget(0, 2, self)
        self._table_points.setHorizontalHeaderLabels([self.tr("y (m)"), self.tr("z (m)")])
        self._table_points.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table_points.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self._lbl_results = QLabel(self.tr("Dessinez puis fermez un contour."), self)
        self._lbl_results.setWordWrap(True)
        self._lbl_dimensions = QLabel("", self)
        self._lbl_dimensions.setWordWrap(True)
        self._lbl_status = QLabel("", self)
        self._lbl_status.setWordWrap(True)
        self._btn_close = QPushButton(self.tr("Fermer le contour"), self)
        self._btn_undo = QPushButton(self.tr("Annuler point"), self)
        self._btn_insert = QPushButton(self.tr("Inserer point"), self)
        self._btn_delete = QPushButton(self.tr("Supprimer point"), self)
        self._btn_clear = QPushButton(self.tr("Effacer"), self)
        self._btn_analyze = QPushButton(self.tr("Analyser"), self)
        self._button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        ok_button = self._button_box.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setText(self.tr("Inserer la section"))
            ok_button.setEnabled(False)

        self._create_actions()
        self._setup_ui()
        self._populate_shapes()
        self._populate_materials(material_tag)
        self._connect_signals()
        self._apply_initial_values()
        self._on_shape_changed()
        self._load_initial_geometry()
        if material_tag is not None:
            self._select_material_tag(material_tag)
        self._refresh_contour_combo()
        self._refresh_points()
        self._refresh_status()
        if not self._sectionproperties_available:
            self._lbl_results.setText(
                self.tr(
                    "sectionproperties indisponible : calcul polygonal simple utilise."
                )
            )

    def result(self) -> dict:
        """Return the section payload expected by ProjectModel.add_section."""
        if self._result is None:
            self._analyze(show_errors=False)
        return dict(self._result or {})

    def _create_actions(self) -> None:
        """Create Section Builder menu actions."""
        self.act_new = QAction(self.tr("Nouveau"), self)
        self.act_open = QAction(self.tr("Ouvrir..."), self)
        self.act_import_shape = QAction(self.tr("Importer profil standard..."), self)
        self.act_save = QAction(self.tr("Enregistrer"), self)
        self.act_save_as = QAction(self.tr("Enregistrer sous..."), self)
        self.act_print_report = QAction(self.tr("Imprimer le rapport"), self)
        self.act_print_report.setEnabled(False)
        self.act_quit = QAction(self.tr("Quitter"), self)

        self.act_sp_insert_library = QAction(
            self.tr("Inserer a partir de la bibliotheque"),
            self,
        )
        self.act_sp_insert_library.setEnabled(self._sectionproperties_available)
        self.act_sp_calculate = QAction(self.tr("Calculer"), self)
        self.act_sp_results = QAction(self.tr("Resultats"), self)
        self.act_sp_show_stress = QAction(self.tr("Afficher contrainte"), self)
        self.act_sp_show_stress.setEnabled(self._sectionproperties_available)
        self.act_sp_show_stress.setToolTip(
            self.tr("Calculer et afficher les contraintes avec sectionproperties.")
        )
        self._tool_action_group = QActionGroup(self)
        self._tool_action_group.setExclusive(True)
        tool_specs = (
            ("select", self.tr("Selection")),
            ("polygon", self.tr("Polygone")),
            ("rectangle", self.tr("Rectangle")),
            ("circle", self.tr("Cercle")),
            ("hole", self.tr("Trou")),
            ("move", self.tr("Deplacer point")),
            ("delete", self.tr("Supprimer point")),
        )
        for mode, label in tool_specs:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(mode)
            if mode == "polygon":
                action.setChecked(True)
            self._tool_action_group.addAction(action)
            self._tool_actions[mode] = action
        self.act_canvas_zoom_in = QAction(self.tr("Zoom +"), self)
        self.act_canvas_zoom_out = QAction(self.tr("Zoom -"), self)
        self.act_canvas_fit = QAction(self.tr("Ajuster"), self)

    def _setup_menu_bar(self) -> None:
        """Build the Section Builder menu bar."""
        self._menu_file = QMenu(self.tr("Fichier"), self._menu_bar)
        self._menu_bar.addMenu(self._menu_file)
        self._menu_file.addAction(self.act_new)
        self._menu_file.addAction(self.act_open)
        self._menu_file.addAction(self.act_import_shape)
        self._menu_file.addSeparator()
        self._menu_file.addAction(self.act_save)
        self._menu_file.addAction(self.act_save_as)
        self._menu_file.addAction(self.act_print_report)
        self._menu_file.addSeparator()
        self._menu_file.addAction(self.act_quit)

        self._menu_sectionproperties = QMenu(
            self.tr("sectionproperties"),
            self._menu_bar,
        )
        self._menu_bar.addMenu(self._menu_sectionproperties)
        self._menu_sectionproperties.addAction(self.act_sp_insert_library)
        self._menu_sectionproperties.addSeparator()
        self._menu_sectionproperties.addAction(self.act_sp_calculate)
        self._menu_sectionproperties.addAction(self.act_sp_results)
        self._menu_sectionproperties.addAction(self.act_sp_show_stress)

    def _setup_ui(self) -> None:
        main = QVBoxLayout(self)
        main.setMenuBar(self._menu_bar)
        self._setup_menu_bar()
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self._build_canvas_panel())
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        main.addWidget(splitter, 1)
        main.addWidget(self._button_box)

    def _build_canvas_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.addWidget(self._build_canvas_toolbar())
        layout.addWidget(self._view, 1)
        layout.addWidget(self._lbl_status)
        return panel

    def _build_canvas_toolbar(self) -> QToolBar:
        toolbar = QToolBar(self.tr("Barre Section Builder"), self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._populate_tool_selector()
        toolbar.addWidget(QLabel(self.tr("Outil :"), self))
        toolbar.addWidget(self._combo_tool)
        toolbar.addSeparator()
        toolbar.addAction(self.act_canvas_zoom_out)
        toolbar.addAction(self.act_canvas_zoom_in)
        toolbar.addAction(self.act_canvas_fit)
        return toolbar

    def _populate_tool_selector(self) -> None:
        if self._combo_tool.count():
            return
        for mode in ("select", "polygon", "rectangle", "circle", "hole", "move", "delete"):
            self._combo_tool.addItem(self._tool_label(mode), mode)
        index = self._combo_tool.findData(self._view.tool_mode())
        if index >= 0:
            self._combo_tool.setCurrentIndex(index)

    def _build_side_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.addWidget(self._side_tabs, 1)
        self._side_tabs.addTab(self._build_general_tab(), self.tr("General"))
        self._side_tabs.addTab(self._build_contour_tab(), self.tr("Contour"))
        self._side_tabs.addTab(self._build_calculation_tab(), self.tr("Calcul"))
        return panel

    def _build_general_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        info_group = QGroupBox(self.tr("Definition"), tab)
        form = QFormLayout(info_group)
        form.addRow(self.tr("Nom :"), self._edit_name)
        form.addRow(self.tr("Materiau :"), self._combo_material)
        form.addRow(self.tr("Pas de grille :"), self._spin_grid)
        form.addRow("", self._chk_snap)
        layout.addWidget(info_group)
        layout.addWidget(self._build_sectionproperties_library_group())
        layout.addStretch(1)
        return tab

    def _build_contour_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        points_group = QGroupBox(self.tr("Points du contour"), tab)
        points_layout = QVBoxLayout(points_group)
        contour_form = QFormLayout()
        contour_form.addRow(self.tr("Contour :"), self._combo_contour)
        points_layout.addLayout(contour_form)
        contour_buttons = QHBoxLayout()
        contour_buttons.addWidget(self._btn_close)
        contour_buttons.addWidget(self._btn_undo)
        contour_buttons.addWidget(self._btn_clear)
        points_layout.addLayout(contour_buttons)
        hole_buttons = QHBoxLayout()
        hole_buttons.addWidget(self._btn_add_hole)
        hole_buttons.addWidget(self._btn_delete_hole)
        points_layout.addLayout(hole_buttons)
        points_layout.addWidget(self._table_points)
        point_buttons = QHBoxLayout()
        point_buttons.addWidget(self._btn_insert)
        point_buttons.addWidget(self._btn_delete)
        points_layout.addLayout(point_buttons)
        points_layout.addWidget(self._lbl_dimensions)
        layout.addWidget(points_group, 1)
        return tab

    def _build_calculation_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        results_group = QGroupBox(self.tr("Analyse"), tab)
        results_layout = QVBoxLayout(results_group)
        results_layout.addWidget(self._chk_use_sectionproperties)
        mesh_form = QFormLayout()
        mesh_form.addRow(self.tr("Surface max. de maille :"), self._spin_mesh_area)
        results_layout.addLayout(mesh_form)
        results_layout.addWidget(self._chk_show_mesh)
        results_layout.addWidget(self._btn_analyze)
        results_layout.addWidget(self._lbl_results)
        layout.addWidget(results_group)
        layout.addStretch(1)
        return tab

    def _build_sectionproperties_library_group(self) -> QWidget:
        group = QGroupBox(self.tr("Bibliotheque sectionproperties"), self)
        layout = QVBoxLayout(group)
        form = QFormLayout()
        form.addRow(self.tr("Forme :"), self._combo_shape)
        layout.addLayout(form)
        layout.addWidget(self._library_params_group)
        layout.addWidget(self._btn_insert_shape)
        layout.addWidget(self._lbl_library_status)
        return group

    def _populate_materials(self, material_tag: int | None) -> None:
        for tag, mat in self._materials.items():
            self._combo_material.addItem(f"{mat.name} ({mat.grade})", tag)
        if not self._materials:
            self._combo_material.addItem(self.tr("(aucun materiau)"), 0)
            return
        if material_tag is not None:
            index = self._combo_material.findData(material_tag)
            if index >= 0:
                self._combo_material.setCurrentIndex(index)

    def _populate_shapes(self) -> None:
        """Populate sectionproperties library shape choices."""
        self._combo_shape.clear()
        for shape in list_sectionproperty_shapes():
            self._combo_shape.addItem(self._shape_label(shape.key), shape.key)

    def _apply_initial_values(self) -> None:
        """Restore the sectionproperties shape selector from existing properties."""
        shape_key = str(self._init_properties.get("shape", "") or "")
        if not shape_key:
            return
        index = self._combo_shape.findData(shape_key)
        if index >= 0:
            self._combo_shape.setCurrentIndex(index)

    def _load_initial_geometry(self) -> None:
        """Load existing section geometry into the canvas when possible."""
        if self._init_properties.get("source") == "sectionproperties":
            self._insert_library_shape(show_errors=False, update_name=False)
            return
        profile_name = str(self._init_properties.get("profile", "") or "").strip()
        if profile_name:
            self._insert_standard_profile(
                profile_name,
                show_errors=False,
                update_name=False,
            )
            return
        points = self._init_properties.get("points")
        if not isinstance(points, list):
            return
        holes = self._init_properties.get("holes")
        normalized_holes = holes if isinstance(holes, list) else []
        try:
            self._view.set_geometry(points, holes=normalized_holes, closed=True)
        except (TypeError, ValueError, IndexError):
            self._view.clear_section()

    def _shape_label(self, shape_key: str) -> str:
        labels = {
            "rectangular": self.tr("Rectangle"),
            "circle": self.tr("Cercle plein"),
            "i": self.tr("I / H"),
            "channel": self.tr("U / Channel"),
            "tee": self.tr("T"),
            "angle": self.tr("Corniere L"),
            "chs": self.tr("Tube circulaire CHS"),
            "rhs": self.tr("Tube rectangulaire RHS/SHS"),
        }
        return labels.get(shape_key, shape_key)

    def _field_label(self, shape_key: str, field: str) -> str:
        if field == "d" and shape_key in {"circle", "chs"}:
            return self.tr("Diametre d :")
        labels = {
            "d": self.tr("Hauteur d :"),
            "b": self.tr("Largeur b :"),
            "t": self.tr("Epaisseur t :"),
            "t_f": self.tr("Epaisseur aile t_f :"),
            "t_w": self.tr("Epaisseur ame t_w :"),
            "r": self.tr("Rayon r :"),
            "r_r": self.tr("Rayon interieur r_r :"),
            "r_t": self.tr("Rayon exterieur r_t :"),
            "r_out": self.tr("Rayon exterieur r_out :"),
        }
        return labels.get(field, f"{field} :")

    def _make_dimension_spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setMinimum(0.0)
        spin.setMaximum(20.0)
        spin.setDecimals(4)
        spin.setSingleStep(0.001)
        spin.setSuffix(" m")
        spin.setValue(float(value))
        spin.valueChanged.connect(self._on_library_dimension_changed)
        return spin

    def _clear_library_parameters(self) -> None:
        while self._library_params_layout.count():
            item = self._library_params_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._dimension_spins.clear()

    def _on_shape_changed(self) -> None:
        shape_key = str(self._combo_shape.currentData() or "rectangular")
        shape = get_sectionproperty_shape(shape_key)
        dimensions = self._initial_dimensions(shape_key)
        self._clear_library_parameters()
        for field in shape.fields:
            spin = self._make_dimension_spin(dimensions[field])
            self._library_params_layout.addRow(self._field_label(shape_key, field), spin)
            self._dimension_spins[field] = spin
        self._select_material_type(shape.default_material_type)
        self._update_library_status()

    def _initial_dimensions(self, shape_key: str) -> dict[str, float]:
        dimensions = default_dimensions(shape_key)
        saved = self._init_properties.get("dimensions")
        if (
            self._init_properties.get("source") == "sectionproperties"
            and self._init_properties.get("shape") == shape_key
            and isinstance(saved, dict)
        ):
            for key in dimensions:
                if key in saved:
                    dimensions[key] = float(saved[key])
        return dimensions

    def _current_dimensions(self) -> dict[str, float]:
        return {key: spin.value() for key, spin in self._dimension_spins.items()}

    def _on_library_dimension_changed(self) -> None:
        self._active_library_shape = None
        self._active_library_dimensions = None
        self._active_catalog_profile = None
        self._invalidate_result()
        self._update_library_status()

    def _select_material_type(self, material_type: str) -> None:
        for index in range(self._combo_material.count()):
            tag = self._combo_material.itemData(index)
            mat = self._materials.get(tag)
            if mat is not None and getattr(mat, "material_type", "") == material_type:
                self._combo_material.setCurrentIndex(index)
                return

    def _select_material_tag(self, material_tag: int) -> None:
        index = self._combo_material.findData(material_tag)
        if index >= 0:
            self._combo_material.setCurrentIndex(index)

    def _validation_message(self, code: str) -> str:
        messages = {
            "positive_dimensions": self.tr("Toutes les dimensions principales doivent etre positives."),
            "positive_radii": self.tr("Les rayons doivent etre positifs ou nuls."),
            "web_too_thick": self.tr("L'ame doit rester inferieure a la largeur."),
            "flange_too_thick": self.tr("Les ailes doivent laisser une ame centrale."),
            "angle_too_thick": self.tr("L'epaisseur de la corniere doit rester inferieure aux deux ailes."),
            "toe_radius_too_large": self.tr("Le rayon exterieur ne doit pas depasser l'epaisseur."),
            "hollow_too_thick": self.tr("Les dimensions interieures doivent rester positives."),
        }
        return messages.get(code, self.tr("Geometrie de section invalide."))

    def _update_library_status(self) -> None:
        if not self._sectionproperties_available:
            self._lbl_library_status.setText(
                self.tr("sectionproperties indisponible : bibliotheque non chargee.")
            )
            return
        shape_key = str(self._combo_shape.currentData() or "rectangular")
        error_code = validate_sectionproperty_dimensions(shape_key, self._current_dimensions())
        if error_code is None:
            count = len(self._backend_info.library_functions)
            self._lbl_library_status.setText(
                self.tr("Bibliotheque sectionproperties prete ({count} fonctions detectees).").format(
                    count=count,
                )
            )
        else:
            self._lbl_library_status.setText(self._validation_message(error_code))

    def _show_standard_profile_import_dialog(self) -> None:
        dialog = StandardProfileImportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        profile_name = dialog.selected_profile_name()
        if profile_name:
            self._insert_standard_profile(profile_name, show_errors=True)

    def _insert_standard_profile(
        self,
        profile_name: str,
        *,
        show_errors: bool,
        update_name: bool = True,
    ) -> bool:
        """Insert a HEXA catalog steel profile into the editable canvas."""
        try:
            profile = get_profile(profile_name)
        except KeyError:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Profil introuvable"),
                    self.tr("Le profil selectionne n'existe pas dans le catalogue."),
                )
            return False

        profile_properties = {"profile": profile.name}
        outer = _section_outer_polygon("I_profile", profile_properties)
        inner = _section_inner_polygon("I_profile", profile_properties)
        if not outer:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Import impossible"),
                    self.tr("Le profil selectionne ne peut pas etre converti en contour."),
                )
            return False

        holes = [inner] if inner else []
        self._set_comfortable_grid_for_geometry(outer, holes)
        self._loading_catalog_profile = True
        try:
            self._view.set_geometry(outer, holes=holes, closed=True)
        finally:
            self._loading_catalog_profile = False
        self._active_catalog_profile = profile.name
        self._active_library_shape = None
        self._active_library_dimensions = None
        self._select_material_type("steel")
        if update_name:
            self._edit_name.setText(profile.name)
        self._invalidate_result()
        self._refresh_contour_combo()
        self._refresh_points()
        self._refresh_status()
        self._side_tabs.setCurrentIndex(1)
        self._view.fit_section_to_view()
        self._lbl_status.setText(
            self.tr("Profil {profile} insere depuis la bibliotheque standard.").format(
                profile=profile.name,
            )
        )
        return True

    def _insert_library_shape(
        self,
        *,
        show_errors: bool,
        update_name: bool = True,
    ) -> bool:
        """Insert a sectionproperties library shape into the editable canvas."""
        if not self._sectionproperties_available:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("sectionproperties indisponible"),
                    self.tr("Installez sectionproperties pour charger sa bibliotheque."),
                )
            return False

        shape_key = str(self._combo_shape.currentData() or "rectangular")
        dimensions = self._current_dimensions()
        error_code = validate_sectionproperty_dimensions(shape_key, dimensions)
        if error_code is not None:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Geometrie de section invalide"),
                    self._validation_message(error_code),
                )
            return False

        shape = get_sectionproperty_shape(shape_key)
        display_properties = display_properties_for_shape(shape_key, dimensions)
        outer = _section_outer_polygon(shape.display_type, display_properties)
        inner = _section_inner_polygon(shape.display_type, display_properties)
        if not outer:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Import impossible"),
                    self.tr("La forme selectionnee ne peut pas etre convertie en contour."),
                )
            return False

        self._set_comfortable_grid_for_geometry(outer, [inner] if inner else [])
        self._loading_library_shape = True
        try:
            self._view.set_geometry(outer, holes=[inner] if inner else [], closed=True)
        finally:
            self._loading_library_shape = False
        self._active_library_shape = shape_key
        self._active_library_dimensions = dict(dimensions)
        self._active_catalog_profile = None
        self._chk_use_sectionproperties.setChecked(True)
        self._select_material_type(shape.default_material_type)
        if update_name and self._edit_name.text().strip() in {
            "",
            self.tr("Section personnalisÃ©e"),
        }:
            self._edit_name.setText(self._shape_label(shape_key))
        self._invalidate_result()
        self._refresh_contour_combo()
        self._refresh_points()
        self._refresh_status()
        self._side_tabs.setCurrentIndex(1)
        self._view.fit_section_to_view()
        self._lbl_status.setText(
            self.tr("Forme {shape} inseree depuis la bibliotheque sectionproperties.").format(
                shape=self._shape_label(shape_key),
            )
        )
        return True

    def _set_comfortable_grid_for_geometry(
        self,
        outer: list[Point2D],
        holes: list[list[Point2D]],
    ) -> None:
        """Use a readable grid spacing for small imported library sections."""
        points = list(outer)
        for hole in holes:
            points.extend(hole)
        if not points:
            return
        ys = [point[0] for point in points]
        zs = [point[1] for point in points]
        max_extent = max(max(ys) - min(ys), max(zs) - min(zs))
        if max_extent <= 0.0:
            return
        target = max_extent / 30.0
        exponent = math.floor(math.log10(target))
        base = 10.0 ** exponent
        ratio = target / base
        if ratio <= 1.0:
            nice = 1.0
        elif ratio <= 2.0:
            nice = 2.0
        elif ratio <= 5.0:
            nice = 5.0
        else:
            nice = 10.0
        step = min(max(nice * base, self._spin_grid.minimum()), self._spin_grid.maximum())
        self._spin_grid.setValue(step)

    def _builder_state(self) -> dict:
        """Return serializable Section Builder state."""
        return {
            "version": 1,
            "name": self._edit_name.text().strip(),
            "material_tag": self._combo_material.currentData() or 0,
            "points": self._view.points(),
            "holes": self._view.holes(),
            "closed": self._view.is_closed(),
            "grid_step": self._spin_grid.value(),
            "snap": self._chk_snap.isChecked(),
            "mesh_area": self._spin_mesh_area.value(),
            "use_sectionproperties": self._chk_use_sectionproperties.isChecked(),
            "library_shape": self._active_library_shape,
            "library_dimensions": self._active_library_dimensions,
        }

    def _load_builder_state(self, state: dict) -> None:
        """Load a serialized Section Builder state."""
        self._edit_name.setText(str(state.get("name", "") or self.tr("Section personnalisÃ©e")))
        material_tag = state.get("material_tag")
        if isinstance(material_tag, int):
            self._select_material_tag(material_tag)
        self._spin_grid.setValue(float(state.get("grid_step", self._spin_grid.value())))
        self._chk_snap.setChecked(bool(state.get("snap", True)))
        self._spin_mesh_area.setValue(float(state.get("mesh_area", self._spin_mesh_area.value())))
        if self._sectionproperties_available:
            self._chk_use_sectionproperties.setChecked(
                bool(state.get("use_sectionproperties", True))
            )

        library_shape = state.get("library_shape")
        library_dimensions = state.get("library_dimensions")
        if isinstance(library_shape, str):
            index = self._combo_shape.findData(library_shape)
            if index >= 0:
                self._combo_shape.setCurrentIndex(index)
                if isinstance(library_dimensions, dict):
                    for key, value in library_dimensions.items():
                        spin = self._dimension_spins.get(str(key))
                        if spin is not None:
                            spin.setValue(float(value))
                self._insert_library_shape(show_errors=False, update_name=False)
                return

        points = state.get("points", [])
        holes = state.get("holes", [])
        if isinstance(points, list):
            self._view.set_geometry(
                points,
                holes=holes if isinstance(holes, list) else [],
                closed=bool(state.get("closed", False)),
            )
        self._active_library_shape = None
        self._active_library_dimensions = None
        self._invalidate_result()
        self._refresh_contour_combo()
        self._refresh_points()
        self._refresh_status()

    def _new_builder_file(self) -> None:
        """Reset the current Section Builder document."""
        self._current_file_path = None
        self._active_library_shape = None
        self._active_library_dimensions = None
        self._edit_name.setText(self.tr("Section personnalisÃ©e"))
        self._view.clear_section()
        self._invalidate_result()
        self._side_tabs.setCurrentIndex(0)

    def _open_builder_file(self) -> None:
        """Open a saved Section Builder document."""
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Ouvrir une section"),
            "",
            self.tr("Section Builder (*.hexa-section-builder.json *.json)"),
        )
        if not file_name:
            return
        try:
            state = json.loads(Path(file_name).read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("invalid_state")
            self._load_builder_state(state)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(
                self,
                self.tr("Ouverture impossible"),
                self.tr("Le fichier ne peut pas etre lu.\n{error}").format(error=str(exc)),
            )
            return
        self._current_file_path = Path(file_name)

    def _save_builder_file(self) -> None:
        """Save the current Section Builder document."""
        if self._current_file_path is None:
            self._save_builder_file_as()
            return
        self._write_builder_state(self._current_file_path)

    def _save_builder_file_as(self) -> None:
        """Save the current Section Builder document under a new path."""
        file_name, _filter = QFileDialog.getSaveFileName(
            self,
            self.tr("Enregistrer la section"),
            "",
            self.tr("Section Builder (*.hexa-section-builder.json)"),
        )
        if not file_name:
            return
        path = Path(file_name)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".hexa-section-builder.json")
        self._write_builder_state(path)
        self._current_file_path = path

    def _write_builder_state(self, path: Path) -> None:
        try:
            path.write_text(
                json.dumps(self._builder_state(), indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                self.tr("Enregistrement impossible"),
                self.tr("Le fichier ne peut pas etre ecrit.\n{error}").format(error=str(exc)),
            )

    def _show_results_summary(self) -> None:
        """Show current analysis results."""
        if self._result is None and not self._analyze(show_errors=True):
            return
        self._side_tabs.setCurrentIndex(2)
        QMessageBox.information(
            self,
            self.tr("Resultats"),
            self._lbl_results.text() or self.tr("Aucun resultat disponible."),
        )

    def _show_stress_dialog(self) -> None:
        """Open the sectionproperties stress plotting dialog."""
        if not self._sectionproperties_available:
            QMessageBox.warning(
                self,
                self.tr("sectionproperties indisponible"),
                self.tr("Installez sectionproperties pour calculer les contraintes."),
            )
            return
        if not self._view.is_closed():
            QMessageBox.warning(
                self,
                self.tr("Contour non ferme"),
                self.tr("Fermez le contour avant de calculer les contraintes."),
            )
            return
        try:
            dialog = SectionStressDialog(self)
        except RuntimeError as exc:
            QMessageBox.warning(
                self,
                self.tr("Matplotlib indisponible"),
                self.tr("Matplotlib ne peut pas etre charge.\n{error}").format(
                    error=str(exc)
                ),
            )
            return
        dialog.exec()

    def _connect_signals(self) -> None:
        self.act_new.triggered.connect(self._new_builder_file)
        self.act_open.triggered.connect(self._open_builder_file)
        self.act_import_shape.triggered.connect(self._show_standard_profile_import_dialog)
        self.act_save.triggered.connect(self._save_builder_file)
        self.act_save_as.triggered.connect(self._save_builder_file_as)
        self.act_quit.triggered.connect(self.reject)
        self.act_sp_insert_library.triggered.connect(lambda: self._insert_library_shape(show_errors=True))
        self.act_sp_calculate.triggered.connect(lambda: self._analyze(show_errors=True))
        self.act_sp_results.triggered.connect(self._show_results_summary)
        self.act_sp_show_stress.triggered.connect(self._show_stress_dialog)
        self._tool_action_group.triggered.connect(self._on_tool_action_triggered)
        self._combo_tool.currentIndexChanged.connect(self._on_tool_combo_changed)
        self.act_canvas_zoom_in.triggered.connect(self._view.zoom_in)
        self.act_canvas_zoom_out.triggered.connect(self._view.zoom_out)
        self.act_canvas_fit.triggered.connect(self._view.fit_section_to_view)
        self._view.geometry_changed.connect(self._on_geometry_changed)
        self._view.closed_changed.connect(lambda _closed: self._refresh_status())
        self._view.tool_changed.connect(self._on_view_tool_changed)
        self._spin_grid.valueChanged.connect(self._view.set_grid_step)
        self._chk_snap.toggled.connect(self._on_snap_toggled)
        self._combo_shape.currentIndexChanged.connect(self._on_shape_changed)
        self._btn_insert_shape.clicked.connect(lambda: self._insert_library_shape(show_errors=True))
        self._chk_use_sectionproperties.toggled.connect(lambda _checked: self._invalidate_result())
        self._spin_mesh_area.valueChanged.connect(lambda _value: self._invalidate_result())
        self._chk_show_mesh.toggled.connect(self._on_mesh_visible_toggled)
        self._combo_contour.currentIndexChanged.connect(self._on_contour_changed)
        self._table_points.itemChanged.connect(self._on_point_table_item_changed)
        self._btn_close.clicked.connect(self._close_contour)
        self._btn_undo.clicked.connect(self._view.remove_last_point)
        self._btn_insert.clicked.connect(self._insert_point)
        self._btn_delete.clicked.connect(self._delete_selected_point)
        self._btn_add_hole.clicked.connect(self._add_hole)
        self._btn_delete_hole.clicked.connect(self._delete_selected_hole)
        self._btn_clear.clicked.connect(self._view.clear_section)
        self._btn_analyze.clicked.connect(lambda: self._analyze(show_errors=True))
        self._button_box.accepted.connect(self._accept)
        self._button_box.rejected.connect(self.reject)

    def _on_tool_action_triggered(self, action: QAction) -> None:
        mode = str(action.data() or "polygon")
        self._view.set_tool_mode(mode)

    def _on_tool_combo_changed(self, *_args) -> None:
        mode = str(self._combo_tool.currentData() or "polygon")
        self._view.set_tool_mode(mode)

    def _on_view_tool_changed(self, mode: str) -> None:
        action = self._tool_actions.get(mode)
        if action is not None:
            action.setChecked(True)
        index = self._combo_tool.findData(mode)
        if index >= 0 and index != self._combo_tool.currentIndex():
            was_blocked = self._combo_tool.blockSignals(True)
            try:
                self._combo_tool.setCurrentIndex(index)
            finally:
                self._combo_tool.blockSignals(was_blocked)
        self._refresh_status()

    def _tool_label(self, mode: str) -> str:
        labels = {
            "select": self.tr("Selection"),
            "polygon": self.tr("Polygone"),
            "rectangle": self.tr("Rectangle"),
            "circle": self.tr("Cercle"),
            "hole": self.tr("Trou"),
            "move": self.tr("Deplacer point"),
            "delete": self.tr("Supprimer point"),
        }
        return labels.get(mode, mode)

    def _on_geometry_changed(self) -> None:
        if not self._loading_library_shape:
            self._active_library_shape = None
            self._active_library_dimensions = None
        if not self._loading_catalog_profile:
            self._active_catalog_profile = None
        self._invalidate_result()
        self._refresh_contour_combo()
        self._refresh_points()
        self._refresh_status()

    def _invalidate_result(self) -> None:
        self._properties = None
        self._sectionproperties_result = None
        self._sectionproperties_stress_result = None
        self._result = None
        self._view.set_centroid(None)
        self._view.set_mesh(None)
        ok_button = self._button_box.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setEnabled(False)

    def _refresh_points(self) -> None:
        points = self._view.current_points()
        self._updating_points_table = True
        try:
            self._table_points.setRowCount(len(points))
            for row, (y_value, z_value) in enumerate(points):
                self._table_points.setItem(row, 0, QTableWidgetItem(f"{y_value:.3f}"))
                self._table_points.setItem(row, 1, QTableWidgetItem(f"{z_value:.3f}"))
        finally:
            self._updating_points_table = False
        self._refresh_dimensions()

    def _refresh_status(self) -> None:
        points = self._view.current_points()
        contour_kind, hole_index = self._view.active_contour()
        mode = self._view.tool_mode()
        self._btn_insert.setEnabled(bool(points))
        self._btn_delete.setEnabled(bool(points))
        self._btn_delete_hole.setEnabled(contour_kind == "hole" and hole_index is not None)
        if self._view.has_open_holes():
            self._btn_analyze.setEnabled(False)
        elif self._view.is_closed():
            self._btn_analyze.setEnabled(True)
        else:
            self._btn_analyze.setEnabled(False)
        if self._view.current_is_closed():
            label = (
                self.tr("Trou {index} ferme : {count} point(s).").format(
                    index=(hole_index or 0) + 1,
                    count=len(points),
                )
                if contour_kind == "hole"
                else self.tr("Contour ferme : {count} point(s).").format(count=len(points))
            )
            self._lbl_status.setText(label)
        elif mode == "rectangle":
            self._lbl_status.setText(self.tr("Rectangle : cliquez-glissez pour definir deux coins."))
        elif mode == "circle":
            self._lbl_status.setText(self.tr("Cercle : cliquez au centre puis glissez le rayon."))
        elif mode == "move":
            self._lbl_status.setText(self.tr("Deplacer point : glissez un point du contour actif."))
        elif mode == "delete":
            self._lbl_status.setText(self.tr("Supprimer point : cliquez un point du contour actif."))
        elif mode == "select":
            self._lbl_status.setText(self.tr("Selection : cliquez un point du contour actif."))
        elif contour_kind == "hole":
            self._lbl_status.setText(
                self.tr(
                    "Dessinez le contour du trou. Cliquez pres du premier point ou utilisez Fermer le contour."
                )
            )
        elif mode == "hole":
            self._lbl_status.setText(self.tr("Trou : fermez le contour exterieur, puis dessinez le trou."))
        else:
            self._lbl_status.setText(
                self.tr(
                    "Cliquez sur la grille pour dessiner le contour. Cliquez pres du premier point ou utilisez Fermer le contour."
                )
            )

    def _refresh_contour_combo(self) -> None:
        contour_kind, hole_index = self._view.active_contour()
        was_blocked = self._combo_contour.blockSignals(True)
        try:
            self._combo_contour.clear()
            self._combo_contour.addItem(self.tr("Contour exterieur"), ("outer", -1))
            for index in range(self._view.hole_count()):
                label = self.tr("Trou {index}").format(index=index + 1)
                if not self._view.is_hole_closed(index):
                    label = self.tr("{label} (ouvert)").format(label=label)
                self._combo_contour.addItem(label, ("hole", index))
            target_data = (contour_kind, hole_index if hole_index is not None else -1)
            for index in range(self._combo_contour.count()):
                if self._combo_contour.itemData(index) == target_data:
                    self._combo_contour.setCurrentIndex(index)
                    break
        finally:
            self._combo_contour.blockSignals(was_blocked)

    def _on_contour_changed(self) -> None:
        data = self._combo_contour.currentData()
        if not isinstance(data, tuple) or len(data) != 2:
            return
        kind, index = data
        if kind == "hole":
            self._view.select_hole_contour(int(index))
        else:
            self._view.select_outer_contour()
        self._refresh_points()
        self._refresh_status()

    def _add_hole(self) -> None:
        if not self._view.is_closed():
            QMessageBox.warning(
                self,
                self.tr("Contour exterieur requis"),
                self.tr("Fermez le contour exterieur avant d'ajouter un trou."),
            )
            return
        self._view.start_hole()
        self._view.set_tool_mode("hole")
        self._refresh_contour_combo()
        self._refresh_points()
        self._refresh_status()

    def _delete_selected_hole(self) -> None:
        if not self._view.delete_active_hole():
            return
        self._refresh_contour_combo()
        self._refresh_points()
        self._refresh_status()

    def _refresh_dimensions(self) -> None:
        points = self._view.current_points()
        if not points:
            self._lbl_dimensions.setText(self.tr("Aucun point."))
            return
        ys = [point[0] for point in points]
        zs = [point[1] for point in points]
        if self._view.is_closed():
            perimeter_text = self.tr(" - Perimetre : {perimeter:.3f} m").format(
                perimeter=polygon_perimeter(points)
            )
        else:
            perimeter_text = ""
        self._lbl_dimensions.setText(
            self.tr("Points : {count} - Dimensions : {width:.3f} m x {height:.3f} m{perimeter}").format(
                count=len(points),
                width=max(ys) - min(ys),
                height=max(zs) - min(zs),
                perimeter=perimeter_text,
            )
        )

    def _selected_point_row(self) -> int | None:
        row = self._table_points.currentRow()
        if row < 0 or row >= len(self._view.current_points()):
            return None
        return row

    def _insert_point(self) -> None:
        row = self._selected_point_row()
        inserted = self._view.insert_point_after(row)
        self._table_points.selectRow(inserted)

    def _delete_selected_point(self) -> None:
        row = self._selected_point_row()
        if row is None:
            return
        self._view.remove_point(row)
        if self._table_points.rowCount():
            self._table_points.selectRow(min(row, self._table_points.rowCount() - 1))

    def _on_point_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_points_table:
            return
        row = item.row()
        y_item = self._table_points.item(row, 0)
        z_item = self._table_points.item(row, 1)
        if y_item is None or z_item is None:
            return
        try:
            point = (float(y_item.text().replace(",", ".")), float(z_item.text().replace(",", ".")))
        except ValueError:
            self._refresh_points()
            return
        self._view.set_point(row, point)

    def _on_snap_toggled(self, checked: bool) -> None:
        self._view.set_snap_enabled(checked)
        if checked:
            self._chk_snap.setText(self.tr("Accrochage grille actif"))
        else:
            self._chk_snap.setText(self.tr("Accrochage grille inactif"))

    def _on_mesh_visible_toggled(self, checked: bool) -> None:
        self._view.set_mesh_visible(checked)
        mesh = self._sectionproperties_result.mesh if self._sectionproperties_result else None
        self._view.set_mesh(mesh if checked else None)

    def _close_contour(self) -> None:
        if not self._view.close_contour():
            QMessageBox.warning(
                self,
                self.tr("Contour incomplet"),
                self.tr("Le contour doit contenir au moins trois points."),
            )

    def _analyze(self, *, show_errors: bool) -> bool:
        if not self._view.is_closed():
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Contour non ferme"),
                    self.tr("Fermez le contour avant l'analyse."),
                )
            return False
        if self._view.has_open_holes():
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Trou incomplet"),
                    self.tr("Fermez ou supprimez le trou en cours avant l'analyse."),
                )
            return False
        try:
            props = polygon_section_properties(self._view.points())
        except SectionBuilderGeometryError as exc:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Analyse impossible"),
                    self._geometry_error_message(exc),
                )
            return False
        except ValueError as exc:
            if show_errors:
                QMessageBox.warning(self, self.tr("Analyse impossible"), str(exc))
            return False

        if self._active_catalog_profile is not None:
            try:
                profile = get_profile(self._active_catalog_profile)
            except KeyError:
                if show_errors:
                    QMessageBox.warning(
                        self,
                        self.tr("Profil introuvable"),
                        self.tr(
                            "Le profil selectionne n'existe plus dans le catalogue."
                        ),
                    )
                return False
            sp_result = self._calculate_with_sectionproperties(show_errors=show_errors)
            self._properties = props
            self._sectionproperties_result = sp_result
            self._result = self._build_standard_profile_result(profile, props, sp_result)
            centroid = (
                float(sp_result.properties.get("centroid_local_y", props.centroid_y))
                if sp_result
                else props.centroid_y,
                float(sp_result.properties.get("centroid_local_z", props.centroid_z))
                if sp_result
                else props.centroid_z,
            )
            self._view.set_centroid(centroid)
            mesh = sp_result.mesh if sp_result and self._chk_show_mesh.isChecked() else None
            self._view.set_mesh(mesh)
            self._lbl_results.setText(
                self._standard_profile_summary(profile, props, sp_result)
            )
            ok_button = self._button_box.button(QDialogButtonBox.Ok)
            if ok_button is not None:
                ok_button.setEnabled(True)
            return True

        if self._active_library_shape is not None:
            sp_result = self._calculate_library_sectionproperties(show_errors=show_errors)
            if sp_result is None:
                return False
            self._properties = props
            self._sectionproperties_result = sp_result
            self._result = self._build_sectionproperties_library_result(sp_result)
            centroid = (
                float(sp_result.properties.get("centroid_local_y", 0.0)),
                float(sp_result.properties.get("centroid_local_z", 0.0)),
            )
            self._view.set_centroid(centroid)
            mesh = sp_result.mesh if self._chk_show_mesh.isChecked() else None
            self._view.set_mesh(mesh)
            self._lbl_results.setText(self._analysis_summary(props, sp_result))
            ok_button = self._button_box.button(QDialogButtonBox.Ok)
            if ok_button is not None:
                ok_button.setEnabled(True)
            return True

        sp_result = self._calculate_with_sectionproperties(show_errors=show_errors)
        if self._view.holes() and sp_result is None:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("sectionproperties requis"),
                    self.tr("Les sections avec trous necessitent sectionproperties."),
                )
            return False
        self._properties = props
        self._sectionproperties_result = sp_result
        self._result = self._build_result(props, sp_result)
        centroid = (
            self._result["properties"]["centroid_y"],
            self._result["properties"]["centroid_z"],
        )
        self._view.set_centroid(centroid)
        mesh = sp_result.mesh if sp_result and self._chk_show_mesh.isChecked() else None
        self._view.set_mesh(mesh)
        self._lbl_results.setText(self._analysis_summary(props, sp_result))
        ok_button = self._button_box.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setEnabled(True)
        return True

    def _calculate_library_sectionproperties(
        self,
        *,
        show_errors: bool,
    ) -> SectionPropertiesResult | None:
        """Calculate the active library shape using sectionproperties directly."""
        if self._active_library_shape is None:
            return None
        dimensions = self._active_library_dimensions or self._current_dimensions()
        error_code = validate_sectionproperty_dimensions(
            self._active_library_shape,
            dimensions,
        )
        if error_code is not None:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Geometrie de section invalide"),
                    self._validation_message(error_code),
                )
            return None
        try:
            return calculate_sectionproperties_section(
                self._active_library_shape,
                dimensions,
                mesh_area=self._spin_mesh_area.value(),
            )
        except SectionPropertiesUnavailable:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("sectionproperties indisponible"),
                    self.tr("Installez sectionproperties pour calculer cette section."),
                )
            return None
        except SectionPropertiesCalculationError as exc:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Calcul sectionproperties impossible"),
                    str(exc),
                )
            return None

    def _calculate_with_sectionproperties(
        self,
        *,
        show_errors: bool,
    ) -> SectionPropertiesResult | None:
        holes = self._view.holes()
        if not self._chk_use_sectionproperties.isChecked() and not holes:
            return None
        try:
            return calculate_polygon_sectionproperties_section(
                self._view.points(),
                holes=holes,
                mesh_area=self._spin_mesh_area.value(),
            )
        except SectionPropertiesUnavailable:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("sectionproperties indisponible"),
                    self.tr("Le calcul polygonal simple sera utilise."),
                )
            return None
        except SectionPropertiesCalculationError as exc:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Calcul sectionproperties impossible"),
                    self.tr("Le calcul polygonal simple sera utilise.\n{error}").format(
                        error=str(exc)
                    ),
                )
            return None

    def _calculate_stress_result(
        self,
        *,
        stress_key: str,
        actions: dict[str, float],
        show_errors: bool,
    ) -> SectionPropertiesStressResult | None:
        try:
            result = calculate_polygon_sectionproperties_stress(
                self._view.points(),
                holes=self._view.holes(),
                mesh_area=self._spin_mesh_area.value(),
                stress_key=stress_key,
                n=actions.get("n", 0.0),
                vx=actions.get("vx", 0.0),
                vy=actions.get("vy", 0.0),
                mxx=actions.get("mxx", 0.0),
                myy=actions.get("myy", 0.0),
                mzz=actions.get("mzz", 0.0),
            )
        except SectionPropertiesUnavailable:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("sectionproperties indisponible"),
                    self.tr("Installez sectionproperties pour calculer les contraintes."),
                )
            return None
        except SectionPropertiesCalculationError as exc:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Calcul des contraintes impossible"),
                    str(exc),
                )
            return None
        self._sectionproperties_stress_result = result
        if result.mesh is not None:
            self._view.set_mesh(result.mesh if self._chk_show_mesh.isChecked() else None)
        return result

    def _analysis_summary(
        self,
        props: PolygonSectionProperties,
        sp_result: SectionPropertiesResult | None,
    ) -> str:
        area = sp_result.area if sp_result else props.area
        inertia_y = sp_result.inertia_y if sp_result else props.inertia_y
        inertia_z = sp_result.inertia_z if sp_result else props.inertia_z
        centroid_y = (
            float(sp_result.properties.get("centroid_local_y", props.centroid_y))
            if sp_result
            else props.centroid_y
        )
        centroid_z = (
            float(sp_result.properties.get("centroid_local_z", props.centroid_z))
            if sp_result
            else props.centroid_z
        )
        engine = "sectionproperties" if sp_result else self.tr("polygonal")
        lines = [
            self.tr("Moteur : {engine}").format(engine=engine),
            "A = {area:.2f} cm2".format(area=area * 1.0e4),
            "P = {perimeter:.3f} m".format(perimeter=props.perimeter),
            "Iy = {iy:.2f} cm4".format(iy=inertia_y * 1.0e8),
            "Iz = {iz:.2f} cm4".format(iz=inertia_z * 1.0e8),
            "Cy = {cy:.3f} m, Cz = {cz:.3f} m".format(
                cy=centroid_y,
                cz=centroid_z,
            ),
        ]
        if self._view.holes():
            lines.append(self.tr("Trous : {count}").format(count=len(self._view.holes())))
        if sp_result:
            lines.append("Iyz = {ixy:.2f} cm4".format(ixy=sp_result.ixy * 1.0e8))
            lines.append(
                "J = {j:.2f} cm4".format(j=sp_result.torsion_constant * 1.0e8)
            )
            if sp_result.mesh:
                lines.append(
                    self.tr("Maillage : {nodes} noeuds, {triangles} triangles").format(
                        nodes=len(sp_result.mesh.vertices),
                        triangles=len(sp_result.mesh.triangles),
                    )
                )
        return "\n".join(lines)

    def _standard_profile_summary(
        self,
        profile: SteelProfile,
        props: PolygonSectionProperties,
        sp_result: SectionPropertiesResult | None,
    ) -> str:
        area = sp_result.area if sp_result else profile.area
        inertia_y = sp_result.inertia_y if sp_result else profile.inertia_y
        inertia_z = sp_result.inertia_z if sp_result else profile.inertia_z
        centroid_y = (
            float(sp_result.properties.get("centroid_local_y", props.centroid_y))
            if sp_result
            else props.centroid_y
        )
        centroid_z = (
            float(sp_result.properties.get("centroid_local_z", props.centroid_z))
            if sp_result
            else props.centroid_z
        )
        engine = (
            self.tr("catalogue standard + sectionproperties")
            if sp_result
            else self.tr("catalogue standard")
        )
        lines = [
            self.tr("Moteur : {engine}").format(engine=engine),
            "A = {area:.2f} cm2".format(area=area * 1.0e4),
            "P = {perimeter:.3f} m".format(perimeter=props.perimeter),
            "Iy = {iy:.2f} cm4".format(iy=inertia_y * 1.0e8),
            "Iz = {iz:.2f} cm4".format(iz=inertia_z * 1.0e8),
            "Cy = {cy:.3f} m, Cz = {cz:.3f} m".format(
                cy=centroid_y,
                cz=centroid_z,
            ),
            self.tr("Catalogue : {profile}").format(profile=profile.name),
        ]
        if self._view.holes():
            lines.append(self.tr("Trous : {count}").format(count=len(self._view.holes())))
        if sp_result:
            lines.append("Iyz = {ixy:.2f} cm4".format(ixy=sp_result.ixy * 1.0e8))
            lines.append(
                "J = {j:.2f} cm4".format(j=sp_result.torsion_constant * 1.0e8)
            )
            if sp_result.mesh:
                lines.append(
                    self.tr("Maillage : {nodes} noeuds, {triangles} triangles").format(
                        nodes=len(sp_result.mesh.vertices),
                        triangles=len(sp_result.mesh.triangles),
                    )
                )
        return "\n".join(lines)

    def _build_result(
        self,
        props: PolygonSectionProperties,
        sp_result: SectionPropertiesResult | None,
    ) -> dict:
        points = self._view.points()
        area = sp_result.area if sp_result else props.area
        inertia_y = sp_result.inertia_y if sp_result else props.inertia_y
        inertia_z = sp_result.inertia_z if sp_result else props.inertia_z
        centroid_y = (
            float(sp_result.properties.get("centroid_local_y", props.centroid_y))
            if sp_result
            else props.centroid_y
        )
        centroid_z = (
            float(sp_result.properties.get("centroid_local_z", props.centroid_z))
            if sp_result
            else props.centroid_z
        )
        section_properties = {
            "source": "section_builder",
            "analysis_engine": "sectionproperties" if sp_result else "polygonal",
            "points": points,
            "holes": self._view.holes(),
            "hole_count": len(self._view.holes()),
            "closed": True,
            "perimeter": props.perimeter,
            "centroid_y": centroid_y,
            "centroid_z": centroid_z,
        }
        if sp_result:
            section_properties["sectionproperties"] = {
                "mesh_area": self._spin_mesh_area.value(),
                "ixy": sp_result.ixy,
                "torsion_constant": sp_result.torsion_constant,
                "mesh_node_count": len(sp_result.mesh.vertices)
                if sp_result.mesh
                else 0,
                "mesh_triangle_count": len(sp_result.mesh.triangles)
                if sp_result.mesh
                else 0,
            }
            if sp_result.torsion_constant > 0.0:
                section_properties["torsion_constant"] = sp_result.torsion_constant
                section_properties["torsion_j"] = sp_result.torsion_constant
                section_properties["J"] = sp_result.torsion_constant
        return {
            "name": self._edit_name.text().strip() or self.tr("Section personnalisée"),
            "section_type": "custom_polygon",
            "material_tag": self._combo_material.currentData() or 0,
            "properties": section_properties,
            "area": area,
            "inertia_y": inertia_y,
            "inertia_z": inertia_z,
        }

    def _build_sectionproperties_library_result(
        self,
        sp_result: SectionPropertiesResult,
    ) -> dict:
        """Build a ProjectModel section payload for an inserted library shape."""
        properties = dict(sp_result.properties)
        properties["source_tool"] = "section_builder"
        properties["points"] = self._view.points()
        properties["holes"] = self._view.holes()
        properties["hole_count"] = len(self._view.holes())
        properties["analysis_engine"] = "sectionproperties"
        if self._active_library_dimensions is not None:
            properties["dimensions"] = dict(self._active_library_dimensions)
        return {
            "name": self._edit_name.text().strip() or self._shape_label(
                str(properties.get("shape", ""))
            ),
            "section_type": "sectionproperties",
            "material_tag": self._combo_material.currentData() or 0,
            "properties": properties,
            "area": sp_result.area,
            "inertia_y": sp_result.inertia_y,
            "inertia_z": sp_result.inertia_z,
        }

    def _build_standard_profile_result(
        self,
        profile: SteelProfile,
        props: PolygonSectionProperties,
        sp_result: SectionPropertiesResult | None,
    ) -> dict:
        """Build a ProjectModel payload for a standard catalog profile."""
        properties = {
            "profile": profile.name,
            "source": "profile_catalog",
            "source_tool": "section_builder",
            "analysis_engine": "sectionproperties" if sp_result else "profile_catalog",
            "family": profile.family,
            "shape": profile.shape,
            "points": self._view.points(),
            "holes": self._view.holes(),
            "hole_count": len(self._view.holes()),
            "closed": True,
            "perimeter": props.perimeter,
            "centroid_y": props.centroid_y,
            "centroid_z": props.centroid_z,
        }
        if sp_result:
            properties["sectionproperties"] = {
                "mesh_area": self._spin_mesh_area.value(),
                "area": sp_result.area,
                "inertia_y": sp_result.inertia_y,
                "inertia_z": sp_result.inertia_z,
                "ixy": sp_result.ixy,
                "torsion_constant": sp_result.torsion_constant,
                "mesh_node_count": len(sp_result.mesh.vertices)
                if sp_result.mesh
                else 0,
                "mesh_triangle_count": len(sp_result.mesh.triangles)
                if sp_result.mesh
                else 0,
            }
        if profile.inertia_torsion > 0.0:
            properties["torsion_constant"] = profile.inertia_torsion
            properties["torsion_j"] = profile.inertia_torsion
            properties["J"] = profile.inertia_torsion
        return {
            "name": self._edit_name.text().strip() or profile.name,
            "section_type": "I_profile",
            "material_tag": self._combo_material.currentData() or 0,
            "properties": properties,
            "area": profile.area,
            "inertia_y": profile.inertia_y,
            "inertia_z": profile.inertia_z,
        }

    def _accept(self) -> None:
        if self._result is None and not self._analyze(show_errors=True):
            return
        self.accept()

    def _geometry_error_message(self, error: SectionBuilderGeometryError) -> str:
        messages = {
            "polygon_min_points": self.tr("Le contour doit contenir au moins trois points."),
            "polygon_duplicate_point": self.tr("Le contour contient deux points consecutifs identiques."),
            "polygon_crossing_edges": self.tr("Le contour contient des segments qui se croisent."),
            "polygon_zero_area": self.tr("L'aire du contour est nulle."),
        }
        return messages.get(error.code, str(error))
