"""
Arbre hiérarchique du modèle.

Nœuds, éléments, matériaux, sections, cas de charges, combinaisons.
Sélection synchronisée avec la vue 3D et le panneau de propriétés.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
)

from core.model_data import PLATE_MESH_MODE_AUTO
from core.plate_mesh_settings import effective_plate_mesh_divisions

if TYPE_CHECKING:
    from core.model_data import ProjectModel


class ItemKind(Enum):
    """Type d'objet représenté par un item de l'arbre."""

    ROOT = auto()
    NODE = auto()
    ELEMENT = auto()
    SURFACE = auto()
    MATERIAL = auto()
    SECTION = auto()
    LOAD_CASE = auto()
    COMBINATION = auto()


# Rôle Qt custom pour stocker le tag et le type d'objet
_ROLE_TAG = Qt.UserRole
_ROLE_KIND = Qt.UserRole + 1


class ModelTree(QTreeWidget):
    """Arbre hiérarchique du modèle structurel.

    Signaux :
        node_selected(int) : tag du nœud sélectionné.
        element_selected(int) : tag de l'élément sélectionné.
        surface_selected(int) : tag de la surface sélectionnée.
        material_selected(int) : tag du matériau sélectionné.
        section_selected(int) : tag de la section sélectionnée.
        load_selected(int) : tag du cas de charge sélectionné.
        combination_selected(int) : tag de la combinaison sélectionnée.
        add_requested(str) : demande d'ajout (\"node\", \"element\", etc.).
        edit_requested(str, int) : demande d'édition (kind, tag).
        delete_requested(str, int) : demande de suppression (kind, tag).
    """

    node_selected = Signal(int)
    element_selected = Signal(int)
    surface_selected = Signal(int)
    material_selected = Signal(int)
    section_selected = Signal(int)
    load_selected = Signal(int)
    combination_selected = Signal(int)
    add_requested = Signal(str)
    edit_requested = Signal(str, int)
    delete_requested = Signal(str, int)
    load_double_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: ProjectModel | None = None

        self.setHeaderLabels(["Élément", "Détails"])
        self.setMinimumWidth(220)
        self.setColumnWidth(0, 150)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        # Connexions
        self.currentItemChanged.connect(self._on_item_changed)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    # ── Mise à jour depuis le modèle ─────────────────────────────────────

    def refresh(self, project: ProjectModel) -> None:
        """Reconstruit l'arbre à partir du modèle.

        Args:
            project: Modèle de données du projet.
        """
        self._project = project
        self.clear()

        self._root_nodes = self._add_category(
            "Nœuds", f"({len(project.nodes)})", ItemKind.ROOT,
        )
        for tag, node in project.nodes.items():
            fix_str = ""
            if node.is_support:
                dof_names = ("Ux", "Uy", "Uz", "Rx", "Ry", "Rz")
                parts = [
                    dof_names[i]
                    for i, f in enumerate(node.fixities)
                    if f
                ]
                fix_str = f" [{','.join(parts)}]"
            coords = f"({node.x:.2f}, {node.y:.2f}, {node.z:.2f})"
            item = QTreeWidgetItem([
                f"N{tag}",
                f"{coords}{fix_str}",
            ])
            item.setData(0, _ROLE_TAG, tag)
            item.setData(0, _ROLE_KIND, ItemKind.NODE)
            self._root_nodes.addChild(item)

        self._root_materials = self._add_category(
            "Matériaux", f"({len(project.materials)})", ItemKind.ROOT,
        )
        for tag, mat in project.materials.items():
            item = QTreeWidgetItem([mat.name, f"{mat.grade} ({mat.material_type})"])
            item.setData(0, _ROLE_TAG, tag)
            item.setData(0, _ROLE_KIND, ItemKind.MATERIAL)
            self._root_materials.addChild(item)

        self._root_sections = self._add_category(
            "Sections", f"({len(project.sections)})", ItemKind.ROOT,
        )
        for tag, sec in project.sections.items():
            item = QTreeWidgetItem([sec.name, sec.section_type])
            item.setData(0, _ROLE_TAG, tag)
            item.setData(0, _ROLE_KIND, ItemKind.SECTION)
            self._root_sections.addChild(item)

        self._root_elements = self._add_category(
            "Éléments", f"({len(project.elements)})", ItemKind.ROOT,
        )
        for tag, elem in project.elements.items():
            sec_name = ""
            sec = project.sections.get(elem.section_tag)
            if sec:
                sec_name = f" [{sec.name}]"
            item = QTreeWidgetItem([
                f"E{tag}",
                f"N{elem.node_i} → N{elem.node_j}{sec_name}",
            ])
            item.setData(0, _ROLE_TAG, tag)
            item.setData(0, _ROLE_KIND, ItemKind.ELEMENT)
            self._root_elements.addChild(item)

        visible_surface_count = len(project.surface_elements) + len(project.plate_regions)
        self._root_surfaces = self._add_category(
            "Surfaces", f"({visible_surface_count})", ItemKind.ROOT,
        )
        for tag, plate in project.plate_regions.items():
            sec_name = ""
            sec = project.sections.get(plate.section_tag)
            if sec:
                sec_name = f" [{sec.name}]"
            mesh_nx, mesh_ny = effective_plate_mesh_divisions(project, plate)
            mesh_label = f"{mesh_nx}x{mesh_ny}"
            if getattr(plate, "mesh_mode", "") == PLATE_MESH_MODE_AUTO:
                mesh_label = f"auto {mesh_label}"
            item = QTreeWidgetItem([
                f"P{tag}",
                (
                    f"{plate.formulation} {mesh_label} - "
                    f"{', '.join(f'N{node_tag}' for node_tag in plate.corner_node_tags)}"
                    f"{sec_name}"
                ),
            ])
            item.setData(0, _ROLE_TAG, tag)
            item.setData(0, _ROLE_KIND, ItemKind.SURFACE)
            self._root_surfaces.addChild(item)
        for tag, surface in project.surface_elements.items():
            sec_name = ""
            sec = project.sections.get(surface.section_tag)
            formulation = surface.surface_type
            if sec:
                sec_name = f" [{sec.name}]"
                formulation = sec.surface_formulation or formulation
            item = QTreeWidgetItem([
                f"S{tag}",
                f"{formulation} - {', '.join(f'N{node_tag}' for node_tag in surface.node_tags)}{sec_name}",
            ])
            item.setData(0, _ROLE_TAG, tag)
            item.setData(0, _ROLE_KIND, ItemKind.SURFACE)
            self._root_surfaces.addChild(item)

        self._root_loads = self._add_category(
            "Charges", f"({len(project.loads)})", ItemKind.ROOT,
        )
        for tag, lc in project.loads.items():
            item = QTreeWidgetItem([lc.name, lc.load_type])
            item.setData(0, _ROLE_TAG, tag)
            item.setData(0, _ROLE_KIND, ItemKind.LOAD_CASE)
            self._root_loads.addChild(item)

        self._root_combos = self._add_category(
            "Combinaisons", f"({len(project.combinations)})", ItemKind.ROOT,
        )
        for tag, combo in project.combinations.items():
            item = QTreeWidgetItem([combo.name, combo.combo_type])
            item.setData(0, _ROLE_TAG, tag)
            item.setData(0, _ROLE_KIND, ItemKind.COMBINATION)
            self._root_combos.addChild(item)

        self.expandAll()
        self._apply_default_expansion()

    def _add_category(self, name: str, detail: str, kind: ItemKind) -> QTreeWidgetItem:
        """Ajoute un item racine (catégorie) à l'arbre."""
        item = QTreeWidgetItem([name, detail])
        item.setData(0, _ROLE_KIND, kind)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        self.addTopLevelItem(item)
        return item

    def _apply_default_expansion(self) -> None:
        """Replie les catégories les plus volumineuses après chaque refresh."""
        for item in (
            getattr(self, "_root_nodes", None),
            getattr(self, "_root_elements", None),
            getattr(self, "_root_surfaces", None),
            getattr(self, "_root_combos", None),
        ):
            if item is not None:
                item.setExpanded(False)

    # ── Sélection externe (depuis la vue 3D) ─────────────────────────────

    def select_node(self, tag: int) -> None:
        """Sélectionne un nœud dans l'arbre par son tag."""
        self._select_by_kind_and_tag(ItemKind.NODE, tag)

    def select_element(self, tag: int) -> None:
        """Sélectionne un élément dans l'arbre par son tag."""
        self._select_by_kind_and_tag(ItemKind.ELEMENT, tag)

    def select_surface(self, tag: int) -> None:
        """Sélectionne une surface dans l'arbre par son tag."""
        self._select_by_kind_and_tag(ItemKind.SURFACE, tag)

    def _select_by_kind_and_tag(self, kind: ItemKind, tag: int) -> None:
        """Sélectionne un item de l'arbre par type et tag."""
        it = self._find_item(kind, tag)
        if it:
            parent = it.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
            self.blockSignals(True)
            self.setCurrentItem(it)
            self.scrollToItem(it)
            self.blockSignals(False)

    def _find_item(self, kind: ItemKind, tag: int) -> QTreeWidgetItem | None:
        """Recherche un item dans l'arbre."""
        for i in range(self.topLevelItemCount()):
            root = self.topLevelItem(i)
            for j in range(root.childCount()):
                child = root.child(j)
                if (child.data(0, _ROLE_KIND) == kind
                        and child.data(0, _ROLE_TAG) == tag):
                    return child
        return None

    # ── Événements ────────────────────────────────────────────────────────

    def _on_item_changed(self, current: QTreeWidgetItem, _previous) -> None:
        """Émet le signal approprié quand la sélection change."""
        if current is None:
            return

        kind = current.data(0, _ROLE_KIND)
        tag = current.data(0, _ROLE_TAG)
        if kind is None or tag is None:
            return

        signal_map = {
            ItemKind.NODE: self.node_selected,
            ItemKind.ELEMENT: self.element_selected,
            ItemKind.SURFACE: self.surface_selected,
            ItemKind.MATERIAL: self.material_selected,
            ItemKind.SECTION: self.section_selected,
            ItemKind.LOAD_CASE: self.load_selected,
            ItemKind.COMBINATION: self.combination_selected,
        }
        signal = signal_map.get(kind)
        if signal:
            signal.emit(tag)

    def _on_context_menu(self, pos) -> None:
        """Menu contextuel pour ajouter/supprimer des objets."""
        item = self.itemAt(pos)
        menu = QMenu(self)

        if item is None:
            return

        kind = item.data(0, _ROLE_KIND)
        tag = item.data(0, _ROLE_TAG)

        if kind == ItemKind.ROOT:
            # Menu sur une catégorie racine
            text = item.text(0)
            kind_map = {
                "Nœuds": "node",
                "Matériaux": "material",
                "Sections": "section",
                "Éléments": "element",
                "Surfaces": "surface",
                "Charges": "load",
                "Combinaisons": "combination",
            }
            obj_type = kind_map.get(text)
            if obj_type:
                act_add = menu.addAction(_add_action_label(obj_type))
                act_add.triggered.connect(lambda: self.add_requested.emit(obj_type))
        elif kind in (ItemKind.NODE, ItemKind.ELEMENT, ItemKind.SURFACE, ItemKind.MATERIAL,
                      ItemKind.SECTION, ItemKind.LOAD_CASE, ItemKind.COMBINATION):
            # Menu sur un objet
            kind_str = _kind_to_str(kind)
            if kind == ItemKind.SURFACE:
                act_edit = menu.addAction(f"Modifier {item.text(0)}...")
                act_edit.triggered.connect(
                    lambda: self.edit_requested.emit(kind_str, tag)
                )
            else:
                act_del = menu.addAction(f"Supprimer {item.text(0)}")
                act_del.triggered.connect(
                    lambda: self.delete_requested.emit(kind_str, tag)
                )

        if menu.actions():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Double-clic : ouvre le dialogue d'édition pour les cas de charge."""
        if item is None:
            return
        kind = item.data(0, _ROLE_KIND)
        tag = item.data(0, _ROLE_TAG)
        if kind == ItemKind.LOAD_CASE and tag is not None:
            self.load_double_clicked.emit(tag)
        elif kind == ItemKind.SURFACE and tag is not None:
            self.edit_requested.emit("surface", tag)


