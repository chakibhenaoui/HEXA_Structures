"""Load case and load entry dialogs."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.model_data import ProjectModel

from core.model_data import (
    ElementLoad,
    LoadData,
    NodalLoad,
    PlateSurfaceLoadData,
    SurfaceLoad,
)
from core.self_weight import is_self_weight_load
from gui.dialogs import load_dialog_ui


# Load types
LOAD_TYPES = {
    "permanent": "Permanente (G)",
    "variable": "Exploitation (Q)",
    "snow": "Neige (S)",
    "wind": "Vent (W)",
    "seismic": "Sismique (E)",
}

# EC1 use categories (NF EN 1991-1-1 table 6.1)
EC1_CATEGORIES = {
    "": "(aucune)",
    "A": "A — Habitation, residentiel",
    "B": "B — Bureaux",
    "C1": "C1 — Espaces avec tables (restaurants)",
    "C2": "C2 — Espaces avec sieges fixes (theatres)",
    "C3": "C3 — Espaces sans obstacles (musees, salles)",
    "C4": "C4 — Activites physiques (gymnases)",
    "C5": "C5 — Foules (tribunes, salles de concert)",
    "D1": "D1 — Commerces de detail",
    "D2": "D2 — Grands magasins",
    "E1": "E1 — Stockage (entrepots)",
    "E2": "E2 — Usage industriel",
    "H": "H — Toitures inaccessibles",
}


# ═══════════════════════════════════════════════════════════════════════════
#  Dialog 1: load case (name, type, category)
# ═══════════════════════════════════════════════════════════════════════════

class LoadCaseManagerDialog(QDialog):
    """Load case manager dialog."""

    def __init__(
        self,
        parent=None,
        *,
        project: ProjectModel,
        selected_node_tags: list[int] | None = None,
        selected_element_tags: list[int] | None = None,
        selected_surface_tags: list[int] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Définir les cas de charge")
        self.resize(780, 500)

        self._project = project.copy_for_load_editing()
        self._selected_node_tags = list(selected_node_tags or [])
        self._selected_element_tags = list(selected_element_tags or [])
        self._selected_surface_tags = list(selected_surface_tags or [])

        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        """Build UI."""
        root = QVBoxLayout(self)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        grp_list = QGroupBox("Cas de charge", self)
        grp_list_lay = QVBoxLayout(grp_list)
        self.list_items = QListWidget(grp_list)
        self.list_items.currentItemChanged.connect(
            lambda _current, _previous: self._refresh_buttons()
        )
        self.list_items.itemDoubleClicked.connect(
            lambda _item: self._define_loads()
        )
        grp_list_lay.addWidget(self.list_items)
        content.addWidget(grp_list, 1)

        grp_actions = QGroupBox("Cliquer pour :", self)
        grp_actions_lay = QVBoxLayout(grp_actions)

        self.btn_add = QPushButton("Ajouter cas de charge...", grp_actions)
        self.btn_add.clicked.connect(self._add_load_case)
        grp_actions_lay.addWidget(self.btn_add)

        self.btn_copy = QPushButton("Ajouter copie du cas...", grp_actions)
        self.btn_copy.clicked.connect(self._copy_load_case)
        grp_actions_lay.addWidget(self.btn_copy)

        self.btn_edit = QPushButton("Modifier / Voir cas...", grp_actions)
        self.btn_edit.clicked.connect(self._modify_load_case)
        grp_actions_lay.addWidget(self.btn_edit)

        self.btn_define = QPushButton("Définir les charges...", grp_actions)
        self.btn_define.clicked.connect(self._define_loads)
        grp_actions_lay.addWidget(self.btn_define)

        self.btn_delete = QPushButton("Supprimer cas de charge", grp_actions)
        self.btn_delete.clicked.connect(self._delete_load_case)
        grp_actions_lay.addWidget(self.btn_delete)

        self.btn_switch_combinations = QPushButton("Aller aux combinaisons...", grp_actions)
        self.btn_switch_combinations.clicked.connect(self._switch_to_combinations)
        grp_actions_lay.addSpacing(8)
        grp_actions_lay.addWidget(self.btn_switch_combinations)

        self.lbl_info = QLabel(
            "Le cas Poids propre est automatique : il utilise les sections "
            "et les masses volumiques des matériaux.",
            grp_actions,
        )
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("color: #607080; margin-top: 8px;")
        grp_actions_lay.addWidget(self.lbl_info)
        grp_actions_lay.addStretch(1)

        content.addWidget(grp_actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_list(self) -> None:
        """Refresh list."""
        current_tag = self.current_tag()

        self.list_items.clear()
        for tag, load in sorted(self._project.loads.items()):
            nodal_count = sum(1 for nl in self._project.nodal_loads if nl.load_tag == tag)
            element_count = sum(1 for el in self._project.element_loads if el.load_tag == tag)
            surface_count = sum(1 for sl in self._project.surface_loads if sl.load_tag == tag)
            surface_count += sum(
                1 for sl in self._project.plate_surface_loads if sl.load_tag == tag
            )
            combo_count = sum(
                1 for combo in self._project.combinations.values()
                if tag in combo.factors
            )
            type_label = self._load_type_label(load)
            details = type_label
            if load.category:
                details += f" - Cat. {load.category}"
            if is_self_weight_load(load):
                details += " - automatique"
            else:
                details += f" - {nodal_count + element_count + surface_count} charge(s)"
            if combo_count:
                details += f" - {combo_count} combinaison(s)"

            item = QListWidgetItem(f"{load.name} (T{tag})\n{details}")
            item.setData(Qt.UserRole, tag)
            self.list_items.addItem(item)

        if self.list_items.count():
            target_row = 0
            if current_tag is not None:
                for row in range(self.list_items.count()):
                    if self.list_items.item(row).data(Qt.UserRole) == current_tag:
                        target_row = row
                        break
            self.list_items.setCurrentRow(target_row)

        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        """Refresh buttons."""
        tag = self.current_tag()
        has_selection = tag is not None
        protected = self._is_protected(tag)

        self.btn_copy.setEnabled(has_selection and not protected)
        self.btn_edit.setEnabled(has_selection and not protected)
        self.btn_define.setEnabled(has_selection and not protected)
        self.btn_delete.setEnabled(has_selection and not protected)
        self.btn_switch_combinations.setEnabled(bool(self._project.loads))

    def current_tag(self) -> int | None:
        """Return tag."""
        item = self.list_items.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _next_tag(self) -> int:
        """Return the next tag."""
        return max(self._project.loads.keys(), default=0) + 1

    def _is_protected(self, tag: int | None) -> bool:
        """Return whether protected."""
        if tag is None:
            return False
        load = self._project.loads.get(tag)
        return load is not None and is_self_weight_load(load)

    @staticmethod
    def _load_type_label(load: LoadData) -> str:
        """Load type label."""
        if is_self_weight_load(load):
            return "Poids propre"
        return LOAD_TYPES.get(load.load_type, load.load_type)

    def _add_load_case(self) -> None:
        """Add load case."""
        dlg = LoadCaseDialog(self, project=self._project)
        if dlg.exec() != LoadCaseDialog.Accepted:
            return
        self._refresh_list()

    def _copy_load_case(self) -> None:
        """Copy load case."""
        tag = self.current_tag()
        if tag is None or self._is_protected(tag):
            return

        source = self._project.loads[tag]
        new_tag = self._next_tag()
        self._project.loads[new_tag] = LoadData(
            tag=new_tag,
            name=f"{source.name} - Copie",
            load_type=source.load_type,
            category=source.category,
        )
        self._refresh_list()

    def _modify_load_case(self) -> None:
        """Handle modify load case."""
        tag = self.current_tag()
        if tag is None:
            return
        if self._is_protected(tag):
            self._show_self_weight_message()
            return

        dlg = LoadCaseDialog(self, project=self._project, load_tag=tag)
        if dlg.exec() != LoadCaseDialog.Accepted:
            return
        self._refresh_list()

    def _define_loads(self) -> None:
        """Handle define loads."""
        tag = self.current_tag()
        if tag is None:
            return
        if self._is_protected(tag):
            self._show_self_weight_message()
            return

        if len(self._project.nodes) == 0:
            QMessageBox.warning(
                self,
                "Attention",
                "Ajoutez au moins un nœud avant de définir des charges.",
            )
            return

        dlg = LoadEntryDialog(
            self,
            project=self._project,
            load_tag=tag,
            selected_node_tags=self._selected_node_tags,
            selected_element_tags=self._selected_element_tags,
            selected_surface_tags=self._selected_surface_tags,
        )
        if dlg.exec() != LoadEntryDialog.Accepted:
            return
        self._refresh_list()

    def _delete_load_case(self) -> None:
        """Delete load case."""
        tag = self.current_tag()
        if tag is None:
            return
        if self._is_protected(tag):
            self._show_self_weight_message()
            return

        load = self._project.loads.get(tag)
        if load is None:
            return

        nodal_count = sum(1 for nl in self._project.nodal_loads if nl.load_tag == tag)
        element_count = sum(1 for el in self._project.element_loads if el.load_tag == tag)
        surface_count = sum(1 for sl in self._project.surface_loads if sl.load_tag == tag)
        surface_count += sum(
            1 for sl in self._project.plate_surface_loads if sl.load_tag == tag
        )
        combo_count = sum(
            1 for combo in self._project.combinations.values()
            if tag in combo.factors
        )

        msg = (
            f"Supprimer le cas de charge '{load.name}' ?\n\n"
            f"- Charges nodales : {nodal_count}\n"
            f"- Charges réparties : {element_count}\n"
            f"- Charges surfaciques : {surface_count}\n"
            f"- References dans les combinaisons : {combo_count}"
        )
        if combo_count:
            msg += "\n\nLes facteurs de ce cas seront retires des combinaisons."

        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        del self._project.loads[tag]
        self._project.nodal_loads = [
            nl for nl in self._project.nodal_loads if nl.load_tag != tag
        ]
        self._project.element_loads = [
            el for el in self._project.element_loads if el.load_tag != tag
        ]
        self._project.surface_loads = [
            sl for sl in self._project.surface_loads if sl.load_tag != tag
        ]
        self._project.plate_surface_loads = [
            sl for sl in self._project.plate_surface_loads if sl.load_tag != tag
        ]
        self._project.plate_surface_loads = [
            sl for sl in self._project.plate_surface_loads if sl.load_tag != tag
        ]
        for combo in self._project.combinations.values():
            combo.factors.pop(tag, None)

        self._refresh_list()

    def _show_self_weight_message(self) -> None:
        """Show self-weight message."""
        QMessageBox.information(
            self,
            "Poids propre automatique",
            "Le cas 'Poids propre' est créé et calculé automatiquement à partir "
            "des sections affectees aux barres et des masses volumiques des "
            "matériaux. Il ne se saisit pas manuellement.",
        )

    def _switch_to_combinations(self) -> None:
        """Handle switch to combinations."""
        self._switch_to_combinations_requested = True
        self.accept()

    def switch_to_combinations_requested(self) -> bool:
        """Handle switch to combinations requested."""
        return bool(getattr(self, "_switch_to_combinations_requested", False))

    def result_loads(self) -> dict[int, LoadData]:
        """Return loads."""
        return deepcopy(self._project.loads)

    def result_nodal_loads(self) -> list[NodalLoad]:
        """Return nodal loads."""
        return deepcopy(self._project.nodal_loads)

    def result_element_loads(self) -> list[ElementLoad]:
        """Return element loads."""
        return deepcopy(self._project.element_loads)

    def result_surface_loads(self) -> list[SurfaceLoad]:
        """Return surface loads."""
        return deepcopy(self._project.surface_loads)

    def result_plate_surface_loads(self) -> list[PlateSurfaceLoadData]:
        """Return plate surface loads."""
        return deepcopy(self._project.plate_surface_loads)

    def result_combinations(self):
        """Return combinations."""
        return deepcopy(self._project.combinations)


class LoadCaseDialog(QDialog):
    """Load case dialog."""

    def __init__(self, parent=None, *, project: ProjectModel,
                 load_tag: int | None = None):
        super().__init__(parent)
        self._project = project
        self._load_tag = load_tag
        self._result_tag: int | None = None

        self.ui = load_dialog_ui(self, "load_case_dlg.ui")

        # Convenience references to widgets
        self._edit_name: QLineEdit = self.ui.editName
        self._combo_type: QComboBox = self.ui.comboType
        self._combo_category: QComboBox = self.ui.comboCategory

        # Populate combo boxes
        for key, label in LOAD_TYPES.items():
            self._combo_type.addItem(label, key)

        for key, label in EC1_CATEGORIES.items():
            self._combo_category.addItem(label, key)

        # Auto-nommage quand le type change
        self._combo_type.currentIndexChanged.connect(self._auto_name)

        # Boutons
        self.ui.buttonBox.accepted.connect(self._on_accept)
        self.ui.buttonBox.rejected.connect(self.reject)

        # Window title and pre-fill for edit mode
        title = "Modifier le cas de charge" if load_tag else "Nouveau cas de charge"
        self.setWindowTitle(title)

        if load_tag is not None:
            self._load_existing(load_tag)

    def _auto_name(self) -> None:
        """Handle auto name."""
        current = self._edit_name.text().strip()
        prefixes = ("Permanente", "Exploitation", "Neige", "Vent", "Sismique", "")
        if not current or any(current.startswith(p) for p in prefixes if p):
            names = {
                "permanent": "Permanente",
                "variable": "Exploitation",
                "snow": "Neige",
                "wind": "Vent",
                "seismic": "Sismique",
            }
            load_type = self._combo_type.currentData()
            self._edit_name.setText(names.get(load_type, ""))

    def _load_existing(self, tag: int) -> None:
        """Load existing."""
        lc = self._project.loads.get(tag)
        if lc is None:
            return
        self._edit_name.setText(lc.name)
        idx = self._combo_type.findData(lc.load_type)
        if idx >= 0:
            self._combo_type.setCurrentIndex(idx)
        idx = self._combo_category.findData(lc.category or "")
        if idx >= 0:
            self._combo_category.setCurrentIndex(idx)

    def _on_accept(self) -> None:
        """Handle accept."""
        name = self._edit_name.text().strip()
        if not name:
            self._edit_name.setFocus()
            return

        load_type = self._combo_type.currentData()
        category = self._combo_category.currentData()

        if self._load_tag is not None:
            tag = self._load_tag
        else:
            tag = self._project.next_load_tag()

        lc = LoadData(tag=tag, name=name, load_type=load_type, category=category)
        self._project.loads[tag] = lc
        self._result_tag = tag
        self.accept()

    def load_tag(self) -> int | None:
        """Load tag."""
        return self._result_tag


# ═══════════════════════════════════════════════════════════════════════════
#  Dialog 2: load entry (nodal + distributed)
# ═══════════════════════════════════════════════════════════════════════════

class LoadEntryDialog(QDialog):
    """Load entry dialog."""

    def __init__(
        self,
        parent=None,
        *,
        project: ProjectModel,
        load_tag: int,
        selected_node_tags: list[int] | None = None,
        selected_element_tags: list[int] | None = None,
        selected_surface_tags: list[int] | None = None,
        selection_only: bool = False,
    ):
        super().__init__(parent)
        self._project = project
        self._load_tag = load_tag
        self._selection_only = selection_only
        self._selected_node_tags = [
            tag for tag in (selected_node_tags or []) if tag in self._project.nodes
        ]
        self._selected_element_tags = [
            tag for tag in (selected_element_tags or []) if tag in self._project.elements
        ]
        self._selected_surface_tags = [
            tag for tag in (selected_surface_tags or [])
            if tag in self._project.surface_elements
            or tag in self._project.plate_regions
        ]

        lc = project.loads.get(load_tag)
        lc_name = lc.name if lc else f"T{load_tag}"
        self.setWindowTitle(f"Charges — {lc_name}")
        self.setMinimumSize(700, 500)

        self._setup_ui()
        self._load_existing()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # -- Summary info --
        lc = self._project.loads.get(self._load_tag)
        if lc:
            type_label = LOAD_TYPES.get(lc.load_type, lc.load_type)
            info = QLabel(
                f"<b>{lc.name}</b> — {type_label}"
                + (f" — Cat. {lc.category}" if lc.category else "")
            )
            info.setStyleSheet("margin: 4px; font-size: 12px;")
            layout.addWidget(info)

        if self._selected_node_tags or self._selected_element_tags or self._selected_surface_tags:
            mode = "Affectation à la sélection" if self._selection_only else "Sélection active"
            selected_info = QLabel(
                f"<b>{mode}</b> : "
                f"{len(self._selected_node_tags)} nœud(s), "
                f"{len(self._selected_element_tags)} Élément(s), "
                f"{len(self._selected_surface_tags)} surface(s)."
            )
            selected_info.setWordWrap(True)
            selected_info.setStyleSheet(
                "background: #eaf7ef; border: 1px solid #8bc9a0; "
                "border-radius: 4px; color: #1f6f3d; padding: 6px; margin: 4px;"
            )
            layout.addWidget(selected_info)

        self._tabs = QTabWidget(self)
        layout.addWidget(self._tabs, 1)

        # -- Nodal loads --
        self._tab_nodal = QWidget(self)
        tab_nodal_layout = QVBoxLayout(self._tab_nodal)
        self._grp_nodal = QGroupBox("Charges nodales", self._tab_nodal)
        v_nodal = QVBoxLayout(self._grp_nodal)
        lbl_nodal_help = QLabel(
            "<b>Convention nodale</b> : axes <b>globaux</b> du modèle. "
            "Les forces positives suivent <b>+X, +Y, +Z</b>. "
            "Les moments positifs <b>Mx, My, Mz</b> tournent autour des axes globaux "
            "selon la <b>regle de la main droite</b>."
        )
        lbl_nodal_help.setWordWrap(True)
        lbl_nodal_help.setStyleSheet("color: #4f5b62; font-size: 11px; margin-bottom: 4px;")
        v_nodal.addWidget(lbl_nodal_help)
        lbl_moment_help = QLabel(
            "Lecture des moments : si le pouce de la main droite pointe selon "
            "+X, +Y ou +Z, le sens de fermeture des doigts donne le signe positif "
            "de Mx, My ou Mz."
        )
        lbl_moment_help.setWordWrap(True)
        lbl_moment_help.setStyleSheet("color: #6c757d; font-size: 10px; margin-bottom: 6px;")
        v_nodal.addWidget(lbl_moment_help)

        # Row 1: node + forces
        h_nodal = QHBoxLayout()
        self._cmb_node = QComboBox()
        h_nodal.addWidget(QLabel("Nœud :"))
        h_nodal.addWidget(self._cmb_node)
        if self._selected_node_tags:
            self._lbl_selected_nodes = QLabel(
                f"Sélection : {len(self._selected_node_tags)} nœud(s)",
            )
            h_nodal.addWidget(self._lbl_selected_nodes)
            self._cmb_node.setEnabled(False)

        self._spn_fx = self._make_force_spin()
        self._spn_fx.setToolTip("Force nodale globale positive suivant l'axe +X.")
        h_nodal.addWidget(QLabel("Fx (+X)"))
        h_nodal.addWidget(self._spn_fx)

        self._spn_fy = self._make_force_spin()
        self._spn_fy.setToolTip("Force nodale globale positive suivant l'axe +Y.")
        h_nodal.addWidget(QLabel("Fy (+Y)"))
        h_nodal.addWidget(self._spn_fy)

        self._spn_fz = self._make_force_spin()
        self._spn_fz.setToolTip("Force nodale globale positive suivant l'axe +Z.")
        h_nodal.addWidget(QLabel("Fz (+Z)"))
        h_nodal.addWidget(self._spn_fz)

        v_nodal.addLayout(h_nodal)

        # Row 2: moments + add button
        h_nodal2 = QHBoxLayout()
        h_nodal2.addStretch()

        self._spn_mx = self._make_moment_spin()
        self._spn_mx.setToolTip(
            "Moment nodal global positif autour de l'axe X, suivant la regle de la main droite."
        )
        h_nodal2.addWidget(QLabel("Mx (+ autour X)"))
        h_nodal2.addWidget(self._spn_mx)

        self._spn_my = self._make_moment_spin()
        self._spn_my.setToolTip(
            "Moment nodal global positif autour de l'axe Y, suivant la regle de la main droite."
        )
        h_nodal2.addWidget(QLabel("My (+ autour Y)"))
        h_nodal2.addWidget(self._spn_my)

        self._spn_mz = self._make_moment_spin()
        self._spn_mz.setToolTip(
            "Moment nodal global positif autour de l'axe Z, suivant la regle de la main droite."
        )
        h_nodal2.addWidget(QLabel("Mz (+ autour Z)"))
        h_nodal2.addWidget(self._spn_mz)

        btn_add_nodal = QPushButton(
            "+ Affecter" if self._selected_node_tags else "+ Ajouter"
        )
        btn_add_nodal.clicked.connect(self._add_nodal)
        h_nodal2.addWidget(btn_add_nodal)

        v_nodal.addLayout(h_nodal2)

        # Tableau
        self._tbl_nodal = QTableWidget()
        self._tbl_nodal.setColumnCount(8)
        self._tbl_nodal.setHorizontalHeaderLabels(
            ["Nœud", "Fx global (kN)", "Fy global (kN)", "Fz global (kN)",
             "Mx global (kN.m)", "My global (kN.m)", "Mz global (kN.m)", ""]
        )
        self._tbl_nodal.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self._tbl_nodal.setSelectionBehavior(QTableWidget.SelectRows)
        v_nodal.addWidget(self._tbl_nodal)

        tab_nodal_layout.addWidget(self._grp_nodal)
        self._tabs.addTab(self._tab_nodal, "Nodales")

        # -- Distributed loads --
        self._tab_elem = QWidget(self)
        tab_elem_layout = QVBoxLayout(self._tab_elem)
        self._grp_elem = QGroupBox("Charges réparties sur éléments", self._tab_elem)
        v_elem = QVBoxLayout(self._grp_elem)
        lbl_elem_help = QLabel(
            "<b>Convention répartie</b> : choisissez un repère <b>local</b> "
            "ou <b>global</b>. En global, une charge gravitaire descendante "
            "se saisit en general avec <b>qZ negatif</b>. Le repère choisi est "
            "conservé et les solveurs convertissent au moment de l'analyse."
        )
        lbl_elem_help.setWordWrap(True)
        lbl_elem_help.setStyleSheet("color: #4f5b62; font-size: 11px; margin-bottom: 4px;")
        v_elem.addWidget(lbl_elem_help)
        lbl_elem_moment_note = QLabel(
            "Les diagrammes d'efforts internes suivent ensuite cette même logique : "
            "torsion autour de x local, flexion autour de y ou z local."
        )
        lbl_elem_moment_note.setWordWrap(True)
        lbl_elem_moment_note.setStyleSheet("color: #6c757d; font-size: 10px; margin-bottom: 6px;")
        v_elem.addWidget(lbl_elem_moment_note)

        h_elem = QHBoxLayout()
        self._cmb_elem = QComboBox()
        h_elem.addWidget(QLabel("Élément :"))
        h_elem.addWidget(self._cmb_elem)
        if self._selected_element_tags:
            self._lbl_selected_elements = QLabel(
                f"Sélection : {len(self._selected_element_tags)} Élément(s)",
            )
            h_elem.addWidget(self._lbl_selected_elements)
            self._cmb_elem.setEnabled(False)

        self._cmb_elem_frame = QComboBox()
        self._cmb_elem_frame.addItem("Local", "local")
        self._cmb_elem_frame.addItem("Global", "global")
        self._cmb_elem_frame.currentIndexChanged.connect(self._on_element_load_frame_changed)
        h_elem.addWidget(QLabel("Repère :"))
        h_elem.addWidget(self._cmb_elem_frame)

        self._spn_wx = self._make_dist_spin()
        self._spn_wx.setToolTip("Charge répartie positive suivant l'axe local +x de l'élément.")
        self._lbl_wx = QLabel("wx (+x local)")
        h_elem.addWidget(self._lbl_wx)
        h_elem.addWidget(self._spn_wx)

        self._spn_wy = self._make_dist_spin()
        self._spn_wy.setToolTip("Charge répartie positive suivant l'axe local +y de l'élément.")
        self._lbl_wy = QLabel("wy (+y local)")
        h_elem.addWidget(self._lbl_wy)
        h_elem.addWidget(self._spn_wy)

        self._spn_wz = self._make_dist_spin()
        self._spn_wz.setToolTip("Charge répartie positive suivant l'axe local +z de l'élément.")
        self._lbl_wz = QLabel("wz (+z local)")
        h_elem.addWidget(self._lbl_wz)
        h_elem.addWidget(self._spn_wz)

        btn_add_elem = QPushButton(
            "+ Affecter" if self._selected_element_tags else "+ Ajouter"
        )
        btn_add_elem.clicked.connect(self._add_element_load)
        h_elem.addWidget(btn_add_elem)

        v_elem.addLayout(h_elem)

        # Tableau
        self._tbl_elem = QTableWidget()
        self._tbl_elem.setColumnCount(6)
        self._tbl_elem.setHorizontalHeaderLabels(
            ["Élément", "Repère", "q1/wx (kN/m)", "q2/wy (kN/m)", "q3/wz (kN/m)", ""]
        )
        self._tbl_elem.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self._tbl_elem.setSelectionBehavior(QTableWidget.SelectRows)
        v_elem.addWidget(self._tbl_elem)

        tab_elem_layout.addWidget(self._grp_elem)
        self._tabs.addTab(self._tab_elem, "Éléments")

        # -- Surface loads --
        self._tab_surface = QWidget(self)
        tab_surface_layout = QVBoxLayout(self._tab_surface)
        self._grp_surface = QGroupBox("Charges surfaciques sur plaques", self._tab_surface)
        v_surface = QVBoxLayout(self._grp_surface)
        lbl_surface_help = QLabel(
            "<b>Convention surfacique</b> : les composantes qX, qY et qZ sont "
            "exprimées dans le repère <b>global</b>. Une charge gravitaire "
            "descendante se saisit donc en general avec <b>qZ negatif</b>."
        )
        lbl_surface_help.setWordWrap(True)
        lbl_surface_help.setStyleSheet("color: #4f5b62; font-size: 11px; margin-bottom: 4px;")
        v_surface.addWidget(lbl_surface_help)
        lbl_surface_note = QLabel(
            "Cette V1 applique une charge uniforme sur chaque plaque et la "
            "convertit en efforts nodaux equivalents."
        )
        lbl_surface_note.setWordWrap(True)
        lbl_surface_note.setStyleSheet("color: #6c757d; font-size: 10px; margin-bottom: 6px;")
        v_surface.addWidget(lbl_surface_note)

        h_surface = QHBoxLayout()
        self._cmb_surface = QComboBox()
        h_surface.addWidget(QLabel("Surface :"))
        h_surface.addWidget(self._cmb_surface)
        if self._selected_surface_tags:
            self._lbl_selected_surfaces = QLabel(
                f"Sélection : {len(self._selected_surface_tags)} surface(s)",
            )
            h_surface.addWidget(self._lbl_selected_surfaces)
            self._cmb_surface.setEnabled(False)

        self._spn_qx = self._make_area_spin()
        self._spn_qx.setToolTip("Charge surfacique globale positive suivant l'axe +X.")
        h_surface.addWidget(QLabel("qX global"))
        h_surface.addWidget(self._spn_qx)

        self._spn_qy = self._make_area_spin()
        self._spn_qy.setToolTip("Charge surfacique globale positive suivant l'axe +Y.")
        h_surface.addWidget(QLabel("qY global"))
        h_surface.addWidget(self._spn_qy)

        self._spn_qz = self._make_area_spin()
        self._spn_qz.setToolTip("Charge surfacique globale positive suivant l'axe +Z.")
        h_surface.addWidget(QLabel("qZ global"))
        h_surface.addWidget(self._spn_qz)

        btn_add_surface = QPushButton(
            "+ Affecter" if self._selected_surface_tags else "+ Ajouter"
        )
        btn_add_surface.clicked.connect(self._add_surface_load)
        h_surface.addWidget(btn_add_surface)

        v_surface.addLayout(h_surface)

        self._tbl_surface = QTableWidget()
        self._tbl_surface.setColumnCount(5)
        self._tbl_surface.setHorizontalHeaderLabels(
            ["Surface", "qX global (kN/m2)", "qY global (kN/m2)", "qZ global (kN/m2)", ""]
        )
        self._tbl_surface.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self._tbl_surface.setSelectionBehavior(QTableWidget.SelectRows)
        v_surface.addWidget(self._tbl_surface)

        tab_surface_layout.addWidget(self._grp_surface)
        self._tabs.addTab(self._tab_surface, "Surfaciques")

        # ── Boutons OK / Annuler ──
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Remplir les combobox
        self._populate_combos()
        if self._selection_only:
            self._grp_nodal.setEnabled(bool(self._selected_node_tags))
            self._grp_elem.setEnabled(bool(self._selected_element_tags))
            self._grp_surface.setEnabled(bool(self._selected_surface_tags))
            self._tabs.setTabEnabled(0, bool(self._selected_node_tags))
            self._tabs.setTabEnabled(1, bool(self._selected_element_tags))
            self._tabs.setTabEnabled(2, bool(self._selected_surface_tags))
        else:
            has_surfaces = bool(self._project.surface_elements or self._project.plate_regions)
            self._grp_surface.setEnabled(has_surfaces)
            self._tabs.setTabEnabled(2, has_surfaces)
        self._select_first_enabled_load_tab()

    def _select_first_enabled_load_tab(self) -> None:
        for index in range(self._tabs.count()):
            if self._tabs.isTabEnabled(index):
                self._tabs.setCurrentIndex(index)
                return

    def _populate_combos(self) -> None:
        """Handle populate combinations."""
        self._cmb_node.clear()
        for ntag in sorted(self._project.nodes.keys()):
            self._cmb_node.addItem(f"N{ntag}", ntag)
        if self._selected_node_tags:
            idx = self._cmb_node.findData(self._selected_node_tags[0])
            if idx >= 0:
                self._cmb_node.setCurrentIndex(idx)

        self._cmb_elem.clear()
        for etag in sorted(self._project.elements.keys()):
            self._cmb_elem.addItem(f"E{etag}", etag)
        if self._selected_element_tags:
            idx = self._cmb_elem.findData(self._selected_element_tags[0])
            if idx >= 0:
                self._cmb_elem.setCurrentIndex(idx)

        self._cmb_surface.clear()
        for stag in sorted(self._project.surface_elements.keys()):
            self._cmb_surface.addItem(f"S{stag}", ("surface", int(stag)))
        for ptag, plate in sorted(self._project.plate_regions.items()):
            label = f"P{ptag}"
            if plate.name:
                label += f" - {plate.name}"
            self._cmb_surface.addItem(label, ("plate", int(ptag)))
        if self._selected_surface_tags:
            target = self._surface_target_from_tag(self._selected_surface_tags[0])
            idx = self._cmb_surface.findData(target)
            if idx >= 0:
                self._cmb_surface.setCurrentIndex(idx)

    def _surface_target_from_tag(self, tag: int):
        """Handle surface target from tag."""
        tag = int(tag)
        if tag in self._project.plate_regions:
            return ("plate", tag)
        if tag in self._project.surface_elements:
            return ("surface", tag)
        return None

    @staticmethod
    def _normalized_surface_target(target):
        if isinstance(target, tuple) and len(target) == 2:
            return str(target[0]), int(target[1])
        if target is None:
            return None
        return "surface", int(target)

    def _surface_load_for_target(
        self,
        target,
        *,
        qx: float,
        qy: float,
        qz: float,
    ) -> SurfaceLoad | PlateSurfaceLoadData | None:
        normalized = self._normalized_surface_target(target)
        if normalized is None:
            return None
        kind, tag = normalized
        if kind == "plate":
            return PlateSurfaceLoadData(
                load_tag=self._load_tag,
                plate_tag=tag,
                qx=qx,
                qy=qy,
                qz=qz,
            )
        return SurfaceLoad(
            load_tag=self._load_tag,
            surface_tag=tag,
            qx=qx,
            qy=qy,
            qz=qz,
        )

    def _load_existing(self) -> None:
        """Load existing."""
        tag = self._load_tag

        for nl in self._project.nodal_loads:
            if nl.load_tag == tag:
                self._add_nodal_row(nl)

        for el in self._project.element_loads:
            if el.load_tag == tag:
                self._add_elem_row(el)

        for sl in self._project.surface_loads:
            if sl.load_tag == tag:
                self._add_surface_row(sl)
        for sl in self._project.plate_surface_loads:
            if sl.load_tag == tag:
                self._add_surface_row(sl)

    # -- Nodal loads --

    def _add_nodal(self) -> None:
        """Add nodal."""
        if self._selected_node_tags:
            self._add_nodal_to_selection()
            return
        node_tag = self._cmb_node.currentData()
        if node_tag is None:
            return

        nl = NodalLoad(
            load_tag=self._load_tag,
            node_tag=node_tag,
            fx=self._spn_fx.value(),
            fy=self._spn_fy.value(),
            fz=self._spn_fz.value(),
            mx=self._spn_mx.value(),
            my=self._spn_my.value(),
            mz=self._spn_mz.value(),
        )
        self._add_nodal_row(nl)

        # Reset
        for spn in (self._spn_fx, self._spn_fy, self._spn_fz,
                    self._spn_mx, self._spn_my, self._spn_mz):
            spn.setValue(0.0)

    def _add_nodal_to_selection(self) -> None:
        """Add nodal to selection."""
        if not self._selected_node_tags:
            return

        values = {
            "fx": self._spn_fx.value(),
            "fy": self._spn_fy.value(),
            "fz": self._spn_fz.value(),
            "mx": self._spn_mx.value(),
            "my": self._spn_my.value(),
            "mz": self._spn_mz.value(),
        }
        for node_tag in self._selected_node_tags:
            self._add_nodal_row(
                NodalLoad(
                    load_tag=self._load_tag,
                    node_tag=node_tag,
                    **values,
                )
            )

        for spn in (self._spn_fx, self._spn_fy, self._spn_fz,
                    self._spn_mx, self._spn_my, self._spn_mz):
            spn.setValue(0.0)

    def _add_nodal_row(self, nl: NodalLoad) -> None:
        """Add nodal row."""
        row = self._tbl_nodal.rowCount()
        self._tbl_nodal.setRowCount(row + 1)

        item_node = QTableWidgetItem(f"N{nl.node_tag}")
        item_node.setData(Qt.UserRole, nl.node_tag)
        item_node.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self._tbl_nodal.setItem(row, 0, item_node)

        for col, val in enumerate([nl.fx, nl.fy, nl.fz, nl.mx, nl.my, nl.mz], 1):
            item = QTableWidgetItem(f"{val:.2f}")
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._tbl_nodal.setItem(row, col, item)

        btn_del = QPushButton("X")
        btn_del.setMaximumWidth(30)
        btn_del.clicked.connect(lambda _, r=row: self._del_nodal_row(r))
        self._tbl_nodal.setCellWidget(row, 7, btn_del)

    def _del_nodal_row(self, row: int) -> None:
        """Delete nodal row."""
        self._tbl_nodal.removeRow(row)
        self._reconnect_delete_buttons()

    # -- Distributed loads --

    def _on_element_load_frame_changed(self) -> None:
        """Handle element load frame changed."""
        if self._cmb_elem_frame.currentData() == "global":
            self._lbl_wx.setText("qX global")
            self._lbl_wy.setText("qY global")
            self._lbl_wz.setText("qZ global")
            self._spn_wx.setToolTip("Charge répartie positive suivant l'axe global +X.")
            self._spn_wy.setToolTip("Charge répartie positive suivant l'axe global +Y.")
            self._spn_wz.setToolTip("Charge répartie positive suivant l'axe global +Z.")
            return

        self._lbl_wx.setText("wx (+x local)")
        self._lbl_wy.setText("wy (+y local)")
        self._lbl_wz.setText("wz (+z local)")
        self._spn_wx.setToolTip("Charge répartie positive suivant l'axe local +x de l'élément.")
        self._spn_wy.setToolTip("Charge répartie positive suivant l'axe local +y de l'élément.")
        self._spn_wz.setToolTip("Charge répartie positive suivant l'axe local +z de l'élément.")

    def _element_dist_components(self) -> tuple[float, float, float]:
        """Handle element dist components."""
        return (
            self._spn_wx.value(),
            self._spn_wy.value(),
            self._spn_wz.value(),
        )

    def _element_dist_coordinate_system(self) -> str:
        """Handle element dist coordinate system."""
        frame = self._cmb_elem_frame.currentData()
        return "global" if frame == "global" else "local"

    def _reset_dist_spins(self) -> None:
        """Reset dist spins."""
        for spn in (self._spn_wx, self._spn_wy, self._spn_wz):
            spn.setValue(0.0)

    def _add_element_load(self) -> None:
        """Add element load."""
        if self._selected_element_tags:
            self._add_element_load_to_selection()
            return
        elem_tag = self._cmb_elem.currentData()
        if elem_tag is None:
            return

        wx, wy, wz = self._element_dist_components()
        el = ElementLoad(
            load_tag=self._load_tag,
            element_tag=elem_tag,
            wx=wx,
            wy=wy,
            wz=wz,
            coordinate_system=self._element_dist_coordinate_system(),
        )
        self._add_elem_row(el)

        self._reset_dist_spins()

    def _add_element_load_to_selection(self) -> None:
        """Add element load to selection."""
        if not self._selected_element_tags:
            return

        for elem_tag in self._selected_element_tags:
            wx, wy, wz = self._element_dist_components()
            self._add_elem_row(
                ElementLoad(
                    load_tag=self._load_tag,
                    element_tag=elem_tag,
                    wx=wx,
                    wy=wy,
                    wz=wz,
                    coordinate_system=self._element_dist_coordinate_system(),
                )
            )

        self._reset_dist_spins()

    def _add_elem_row(self, el: ElementLoad) -> None:
        """Add element row."""
        row = self._tbl_elem.rowCount()
        self._tbl_elem.setRowCount(row + 1)

        item_elem = QTableWidgetItem(f"E{el.element_tag}")
        item_elem.setData(Qt.UserRole, el.element_tag)
        item_elem.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self._tbl_elem.setItem(row, 0, item_elem)

        coordinate_system = str(
            getattr(el, "coordinate_system", "local") or "local",
        ).strip().lower()
        coordinate_system = "global" if coordinate_system == "global" else "local"
        item_frame = QTableWidgetItem("Global" if coordinate_system == "global" else "Local")
        item_frame.setData(Qt.UserRole, coordinate_system)
        item_frame.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self._tbl_elem.setItem(row, 1, item_frame)

        for col, val in enumerate([el.wx, el.wy, el.wz], 2):
            item = QTableWidgetItem(f"{val:.2f}")
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._tbl_elem.setItem(row, col, item)

        btn_del = QPushButton("X")
        btn_del.setMaximumWidth(30)
        btn_del.clicked.connect(lambda _, r=row: self._del_elem_row(r))
        self._tbl_elem.setCellWidget(row, 5, btn_del)

    def _del_elem_row(self, row: int) -> None:
        """Delete element row."""
        self._tbl_elem.removeRow(row)
        self._reconnect_delete_buttons()

    # -- Surface loads --

    def _reset_surface_spins(self) -> None:
        """Reset surface spins."""
        for spn in (self._spn_qx, self._spn_qy, self._spn_qz):
            spn.setValue(0.0)

    def _add_surface_load(self) -> None:
        """Add surface load."""
        if self._selected_surface_tags:
            self._add_surface_load_to_selection()
            return
        target = self._cmb_surface.currentData()
        if target is None:
            return

        sl = self._surface_load_for_target(
            target,
            qx=self._spn_qx.value(),
            qy=self._spn_qy.value(),
            qz=self._spn_qz.value(),
        )
        if sl is None:
            return
        self._add_surface_row(sl)
        self._reset_surface_spins()

    def _add_surface_load_to_selection(self) -> None:
        """Add surface load to selection."""
        if not self._selected_surface_tags:
            return

        for surface_tag in self._selected_surface_tags:
            target = self._surface_target_from_tag(surface_tag)
            sl = self._surface_load_for_target(
                target,
                qx=self._spn_qx.value(),
                qy=self._spn_qy.value(),
                qz=self._spn_qz.value(),
            )
            if sl is not None:
                self._add_surface_row(sl)

        self._reset_surface_spins()

    def _add_surface_row(self, sl: SurfaceLoad | PlateSurfaceLoadData) -> None:
        """Add surface row."""
        row = self._tbl_surface.rowCount()
        self._tbl_surface.setRowCount(row + 1)

        if isinstance(sl, PlateSurfaceLoadData):
            target = ("plate", int(sl.plate_tag))
            label = f"P{sl.plate_tag}"
        else:
            target = ("surface", int(sl.surface_tag))
            label = f"S{sl.surface_tag}"

        item_surface = QTableWidgetItem(label)
        item_surface.setData(Qt.UserRole, target)
        item_surface.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self._tbl_surface.setItem(row, 0, item_surface)

        for col, val in enumerate([sl.qx, sl.qy, sl.qz], 1):
            item = QTableWidgetItem(f"{val:.2f}")
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._tbl_surface.setItem(row, col, item)

        btn_del = QPushButton("X")
        btn_del.setMaximumWidth(30)
        btn_del.clicked.connect(lambda _, r=row: self._del_surface_row(r))
        self._tbl_surface.setCellWidget(row, 4, btn_del)

    def _del_surface_row(self, row: int) -> None:
        """Delete surface row."""
        self._tbl_surface.removeRow(row)
        self._reconnect_delete_buttons()

    def _reconnect_delete_buttons(self) -> None:
        """Handle reconnect delete buttons."""
        for row in range(self._tbl_nodal.rowCount()):
            btn = QPushButton("X")
            btn.setMaximumWidth(30)
            btn.clicked.connect(lambda _, r=row: self._del_nodal_row(r))
            self._tbl_nodal.setCellWidget(row, 7, btn)

        for row in range(self._tbl_elem.rowCount()):
            btn = QPushButton("X")
            btn.setMaximumWidth(30)
            btn.clicked.connect(lambda _, r=row: self._del_elem_row(r))
            self._tbl_elem.setCellWidget(row, 5, btn)

        for row in range(self._tbl_surface.rowCount()):
            btn = QPushButton("X")
            btn.setMaximumWidth(30)
            btn.clicked.connect(lambda _, r=row: self._del_surface_row(r))
            self._tbl_surface.setCellWidget(row, 4, btn)

    # ── Validation ──

    def _on_accept(self) -> None:
        """Handle accept."""
        tag = self._load_tag

        # Remove the old loads for this case
        self._project.nodal_loads = [
            nl for nl in self._project.nodal_loads if nl.load_tag != tag
        ]
        self._project.element_loads = [
            el for el in self._project.element_loads if el.load_tag != tag
        ]
        self._project.surface_loads = [
            sl for sl in self._project.surface_loads if sl.load_tag != tag
        ]

        # Add nodal loads from the table
        for row in range(self._tbl_nodal.rowCount()):
            node_item = self._tbl_nodal.item(row, 0)
            if node_item is None:
                continue
            node_tag = node_item.data(Qt.UserRole)
            vals = []
            for col in range(1, 7):
                item = self._tbl_nodal.item(row, col)
                vals.append(float(item.text()) if item else 0.0)

            nl = NodalLoad(
                load_tag=tag, node_tag=node_tag,
                fx=vals[0], fy=vals[1], fz=vals[2],
                mx=vals[3], my=vals[4], mz=vals[5],
            )
            self._project.nodal_loads.append(nl)

        # Add distributed loads from the table
        for row in range(self._tbl_elem.rowCount()):
            elem_item = self._tbl_elem.item(row, 0)
            if elem_item is None:
                continue
            elem_tag = elem_item.data(Qt.UserRole)
            frame_item = self._tbl_elem.item(row, 1)
            coordinate_system = (
                frame_item.data(Qt.UserRole)
                if frame_item is not None
                else "local"
            )
            if coordinate_system not in {"local", "global"}:
                coordinate_system = "local"
            vals = []
            for col in range(2, 5):
                item = self._tbl_elem.item(row, col)
                vals.append(float(item.text()) if item else 0.0)

            el = ElementLoad(
                load_tag=tag, element_tag=elem_tag,
                wx=vals[0], wy=vals[1], wz=vals[2],
                coordinate_system=coordinate_system,
            )
            self._project.element_loads.append(el)

        # Add surface loads from the table
        for row in range(self._tbl_surface.rowCount()):
            surface_item = self._tbl_surface.item(row, 0)
            if surface_item is None:
                continue
            target = self._normalized_surface_target(surface_item.data(Qt.UserRole))
            if target is None:
                continue
            vals = []
            for col in range(1, 4):
                item = self._tbl_surface.item(row, col)
                vals.append(float(item.text()) if item else 0.0)

            kind, surface_tag = target
            if kind == "plate":
                sl = PlateSurfaceLoadData(
                    load_tag=tag,
                    plate_tag=surface_tag,
                    qx=vals[0],
                    qy=vals[1],
                    qz=vals[2],
                )
                self._project.plate_surface_loads.append(sl)
            else:
                sl = SurfaceLoad(
                    load_tag=tag,
                    surface_tag=surface_tag,
                    qx=vals[0],
                    qy=vals[1],
                    qz=vals[2],
                )
                self._project.surface_loads.append(sl)

        self.accept()

    # ── Helpers ──

    @staticmethod
    def _make_force_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-1e9, 1e9)
        spin.setDecimals(2)
        spin.setSuffix(" kN")
        spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        spin.setMaximumWidth(100)
        return spin

    @staticmethod
    def _make_moment_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-1e9, 1e9)
        spin.setDecimals(2)
        spin.setSuffix(" kN.m")
        spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        spin.setMaximumWidth(100)
        return spin

    @staticmethod
    def _make_dist_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-1e9, 1e9)
        spin.setDecimals(2)
        spin.setSuffix(" kN/m")
        spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        spin.setMaximumWidth(100)
        return spin

    @staticmethod
    def _make_area_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-1e9, 1e9)
        spin.setDecimals(2)
        spin.setSuffix(" kN/m2")
        spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        spin.setMaximumWidth(110)
        return spin
