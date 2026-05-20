"""Vue 2D de file pour le dessin sur grille."""

from __future__ import annotations

from string import ascii_uppercase
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from core.model_data import Grid3DData, ProjectModel


class PlaneEditorView(QWidget):
    """Vue 2D d'une file active de la grille."""

    grid_point_picked = Signal(float, float, float)
    draw_finalize_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: ProjectModel | None = None
        self._plane = "XZ"
        self._value: float | None = None
        self._draw_mode = False
        self._draw_start_point: tuple[float, float, float] | None = None
        self._hover_point: tuple[float, float, float] | None = None
        self.setMinimumWidth(360)
        self.setMouseTracking(True)
        self.setAutoFillBackground(True)

    def set_project(self, project: ProjectModel) -> None:
        """Assigne le projet courant."""
        self._project = project
        self.update()

    def set_plane_context(self, plane: str, value: float | None) -> None:
        """Définit le plan actif et la valeur de la file."""
        self._plane = plane
        self._value = value
        self.update()

    def set_drawing_mode(self, enabled: bool) -> None:
        """Active ou désactive le mode dessin."""
        self._draw_mode = enabled
        if not enabled:
            self._hover_point = None
        self.update()

    def set_preview_start(self, point: tuple[float, float, float] | None) -> None:
        """Définit le point de départ de la barre en cours."""
        self._draw_start_point = point
        self.update()

    def clear_drawing_state(self) -> None:
        """Efface les repères de dessin."""
        self._draw_start_point = None
        self._hover_point = None
        self.update()

    def mouseMoveEvent(self, event) -> None:
        """Met à jour la prévisualisation pendant le dessin."""
        if not self._draw_mode or self._draw_start_point is None:
            self._hover_point = None
            self.update()
            return
        point = self._nearest_grid_point(event.position())
        self._hover_point = point
        self.update()

    def leaveEvent(self, event) -> None:
        """Efface le point survolé à la sortie."""
        self._hover_point = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        """Envoie le point de grille sélectionné."""
        if event.button() == Qt.RightButton and self._draw_mode:
            self.draw_finalize_requested.emit()
            return
        if event.button() != Qt.LeftButton:
            return
        point = self._nearest_grid_point(event.position())
        if point is None:
            return
        self.grid_point_picked.emit(point[0], point[1], point[2])

    def paintEvent(self, event) -> None:
        """Dessine la file active et ses éléments."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self._project is None or not self._project.grid.enabled or self._value is None:
            painter.setPen(QColor("#999999"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Aucune file active")
            return

        grid_points = self._plane_grid_points(self._project.grid, self._plane, self._value)
        if not grid_points:
            painter.setPen(QColor("#999999"))
            painter.drawText(self.rect(), Qt.AlignCenter, "File vide")
            return

        bbox = self._compute_bbox(grid_points)
        draw_rect = QRectF(60.0, 40.0, max(10.0, self.width() - 90.0), max(10.0, self.height() - 80.0))

        self._draw_grid_lines(painter, grid_points, bbox, draw_rect)
        self._draw_existing_surfaces(painter, bbox, draw_rect)
        self._draw_existing_elements(painter, bbox, draw_rect)
        self._draw_supports(painter, bbox, draw_rect)
        self._draw_axis_labels(painter, grid_points, bbox, draw_rect)
        self._draw_preview(painter, bbox, draw_rect)

    def _draw_grid_lines(
        self,
        painter: QPainter,
        grid_points: list[tuple[float, float, float]],
        bbox: tuple[float, float, float, float],
        draw_rect: QRectF,
    ) -> None:
        """Dessine la grille 2D de la file."""
        pen = QPen(QColor("#e6e600"))
        pen.setWidth(1)
        painter.setPen(pen)

        xs = sorted({self._project_to_plane(point)[0] for point in grid_points})
        ys = sorted({self._project_to_plane(point)[1] for point in grid_points})

        for x in xs:
            p1 = self._map_to_widget((x, ys[0]), bbox, draw_rect)
            p2 = self._map_to_widget((x, ys[-1]), bbox, draw_rect)
            painter.drawLine(p1, p2)

        for y in ys:
            p1 = self._map_to_widget((xs[0], y), bbox, draw_rect)
            p2 = self._map_to_widget((xs[-1], y), bbox, draw_rect)
            painter.drawLine(p1, p2)

    def _draw_existing_elements(
        self,
        painter: QPainter,
        bbox: tuple[float, float, float, float],
        draw_rect: QRectF,
    ) -> None:
        """Dessine les barres appartenant à la file active."""
        if self._project is None:
            return
        pen = QPen(QColor("#ffff66"))
        pen.setWidth(2)
        painter.setPen(pen)

        for elem in self._project.elements.values():
            ni = self._project.nodes.get(elem.node_i)
            nj = self._project.nodes.get(elem.node_j)
            if ni is None or nj is None:
                continue
            if not self._point_on_plane((ni.x, ni.y, ni.z)):
                continue
            if not self._point_on_plane((nj.x, nj.y, nj.z)):
                continue

            p1 = self._map_to_widget(self._project_to_plane((ni.x, ni.y, ni.z)), bbox, draw_rect)
            p2 = self._map_to_widget(self._project_to_plane((nj.x, nj.y, nj.z)), bbox, draw_rect)
            painter.drawLine(p1, p2)

    def _draw_existing_surfaces(
        self,
        painter: QPainter,
        bbox: tuple[float, float, float, float],
        draw_rect: QRectF,
    ) -> None:
        """Dessine les surfaces de la file active comme aplats légers."""
        painter.setPen(QPen(QColor("#7fc8f8"), 1))
        painter.setBrush(QColor(127, 200, 248, 45))

        for polygon in self._surface_polygons_on_plane():
            if len(polygon) < 3:
                continue

            path = QPainterPath()
            first = self._map_to_widget(polygon[0], bbox, draw_rect)
            path.moveTo(first)
            for point in polygon[1:]:
                path.lineTo(self._map_to_widget(point, bbox, draw_rect))
            path.closeSubpath()
            painter.drawPath(path)

    def _surface_polygons_on_plane(self) -> list[list[tuple[float, float]]]:
        """Retourne les polygones des surfaces entièrement contenues dans la file."""
        if self._project is None:
            return []

        polygons: list[list[tuple[float, float]]] = []
        for surface in self._project.surface_elements.values():
            polygon: list[tuple[float, float]] = []
            for node_tag in surface.node_tags:
                node = self._project.nodes.get(node_tag)
                if node is None:
                    polygon = []
                    break
                point = (node.x, node.y, node.z)
                if not self._point_on_plane(point):
                    polygon = []
                    break
                polygon.append(self._project_to_plane(point))
            if len(polygon) >= 3:
                polygons.append(polygon)
        return polygons

    def _draw_supports(
        self,
        painter: QPainter,
        bbox: tuple[float, float, float, float],
        draw_rect: QRectF,
    ) -> None:
        """Dessine des appuis simplifiés sur la file."""
        if self._project is None:
            return
        painter.setPen(QPen(QColor("#00ff00"), 2))
        painter.setBrush(Qt.NoBrush)

        for node in self._project.nodes.values():
            if not node.is_support:
                continue
            if not self._point_on_plane((node.x, node.y, node.z)):
                continue
            p = self._map_to_widget(self._project_to_plane((node.x, node.y, node.z)), bbox, draw_rect)
            painter.drawRect(QRectF(p.x() - 10, p.y() - 10, 20, 20))

    def _draw_axis_labels(
        self,
        painter: QPainter,
        grid_points: list[tuple[float, float, float]],
        bbox: tuple[float, float, float, float],
        draw_rect: QRectF,
    ) -> None:
        """Dessine les repères d'axes comme aide de navigation."""
        painter.setPen(QColor("#00ff00"))
        xs = sorted({self._project_to_plane(point)[0] for point in grid_points})
        ys = sorted({self._project_to_plane(point)[1] for point in grid_points})

        for idx, x in enumerate(xs):
            p = self._map_to_widget((x, ys[-1]), bbox, draw_rect)
            label = ascii_uppercase[idx] if idx < len(ascii_uppercase) else str(idx + 1)
            painter.drawText(QRectF(p.x() - 15, 5, 30, 24), Qt.AlignCenter, label)

        for idx, y in enumerate(reversed(ys), start=1):
            p = self._map_to_widget((xs[0], y), bbox, draw_rect)
            painter.drawText(QRectF(5, p.y() - 10, 30, 20), Qt.AlignCenter, str(idx))

    def _draw_preview(
        self,
        painter: QPainter,
        bbox: tuple[float, float, float, float],
        draw_rect: QRectF,
    ) -> None:
        """Dessine le point de départ et la prévisualisation de la barre."""
        if self._draw_start_point is None:
            return

        start_2d = self._map_to_widget(
            self._project_to_plane(self._draw_start_point),
            bbox,
            draw_rect,
        )
        painter.setPen(QPen(QColor("#ffcc00"), 2))
        painter.setBrush(QColor("#ffcc00"))
        painter.drawEllipse(start_2d, 5, 5)

        if self._hover_point is None:
            return

        hover_2d = self._map_to_widget(
            self._project_to_plane(self._hover_point),
            bbox,
            draw_rect,
        )
        painter.setPen(QPen(QColor("#ff5555"), 2, Qt.DashLine))
        painter.setBrush(QColor("#ff5555"))
        painter.drawLine(start_2d, hover_2d)
        painter.drawEllipse(hover_2d, 4, 4)

    def _nearest_grid_point(self, position: QPointF) -> tuple[float, float, float] | None:
        """Retourne l'intersection de grille la plus proche du curseur."""
        if self._project is None or self._value is None:
            return None

        grid_points = self._plane_grid_points(self._project.grid, self._plane, self._value)
        if not grid_points:
            return None

        bbox = self._compute_bbox(grid_points)
        draw_rect = QRectF(60.0, 40.0, max(10.0, self.width() - 90.0), max(10.0, self.height() - 80.0))

        nearest = None
        best = float("inf")
        for point in grid_points:
            p = self._map_to_widget(self._project_to_plane(point), bbox, draw_rect)
            dist = ((p.x() - position.x()) ** 2 + (p.y() - position.y()) ** 2) ** 0.5
            if dist < best:
                best = dist
                nearest = point
        if best > 18.0:
            return None
        return nearest

    def _point_on_plane(self, point: tuple[float, float, float], tol: float = 1e-9) -> bool:
        """Indique si un point appartient à la file active."""
        if self._value is None:
            return False
        if self._plane == "XY":
            return abs(point[2] - self._value) <= tol
        if self._plane == "XZ":
            return abs(point[1] - self._value) <= tol
        if self._plane == "YZ":
            return abs(point[0] - self._value) <= tol
        return False

    @staticmethod
    def _plane_grid_points(
        grid: Grid3DData,
        plane: str,
        value: float,
    ) -> list[tuple[float, float, float]]:
        """Retourne les intersections de la file active."""
        xs = grid.axis_values("X")
        ys = grid.axis_values("Y")
        zs = grid.axis_values("Z")

        if plane == "XY":
            return [(x, y, value) for x in xs for y in ys]
        if plane == "XZ":
            return [(x, value, z) for x in xs for z in zs]
        if plane == "YZ":
            return [(value, y, z) for y in ys for z in zs]
        return []

    def _project_to_plane(self, point: tuple[float, float, float]) -> tuple[float, float]:
        """Projette un point 3D dans la vue 2D active."""
        x, y, z = point
        if self._plane == "XY":
            return x, y
        if self._plane == "XZ":
            return x, z
        return y, z

    def _compute_bbox(
        self,
        points: list[tuple[float, float, float]],
    ) -> tuple[float, float, float, float]:
        """Calcule la boîte englobante 2D du plan actif."""
        projected = [self._project_to_plane(point) for point in points]
        xs = [point[0] for point in projected]
        ys = [point[1] for point in projected]
        return min(xs), max(xs), min(ys), max(ys)

    def _map_to_widget(
        self,
        point_2d: tuple[float, float],
        bbox: tuple[float, float, float, float],
        draw_rect: QRectF,
    ) -> QPointF:
        """Convertit un point du plan en coordonnées widget."""
        min_x, max_x, min_y, max_y = bbox
        width = max(max_x - min_x, 1e-9)
        height = max(max_y - min_y, 1e-9)
        sx = draw_rect.width() / width
        sy = draw_rect.height() / height
        scale = min(sx, sy)
        offset_x = draw_rect.left() + (draw_rect.width() - width * scale) * 0.5
        offset_y = draw_rect.top() + (draw_rect.height() - height * scale) * 0.5

        x = offset_x + (point_2d[0] - min_x) * scale
        y = offset_y + (max_y - point_2d[1]) * scale
        return QPointF(x, y)
