"""
Éditeur visuel de charges.

Création et gestion des cas de charges, charges nodales et réparties.
Interface en panneau avec liste des cas de charge et détail des charges.
"""

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
from gui.resources import app_resource_path


# Types de charges avec labels français
LOAD_TYPES = {
    "dead": "Permanente (G)",
    "live": "Exploitation (Q)",
    "snow": "Neige (S)",
    "wind": "Vent (W)",
    "seismic": "Sismique (E)",
    "temperature": "Température (T)",
}

# Catégories EC1 pour charges d'exploitation
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
    """Widget éditeur de charges."""

    # Signal émis quand le modèle est modifié
    model_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._project: ProjectModel | None = None
        self._load_ui()
        self._populate_combos()
        self._connect_signals()

    def _load_ui(self) -> None:
        """Charge le fichier .ui via QUiLoader."""
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
        """Remplit les combo boxes avec les données dynamiques."""
        for key, label in LOAD_TYPES.items():
            self.ui.cmb_type.addItem(label, key)
        for key, label in LIVE_CATEGORIES.items():
            self.ui.cmb_category.addItem(label, key)

    def _connect_signals(self) -> None:
        """Connecte les signaux des widgets."""
        self.ui.lst_loads.currentRowChanged.connect(self._on_load_selected)
        self.ui.btn_add_load.clicked.connect(self._add_load_case)
        self.ui.btn_del_load.clicked.connect(self._del_load_case)
        self.ui.edt_name.textChanged.connect(self._on_info_changed)
        self.ui.cmb_type.currentIndexChanged.connect(self._on_type_changed)
        self.ui.btn_add_nodal.clicked.connect(self._add_nodal_load)
        self.ui.btn_add_elem.clicked.connect(self._add_element_load)

    def set_project(self, project: ProjectModel) -> None:
        """Définit le projet courant et rafraîchit l'affichage."""
        self._project = project
        self._refresh_load_list()

    def _refresh_load_list(self) -> None:
        """Rafraîchit la liste des cas de charge."""
        self.ui.lst_loads.clear()
        if not self._project:
            return
        for lc in self._project.loads.values():
            type_label = LOAD_TYPES.get(lc.load_type, lc.load_type)
            item = QListWidgetItem(f"{lc.name} ({type_label})")
            item.setData(Qt.UserRole, lc.tag)
            self.ui.lst_loads.addItem(item)

    def _on_load_selected(self, row: int) -> None:
        """Un cas de charge est sélectionné dans la liste."""
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
        """Affiche/masque la catégorie selon le type."""
        load_type = self.ui.cmb_type.currentData()
        self.ui.cmb_category.setVisible(load_type == "live")

    def _on_info_changed(self) -> None:
        """Met à jour le nom du cas de charge sélectionné."""
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
        """Ajoute un nouveau cas de charge."""
        if not self._project:
            return

        tag = self._project.next_load_tag()
        load_type = self.ui.cmb_type.currentData() or "dead"
        category = ""
        if load_type == "live":
            category = self.ui.cmb_category.currentData() or "A"

        name = f"{LOAD_TYPES.get(load_type, 'Charge')} {tag}"
        lc = LoadData(tag=tag, name=name, load_type=load_type, category=category)
        self._project.loads[tag] = lc

        self._refresh_load_list()
        self.ui.lst_loads.setCurrentRow(self.ui.lst_loads.count() - 1)
        self.model_changed.emit()

    def _del_load_case(self) -> None:
        """Supprime le cas de charge sélectionné."""
        if not self._project:
            return
        item = self.ui.lst_loads.currentItem()
        if not item:
            return
        tag = item.data(Qt.UserRole)

        # Supprimer le cas et ses charges associées
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
        """Retourne le tag du cas de charge sélectionné."""
        item = self.ui.lst_loads.currentItem()
        if not item:
            return None
        return item.data(Qt.UserRole)

    def _add_nodal_load(self) -> None:
        """Ajoute une charge nodale au cas sélectionné."""
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
        """Ajoute une charge répartie au cas sélectionné."""
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
