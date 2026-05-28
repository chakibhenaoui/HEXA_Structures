"""Member property dialog."""

from __future__ import annotations

import math
from dataclasses import fields, is_dataclass

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

from core.model_data import ProjectModel
from gui.i18n.display_labels import load_name_label


def _fmt(value, precision: int = 6) -> str:
    """Handle fmt."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, (int, str)):
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 1e5 or (0 < abs(number) < 1e-4):
        return f"{number:.{precision}e}"
    return f"{number:.{precision}g}"


def _object_items(obj) -> list[tuple[str, object]]:
    """Handle object items."""
    if obj is None:
        return []
    if isinstance(obj, dict):
        return sorted(obj.items(), key=lambda item: str(item[0]))
    if is_dataclass(obj):
        return [(field.name, getattr(obj, field.name, None)) for field in fields(obj)]
    return []


class ElementPropertiesDialog(QDialog):
    """Element properties dialog."""

    def __init__(
        self,
        parent,
        project: ProjectModel,
        element_tag: int,
        *,
        case_name: str | None = None,
        case_results: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.element_tag = int(element_tag)
        self.element = project.elements[self.element_tag]
        self.case_name = case_name
        self.case_results = case_results or {}

        suffix = f" - {case_name}" if case_name else ""
        self.setWindowTitle(
            self.tr("Propriétés de la barre E{tag}{suffix}").format(
                tag=self.element_tag,
                suffix=suffix,
            )
        )
        self.resize(780, 620)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_geometry_tab(), self.tr("Géométrie"))
        self.tabs.addTab(self._build_section_tab(), self.tr("Propriétés"))
        self.tabs.addTab(self._build_loads_tab(), self.tr("Charges"))
        if self._element_result() is not None:
            self.tabs.addTab(self._build_ntm_tab(), self.tr("NTM"))
        if self._has_displacement_results():
            self.tabs.addTab(self._build_displacements_tab(), self.tr("Déplacements"))
        self.tabs.addTab(self._build_check_tab(), self.tr("Vérification"))

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_geometry_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        ni = self.project.nodes.get(self.element.node_i)
        nj = self.project.nodes.get(self.element.node_j)
        dx = dy = dz = length = 0.0
        ux = uy = uz = 0.0
        if ni is not None and nj is not None:
            dx = float(nj.x - ni.x)
            dy = float(nj.y - ni.y)
            dz = float(nj.z - ni.z)
            length = math.sqrt(dx * dx + dy * dy + dz * dz)
            if length > 0:
                ux = dx / length
                uy = dy / length
                uz = dz / length

        general = QGroupBox(self.tr("Identification"), tab)
        form = QFormLayout(general)
        form.addRow(self.tr("Barre :"), QLabel(f"E{self.element.tag}", general))
        form.addRow(self.tr("Type :"), QLabel(self.element.element_type, general))
        form.addRow(self.tr("Nœud i :"), QLabel(f"N{self.element.node_i}", general))
        form.addRow(self.tr("Nœud j :"), QLabel(f"N{self.element.node_j}", general))
        form.addRow(self.tr("Section :"), QLabel(f"T{self.element.section_tag}", general))
        if self.case_name:
            form.addRow(self.tr("Cas courant :"), QLabel(self.case_name, general))
        layout.addWidget(general)

        geometry = QGroupBox(self.tr("Géométrie"), tab)
        geom_form = QFormLayout(geometry)
        if ni is not None:
            geom_form.addRow(self.tr("Coordonnées i :"), QLabel(self._coord_text(ni), geometry))
        if nj is not None:
            geom_form.addRow(self.tr("Coordonnées j :"), QLabel(self._coord_text(nj), geometry))
        geom_form.addRow(self.tr("Longueur :"), QLabel(f"{_fmt(length)} m", geometry))
        geom_form.addRow(self.tr("Delta X / Y / Z :"), QLabel(f"{_fmt(dx)} / {_fmt(dy)} / {_fmt(dz)} m", geometry))
        geom_form.addRow(self.tr("Axe local x :"), QLabel(f"{_fmt(ux)} / {_fmt(uy)} / {_fmt(uz)}", geometry))
        layout.addWidget(geometry)
        layout.addStretch(1)
        return tab

    def _build_section_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        section = self.project.sections.get(self.element.section_tag)
        material = (
            self.project.materials.get(section.material_tag)
            if section is not None
            else None
        )

        section_group = QGroupBox(self.tr("Section"), tab)
        section_form = QFormLayout(section_group)
        if section is None:
            section_form.addRow(self.tr("Section :"), QLabel(self.tr("Section introuvable"), section_group))
        else:
            section_form.addRow(self.tr("Nom :"), QLabel(section.name, section_group))
            section_form.addRow(self.tr("Type :"), QLabel(section.section_type, section_group))
            section_form.addRow(self.tr("Aire A :"), QLabel(f"{_fmt(section.area)} m2", section_group))
            section_form.addRow(self.tr("Inertie Iy :"), QLabel(f"{_fmt(section.inertia_y)} m4", section_group))
            section_form.addRow(self.tr("Inertie Iz :"), QLabel(f"{_fmt(section.inertia_z)} m4", section_group))
        layout.addWidget(section_group)

        material_group = QGroupBox(self.tr("Matériau"), tab)
        material_form = QFormLayout(material_group)
        if material is None:
            material_form.addRow(self.tr("Matériau :"), QLabel(self.tr("Matériau introuvable"), material_group))
        else:
            material_form.addRow(self.tr("Nom :"), QLabel(material.name, material_group))
            material_form.addRow(self.tr("Type :"), QLabel(material.material_type, material_group))
            material_form.addRow(self.tr("Nuance :"), QLabel(material.grade, material_group))
        layout.addWidget(material_group)

        table = self._make_table([self.tr("Propriété"), self.tr("Valeur")])
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
        table = self._make_table([self.tr("Cas"), "Tag", self.tr("Repère"), "q1/wx", "q2/wy", "q3/wz"])
        rows = []
        for load in self.project.element_loads:
            if int(load.element_tag) != self.element_tag:
                continue
            load_case = self.project.loads.get(load.load_tag)
            label = (
                load_name_label(load_case)
                if load_case is not None
                else self.tr("Cas introuvable")
            )
            rows.append([
                label,
                f"T{load.load_tag}",
                self.tr("Global")
                if str(getattr(load, "coordinate_system", "local")).lower() == "global"
                else self.tr("Local"),
                f"{_fmt(load.wx)} kN/m",
                f"{_fmt(load.wy)} kN/m",
                f"{_fmt(load.wz)} kN/m",
            ])
        self._fill_table(table, rows)
        layout.addWidget(table)
        return tab

    def _build_ntm_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        table = self._make_table([self.tr("Extrémité"), "N", "Vy", "Vz", "T", "My", "Mz"])
        result = self._element_result()
        rows = []
        if result is not None:
            rows = [
                [
                    "i",
                    f"{_fmt(getattr(result, 'n_i', None))} kN",
                    f"{_fmt(getattr(result, 'vy_i', None))} kN",
                    f"{_fmt(getattr(result, 'vz_i', None))} kN",
                    f"{_fmt(getattr(result, 't_i', None))} kN.m",
                    f"{_fmt(getattr(result, 'my_i', None))} kN.m",
                    f"{_fmt(getattr(result, 'mz_i', None))} kN.m",
                ],
                [
                    "j",
                    f"{_fmt(getattr(result, 'n_j', None))} kN",
                    f"{_fmt(getattr(result, 'vy_j', None))} kN",
                    f"{_fmt(getattr(result, 'vz_j', None))} kN",
                    f"{_fmt(getattr(result, 't_j', None))} kN.m",
                    f"{_fmt(getattr(result, 'my_j', None))} kN.m",
                    f"{_fmt(getattr(result, 'mz_j', None))} kN.m",
                ],
            ]
        self._fill_table(table, rows)
        layout.addWidget(table)
        return tab

    def _build_displacements_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        table = self._make_table([self.tr("Nœud"), "Ux", "Uy", "Uz", "Rx", "Ry", "Rz"])
        displacements = self.case_results.get("displacements", {})
        rows = []
        for node_tag in (self.element.node_i, self.element.node_j):
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
            self.tr(
                "La vérification réglementaire mono-barre sera branchée ici "
                "lorsque le module de dimensionnement sera disponible."
            ),
            tab,
        )
        label.setWordWrap(True)
        label.setStyleSheet("color: #5f6b73;")
        layout.addWidget(label)
        layout.addStretch(1)
        return tab

    def _element_result(self):
        forces = self.case_results.get("element_forces", {})
        return forces.get(self.element_tag) or forces.get(str(self.element_tag))

    def _has_displacement_results(self) -> bool:
        displacements = self.case_results.get("displacements", {})
        return any(
            displacements.get(tag) or displacements.get(str(tag))
            for tag in (self.element.node_i, self.element.node_j)
        )

    @staticmethod
    def _coord_text(node) -> str:
        return f"({_fmt(node.x)}, {_fmt(node.y)}, {_fmt(node.z)}) m"

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    def _fill_table(self, table: QTableWidget, rows: list[list[object] | tuple[object, ...]]) -> None:
        table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        if not rows:
            table.setRowCount(1)
            item = QTableWidgetItem(self.tr("Aucune donnée"))
            table.setItem(0, 0, item)
            table.setSpan(0, 0, 1, table.columnCount())
