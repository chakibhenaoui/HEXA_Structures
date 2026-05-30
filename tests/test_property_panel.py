from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.model_data import ProjectModel
from gui.widgets.property_panel import PropertyPanel


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _project_with_element() -> ProjectModel:
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_material("Acier S235", "steel", "S235")
    project.add_section(
        "HEA 200",
        "rectangular",
        1,
        area=0.02,
        inertia_y=1e-4,
        inertia_z=1e-4,
    )
    project.add_element(1, 2, section_tag=1)
    return project


def test_property_panel_detaches_previous_form_immediately() -> None:
    _app()
    panel = PropertyPanel()
    panel.set_project(_project_with_element())

    panel.show_element(1)
    first_group = panel._layout.itemAt(1).widget()

    panel.show_element(1)
    second_group = panel._layout.itemAt(1).widget()

    assert panel._layout.count() == 2
    assert first_group is not second_group
    assert first_group.parent() is None


def test_property_panel_updates_element_roll_angle() -> None:
    _app()
    project = _project_with_element()
    panel = PropertyPanel()
    panel.set_project(project)

    panel.show_element(1)
    panel._spin_roll_angle.setValue(45.0)
    panel._apply_element()

    assert project.elements[1].roll_angle_deg == 45.0
    assert project.elements[1].section_tag == 1


def test_property_panel_element_fields_stay_compact() -> None:
    _app()
    panel = PropertyPanel()
    panel.set_project(_project_with_element())

    panel.show_element(1)

    assert panel.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert panel._combo_elem_type.maximumWidth() <= 170
    assert panel._combo_section.maximumWidth() <= 170
    assert panel._spin_roll_angle.maximumWidth() <= 120
