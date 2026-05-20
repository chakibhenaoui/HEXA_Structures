from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.model_data import LoadData, ProjectModel, SurfaceLoad
from core.results import NodalResult, SurfaceResult
from gui.dialogs.surface_properties_dlg import SurfacePropertiesDialog


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _surface_project() -> ProjectModel:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(4.0, 0.0, 1.0)
    project.add_node(4.0, 3.0, 1.4)
    project.add_node(0.0, 3.0, 0.2)
    project.add_material("Béton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_surface_element((1, 2, 3, 4), section_tag=section.tag)
    project.loads[1] = LoadData(tag=1, name="Exploitation", load_type="live")
    project.surface_loads.append(SurfaceLoad(load_tag=1, surface_tag=1, qz=-2.5))
    return project


def test_surface_properties_dialog_shows_expected_tabs() -> None:
    _app()
    project = _surface_project()
    gauss = tuple(
        (1.0, 2.0, 0.1, 4.0, 5.0, 0.2, 0.3, 0.4)
        for _ in range(4)
    )
    dialog = SurfacePropertiesDialog(
        None,
        project,
        1,
        case_name="LC1",
        case_results={
            "surface_results": {1: SurfaceResult(tag=1, gauss_resultants=gauss)},
            "displacements": {
                1: NodalResult(tag=1, ux=0.001),
                2: NodalResult(tag=2, uz=-0.002),
            },
        },
    )

    tabs = [
        dialog.tabs.tabText(index)
        for index in range(dialog.tabs.count())
    ]

    assert tabs == [
        "Géométrie",
        "Propriétés",
        "Charges",
        "NTM",
        "Déplacements",
        "Vérification",
    ]
    assert "S1" in dialog.windowTitle()
