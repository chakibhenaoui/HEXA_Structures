"""Macro plate property dialog."""

from __future__ import annotations

import math

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.geometry.plate_intersections import detect_plate_intersections
from core.model_data import (
    PLATE_MESH_MODE_AUTO,
    ProjectModel,
    normalize_plate_mesh_mode,
)
from core.plate_mesh_settings import effective_plate_mesh_divisions
from gui.dialogs.element_properties_dlg import _fmt, _object_items


class PlateRegionPropertiesDialog(QDialog):
    """Display macro plate properties and diagnostics."""

    def __init__(
        self,
        parent,
        project: ProjectModel,
        plate_tag: int,
        *,
        case_name: str | None = None,
        case_results: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.plate_tag = int(plate_tag)
        self.plate = project.plate_regions[self.plate_tag]
        self.case_name = case_name
        self.case_results = case_results or {}

        suffix = f" - {case_name}" if case_name else ""
        self.setWindowTitle(f"Proprietes de la plaque macro P{self.plate_tag}{suffix}")
        self.resize(820, 640)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_geometry_tab(), "Geometrie")
        self.tabs.addTab(self._build_mesh_tab(), "Maillage")
        self.tabs.addTab(self._build_diagnostics_tab(), "Intersections")
        self.tabs.addTab(self._build_loads_tab(), "Charges")

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_geometry_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        section = self.project.sections.get(self.plate.section_tag)

        general = QGroupBox("Identification", tab)
        form = QFormLayout(general)
        form.addRow("Plaque :", QLabel(f"P{self.plate.tag}", general))
        form.addRow("Type :", QLabel("Plaque macro", general))
        form.addRow(
            "Noeuds :",
            QLabel(
                ", ".join(f"N{tag}" for tag in self.plate.corner_node_tags),
                general,
            ),
        )
        form.addRow(
            "Section :",
            QLabel(
                f"{section.name} (T{section.tag})" if section is not None else "-",
                general,
            ),
        )
        form.addRow("Formulation :", QLabel(self.plate.formulation, general))
        if self.case_name:
            form.addRow("Cas courant :", QLabel(self.case_name, general))
        layout.addWidget(general)

        geometry = QGroupBox("Geometrie", tab)
        geom_form = QFormLayout(geometry)
        centroid = self._centroid()
        normal = self._normal()
        geom_form.addRow("Aire :", QLabel(f"{_fmt(self._area())} m2", geometry))
        geom_form.addRow(
            "Centre :",
            QLabel(
                f"({_fmt(centroid[0])}, {_fmt(centroid[1])}, {_fmt(centroid[2])}) m",
                geometry,
            ),
        )
        geom_form.addRow(
            "Normale locale :",
            QLabel(
                "-"
                if normal is None
                else f"{_fmt(normal[0])} / {_fmt(normal[1])} / {_fmt(normal[2])}",
                geometry,
            ),
        )
        layout.addWidget(geometry)

        table = self._make_table(["Noeud", "X", "Y", "Z"])
        rows = []
        for tag in self.plate.corner_node_tags:
            node = self.project.nodes.get(int(tag))
            if node is None:
                continue
            rows.append([
                f"N{tag}",
                f"{_fmt(node.x)} m",
                f"{_fmt(node.y)} m",
                f"{_fmt(node.z)} m",
            ])
        self._fill_table(table, rows)
        layout.addWidget(table, 1)
        return tab

    def _build_mesh_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        mesh_nx, mesh_ny = effective_plate_mesh_divisions(self.project, self.plate)
        mode = normalize_plate_mesh_mode(getattr(self.plate, "mesh_mode", None))

        group = QGroupBox("Maillage structure", tab)
        form = QFormLayout(group)
        form.addRow(
            "Mode :",
            QLabel("Automatique" if mode == PLATE_MESH_MODE_AUTO else "Utilisateur", group),
        )
        form.addRow("Demande X :", QLabel(str(int(self.plate.mesh_nx)), group))
        form.addRow("Demande Y :", QLabel(str(int(self.plate.mesh_ny)), group))
        form.addRow("Retenu X :", QLabel(str(mesh_nx), group))
        form.addRow("Retenu Y :", QLabel(str(mesh_ny), group))
        layout.addWidget(group)

        section = self.project.sections.get(self.plate.section_tag)
        table = self._make_table(["Propriete", "Valeur"])
        rows: list[tuple[str, object]] = []
        if section is not None:
            rows.extend((f"section.{key}", value) for key, value in _object_items(section.properties))
        self._fill_table(table, [(name, _fmt(value)) for name, value in rows])
        layout.addWidget(table, 1)
        return tab

    def _build_diagnostics_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        try:
            report = detect_plate_intersections(self.project, self.plate)
        except ValueError as exc:
            label = QLabel(f"Diagnostic indisponible : {exc}", tab)
            label.setWordWrap(True)
            layout.addWidget(label)
            return tab

        node_table = self._make_table(["Noeud", "Position", "u", "v", "Distance"])
        node_rows = [
            [
                f"N{hit.node_tag}",
                hit.location.value,
                _fmt(hit.u),
                _fmt(hit.v),
                f"{_fmt(hit.distance_to_plane)} m",
            ]
            for hit in report.node_hits
        ]
        self._fill_table(node_table, node_rows)
        layout.addWidget(node_table)

        bar_table = self._make_table(["Barre", "Diagnostic", "u", "v", "Message"])
        bar_rows = [
            [
                f"E{hit.element_tag}",
                hit.kind.value,
                "-" if hit.u is None else _fmt(hit.u),
                "-" if hit.v is None else _fmt(hit.v),
                hit.message,
            ]
            for hit in report.bar_hits
        ]
        self._fill_table(bar_table, bar_rows)
        layout.addWidget(bar_table, 1)
        return tab

    def _build_loads_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        surface_load_table = self._make_table(["Cas", "Tag", "qX", "qY", "qZ"])
        surface_rows = []
        for load in self.project.plate_surface_loads:
            if int(load.plate_tag) != self.plate_tag:
                continue
            load_case = self.project.loads.get(int(load.load_tag))
            surface_rows.append([
                load_case.name if load_case is not None else "Cas introuvable",
                f"T{load.load_tag}",
                f"{_fmt(load.qx)} kN/m2",
                f"{_fmt(load.qy)} kN/m2",
                f"{_fmt(load.qz)} kN/m2",
            ])
        self._fill_table(surface_load_table, surface_rows)
        layout.addWidget(surface_load_table)

        edge_table = self._make_table(["Bord", "Ux", "Uy", "Uz", "Rx", "Ry", "Rz"])
        edge_rows = []
        for support in self.project.plate_edge_supports:
            if int(support.plate_tag) != self.plate_tag:
                continue
            edge_rows.append([support.edge, *[str(value) for value in support.fixities]])
        self._fill_table(edge_table, edge_rows)
        layout.addWidget(edge_table)
        return tab

    def _points(self) -> list[tuple[float, float, float]]:
        points = []
        for tag in self.plate.corner_node_tags:
            node = self.project.nodes.get(int(tag))
            if node is not None:
                points.append((float(node.x), float(node.y), float(node.z)))
        return points

    def _centroid(self) -> tuple[float, float, float]:
        points = self._points()
        if not points:
            return 0.0, 0.0, 0.0
        count = float(len(points))
        return (
            sum(point[0] for point in points) / count,
            sum(point[1] for point in points) / count,
            sum(point[2] for point in points) / count,
        )

    def _area(self) -> float:
        points = self._points()
        if len(points) < 3:
            return 0.0
        if len(points) == 3:
            return self._triangle_area(points[0], points[1], points[2])
        return (
            self._triangle_area(points[0], points[1], points[2])
            + self._triangle_area(points[0], points[2], points[3])
        )

    def _normal(self) -> tuple[float, float, float] | None:
        points = self._points()
        if len(points) < 3:
            return None
        origin = points[0]
        for idx in range(1, len(points) - 1):
            normal = self._cross(
                self._sub(points[idx], origin),
                self._sub(points[idx + 1], origin),
            )
            norm = math.sqrt(sum(value * value for value in normal))
            if norm > 1e-12:
                return normal[0] / norm, normal[1] / norm, normal[2] / norm
        return None

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    @staticmethod
    def _fill_table(
        table: QTableWidget,
        rows: list[list[object] | tuple[object, ...]],
    ) -> None:
        table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        if not rows:
            table.setRowCount(1)
            item = QTableWidgetItem("Aucune donnee")
            table.setItem(0, 0, item)
            table.setSpan(0, 0, 1, table.columnCount())

    @staticmethod
    def _sub(
        p1: tuple[float, float, float],
        p0: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        return p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]

    @staticmethod
    def _cross(
        v1: tuple[float, float, float],
        v2: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        return (
            v1[1] * v2[2] - v1[2] * v2[1],
            v1[2] * v2[0] - v1[0] * v2[2],
            v1[0] * v2[1] - v1[1] * v2[0],
        )

    @classmethod
    def _triangle_area(
        cls,
        p0: tuple[float, float, float],
        p1: tuple[float, float, float],
        p2: tuple[float, float, float],
    ) -> float:
        cross = cls._cross(cls._sub(p1, p0), cls._sub(p2, p0))
        return 0.5 * math.sqrt(sum(value * value for value in cross))
