"""Section creation and editing dialog."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QDialog,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from core.sections import (
    RectangularSection,
    TSection,
    get_profile,
    list_profile_families,
    list_profiles,
)
from gui.dialogs import load_dialog_ui


_LINE_SECTION_TYPE_KEYS = (
    "rectangular",
    "T",
    "I",
    "channel",
    "angle",
    "pipe",
    "tube",
    "I_profile",
)
_SECTION_TYPE_KEYS = (*_LINE_SECTION_TYPE_KEYS, "surface")

_PROFILE_FAMILIES = tuple(list_profile_families())
_DIMENSION_CLEARANCE = 0.001


def _section_geometry_error_code(section_type: str, properties: dict) -> str | None:
    """Return a validation code when geometric dimensions cannot define the shape."""
    def as_float(value) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    values = {key: as_float(value) for key, value in properties.items()}

    if section_type == "rectangular":
        if values.get("b", 0.0) <= 0.0 or values.get("h", 0.0) <= 0.0:
            return "positive_dimensions"
        return None

    if section_type == "T":
        bw = values.get("bw", 0.0)
        hw = values.get("hw", 0.0)
        bf = values.get("bf", 0.0)
        hf = values.get("hf", 0.0)
        if min(bw, hw, bf, hf) <= 0.0:
            return "positive_dimensions"
        if bw >= bf:
            return "t_web_too_wide"
        return None

    if section_type == "I":
        h = values.get("h", 0.0)
        b = values.get("b", 0.0)
        tw = values.get("tw", 0.0)
        tf = values.get("tf", 0.0)
        if min(h, b, tw, tf) <= 0.0:
            return "positive_dimensions"
        if tw >= b:
            return "i_web_too_thick"
        if 2.0 * tf >= h:
            return "i_flange_too_thick"
        return None

    if section_type == "channel":
        h = values.get("h", 0.0)
        b = values.get("b", 0.0)
        tw = values.get("tw", 0.0)
        tf = values.get("tf", 0.0)
        if min(h, b, tw, tf) <= 0.0:
            return "positive_dimensions"
        if tw >= b:
            return "channel_web_too_thick"
        if 2.0 * tf >= h:
            return "channel_flange_too_thick"
        return None

    if section_type == "angle":
        h = values.get("h", 0.0)
        b = values.get("b", 0.0)
        t = values.get("t", 0.0)
        if min(h, b, t) <= 0.0:
            return "positive_dimensions"
        if t >= min(h, b):
            return "angle_too_thick"
        return None

    if section_type == "pipe":
        d = values.get("d", 0.0)
        t = values.get("t", 0.0)
        if min(d, t) <= 0.0:
            return "positive_dimensions"
        if 2.0 * t >= d:
            return "pipe_too_thick"
        return None

    if section_type == "tube":
        h = values.get("h", 0.0)
        b = values.get("b", 0.0)
        t = values.get("t", 0.0)
        if min(h, b, t) <= 0.0:
            return "positive_dimensions"
        if 2.0 * t >= min(h, b):
            return "tube_too_thick"
        return None

    return None


def _composite_rectangles(
    rectangles: tuple[tuple[float, float, float, float, float], ...],
) -> tuple[float, float, float, float, float]:
    """Return area, centroid_y, centroid_z, Iy, Iz for signed rectangles."""
    area = sum(sign * width * height for sign, _y, _z, width, height in rectangles)
    if area <= 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    cy = sum(sign * width * height * y for sign, y, _z, width, height in rectangles) / area
    cz = sum(sign * width * height * z for sign, _y, z, width, height in rectangles) / area
    iy = 0.0
    iz = 0.0
    for sign, y, z, width, height in rectangles:
        signed_area = sign * width * height
        iy += sign * width * height**3 / 12.0 + signed_area * (z - cz) ** 2
        iz += sign * height * width**3 / 12.0 + signed_area * (y - cy) ** 2
    return area, cy, cz, iy, iz


def _section_properties(section_type: str, properties: dict) -> tuple[float, float, float]:
    """Compute area, Iy and Iz for a section definition."""
    if _section_geometry_error_code(section_type, properties):
        return 0.0, 0.0, 0.0

    if section_type == "rectangular":
        rect = RectangularSection(
            b=float(properties.get("b", 0.0)),
            h=float(properties.get("h", 0.0)),
        )
        return rect.area, rect.inertia_y, rect.inertia_z

    if section_type == "T":
        tsec = TSection(
            bw=float(properties.get("bw", 0.0)),
            hw=float(properties.get("hw", 0.0)),
            bf=float(properties.get("bf", 0.0)),
            hf=float(properties.get("hf", 0.0)),
        )
        iz = tsec.hw * tsec.bw**3 / 12.0 + tsec.hf * tsec.bf**3 / 12.0
        return tsec.area, tsec.inertia_y, iz

    if section_type == "I":
        h = float(properties.get("h", 0.0))
        b = float(properties.get("b", 0.0))
        tw = float(properties.get("tw", 0.0))
        tf = float(properties.get("tf", 0.0))
        web_h = max(h - 2.0 * tf, 0.0)
        area = 2.0 * b * tf + web_h * tw
        iy = (b * h**3 - (b - tw) * web_h**3) / 12.0 if h > 0.0 else 0.0
        iz = 2.0 * (tf * b**3 / 12.0) + web_h * tw**3 / 12.0
        return area, iy, iz

    if section_type == "channel":
        h = float(properties.get("h", 0.0))
        b = float(properties.get("b", 0.0))
        tw = float(properties.get("tw", 0.0))
        tf = float(properties.get("tf", 0.0))
        web_h = max(h - 2.0 * tf, 0.0)
        area, _cy, _cz, iy, iz = _composite_rectangles(
            (
                (1.0, tw / 2.0, h / 2.0, tw, web_h),
                (1.0, b / 2.0, tf / 2.0, b, tf),
                (1.0, b / 2.0, h - tf / 2.0, b, tf),
            )
        )
        return area, iy, iz

    if section_type == "angle":
        h = float(properties.get("h", 0.0))
        b = float(properties.get("b", 0.0))
        t = float(properties.get("t", 0.0))
        area, _cy, _cz, iy, iz = _composite_rectangles(
            (
                (1.0, t / 2.0, h / 2.0, t, h),
                (1.0, b / 2.0, t / 2.0, b, t),
                (-1.0, t / 2.0, t / 2.0, t, t),
            )
        )
        return area, iy, iz

    if section_type == "pipe":
        d = float(properties.get("d", 0.0))
        t = float(properties.get("t", 0.0))
        inner = max(d - 2.0 * t, 0.0)
        area = math.pi * (d**2 - inner**2) / 4.0
        inertia = math.pi * (d**4 - inner**4) / 64.0
        return area, inertia, inertia

    if section_type == "tube":
        h = float(properties.get("h", 0.0))
        b = float(properties.get("b", 0.0))
        t = float(properties.get("t", 0.0))
        inner_h = max(h - 2.0 * t, 0.0)
        inner_b = max(b - 2.0 * t, 0.0)
        area = b * h - inner_b * inner_h
        iy = (b * h**3 - inner_b * inner_h**3) / 12.0
        iz = (h * b**3 - inner_h * inner_b**3) / 12.0
        return area, iy, iz

    return 0.0, 0.0, 0.0


def _catalog_profile_properties(profile_name: str) -> tuple[float, float, float]:
    try:
        profile = get_profile(profile_name)
    except KeyError:
        return 0.0, 0.0, 0.0
    return profile.area, profile.inertia_y, profile.inertia_z


def _section_outer_polygon(section_type: str, properties: dict) -> list[tuple[float, float]]:
    """Return a drawable section outline in local y/z coordinates."""
    if _section_geometry_error_code(section_type, properties):
        return []

    if section_type == "rectangular":
        b = float(properties.get("b", 0.0))
        h = float(properties.get("h", 0.0))
        return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]

    if section_type == "T":
        bw = float(properties.get("bw", 0.0))
        hw = float(properties.get("hw", 0.0))
        bf = float(properties.get("bf", 0.0))
        hf = float(properties.get("hf", 0.0))
        tsec = TSection(bw=bw, hw=hw, bf=bf, hf=hf)
        z0 = -tsec.centroid_y
        z1 = hw - tsec.centroid_y
        z2 = tsec.h - tsec.centroid_y
        return [
            (-bw / 2, z0),
            (bw / 2, z0),
            (bw / 2, z1),
            (bf / 2, z1),
            (bf / 2, z2),
            (-bf / 2, z2),
            (-bf / 2, z1),
            (-bw / 2, z1),
        ]

    if section_type == "I":
        h = float(properties.get("h", 0.0))
        b = float(properties.get("b", 0.0))
        tw = float(properties.get("tw", 0.0))
        tf = float(properties.get("tf", 0.0))
        return [
            (-b / 2, h / 2),
            (b / 2, h / 2),
            (b / 2, h / 2 - tf),
            (tw / 2, h / 2 - tf),
            (tw / 2, -h / 2 + tf),
            (b / 2, -h / 2 + tf),
            (b / 2, -h / 2),
            (-b / 2, -h / 2),
            (-b / 2, -h / 2 + tf),
            (-tw / 2, -h / 2 + tf),
            (-tw / 2, h / 2 - tf),
            (-b / 2, h / 2 - tf),
        ]

    if section_type == "channel":
        h = float(properties.get("h", 0.0))
        b = float(properties.get("b", 0.0))
        tw = float(properties.get("tw", 0.0))
        tf = float(properties.get("tf", 0.0))
        _area, cy, cz, _iy, _iz = _composite_rectangles(
            (
                (1.0, tw / 2.0, h / 2.0, tw, max(h - 2.0 * tf, 0.0)),
                (1.0, b / 2.0, tf / 2.0, b, tf),
                (1.0, b / 2.0, h - tf / 2.0, b, tf),
            )
        )
        return [
            (-cy, h - cz),
            (b - cy, h - cz),
            (b - cy, h - tf - cz),
            (tw - cy, h - tf - cz),
            (tw - cy, tf - cz),
            (b - cy, tf - cz),
            (b - cy, -cz),
            (-cy, -cz),
        ]

    if section_type == "angle":
        h = float(properties.get("h", 0.0))
        b = float(properties.get("b", 0.0))
        t = float(properties.get("t", 0.0))
        _area, cy, cz, _iy, _iz = _composite_rectangles(
            (
                (1.0, t / 2.0, h / 2.0, t, h),
                (1.0, b / 2.0, t / 2.0, b, t),
                (-1.0, t / 2.0, t / 2.0, t, t),
            )
        )
        return [
            (-cy, -cz),
            (b - cy, -cz),
            (b - cy, t - cz),
            (t - cy, t - cz),
            (t - cy, h - cz),
            (-cy, h - cz),
        ]

    if section_type == "pipe":
        d = float(properties.get("d", 0.0))
        radius = d / 2.0
        return [
            (
                math.cos(angle) * radius,
                math.sin(angle) * radius,
            )
            for angle in (2.0 * math.pi * idx / 64 for idx in range(64))
        ]

    if section_type == "tube":
        b = float(properties.get("b", 0.0))
        h = float(properties.get("h", 0.0))
        return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]

    if section_type == "I_profile":
        profile_name = str(properties.get("profile", "")).strip()
        try:
            profile = get_profile(profile_name)
        except KeyError:
            return []
        base = {
            "h": profile.h,
            "b": profile.b,
            "tw": profile.tw,
            "tf": profile.tf,
            "d": profile.dimension("d", profile.h),
            "t": profile.dimension("t", profile.tw),
        }
        shape = getattr(profile, "shape", "i_section")
        if shape == "i_section":
            return _section_outer_polygon("I", base)
        if shape == "channel":
            return _section_outer_polygon("channel", base)
        if shape == "angle_equal":
            return _section_outer_polygon(
                "angle",
                {"h": profile.h, "b": profile.b, "t": profile.dimension("t", profile.tw)},
            )
        if shape == "angle_unequal":
            return _section_outer_polygon(
                "angle",
                {"h": profile.h, "b": profile.b, "t": profile.dimension("t", profile.tw)},
            )
        if shape == "circular_hollow":
            return _section_outer_polygon("pipe", base)
        if shape == "rectangular_hollow":
            return _section_outer_polygon("tube", base)

    return []


def _section_inner_polygon(section_type: str, properties: dict) -> list[tuple[float, float]]:
    """Return the drawable inner void outline for hollow sections."""
    if _section_geometry_error_code(section_type, properties):
        return []

    if section_type == "pipe":
        d = float(properties.get("d", 0.0))
        t = float(properties.get("t", 0.0))
        radius = max((d - 2.0 * t) / 2.0, 0.0)
        return [
            (
                math.cos(angle) * radius,
                math.sin(angle) * radius,
            )
            for angle in (2.0 * math.pi * idx / 64 for idx in range(64))
        ]

    if section_type == "tube":
        b = float(properties.get("b", 0.0))
        h = float(properties.get("h", 0.0))
        t = float(properties.get("t", 0.0))
        inner_b = max(b - 2.0 * t, 0.0)
        inner_h = max(h - 2.0 * t, 0.0)
        return [
            (-inner_b / 2, -inner_h / 2),
            (inner_b / 2, -inner_h / 2),
            (inner_b / 2, inner_h / 2),
            (-inner_b / 2, inner_h / 2),
        ]

    if section_type == "I_profile":
        profile_name = str(properties.get("profile", "")).strip()
        try:
            profile = get_profile(profile_name)
        except KeyError:
            return []
        shape = getattr(profile, "shape", "i_section")
        if shape == "circular_hollow":
            return _section_inner_polygon(
                "pipe",
                {"d": profile.dimension("d", profile.h), "t": profile.dimension("t", profile.tw)},
            )
        if shape == "rectangular_hollow":
            return _section_inner_polygon(
                "tube",
                {
                    "h": profile.h,
                    "b": profile.b,
                    "t": profile.dimension("t", profile.tw),
                },
            )

    return []


class SectionPreviewWidget(QWidget):
    """Simple live 2D preview for section geometry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._outer: list[tuple[float, float]] = []
        self._inner: list[tuple[float, float]] = []
        self.setMinimumSize(230, 230)

    def set_section(self, section_type: str, properties: dict) -> None:
        self._outer = _section_outer_polygon(section_type, properties)
        self._inner = _section_inner_polygon(section_type, properties)
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
        rect = self.rect().adjusted(12, 12, -12, -12)
        painter.fillRect(self.rect(), QColor("#f7f7f7"))
        painter.setPen(QPen(QColor("#d2d2d2"), 1))
        painter.drawRect(rect)
        if not self._outer:
            painter.setPen(QColor("#888888"))
            painter.drawText(rect, Qt.AlignCenter, self.tr("Apercu"))
            return

        points = self._outer + self._inner
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        width = max(max(xs) - min(xs), 1e-9)
        height = max(max(ys) - min(ys), 1e-9)
        scale = min(rect.width() / width, rect.height() / height) * 0.72
        cx = rect.center().x() - ((max(xs) + min(xs)) * 0.5 * scale)
        cy = rect.center().y() + ((max(ys) + min(ys)) * 0.5 * scale)

        outer_path = self._path(self._outer, scale, cx, cy)
        painter.setPen(QPen(QColor("#222222"), 2))
        painter.setBrush(QColor("#d9dce1"))
        painter.drawPath(outer_path)
        if self._inner:
            inner_path = self._path(self._inner, scale, cx, cy)
            painter.setBrush(QColor("#f7f7f7"))
            painter.drawPath(inner_path)


