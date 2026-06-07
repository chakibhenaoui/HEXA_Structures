"""Material and section library manager dialogs."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.material_properties import build_material_properties, isotropic_material_properties
from core.model_data import MaterialData, SectionData
from gui.dialogs.material_dlg import MaterialDialog
from gui.dialogs.section_dlg import SectionDialog


class MaterialManagerDialog(QDialog):
    """Material manager dialog."""

    def __init__(
        self,
        parent=None,
        *,
        materials: dict[int, MaterialData] | None = None,
        sections: dict[int, SectionData] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Définir les matériaux"))
        self.resize(760, 500)

        self._materials = deepcopy(materials or {})
        self._sections = deepcopy(sections or {})

        self._build_ui()
        self.retranslate_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        """Build UI."""
        root = QVBoxLayout(self)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        self.grp_list = QGroupBox(self.tr("Matériaux"), self)
        grp_list_lay = QVBoxLayout(self.grp_list)
        self.list_items = QListWidget(self.grp_list)
        self.list_items.itemDoubleClicked.connect(
            lambda _item: self._modify_material()
        )
        grp_list_lay.addWidget(self.list_items)
        content.addWidget(self.grp_list, 1)

        self.grp_actions = QGroupBox(self.tr("Cliquer pour :"), self)
        grp_actions_lay = QVBoxLayout(self.grp_actions)

        self.btn_add_quick = QPushButton(self.tr("Ajouter matériau rapide..."), self.grp_actions)
        self.btn_add_quick.clicked.connect(self._add_material_quick)
        grp_actions_lay.addWidget(self.btn_add_quick)

        self.btn_add = QPushButton(self.tr("Ajouter matériau..."), self.grp_actions)
        self.btn_add.clicked.connect(self._add_material)
        grp_actions_lay.addWidget(self.btn_add)

        self.btn_copy = QPushButton(self.tr("Ajouter copie du matériau..."), self.grp_actions)
        self.btn_copy.clicked.connect(self._copy_material)
        grp_actions_lay.addWidget(self.btn_copy)

        self.btn_edit = QPushButton(self.tr("Modifier / Voir matériau..."), self.grp_actions)
        self.btn_edit.clicked.connect(self._modify_material)
        grp_actions_lay.addWidget(self.btn_edit)

        self.btn_delete = QPushButton(self.tr("Supprimer matériau"), self.grp_actions)
        self.btn_delete.clicked.connect(self._delete_material)
        grp_actions_lay.addWidget(self.btn_delete)

        self.chk_advanced = QCheckBox(self.tr("Afficher les propriétés avancées"), self.grp_actions)
        self.chk_advanced.setEnabled(False)
        grp_actions_lay.addSpacing(8)
        grp_actions_lay.addWidget(self.chk_advanced)
        grp_actions_lay.addStretch(1)

        content.addWidget(self.grp_actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def retranslate_ui(self) -> None:
        """Refresh persistent labels after a language change."""
        self.setWindowTitle(self.tr("Définir les matériaux"))
        self.grp_list.setTitle(self.tr("Matériaux"))
        self.grp_actions.setTitle(self.tr("Cliquer pour :"))
        self.btn_add_quick.setText(self.tr("Ajouter matériau rapide..."))
        self.btn_add.setText(self.tr("Ajouter matériau..."))
        self.btn_copy.setText(self.tr("Ajouter copie du matériau..."))
        self.btn_edit.setText(self.tr("Modifier / Voir matériau..."))
        self.btn_delete.setText(self.tr("Supprimer matériau"))
        self.chk_advanced.setText(self.tr("Afficher les propriétés avancées"))

    def _refresh_list(self) -> None:
        """Refresh list."""
        current_tag = self.current_tag()

        self.list_items.clear()
        for tag, mat in sorted(self._materials.items()):
            props = isotropic_material_properties(mat.material_type, mat.grade, mat.properties)
            item = QListWidgetItem(
                f"{mat.name}\n"
                f"{mat.grade} ({mat.material_type})\n"
                f"E={props['young_modulus']:.0f} kPa  |  gamma={props['unit_weight']:.2f} kN/m3"
            )
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

        has_items = bool(self._materials)
        self.btn_copy.setEnabled(has_items)
        self.btn_edit.setEnabled(has_items)
        self.btn_delete.setEnabled(has_items)

    def current_tag(self) -> int | None:
        """Return tag."""
        item = self.list_items.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _next_tag(self) -> int:
        """Return the next tag."""
        return max(self._materials.keys(), default=0) + 1

    def _add_material_quick(self) -> None:
        """Add material quick."""
        tag = self._next_tag()
        self._materials[tag] = MaterialData(
            tag=tag,
            name=f"Béton C30/37 {tag}",
            material_type="concrete",
            grade="C30/37",
            properties=build_material_properties(
                **isotropic_material_properties("concrete", "C30/37", {}),
            ),
        )
        self._refresh_list()

    def _add_material(self) -> None:
        """Add material."""
        dlg = MaterialDialog(self)
        if dlg.exec() != MaterialDialog.Accepted:
            return

        data = dlg.result()
        tag = self._next_tag()
        self._materials[tag] = MaterialData(
            tag=tag,
            name=data["name"],
            material_type=data["material_type"],
            grade=data["grade"],
            properties=data["properties"],
        )
        self._refresh_list()

    def _copy_material(self) -> None:
        """Copy material."""
        tag = self.current_tag()
        if tag is None:
            return
        source = self._materials[tag]

        dlg = MaterialDialog(
            self,
            name=f"{source.name} - Copie",
            material_type=source.material_type,
            grade=source.grade,
            properties=source.properties,
        )
        if dlg.exec() != MaterialDialog.Accepted:
            return

        data = dlg.result()
        new_tag = self._next_tag()
        self._materials[new_tag] = MaterialData(
            tag=new_tag,
            name=data["name"],
            material_type=data["material_type"],
            grade=data["grade"],
            properties=data["properties"],
        )
        self._refresh_list()

    def _modify_material(self) -> None:
        """Handle modify material."""
        tag = self.current_tag()
        if tag is None:
            return

        mat = self._materials[tag]
        dlg = MaterialDialog(
            self,
            name=mat.name,
            material_type=mat.material_type,
            grade=mat.grade,
            properties=mat.properties,
        )
        if dlg.exec() != MaterialDialog.Accepted:
            return

        data = dlg.result()
        mat.name = data["name"]
        mat.material_type = data["material_type"]
        mat.grade = data["grade"]
        mat.properties = data["properties"]
        self._refresh_list()

    def _delete_material(self) -> None:
        """Delete material."""
        tag = self.current_tag()
        if tag is None:
            return

        mat = self._materials[tag]
        used_by = [
            sec.tag for sec in self._sections.values()
            if sec.material_tag == tag
        ]
        if used_by:
            QMessageBox.warning(
                self,
                self.tr("Suppression impossible"),
                self.tr("Ce matériau est encore utilisé par une ou plusieurs sections."),
            )
            return

        reply = QMessageBox.question(
            self,
            self.tr("Confirmer la suppression"),
            self.tr("Supprimer le matériau « {name} » ?").format(name=mat.name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        del self._materials[tag]
        self._refresh_list()

    def result_materials(self) -> dict[int, MaterialData]:
        """Return materials."""
        return deepcopy(self._materials)


class SectionManagerDialog(QDialog):
    """Section manager dialog."""

    def __init__(
        self,
        parent=None,
        *,
        sections: dict[int, SectionData] | None = None,
        materials: dict[int, MaterialData] | None = None,
        element_section_tags: set[int] | None = None,
        allowed_types: list[str] | tuple[str, ...] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Définir les sections"))
        self.resize(820, 520)

        self._sections = deepcopy(sections or {})
        self._materials = deepcopy(materials or {})
        self._element_section_tags = set(element_section_tags or set())
        self._allowed_types = tuple(
            allowed_types or (*SectionDialog.line_section_types(), "surface")
        )

        self._build_ui()
        self.retranslate_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        """Build UI."""
        root = QVBoxLayout(self)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        self.grp_list = QGroupBox(self.tr("Sections"), self)
        grp_list_lay = QVBoxLayout(self.grp_list)
        self.list_items = QListWidget(self.grp_list)
        self.list_items.itemDoubleClicked.connect(
            lambda _item: self._modify_section()
        )
        grp_list_lay.addWidget(self.list_items)
        content.addWidget(self.grp_list, 1)

        self.grp_actions = QGroupBox(self.tr("Cliquer pour :"), self)
        grp_actions_lay = QVBoxLayout(self.grp_actions)

        self.btn_add = QPushButton(self.tr("Ajouter section..."), self.grp_actions)
        self.btn_add.clicked.connect(self._add_section)
        grp_actions_lay.addWidget(self.btn_add)

        self.btn_copy = QPushButton(self.tr("Ajouter copie de section..."), self.grp_actions)
        self.btn_copy.clicked.connect(self._copy_section)
        grp_actions_lay.addWidget(self.btn_copy)

        self.btn_edit = QPushButton(self.tr("Modifier / Voir section..."), self.grp_actions)
        self.btn_edit.clicked.connect(self._modify_section)
        grp_actions_lay.addWidget(self.btn_edit)

        self.btn_delete = QPushButton(self.tr("Supprimer section"), self.grp_actions)
        self.btn_delete.clicked.connect(self._delete_section)
        grp_actions_lay.addWidget(self.btn_delete)

        self.chk_advanced = QCheckBox(self.tr("Afficher les propriétés avancées"), self.grp_actions)
        self.chk_advanced.setEnabled(False)
        grp_actions_lay.addSpacing(8)
        grp_actions_lay.addWidget(self.chk_advanced)
        grp_actions_lay.addStretch(1)

        content.addWidget(self.grp_actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def retranslate_ui(self) -> None:
        """Refresh persistent labels after a language change."""
        self.setWindowTitle(self.tr("Définir les sections"))
        self.grp_list.setTitle(self.tr("Sections"))
        self.grp_actions.setTitle(self.tr("Cliquer pour :"))
        self.btn_add.setText(self.tr("Ajouter section..."))
        self.btn_copy.setText(self.tr("Ajouter copie de section..."))
        self.btn_edit.setText(self.tr("Modifier / Voir section..."))
        self.btn_delete.setText(self.tr("Supprimer section"))
        self.chk_advanced.setText(self.tr("Afficher les propriétés avancées"))

    def _refresh_list(self) -> None:
        """Refresh list."""
        current_tag = self.current_tag()

        self.list_items.clear()
        for tag, sec in sorted(self._sections.items()):
            item = QListWidgetItem(self._section_summary(sec))
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

        has_items = bool(self._sections)
        has_materials = bool(self._materials)
        self.btn_add.setEnabled(has_materials)
        self.btn_copy.setEnabled(has_items)
        self.btn_edit.setEnabled(has_items)
        self.btn_delete.setEnabled(has_items)

    def _section_summary(self, sec: SectionData) -> str:
        """Handle section summary."""
        material = self._materials.get(sec.material_tag)
        material_name = material.name if material is not None else f"Mat T{sec.material_tag}"
        if sec.is_surface:
            return (
                f"{sec.name}\n"
                f"surface - {material_name} - e={sec.thickness*100:.1f} cm"
            )
        return f"{sec.name}\n{sec.section_type} - {material_name}"

    def current_tag(self) -> int | None:
        """Return tag."""
        item = self.list_items.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _next_tag(self) -> int:
        """Return the next tag."""
        return max(self._sections.keys(), default=0) + 1

    def _add_section(self) -> None:
        """Add section."""
        dlg = SectionDialog(
            self,
            materials=self._materials,
            allowed_types=self._allowed_types,
        )
        if dlg.exec() != SectionDialog.Accepted:
            return

        data = dlg.result()
        tag = self._next_tag()
        self._sections[tag] = SectionData(
            tag=tag,
            name=data["name"],
            section_type=data["section_type"],
            material_tag=data["material_tag"],
            properties=data.get("properties", {}),
            area=data.get("area", 0.0),
            inertia_y=data.get("inertia_y", 0.0),
            inertia_z=data.get("inertia_z", 0.0),
        )
        self._refresh_list()

    def _copy_section(self) -> None:
        """Copy section."""
        tag = self.current_tag()
        if tag is None:
            return
        source = self._sections[tag]

        if source.section_type == "sectionproperties":
            from gui.dialogs.section_builder_dlg import SectionBuilderDialog

            dlg = SectionBuilderDialog(
                self,
                materials=self._materials,
                name=f"{source.name} - Copie",
                material_tag=source.material_tag,
                properties=source.properties,
            )
        else:
            dlg = SectionDialog(
                self,
                materials=self._materials,
                name=f"{source.name} - Copie",
                section_type=source.section_type,
                material_tag=source.material_tag,
                properties=source.properties,
                allowed_types=self._allowed_types,
            )
        if dlg.exec() != SectionDialog.Accepted:
            return

        data = dlg.result()
        if not data:
            return
        new_tag = self._next_tag()
        self._sections[new_tag] = SectionData(
            tag=new_tag,
            name=data["name"],
            section_type=data["section_type"],
            material_tag=data["material_tag"],
            properties=data.get("properties", {}),
            area=data.get("area", 0.0),
            inertia_y=data.get("inertia_y", 0.0),
            inertia_z=data.get("inertia_z", 0.0),
        )
        self._refresh_list()

    def _modify_section(self) -> None:
        """Handle modify section."""
        tag = self.current_tag()
        if tag is None:
            return

        sec = self._sections[tag]
        if sec.section_type == "sectionproperties":
            from gui.dialogs.section_builder_dlg import SectionBuilderDialog

            dlg = SectionBuilderDialog(
                self,
                materials=self._materials,
                name=sec.name,
                material_tag=sec.material_tag,
                properties=sec.properties,
            )
        else:
            dlg = SectionDialog(
                self,
                materials=self._materials,
                name=sec.name,
                section_type=sec.section_type,
                material_tag=sec.material_tag,
                properties=sec.properties,
                allowed_types=self._allowed_types,
            )
        if dlg.exec() != SectionDialog.Accepted:
            return

        data = dlg.result()
        if not data:
            return
        sec.name = data["name"]
        sec.section_type = data["section_type"]
        sec.material_tag = data["material_tag"]
        sec.properties = data.get("properties", {})
        sec.area = data.get("area", 0.0)
        sec.inertia_y = data.get("inertia_y", 0.0)
        sec.inertia_z = data.get("inertia_z", 0.0)
        self._refresh_list()

    def _delete_section(self) -> None:
        """Delete section."""
        tag = self.current_tag()
        if tag is None:
            return

        sec = self._sections[tag]
        if tag in self._element_section_tags:
            QMessageBox.warning(
                self,
                self.tr("Suppression impossible"),
                self.tr(
                    "Cette section est encore utilisée par un ou plusieurs éléments ou surfaces."
                ),
            )
            return

        reply = QMessageBox.question(
            self,
            self.tr("Confirmer la suppression"),
            self.tr("Supprimer la section « {name} » ?").format(name=sec.name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        del self._sections[tag]
        self._refresh_list()

    def result_sections(self) -> dict[int, SectionData]:
        """Return sections."""
        return deepcopy(self._sections)
