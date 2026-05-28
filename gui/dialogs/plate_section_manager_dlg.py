"""Plate section manager dialog."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
)

from core.model_data import MaterialData, SectionData
from gui.dialogs.plate_section_dlg import PlateSectionDialog


class PlateSectionManagerDialog(QDialog):
    """Plate section manager dialog."""

    def __init__(
        self,
        parent=None,
        *,
        sections: dict[int, SectionData] | None = None,
        materials: dict[int, MaterialData] | None = None,
        used_section_tags: set[int] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Définir les sections plaque"))
        self.resize(820, 520)

        self._sections = {
            tag: deepcopy(sec)
            for tag, sec in (sections or {}).items()
            if sec.is_surface
        }
        self._reserved_section_tags = set((sections or {}).keys())
        self._materials = deepcopy(materials or {})
        self._used_section_tags = set(used_section_tags or set())

        self._build_ui()
        self.retranslate_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        self.grp_list = QGroupBox(self.tr("Sections plaque"), self)
        grp_list_lay = QVBoxLayout(self.grp_list)
        self.list_items = QListWidget(self.grp_list)
        self.list_items.itemDoubleClicked.connect(lambda _item: self._edit_section())
        grp_list_lay.addWidget(self.list_items)
        content.addWidget(self.grp_list, 1)

        self.grp_actions = QGroupBox(self.tr("Cliquer pour :"), self)
        grp_actions_lay = QVBoxLayout(self.grp_actions)

        self.btn_add = QPushButton(self.tr("Ajouter section plaque..."), self.grp_actions)
        self.btn_add.clicked.connect(self._add_section)
        grp_actions_lay.addWidget(self.btn_add)

        self.btn_copy = QPushButton(self.tr("Ajouter copie de plaque..."), self.grp_actions)
        self.btn_copy.clicked.connect(self._copy_section)
        grp_actions_lay.addWidget(self.btn_copy)

        self.btn_edit = QPushButton(self.tr("Modifier / Voir plaque..."), self.grp_actions)
        self.btn_edit.clicked.connect(self._edit_section)
        grp_actions_lay.addWidget(self.btn_edit)

        self.btn_delete = QPushButton(self.tr("Supprimer section plaque"), self.grp_actions)
        self.btn_delete.clicked.connect(self._delete_section)
        grp_actions_lay.addWidget(self.btn_delete)

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
        self.setWindowTitle(self.tr("Définir les sections plaque"))
        self.grp_list.setTitle(self.tr("Sections plaque"))
        self.grp_actions.setTitle(self.tr("Cliquer pour :"))
        self.btn_add.setText(self.tr("Ajouter section plaque..."))
        self.btn_copy.setText(self.tr("Ajouter copie de plaque..."))
        self.btn_edit.setText(self.tr("Modifier / Voir plaque..."))
        self.btn_delete.setText(self.tr("Supprimer section plaque"))

    def _refresh_list(self) -> None:
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
        self.btn_add.setEnabled(True)
        self.btn_copy.setEnabled(has_items)
        self.btn_edit.setEnabled(has_items)
        self.btn_delete.setEnabled(has_items)

    def _section_summary(self, sec: SectionData) -> str:
        material = self._materials.get(sec.material_tag)
        material_name = material.name if material is not None else f"Mat T{sec.material_tag}"
        return (
            f"{sec.name}\n"
            f"{sec.surface_formulation} - {material_name} - e={sec.thickness*100:.1f} cm"
        )

    def current_tag(self) -> int | None:
        item = self.list_items.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _next_tag(self) -> int:
        used_tags = self._reserved_section_tags | set(self._sections.keys())
        return max(used_tags, default=0) + 1

    def _open_dialog(
        self,
        *,
        name: str = "",
        material_tag: int | None = None,
        properties: dict | None = None,
    ) -> tuple[dict[str, object] | None, dict[int, MaterialData] | None]:
        dlg = PlateSectionDialog(
            self,
            materials=self._materials,
            name=name,
            material_tag=material_tag,
            properties=properties,
        )
        if dlg.exec() != PlateSectionDialog.Accepted:
            return None, None
        return dlg.result(), dlg.result_materials()

    def _add_section(self) -> None:
        data, materials = self._open_dialog()
        if data is None or materials is None:
            return

        self._materials = materials
        tag = self._next_tag()
        self._sections[tag] = SectionData(
            tag=tag,
            name=str(data["name"]),
            section_type="surface",
            material_tag=int(data["material_tag"]),
            properties=dict(data.get("properties", {})),
            area=0.0,
            inertia_y=0.0,
            inertia_z=0.0,
        )
        self._refresh_list()

    def _copy_section(self) -> None:
        tag = self.current_tag()
        if tag is None:
            return
        source = self._sections[tag]
        data, materials = self._open_dialog(
            name=f"{source.name} - Copie",
            material_tag=source.material_tag,
            properties=source.properties,
        )
        if data is None or materials is None:
            return

        self._materials = materials
        new_tag = self._next_tag()
        self._sections[new_tag] = SectionData(
            tag=new_tag,
            name=str(data["name"]),
            section_type="surface",
            material_tag=int(data["material_tag"]),
            properties=dict(data.get("properties", {})),
            area=0.0,
            inertia_y=0.0,
            inertia_z=0.0,
        )
        self._refresh_list()

    def _edit_section(self) -> None:
        tag = self.current_tag()
        if tag is None:
            return
        sec = self._sections[tag]
        data, materials = self._open_dialog(
            name=sec.name,
            material_tag=sec.material_tag,
            properties=sec.properties,
        )
        if data is None or materials is None:
            return

        self._materials = materials
        sec.name = str(data["name"])
        sec.material_tag = int(data["material_tag"])
        sec.properties = dict(data.get("properties", {}))
        sec.area = 0.0
        sec.inertia_y = 0.0
        sec.inertia_z = 0.0
        self._refresh_list()

    def _delete_section(self) -> None:
        tag = self.current_tag()
        if tag is None:
            return

        sec = self._sections[tag]
        if tag in self._used_section_tags:
            QMessageBox.warning(
                self,
                self.tr("Suppression impossible"),
                self.tr("Cette section plaque est encore utilisée par une ou plusieurs surfaces."),
            )
            return

        reply = QMessageBox.question(
            self,
            self.tr("Confirmer la suppression"),
            self.tr("Supprimer la section plaque « {name} » ?").format(name=sec.name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        del self._sections[tag]
        self._refresh_list()

    def result_sections(self) -> dict[int, SectionData]:
        return deepcopy(self._sections)

    def result_materials(self) -> dict[int, MaterialData]:
        return deepcopy(self._materials)