class SectionDialog(QDialog):
    """Section dialog."""

    def __init__(self, parent=None, *, materials: dict | None = None,
                 name: str = "", section_type: str = "",
                 material_tag: int | None = None,
                 properties: dict | None = None,
                 allowed_types: list[str] | tuple[str, ...] | None = None):
        super().__init__(parent)

        self._materials = materials or {}
        self._init_name = name
        self._init_type = section_type
        self._init_material_tag = material_tag
        self._init_properties = properties or {}
        self._allowed_types = tuple(allowed_types or _SECTION_TYPE_KEYS)

        self.ui = load_dialog_ui(self, "section_dlg.ui")

        # Convenient references to widgets
        self._edit_name = self.ui.editName
        self._combo_type = self.ui.comboType
        self._combo_material = self.ui.comboMaterial
        self._stack = self.ui.stack
        self._spin_b = self.ui.spinB
        self._spin_h = self.ui.spinH
        self._spin_bw = self.ui.spinBw
        self._spin_hw = self.ui.spinHw
        self._spin_bf = self.ui.spinBf
        self._spin_hf = self.ui.spinHf
        self._spin_thickness = self.ui.spinThickness
        self._combo_family = self.ui.comboFamily
        self._combo_profile = self.ui.comboProfile
        self._lbl_profile_info = self.ui.lblProfileInfo
        self._lbl_summary = self.ui.lblSummary
        self._shape_spins: dict[str, dict[str, QDoubleSpinBox]] = {}
        self._page_by_type: dict[str, int] = {}
        self._updating_dimension_limits = False
        self._preview = SectionPreviewWidget(self)
        self._preview_group = QGroupBox(self.tr("Apercu"), self)
        self._setup_dialog_layout()
        self._setup_parametric_pages()

        self._populate_combos()
        self._connect_signals()

        # Init
        if self._init_type:
            idx = self._combo_type.findData(self._init_type)
            if idx >= 0:
                self._combo_type.setCurrentIndex(idx)
        self._on_type_changed()
        self._apply_initial_values()
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Refresh persistent dialog labels after a language change."""
        self.setWindowTitle(self.tr("Section"))
        self._preview_group.setTitle(self.tr("Apercu"))
        self._refresh_type_labels()
        self._update_summary()

    @staticmethod
    def line_section_types() -> tuple[str, ...]:
        """Return the available line section type keys."""
        return _LINE_SECTION_TYPE_KEYS

    def _setup_dialog_layout(self) -> None:
        """Add the live preview beside the existing form."""
        self.setMinimumSize(820, 520)
        self.resize(900, 580)

        preview_layout = QVBoxLayout(self._preview_group)
        preview_layout.addWidget(self._preview, 1)

        main_layout = self.ui.mainLayout
        main_layout.removeWidget(self.ui.groupMain)
        main_layout.removeWidget(self._stack)
        main_layout.removeWidget(self._lbl_summary)
        main_layout.removeWidget(self.ui.buttonBox)

        controls = QWidget(self)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self.ui.groupMain)
        controls_layout.addWidget(self._stack, 1)
        controls_layout.addWidget(self._lbl_summary)

        content = QWidget(self)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._preview_group, 0)
        content_layout.addWidget(controls, 1)

        main_layout.addWidget(content, 1)
        main_layout.addWidget(self.ui.buttonBox)

    @staticmethod
    def _make_dimension_spin(value: float, maximum: float = 10.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setMinimum(0.001)
        spin.setMaximum(maximum)
        spin.setDecimals(3)
        spin.setSingleStep(0.005)
        spin.setSuffix(" m")
        spin.setValue(value)
        return spin

    def _add_parametric_page(
        self,
        section_type: str,
        fields: tuple[tuple[str, str, float, float], ...],
    ) -> None:
        page = QWidget(self._stack)
        form = QFormLayout(page)
        spins: dict[str, QDoubleSpinBox] = {}
        for key, label, value, maximum in fields:
            spin = self._make_dimension_spin(value, maximum)
            spin.valueChanged.connect(self._on_dimension_changed)
            form.addRow(label, spin)
            spins[key] = spin
        self._shape_spins[section_type] = spins
        self._page_by_type[section_type] = self._stack.addWidget(page)

    def _setup_parametric_pages(self) -> None:
        """Add steel parametric section pages to the existing stack."""
        self._page_by_type = {
            "rectangular": self._stack.indexOf(self.ui.pageRect),
            "T": self._stack.indexOf(self.ui.pageT),
            "I_profile": self._stack.indexOf(self.ui.pageProfile),
            "surface": self._stack.indexOf(self.ui.pageSurface),
        }
        self._add_parametric_page(
            "I",
            (
                ("h", self.tr("Hauteur h :"), 0.300, 5.0),
                ("b", self.tr("Largeur b :"), 0.150, 5.0),
                ("tw", self.tr("Epaisseur ame tw :"), 0.008, 1.0),
                ("tf", self.tr("Epaisseur ailes tf :"), 0.012, 1.0),
            ),
        )
        self._add_parametric_page(
            "channel",
            (
                ("h", self.tr("Hauteur h :"), 0.200, 5.0),
                ("b", self.tr("Largeur ailes b :"), 0.080, 5.0),
                ("tw", self.tr("Epaisseur ame tw :"), 0.008, 1.0),
                ("tf", self.tr("Epaisseur ailes tf :"), 0.010, 1.0),
            ),
        )
        self._add_parametric_page(
            "angle",
            (
                ("h", self.tr("Aile verticale h :"), 0.100, 5.0),
                ("b", self.tr("Aile horizontale b :"), 0.075, 5.0),
                ("t", self.tr("Epaisseur t :"), 0.008, 1.0),
            ),
        )
        self._add_parametric_page(
            "pipe",
            (
                ("d", self.tr("Diametre d :"), 0.114, 5.0),
                ("t", self.tr("Epaisseur t :"), 0.005, 1.0),
            ),
        )
        self._add_parametric_page(
            "tube",
            (
                ("h", self.tr("Hauteur h :"), 0.200, 5.0),
                ("b", self.tr("Largeur b :"), 0.100, 5.0),
                ("t", self.tr("Epaisseur t :"), 0.006, 1.0),
            ),
        )

    def _section_type_label(self, section_type: str) -> str:
        labels = {
            "rectangular": self.tr("Rectangulaire"),
            "T": self.tr("Section en T"),
            "I": self.tr("I / H parametrique"),
            "channel": self.tr("U / Channel parametrique"),
            "angle": self.tr("Corniere L parametrique"),
            "pipe": self.tr("Tube circulaire"),
            "tube": self.tr("Tube rectangulaire"),
            "I_profile": self.tr("Profilé acier (catalogue)"),
            "surface": self.tr("Section surfacique"),
        }
        return labels.get(section_type, section_type)

    def _refresh_type_labels(self) -> None:
        current = self._combo_type.currentData()
        self._combo_type.blockSignals(True)
        for index in range(self._combo_type.count()):
            key = str(self._combo_type.itemData(index) or "")
            self._combo_type.setItemText(index, self._section_type_label(key))
        idx = self._combo_type.findData(current)
        if idx >= 0:
            self._combo_type.setCurrentIndex(idx)
        self._combo_type.blockSignals(False)

    @staticmethod
    def _default_material_type_for_section(section_type: str) -> str | None:
        """Return the preferred material type for a section type."""
        return {
            "rectangular": "concrete",
            "I": "steel",
            "channel": "steel",
            "angle": "steel",
            "pipe": "steel",
            "tube": "steel",
            "I_profile": "steel",
        }.get(section_type)

    def _select_material_type(self, material_type: str | None) -> None:
        """Select the first material matching a material type, if available."""
        if not material_type:
            return
        for index in range(self._combo_material.count()):
            tag = self._combo_material.itemData(index)
            mat = self._materials.get(tag)
            if mat is None:
                continue
            if str(getattr(mat, "material_type", "")) == material_type:
                self._combo_material.setCurrentIndex(index)
                return

    def _populate_combos(self) -> None:
        """Populate type and material combo boxes."""
        for key in self._allowed_types:
            if key not in _SECTION_TYPE_KEYS:
                continue
            self._combo_type.addItem(self._section_type_label(key), key)

        self._combo_family.clear()
        self._combo_family.addItems(_PROFILE_FAMILIES)

        for tag, mat in self._materials.items():
            self._combo_material.addItem(f"{mat.name} ({mat.grade})", tag)
        if not self._materials:
            self._combo_material.addItem(self.tr("(aucun matériau)"), 0)

    def _connect_signals(self) -> None:
        """Wire up all signals."""
        self._combo_type.currentIndexChanged.connect(self._on_type_changed)
        self._combo_family.currentIndexChanged.connect(self._on_family_changed)
        self._combo_profile.currentIndexChanged.connect(self._on_profile_changed)
        self._spin_b.valueChanged.connect(self._on_dimension_changed)
        self._spin_h.valueChanged.connect(self._on_dimension_changed)
        self._spin_bw.valueChanged.connect(self._on_dimension_changed)
        self._spin_hw.valueChanged.connect(self._on_dimension_changed)
        self._spin_bf.valueChanged.connect(self._on_dimension_changed)
        self._spin_hf.valueChanged.connect(self._on_dimension_changed)
        self._spin_thickness.valueChanged.connect(self._on_dimension_changed)

        self.ui.buttonBox.accepted.connect(self._validate)
        self.ui.buttonBox.rejected.connect(self.reject)

    def _on_dimension_changed(self) -> None:
        """Refresh limits and preview after a dimensional input changes."""
        if self._updating_dimension_limits:
            return
        self._refresh_dimension_limits()
        self._update_summary()

    @staticmethod
    def _limited_maximum(value: float) -> float:
        return max(0.001, value - _DIMENSION_CLEARANCE)

    def _set_spin_maximum(self, spin: QDoubleSpinBox, maximum: float) -> None:
        maximum = max(spin.minimum(), maximum)
        previous_state = spin.blockSignals(True)
        try:
            spin.setMaximum(maximum)
            if spin.value() > maximum:
                spin.setValue(maximum)
        finally:
            spin.blockSignals(previous_state)

    def _refresh_dimension_limits(self) -> None:
        """Clamp dependent dimensions so the selected shape remains possible."""
        self._updating_dimension_limits = True
        try:
            sec_type = self._combo_type.currentData()
            if sec_type == "T":
                self._set_spin_maximum(
                    self._spin_bw,
                    self._limited_maximum(self._spin_bf.value()),
                )
                return

            spins = self._shape_spins.get(sec_type)
            if not spins:
                return

            if sec_type == "I":
                self._set_spin_maximum(
                    spins["tw"],
                    self._limited_maximum(spins["b"].value()),
                )
                self._set_spin_maximum(
                    spins["tf"],
                    self._limited_maximum(spins["h"].value() / 2.0),
                )
            elif sec_type == "channel":
                self._set_spin_maximum(
                    spins["tw"],
                    self._limited_maximum(spins["b"].value()),
                )
                self._set_spin_maximum(
                    spins["tf"],
                    self._limited_maximum(spins["h"].value() / 2.0),
                )
            elif sec_type == "angle":
                self._set_spin_maximum(
                    spins["t"],
                    self._limited_maximum(min(spins["h"].value(), spins["b"].value())),
                )
            elif sec_type == "pipe":
                self._set_spin_maximum(
                    spins["t"],
                    self._limited_maximum(spins["d"].value() / 2.0),
                )
            elif sec_type == "tube":
                self._set_spin_maximum(
                    spins["t"],
                    self._limited_maximum(
                        min(spins["h"].value(), spins["b"].value()) / 2.0
                    ),
                )
        finally:
            self._updating_dimension_limits = False

    def _current_section_properties(self) -> dict:
        """Return properties for the currently selected section type."""
        sec_type = self._combo_type.currentData()
        if sec_type == "rectangular":
            return {"b": self._spin_b.value(), "h": self._spin_h.value()}
        if sec_type == "T":
            return {
                "bw": self._spin_bw.value(),
                "hw": self._spin_hw.value(),
                "bf": self._spin_bf.value(),
                "hf": self._spin_hf.value(),
            }
        if sec_type in self._shape_spins:
            return {
                key: spin.value()
                for key, spin in self._shape_spins[sec_type].items()
            }
        if sec_type == "I_profile":
            return {"profile": self._combo_profile.currentText()}
        if sec_type == "surface":
            return {"thickness": self._spin_thickness.value()}
        return {}

    def _set_parametric_values(self, section_type: str, properties: dict) -> None:
        """Apply saved parametric values to a dynamic page."""
        for key, spin in self._shape_spins.get(section_type, {}).items():
            if key in properties:
                spin.setValue(float(properties[key]))

    def _apply_initial_values(self) -> None:
        """Apply initial values."""
        if self._init_material_tag is not None:
            idx = self._combo_material.findData(self._init_material_tag)
            if idx >= 0:
                self._combo_material.setCurrentIndex(idx)

        sec_type = self._combo_type.currentData()
        props = self._init_properties

        if sec_type == "rectangular":
            self._spin_b.setValue(float(props.get("b", 0.30)))
            self._spin_h.setValue(float(props.get("h", 0.30)))
        elif sec_type == "T":
            self._spin_bw.setValue(float(props.get("bw", 0.25)))
            self._spin_hw.setValue(float(props.get("hw", 0.40)))
            self._spin_bf.setValue(float(props.get("bf", 0.80)))
            self._spin_hf.setValue(float(props.get("hf", 0.12)))
        elif sec_type in self._shape_spins:
            self._set_parametric_values(sec_type, props)
        elif sec_type == "I_profile":
            profile_name = str(props.get("profile", "")).strip()
            if profile_name:
                try:
                    family = get_profile(profile_name).family
                except KeyError:
                    family = profile_name.split()[0]
                idx_family = self._combo_family.findText(family)
                if idx_family >= 0:
                    self._combo_family.setCurrentIndex(idx_family)
                idx_profile = self._combo_profile.findText(profile_name)
                if idx_profile >= 0:
                    self._combo_profile.setCurrentIndex(idx_profile)
        elif sec_type == "surface":
            self._spin_thickness.setValue(float(props.get("thickness", 0.20)))

        if self._init_name:
            self._edit_name.setText(self._init_name)
        self._refresh_dimension_limits()
        self._update_summary()

    # ── Slots ──────────────────────────────────────────────────────

    def _on_type_changed(self) -> None:
        """Handle type changed."""
        sec_type = self._combo_type.currentData()
        self._stack.setCurrentIndex(self._page_by_type.get(sec_type, 0))
        self._select_material_type(self._default_material_type_for_section(sec_type))
        self._refresh_dimension_limits()

        if sec_type == "I_profile":
            self._on_family_changed()

        self._update_summary()

    def _on_family_changed(self) -> None:
        """Handle family changed."""
        self._combo_profile.clear()
        family = self._combo_family.currentText()
        profiles = list_profiles(family)
        self._combo_profile.addItems(profiles)
        self._on_profile_changed()

    def _on_profile_changed(self) -> None:
        """Handle profile changed."""
        name = self._combo_profile.currentText()
        if not name:
            self._lbl_profile_info.setText("")
            return

        try:
            p = get_profile(name)
            self._lbl_profile_info.setText(
                self.tr("h = {h:.0f} mm, b = {b:.0f} mm\n").format(
                    h=p.h * 1000,
                    b=p.b * 1000,
                )
                + self.tr("A = {area:.1f} cm², Iy = {iy:.0f} cm⁴\n").format(
                    area=p.area * 1e4,
                    iy=p.inertia_y * 1e8,
                )
                + self.tr("Iz = {iz:.0f} cm4, ").format(iz=p.inertia_z * 1e8)
                + self.tr("Masse = {mass:.1f} kg/m").format(mass=p.mass)
            )
        except KeyError:
            self._lbl_profile_info.setText("")

        # Auto-nommer
        current = self._edit_name.text().strip()
        if not current or any(current.startswith(f) for f in _PROFILE_FAMILIES):
            self._edit_name.setText(name)

        self._update_summary()

    def _update_summary(self) -> None:
        """Update summary."""
        sec_type = self._combo_type.currentData()
        properties = self._current_section_properties()
        self._preview.set_section(sec_type, properties)

        if sec_type == "surface":
            self._lbl_summary.setText(
                self.tr("e = {thickness:.1f} cm  |  Section surfacique").format(
                    thickness=float(properties.get("thickness", 0.0)) * 100,
                )
            )
            return

        error_code = _section_geometry_error_code(sec_type, properties)
        if error_code is not None:
            self._lbl_summary.setText(self._geometry_error_message(error_code))
            return

        if sec_type == "I_profile":
            area, iy, iz = _catalog_profile_properties(str(properties.get("profile", "")))
        else:
            area, iy, iz = _section_properties(sec_type, properties)

        if area <= 0.0:
            self._lbl_summary.setText("")
            return
        self._lbl_summary.setText(
            f"A = {area*1e4:.2f} cm2  |  "
            f"Iy = {iy*1e8:.1f} cm4  |  "
            f"Iz = {iz*1e8:.1f} cm4"
        )
        return

        if sec_type == "rectangular":
            b = self._spin_b.value()
            h = self._spin_h.value()
            rect = RectangularSection(b=b, h=h)
            self._lbl_summary.setText(
                f"A = {rect.area*1e4:.2f} cm²  |  "
                f"Iy = {rect.inertia_y*1e8:.1f} cm⁴"
            )
        elif sec_type == "T":
            bw = self._spin_bw.value()
            hw = self._spin_hw.value()
            bf = self._spin_bf.value()
            hf = self._spin_hf.value()
            tsec = TSection(bw=bw, hw=hw, bf=bf, hf=hf)
            self._lbl_summary.setText(
                f"A = {tsec.area*1e4:.2f} cm²  |  "
                f"Iy = {tsec.inertia_y*1e8:.1f} cm⁴"
            )
        elif sec_type == "I_profile":
            name = self._combo_profile.currentText()
            if name:
                try:
                    p = get_profile(name)
                    self._lbl_summary.setText(
                        f"A = {p.area*1e4:.2f} cm²  |  "
                        f"Iy = {p.inertia_y*1e8:.1f} cm⁴"
                    )
                except KeyError:
                    self._lbl_summary.setText("")
            else:
                self._lbl_summary.setText("")
        elif sec_type == "surface":
            thickness = self._spin_thickness.value()
            self._lbl_summary.setText(
                self.tr("e = {thickness:.1f} cm  |  Section surfacique").format(
                    thickness=thickness * 100,
                )
            )

    def _geometry_error_message(self, code: str) -> str:
        """Return a user-facing message for a section geometry validation code."""
        messages = {
            "positive_dimensions": self.tr("Toutes les dimensions doivent etre positives."),
            "t_web_too_wide": self.tr("Pour une section en T, l'ame doit rester plus etroite que la table."),
            "i_web_too_thick": self.tr("Pour une section I/H, l'ame tw doit rester inferieure a la largeur b."),
            "i_flange_too_thick": self.tr("Pour une section I/H, les ailes tf doivent laisser une ame centrale."),
            "channel_web_too_thick": self.tr("Pour une section U, l'ame tw doit rester inferieure a la largeur b."),
            "channel_flange_too_thick": self.tr("Pour une section U, les ailes tf doivent laisser une ame centrale."),
            "angle_too_thick": self.tr("Pour une corniere L, l'epaisseur t doit rester inferieure aux deux ailes."),
            "pipe_too_thick": self.tr("Pour un tube circulaire, le diametre interieur doit rester positif."),
            "tube_too_thick": self.tr("Pour un tube rectangulaire, les dimensions interieures doivent rester positives."),
        }
        return messages.get(code, self.tr("Geometrie de section invalide."))

    def _validate(self) -> None:
        """Handle validate."""
        name = self._edit_name.text().strip()
        if not name:
            self._edit_name.setFocus()
            return
        error_code = _section_geometry_error_code(
            str(self._combo_type.currentData() or ""),
            self._current_section_properties(),
        )
        if error_code is not None:
            QMessageBox.warning(
                self,
                self.tr("Geometrie de section invalide"),
                self._geometry_error_message(error_code),
            )
            return
        self.accept()

    def result(self) -> dict:
        """Handle result."""
        sec_type = self._combo_type.currentData()
        mat_tag = self._combo_material.currentData() or 0
        name = self._edit_name.text().strip()

        data = {
            "name": name,
            "section_type": sec_type,
            "material_tag": mat_tag,
        }

        if sec_type in {"rectangular", "T", "I", "channel", "angle", "pipe", "tube"}:
            properties = self._current_section_properties()
            area, iy, iz = _section_properties(sec_type, properties)
            data["area"] = area
            data["inertia_y"] = iy
            data["inertia_z"] = iz
            data["properties"] = properties
            return data

        if sec_type == "rectangular":
            b = self._spin_b.value()
            h = self._spin_h.value()
            rect = RectangularSection(b=b, h=h)
            data["area"] = rect.area
            data["inertia_y"] = rect.inertia_y
            data["inertia_z"] = rect.inertia_z
            data["properties"] = {"b": b, "h": h}

        elif sec_type == "T":
            bw = self._spin_bw.value()
            hw = self._spin_hw.value()
            bf = self._spin_bf.value()
            hf = self._spin_hf.value()
            tsec = TSection(bw=bw, hw=hw, bf=bf, hf=hf)
            data["area"] = tsec.area
            data["inertia_y"] = tsec.inertia_y
            data["inertia_z"] = 0.0
            data["properties"] = {"bw": bw, "hw": hw, "bf": bf, "hf": hf}

        elif sec_type == "I_profile":
            profile_name = self._combo_profile.currentText()
            try:
                p = get_profile(profile_name)
                data["area"] = p.area
                data["inertia_y"] = p.inertia_y
                data["inertia_z"] = p.inertia_z
                data["properties"] = {"profile": profile_name}
            except KeyError:
                data["area"] = 0.0
                data["inertia_y"] = 0.0
                data["inertia_z"] = 0.0
        elif sec_type == "surface":
            thickness = self._spin_thickness.value()
            data["area"] = 0.0
            data["inertia_y"] = 0.0
            data["inertia_z"] = 0.0
            data["properties"] = {"thickness": thickness}

        return data
