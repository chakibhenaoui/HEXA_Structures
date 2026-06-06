"""Interactive 2D Section Builder for custom polygon sections."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
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
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
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
from core.sectionproperties_adapter import (
    SectionPropertiesCalculationError,
    SectionPropertiesMesh,
    SectionPropertiesResult,
    SectionPropertiesUnavailable,
    calculate_polygon_sectionproperties_section,
    is_sectionproperties_available,
)


class SectionBuilderView(QGraphicsView):
    """QGraphicsView canvas for drawing one closed outer section contour."""

    geometry_changed = Signal()
    closed_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._grid_step = 0.05
        self._snap_enabled = True
        self._points: list[Point2D] = []
        self._closed = False
        self._path_item = QGraphicsPathItem()
        self._mesh_item: QGraphicsPathItem | None = None
        self._polygon_item: QGraphicsPolygonItem | None = None
        self._centroid_item: QGraphicsEllipseItem | None = None
        self._point_items: list[QGraphicsEllipseItem] = []
        self._grid_items: list[QGraphicsLineItem] = []
        self._centroid: Point2D | None = None
        self._mesh: SectionPropertiesMesh | None = None
        self._mesh_visible = True

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

    def is_closed(self) -> bool:
        """Return whether the contour is closed."""
        return self._closed

    def set_grid_step(self, step: float) -> None:
        """Set grid and snap spacing in meters."""
        self._grid_step = max(float(step), 0.001)
        self._draw_grid()

    def set_snap_enabled(self, enabled: bool) -> None:
        """Enable or disable grid snapping."""
        self._snap_enabled = bool(enabled)

    def set_points(self, points: list[Point2D], *, closed: bool = False) -> None:
        """Set points programmatically, useful for tests and future imports."""
        self._points = [(float(y), float(z)) for y, z in points]
        self._closed = bool(closed and len(self._points) >= 3)
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self._closed)

    def clear_section(self) -> None:
        """Clear the current contour."""
        self._points.clear()
        self._closed = False
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(False)

    def remove_last_point(self) -> None:
        """Remove the last drawn point."""
        if not self._points:
            return
        self._points.pop()
        self._closed = False
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(False)

    def set_point(self, index: int, point: Point2D) -> bool:
        """Update one existing point."""
        if index < 0 or index >= len(self._points):
            return False
        self._points[index] = self._snap_point(QPointF(point[0], point[1]))
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        return True

    def insert_point_after(self, index: int | None = None) -> int:
        """Insert a point after index and return the inserted row."""
        if not self._points:
            self._points.append((0.0, 0.0))
            self._closed = False
            inserted = 0
        else:
            if index is None or index < 0 or index >= len(self._points):
                index = len(self._points) - 1
            y0, z0 = self._points[index]
            if self._closed or index < len(self._points) - 1:
                next_index = (index + 1) % len(self._points)
                y1, z1 = self._points[next_index]
                point = ((y0 + y1) * 0.5, (z0 + z1) * 0.5)
            else:
                point = (y0 + self._grid_step, z0)
            inserted = index + 1
            self._points.insert(inserted, self._snap_point(QPointF(point[0], point[1])))
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self._closed)
        return inserted

    def remove_point(self, index: int) -> bool:
        """Remove one point by index."""
        if index < 0 or index >= len(self._points):
            return False
        self._points.pop(index)
        if len(self._points) < 3:
            self._closed = False
        self._centroid = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(self._closed)
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
        if len(self._points) < 3:
            return False
        self._closed = True
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()
        self.closed_changed.emit(True)
        return True

    def add_point(self, point: Point2D) -> None:
        """Append one point to the current open contour."""
        if self._closed:
            return
        self._points.append(self._snap_point(QPointF(point[0], point[1])))
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton:
            self.close_contour()
            return
        if event.button() != Qt.LeftButton or self._closed:
            super().mousePressEvent(event)
            return

        point = self._snap_point(self.mapToScene(event.position().toPoint()))
        if len(self._points) >= 3 and self._distance(point, self._points[0]) <= self._grid_step * 0.75:
            self.close_contour()
            return
        self._points.append(point)
        self._centroid = None
        self._mesh = None
        self._refresh_items()
        self.geometry_changed.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)

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
        pen = QPen(QColor("#1f2933"), 0)
        pen.setCosmetic(True)
        self._path_item.setPen(pen)
        self._path_item.setPath(path)
        self._path_item.setZValue(5)

        if self._closed and len(self._points) >= 3:
            polygon = QPolygonF([QPointF(y, z) for y, z in self._points])
            self._polygon_item = self._scene.addPolygon(
                polygon,
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
        point_brush = QBrush(QColor("#ffffff"))
        radius = 0.012
        for y, z in self._points:
            item = self._scene.addEllipse(y - radius, z - radius, radius * 2, radius * 2, point_pen, point_brush)
            item.setZValue(8)
            self._point_items.append(item)

        if self._centroid is not None:
            y, z = self._centroid
            centroid_pen = QPen(QColor("#c53030"), 0)
            centroid_pen.setCosmetic(True)
            self._centroid_item = self._scene.addEllipse(
                y - radius * 1.35,
                z - radius * 1.35,
                radius * 2.7,
                radius * 2.7,
                centroid_pen,
                QBrush(QColor("#c53030")),
            )
            self._centroid_item.setZValue(12)


class SectionBuilderDialog(QDialog):
    """Dialog used to draw and analyze one custom polygon section."""

    def __init__(
        self,
        parent=None,
        *,
        materials: dict | None = None,
        name: str = "",
        material_tag: int | None = None,
    ):
        super().__init__(parent)
        self._materials = materials or {}
        self._properties: PolygonSectionProperties | None = None
        self._sectionproperties_result: SectionPropertiesResult | None = None
        self._sectionproperties_available = is_sectionproperties_available()
        self._result: dict | None = None
        self._updating_points_table = False

        self.setWindowTitle(self.tr("Section Builder HEXA"))
        self.setMinimumSize(1120, 720)
        self.resize(1240, 780)

        self._view = SectionBuilderView(self)
        self._edit_name = QLineEdit(name or self.tr("Section personnalisée"), self)
        self._combo_material = QComboBox(self)
        self._spin_grid = QDoubleSpinBox(self)
        self._spin_grid.setRange(0.001, 1.0)
        self._spin_grid.setDecimals(3)
        self._spin_grid.setSingleStep(0.01)
        self._spin_grid.setSuffix(" m")
        self._spin_grid.setValue(0.05)
        self._chk_snap = QPushButton(self.tr("Accrochage grille actif"), self)
        self._chk_snap.setCheckable(True)
        self._chk_snap.setChecked(True)
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

        self._setup_ui()
        self._populate_materials(material_tag)
        self._connect_signals()
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

    def _setup_ui(self) -> None:
        main = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self._build_canvas_panel())
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main.addWidget(splitter, 1)
        main.addWidget(self._button_box)

    def _build_canvas_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.addWidget(self._view, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self._btn_close)
        buttons.addWidget(self._btn_undo)
        buttons.addWidget(self._btn_insert)
        buttons.addWidget(self._btn_delete)
        buttons.addWidget(self._btn_clear)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(self._lbl_status)
        return panel

    def _build_side_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        info_group = QGroupBox(self.tr("Definition"), panel)
        form = QFormLayout(info_group)
        form.addRow(self.tr("Nom :"), self._edit_name)
        form.addRow(self.tr("Materiau :"), self._combo_material)
        form.addRow(self.tr("Pas de grille :"), self._spin_grid)
        form.addRow("", self._chk_snap)
        layout.addWidget(info_group)
        points_group = QGroupBox(self.tr("Points du contour"), panel)
        points_layout = QVBoxLayout(points_group)
        points_layout.addWidget(self._table_points)
        points_layout.addWidget(self._lbl_dimensions)
        layout.addWidget(points_group, 1)
        results_group = QGroupBox(self.tr("Analyse"), panel)
        results_layout = QVBoxLayout(results_group)
        results_layout.addWidget(self._chk_use_sectionproperties)
        mesh_form = QFormLayout()
        mesh_form.addRow(self.tr("Surface max. de maille :"), self._spin_mesh_area)
        results_layout.addLayout(mesh_form)
        results_layout.addWidget(self._chk_show_mesh)
        results_layout.addWidget(self._btn_analyze)
        results_layout.addWidget(self._lbl_results)
        layout.addWidget(results_group)
        return panel

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

    def _connect_signals(self) -> None:
        self._view.geometry_changed.connect(self._on_geometry_changed)
        self._view.closed_changed.connect(lambda _closed: self._refresh_status())
        self._spin_grid.valueChanged.connect(self._view.set_grid_step)
        self._chk_snap.toggled.connect(self._on_snap_toggled)
        self._chk_use_sectionproperties.toggled.connect(lambda _checked: self._invalidate_result())
        self._spin_mesh_area.valueChanged.connect(lambda _value: self._invalidate_result())
        self._chk_show_mesh.toggled.connect(self._on_mesh_visible_toggled)
        self._table_points.itemChanged.connect(self._on_point_table_item_changed)
        self._btn_close.clicked.connect(self._close_contour)
        self._btn_undo.clicked.connect(self._view.remove_last_point)
        self._btn_insert.clicked.connect(self._insert_point)
        self._btn_delete.clicked.connect(self._delete_selected_point)
        self._btn_clear.clicked.connect(self._view.clear_section)
        self._btn_analyze.clicked.connect(lambda: self._analyze(show_errors=True))
        self._button_box.accepted.connect(self._accept)
        self._button_box.rejected.connect(self.reject)

    def _on_geometry_changed(self) -> None:
        self._invalidate_result()
        self._refresh_points()
        self._refresh_status()

    def _invalidate_result(self) -> None:
        self._properties = None
        self._sectionproperties_result = None
        self._result = None
        self._view.set_centroid(None)
        self._view.set_mesh(None)
        ok_button = self._button_box.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setEnabled(False)

    def _refresh_points(self) -> None:
        points = self._view.points()
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
        points = self._view.points()
        self._btn_insert.setEnabled(bool(points))
        self._btn_delete.setEnabled(bool(points))
        if self._view.is_closed():
            self._lbl_status.setText(
                self.tr("Contour ferme : {count} point(s).").format(count=len(points))
            )
            self._btn_analyze.setEnabled(True)
        else:
            self._lbl_status.setText(
                self.tr(
                    "Cliquez sur la grille pour dessiner le contour. Cliquez pres du premier point ou utilisez Fermer le contour."
                )
            )
            self._btn_analyze.setEnabled(False)

    def _refresh_dimensions(self) -> None:
        points = self._view.points()
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
        if row < 0 or row >= len(self._view.points()):
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

        sp_result = self._calculate_with_sectionproperties(show_errors=show_errors)
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

    def _calculate_with_sectionproperties(
        self,
        *,
        show_errors: bool,
    ) -> SectionPropertiesResult | None:
        if not self._chk_use_sectionproperties.isChecked():
            return None
        try:
            return calculate_polygon_sectionproperties_section(
                self._view.points(),
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
