"""Surface property dialog."""

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

from core.model_data import ProjectModel, surface_expected_node_count
from core.results import SURFACE_RESULTANT_COMPONENTS
from gui.dialogs.element_properties_dlg import _fmt, _object_items


class SurfacePropertiesDialog(QDialog):
    """Surface properties dialog."""

    def __init__(
        self,
        parent,
        project: ProjectModel,
        surface_tag: int,
        *,
        case_name: str | None = None,
        case_results: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.surface_tag = int(surface_tag)
        self.surface = project.surface_elements[self.surface_tag]
        self.case_name = case_name
        self.case_results = case_results or {}

        suffix = f" - {case_name}" if case_name else ""
        self.setWindowTitle(f"Propriétés de la plaque S{self.surface_tag}{suffix}")
        self.resize(820, 640)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_geometry_tab(), "Géométrie")
        self.tabs.addTab(self._build_properties_tab(), "Propriétés")
        self.tabs.addTab(self._build_loads_tab(), "Charges")
        self.tabs.addTab(self._build_ntm_tab(), "NTM")
        self.tabs.addTab(self._build_displacements_tab(), "Déplacements")
        self.tabs.addTab(self._build_check_tab(), "Vérification")

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_geometry_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        section = self.project.sections.get(self.surface.section_tag)
        general = QGroupBox("Identification", tab)
        form = QFormLayout(general)
        form.addRow("Plaque :", QLabel(f"S{self.surface.tag}", general))
        form.addRow("Type :", QLabel(self.surface.surface_type, general))
        form.addRow(
            "Noeuds :",
            QLabel(", ".join(f"N{tag}" for tag in self.surface.node_tags), general),
        )
        form.addRow(
            "Section :",
            QLabel(
                f"{section.name} (T{section.tag})" if section is not None else "-",
                general,
            ),
        )
        if self.case_name:
            form.addRow("Cas courant :", QLabel(self.case_name, general))
        layout.addWidget(general)

        geometry = QGroupBox("Géométrie", tab)
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
        geom_form.addRow(
            "Ecart au plan :",
            QLabel(f"{_fmt(self._max_plane_offset())} m", geometry),
        )
        layout.addWidget(geometry)

        table = self._make_table(["Noeud", "X", "Y", "Z"])
        rows = []
        for tag in self.surface.node_tags:
            node = self.project.nodes.get(tag)
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

    def _build_properties_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        section = self.project.sections.get(self.surface.section_tag)
        material = (
            self.project.materials.get(section.material_tag)
            if section is not None
            else None
        )

        section_group = QGroupBox("Section plaque", tab)
        section_form = QFormLayout(section_group)
        if section is None:
            section_form.addRow("Section :", QLabel("Section introuvable", section_group))
        else:
            formulation = section.surface_formulation
            section_form.addRow("Nom :", QLabel(section.name, section_group))
            section_form.addRow("Type :", QLabel(section.section_type, section_group))
            section_form.addRow("Formulation :", QLabel(formulation, section_group))
            section_form.addRow(
                "Noeuds attendus :",
                QLabel(str(surface_expected_node_count(formulation)), section_group),
            )
            section_form.addRow(
                "Epaisseur :",
                QLabel(f"{_fmt(section.thickness)} m", section_group),
            )
        section_form.addRow("Type solveur :", QLabel(self.surface.surface_type, section_group))
        layout.addWidget(section_group)

        material_group = QGroupBox("Matériau", tab)
        material_form = QFormLayout(material_group)
        if material is None:
            material_form.addRow("Matériau :", QLabel("Matériau introuvable", material_group))
        else:
            material_form.addRow("Nom :", QLabel(material.name, material_group))
            material_form.addRow("Type :", QLabel(material.material_type, material_group))
            material_form.addRow("Nuance :", QLabel(material.grade, material_group))
        layout.addWidget(material_group)

        table = self._make_table(["Propriété", "Valeur"])
        rows: list[tuple[str, object]] = []
        if section is not None:
            rows.extend((f"section.{key}", value) for key, value in _object_items(section.properties))
        if material is not None:
            rows.extend((f"matériau.{key}", value) for key, value in _object_items(material.properties))
        self._fill_table(table, [(name, _fmt(value)) for name, value in rows])
        layout.addWidget(table, 1)
        return tab

    def _build_loads_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        table = self._make_table(["Cas", "Tag", "qX global", "qY global", "qZ global"])
        rows = []
        for load in self.project.surface_loads:
            if int(load.surface_tag) != self.surface_tag:
                continue
            load_case = self.project.loads.get(load.load_tag)
            rows.append([
                load_case.name if load_case is not None else "Cas introuvable",
                f"T{load.load_tag}",
                f"{_fmt(load.qx)} kN/m2",
                f"{_fmt(load.qy)} kN/m2",
                f"{_fmt(load.qz)} kN/m2",
            ])
        self._fill_table(table, rows)
        layout.addWidget(table)
        return tab

    def _build_ntm_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        result = self._surface_result()

        average_table = self._make_table(["Composante", "Valeur moyenne"])
        average_rows = []
        if result is not None:
            for key, label, unit in self._surface_components():
                average_rows.append([
                    label,
                    f"{_fmt(getattr(result, key, None))} {unit}",
                ])
        self._fill_table(average_table, average_rows)
        layout.addWidget(average_table)

        gauss_table = self._make_table(["Point", "Nxx", "Nyy", "Nxy", "Mxx", "Myy", "Mxy", "Qx", "Qy"])
        gauss_rows = []
        if result is not None:
            for idx, values in enumerate(result.gauss_resultants, start=1):
                gauss_rows.append([
                    f"GP{idx}",
                    *[
                        _fmt(values[col_idx]) if col_idx < len(values) else "-"
                        for col_idx in range(len(SURFACE_RESULTANT_COMPONENTS))
                    ],
                ])
        self._fill_table(gauss_table, gauss_rows)
        layout.addWidget(gauss_table, 1)
        return tab

    def _build_displacements_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        table = self._make_table(["Noeud", "Ux", "Uy", "Uz", "Rx", "Ry", "Rz"])
        displacements = self.case_results.get("displacements", {})
        rows = []
        for node_tag in self.surface.node_tags:
            disp = displacements.get(node_tag) or displacements.get(str(node_tag))
            if disp is None:
                continue
            rows.append([
                f"N{node_tag}",
                f"{_fmt(getattr(disp, 'ux', None))} m",
                f"{_fmt(getattr(disp, 'uy', None))} m",
                f"{_fmt(getattr(disp, 'uz', None))} m",
                f"{_fmt(getattr(disp, 'rx', None))} rad",
                f"{_fmt(getattr(disp, 'ry', None))} rad",
                f"{_fmt(getattr(disp, 'rz', None))} rad",
            ])
        self._fill_table(table, rows)
        layout.addWidget(table)
        return tab

    def _build_check_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        label = QLabel(
            "La vérification réglementaire mono-plaque sera branchée ici "
            "lorsque le module de dimensionnement des plaques sera disponible.",
            tab,
        )
        label.setWordWrap(True)
        label.setStyleSheet("color: #5f6b73;")
        layout.addWidget(label)
        layout.addStretch(1)
        return tab

    def _surface_result(self):
        surface_results = self.case_results.get("surface_results", {})
        return surface_results.get(self.surface_tag) or surface_results.get(str(self.surface_tag))

    def _points(self) -> list[tuple[float, float, float]]:
        points = []
        for tag in self.surface.node_tags:
            node = self.project.nodes.get(tag)
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

    def _max_plane_offset(self) -> float:
        normal = self._normal()
        points = self._points()
        if normal is None or not points:
            return 0.0
        origin = points[0]
        return max(
            abs(self._dot(self._sub(point, origin), normal))
            for point in points
        )

    @staticmethod
    def _surface_components() -> list[tuple[str, str, str]]:
        return [
            ("nxx", "Nxx", "kN/m"),
            ("nyy", "Nyy", "kN/m"),
            ("nxy", "Nxy", "kN/m"),
            ("mxx", "Mxx", "kN.m/m"),
            ("myy", "Myy", "kN.m/m"),
            ("mxy", "Mxy", "kN.m/m"),
            ("qx", "Qx", "kN/m"),
            ("qy", "Qy", "kN/m"),
        ]

    @staticmethod
    def _sub(
        p1: tuple[float, float, float],
        p0: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        return p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]

    @staticmethod
    def _dot(
        v1: tuple[float, float, float],
        v2: tuple[float, float, float],
    ) -> float:
        return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]

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
            item = QTableWidgetItem("Aucune donnée")
            table.setItem(0, 0, item)
            table.setSpan(0, 0, 1, table.columnCount())
