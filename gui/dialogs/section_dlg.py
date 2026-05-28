"""Section creation and editing dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from core.sections import (
    RectangularSection,
    TSection,
    get_profile,
    list_profiles,
)
from gui.dialogs import load_dialog_ui


_SECTION_TYPE_KEYS = ("rectangular", "T", "I_profile", "surface")

_PROFILE_FAMILIES = ["IPE", "HEA", "HEB"]


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
        self._refresh_type_labels()
        self._update_summary()

    def _section_type_label(self, section_type: str) -> str:
        labels = {
            "rectangular": self.tr("Rectangulaire"),
            "T": self.tr("Section en T"),
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

    def _populate_combos(self) -> None:
        """Populate type and material combo boxes."""
        for key in self._allowed_types:
            if key not in _SECTION_TYPE_KEYS:
                continue
            self._combo_type.addItem(self._section_type_label(key), key)

        for tag, mat in self._materials.items():
            self._combo_material.addItem(f"{mat.name} ({mat.grade})", tag)
        if not self._materials:
            self._combo_material.addItem(self.tr("(aucun matériau)"), 0)

    def _connect_signals(self) -> None:
        """Wire up all signals."""
        self._combo_type.currentIndexChanged.connect(self._on_type_changed)
        self._combo_family.currentIndexChanged.connect(self._on_family_changed)
        self._combo_profile.currentIndexChanged.connect(self._on_profile_changed)
        self._spin_b.valueChanged.connect(self._update_summary)
        self._spin_h.valueChanged.connect(self._update_summary)
        self._spin_bw.valueChanged.connect(self._update_summary)
        self._spin_hw.valueChanged.connect(self._update_summary)
        self._spin_bf.valueChanged.connect(self._update_summary)
        self._spin_hf.valueChanged.connect(self._update_summary)
        self._spin_thickness.valueChanged.connect(self._update_summary)

        self.ui.buttonBox.accepted.connect(self._validate)
        self.ui.buttonBox.rejected.connect(self.reject)

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
        elif sec_type == "I_profile":
            profile_name = str(props.get("profile", "")).strip()
            if profile_name:
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
        self._update_summary()

    # ── Slots ──────────────────────────────────────────────────────

    def _on_type_changed(self) -> None:
        """Handle type changed."""
        sec_type = self._combo_type.currentData()
        page_map = {"rectangular": 0, "T": 1, "I_profile": 2, "surface": 3}
        self._stack.setCurrentIndex(page_map.get(sec_type, 0))

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

    def _validate(self) -> None:
        """Handle validate."""
        name = self._edit_name.text().strip()
        if not name:
            self._edit_name.setFocus()
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
