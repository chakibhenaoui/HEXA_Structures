from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.model_data import LoadData, ProjectModel
from gui.dialogs.load_dlg import LoadEntryDialog


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _project_with_load_targets() -> ProjectModel:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(4.0, 0.0, 0.0)
    project.add_node(4.0, 3.0, 0.0)
    project.add_node(0.0, 3.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    beam_section = project.add_section(
        "Poutre 30x50",
        "rectangular",
        1,
        area=0.15,
        inertia_y=0.003125,
        inertia_z=0.001125,
    )
    surface_section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_element(1, 2, section_tag=beam_section.tag)
    project.add_surface_element((1, 2, 3, 4), section_tag=surface_section.tag)
    project.loads[1] = LoadData(tag=1, name="Q", load_type="variable")
    return project


def _project_with_macro_plate_target() -> ProjectModel:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(4.0, 0.0, 0.0)
    project.add_node(4.0, 3.0, 0.0)
    project.add_node(0.0, 3.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_plate_region((1, 2, 3, 4), section_tag=section.tag)
    project.loads[1] = LoadData(tag=1, name="Q", load_type="variable")
    return project


def test_load_entry_dialog_uses_tabs_for_load_families() -> None:
    _app()
    dialog = LoadEntryDialog(None, project=_project_with_load_targets(), load_tag=1)

    try:
        assert [
            dialog._tabs.tabText(index)
            for index in range(dialog._tabs.count())
        ] == ["Nodales", "Éléments", "Surfaciques"]
        assert dialog._tabs.widget(0) is dialog._tab_nodal
        assert dialog._tabs.widget(1) is dialog._tab_elem
        assert dialog._tabs.widget(2) is dialog._tab_surface
    finally:
        dialog.deleteLater()


def test_load_entry_dialog_selection_only_opens_surface_tab() -> None:
    _app()
    dialog = LoadEntryDialog(
        None,
        project=_project_with_load_targets(),
        load_tag=1,
        selected_surface_tags=[1],
        selection_only=True,
    )

    try:
        assert dialog._tabs.isTabEnabled(0) is False
        assert dialog._tabs.isTabEnabled(1) is False
        assert dialog._tabs.isTabEnabled(2) is True
        assert dialog._tabs.currentIndex() == 2
    finally:
        dialog.deleteLater()


def test_load_entry_dialog_selection_only_accepts_macro_plate_surface_load() -> None:
    _app()
    project = _project_with_macro_plate_target()
    dialog = LoadEntryDialog(
        None,
        project=project,
        load_tag=1,
        selected_surface_tags=[1],
        selection_only=True,
    )

    try:
        assert dialog._tabs.isTabEnabled(2) is True
        assert dialog._tabs.currentIndex() == 2
        dialog._spn_qz.setValue(-2.5)
        dialog._add_surface_load()
        dialog._on_accept()

        assert project.surface_loads == []
        assert len(project.plate_surface_loads) == 1
        assert project.plate_surface_loads[0].plate_tag == 1
        assert project.plate_surface_loads[0].qz == -2.5
    finally:
        dialog.deleteLater()
