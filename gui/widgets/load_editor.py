"""Load editor widgets."""

from __future__ import annotations


from PySide6.QtCore import QFile, QIODevice, Qt, Signal
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.model_data import (
    LoadData,
    NodalLoad,
    ElementLoad,
    ProjectModel,
)
from gui.i18n.display_labels import load_name_label, load_type_label
from gui.resources import app_resource_path


# Load types with French labels
LOAD_TYPES = {
    "dead": "Permanente (G)",
    "live": "Exploitation (Q)",
    "snow": "Neige (S)",
    "wind": "Vent (W)",
    "seismic": "Sismique (E)",
    "temperature": "Température (T)",
}

# EC1 categories for imposed loads
LIVE_CATEGORIES = {
    "A": "A — Habitation, résidentiel",
    "B": "B — Bureaux",
    "C": "C — Lieux de réunion",
    "D": "D — Commerces",
    "E": "E — Stockage",
    "F": "F — Trafic véhicules ≤ 30 kN",
    "G": "G — Trafic véhicules > 30 kN",
    "H": "H — Toitures",
}


class LoadEditor(QWidget):
    """Load editor."""

    # Signal emitted when the model changes
    model_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._project: ProjectModel | None = None
        self._load_ui()
        self._populate_combos()
        self._connect_signals()

    def _load_ui(self) -> None:
        """Load UI."""
        ui_path = app_resource_path("gui", "ui", "load_editor.ui")
        loader = QUiLoader()
        file = QFile(ui_path)
        if not file.open(QIODevice.ReadOnly):
            raise RuntimeError(f"Unable to open/read ui device: {ui_path}")
        self.ui = loader.load(file, self)
        file.close()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)

    def _populate_combos(self) -> None:
        """Handle populate combinations."""
        for key in LOAD_TYPES:
            self.ui.cmb_type.addItem(load_type_label(key), key)
        for key in LIVE_CATEGORIES:
            self.ui.cmb_category.addItem(self._category_label(key), key)

    def _category_label(self, key: str) -> str:
        labels = {
            "A": self.tr("A — Habitation, résidentiel"),
            "B": self.tr("B — Bureaux"),
            "C": self.tr("C — Lieux de réunion"),
            "D": self.tr("D — Commerces"),
            "E": self.tr("E — Stockage"),
            "F": self.tr("F — Trafic véhicules ≤ 30 kN"),
            "G": self.tr("G — Trafic véhicules > 30 kN"),
            "H": self.tr("H — Toitures"),
        }
        return labels.get(key, key)

    def _connect_signals(self) -> None:
        """Handle connect signals."""
        self.ui.lst_loads.currentRowChanged.connect(self._on_load_selected)
        self.ui.btn_add_load.clicked.connect(self._add_load_case)
        self.ui.btn_del_load.clicked.connect(self._del_load_case)
        self.ui.edt_name.textChanged.connect(self._on_info_changed)
        self.ui.cmb_type.currentIndexChanged.connect(self._on_type_changed)
        self.ui.btn_add_nodal.clicked.connect(self._add_nodal_load)
        self.ui.btn_add_elem.clicked.connect(self._add_element_load)

    def set_project(self, project: ProjectModel) -> None:
        """Set project."""
        self._project = project
        self._refresh_load_list()

    def _refresh_load_list(self) -> None:
        """Refresh load list."""
        self.ui.lst_loads.clear()
        if not self._project:
            return
        for lc in self._project.loads.values():
            type_label = load_type_label(lc.load_type)
            item = QListWidgetItem(
                self.tr("{name} ({type})").format(
                    name=load_name_label(lc),
                    type=type_label,
                )
            )
            item.setData(Qt.UserRole, lc.tag)
            self.ui.lst_loads.addItem(item)

    def _on_load_selected(self, row: int) -> None:
        """Handle load selected."""
        if row < 0 or not self._project:
            return
        item = self.ui.lst_loads.item(row)
        if not item:
            return
        tag = item.data(Qt.UserRole)
        lc = self._project.loads.get(tag)
        if not lc:
            return

        self.ui.edt_name.blockSignals(True)
        self.ui.edt_name.setText(lc.name)
        self.ui.edt_name.blockSignals(False)

        idx = self.ui.cmb_type.findData(lc.load_type)
        if idx >= 0:
            self.ui.cmb_type.blockSignals(True)
            self.ui.cmb_type.setCurrentIndex(idx)
            self.ui.cmb_type.blockSignals(False)

        cat_idx = self.ui.cmb_category.findData(lc.category)
        if cat_idx >= 0:
            self.ui.cmb_category.setCurrentIndex(cat_idx)

        self._on_type_changed()

    def _on_type_changed(self) -> None:
        """Handle type changed."""
        load_type = self.ui.cmb_type.currentData()
        self.ui.cmb_category.setVisible(load_type == "live")

    def _on_info_changed(self) -> None:
        """Handle info changed."""
        if not self._project:
            return
        item = self.ui.lst_loads.currentItem()
        if not item:
            return
        tag = item.data(Qt.UserRole)
        lc = self._project.loads.get(tag)
        if lc:
            lc.name = self.ui.edt_name.text()
            self._refresh_load_list()
            self.model_changed.emit()

    def _add_load_case(self) -> None:
        """Add load case."""
        if not self._project:
            return

        tag = self._project.next_load_tag()
        load_type = self.ui.cmb_type.currentData() or "dead"
        category = ""
        if load_type == "live":
            category = self.ui.cmb_category.currentData() or "A"

        name = self.tr("{type} {tag}").format(
            type=load_type_label(load_type) or self.tr("Charge"),
            tag=tag,
        )
        lc = LoadData(tag=tag, name=name, load_type=load_type, category=category)
        self._project.loads[tag] = lc

        self._refresh_load_list()
        self.ui.lst_loads.setCurrentRow(self.ui.lst_loads.count() - 1)
        self.model_changed.emit()

    def _del_load_case(self) -> None:
        """Delete load case."""
        if not self._project:
            return
        item = self.ui.lst_loads.currentItem()
        if not item:
            return
        tag = item.data(Qt.UserRole)

        # Delete the case and its associated loads
        self._project.loads.pop(tag, None)
        self._project.nodal_loads = [
            nl for nl in self._project.nodal_loads if nl.load_tag != tag
        ]
        self._project.element_loads = [
            el for el in self._project.element_loads if el.load_tag != tag
        ]

        self._refresh_load_list()
        self.model_changed.emit()

    def _get_current_load_tag(self) -> int | None:
        """Return current load tag."""
        item = self.ui.lst_loads.currentItem()
        if not item:
            return None
        return item.data(Qt.UserRole)

    def _add_nodal_load(self) -> None:
        """Add nodal load."""
        if not self._project:
            return
        load_tag = self._get_current_load_tag()
        if load_tag is None:
            return

        nl = NodalLoad(
            load_tag=load_tag,
            node_tag=self.ui.spn_node_tag.value(),
            fx=self.ui.spn_fx.value(),
            fy=self.ui.spn_fy.value(),
            fz=self.ui.spn_fz.value(),
            mx=self.ui.spn_mx.value(),
            my=self.ui.spn_my.value(),
            mz=self.ui.spn_mz.value(),
        )
        self._project.nodal_loads.append(nl)
        self.model_changed.emit()

    def _add_element_load(self) -> None:
        """Add element load."""
        if not self._project:
            return
        load_tag = self._get_current_load_tag()
        if load_tag is None:
            return

        el = ElementLoad(
            load_tag=load_tag,
            element_tag=self.ui.spn_elem_tag.value(),
            wx=self.ui.spn_wx.value(),
            wy=self.ui.spn_wy.value(),
            wz=self.ui.spn_wz.value(),
        )
        self._project.element_loads.append(el)
        self.model_changed.emit()
