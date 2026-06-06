"""Dialog for user sections calculated with sectionproperties."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.sectionproperties_adapter import (
    SectionPropertiesCalculationError,
    SectionPropertiesUnavailable,
    calculate_sectionproperties_section,
    default_dimensions,
    display_properties_for_shape,
    get_sectionproperty_shape,
    list_sectionproperty_shapes,
    sectionproperties_backend_info,
    validate_sectionproperty_dimensions,
)
from gui.dialogs.section_dlg import _section_inner_polygon, _section_outer_polygon


class SectionWorkbenchCanvas(QWidget):
    """Large 2D canvas prepared for the future user-section workbench."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._outer: list[tuple[float, float]] = []
        self._inner: list[tuple[float, float]] = []
        self._mesh_visible = True
        self._tool_label = ""
        self.setMinimumSize(560, 460)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_section(self, section_type: str, properties: dict) -> None:
        """Set the displayed section outline."""
        self._outer = _section_outer_polygon(section_type, properties)
        self._inner = _section_inner_polygon(section_type, properties)
        self.update()

    def set_mesh_visible(self, visible: bool) -> None:
        """Toggle the illustrative mesh overlay."""
        self._mesh_visible = bool(visible)
        self.update()

    def set_tool_label(self, label: str) -> None:
        """Show the selected workbench tool in the canvas corner."""
        self._tool_label = label
        self.update()

    @staticmethod
    def _path(points: list[tuple[float, float]], scale: float, cx: float, cy: float) -> QPainterPath:
        path = QPainterPath()
        if not points:
            return path
        first = points[0]
        path.moveTo(QPointF(cx + first[0] * scale, cy - first[1] * scale))
        for x, y in points[1:]:
            path.lineTo(QPointF(cx + x * scale, cy - y * scale))
        path.closeSubpath()
        return path

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f4f6f8"))
        work_rect = self.rect().adjusted(18, 18, -18, -18)
        painter.setPen(QPen(QColor("#d5dbe3"), 1))
        painter.drawRect(work_rect)
        self._draw_grid(painter, work_rect)

        if not self._outer:
            painter.setPen(QColor("#6f7782"))
            painter.drawText(work_rect, Qt.AlignCenter, self.tr("Aucune section a afficher"))
            return

        points = self._outer + self._inner
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        width = max(max(xs) - min(xs), 1e-9)
        height = max(max(ys) - min(ys), 1e-9)
        scale = min(work_rect.width() / width, work_rect.height() / height) * 0.72
        cx = work_rect.center().x() - ((max(xs) + min(xs)) * 0.5 * scale)
        cy = work_rect.center().y() + ((max(ys) + min(ys)) * 0.5 * scale)

        section_path = self._path(self._outer, scale, cx, cy)
        section_path.setFillRule(Qt.OddEvenFill)
        if self._inner:
            section_path.addPath(self._path(self._inner, scale, cx, cy))

        painter.setPen(QPen(QColor("#1f2933"), 2))
        painter.setBrush(QColor("#d9dee7"))
        painter.drawPath(section_path)

        if self._mesh_visible:
            painter.save()
            painter.setClipPath(section_path)
            painter.setPen(QPen(QColor("#87a7c7"), 1, Qt.DashLine))
            spacing = max(18, min(work_rect.width(), work_rect.height()) // 14)
            for x in range(work_rect.left() - work_rect.height(), work_rect.right(), spacing):
                painter.drawLine(x, work_rect.bottom(), x + work_rect.height(), work_rect.top())
            for x in range(work_rect.left(), work_rect.right() + work_rect.height(), spacing):
                painter.drawLine(x, work_rect.top(), x - work_rect.height(), work_rect.bottom())
            painter.restore()

        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#2c3e50"), 1))
        for y, z in self._outer:
            painter.drawEllipse(QPointF(cx + y * scale, cy - z * scale), 3.5, 3.5)

        self._draw_axes(painter, work_rect)
        if self._tool_label:
            painter.setPen(QColor("#374151"))
            painter.drawText(
                QRectF(work_rect.left() + 12, work_rect.top() + 10, 280, 24),
                Qt.AlignLeft | Qt.AlignVCenter,
                self._tool_label,
            )

    def _draw_grid(self, painter: QPainter, rect) -> None:
        painter.setPen(QPen(QColor("#e1e6ec"), 1))
        step = 32
        x = rect.left() + step
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += step
        y = rect.top() + step
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += step

    def _draw_axes(self, painter: QPainter, rect) -> None:
        origin = QPointF(rect.left() + 52, rect.bottom() - 44)
        painter.setPen(QPen(QColor("#2f855a"), 2))
        painter.drawLine(origin, QPointF(origin.x() + 54, origin.y()))
        painter.drawText(QPointF(origin.x() + 60, origin.y() + 5), "y")
        painter.setPen(QPen(QColor("#2b6cb0"), 2))
        painter.drawLine(origin, QPointF(origin.x(), origin.y() - 54))
        painter.drawText(QPointF(origin.x() - 7, origin.y() - 62), "z")


class SectionPropertiesDialog(QDialog):
    """Create or edit a line section calculated by sectionproperties."""

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
        self._result: dict | None = None
        self._dimension_spins: dict[str, QDoubleSpinBox] = {}
        self._backend_info = sectionproperties_backend_info()
        self._sectionproperties_available = self._backend_info.available

        self.setWindowTitle(self.tr("Atelier de section"))
        self.setMinimumSize(1120, 720)
        self.resize(1240, 780)

        self._edit_name = QLineEdit(name, self)
        self._combo_shape = QComboBox(self)
        self._combo_material = QComboBox(self)
        self._mesh_area = QDoubleSpinBox(self)
        self._mesh_area.setMinimum(1.0e-8)
        self._mesh_area.setMaximum(1.0)
        self._mesh_area.setDecimals(8)
        self._mesh_area.setSingleStep(1.0e-5)
        self._mesh_area.setSuffix(" m2")
        self._mesh_area.setValue(float(self._init_properties.get("mesh_area", 1.0e-4)))

        self._params_group = QGroupBox(self.tr("Dimensions"), self)
        self._params_layout = QFormLayout(self._params_group)
        self._canvas = SectionWorkbenchCanvas(self)
        self._preview = self._canvas
        self._tool_buttons: dict[str, QToolButton] = {}
        self._tabs = QTabWidget(self)
        self._backend_label = QLabel("", self)
        self._backend_label.setWordWrap(True)
        self._capabilities_table = QTableWidget(0, 4, self)
        self._capabilities_table.setHorizontalHeaderLabels(
            [
                self.tr("Option"),
                self.tr("API"),
                self.tr("Etat HEXA"),
                self.tr("Module"),
            ]
        )
        self._capabilities_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._capabilities_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._library_label = QLabel("", self)
        self._library_label.setWordWrap(True)
        self._points_table = QTableWidget(0, 2, self)
        self._points_table.setHorizontalHeaderLabels([self.tr("y (m)"), self.tr("z (m)")])
        header = self._points_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self._chk_show_mesh = QCheckBox(self.tr("Afficher le maillage"), self)
        self._chk_show_mesh.setChecked(True)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._result_label = QLabel("", self)
        self._result_label.setWordWrap(True)
        self._mesh_info = QLabel("", self)
        self._mesh_info.setWordWrap(True)
        self._properties_info = QLabel("", self)
        self._properties_info.setWordWrap(True)
        self._btn_calculate = QPushButton(self.tr("Calculer"), self)
        self._btn_add_point = QPushButton(self.tr("Ajouter point"), self)
        self._btn_delete_point = QPushButton(self.tr("Supprimer point"), self)
        self._btn_add_point.setEnabled(False)
        self._btn_delete_point.setEnabled(False)
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self,
        )
        ok_button = self._button_box.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setText(self.tr("Ajouter a la bibliotheque"))

        self._setup_ui()
        self._populate_shapes()
        self._populate_materials()
        self._connect_signals()
        self._refresh_backend_tab()
        self._apply_initial_values()
        self._on_shape_changed()
        if material_tag is not None:
            self._select_material_tag(material_tag)

        if not self._sectionproperties_available:
            self._status.setText(
                self.tr(
                    "La bibliotheque sectionproperties n'est pas installee dans cet environnement."
                )
            )
            self._btn_calculate.setEnabled(False)
            ok_button = self._button_box.button(QDialogButtonBox.Ok)
            if ok_button is not None:
                ok_button.setEnabled(False)

    def result(self) -> dict:
        """Return the section payload expected by ProjectModel.add_section."""
        if self._result is None:
            self._calculate(show_errors=False)
        if self._result is None:
            return {}
        data = dict(self._result)
        data["name"] = self._edit_name.text().strip()
        data["material_tag"] = self._combo_material.currentData() or 0
        return data

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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._build_tool_bar())
        layout.addWidget(self._canvas, 1)
        layout.addWidget(self._status)
        return panel

    def _build_tool_bar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        tool_specs = (
            ("select", self.tr("Selection")),
            ("polygon", self.tr("Polygone")),
            ("rectangle", self.tr("Rectangle")),
            ("circle", self.tr("Cercle")),
            ("hole", self.tr("Trou")),
            ("mesh", self.tr("Maillage")),
            ("dxf", self.tr("DXF")),
        )
        for key, label in tool_specs:
            button = QToolButton(self)
            button.setText(label)
            button.setCheckable(key != "dxf")
            if key == "dxf":
                button.setEnabled(False)
                button.setToolTip(self.tr("Import DXF prevu dans une prochaine etape."))
            else:
                button.clicked.connect(lambda _checked=False, name=label: self._select_tool(name))
            toolbar.addWidget(button)
            self._tool_buttons[key] = button
        self._tool_buttons["select"].setChecked(True)
        toolbar.addStretch(1)
        return toolbar

    def _build_side_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tabs.addTab(self._build_backend_tab(), self.tr("Bibliotheque"))
        self._tabs.addTab(self._build_geometry_tab(), self.tr("Geometrie"))
        self._tabs.addTab(self._build_coordinates_tab(), self.tr("Coordonnees"))
        self._tabs.addTab(self._build_mesh_tab(), self.tr("Maillage"))
        self._tabs.addTab(self._build_results_tab(), self.tr("Resultats"))
        layout.addWidget(self._tabs, 1)
        return panel

    def _build_backend_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.addWidget(self._backend_label)
        layout.addWidget(self._capabilities_table, 1)
        layout.addWidget(self._library_label)
        return tab

    def _build_geometry_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        controls = QWidget(tab)
        form = QFormLayout(controls)
        form.addRow(self.tr("Nom :"), self._edit_name)
        form.addRow(self.tr("Forme :"), self._combo_shape)
        form.addRow(self.tr("Materiau :"), self._combo_material)
        layout.addWidget(controls)
        layout.addWidget(self._params_group)
        layout.addWidget(self._properties_info)
        layout.addStretch(1)
        return tab

    def _build_coordinates_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.addWidget(self._points_table, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self._btn_add_point)
        buttons.addWidget(self._btn_delete_point)
        layout.addLayout(buttons)
        layout.addWidget(
            QLabel(
                self.tr(
                    "La saisie directe des points sera branchee dans l'etape dessin par coordonnees."
                ),
                tab,
            )
        )
        return tab

    def _build_mesh_tab(self) -> QWidget:
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.addRow(self.tr("Surface max. de maille :"), self._mesh_area)
        form.addRow("", self._chk_show_mesh)
        form.addRow(self.tr("Etat :"), self._mesh_info)
        return tab

    def _build_results_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.addWidget(self._btn_calculate)
        layout.addWidget(self._result_label)
        layout.addStretch(1)
        return tab

    def _populate_shapes(self) -> None:
        for shape in list_sectionproperty_shapes():
            self._combo_shape.addItem(self._shape_label(shape.key), shape.key)

    def _populate_materials(self) -> None:
        self._combo_material.clear()
        for tag, mat in self._materials.items():
            self._combo_material.addItem(f"{mat.name} ({mat.grade})", tag)
        if not self._materials:
            self._combo_material.addItem(self.tr("(aucun materiau)"), 0)

    def _connect_signals(self) -> None:
        self._combo_shape.currentIndexChanged.connect(self._on_shape_changed)
        self._mesh_area.valueChanged.connect(self._invalidate_result)
        self._mesh_area.valueChanged.connect(lambda _value: self._update_mesh_info())
        self._chk_show_mesh.toggled.connect(self._canvas.set_mesh_visible)
        self._btn_calculate.clicked.connect(lambda: self._calculate(show_errors=True))
        self._button_box.accepted.connect(self._accept)
        self._button_box.rejected.connect(self.reject)

    def _refresh_backend_tab(self) -> None:
        info = self._backend_info
        if info.available:
            self._backend_label.setText(
                self.tr("sectionproperties importe avec succes. Version : {version}").format(
                    version=info.version or self.tr("inconnue")
                )
            )
        else:
            self._backend_label.setText(
                self.tr("sectionproperties indisponible : {reason}").format(
                    reason=info.error or self.tr("module introuvable")
                )
            )

        self._capabilities_table.setRowCount(len(info.capabilities))
        for row, capability in enumerate(info.capabilities):
            state = self.tr("branche") if capability.implemented else self.tr("prevu")
            values = (
                self._capability_label(capability.key),
                capability.api_name,
                state,
                capability.module_path,
            )
            for column, value in enumerate(values):
                self._capabilities_table.setItem(row, column, QTableWidgetItem(value))

        if info.library_functions:
            self._library_label.setText(
                self.tr("{count} fonctions de bibliotheque detectees.").format(
                    count=len(info.library_functions)
                )
            )
        else:
            self._library_label.setText(
                self.tr("Aucune fonction de bibliotheque detectee pour l'instant.")
            )

    def _capability_label(self, key: str) -> str:
        labels = {
            "geometry_library": self.tr("Bibliotheque de sections"),
            "mesh": self.tr("Generation du maillage"),
            "geometric": self.tr("Analyse geometrique"),
            "warping": self.tr("Analyse torsion / gauchissement"),
            "frame": self.tr("Proprietes frame"),
            "plastic": self.tr("Analyse plastique"),
            "stress": self.tr("Analyse de contraintes"),
            "post": self.tr("Post-traitement"),
        }
        return labels.get(key, key)

    def _apply_initial_values(self) -> None:
        shape_key = str(self._init_properties.get("shape", "") or "")
        if shape_key:
            was_blocked = self._combo_shape.blockSignals(True)
            try:
                idx = self._combo_shape.findData(shape_key)
                if idx >= 0:
                    self._combo_shape.setCurrentIndex(idx)
            finally:
                self._combo_shape.blockSignals(was_blocked)

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
        spin.valueChanged.connect(self._on_dimension_changed)
        return spin

    def _clear_parameters(self) -> None:
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._dimension_spins.clear()

    def _on_shape_changed(self) -> None:
        shape_key = str(self._combo_shape.currentData() or "rectangular")
        shape = get_sectionproperty_shape(shape_key)
        initial_dimensions = self._initial_dimensions(shape_key)
        self._clear_parameters()
        for field in shape.fields:
            spin = self._make_dimension_spin(initial_dimensions[field])
            self._params_layout.addRow(self._field_label(shape_key, field), spin)
            self._dimension_spins[field] = spin
        self._select_material_type(shape.default_material_type)
        if not self._edit_name.text().strip():
            self._edit_name.setText(self._shape_label(shape_key))
        self._on_dimension_changed()

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

    def _select_material_type(self, material_type: str) -> None:
        for index in range(self._combo_material.count()):
            tag = self._combo_material.itemData(index)
            mat = self._materials.get(tag)
            if mat is not None and getattr(mat, "material_type", "") == material_type:
                self._combo_material.setCurrentIndex(index)
                return

    def _select_material_tag(self, material_tag: int) -> None:
        idx = self._combo_material.findData(material_tag)
        if idx >= 0:
            self._combo_material.setCurrentIndex(idx)

    def _on_dimension_changed(self) -> None:
        self._invalidate_result()
        self._update_preview()
        self._update_status()

    def _invalidate_result(self) -> None:
        self._result = None
        self._result_label.setText("")

    def _update_preview(self) -> None:
        shape_key = str(self._combo_shape.currentData() or "rectangular")
        try:
            shape = get_sectionproperty_shape(shape_key)
            display_props = display_properties_for_shape(shape_key, self._current_dimensions())
            self._preview.set_section(shape.display_type, display_props)
            self._refresh_coordinate_table(shape.display_type, display_props)
            self._update_properties_info(shape.display_type, display_props)
            self._update_mesh_info()
        except SectionPropertiesCalculationError:
            self._preview.set_section("", {})
            self._points_table.setRowCount(0)

    def _update_status(self) -> None:
        if not self._sectionproperties_available:
            return
        shape_key = str(self._combo_shape.currentData() or "rectangular")
        error_code = validate_sectionproperty_dimensions(shape_key, self._current_dimensions())
        if error_code is None:
            self._status.setText(self.tr("Pret pour le calcul sectionproperties."))
        else:
            self._status.setText(self._validation_message(error_code))

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

    def _select_tool(self, label: str) -> None:
        """Select a workbench tool placeholder."""
        for button in self._tool_buttons.values():
            if button.isCheckable():
                button.setChecked(button.text() == label)
        self._canvas.set_tool_label(self.tr("Outil actif : {tool}").format(tool=label))
        self._status.setText(
            self.tr(
                "Interface prete. Les interactions de dessin seront branchees dans l'etape suivante."
            )
        )

    def _refresh_coordinate_table(self, section_type: str, properties: dict) -> None:
        """Refresh the coordinate table from the current displayed outline."""
        points = _section_outer_polygon(section_type, properties)
        self._points_table.setRowCount(len(points))
        for row, (y_value, z_value) in enumerate(points):
            self._points_table.setItem(row, 0, QTableWidgetItem(f"{y_value:.4f}"))
            self._points_table.setItem(row, 1, QTableWidgetItem(f"{z_value:.4f}"))

    def _update_properties_info(self, section_type: str, properties: dict) -> None:
        """Show a short geometry summary for the current parametric shape."""
        if section_type == "rectangular":
            self._properties_info.setText(
                self.tr("Rectangle {b:.3f} m x {h:.3f} m").format(
                    b=float(properties.get("b", 0.0)),
                    h=float(properties.get("h", 0.0)),
                )
            )
        elif section_type == "circle":
            self._properties_info.setText(
                self.tr("Cercle plein d = {d:.3f} m").format(
                    d=float(properties.get("d", 0.0)),
                )
            )
        else:
            self._properties_info.setText(
                self.tr("Contour affiche dans le repere local y/z.")
            )

    def _update_mesh_info(self) -> None:
        """Refresh mesh-tab text."""
        self._mesh_info.setText(
            self.tr("Maillage indicatif affiche. Surface cible : {area:.6f} m2").format(
                area=self._mesh_area.value(),
            )
        )

    def _calculate(self, *, show_errors: bool) -> bool:
        name = self._edit_name.text().strip()
        if not name:
            self._edit_name.setFocus()
            return False
        shape_key = str(self._combo_shape.currentData() or "rectangular")
        error_code = validate_sectionproperty_dimensions(shape_key, self._current_dimensions())
        if error_code is not None:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Geometrie de section invalide"),
                    self._validation_message(error_code),
                )
            return False

        try:
            result = calculate_sectionproperties_section(
                shape_key,
                self._current_dimensions(),
                mesh_area=self._mesh_area.value(),
            )
        except SectionPropertiesUnavailable:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("sectionproperties indisponible"),
                    self.tr(
                        "Installez sectionproperties pour calculer les sections utilisateur."
                    ),
                )
            return False
        except SectionPropertiesCalculationError as exc:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.tr("Calcul sectionproperties impossible"),
                    str(exc),
                )
            return False

        self._result = {
            "name": name,
            "section_type": "sectionproperties",
            "material_tag": self._combo_material.currentData() or 0,
            "properties": result.properties,
            "area": result.area,
            "inertia_y": result.inertia_y,
            "inertia_z": result.inertia_z,
        }
        self._result_label.setText(
            "A = {area:.2f} cm2  |  Iy = {iy:.1f} cm4  |  "
            "Iz = {iz:.1f} cm4  |  J = {j:.1f} cm4".format(
                area=result.area * 1.0e4,
                iy=result.inertia_y * 1.0e8,
                iz=result.inertia_z * 1.0e8,
                j=result.torsion_constant * 1.0e8,
            )
        )
        self._status.setText(self.tr("Section calculee avec sectionproperties."))
        return True

    def _accept(self) -> None:
        if self._calculate(show_errors=True):
            self.accept()