def _kind_to_str(kind: ItemKind) -> str:
    """Convertit un ItemKind en chaîne pour les signaux."""
    return {
        ItemKind.NODE: "node",
        ItemKind.ELEMENT: "element",
        ItemKind.SURFACE: "surface",
        ItemKind.MATERIAL: "material",
        ItemKind.SECTION: "section",
        ItemKind.LOAD_CASE: "load",
        ItemKind.COMBINATION: "combination",
    }.get(kind, "")


def _french_name(obj_type: str) -> str:
    """Nom français pour le menu contextuel."""
    return {
        "node": "nœud",
        "element": "élément",
        "surface": "surface",
        "material": "matériau",
        "section": "section",
        "load": "cas de charge",
        "combination": "combinaison",
    }.get(obj_type, obj_type)


def _add_action_label(obj_type: str) -> str:
    """Libellé complet d'ajout pour les menus contextuels racine."""
    return {
        "node": "Ajouter un nœud...",
        "element": "Ajouter un élément...",
        "surface": "Ajouter une surface...",
        "material": "Ajouter un matériau...",
        "section": "Ajouter une section...",
        "load": "Ajouter un cas de charge...",
        "combination": "Ajouter une combinaison...",
    }.get(obj_type, f"Ajouter {_french_name(obj_type)}...")
