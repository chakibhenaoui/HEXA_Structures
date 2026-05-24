from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.model_data import ProjectModel
from gui.dialogs.plate_mesh_dlg import PlateMeshDialog
from gui.dialogs.plate_region_properties_dlg import PlateRegionPropertiesDialog


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _plate_project() -> ProjectModel:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_plate_region((1, 2, 3, 4), section_tag=section.tag)
    return project


def test_plate_mesh_dialog_returns_both_divisions() -> None:
    _app()
    dialog = PlateMeshDialog(None, mesh_nx=6, mesh_ny=4, plate_tag=1)

    dialog.spin_nx.setValue(12)
    dialog.spin_ny.setValue(10)

    assert dialog.values() == (12, 10)


def test_plate_region_properties_dialog_opens_for_macro_plate() -> None:
    _app()
    project = _plate_project()

    dialog = PlateRegionPropertiesDialog(None, project, 1)

    assert dialog.windowTitle().startswith("Proprietes de la plaque macro P1")
    assert dialog.tabs.count() == 4
