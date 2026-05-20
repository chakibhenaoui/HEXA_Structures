"""
Vue graphique 3D du modèle structurel via PyVista.

Utilise pyvistaqt.QtInteractor pour l'integration PySide6.
Affichage du maillage, déformée, symboles d'appui, charges.
Sélection interactive des nœuds et éléments au clic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pyvista as pv
from PySide6.QtCore import QEvent, QLineF, QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QRubberBand, QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from core.sections import TSection, get_profile

if TYPE_CHECKING:
    from core.model_data import Grid3DData, ProjectModel, SurfaceElementData


_COLORS = {
    "background_bottom": "#ffffff",
    "background_top": "#ffffff",
    "node": "#ff0000",
    "node_label": "#c62828",
    "node_fixed": "#f39c12",
    "node_selected": "#2ecc71",
    "element": "#3498db",
    "element_selected": "#2ecc71",
    "deformed": "#e74c3c",
    "undeformed": "#555555",
    "grid": "#666666",
    "grid_point": "#9a9a9a",
    "grid_extension": "#8f8f8f",
    "grid_label_text": "#1f1f1f",
    "grid_label_fill": "#f5f5f2",
    "draw_start": "#2e8b57",
    "draw_hover": "#3aa76d",
    "draw_snap": "#ff5555",
    "label": "#cccccc",
    "section_label": "#2e8b57",
    "section_edge": "#000000",
    "surface_fill": "#8fb9dd",
    "surface_edge": "#355c7d",
    "support_triangle": "#f39c12",
}


@dataclass(frozen=True)
class _CameraState:
    position: tuple[float, float, float]
    focal_point: tuple[float, float, float]
    up: tuple[float, float, float]
    parallel_projection: bool
    parallel_scale: float | None = None
    view_angle: float | None = None


@dataclass(frozen=True)
class _SurfaceScreenHit:
    tag: int
    distance: float
    depth: float
    inside: bool


@dataclass(frozen=True)
class _NodeScreenHit:
    tag: int
    distance: float
    depth: float


class ModelView(QWidget):
    """Widget de visualisation 3D du modèle structurel."""

    _NODE_GLYPH_LIMIT = 1200
    _CAMERA_PADDING = 1.18

    node_picked = Signal(int)
    element_picked = Signal(int)
    element_context_requested = Signal(int, QPoint)
    surface_context_requested = Signal(int, QPoint)
    grid_point_picked = Signal(float, float, float)
    draw_finalize_requested = Signal()
    cursor_point_picked = Signal(float, float, float)
    cursor_pick_cancelled = Signal()
    selection_mode_requested = Signal()
    selection_changed = Signal(list, list, list)
    selection_delete_requested = Signal(list, list, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: ProjectModel | None = None
        self._tag_to_idx: dict[int, int] = {}
        self._elem_tags: list[int] = []
        self._selected_node: int | None = None
        self._selected_element: int | None = None
        self._selected_surface: int | None = None
        self._grid_points = np.empty((0, 3))
        self._draw_mode_enabled = False
        self._selection_mode_enabled = True
        self._cursor_pick_enabled = False
        self._cursor_pick_snap_to_grid = False
        self._draw_start_point: tuple[float, float, float] | None = None
        self._hover_point: tuple[float, float, float] | None = None
        self._selected_nodes: set[int] = set()
        self._selected_elements: set[int] = set()
        self._selected_surfaces: set[int] = set()
        self._drag_origin: QPoint | None = None
        self._camera_drag_mode: str | None = None
        self._active_plane: str | None = None
        self._active_plane_value: float | None = None
        self._extruded_mesh_cache: dict[tuple, tuple[pv.PolyData | None, list[int]]] = {}
        self._extruded_guides_cache: dict[tuple, pv.PolyData | None] = {}
        self._extruded_cache_max_entries = 8
        self.show_node_tags: bool = True
        self.show_section_names: bool = False
        self.show_extruded_sections: bool = False
        self.show_grid: bool = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Construit le widget PyVista embarque dans Qt."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)
        self.plotter.track_mouse_position()
        self.plotter.interactor.setMouseTracking(True)
        self.plotter.interactor.setFocusPolicy(Qt.StrongFocus)
        self.plotter.interactor.installEventFilter(self)
        self._rubber_band = QRubberBand(QRubberBand.Rectangle, self.plotter.interactor)

        self._apply_background()
        self.plotter.add_axes()
        self.plotter.enable_point_picking(
            callback=self._on_point_picked,
            show_message=False,
            show_point=False,
            left_clicking=True,
            tolerance=0.025,
            use_picker=True,
        )

    def _clear_scene(self) -> None:
        """Efface les acteurs sans forcer de rendu intermediaire."""
        try:
            self.plotter.clear(render=False)
        except TypeError:
            self.plotter.clear()

    def _apply_background(self) -> None:
        """Réapplique le fond dégradé après les clear() PyVista."""
        self.plotter.set_background(
            _COLORS["background_bottom"],
            top=_COLORS["background_top"],
        )
        try:
            renderer = self.plotter.renderer
            bottom = pv.Color(_COLORS["background_bottom"]).float_rgb
            top = pv.Color(_COLORS["background_top"]).float_rgb
            renderer.SetBackground(*bottom)
            renderer.SetBackground2(*top)
            renderer.SetGradientBackground(True)
            renderer.Modified()
        except Exception:
            pass

    def display_model(self, project: ProjectModel, preserve_camera: bool = False) -> None:
        """Affiche le modèle structurel (grille + nœuds + éléments + appuis)."""
        self._clear_scene()
        self._apply_background()
        self._project = project
        self._tag_to_idx.clear()
        self._elem_tags.clear()
        self._grid_points = np.empty((0, 3))

        self._draw_grid(project.grid)

        if not project.nodes:
            self._finalize_scene_view(preserve_camera=preserve_camera)
            if self._draw_mode_enabled and self._draw_start_point is not None:
                self.set_preview_start(self._draw_start_point)
            elif self._draw_mode_enabled:
                self._update_hover_preview()
            return

        visible_tags = [
            tag for tag, node in project.nodes.items()
            if self._node_on_active_plane(node.x, node.y, node.z)
        ]

        if not visible_tags:
            self._finalize_scene_view(preserve_camera=preserve_camera)
            if self._draw_mode_enabled and self._draw_start_point is not None:
                self.set_preview_start(self._draw_start_point)
            elif self._draw_mode_enabled:
                self._update_hover_preview()
            return

        coords: list[list[float]] = []
        labels: list[str] = []
        for i, tag in enumerate(visible_tags):
            node = project.nodes[tag]
            self._tag_to_idx[tag] = i
            coords.append([node.x, node.y, node.z])
            labels.append(f"{tag}")
        points = np.array(coords)
        node_tags = np.array([int(tag) for tag in visible_tags], dtype=np.int32)

        try:
            self._draw_supports(project, points)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._last_support_error = str(e)

        self._draw_surface_elements(project, points)

        node_radius = max(self._model_scale(points) * 0.12, 0.04)
        if len(points) > self._NODE_GLYPH_LIMIT:
            node_mesh = pv.PolyData(points)
            node_mesh.point_data["node_tag"] = node_tags
            self.plotter.add_mesh(
                node_mesh,
                color=_COLORS["node"],
                point_size=8,
                render_points_as_spheres=True,
                lighting=False,
                show_scalar_bar=False,
                name="nodes",
                render=False,
            )
        else:
            self.plotter.add_mesh(
                self._build_node_spheres(points, node_radius, node_tags),
                color=_COLORS["node"],
                lighting=False,
                show_scalar_bar=False,
                name="nodes",
                render=False,
            )

        if self.show_node_tags:
            self.plotter.add_point_labels(
                points,
                labels,
                font_size=13,
                bold=True,
                text_color=_COLORS["node_label"],
                shape=None,
                always_visible=True,
                name="node_labels",
                render=False,
            )

        if project.elements:
            if self._use_extruded_sections():
                self._draw_extruded_elements(project)
            else:
                mesh = self._build_line_elements_mesh(project, points)
                if mesh is not None and mesh.n_cells > 0:
                    self.plotter.add_mesh(
                        mesh,
                        color=_COLORS["element"],
                        line_width=4,
                        name="elements",
                        render=False,
                    )
                    if self.show_section_names:
                        self._draw_section_labels(project, points)

        self._finalize_scene_view(preserve_camera=preserve_camera, render=False)
        self._update_selection_actors(render=False)
        if self._draw_mode_enabled and self._draw_start_point is not None:
            self.set_preview_start(self._draw_start_point)
        elif self._draw_mode_enabled:
            self._update_hover_preview()
        else:
            self.plotter.render()

    def _finalize_scene_view(
        self,
        preserve_camera: bool = False,
        *,
        render: bool = True,
    ) -> None:
        """Termine la scène avec une caméra stable avant le premier rendu."""
        if preserve_camera:
            self._reset_clipping_range()
            if render:
                self.plotter.render()
                self._refresh_section_label_overlay()
            return
        self._apply_active_view_camera(render=render)

    def _restore_camera(self, *, render: bool = True) -> None:
        """Restaure une caméra lisible pour les structures."""
        self._apply_3d_camera(render=render)

    def _reset_clipping_range(self) -> None:
        """Recalcule le clipping sans toucher au cadrage."""
        try:
            self.plotter.renderer.ResetCameraClippingRange()
        except Exception:
            pass

    def _apply_active_view_camera(self, *, render: bool = True) -> None:
        """Applique le preset caméra courant sans état transitoire visible."""
        if self._active_plane is not None and self._active_plane_value is not None:
            position, focal_point, up, parallel_scale = self._plane_camera_state(
                self._active_plane,
                self._active_plane_value,
            )
            self._apply_camera_state(
                _CameraState(
                    position=position,
                    focal_point=focal_point,
                    up=up,
                    parallel_projection=True,
                    parallel_scale=max(parallel_scale, 0.5),
                ),
                render=render,
            )
            return
        self._apply_3d_camera(render=render)

    def _apply_3d_camera(self, *, render: bool = True) -> None:
        """Cadre le modèle avec un preset isométrique déterministe."""
        self._apply_camera_state(self._isometric_camera_state(), render=render)

    def _apply_camera_state(self, state: _CameraState, *, render: bool = True) -> None:
        """Applique un état caméra atomique."""
        camera = self.plotter.camera
        camera.position = state.position
        camera.focal_point = state.focal_point
        camera.up = state.up
        camera.parallel_projection = state.parallel_projection
        if state.parallel_scale is not None:
            camera.parallel_scale = state.parallel_scale
        if state.view_angle is not None:
            try:
                camera.view_angle = state.view_angle
            except Exception:
                try:
                    camera.SetViewAngle(state.view_angle)
                except Exception:
                    pass
        self._reset_clipping_range()
        if render:
            self.plotter.render()
            self._refresh_section_label_overlay()

    def _visible_scene_points(self) -> np.ndarray:
        """Retourne les points utiles au cadrage courant."""
        points: list[list[float]] = []
        if self._project is not None:
            for node in self._project.nodes.values():
                if self._node_on_active_plane(node.x, node.y, node.z):
                    points.append([node.x, node.y, node.z])
            if self._grid_points.size:
                points.extend(self._grid_points.tolist())
            elif self._project.grid.enabled:
                points.extend(self._grid_camera_points(self._project.grid))
        if not points:
            return np.array([[0.0, 0.0, 0.0]], dtype=float)
        return np.array(points, dtype=float)

    def _grid_camera_points(self, grid: Grid3DData) -> list[list[float]]:
        """Construit les coins de grille nécessaires au cadrage."""
        xs = grid.axis_values("X") or [0.0]
        ys = grid.axis_values("Y") or [0.0]
        zs = grid.axis_values("Z") or [0.0]
        if self._active_plane == "XY" and self._active_plane_value is not None:
            return [
                [x, y, self._active_plane_value]
                for x in (xs[0], xs[-1])
                for y in (ys[0], ys[-1])
            ]
        if self._active_plane == "XZ" and self._active_plane_value is not None:
            return [
                [x, self._active_plane_value, z]
                for x in (xs[0], xs[-1])
                for z in (zs[0], zs[-1])
            ]
        if self._active_plane == "YZ" and self._active_plane_value is not None:
            return [
                [self._active_plane_value, y, z]
                for y in (ys[0], ys[-1])
                for z in (zs[0], zs[-1])
            ]
        return [
            [x, y, z]
            for x in (xs[0], xs[-1])
            for y in (ys[0], ys[-1])
            for z in (zs[0], zs[-1])
        ]

    @staticmethod
    def _scene_bounds(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        """Retourne centre, dimensions protegees et rayon de cadrage."""
        if points.size == 0:
            points = np.array([[0.0, 0.0, 0.0]], dtype=float)
        mins = points.min(axis=0)
        maxs = points.max(axis=0)
        spans = maxs - mins
        reference = max(float(spans.max()), 1.0)
        spans = np.maximum(spans, reference * 0.02)
        center = (mins + maxs) * 0.5
        radius = max(float(np.linalg.norm(spans) * 0.5), 1.0)
        return center, spans, radius

    def _isometric_camera_state(self) -> _CameraState:
        """Calcule la caméra 3D standard à partir des limites réelles."""
        center, _spans, radius = self._scene_bounds(self._visible_scene_points())
        direction = np.array([1.35, -1.65, 1.15], dtype=float)
        direction /= float(np.linalg.norm(direction))
        view_angle = 30.0
        distance = (radius / np.tan(np.radians(view_angle * 0.5))) * self._CAMERA_PADDING
        position = center + direction * max(distance, 4.0)
        return _CameraState(
            position=tuple(float(v) for v in position),
            focal_point=tuple(float(v) for v in center),
            up=(0.0, 0.0, 1.0),
            parallel_projection=False,
            view_angle=view_angle,
        )

    def _model_scale(self, points: np.ndarray) -> float:
        """Retourne une taille de reference proportionnelle au modèle."""
        if len(points) < 2:
            if self._project is not None and self._project.grid.enabled:
                return max(
                    self._project.grid.axis_step("X"),
                    self._project.grid.axis_step("Y"),
                    self._project.grid.axis_step("Z"),
                    1.0,
                ) * 0.08
            return 0.3
        bbox = points.max(axis=0) - points.min(axis=0)
        return max(bbox.max() * 0.03, 0.1)

    def _draw_section_labels(self, project: ProjectModel, points: np.ndarray) -> None:
        """Dessine les noms de sections au milieu des éléments."""
        sec_midpoints: list[list[float]] = []
        sec_labels: list[str] = []

        for elem in project.elements.values():
            sec = project.sections.get(elem.section_tag)
            if sec is None:
                continue
            idx_i = self._tag_to_idx.get(elem.node_i)
            idx_j = self._tag_to_idx.get(elem.node_j)
            if idx_i is None or idx_j is None:
                continue

            mid = (points[idx_i] + points[idx_j]) / 2.0
            sec_midpoints.append(mid.tolist())
            sec_labels.append(sec.name)

        if sec_midpoints:
            self.plotter.add_point_labels(
                np.array(sec_midpoints),
                sec_labels,
                font_size=10,
                bold=False,
                italic=True,
                text_color="#2e8b57",
                shape=None,
                always_visible=True,
                name="section_labels",
                render=False,
            )

    def _draw_surface_elements(self, project: ProjectModel, points: np.ndarray) -> None:
        """Dessine les éléments surfaciques sous forme de plaques translucides."""
        surface_mesh = self._build_surface_elements_mesh(project)
        if surface_mesh is not None and surface_mesh.n_cells > 0:
            self.plotter.add_mesh(
                surface_mesh,
                color=_COLORS["surface_fill"],
                opacity=0.18,
                smooth_shading=True,
                show_edges=False,
                pickable=True,
                name="surface_elements",
                render=False,
            )

            self._add_extruded_feature_edges(
                surface_mesh,
                actor_name="surface_edges",
                render=False,
            )

    def _refresh_section_label_overlay(self) -> None:
        """Met à jour la visibilité et le contenu du calque des noms de sections."""
        overlay = getattr(self, "_section_label_overlay", None)
        if overlay is None:
            return
        overlay.setGeometry(self.plotter.interactor.rect())
        visible = (
            self._project is not None
            and self.show_section_names
            and not self.show_extruded_sections
        )
        overlay.setVisible(visible)
        if visible:
            overlay.raise_()
            overlay.update()

    @staticmethod
    def _section_label_font() -> QFont:
        """Police utilisée pour les noms de sections en surimpression."""
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        return font

    def _iter_section_label_screen_data(self) -> list[tuple[str, QPointF, float]]:
        """Retourne les libellés de sections projetés à l'écran avec leur angle."""
        if self._project is None or not self.show_section_names or self.show_extruded_sections:
            return []

        metrics = QFontMetricsF(self._section_label_font())
        labels: list[tuple[str, QPointF, float]] = []
        for elem in self._project.elements.values():
            ni = self._project.nodes.get(elem.node_i)
            nj = self._project.nodes.get(elem.node_j)
            sec = self._project.sections.get(elem.section_tag)
            if ni is None or nj is None or sec is None:
                continue
            if not self._node_on_active_plane(ni.x, ni.y, ni.z):
                continue
            if not self._node_on_active_plane(nj.x, nj.y, nj.z):
                continue

            p1 = self._project_world_to_screen((ni.x, ni.y, ni.z))
            p2 = self._project_world_to_screen((nj.x, nj.y, nj.z))
            if p1 is None or p2 is None:
                continue

            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = float((dx * dx + dy * dy) ** 0.5)
            text_width = metrics.horizontalAdvance(sec.name)
            if length < max(36.0, text_width + 14.0):
                continue

            angle = float(np.degrees(np.arctan2(dy, dx)))
            if angle > 90.0:
                angle -= 180.0
            elif angle < -90.0:
                angle += 180.0

            normal_x = -dy / length
            normal_y = dx / length
            midpoint = QPointF(
                (p1.x() + p2.x()) * 0.5 + normal_x * 8.0,
                (p1.y() + p2.y()) * 0.5 + normal_y * 8.0,
            )
            labels.append((sec.name, midpoint, angle))

        return labels

    def _paint_section_label_overlay(self, event) -> None:
        """Dessine les noms de sections comme un overlay parallèle aux éléments."""
        _ = event
        overlay = getattr(self, "_section_label_overlay", None)
        if overlay is None:
            return

        labels = self._iter_section_label_screen_data()
        if not labels:
            return

        painter = QPainter(overlay)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        font = self._section_label_font()
        metrics = QFontMetricsF(font)
        outline_pen = QPen(QColor(255, 255, 255, 210), 1.8)
        outline_pen.setJoinStyle(Qt.RoundJoin)
        fill_color = QColor(_COLORS["section_label"])

        for text, position, angle in labels:
            text_rect = metrics.tightBoundingRect(text)
            baseline = QPointF(
                -text_rect.width() * 0.5 - text_rect.left(),
                text_rect.height() * 0.5,
            )
            path = QPainterPath()
            path.addText(baseline, font, text)

            painter.save()
            painter.translate(position)
            painter.rotate(angle)
            painter.strokePath(path, outline_pen)
            painter.fillPath(path, fill_color)
            painter.restore()

        painter.end()

    @staticmethod
    def _build_node_spheres(
        points: np.ndarray,
        radius: float,
        node_tags: np.ndarray | None = None,
    ) -> pv.PolyData:
        """Construit un maillage de sphères pour des nœuds bien visibles."""
        if len(points) == 0:
            return pv.PolyData()
        glyph = pv.Sphere(
            radius=radius,
            theta_resolution=12,
            phi_resolution=12,
        )
        try:
            base = pv.PolyData(points)
            if node_tags is not None and len(node_tags) == len(points):
                base.point_data["node_tag"] = np.asarray(node_tags, dtype=np.int32)
            mesh = base.glyph(
                geom=glyph,
                orient=False,
                scale=False,
            )
            ModelView._assign_repeated_node_tags(mesh, node_tags)
            return mesh
        except Exception:
            meshes = [
                pv.Sphere(
                    radius=radius,
                    center=tuple(float(v) for v in point),
                    theta_resolution=12,
                    phi_resolution=12,
                )
                for point in points
            ]
            merged = meshes[0].copy()
            for mesh in meshes[1:]:
                merged = merged.merge(mesh, merge_points=False)
            ModelView._assign_repeated_node_tags(merged, node_tags)
            return merged

    @staticmethod
    def _assign_repeated_node_tags(
        mesh: pv.PolyData,
        node_tags: np.ndarray | None,
    ) -> None:
        """Propage les tags de noeuds sur un maillage de glyphes fusionnes."""
        if node_tags is None:
            return
        tags = np.asarray(node_tags, dtype=np.int32)
        if len(tags) == 0:
            return
        if mesh.n_points > 0 and mesh.n_points % len(tags) == 0:
            mesh.point_data["node_tag"] = np.repeat(tags, mesh.n_points // len(tags))
        if mesh.n_cells > 0 and mesh.n_cells % len(tags) == 0:
            mesh.cell_data["node_tag"] = np.repeat(tags, mesh.n_cells // len(tags))

    def _build_section_text_mesh(
        self,
        text: str,
        start: np.ndarray,
        end: np.ndarray,
        size: float,
    ) -> pv.PolyData | None:
        """Construit un texte vectoriel orienté selon l'axe de l'élément."""
        frame = self._local_frame_from_points(start, end)
        if frame is None:
            return None
        x_axis, y_axis, z_axis, _length = frame

        mesh = self._create_text_mesh(text)
        if mesh is None or mesh.n_points == 0:
            return None

        bounds = mesh.bounds
        width = max(bounds[1] - bounds[0], 1e-9)
        height = max(bounds[3] - bounds[2], 1e-9)
        scale = size / width
        mesh.scale([scale, scale, scale], inplace=True)

        bounds = mesh.bounds
        center = np.array(
            [
                (bounds[0] + bounds[1]) / 2.0,
                (bounds[2] + bounds[3]) / 2.0,
                (bounds[4] + bounds[5]) / 2.0,
            ],
            dtype=float,
        )
        mesh.translate(-center, inplace=True)

        transform = np.eye(4)
        transform[:3, 0] = x_axis
        transform[:3, 1] = z_axis
        transform[:3, 2] = y_axis
        transform[:3, 3] = (start + end) / 2.0 + y_axis * max(height * scale * 0.8, size * 0.20)
        mesh.transform(transform, inplace=True)
        return mesh.clean()

    @staticmethod
    def _create_text_mesh(text: str) -> pv.PolyData | None:
        """Construit un maillage de texte avec fallback selon la version de PyVista."""
        text3d = getattr(pv, "Text3D", None)
        if text3d is not None:
            try:
                mesh = text3d(text, depth=0.25)
            except TypeError:
                try:
                    mesh = text3d(text)
                except Exception:
                    mesh = None
            except Exception:
                mesh = None
            if mesh is not None and mesh.n_points > 0:
                return mesh

        vector_text = getattr(pv, "vector_text", None)
        if vector_text is not None:
            try:
                mesh = vector_text(text)
            except Exception:
                mesh = None
            if mesh is not None and mesh.n_points > 0:
                return mesh.triangulate().clean()

        return None

    def _use_extruded_sections(self) -> bool:
        """Retourne vrai si l'affichage extrudé est demandé en vraie vue 3D."""
        return self.show_extruded_sections and (
            self._active_plane is None or self._active_plane == "3D"
        )

    def _draw_extruded_elements(self, project: ProjectModel) -> None:
        """Dessine les elements extrudes avec un nombre reduit d'acteurs VTK."""
        self._elem_tags.clear()

        mesh = self._build_extruded_elements_mesh(project)
        if mesh is None or mesh.n_cells == 0:
            return

        try:
            self.plotter.add_mesh(
                mesh,
                scalars="section_rgb",
                rgb=True,
                smooth_shading=True,
                show_scalar_bar=False,
                name="elements",
                render=False,
            )
        except (TypeError, ValueError):
            self.plotter.add_mesh(
                mesh,
                color=_COLORS["element"],
                smooth_shading=True,
                show_scalar_bar=False,
                name="elements",
                render=False,
            )

        detail_mesh = self._build_extruded_section_guides_mesh(project)
        self._add_extruded_feature_edges(
            mesh,
            actor_name="element_edges",
            extra_mesh=detail_mesh,
            render=False,
        )

    def _add_extruded_feature_edges(
        self,
        mesh: pv.PolyData,
        actor_name: str,
        extra_mesh: pv.PolyData | None = None,
        render: bool = False,
    ) -> None:
        """Dessine uniquement les arêtes géométriques utiles d'un maillage extrudé."""
        try:
            edge_mesh = mesh.extract_feature_edges(
                boundary_edges=True,
                non_manifold_edges=False,
                feature_edges=True,
                manifold_edges=False,
                feature_angle=25.0,
            )
        except Exception:
            edge_mesh = None

        if extra_mesh is not None and extra_mesh.n_cells > 0:
            if edge_mesh is None or edge_mesh.n_cells == 0:
                edge_mesh = extra_mesh
            else:
                try:
                    edge_mesh = edge_mesh.merge(extra_mesh, merge_points=False)
                except Exception:
                    pass

        if edge_mesh is None or edge_mesh.n_cells == 0:
            return

        self.plotter.add_mesh(
            edge_mesh,
            color=_COLORS["section_edge"],
            line_width=1.2,
            name=actor_name,
            pickable=False,
            render=render,
        )

    def _build_element_display_mesh(
        self,
        project: ProjectModel,
        points: np.ndarray,
    ) -> pv.PolyData | None:
        """Construit le maillage d'affichage des éléments."""
        if self._use_extruded_sections():
            mesh = self._build_extruded_elements_mesh(project)
            if mesh is not None and mesh.n_cells > 0:
                return mesh
        return self._build_line_elements_mesh(project, points)

    @staticmethod
    def _section_palette() -> list[str]:
        """Palette discrète pour distinguer visuellement les sections assignées."""
        return [
            "#2E86AB",
            "#E07A5F",
            "#81B29A",
            "#F2CC8F",
            "#7D5BA6",
            "#D1495B",
            "#3D405B",
            "#6B8E23",
            "#C1666B",
            "#4D908E",
        ]

    @classmethod
    def _section_color_for_tag(cls, section_tag: int) -> str:
        """Retourne une couleur stable à partir du tag de section."""
        palette = cls._section_palette()
        return palette[(max(section_tag, 1) - 1) % len(palette)]

    @staticmethod
    def _hex_to_uint8_rgb(color: str) -> np.ndarray:
        """Convertit une couleur hexadécimale '#RRGGBB' en RGB uint8."""
        value = color.strip().lstrip("#")
        if len(value) != 6:
            raise ValueError(f"Couleur hexadécimale invalide: {color}")
        return np.array(
            [int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)],
            dtype=np.uint8,
        )

    @staticmethod
    def _signature_value(value):
        """Transforme une valeur projet mutable en tuple stable pour les caches."""
        if isinstance(value, dict):
            return tuple(
                (key, ModelView._signature_value(item_value))
                for key, item_value in sorted(value.items(), key=lambda item: str(item[0]))
            )
        if isinstance(value, (list, tuple)):
            return tuple(ModelView._signature_value(item) for item in value)
        if isinstance(value, set):
            return tuple(
                sorted(
                    (ModelView._signature_value(item) for item in value),
                    key=repr,
                )
            )
        if isinstance(value, float):
            return round(value, 12)
        return value

    def _extruded_cache_key(
        self,
        project: ProjectModel,
        only_tags: set[int] | None = None,
    ) -> tuple:
        """Cle de cache des maillages extrudes, independante des charges."""
        requested_tags = None if only_tags is None else tuple(sorted(only_tags))
        node_tags: set[int] = set()
        element_parts: list[tuple] = []
        section_tags: set[int] = set()

        for elem in project.elements.values():
            if only_tags is not None and elem.tag not in only_tags:
                continue
            element_parts.append(
                (
                    elem.tag,
                    elem.node_i,
                    elem.node_j,
                    elem.section_tag,
                    elem.element_type,
                )
            )
            node_tags.add(elem.node_i)
            node_tags.add(elem.node_j)
            section_tags.add(elem.section_tag)

        nodes = tuple(
            (
                tag,
                round(float(node.x), 12),
                round(float(node.y), 12),
                round(float(node.z), 12),
            )
            for tag, node in sorted(project.nodes.items())
            if tag in node_tags
        )
        sections = tuple(
            (
                tag,
                section.section_type,
                self._signature_value(section.properties),
            )
            for tag, section in sorted(project.sections.items())
            if tag in section_tags
        )
        return (
            requested_tags,
            self._active_plane,
            round(float(self._active_plane_value), 12)
            if self._active_plane_value is not None
            else None,
            nodes,
            tuple(sorted(element_parts)),
            sections,
        )

    def _remember_extruded_cache(self, cache: dict, key: tuple, value) -> None:
        """Stocke une entree en gardant un cache borne."""
        cache[key] = value
        while len(cache) > self._extruded_cache_max_entries:
            cache.pop(next(iter(cache)))

    @staticmethod
    def _ensure_section_rgb_scalars(mesh: pv.PolyData, cell_colors: list[np.ndarray]) -> None:
        """Garantit un tableau RGB compatible avec le nombre de cellules fusionnees."""
        if mesh.n_cells <= 0:
            return

        existing = None
        try:
            existing = np.asarray(mesh.cell_data["section_rgb"], dtype=np.uint8)
        except Exception:
            existing = None
        if existing is not None and existing.shape == (mesh.n_cells, 3):
            return

        if cell_colors:
            colors = np.vstack(cell_colors).astype(np.uint8)
        else:
            colors = np.tile(
                ModelView._hex_to_uint8_rgb(_COLORS["element"]),
                (mesh.n_cells, 1),
            )

        if colors.shape != (mesh.n_cells, 3):
            colors = np.resize(colors, (mesh.n_cells, 3)).astype(np.uint8)
        mesh.cell_data["section_rgb"] = colors

    def _build_line_elements_mesh(
        self,
        project: ProjectModel,
        points: np.ndarray,
    ) -> pv.PolyData | None:
        """Construit l'affichage filaire des axes d'éléments."""
        lines: list[int] = []
        self._elem_tags.clear()
        for elem in project.elements.values():
            idx_i = self._tag_to_idx.get(elem.node_i)
            idx_j = self._tag_to_idx.get(elem.node_j)
            if idx_i is None or idx_j is None:
                continue
            lines.extend([2, idx_i, idx_j])
            self._elem_tags.append(elem.tag)

        if not lines:
            return None
        return pv.PolyData(points, lines=lines)

    def _build_surface_elements_mesh(
        self,
        project: ProjectModel,
        only_tags: set[int] | None = None,
    ) -> pv.PolyData | None:
        """Construit un maillage léger de faces pour les surfaces visibles."""
        meshes: list[pv.PolyData] = []

        for tag, surface in self._visible_surface_items(project):
            if only_tags is not None and tag not in only_tags:
                continue
            polygon_points = self._surface_polygon_world_points(surface)
            if polygon_points is None or len(polygon_points) < 3:
                continue
            section = project.sections.get(surface.section_tag)
            thickness = float(section.thickness) if section is not None else 0.0
            mesh = self._build_surface_solid_mesh(polygon_points, thickness)
            if mesh is None or mesh.n_cells == 0:
                continue
            mesh.cell_data["surface_tag"] = np.full(mesh.n_cells, int(tag), dtype=np.int32)
            meshes.append(mesh)

        if not meshes:
            return None

        merged = meshes[0].copy()
        for mesh in meshes[1:]:
            merged = merged.merge(mesh, merge_points=False)
        return merged

    @staticmethod
    def _visible_surface_items(project: ProjectModel):
        for tag, plate in project.plate_regions.items():
            yield int(tag), plate
        for tag, surface in project.surface_elements.items():
            yield int(tag), surface

    def _surface_polygon_world_points(
        self,
        surface: "SurfaceElementData",
    ) -> np.ndarray | None:
        """Retourne les sommets monde d'une surface visible."""
        if self._project is None:
            return None

        polygon_points: list[list[float]] = []
        node_tags = getattr(surface, "node_tags", None)
        if node_tags is None:
            node_tags = getattr(surface, "corner_node_tags", ())
        for node_tag in node_tags:
            node = self._project.nodes.get(node_tag)
            if node is None:
                return None
            if not self._node_on_active_plane(node.x, node.y, node.z):
                return None
            polygon_points.append([float(node.x), float(node.y), float(node.z)])

        if len(polygon_points) < 3:
            return None
        return np.array(polygon_points, dtype=float)

    @staticmethod
    def _surface_normal(points: np.ndarray) -> np.ndarray | None:
        """Calcule une normale unitaire à partir d'un polygone 3D."""
        if len(points) < 3:
            return None

        origin = points[0]
        for idx in range(1, len(points) - 1):
            normal = np.cross(points[idx] - origin, points[idx + 1] - origin)
            norm = float(np.linalg.norm(normal))
            if norm > 1e-10:
                return normal / norm
        return None

    @classmethod
    def _build_surface_solid_mesh(
        cls,
        polygon_points: np.ndarray,
        thickness: float,
    ) -> pv.PolyData | None:
        """Extrude légèrement un polygone de plaque autour de son plan moyen."""
        normal = cls._surface_normal(polygon_points)
        if normal is None:
            return None

        shell_thickness = max(float(thickness), 0.001)
        offset = normal * (shell_thickness * 0.5)
        top = polygon_points + offset
        bottom = polygon_points - offset
        vertices = np.vstack((top, bottom))

        node_count = len(polygon_points)
        faces: list[int] = [node_count, *range(node_count)]
        faces.extend([node_count, *range(2 * node_count - 1, node_count - 1, -1)])
        for idx in range(node_count):
            nxt = (idx + 1) % node_count
            faces.extend([4, idx, nxt, node_count + nxt, node_count + idx])

        mesh = pv.PolyData(vertices, faces=np.array(faces, dtype=np.int32))
        return mesh.triangulate().clean()

    def _build_surface_outline_mesh(
        self,
        project: ProjectModel,
    ) -> pv.PolyData | None:
        """Construit les contours visibles des surfaces pour clarifier la lecture."""
        points: list[list[float]] = []
        lines: list[int] = []

        for _tag, surface in self._visible_surface_items(project):
            polygon_points: list[list[float]] = []
            node_tags = getattr(surface, "node_tags", None)
            if node_tags is None:
                node_tags = getattr(surface, "corner_node_tags", ())
            for node_tag in node_tags:
                node = project.nodes.get(node_tag)
                if node is None or node_tag not in self._tag_to_idx:
                    polygon_points = []
                    break
                polygon_points.append([node.x, node.y, node.z])
            if len(polygon_points) < 3:
                continue

            for idx in range(len(polygon_points)):
                start = polygon_points[idx]
                end = polygon_points[(idx + 1) % len(polygon_points)]
                start_idx = len(points)
                points.append(start)
                points.append(end)
                lines.extend([2, start_idx, start_idx + 1])

        if not points or not lines:
            return None
        return pv.PolyData(np.array(points, dtype=float), lines=lines)

    def _build_extruded_elements_mesh(
        self,
        project: ProjectModel,
        only_tags: set[int] | None = None,
    ) -> pv.PolyData | None:
        """Construit un maillage extrudé à partir des vraies sections."""
        cache_key = self._extruded_cache_key(project, only_tags)
        cached = self._extruded_mesh_cache.get(cache_key)
        if cached is not None:
            mesh, elem_tags = cached
            if only_tags is None:
                self._elem_tags = list(elem_tags)
            return mesh

        meshes: list[pv.PolyData] = []
        cell_colors: list[np.ndarray] = []
        elem_tags: list[int] = []
        if only_tags is None:
            self._elem_tags.clear()

        for elem in project.elements.values():
            if only_tags is not None and elem.tag not in only_tags:
                continue
            ni = project.nodes.get(elem.node_i)
            nj = project.nodes.get(elem.node_j)
            section = project.sections.get(elem.section_tag)
            if ni is None or nj is None or section is None:
                continue
            if not self._node_on_active_plane(ni.x, ni.y, ni.z):
                continue
            if not self._node_on_active_plane(nj.x, nj.y, nj.z):
                continue

            mesh = self._build_single_element_extrusion(section, ni, nj)
            if mesh is None or mesh.n_cells == 0:
                continue
            color = self._hex_to_uint8_rgb(self._section_color_for_tag(section.tag))
            mesh.cell_data["section_rgb"] = np.tile(color, (mesh.n_cells, 1))
            meshes.append(mesh)
            cell_colors.append(np.tile(color, (mesh.n_cells, 1)))
            elem_tags.append(elem.tag)

        if not meshes:
            self._remember_extruded_cache(self._extruded_mesh_cache, cache_key, (None, []))
            return None

        merged = meshes[0].copy()
        for mesh in meshes[1:]:
            merged = merged.merge(mesh, merge_points=False)
        self._ensure_section_rgb_scalars(merged, cell_colors)
        if only_tags is None:
            self._elem_tags = list(elem_tags)
        self._remember_extruded_cache(
            self._extruded_mesh_cache,
            cache_key,
            (merged, elem_tags),
        )
        return merged

    def _build_extruded_section_guides_mesh(
        self,
        project: ProjectModel,
        only_tags: set[int] | None = None,
    ) -> pv.PolyData | None:
        """Assemble les lignes-guide légères des sections extrudées visibles."""
        cache_key = self._extruded_cache_key(project, only_tags)
        if cache_key in self._extruded_guides_cache:
            return self._extruded_guides_cache[cache_key]

        guide_meshes: list[pv.PolyData] = []

        for elem in project.elements.values():
            if only_tags is not None and elem.tag not in only_tags:
                continue
            ni = project.nodes.get(elem.node_i)
            nj = project.nodes.get(elem.node_j)
            section = project.sections.get(elem.section_tag)
            if ni is None or nj is None or section is None:
                continue
            if not self._node_on_active_plane(ni.x, ni.y, ni.z):
                continue
            if not self._node_on_active_plane(nj.x, nj.y, nj.z):
                continue

            mesh = self._build_extruded_section_guides(section, ni, nj)
            if mesh is None or mesh.n_cells == 0:
                continue
            guide_meshes.append(mesh)

        if not guide_meshes:
            self._remember_extruded_cache(self._extruded_guides_cache, cache_key, None)
            return None

        merged = guide_meshes[0].copy()
        for mesh in guide_meshes[1:]:
            merged = merged.merge(mesh, merge_points=False)
        self._remember_extruded_cache(self._extruded_guides_cache, cache_key, merged)
        return merged

    def _build_single_element_extrusion(self, section, node_i, node_j) -> pv.PolyData | None:
        """Extrude une section locale le long d'un élément."""
        frame = self._local_frame_from_points(
            np.array([node_i.x, node_i.y, node_i.z], dtype=float),
            np.array([node_j.x, node_j.y, node_j.z], dtype=float),
        )
        if frame is None:
            return None
        x_axis, y_axis, z_axis, length = frame

        polygon = self._section_polygon_points(section.section_type, section.properties)
        if polygon is None or len(polygon) < 3:
            return None

        local_points = np.column_stack(
            [
                np.zeros(len(polygon), dtype=float),
                polygon[:, 0],
                polygon[:, 1],
            ]
        )
        faces = np.hstack([[len(local_points)], np.arange(len(local_points), dtype=np.int32)])
        profile = pv.PolyData(local_points, faces=faces)
        extruded = profile.extrude((length, 0.0, 0.0), capping=True)

        transform = np.eye(4)
        transform[:3, 0] = x_axis
        transform[:3, 1] = y_axis
        transform[:3, 2] = z_axis
        transform[:3, 3] = np.array([node_i.x, node_i.y, node_i.z], dtype=float)

        extruded.transform(transform, inplace=True)
        return extruded.clean()

    def _build_extruded_section_guides(self, section, node_i, node_j) -> pv.PolyData | None:
        """Construit des lignes-guide légères pour les sections ouvertes type I."""
        frame = self._local_frame_from_points(
            np.array([node_i.x, node_i.y, node_i.z], dtype=float),
            np.array([node_j.x, node_j.y, node_j.z], dtype=float),
        )
        if frame is None:
            return None
        x_axis, y_axis, z_axis, length = frame

        guide_points = self._section_guide_points(section.section_type, section.properties)
        fillet_points = self._section_fillet_guide_points(
            section.section_type,
            section.properties,
        )
        if fillet_points.size > 0:
            if guide_points.size == 0:
                guide_points = fillet_points
            else:
                guide_points = np.vstack((guide_points, fillet_points))
        if guide_points.size == 0:
            return None

        span = float(np.linalg.norm(np.ptp(guide_points, axis=0)))
        outward_offset = max(span * 0.008, 0.0005)
        local_points: list[list[float]] = []
        lines: list[int] = []

        for point in guide_points:
            radial = np.array(point, dtype=float)
            radial_norm = float(np.linalg.norm(radial))
            if radial_norm > 1e-12:
                radial = radial + (radial / radial_norm) * outward_offset
            start_idx = len(local_points)
            local_points.append([0.0, float(radial[0]), float(radial[1])])
            local_points.append([length, float(radial[0]), float(radial[1])])
            lines.extend([2, start_idx, start_idx + 1])

        if not local_points:
            return None

        guide_mesh = pv.PolyData(np.array(local_points, dtype=float), lines=np.array(lines))
        transform = np.eye(4)
        transform[:3, 0] = x_axis
        transform[:3, 1] = y_axis
        transform[:3, 2] = z_axis
        transform[:3, 3] = np.array([node_i.x, node_i.y, node_i.z], dtype=float)
        guide_mesh.transform(transform, inplace=True)
        return guide_mesh.clean()

    @staticmethod
    def _local_frame_from_points(
        start: np.ndarray,
        end: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float] | None:
        """Construit le repère local d'un élément 3D."""
        delta = end - start
        length = float(np.linalg.norm(delta))
        if length < 1e-12:
            return None

        x_axis = delta / length
        ref = np.array([0.0, 0.0, 1.0], dtype=float)
        if abs(x_axis[2]) > 0.95:
            ref = np.array([1.0, 0.0, 0.0], dtype=float)

        y_axis = np.cross(ref, x_axis)
        norm_y = float(np.linalg.norm(y_axis))
        if norm_y < 1e-10:
            ref = np.array([0.0, 1.0, 0.0], dtype=float)
            y_axis = np.cross(ref, x_axis)
            norm_y = float(np.linalg.norm(y_axis))
        if norm_y < 1e-10:
            return None
        y_axis /= norm_y
        z_axis = np.cross(x_axis, y_axis)
        z_axis /= float(np.linalg.norm(z_axis))
        return x_axis, y_axis, z_axis, length

    @staticmethod
    def _section_polygon_points(
        section_type: str,
        properties: dict,
    ) -> np.ndarray | None:
        """Retourne le contour 2D local (y, z) d'une section réelle."""
        if section_type == "rectangular":
            b = float(properties.get("b", 0.0))
            h = float(properties.get("h", 0.0))
            if b <= 0.0 or h <= 0.0:
                return None
            return np.array(
                [
                    [-b / 2.0, -h / 2.0],
                    [b / 2.0, -h / 2.0],
                    [b / 2.0, h / 2.0],
                    [-b / 2.0, h / 2.0],
                ],
                dtype=float,
            )

        if section_type == "T":
            bw = float(properties.get("bw", 0.0))
            hw = float(properties.get("hw", 0.0))
            bf = float(properties.get("bf", 0.0))
            hf = float(properties.get("hf", 0.0))
            if min(bw, hw, bf, hf) <= 0.0:
                return None
            t_section = TSection(bw=bw, hw=hw, bf=bf, hf=hf)
            z0 = -t_section.centroid_y
            z1 = hw - t_section.centroid_y
            z2 = t_section.h - t_section.centroid_y
            return np.array(
                [
                    [-bw / 2.0, z0],
                    [bw / 2.0, z0],
                    [bw / 2.0, z1],
                    [bf / 2.0, z1],
                    [bf / 2.0, z2],
                    [-bf / 2.0, z2],
                    [-bf / 2.0, z1],
                    [-bw / 2.0, z1],
                ],
                dtype=float,
            )

        if section_type == "I_profile":
            profile_name = str(properties.get("profile", "")).strip()
            if not profile_name:
                return None
            try:
                profile = get_profile(profile_name)
            except KeyError:
                return None

            b = profile.b
            h = profile.h
            tw = profile.tw
            tf = profile.tf
            return np.array(
                [
                    [-b / 2.0, h / 2.0],
                    [b / 2.0, h / 2.0],
                    [b / 2.0, h / 2.0 - tf],
                    [tw / 2.0, h / 2.0 - tf],
                    [tw / 2.0, -h / 2.0 + tf],
                    [b / 2.0, -h / 2.0 + tf],
                    [b / 2.0, -h / 2.0],
                    [-b / 2.0, -h / 2.0],
                    [-b / 2.0, -h / 2.0 + tf],
                    [-tw / 2.0, -h / 2.0 + tf],
                    [-tw / 2.0, h / 2.0 - tf],
                    [-b / 2.0, h / 2.0 - tf],
                ],
                dtype=float,
            )

        return None

    @staticmethod
    def _section_guide_points(
        section_type: str,
        properties: dict,
    ) -> np.ndarray:
        """Retourne des points de repère leger pour rendre lisibles les profils ouverts."""
        if section_type != "I_profile":
            return np.empty((0, 2), dtype=float)

        profile_name = str(properties.get("profile", "")).strip()
        if not profile_name:
            return np.empty((0, 2), dtype=float)
        try:
            profile = get_profile(profile_name)
        except KeyError:
            return np.empty((0, 2), dtype=float)

        half_web = profile.tw / 2.0
        flange_knee = profile.h / 2.0 - profile.tf
        if half_web <= 0.0 or flange_knee <= 0.0:
            return np.empty((0, 2), dtype=float)

        return np.array(
            [
                [half_web, flange_knee],
                [-half_web, flange_knee],
                [half_web, -flange_knee],
                [-half_web, -flange_knee],
            ],
            dtype=float,
        )

    @staticmethod
    def _section_fillet_guide_points(
        section_type: str,
        properties: dict,
    ) -> np.ndarray:
        """Retourne des points de repère indicatifs pour suggerer les conges des profils I."""
        if section_type != "I_profile":
            return np.empty((0, 2), dtype=float)

        profile_name = str(properties.get("profile", "")).strip()
        if not profile_name:
            return np.empty((0, 2), dtype=float)
        try:
            profile = get_profile(profile_name)
        except KeyError:
            return np.empty((0, 2), dtype=float)

        half_web = profile.tw / 2.0
        flange_knee = profile.h / 2.0 - profile.tf
        flange_gap = (profile.b - profile.tw) / 2.0
        fillet_offset = min(
            max(profile.tf, profile.tw),
            flange_gap * 0.35,
            flange_knee * 0.18,
        )
        if half_web <= 0.0 or flange_knee <= fillet_offset or fillet_offset <= 0.0:
            return np.empty((0, 2), dtype=float)

        return np.array(
            [
                [half_web + fillet_offset, flange_knee - fillet_offset],
                [-(half_web + fillet_offset), flange_knee - fillet_offset],
                [half_web + fillet_offset, -(flange_knee - fillet_offset)],
                [-(half_web + fillet_offset), -(flange_knee - fillet_offset)],
            ],
            dtype=float,
        )

    def _draw_supports(self, project: ProjectModel, points: np.ndarray) -> None:
        """Dessine les symboles d'appui en glyphes 3D."""
        scale = self._model_scale(points)

        for tag, node in project.nodes.items():
            if not node.is_support:
                continue
            if not self._node_on_active_plane(node.x, node.y, node.z):
                continue

            fix = node.fixities
            n_trans = sum(fix[:3])
            n_rot = sum(fix[3:])
            pos = [node.x, node.y, node.z]

            if n_trans == 3 and n_rot == 3:
                glyph = pv.Cube(
                    center=pos,
                    x_length=scale * 0.6,
                    y_length=scale * 0.6,
                    z_length=scale * 0.6,
                )
            elif n_trans >= 2:
                glyph = pv.Sphere(radius=scale * 0.3, center=pos)
            else:
                glyph = pv.Cone(
                    center=[pos[0], pos[1], pos[2] - scale * 0.3],
                    direction=[0, 0, 1],
                    height=scale * 0.6,
                    radius=scale * 0.35,
                    resolution=3,
                )

            self.plotter.add_mesh(
                glyph,
                color=_COLORS["support_triangle"],
                name=f"support_{tag}",
                render=False,
            )

    def _draw_grid(self, grid: Grid3DData) -> None:
        """Dessine la grille 3D et les points d'accrochage."""
        if not self.show_grid or not grid.enabled:
            return

        if self._active_plane is not None and self._active_plane_value is not None:
            points, lines = self._build_plane_geometry(
                grid,
                self._active_plane,
                self._active_plane_value,
            )
        else:
            points, lines = self._build_grid_geometry(grid)
        self._grid_points = points
        if len(points) == 0:
            return

        grid_mesh = pv.PolyData(points, lines=lines)
        self.plotter.add_mesh(
            grid_mesh,
            color=_COLORS["grid"],
            line_width=1,
            opacity=0.85,
            name="grid",
            pickable=True,
            render=False,
        )

        point_cloud = pv.PolyData(points)
        self.plotter.add_mesh(
            point_cloud,
            color=_COLORS["grid_point"],
            point_size=10,
            opacity=0.5,
            render_points_as_spheres=True,
            name="grid_points",
            pickable=True,
            render=False,
        )

        ext_points, ext_lines, label_points, label_texts = self._build_grid_annotations(
            grid,
            plane=self._active_plane,
            value=self._active_plane_value,
        )
        if len(ext_points) > 0 and ext_lines:
            ext_mesh = pv.PolyData(ext_points, lines=ext_lines)
            self.plotter.add_mesh(
                ext_mesh,
                color=_COLORS["grid_extension"],
                line_width=1.2,
                opacity=0.95,
                name="grid_extensions",
                pickable=False,
                render=False,
            )
        if len(label_points) > 0 and label_texts:
            self.plotter.add_point_labels(
                label_points,
                label_texts,
                font_size=12,
                bold=True,
                text_color=_COLORS["grid_label_text"],
                show_points=False,
                shape="rounded_rect",
                shape_color=_COLORS["grid_label_fill"],
                fill_shape=True,
                shape_opacity=0.95,
                margin=6,
                pickable=False,
                always_visible=False,
                name="grid_labels",
                render=False,
            )

    @staticmethod
    def _build_grid_geometry(grid: Grid3DData) -> tuple[np.ndarray, list[int]]:
        """Construit les intersections et segments de la grille."""
        xs = grid.axis_values("X")
        ys = grid.axis_values("Y")
        zs = grid.axis_values("Z")

        points: list[list[float]] = []
        point_index: dict[tuple[int, int, int], int] = {}
        for ix, x in enumerate(xs):
            for iy, y in enumerate(ys):
                for iz, z in enumerate(zs):
                    point_index[(ix, iy, iz)] = len(points)
                    points.append([x, y, z])

        lines: list[int] = []
        for iy in range(len(ys)):
            for iz in range(len(zs)):
                for ix in range(len(xs) - 1):
                    lines.extend(
                        [2, point_index[(ix, iy, iz)], point_index[(ix + 1, iy, iz)]]
                    )
        for ix in range(len(xs)):
            for iz in range(len(zs)):
                for iy in range(len(ys) - 1):
                    lines.extend(
                        [2, point_index[(ix, iy, iz)], point_index[(ix, iy + 1, iz)]]
                    )
        for ix in range(len(xs)):
            for iy in range(len(ys)):
                for iz in range(len(zs) - 1):
                    lines.extend(
                        [2, point_index[(ix, iy, iz)], point_index[(ix, iy, iz + 1)]]
                    )

        return np.array(points, dtype=float), lines

    @staticmethod
    def _build_plane_geometry(
        grid: Grid3DData,
        plane: str,
        value: float,
    ) -> tuple[np.ndarray, list[int]]:
        """Construit uniquement la file active pour une vue 2D de dessin."""
        xs = grid.axis_values("X")
        ys = grid.axis_values("Y")
        zs = grid.axis_values("Z")

        points: list[list[float]] = []
        index: dict[tuple[int, int], int] = {}

        if plane == "XY":
            for ix, x in enumerate(xs):
                for iy, y in enumerate(ys):
                    index[(ix, iy)] = len(points)
                    points.append([x, y, value])

            lines: list[int] = []
            for iy in range(len(ys)):
                for ix in range(len(xs) - 1):
                    lines.extend([2, index[(ix, iy)], index[(ix + 1, iy)]])
            for ix in range(len(xs)):
                for iy in range(len(ys) - 1):
                    lines.extend([2, index[(ix, iy)], index[(ix, iy + 1)]])
            return np.array(points, dtype=float), lines

        if plane == "XZ":
            for ix, x in enumerate(xs):
                for iz, z in enumerate(zs):
                    index[(ix, iz)] = len(points)
                    points.append([x, value, z])

            lines = []
            for iz in range(len(zs)):
                for ix in range(len(xs) - 1):
                    lines.extend([2, index[(ix, iz)], index[(ix + 1, iz)]])
            for ix in range(len(xs)):
                for iz in range(len(zs) - 1):
                    lines.extend([2, index[(ix, iz)], index[(ix, iz + 1)]])
            return np.array(points, dtype=float), lines

        if plane == "YZ":
            for iy, y in enumerate(ys):
                for iz, z in enumerate(zs):
                    index[(iy, iz)] = len(points)
                    points.append([value, y, z])

            lines = []
            for iz in range(len(zs)):
                for iy in range(len(ys) - 1):
                    lines.extend([2, index[(iy, iz)], index[(iy + 1, iz)]])
            for iy in range(len(ys)):
                for iz in range(len(zs) - 1):
                    lines.extend([2, index[(iy, iz)], index[(iy, iz + 1)]])
            return np.array(points, dtype=float), lines

        return np.empty((0, 3)), []

    @staticmethod
    def _grid_annotation_offset(span: float, step: float) -> float:
        """Retourne un decalage lisible pour les lignes d'extension."""
        if step > 0.0:
            return max(step * 0.32, span * 0.04, 0.3)
        if span > 0.0:
            return max(span * 0.06, 0.3)
        return 0.3

    @classmethod
    def _build_grid_annotations(
        cls,
        grid: Grid3DData,
        *,
        plane: str | None,
        value: float | None,
    ) -> tuple[np.ndarray, list[int], np.ndarray, list[str]]:
        """Construit les lignes d'extension et bulles de repère de grille."""
        x_entries = grid.axis_entries("X")
        y_entries = grid.axis_entries("Y")
        z_entries = grid.axis_entries("Z")
        if not x_entries or not y_entries or not z_entries:
            return np.empty((0, 3)), [], np.empty((0, 3)), []

        xs = [entry.coordinate for entry in x_entries]
        ys = [entry.coordinate for entry in y_entries]
        zs = [entry.coordinate for entry in z_entries]
        span_x = max(xs[-1] - xs[0], 0.0)
        span_y = max(ys[-1] - ys[0], 0.0)
        span_z = max(zs[-1] - zs[0], 0.0)
        offset_x = cls._grid_annotation_offset(span_x, grid.axis_step("X"))
        offset_y = cls._grid_annotation_offset(span_y, grid.axis_step("Y"))
        offset_z = cls._grid_annotation_offset(span_z, grid.axis_step("Z"))
        label_gap_x = offset_x * 0.28
        label_gap_y = offset_y * 0.28
        label_gap_z = offset_z * 0.28

        ext_points: list[list[float]] = []
        ext_lines: list[int] = []
        label_points: list[list[float]] = []
        label_texts: list[str] = []

        def add_extension(
            start: tuple[float, float, float],
            end: tuple[float, float, float],
            label_point: tuple[float, float, float],
            label_text: str,
        ) -> None:
            if not label_text.strip():
                return
            start_idx = len(ext_points)
            ext_points.append([start[0], start[1], start[2]])
            ext_points.append([end[0], end[1], end[2]])
            ext_lines.extend([2, start_idx, start_idx + 1])
            label_points.append([label_point[0], label_point[1], label_point[2]])
            label_texts.append(label_text.strip())

        if plane == "XY" and value is not None:
            y_base = ys[-1]
            x_base = xs[-1]
            for entry in x_entries:
                add_extension(
                    (entry.coordinate, y_base, value),
                    (entry.coordinate, y_base + offset_y, value),
                    (entry.coordinate, y_base + offset_y + label_gap_y, value),
                    entry.marker,
                )
            for entry in y_entries:
                add_extension(
                    (x_base, entry.coordinate, value),
                    (x_base + offset_x, entry.coordinate, value),
                    (x_base + offset_x + label_gap_x, entry.coordinate, value),
                    entry.marker,
                )
        elif plane == "XZ" and value is not None:
            z_base = zs[-1]
            for entry in x_entries:
                add_extension(
                    (entry.coordinate, value, z_base),
                    (entry.coordinate, value, z_base + offset_z),
                    (entry.coordinate, value, z_base + offset_z + label_gap_z),
                    entry.marker,
                )
        elif plane == "YZ" and value is not None:
            z_base = zs[-1]
            for entry in y_entries:
                add_extension(
                    (value, entry.coordinate, z_base),
                    (value, entry.coordinate, z_base + offset_z),
                    (value, entry.coordinate, z_base + offset_z + label_gap_z),
                    entry.marker,
                )
        else:
            y_base = ys[-1]
            x_base = xs[-1]
            z_base = zs[0]
            for entry in x_entries:
                add_extension(
                    (entry.coordinate, y_base, z_base),
                    (entry.coordinate, y_base + offset_y, z_base),
                    (entry.coordinate, y_base + offset_y + label_gap_y, z_base),
                    entry.marker,
                )
            for entry in y_entries:
                add_extension(
                    (x_base, entry.coordinate, z_base),
                    (x_base + offset_x, entry.coordinate, z_base),
                    (x_base + offset_x + label_gap_x, entry.coordinate, z_base),
                    entry.marker,
                )

        return (
            np.array(ext_points, dtype=float) if ext_points else np.empty((0, 3)),
            ext_lines,
            np.array(label_points, dtype=float) if label_points else np.empty((0, 3)),
            label_texts,
        )

    def _on_point_picked(self, point: np.ndarray) -> None:
        """Callback quand un point est clique dans la vue."""
        if self._project is None:
            return

        if self._draw_mode_enabled and self._project.grid.enabled:
            snapped = self._nearest_grid_point(point)
            if snapped is None:
                return
            self._show_temp_point(snapped, "snap_pick", _COLORS["draw_snap"])
            self.grid_point_picked.emit(
                float(snapped[0]),
                float(snapped[1]),
                float(snapped[2]),
            )
        return

    def _nearest_grid_point(self, point: np.ndarray) -> np.ndarray | None:
        """Retourne le point de grille le plus proche."""
        if len(self._grid_points) == 0:
            return None
        distances = np.linalg.norm(self._grid_points - point, axis=1)
        return self._grid_points[int(np.argmin(distances))]

    def eventFilter(self, watched, event) -> bool:
        """Met à jour le point de survol pendant le dessin."""
        if watched is self.plotter.interactor:
            if event.type() == QEvent.MouseMove:
                if self._cursor_pick_enabled:
                    self._update_cursor_pick_preview()
                if (
                    self._camera_drag_mode is not None
                    and bool(event.buttons() & Qt.MiddleButton)
                ):
                    self._forward_camera_drag(event)
                    return True
                if self._draw_mode_enabled:
                    self._update_hover_preview()
                if (
                    self._selection_mode_enabled
                    and self._drag_origin is not None
                    and bool(event.buttons() & Qt.LeftButton)
                ):
                    return self._handle_selection_drag(event)
            elif event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Escape:
                    if self._cursor_pick_enabled:
                        self.set_cursor_pick_mode(False)
                        self.cursor_pick_cancelled.emit()
                        return True
                    if self._draw_mode_enabled:
                        self.selection_mode_requested.emit()
                        return True
                    self._clear_selection_and_emit()
                    return True
                if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                    if self._selected_nodes or self._selected_elements or self._selected_surfaces:
                        self.selection_delete_requested.emit(
                            sorted(self._selected_nodes),
                            sorted(self._selected_elements),
                            sorted(self._selected_surfaces),
                        )
                        return True
            elif (
                event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton
            ):
                self.plotter.interactor.setFocus()
                if self._cursor_pick_enabled:
                    return self._handle_cursor_pick_click(event)
                if self._draw_mode_enabled:
                    return self._handle_draw_click(event)
                if self._selection_mode_enabled:
                    self._drag_origin = event.position().toPoint()
                    return True
            elif (
                event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.RightButton
            ):
                self.plotter.interactor.setFocus()
                if self._cursor_pick_enabled:
                    self.set_cursor_pick_mode(False)
                    self.cursor_pick_cancelled.emit()
                    return True
                if self._draw_mode_enabled:
                    self.draw_finalize_requested.emit()
                    return True
                if self._selection_mode_enabled:
                    return self._handle_object_context_click(event)
            elif (
                event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.MiddleButton
            ):
                self.plotter.interactor.setFocus()
                self._start_camera_drag(event)
                return True
            elif (
                event.type() == QEvent.MouseButtonRelease
                and event.button() == Qt.LeftButton
                and self._selection_mode_enabled
                and self._drag_origin is not None
            ):
                return self._handle_selection_release(event)
            elif (
                event.type() == QEvent.MouseButtonRelease
                and event.button() == Qt.MiddleButton
                and self._camera_drag_mode is not None
            ):
                self._stop_camera_drag(event)
                return True
            elif event.type() == QEvent.Leave:
                self._clear_hover_preview()
        return super().eventFilter(watched, event)

    def _vtk_event_modifiers(self, event) -> tuple[int, int]:
        """Convertit les modificateurs Qt en drapeaux attendus par VTK."""
        modifiers = event.modifiers()
        ctrl = int(bool(modifiers & Qt.ControlModifier))
        shift = int(bool(modifiers & Qt.ShiftModifier))
        return ctrl, shift

    def _set_vtk_mouse_event(self, event) -> None:
        """Publie la position souris courante dans l'interacteur VTK."""
        pos = event.position()
        scale = self._display_scale()
        x = int(round(pos.x() * scale))
        y = int(round(pos.y() * scale))
        ctrl, shift = self._vtk_event_modifiers(event)
        self.plotter.interactor.SetEventInformationFlipY(
            x,
            y,
            ctrl,
            shift,
            "0",
            0,
            None,
        )

    def _start_camera_drag(self, event) -> None:
        """Demarre une navigation 3D fluide sur le bouton du milieu."""
        self._camera_drag_mode = "pan" if bool(event.modifiers() & Qt.ShiftModifier) else "rotate"
        self._set_vtk_mouse_event(event)
        if self._camera_drag_mode == "rotate":
            self.plotter.interactor.LeftButtonPressEvent()
        else:
            self.plotter.interactor.MiddleButtonPressEvent()

    def _forward_camera_drag(self, event) -> None:
        """Propage le déplacement souris à l'interacteur VTK."""
        self._set_vtk_mouse_event(event)
        self.plotter.interactor.MouseMoveEvent()

    def _stop_camera_drag(self, event) -> None:
        """Termine la navigation 3D sur bouton du milieu."""
        self._set_vtk_mouse_event(event)
        if self._camera_drag_mode == "rotate":
            self.plotter.interactor.LeftButtonReleaseEvent()
        else:
            self.plotter.interactor.MiddleButtonReleaseEvent()
        self._camera_drag_mode = None

    def _handle_selection_release(self, event) -> bool:
        """Termine une sélection simple au clic."""
        release_pos = event.position().toPoint()
        drag_origin = self._drag_origin
        self._rubber_band.hide()
        self._drag_origin = None
        if drag_origin is None:
            return True

        rect = QRect(drag_origin, release_pos).normalized()
        if rect.width() <= 4 and rect.height() <= 4:
            self._select_at_click(release_pos)
        else:
            self._select_in_rect(rect)
        return True

    def _handle_selection_drag(self, event) -> bool:
        """Met à jour le rectangle de sélection pendant le glisser."""
        if self._drag_origin is None:
            return False
        current_pos = event.position().toPoint()
        rect = QRect(self._drag_origin, current_pos).normalized()
        if rect.width() <= 2 and rect.height() <= 2:
            self._rubber_band.hide()
        else:
            self._rubber_band.setGeometry(rect)
            self._rubber_band.show()
        return True

    def _handle_draw_click(self, event) -> bool:
        """Traite un clic gauche en mode dessin à partir du point survolé."""
        if self._project is None or not self._project.grid.enabled:
            return True

        snapped = None
        if self._hover_point is not None:
            snapped = np.array(self._hover_point, dtype=float)
        else:
            picked = self._pick_position_from_event(event)
            if picked is not None:
                snapped = self._nearest_grid_point(picked)

        if snapped is None:
            return True

        self._show_temp_point(snapped, "snap_pick", _COLORS["draw_snap"])
        self.grid_point_picked.emit(
            float(snapped[0]),
            float(snapped[1]),
            float(snapped[2]),
        )
        return True

    def _handle_cursor_pick_click(self, event) -> bool:
        """Recupere un point monde ou un point de grille pour un outil externe."""
        picked = self._pick_position_from_event(event)
        if picked is None:
            return True

        if (
            self._cursor_pick_snap_to_grid
            and self._project is not None
            and self._project.grid.enabled
        ):
            snapped = self._nearest_grid_point(picked)
            if snapped is None:
                return True
            picked = np.array(snapped, dtype=float)

        self._show_temp_point(picked, "snap_pick", _COLORS["draw_snap"])
        self.cursor_point_picked.emit(
            float(picked[0]),
            float(picked[1]),
            float(picked[2]),
        )
        return True

    def _pick_position_from_event(self, event) -> np.ndarray | None:
        """Projette la position écran du clic dans la scène 3D."""
        try:
            pos = event.position()
            renderer = self.plotter.iren.get_poked_renderer()
            x, y = self._qt_to_vtk_display(pos.x(), pos.y())
            self.plotter.iren.picker.Pick(x, y, 0, renderer)
            picked = np.array(self.plotter.iren.picker.GetPickPosition(), dtype=float)
        except Exception:
            return None
        if picked.shape != (3,) or not np.all(np.isfinite(picked)):
            return None
        return picked

    def _pick_position_from_screen(self, pos: QPoint) -> np.ndarray | None:
        """Projette une position écran Qt dans la scène 3D."""
        try:
            renderer = self.plotter.iren.get_poked_renderer()
            x, y = self._qt_to_vtk_display(pos.x(), pos.y())
            self.plotter.iren.picker.Pick(x, y, 0, renderer)
            picked = np.array(self.plotter.iren.picker.GetPickPosition(), dtype=float)
        except Exception:
            return None
        if picked.shape != (3,) or not np.all(np.isfinite(picked)):
            return None
        return picked

    def _update_hover_preview(self) -> None:
        """Affiche un point jaune sur l'intersection de grille visée."""
        if not self._draw_mode_enabled or self._project is None or not self._project.grid.enabled:
            self._clear_hover_preview()
            return
        if len(self._grid_points) == 0:
            self._clear_hover_preview()
            return

        try:
            picked = np.array(self.plotter.pick_mouse_position(), dtype=float)
        except Exception:
            return
        if picked.shape != (3,) or not np.all(np.isfinite(picked)):
            self._clear_hover_preview()
            return

        snapped = self._nearest_grid_point(picked)
        if snapped is None:
            self._clear_hover_preview()
            return

        hover = (float(snapped[0]), float(snapped[1]), float(snapped[2]))
        if self._hover_point == hover:
            return
        self._hover_point = hover
        self._show_temp_point(np.array(hover), "draw_hover", _COLORS["draw_hover"])

    def _update_cursor_pick_preview(self) -> None:
        """Affiche un apercu du point vise pendant un choix d'origine."""
        if not self._cursor_pick_enabled:
            self._clear_hover_preview()
            return

        try:
            picked = np.array(self.plotter.pick_mouse_position(), dtype=float)
        except Exception:
            return
        if picked.shape != (3,) or not np.all(np.isfinite(picked)):
            self._clear_hover_preview()
            return

        if (
            self._cursor_pick_snap_to_grid
            and self._project is not None
            and self._project.grid.enabled
        ):
            snapped = self._nearest_grid_point(picked)
            if snapped is None:
                self._clear_hover_preview()
                return
            picked = np.array(snapped, dtype=float)

        hover = (float(picked[0]), float(picked[1]), float(picked[2]))
        if self._hover_point == hover:
            return
        self._hover_point = hover
        self._show_temp_point(np.array(hover), "draw_hover", _COLORS["draw_hover"])

    def _clear_hover_preview(self) -> None:
        """Efface le point de survol."""
        if self._hover_point is None:
            return
        self._hover_point = None
        self.plotter.remove_actor("draw_hover", render=False)
        self.plotter.render()

    def set_drawing_mode(self, enabled: bool) -> None:
        """Active ou desactive le mode dessin."""
        self._draw_mode_enabled = enabled
        if not enabled:
            self.clear_drawing_state()
        else:
            self._update_hover_preview()

    def set_cursor_pick_mode(self, enabled: bool, *, snap_to_grid: bool = False) -> None:
        """Active un mode temporaire de choix de point dans la vue."""
        self._cursor_pick_enabled = enabled
        self._cursor_pick_snap_to_grid = snap_to_grid
        if not enabled:
            self._clear_hover_preview()
            self.plotter.remove_actor("snap_pick", render=False)
            self.plotter.render()
            return
        self._update_cursor_pick_preview()

    def set_selection_mode(self, enabled: bool) -> None:
        """Active l'outil de sélection."""
        self._selection_mode_enabled = enabled
        if not enabled and self._drag_origin is not None:
            self._drag_origin = None
            self._rubber_band.hide()

    def _node_on_active_plane(self, x: float, y: float, z: float, tol: float = 1e-9) -> bool:
        """Indique si un nœud appartient a la file actuellement active."""
        if self._active_plane is None or self._active_plane_value is None:
            return True
        if self._active_plane == "XY":
            return abs(z - self._active_plane_value) <= tol
        if self._active_plane == "XZ":
            return abs(y - self._active_plane_value) <= tol
        if self._active_plane == "YZ":
            return abs(x - self._active_plane_value) <= tol
        return True

    @staticmethod
    def plane_axis_label(plane: str) -> str:
        """Retourne l'axe fixe associé à un plan de vue."""
        return {
            "XY": "Z",
            "XZ": "Y",
            "YZ": "X",
        }.get(plane, "")

    @staticmethod
    def plane_values(grid: Grid3DData, plane: str) -> list[float]:
        """Retourne les valeurs de files disponibles pour un plan."""
        if plane == "XY":
            return grid.axis_values("Z")
        if plane == "XZ":
            return grid.axis_values("Y")
        if plane == "YZ":
            return grid.axis_values("X")
        return []

    def _plane_camera_state(
        self,
        plane: str,
        value: float,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]:
        """Calcule une vraie vue orthographique de plan/coupe."""
        center, spans, radius = self._scene_bounds(self._visible_scene_points())
        span_x, span_y, span_z = (float(v) for v in spans)
        cx, cy, cz = (float(v) for v in center)
        offset = max(radius * 4.0, 10.0)
        padding = self._CAMERA_PADDING * 0.5

        if plane == "XY":
            return (
                (cx, cy, value + offset),
                (cx, cy, value),
                (0.0, 1.0, 0.0),
                max(span_x, span_y, 1.0) * padding,
            )
        if plane == "XZ":
            return (
                (cx, value - offset, cz),
                (cx, value, cz),
                (0.0, 0.0, 1.0),
                max(span_x, span_z, 1.0) * padding,
            )
        if plane == "YZ":
            return (
                (value - offset, cy, cz),
                (value, cy, cz),
                (0.0, 0.0, 1.0),
                max(span_y, span_z, 1.0) * padding,
            )
        return (
            (cx, cy, cz + offset),
            (cx, cy, cz),
            (0.0, 1.0, 0.0),
            max(span_x, span_y, 1.0) * padding,
        )

    def _view_plane_value(self, plane: str) -> float:
        """Retourne une valeur de plan adaptée à un simple preset caméra."""
        if self._active_plane == plane and self._active_plane_value is not None:
            return float(self._active_plane_value)
        center, _spans, _radius = self._scene_bounds(self._visible_scene_points())
        if plane == "XY":
            return float(center[2])
        if plane == "XZ":
            return float(center[1])
        if plane == "YZ":
            return float(center[0])
        return 0.0

    def set_parallel_plane(
        self,
        plane: str | None,
        value: float | None = None,
        refresh_scene: bool = True,
    ) -> None:
        """Place la caméra en projection parallèle propre sur une file/plan."""
        self._active_plane = plane
        self._active_plane_value = value

        if self._project is None:
            return

        if refresh_scene:
            self.display_model(self._project)
            return

        self._apply_active_view_camera(render=True)

    def set_preview_start(self, point: tuple[float, float, float] | None) -> None:
        """Affiche le point de depart du dessin courant."""
        self._draw_start_point = point
        self.plotter.remove_actor("draw_start", render=False)
        if point is not None:
            self._show_temp_point(np.array(point), "draw_start", _COLORS["draw_start"])
        else:
            self.plotter.render()

    def clear_drawing_state(self) -> None:
        """Efface les repères temporaires de dessin."""
        self._draw_start_point = None
        self._hover_point = None
        self.plotter.remove_actor("draw_start", render=False)
        self.plotter.remove_actor("draw_hover", render=False)
        self.plotter.remove_actor("snap_pick", render=False)
        self.plotter.render()

    def clear_selection(self) -> None:
        """Efface la sélection courante."""
        self._selected_nodes.clear()
        self._selected_elements.clear()
        self._selected_surfaces.clear()
        self._selected_node = None
        self._selected_element = None
        self._selected_surface = None
        self._update_selection_actors()

    def _clear_selection_and_emit(self) -> None:
        """Efface la sélection courante et notifie l'interface."""
        self._selected_node = None
        self._selected_element = None
        self._selected_surface = None
        self.set_selected_objects([], [], [], emit_signal=True)

    def set_selected_objects(
        self,
        node_tags: list[int] | set[int] | tuple[int, ...],
        element_tags: list[int] | set[int] | tuple[int, ...],
        surface_tags: list[int] | set[int] | tuple[int, ...] | None = None,
        emit_signal: bool = False,
    ) -> None:
        """Définit la sélection courante dans la vue."""
        self._selected_nodes = set(node_tags)
        self._selected_elements = set(element_tags)
        self._selected_surfaces = set(surface_tags or [])
        self._selected_node = next(iter(self._selected_nodes), None) if len(self._selected_nodes) == 1 else None
        self._selected_element = (
            next(iter(self._selected_elements), None)
            if len(self._selected_elements) == 1
            else None
        )
        self._selected_surface = (
            next(iter(self._selected_surfaces), None)
            if len(self._selected_surfaces) == 1
            else None
        )
        self._update_selection_actors()
        if emit_signal:
            self.selection_changed.emit(
                sorted(self._selected_nodes),
                sorted(self._selected_elements),
                sorted(self._selected_surfaces),
            )

    def _show_temp_point(self, point: np.ndarray, name: str, color: str) -> None:
        """Dessine un point temporaire dans la vue."""
        mesh = pv.PolyData([point.tolist()])
        self.plotter.remove_actor(name, render=False)
        self.plotter.add_mesh(
            mesh,
            color=color,
            point_size=16,
            render_points_as_spheres=True,
            name=name,
        )
        self.plotter.render()

    def capture_view_state(self) -> dict | None:
        """Capture l'état courant de caméra pour le restaurer après refresh."""
        try:
            camera = self.plotter.camera
            return {
                "camera_position": self.plotter.camera_position,
                "parallel_projection": bool(camera.parallel_projection),
                "parallel_scale": float(camera.parallel_scale),
                "up": tuple(camera.up),
            }
        except Exception:
            return None

    def restore_view_state(self, state: dict | None) -> None:
        """Restaure un état de caméra précédemment capturé."""
        if not state:
            return
        try:
            self.plotter.camera_position = state["camera_position"]
            camera = self.plotter.camera
            camera.up = state.get("up", (0.0, 0.0, 1.0))
            camera.parallel_projection = bool(state.get("parallel_projection", False))
            if camera.parallel_projection:
                camera.parallel_scale = float(state.get("parallel_scale", camera.parallel_scale))
            self.plotter.render()
            self._refresh_section_label_overlay()
        except Exception:
            pass

    def highlight_node(self, tag: int) -> None:
        """Met en surbrillance un nœud dans la vue."""
        if self._project is None or tag not in self._project.nodes:
            return
        self.set_selected_objects([tag], [], emit_signal=False)

    def highlight_element(self, tag: int) -> None:
        """Met en surbrillance un element dans la vue."""
        if self._project is None or tag not in self._project.elements:
            return
        self.set_selected_objects([], [tag], emit_signal=False)

    def highlight_surface(self, tag: int) -> None:
        """Met en surbrillance une surface dans la vue."""
        if self._project is None or (
            tag not in self._project.surface_elements
            and tag not in self._project.plate_regions
        ):
            return
        self.set_selected_objects([], [], [tag], emit_signal=False)

    def _update_selection_actors(self, render: bool = True) -> None:
        """Met à jour les acteurs de sélection."""
        self.plotter.remove_actor("highlight_nodes", render=False)
        self.plotter.remove_actor("highlight_elems", render=False)
        self.plotter.remove_actor("highlight_elems_edges", render=False)
        self.plotter.remove_actor("highlight_surfaces", render=False)
        self.plotter.remove_actor("highlight_surfaces_edges", render=False)
        self.plotter.remove_actor("highlight_node", render=False)
        self.plotter.remove_actor("highlight_elem", render=False)

        if self._project is not None and self._selected_nodes:
            points = []
            for tag in sorted(self._selected_nodes):
                node = self._project.nodes.get(tag)
                if node is None:
                    continue
                if not self._node_on_active_plane(node.x, node.y, node.z):
                    continue
                points.append([node.x, node.y, node.z])
            if points:
                pt = pv.PolyData(points)
                pt.point_data["node_tag"] = np.array(
                    [
                        int(tag)
                        for tag in sorted(self._selected_nodes)
                        if (
                            (node := self._project.nodes.get(tag)) is not None
                            and self._node_on_active_plane(node.x, node.y, node.z)
                        )
                    ],
                    dtype=np.int32,
                )
                self.plotter.add_mesh(
                    pt,
                    color=_COLORS["node_selected"],
                    point_size=16,
                    render_points_as_spheres=True,
                    name="highlight_nodes",
                    render=False,
                )

        if self._project is not None and self._selected_elements:
            if self._use_extruded_sections():
                selected_tags = set(self._selected_elements)
                mesh = self._build_extruded_elements_mesh(
                    self._project,
                    only_tags=selected_tags,
                )
                if mesh is not None and mesh.n_cells > 0:
                    detail_mesh = self._build_extruded_section_guides_mesh(
                        self._project,
                        only_tags=selected_tags,
                    )
                    self.plotter.add_mesh(
                        mesh,
                        color=_COLORS["element_selected"],
                        smooth_shading=True,
                        name="highlight_elems",
                        render=False,
                    )
                    self._add_extruded_feature_edges(
                        mesh,
                        actor_name="highlight_elems_edges",
                        extra_mesh=detail_mesh,
                        render=False,
                    )
            else:
                points: list[list[float]] = []
                lines: list[int] = []
                for tag in sorted(self._selected_elements):
                    elem = self._project.elements.get(tag)
                    if elem is None:
                        continue
                    ni = self._project.nodes.get(elem.node_i)
                    nj = self._project.nodes.get(elem.node_j)
                    if ni is None or nj is None:
                        continue
                    if not self._node_on_active_plane(ni.x, ni.y, ni.z):
                        continue
                    if not self._node_on_active_plane(nj.x, nj.y, nj.z):
                        continue
                    start_idx = len(points)
                    points.append([ni.x, ni.y, ni.z])
                    points.append([nj.x, nj.y, nj.z])
                    lines.extend([2, start_idx, start_idx + 1])
                if points and lines:
                    mesh = pv.PolyData(np.array(points), lines=lines)
                    self.plotter.add_mesh(
                        mesh,
                        color=_COLORS["element_selected"],
                        line_width=8,
                        name="highlight_elems",
                        render=False,
                    )

        if self._project is not None and self._selected_surfaces:
            selected_tags = set(self._selected_surfaces)
            mesh = self._build_surface_elements_mesh(
                self._project,
                only_tags=selected_tags,
            )
            if mesh is not None and mesh.n_cells > 0:
                self.plotter.add_mesh(
                    mesh,
                    color=_COLORS["element_selected"],
                    opacity=0.34,
                    smooth_shading=True,
                    show_edges=False,
                    name="highlight_surfaces",
                    render=False,
                )
                self._add_extruded_feature_edges(
                    mesh,
                    actor_name="highlight_surfaces_edges",
                    render=False,
                )

        if render:
            self.plotter.render()

    def _select_in_rect(self, rect: QRect) -> None:
        """Sélectionne les objets visibles dont la projection tombe dans le cadre."""
        if self._project is None:
            self.set_selected_objects([], [], [], emit_signal=True)
            return

        rectf = QRectF(rect.normalized())
        node_tags: set[int] = set()
        element_tags: set[int] = set()
        surface_tags: set[int] = set()

        for tag, node in self._project.nodes.items():
            if not self._node_on_active_plane(node.x, node.y, node.z):
                continue
            screen_pos = self._project_world_to_screen((node.x, node.y, node.z))
            if screen_pos is not None and rectf.contains(screen_pos):
                node_tags.add(tag)

        for tag, elem in self._project.elements.items():
            ni = self._project.nodes.get(elem.node_i)
            nj = self._project.nodes.get(elem.node_j)
            if ni is None or nj is None:
                continue
            if not self._node_on_active_plane(ni.x, ni.y, ni.z):
                continue
            if not self._node_on_active_plane(nj.x, nj.y, nj.z):
                continue
            p1 = self._project_world_to_screen((ni.x, ni.y, ni.z))
            p2 = self._project_world_to_screen((nj.x, nj.y, nj.z))
            if p1 is None or p2 is None:
                continue
            if rectf.contains(p1) and rectf.contains(p2):
                element_tags.add(tag)

        for tag, surface in self._visible_surface_items(self._project):
            polygon = self._surface_screen_polygon(surface)
            if len(polygon) < 3:
                continue
            if self._polygon_intersects_rect(polygon, rectf):
                surface_tags.add(tag)

        node_tags.update(self._selected_nodes)
        element_tags.update(self._selected_elements)
        surface_tags.update(self._selected_surfaces)

        self._selected_node = None
        self._selected_element = None
        self._selected_surface = None
        self.set_selected_objects(node_tags, element_tags, surface_tags, emit_signal=True)

    def _select_at_click(self, pos: QPoint) -> None:
        """Sélection simple additive par clic avec bascule sélection/désélection."""
        picked = self._pick_visible_object(pos)
        if picked is None:
            self._clear_selection_and_emit()
            return

        kind, tag = picked
        if kind == "node":
            self._selected_node = tag
            self._selected_element = None
            self._selected_surface = None
            node_tags = set(self._selected_nodes)
            if tag in node_tags:
                node_tags.remove(tag)
            else:
                node_tags.add(tag)
            self.set_selected_objects(
                node_tags,
                self._selected_elements,
                self._selected_surfaces,
                emit_signal=True,
            )
            if tag in node_tags:
                self.node_picked.emit(tag)
            return

        if kind == "element":
            self._selected_node = None
            self._selected_element = tag
            self._selected_surface = None
            element_tags = set(self._selected_elements)
            if tag in element_tags:
                element_tags.remove(tag)
            else:
                element_tags.add(tag)
            self.set_selected_objects(
                self._selected_nodes,
                element_tags,
                self._selected_surfaces,
                emit_signal=True,
            )
            if tag in element_tags:
                self.element_picked.emit(tag)
            return

        if kind == "surface":
            self._selected_node = None
            self._selected_element = None
            self._selected_surface = tag
            surface_tags = set(self._selected_surfaces)
            if tag in surface_tags:
                surface_tags.remove(tag)
            else:
                surface_tags.add(tag)
            self.set_selected_objects(
                self._selected_nodes,
                self._selected_elements,
                surface_tags,
                emit_signal=True,
            )
            return

        self._selected_node = None
        self._selected_element = None
        self._selected_surface = None
        self.set_selected_objects([], [], [], emit_signal=True)

    def _handle_object_context_click(self, event) -> bool:
        """Selectionne une barre ou une surface et demande son menu contextuel."""
        if self._project is None:
            return True

        pos = event.position().toPoint()
        picked = self._pick_visible_object(pos)
        if picked is None or picked[0] not in {"element", "surface"}:
            return True

        tag = int(picked[1])
        if picked[0] == "element":
            self.set_selected_objects([], [tag], [], emit_signal=True)
        else:
            self.set_selected_objects([], [], [tag], emit_signal=True)
        try:
            global_pos = event.globalPosition().toPoint()
        except AttributeError:
            global_pos = self.plotter.interactor.mapToGlobal(pos)
        if picked[0] == "element":
            self.element_context_requested.emit(tag, global_pos)
        else:
            self.surface_context_requested.emit(tag, global_pos)
        return True

    def _pick_visible_object(self, pos: QPoint) -> tuple[str, int] | None:
        """Retourne l'objet visible le plus proche du clic en pixels."""
        direct_hit = self._pick_object_at_screen(pos)
        node_tag, node_dist = self._closest_node_to_screen(pos)
        elem_tag, elem_dist = self._closest_element_to_screen(pos)
        surface_tag, surface_dist = self._closest_surface_to_screen(pos)
        if direct_hit is not None:
            direct_kind, direct_tag = direct_hit
            if direct_kind == "node":
                direct_dist = self._node_distance_to_screen(direct_tag, pos)
                if direct_dist is not None:
                    node_tag, node_dist = direct_tag, direct_dist
            elif direct_kind == "element":
                elem_tag, elem_dist = direct_tag, 0.0
            elif direct_kind == "surface":
                surface_tag, surface_dist = direct_tag, 0.0

        node_threshold = 9.0
        elem_threshold = 10.0
        surface_threshold = 12.0

        node_hit = node_tag is not None and node_dist <= node_threshold
        elem_hit = elem_tag is not None and elem_dist <= elem_threshold
        surface_hit = surface_tag is not None and surface_dist <= surface_threshold

        if node_hit and (not elem_hit or node_dist <= elem_dist + 4.0):
            if not surface_hit or node_dist <= surface_dist + 4.0:
                return ("node", node_tag)
        if elem_hit and (not surface_hit or elem_dist <= surface_dist + 2.0):
            return ("element", elem_tag)
        if surface_hit:
            return ("surface", surface_tag)
        if node_hit:
            return ("node", node_tag)
        if elem_hit:
            return ("element", elem_tag)
        return None

    def _pick_object_at_screen(self, pos: QPoint) -> tuple[str, int] | None:
        """Retourne l'objet effectivement touché à l'écran."""
        picked = self._pick_position_from_screen(pos)
        if picked is None or self._project is None:
            return None

        actor = None
        try:
            actor = self.plotter.iren.picker.GetActor()
        except Exception:
            actor = None
        actor_name = self._actor_name(actor)
        if actor_name is None:
            return None

        if actor_name in {"nodes", "highlight_nodes"}:
            tag = self._node_tag_from_picked_mesh(actor)
            if tag is None:
                tag = self._closest_node_to_world(picked)
            return ("node", tag) if tag is not None else None

        if actor_name in {"elements", "highlight_elems"} or actor_name.startswith("element_"):
            tag = self._closest_element_to_world(picked)
            return ("element", tag) if tag is not None else None

        if actor_name in {"surface_elements", "highlight_surfaces"}:
            tag = self._surface_tag_from_picked_cell(actor)
            if tag is None:
                tag = self._closest_surface_to_world(picked)
            return ("surface", tag) if tag is not None else None

        return None

    def _surface_tag_from_picked_cell(self, actor) -> int | None:
        """Lit le tag de surface stocke dans la cellule VTK touchee."""
        if self._project is None:
            return None
        try:
            cell_id = int(self.plotter.iren.picker.GetCellId())
        except Exception:
            return None
        if cell_id < 0:
            return None

        try:
            dataset = actor.GetMapper().GetInput()
            tags = dataset.GetCellData().GetArray("surface_tag")
            if tags is None or cell_id >= int(tags.GetNumberOfTuples()):
                return None
            tag = int(round(float(tags.GetTuple1(cell_id))))
        except Exception:
            return None
        if tag in self._project.surface_elements or tag in self._project.plate_regions:
            return tag
        return None

    def _node_tag_from_picked_mesh(self, actor) -> int | None:
        """Lit le tag de noeud stocke dans le maillage VTK touche."""
        if self._project is None:
            return None

        try:
            dataset = actor.GetMapper().GetInput()
        except Exception:
            return None

        try:
            point_id = int(self.plotter.iren.picker.GetPointId())
        except Exception:
            point_id = -1
        tag = self._node_tag_from_point_data(dataset, point_id)
        if tag is not None:
            return tag

        try:
            cell_id = int(self.plotter.iren.picker.GetCellId())
        except Exception:
            cell_id = -1
        if cell_id < 0:
            return None

        try:
            cell_tags = dataset.GetCellData().GetArray("node_tag")
            if cell_tags is not None and cell_id < int(cell_tags.GetNumberOfTuples()):
                tag = int(round(float(cell_tags.GetTuple1(cell_id))))
                return tag if tag in self._project.nodes else None
        except Exception:
            pass

        try:
            cell = dataset.GetCell(cell_id)
            if cell is not None and cell.GetNumberOfPoints() > 0:
                point_id = int(cell.GetPointId(0))
        except Exception:
            return None
        return self._node_tag_from_point_data(dataset, point_id)

    def _node_tag_from_point_data(self, dataset, point_id: int) -> int | None:
        """Lit un tag de noeud depuis les donnees de point VTK."""
        if self._project is None or point_id < 0:
            return None
        try:
            point_tags = dataset.GetPointData().GetArray("node_tag")
            if point_tags is None or point_id >= int(point_tags.GetNumberOfTuples()):
                return None
            tag = int(round(float(point_tags.GetTuple1(point_id))))
        except Exception:
            return None
        return tag if tag in self._project.nodes else None

    def _actor_name(self, actor) -> str | None:
        """Retrouve le nom logique d'un acteur PyVista."""
        if actor is None:
            return None
        try:
            for name, known_actor in self.plotter.actors.items():
                if actor == known_actor:
                    return str(name)
        except Exception:
            return None
        return None

    def _closest_node_to_world(self, point: np.ndarray) -> int | None:
        """Retourne le nœud visible le plus proche d'un point monde."""
        if self._project is None:
            return None
        best_tag = None
        best_dist = float("inf")
        for tag, node in self._project.nodes.items():
            if not self._node_on_active_plane(node.x, node.y, node.z):
                continue
            dist = float(
                np.linalg.norm(point - np.array([node.x, node.y, node.z], dtype=float))
            )
            if dist < best_dist:
                best_dist = dist
                best_tag = tag
        return best_tag

    def _closest_element_to_world(self, point: np.ndarray) -> int | None:
        """Retourne l'élément visible le plus proche d'un point monde."""
        if self._project is None:
            return None
        best_tag = None
        best_dist = float("inf")
        for tag, elem in self._project.elements.items():
            ni = self._project.nodes.get(elem.node_i)
            nj = self._project.nodes.get(elem.node_j)
            if ni is None or nj is None:
                continue
            if not self._node_on_active_plane(ni.x, ni.y, ni.z):
                continue
            if not self._node_on_active_plane(nj.x, nj.y, nj.z):
                continue
            start = np.array([ni.x, ni.y, ni.z], dtype=float)
            end = np.array([nj.x, nj.y, nj.z], dtype=float)
            dist = self._point_to_segment_distance_world(point, start, end)
            if dist < best_dist:
                best_dist = dist
                best_tag = tag
        return best_tag

    def _closest_surface_to_world(self, point: np.ndarray) -> int | None:
        """Retourne la surface visible la plus proche d'un point monde."""
        if self._project is None:
            return None

        best_tag = None
        best_dist = float("inf")
        for tag, surface in self._visible_surface_items(self._project):
            polygon = self._surface_polygon_world_points(surface)
            if polygon is None or len(polygon) < 3:
                continue
            dist = self._point_to_surface_distance_world(point, polygon)
            if dist < best_dist:
                best_dist = dist
                best_tag = tag
        return best_tag

    @classmethod
    def _point_to_surface_distance_world(
        cls,
        point: np.ndarray,
        polygon: np.ndarray,
    ) -> float:
        """Distance d'un point monde au contour surfacique reel."""
        normal = cls._surface_normal(polygon)
        if normal is None:
            return float("inf")

        origin = polygon[0]
        plane_distance = float(np.dot(point - origin, normal))
        projected = point - plane_distance * normal

        axis_u = polygon[1] - origin
        norm_u = float(np.linalg.norm(axis_u))
        if norm_u <= 1e-12:
            return float("inf")
        axis_u = axis_u / norm_u
        axis_v = np.cross(normal, axis_u)
        norm_v = float(np.linalg.norm(axis_v))
        if norm_v <= 1e-12:
            return float("inf")
        axis_v = axis_v / norm_v

        def to_local(world_point: np.ndarray) -> QPointF:
            rel = world_point - origin
            return QPointF(float(np.dot(rel, axis_u)), float(np.dot(rel, axis_v)))

        local_polygon = [to_local(vertex) for vertex in polygon]
        local_projected = to_local(projected)
        if cls._point_in_polygon(local_projected, local_polygon):
            return abs(plane_distance)

        return min(
            cls._point_to_segment_distance_world(
                point,
                polygon[idx],
                polygon[(idx + 1) % len(polygon)],
            )
            for idx in range(len(polygon))
        )

    @staticmethod
    def _point_to_segment_distance_world(
        point: np.ndarray,
        start: np.ndarray,
        end: np.ndarray,
    ) -> float:
        """Distance point-segment en 3D."""
        segment = end - start
        seg_len2 = float(np.dot(segment, segment))
        if seg_len2 <= 1e-12:
            return float(np.linalg.norm(point - start))
        t = float(np.dot(point - start, segment) / seg_len2)
        t = max(0.0, min(1.0, t))
        projection = start + t * segment
        return float(np.linalg.norm(point - projection))

    def _closest_node_to_screen(self, pos: QPoint) -> tuple[int | None, float]:
        """Retourne le nœud visible le plus proche en pixels."""
        if self._project is None:
            return None, float("inf")
        hits = self._node_screen_hits(pos)
        if not hits:
            return None, float("inf")

        min_distance = min(hit.distance for hit in hits)
        close_hits = [
            hit for hit in hits
            if hit.distance <= min_distance + 2.0
        ]
        best = min(close_hits, key=lambda hit: (hit.depth, hit.distance, hit.tag))
        return best.tag, best.distance

    def _node_screen_hits(self, pos: QPoint) -> list[_NodeScreenHit]:
        """Retourne les noeuds candidats sous le clic, avec profondeur camera."""
        if self._project is None:
            return []

        click = QPointF(pos)
        hits: list[_NodeScreenHit] = []
        for tag, node in self._project.nodes.items():
            if not self._node_on_active_plane(node.x, node.y, node.z):
                continue
            display_pos = self._project_world_to_display((node.x, node.y, node.z))
            if display_pos is None:
                continue
            screen_pos = self._vtk_to_qt_display(display_pos[0], display_pos[1])
            dist = (
                (screen_pos.x() - click.x()) ** 2
                + (screen_pos.y() - click.y()) ** 2
            ) ** 0.5
            hits.append(
                _NodeScreenHit(
                    tag=int(tag),
                    distance=float(dist),
                    depth=float(display_pos[2]),
                )
            )
        return hits

    def _node_distance_to_screen(self, tag: int, pos: QPoint) -> float | None:
        """Distance ecran entre un clic et le centre projete d'un noeud."""
        if self._project is None:
            return None
        node = self._project.nodes.get(tag)
        if node is None or not self._node_on_active_plane(node.x, node.y, node.z):
            return None
        display_pos = self._project_world_to_display((node.x, node.y, node.z))
        if display_pos is None:
            return None
        screen_pos = self._vtk_to_qt_display(display_pos[0], display_pos[1])
        click = QPointF(pos)
        return float(
            (
                (screen_pos.x() - click.x()) ** 2
                + (screen_pos.y() - click.y()) ** 2
            ) ** 0.5
        )

    def _closest_element_to_screen(self, pos: QPoint) -> tuple[int | None, float]:
        """Retourne l'élément visible le plus proche en pixels."""
        if self._project is None:
            return None, float("inf")
        best_tag = None
        best_dist = float("inf")
        click = QPointF(pos)
        for tag, elem in self._project.elements.items():
            ni = self._project.nodes.get(elem.node_i)
            nj = self._project.nodes.get(elem.node_j)
            if ni is None or nj is None:
                continue
            if not self._node_on_active_plane(ni.x, ni.y, ni.z):
                continue
            if not self._node_on_active_plane(nj.x, nj.y, nj.z):
                continue
            p1 = self._project_world_to_screen((ni.x, ni.y, ni.z))
            p2 = self._project_world_to_screen((nj.x, nj.y, nj.z))
            if p1 is None or p2 is None:
                continue
            dist = self._point_to_segment_distance(click, p1, p2)
            if dist < best_dist:
                best_dist = dist
                best_tag = tag
        return best_tag, best_dist

    def _closest_surface_to_screen(self, pos: QPoint) -> tuple[int | None, float]:
        """Retourne la surface visible la plus proche en pixels."""
        if self._project is None:
            return None, float("inf")

        hits = self._surface_screen_hits(pos)
        if not hits:
            return None, float("inf")

        inside_hits = [hit for hit in hits if hit.inside]
        if inside_hits:
            best = min(inside_hits, key=lambda hit: (hit.depth, hit.distance, hit.tag))
            return best.tag, 0.0

        best = min(hits, key=lambda hit: (hit.distance, hit.depth, hit.tag))
        return best.tag, best.distance

    def _surface_screen_hits(self, pos: QPoint) -> list[_SurfaceScreenHit]:
        """Retourne les plaques candidates sous le clic, avec profondeur camera."""
        if self._project is None:
            return []

        click = QPointF(pos)
        hits: list[_SurfaceScreenHit] = []
        for tag, surface in self._visible_surface_items(self._project):
            polygon, depths = self._surface_screen_polygon_data(surface)
            if len(polygon) < 3:
                continue
            inside = self._point_in_polygon(click, polygon)
            distance = 0.0 if inside else self._point_to_polygon_distance(click, polygon)
            depth = self._surface_depth_at_screen_point(click, polygon, depths)
            hits.append(
                _SurfaceScreenHit(
                    tag=int(tag),
                    distance=float(distance),
                    depth=float(depth),
                    inside=inside,
                )
            )
        return hits

    def _surface_screen_polygon(self, surface: "SurfaceElementData") -> list[QPointF]:
        """Projette les sommets visibles d'une surface en coordonnées écran."""
        polygon, _depths = self._surface_screen_polygon_data(surface)
        return polygon

    def _surface_screen_polygon_data(
        self,
        surface: "SurfaceElementData",
    ) -> tuple[list[QPointF], list[float]]:
        """Projette une surface en coordonnees ecran et conserve sa profondeur."""
        polygon = self._surface_polygon_world_points(surface)
        if polygon is None:
            return [], []

        points: list[QPointF] = []
        depths: list[float] = []
        for point in polygon:
            display_pos = self._project_world_to_display(
                (float(point[0]), float(point[1]), float(point[2]))
            )
            if display_pos is None:
                return [], []
            points.append(self._vtk_to_qt_display(display_pos[0], display_pos[1]))
            depths.append(float(display_pos[2]))
        return points, depths

    @classmethod
    def _surface_depth_at_screen_point(
        cls,
        point: QPointF,
        polygon: list[QPointF],
        depths: list[float],
    ) -> float:
        """Interpole la profondeur ecran au point clique dans la plaque."""
        if len(polygon) < 3 or len(depths) != len(polygon):
            return float("inf")

        for idx in range(1, len(polygon) - 1):
            weights = cls._triangle_barycentric(
                point,
                polygon[0],
                polygon[idx],
                polygon[idx + 1],
            )
            if weights is None:
                continue
            w0, w1, w2 = weights
            if min(w0, w1, w2) >= -1e-6:
                return float(w0 * depths[0] + w1 * depths[idx] + w2 * depths[idx + 1])

        return float(sum(depths) / len(depths))

    @staticmethod
    def _triangle_barycentric(
        point: QPointF,
        a: QPointF,
        b: QPointF,
        c: QPointF,
    ) -> tuple[float, float, float] | None:
        """Coordonnees barycentriques 2D dans un triangle ecran."""
        v0x = b.x() - a.x()
        v0y = b.y() - a.y()
        v1x = c.x() - a.x()
        v1y = c.y() - a.y()
        v2x = point.x() - a.x()
        v2y = point.y() - a.y()
        denom = v0x * v1y - v1x * v0y
        if abs(denom) <= 1e-12:
            return None
        w1 = (v2x * v1y - v1x * v2y) / denom
        w2 = (v0x * v2y - v2x * v0y) / denom
        w0 = 1.0 - w1 - w2
        return float(w0), float(w1), float(w2)

    def _project_world_to_screen(
        self,
        point: tuple[float, float, float],
    ) -> QPointF | None:
        """Projette un point monde en coordonnées écran Qt."""
        display_pos = self._project_world_to_display(point)
        if display_pos is None:
            return None
        return self._vtk_to_qt_display(display_pos[0], display_pos[1])

    def _project_world_to_display(
        self,
        point: tuple[float, float, float],
    ) -> tuple[float, float, float] | None:
        """Projette un point monde en coordonnees d'affichage VTK."""
        try:
            renderer = self.plotter.renderer
            renderer.SetWorldPoint(point[0], point[1], point[2], 1.0)
            renderer.WorldToDisplay()
            x, y, z = renderer.GetDisplayPoint()
            if not np.all(np.isfinite([x, y, z])):
                return None
            return float(x), float(y), float(z)
        except Exception:
            return None

    def _display_scale(self) -> float:
        """Retourne le facteur HiDPI appliqué par QVTK."""
        try:
            scale = float(self.plotter.interactor.devicePixelRatioF())
        except Exception:
            scale = 1.0
        return scale if scale > 0.0 else 1.0

    def _qt_to_vtk_display(self, x: float, y: float) -> tuple[float, float]:
        """Convertit une position Qt en coordonnées d'affichage VTK."""
        scale = self._display_scale()
        height = float(self.plotter.interactor.height())
        return float(x * scale), float((height - y - 1.0) * scale)

    def _vtk_to_qt_display(self, x: float, y: float) -> QPointF:
        """Convertit une position d'affichage VTK en coordonnées Qt."""
        scale = self._display_scale()
        height = float(self.plotter.interactor.height())
        return QPointF(float(x) / scale, height - (float(y) / scale) - 1.0)

    @staticmethod
    def _point_to_segment_distance(point: QPointF, start: QPointF, end: QPointF) -> float:
        """Distance point-segment en coordonnées écran."""
        vx = end.x() - start.x()
        vy = end.y() - start.y()
        wx = point.x() - start.x()
        wy = point.y() - start.y()
        seg_len2 = vx * vx + vy * vy
        if seg_len2 <= 1e-9:
            return ((point.x() - start.x()) ** 2 + (point.y() - start.y()) ** 2) ** 0.5
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / seg_len2))
        proj_x = start.x() + t * vx
        proj_y = start.y() + t * vy
        return ((point.x() - proj_x) ** 2 + (point.y() - proj_y) ** 2) ** 0.5

    @classmethod
    def _point_to_polygon_distance(
        cls,
        point: QPointF,
        polygon: list[QPointF],
    ) -> float:
        """Distance minimale point-polygone en coordonnées écran."""
        if len(polygon) < 2:
            return float("inf")

        best = float("inf")
        for idx, start in enumerate(polygon):
            end = polygon[(idx + 1) % len(polygon)]
            best = min(best, cls._point_to_segment_distance(point, start, end))
        return best

    @staticmethod
    def _point_in_polygon(point: QPointF, polygon: list[QPointF]) -> bool:
        """Teste si un point est contenu dans un polygone écran par lancer de rayon."""
        if len(polygon) < 3:
            return False

        inside = False
        x = point.x()
        y = point.y()
        prev = polygon[-1]
        for curr in polygon:
            x1 = prev.x()
            y1 = prev.y()
            x2 = curr.x()
            y2 = curr.y()
            if (y1 > y) != (y2 > y):
                x_inter = x1 + ((y - y1) * (x2 - x1) / max(y2 - y1, 1e-12))
                if x < x_inter:
                    inside = not inside
            prev = curr
        return inside

    @classmethod
    def _polygon_intersects_rect(
        cls,
        polygon: list[QPointF],
        rect: QRectF,
    ) -> bool:
        """Indique si un polygone projété intersecte un cadre de sélection."""
        if len(polygon) < 3:
            return False
        if any(rect.contains(point) for point in polygon):
            return True
        if cls._point_in_polygon(rect.center(), polygon):
            return True
        for idx, start in enumerate(polygon):
            end = polygon[(idx + 1) % len(polygon)]
            if cls._segment_intersects_rect(start, end, rect):
                return True
        return False

    @staticmethod
    def _segment_intersects_rect(start: QPointF, end: QPointF, rect: QRectF) -> bool:
        """Indique si un segment coupe ou entre dans un rectangle."""
        if rect.contains(start) or rect.contains(end):
            return True
        line = QLineF(start, end)
        rect_lines = [
            QLineF(rect.topLeft(), rect.topRight()),
            QLineF(rect.topRight(), rect.bottomRight()),
            QLineF(rect.bottomRight(), rect.bottomLeft()),
            QLineF(rect.bottomLeft(), rect.topLeft()),
        ]
        return any(line.intersects(edge)[0] != QLineF.NoIntersection for edge in rect_lines)

    def display_deformed(
        self,
        project: ProjectModel,
        displacements: dict,
        scale: float = 10.0,
        preserve_camera: bool = False,
    ) -> None:
        """Affiche la déformée superposée au modèle initial."""
        self._clear_scene()
        self._apply_background()
        self._project = project
        self._grid_points = np.empty((0, 3))
        self._draw_grid(project.grid)

        if not project.nodes or not displacements:
            self._finalize_scene_view(preserve_camera=preserve_camera)
            return

        tag_to_idx: dict[int, int] = {}
        coords_init: list[list[float]] = []
        coords_def: list[list[float]] = []
        for i, (tag, node) in enumerate(project.nodes.items()):
            tag_to_idx[tag] = i
            coords_init.append([node.x, node.y, node.z])
            disp = displacements.get(tag)
            ux = disp.ux if disp else 0.0
            uy = disp.uy if disp else 0.0
            uz = disp.uz if disp else 0.0
            coords_def.append(
                [
                    node.x + scale * ux,
                    node.y + scale * uy,
                    node.z + scale * uz,
                ]
            )

        pts_init = np.array(coords_init)
        pts_def = np.array(coords_def)

        lines: list[int] = []
        for elem in project.elements.values():
            idx_i = tag_to_idx.get(elem.node_i)
            idx_j = tag_to_idx.get(elem.node_j)
            if idx_i is not None and idx_j is not None:
                lines.extend([2, idx_i, idx_j])

        if lines:
            mesh_init = pv.PolyData(pts_init, lines=lines)
            self.plotter.add_mesh(
                mesh_init,
                color=_COLORS["undeformed"],
                line_width=2,
                render=False,
            )

            mesh_def = pv.PolyData(pts_def, lines=lines)
            self.plotter.add_mesh(
                mesh_def,
                color=_COLORS["deformed"],
                line_width=4,
                render=False,
            )

        self._finalize_scene_view(preserve_camera=preserve_camera)

    def clear(self) -> None:
        """Efface la vue."""
        self._clear_scene()
        self._apply_background()
        self._restore_camera()

    def set_view_xy(self) -> None:
        """Vue de dessus (plan XY, regard selon -Z)."""
        value = self._view_plane_value("XY")
        state = self._plane_camera_state("XY", value)
        self._apply_camera_state(
            _CameraState(
                position=state[0],
                focal_point=state[1],
                up=state[2],
                parallel_projection=True,
                parallel_scale=max(state[3], 0.5),
            )
        )

    def set_view_xz(self) -> None:
        """Vue de face (plan XZ, Z vertical)."""
        value = self._view_plane_value("XZ")
        state = self._plane_camera_state("XZ", value)
        self._apply_camera_state(
            _CameraState(
                position=state[0],
                focal_point=state[1],
                up=state[2],
                parallel_projection=True,
                parallel_scale=max(state[3], 0.5),
            )
        )

    def set_view_yz(self) -> None:
        """Vue laterale (plan YZ, Z vertical)."""
        value = self._view_plane_value("YZ")
        state = self._plane_camera_state("YZ", value)
        self._apply_camera_state(
            _CameraState(
                position=state[0],
                focal_point=state[1],
                up=state[2],
                parallel_projection=True,
                parallel_scale=max(state[3], 0.5),
            )
        )

    def set_view_isometric(self) -> None:
        """Vue isométrique."""
        self._restore_camera()

    def screenshot(self, filename: str) -> None:
        """Sauvegarde une capture d'écran."""
        self.plotter.screenshot(filename)

    def closeEvent(self, event) -> None:
        """Ferme proprement le widget PyVista."""
        super().closeEvent(event)
