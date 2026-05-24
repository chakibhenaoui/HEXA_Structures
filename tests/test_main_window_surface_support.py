from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QMessageBox
from PySide6.QtGui import QAction

from core.analysis_model_builder import build_analysis_model
from core.model_data import (
    ElementData,
    LoadData,
    PlateEdgeSupportData,
    PlateSurfaceLoadData,
    ProjectModel,
    SurfaceLoad,
)
from core.solvers import SolverEngine
import gui.main_window as main_window_module
import gui.dialogs.copy_selection_dlg as copy_selection_dlg
import gui.dialogs.plate_section_dlg as plate_section_dlg
from gui.main_window import MainWindow


class _DummyTree:
    def __init__(self) -> None:
        self.selected_surface_tag: int | None = None
        self.selected_node_tag: int | None = None
        self.selected_element_tag: int | None = None

    def blockSignals(self, _blocked: bool) -> None:
        pass

    def clearSelection(self) -> None:
        pass

    def setCurrentItem(self, _item) -> None:
        pass

    def select_surface(self, tag: int) -> None:
        self.selected_surface_tag = tag

    def select_node(self, tag: int) -> None:
        self.selected_node_tag = tag

    def select_element(self, tag: int) -> None:
        self.selected_element_tag = tag


class _DummyProperties:
    def __init__(self) -> None:
        self.last_surface_tag: int | None = None
        self.last_node_tag: int | None = None
        self.last_element_tag: int | None = None

    def clear_display(self) -> None:
        pass

    def show_surface(self, tag: int) -> None:
        self.last_surface_tag = tag

    def show_node(self, tag: int) -> None:
        self.last_node_tag = tag

    def show_element(self, tag: int) -> None:
        self.last_element_tag = tag


class _DummyView:
    def __init__(self) -> None:
        self.preview_start = None
        self.last_selected_args = None

    def set_preview_start(self, point) -> None:
        self.preview_start = point

    def clear_drawing_state(self) -> None:
        self.preview_start = None

    def set_selected_objects(self, *args, **kwargs) -> None:
        self.last_selected_args = (args, kwargs)


class _DummyDock:
    def __init__(self) -> None:
        self.show_calls = 0
        self.raise_calls = 0

    def show(self) -> None:
        self.show_calls += 1

    def raise_(self) -> None:
        self.raise_calls += 1


class _FakeMenuAction:
    def __init__(self, text: str) -> None:
        self.text = text
        self.enabled = True
        self.tooltip = ""
        self.checkable = False
        self.checked = False

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 - Qt-style name
        self.enabled = bool(enabled)

    def setToolTip(self, tooltip: str) -> None:  # noqa: N802 - Qt-style name
        self.tooltip = tooltip

    def setCheckable(self, checkable: bool) -> None:  # noqa: N802 - Qt-style name
        self.checkable = bool(checkable)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt-style name
        self.checked = bool(checked)


class _FakeContextMenu:
    last: "_FakeContextMenu | None" = None
    chosen_text: str | None = None

    def __init__(self, _parent=None) -> None:
        self.actions: list[_FakeMenuAction | None] = []
        self.submenus: dict[str, _FakeContextMenu] = {}
        _FakeContextMenu.last = self

    def addAction(self, text: str) -> _FakeMenuAction:  # noqa: N802 - Qt-style name
        action = _FakeMenuAction(text)
        self.actions.append(action)
        return action

    def addMenu(self, text: str) -> "_FakeContextMenu":  # noqa: N802 - Qt-style name
        menu = _FakeContextMenu()
        menu.title = text
        self.submenus[text] = menu
        self.actions.append(_FakeMenuAction(text))
        _FakeContextMenu.last = self
        return menu

    def addSeparator(self) -> None:  # noqa: N802 - Qt-style name
        self.actions.append(None)

    def exec(self, _global_pos):  # noqa: A003 - Qt API name
        if self.chosen_text is None:
            return None
        for action in self.actions:
            if action is not None and action.text == self.chosen_text:
                return action
        return None


class _DummySolverManager:
    def __init__(self, resolved: SolverEngine) -> None:
        self.resolved = resolved

    def resolve_engine(self, _requested) -> SolverEngine:
        return self.resolved


class _DummySettings:
    class _Analysis:
        def __init__(self, solver_engine: str) -> None:
            self.solver_engine = solver_engine

    def __init__(self, solver_engine: str) -> None:
        self.analysis = self._Analysis(solver_engine)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_window_with_surface_project() -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section("HEA 200", "rectangular", 1, properties={"b": 0.20, "h": 0.20})
    project.add_section("Dalle 20 cm", "surface", 1, properties={"thickness": 0.20})
    project.add_surface_element((1, 2, 3, 4), section_tag=2)
    window.project = project
    return window


def _make_window_with_plate_project() -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    surface_section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20},
    )
    project.add_plate_region((1, 2, 3, 4), section_tag=surface_section.tag)
    window.project = project
    return window


def test_connected_surface_tags_for_node_returns_matching_surfaces() -> None:
    window = _make_window_with_surface_project()

    assert window._connected_surface_tags_for_node(1) == [1]
    assert window._connected_surface_tags_for_node(4) == [1]
    assert window._connected_surface_tags_for_node(99) == []


def test_delete_surface_elements_by_tags_removes_requested_surfaces() -> None:
    window = _make_window_with_surface_project()
    window.project.surface_loads.append(SurfaceLoad(load_tag=1, surface_tag=1, qz=-3.0))

    window._delete_surface_elements_by_tags([1])

    assert window.project.surface_elements == {}
    assert window.project.surface_loads == []


def test_delete_surface_elements_by_tags_removes_requested_plate_regions() -> None:
    window = _make_window_with_plate_project()
    window.project.loads[1] = LoadData(tag=1, name="G", load_type="permanent")
    window.project.plate_surface_loads.append(
        PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-3.0)
    )
    window.project.plate_edge_supports.append(
        PlateEdgeSupportData(plate_tag=1, edge="12", fixities=(1, 1, 1, 0, 0, 0))
    )

    window._delete_surface_elements_by_tags([1])

    assert window.project.plate_regions == {}
    assert window.project.plate_surface_loads == []
    assert window.project.plate_edge_supports == []


def test_delete_selected_objects_removes_connected_surfaces(monkeypatch) -> None:
    window = _make_window_with_surface_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = None
    window.secondary_view = None

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    window._delete_selected_objects([1], [])

    assert 1 not in window.project.nodes
    assert window.project.surface_elements == {}
    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert any("surface" in message.lower() for message in logs)


def test_delete_selected_objects_removes_connected_plate_regions(monkeypatch) -> None:
    window = _make_window_with_plate_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = None
    window.secondary_view = None

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    window._delete_selected_objects([1], [])

    assert 1 not in window.project.nodes
    assert window.project.plate_regions == {}
    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert any("surface" in message.lower() for message in logs)


def test_delete_selected_objects_removes_explicit_surface_selection(monkeypatch) -> None:
    window = _make_window_with_surface_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = _DummyView()

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    window._delete_selected_objects([], [], [1])

    assert window.project.surface_elements == {}
    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert any("surface" in message.lower() for message in logs)


def test_delete_selected_objects_removes_explicit_plate_selection(monkeypatch) -> None:
    window = _make_window_with_plate_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = _DummyView()

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    window._delete_selected_objects([], [], [1])

    assert window.project.plate_regions == {}
    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert any("surface" in message.lower() for message in logs)


def test_delete_surface_from_menu_removes_plate_region(monkeypatch) -> None:
    window = _make_window_with_plate_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = _DummyView()

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    window._delete_surface_from_menu(1)

    assert window.project.plate_regions == {}
    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert any("plaque p1" in message.lower() for message in logs)


def test_line_section_items_and_draw_combo_exclude_surface_sections() -> None:
    _app()
    window = _make_window_with_surface_project()
    window.combo_draw_section = QComboBox()

    line_sections = window._line_section_items()
    window._refresh_draw_section_controls()

    assert [tag for tag, _sec in line_sections] == [1]
    assert window.combo_draw_section.count() == 1
    assert window.combo_draw_section.itemData(0) == 1
    assert window._default_draw_section_tag() == 1


def test_delete_section_from_menu_blocks_surface_used_section(monkeypatch) -> None:
    window = _make_window_with_surface_project()
    window.properties = _DummyProperties()
    warnings: list[str] = []

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(str(args[2])) or QMessageBox.Ok,
    )

    window._delete_section_from_menu(2)

    assert 2 in window.project.sections
    assert any("surface" in message.lower() for message in warnings)


def test_add_surface_from_selection_creates_surface_and_selects_it() -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section("Dalle 20 cm", "surface", 1, properties={"thickness": 0.20})
    window.project = project
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = None
    window.secondary_view = None
    window._selected_node_tags = [1, 2, 3, 4]
    window._selected_element_tags = []

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []
    refresh_menu_calls: list[bool] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)
    window._refresh_model_management_menus = lambda: refresh_menu_calls.append(True)

    window._add_surface()

    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert refresh_menu_calls == [True]
    assert window.project.surface_elements == {}
    assert 1 in window.project.plate_regions
    assert window.project.plate_regions[1].corner_node_tags == (1, 2, 3, 4)
    assert window.project.plate_regions[1].mesh_nx == 8
    assert window.project.plate_regions[1].mesh_ny == 8
    assert window.project.plate_regions[1].mesh_mode == "auto"
    assert window.tree.selected_surface_tag == 1
    assert window.properties.last_surface_tag == 1
    assert any("Plaque P1" in message for message in logs)


def test_analysis_mesh_diagnostic_logs_generated_bar_segments() -> None:
    window = MainWindow.__new__(MainWindow)
    logs: list[str] = []
    window._log = lambda message: logs.append(message)
    window._all_results = {
        "G (cas 1)": {
            "result_context": {
                "generated_bar_count": 1,
                "generated_bar_segment_count": 4,
            }
        }
    }

    window._log_analysis_mesh_diagnostic()

    assert logs == [
        "Maillage d'analyse : 1 barre(s) coplanaire(s) integree(s) "
        "en 4 segment(s) interne(s)."
    ]


def test_add_user_plate_region_rejects_line_section(monkeypatch) -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Acier S235", "steel", "S235")
    line_section = project.add_section(
        "IPE 100",
        "I_profile",
        1,
        properties={"h": 0.10, "b": 0.055, "tw": 0.0041, "tf": 0.0057},
    )
    window.project = project

    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(str(args[2])) or QMessageBox.Ok,
    )

    plate = window._add_user_plate_region((1, 2, 3, 4), line_section.tag, "XY")

    assert plate is None
    assert project.plate_regions == {}
    assert any("section plaque" in message.lower() for message in warnings)


def test_surface_section_compatibility_reports_macro_plate_line_section() -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Acier S235", "steel", "S235")
    line_section = project.add_section(
        "IPE 100",
        "I_profile",
        1,
        properties={"h": 0.10, "b": 0.055, "tw": 0.0041, "tf": 0.0057},
    )
    surface_section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    plate = project.add_plate_region((1, 2, 3, 4), surface_section.tag)
    plate.section_tag = line_section.tag
    window.project = project

    issues = window._surface_section_compatibility_issues()

    assert len(issues) == 1
    assert issues[0][0] == plate.tag
    assert "section plaque" in issues[0][1].lower()


def test_run_analysis_blocks_invalid_macro_plate_before_backend(monkeypatch) -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.nodes[1].fixities = (1, 1, 1, 1, 1, 1)
    project.add_material("Acier S235", "steel", "S235")
    line_section = project.add_section(
        "IPE 100",
        "I_profile",
        1,
        properties={"h": 0.10, "b": 0.055, "tw": 0.0041, "tf": 0.0057},
    )
    surface_section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    plate = project.add_plate_region((1, 2, 3, 4), surface_section.tag)
    plate.section_tag = line_section.tag
    project.loads[1] = LoadData(tag=1, name="Poids propre", load_type="dead")
    project.plate_surface_loads.append(PlateSurfaceLoadData(load_tag=1, plate_tag=1, qz=-1.0))
    window.project = project
    window._surface_features_enabled = lambda: True
    window._surface_features_disabled_reason = lambda: ""

    warnings: list[str] = []
    logs: list[str] = []
    selections: list[int] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(str(args[2])) or QMessageBox.Ok,
    )
    window._log = lambda message: logs.append(message)
    window._select_surface_after_change = lambda tag: selections.append(tag)

    window._run_analysis()

    assert any("section plaque" in message.lower() for message in warnings)
    assert any("configuration plaques" in message.lower() for message in logs)
    assert selections == [plate.tag]


def test_run_analysis_blocks_bar_using_surface_section_before_backend(monkeypatch) -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(0.0, 0.0, 3.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    surface_section = project.add_section(
        "DALLE",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.elements[1] = ElementData(
        tag=1,
        node_i=1,
        node_j=2,
        section_tag=surface_section.tag,
    )
    project.loads[1] = LoadData(tag=1, name="Poids propre", load_type="self_weight")
    window.project = project
    window._surface_features_enabled = lambda: True
    window._surface_features_disabled_reason = lambda: ""

    warnings: list[str] = []
    logs: list[str] = []
    selections: list[int] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(str(args[2])) or QMessageBox.Ok,
    )
    window._log = lambda message: logs.append(message)
    window._select_element_for_context = lambda tag: selections.append(tag)

    window._run_analysis()

    assert any("section plaque" in message.lower() for message in warnings)
    assert any("configuration barres" in message.lower() for message in logs)
    assert selections == [1]


def test_edit_surface_selects_surface_and_opens_properties() -> None:
    window = _make_window_with_surface_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = _DummyView()
    window.dock_properties = _DummyDock()
    window._selected_surface_tags = [1]

    refresh_menu_calls: list[bool] = []
    logs: list[str] = []
    window._refresh_model_management_menus = lambda: refresh_menu_calls.append(True)
    window._log = lambda message: logs.append(message)

    window._edit_surface(1)

    assert window.tree.selected_surface_tag == 1
    assert window.properties.last_surface_tag == 1
    assert window.dock_properties.show_calls == 1
    assert window.dock_properties.raise_calls == 1
    assert refresh_menu_calls
    assert any("prête à être modifiée" in message for message in logs)


def test_view_surface_selection_syncs_tree_properties_and_views() -> None:
    window = _make_window_with_surface_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = _DummyView()
    refresh_menu_calls: list[bool] = []
    logs: list[str] = []

    window._refresh_model_management_menus = lambda: refresh_menu_calls.append(True)
    window._log = lambda message: logs.append(message)

    window._on_view_selection_changed([], [], [1])

    assert window._selected_surface_tags == [1]
    assert window.tree.selected_surface_tag == 1
    assert window.properties.last_surface_tag == 1
    assert window.model_view.last_selected_args == (([], [], [1]), {"emit_signal": False})
    assert window.secondary_view.last_selected_args == (([], [], [1]), {"emit_signal": False})
    assert refresh_menu_calls
    assert logs == []


def test_surface_context_menu_lists_expected_actions(monkeypatch) -> None:
    _app()
    window = _make_window_with_surface_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window._all_results = {}
    window._selected_node_tags = []
    window._selected_element_tags = []
    window._selected_surface_tags = []
    window._refresh_model_management_menus = lambda: None

    _FakeContextMenu.chosen_text = None
    monkeypatch.setattr(main_window_module, "QMenu", _FakeContextMenu)

    window._show_surface_context_menu(1, QPoint(12, 24))

    menu = _FakeContextMenu.last
    assert menu is not None
    actions = [action for action in menu.actions if action is not None]
    assert [action.text for action in actions] == [
        "Modifier",
        "Supprimer",
        "Copier",
        "Afficher diagrammes",
        "Plaque",
        "Propriétés",
    ]
    assert actions[3].enabled is False
    assert "analyse" in actions[3].tooltip.lower()
    plate_menu = menu.submenus["Plaque"]
    plate_actions = [action for action in plate_menu.actions if action is not None]
    assert [action.text for action in plate_actions] == [
        "Maillage automatique",
        "Nombre de mailles...",
        "Maillage retenu : 1 x 1",
        "Integrer une barre diagonale...",
        "Creer un noeud a l'intersection...",
        "Decouper une barre traversante...",
        "Maillage non structure...",
    ]
    assert plate_actions[0].enabled is False
    assert plate_actions[1].enabled is False
    assert all(action.enabled is False for action in plate_actions[2:])
    assert window._selected_surface_tags == [1]
    assert window.tree.selected_surface_tag == 1
    assert window.properties.last_surface_tag == 1
    assert window.model_view.last_selected_args == (([], [], [1]), {"emit_signal": False})


def test_macro_plate_context_menu_exposes_mesh_choice_and_disabled_future_actions(monkeypatch) -> None:
    _app()
    window = _make_window_with_plate_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window._all_results = {}
    window._selected_node_tags = []
    window._selected_element_tags = []
    window._selected_surface_tags = []
    window._refresh_model_management_menus = lambda: None

    _FakeContextMenu.chosen_text = None
    monkeypatch.setattr(main_window_module, "QMenu", _FakeContextMenu)

    window._show_surface_context_menu(1, QPoint(12, 24))

    menu = _FakeContextMenu.last
    assert menu is not None
    actions = [action for action in menu.actions if action is not None]
    assert "Plaque macro" in [action.text for action in actions]
    macro_menu = menu.submenus["Plaque macro"]
    macro_actions = [action for action in macro_menu.actions if action is not None]

    assert [action.text for action in macro_actions] == [
        "Maillage automatique",
        "Nombre de mailles...",
        "Maillage retenu : 20 x 16",
        "Integrer une barre diagonale...",
        "Creer un noeud a l'intersection...",
        "Decouper une barre traversante...",
        "Maillage non structure...",
    ]
    assert macro_actions[0].enabled is True
    assert macro_actions[1].enabled is True
    assert macro_actions[2].enabled is False
    assert all(action.enabled is False for action in macro_actions[3:])
    assert all(action.tooltip == "Fonction a venir." for action in macro_actions[3:])


def test_surface_context_menu_copy_uses_clicked_surface(monkeypatch) -> None:
    _app()
    window = _make_window_with_surface_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window._all_results = {}
    window._selected_node_tags = []
    window._selected_element_tags = []
    window._selected_surface_tags = []
    window._refresh_model_management_menus = lambda: None

    copy_calls: list[list[int]] = []
    window._copy_selected_objects = lambda: copy_calls.append(list(window._selected_surface_tags))

    _FakeContextMenu.chosen_text = "Copier"
    monkeypatch.setattr(main_window_module, "QMenu", _FakeContextMenu)

    window._show_surface_context_menu(1, QPoint(12, 24))

    assert copy_calls == [[1]]


def test_surface_context_menu_diagrams_targets_clicked_surface(monkeypatch) -> None:
    _app()
    window = _make_window_with_surface_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window._all_results = {"LC1": {"surface_results": {1: object()}}}
    window._selected_node_tags = []
    window._selected_element_tags = []
    window._selected_surface_tags = []
    window._refresh_model_management_menus = lambda: None

    diagram_calls: list[dict] = []

    def _show_surface_result_map(**kwargs) -> None:
        diagram_calls.append(kwargs)

    window._show_surface_result_map = _show_surface_result_map

    _FakeContextMenu.chosen_text = "Afficher diagrammes"
    monkeypatch.setattr(main_window_module, "QMenu", _FakeContextMenu)

    window._show_surface_context_menu(1, QPoint(12, 24))

    assert diagram_calls == [{"surface_tag": 1}]


def test_plate_mesh_auto_context_action_updates_macro_plate() -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 5.0, 0.0)
    project.add_node(0.0, 5.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    plate = project.add_plate_region(
        (1, 2, 3, 4),
        section.tag,
        mesh_nx=4,
        mesh_ny=4,
    )
    window.project = project
    window.properties = _DummyProperties()
    mark_calls: list[bool] = []
    refresh_calls: list[bool] = []
    logs: list[str] = []
    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)

    window._set_plate_mesh_auto(plate.tag)

    assert plate.mesh_mode == "auto"
    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert window.properties.last_surface_tag == plate.tag
    assert any("16 x 16" in message for message in logs)


def test_plate_mesh_user_context_action_prompts_for_divisions(monkeypatch) -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 5.0, 0.0)
    project.add_node(0.0, 5.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    plate = project.add_plate_region((1, 2, 3, 4), section.tag)
    window.project = project
    window.properties = _DummyProperties()
    window._mark_project_modified = lambda: None
    window._refresh = lambda preserve_view=False: None
    window._log = lambda message: None
    dialog_calls: list[dict[str, int]] = []

    class _AcceptedMeshDialog:
        def __init__(self, _parent=None, **kwargs) -> None:
            dialog_calls.append(dict(kwargs))

        def exec(self) -> int:
            return QDialog.Accepted

        def values(self) -> tuple[int, int]:
            return 12, 10

    monkeypatch.setattr(main_window_module, "PlateMeshDialog", _AcceptedMeshDialog)

    window._set_plate_mesh_user_from_menu(plate.tag)

    assert dialog_calls == [{"mesh_nx": 8, "mesh_ny": 8, "plate_tag": plate.tag}]
    assert plate.mesh_mode == "user"
    assert plate.mesh_nx == 12
    assert plate.mesh_ny == 10
    assert window.properties.last_surface_tag == plate.tag


def test_macro_plate_properties_opens_dedicated_dialog(monkeypatch) -> None:
    window = _make_window_with_plate_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window._selected_node_tags = []
    window._selected_element_tags = []
    window._selected_surface_tags = []
    window._current_case = None
    window._all_results = {}
    window._refresh_model_management_menus = lambda: None
    dialog_calls: list[dict[str, object]] = []

    class _FakePlateRegionPropertiesDialog:
        def __init__(self, parent, project, tag, **kwargs) -> None:
            dialog_calls.append(
                {
                    "parent": parent,
                    "project": project,
                    "tag": tag,
                    **kwargs,
                }
            )

        def exec(self) -> int:
            return QDialog.Accepted

    monkeypatch.setattr(
        main_window_module,
        "PlateRegionPropertiesDialog",
        _FakePlateRegionPropertiesDialog,
    )

    window._show_surface_properties(1)

    assert len(dialog_calls) == 1
    assert dialog_calls[0]["parent"] is window
    assert dialog_calls[0]["project"] is window.project
    assert dialog_calls[0]["tag"] == 1


def test_surface_result_support_uses_analysis_model_for_macro_plate() -> None:
    pytest.importorskip("matplotlib")
    _app()
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(2.0, 0.0, 0.0)
    project.add_node(2.0, 2.0, 0.0)
    project.add_node(0.0, 2.0, 0.0)
    project.add_material("Beton C30", "concrete", "C30/37")
    section = project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    project.add_plate_region((1, 2, 3, 4), section.tag, mesh_nx=2, mesh_ny=2)
    analysis_project = build_analysis_model(project)
    mesh = getattr(analysis_project, "generated_plate_meshes")[1]

    window.project = project
    window._runner = None
    window._current_case = "LC1"
    window._all_results = {
        "LC1": {
            "surface_results": {tag: object() for tag in mesh.surface_tags},
            "analysis_project": analysis_project,
        }
    }
    window._surface_result_support_reason = ""

    assert project.surface_elements == {}
    assert window._surface_result_support_is_available() is True



def test_draw_surface_from_points_creates_surface_after_fourth_pick() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    window.project = project
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window.act_draw_surface = QAction("Dessiner une surface", None)
    window.act_draw_orthogonal = QAction("Trace orthogonale", None)
    window.act_draw_orthogonal.setCheckable(True)
    window.act_draw_orthogonal.setChecked(True)
    window._draw_mode_kind = "surface"
    window._draw_surface_points = []
    window._draw_surface_section_tag = 1
    window._draw_start_point = None
    window._surface_draw_saved_orthogonal_state = None
    window._selected_node_tags = []
    window._selected_element_tags = []

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []
    refresh_menu_calls: list[bool] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)
    window._refresh_model_management_menus = lambda: refresh_menu_calls.append(True)

    for point in (
        (0.0, 0.0, 0.0),
        (5.0, 0.0, 0.0),
        (5.0, 4.0, 0.0),
        (-2.0, 3.5, 0.0),
    ):
        window._on_grid_point_picked(*point)

    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert refresh_menu_calls
    assert len(project.nodes) == 4
    assert project.surface_elements == {}
    assert 1 in project.plate_regions
    assert project.plate_regions[1].corner_node_tags == (1, 2, 3, 4)
    assert project.plate_regions[1].formulation == "ShellMITC4"
    assert window._draw_surface_points == []
    assert window._draw_start_point is None
    assert any("Plaque P1" in message for message in logs)


def test_draw_surface_accepts_inclined_coplanar_quad() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section(
        "Dalle inclinée",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    window.project = project
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window.act_draw_surface = QAction("Dessiner une surface", None)
    window.act_draw_orthogonal = QAction("Trace orthogonale", None)
    window.act_draw_orthogonal.setCheckable(True)
    window.act_draw_orthogonal.setChecked(False)
    window._draw_mode_kind = "surface"
    window._draw_surface_points = []
    window._draw_surface_section_tag = 1
    window._draw_start_point = None
    window._surface_draw_saved_orthogonal_state = None
    window._selected_node_tags = []
    window._selected_element_tags = []

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []
    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)
    window._refresh_model_management_menus = lambda: None

    for point in (
        (0.0, 0.0, 0.0),
        (4.0, 0.0, 1.0),
        (4.0, 3.0, 2.0),
        (0.0, 3.0, 1.0),
    ):
        window._on_grid_point_picked(*point)

    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert project.surface_elements == {}
    assert 1 in project.plate_regions
    assert project.plate_regions[1].corner_node_tags == (1, 2, 3, 4)
    assert window._surface_plane_for_node_tags((1, 2, 3, 4)) == "3D"
    assert any("Plaque P1" in message for message in logs)


def test_surface_right_click_finalize_creates_surface_from_pending_points() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    window.project = project
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window.act_draw_surface = QAction("Dessiner une surface", None)
    window.act_draw_orthogonal = QAction("Trace orthogonale", None)
    window.act_draw_orthogonal.setCheckable(True)
    window.act_draw_orthogonal.setChecked(True)
    window._draw_mode_kind = "surface"
    window._draw_surface_points = [
        (0.0, 0.0, 0.0),
        (5.0, 0.0, 0.0),
        (5.0, 4.0, 0.0),
    ]
    window._draw_surface_section_tag = 1
    window._draw_start_point = (5.0, 4.0, 0.0)
    window._surface_draw_saved_orthogonal_state = None
    window._selected_node_tags = []
    window._selected_element_tags = []

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []
    refresh_menu_calls: list[bool] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)
    window._refresh_model_management_menus = lambda: refresh_menu_calls.append(True)

    window._on_surface_draw_finalize_requested()

    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert refresh_menu_calls
    assert project.surface_elements == {}
    assert 1 in project.plate_regions
    assert project.plate_regions[1].corner_node_tags == (1, 2, 3, 4)
    assert window._draw_surface_points == []
    assert any("Plaque P1" in message for message in logs)


def test_surface_right_click_resets_partial_contour_before_third_point() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    window.project = ProjectModel()
    window.model_view = _DummyView()
    window.secondary_view = None
    window._draw_mode_kind = "surface"
    window._draw_surface_points = [
        (0.0, 0.0, 0.0),
        (5.0, 0.0, 0.0),
    ]
    window._draw_surface_section_tag = 1
    window._draw_start_point = (5.0, 0.0, 0.0)

    logs: list[str] = []
    refresh_menu_calls: list[bool] = []

    window._log = lambda message: logs.append(message)
    window._refresh_model_management_menus = lambda: refresh_menu_calls.append(True)

    window._on_draw_finalize_requested()

    assert window._draw_surface_points == []
    assert window._draw_start_point is None
    assert window.model_view.preview_start is None
    assert refresh_menu_calls == [True]
    assert window.project.surface_elements == {}
    assert any("plaque" in message.lower() and "annule" in message.lower() for message in logs)


def test_surface_right_click_finalize_requires_expected_point_count() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    window.project = project
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window.act_draw_surface = QAction("Dessiner une surface", None)
    window.act_draw_orthogonal = QAction("Trace orthogonale", None)
    window.act_draw_orthogonal.setCheckable(True)
    window.act_draw_orthogonal.setChecked(True)
    window._draw_mode_kind = "surface"
    window._draw_surface_points = [
        (0.0, 0.0, 0.0),
        (5.0, 0.0, 0.0),
        (8.0, 0.0, 0.0),
    ]
    window._draw_surface_section_tag = 1
    window._draw_start_point = (8.0, 0.0, 0.0)
    window._surface_draw_saved_orthogonal_state = None
    window._selected_node_tags = []
    window._selected_element_tags = []

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)
    window._refresh_model_management_menus = lambda: None

    window._on_surface_draw_finalize_requested()

    assert mark_calls == []
    assert refresh_calls == []
    assert project.surface_elements == {}
    assert any("définir un plan" in message for message in logs)


def test_toggle_draw_surface_keeps_orthogonal_mode_available() -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.grid.enabled = True
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section(
        "Dalle 20 cm",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "ShellMITC4"},
    )
    window.project = project
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window.act_draw_surface = QAction("Dessiner une surface", None)
    window.act_draw_surface.setCheckable(True)
    window.act_draw_surface.setChecked(True)
    window.act_draw_orthogonal = QAction("Trace orthogonale", None)
    window.act_draw_orthogonal.setCheckable(True)
    window.act_draw_orthogonal.setChecked(False)
    window.act_draw_node = QAction("Dessiner un nœud", None)
    window.act_draw_node.setCheckable(True)
    window.act_draw_bars = QAction("Dessiner une barre", None)
    window.act_draw_bars.setCheckable(True)
    window.act_select_tool = QAction("Sélection", None)
    window.act_select_tool.setCheckable(True)
    window.act_select_tool.setChecked(True)
    window._draw_surface_points = []
    window._draw_surface_section_tag = None
    window._draw_start_point = None
    window._draw_mode_kind = None
    window._surface_draw_saved_orthogonal_state = None

    logs: list[str] = []
    selection_states: list[bool] = []
    interactive_states: list[bool] = []

    window._ensure_surface_features_available = lambda: True
    window._choose_surface_section_tag = lambda: 1
    window._ensure_work_plane_for_drawing = lambda: None
    window._set_selection_mode_enabled = lambda enabled: selection_states.append(enabled)
    window._set_interactive_drawing_enabled = lambda enabled: interactive_states.append(enabled)
    window._refresh_model_management_menus = lambda: None
    window._log = lambda message: logs.append(message)

    window._toggle_draw_surface(True)

    assert window._draw_mode_kind == "surface"
    assert window.act_draw_orthogonal.isChecked() is False
    assert window.act_draw_orthogonal.isEnabled() is True
    assert selection_states[-1] is False
    assert interactive_states[-1] is True

    window._toggle_draw_surface(False)

    assert window._draw_mode_kind is None
    assert window.act_draw_orthogonal.isChecked() is False
    assert window.act_draw_orthogonal.isEnabled() is True
    assert selection_states[-1] is True
    assert interactive_states[-1] is False
    assert any("plan incliné" in message.lower() for message in logs)


def test_toggle_draw_surface_rejects_tri31_sections(monkeypatch) -> None:
    _app()
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.grid.enabled = True
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section(
        "Plaque triangulaire",
        "surface",
        1,
        properties={"thickness": 0.20, "element_formulation": "Tri31"},
    )
    window.project = project
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = None
    window.act_draw_surface = QAction("Dessiner une surface", None)
    window.act_draw_surface.setCheckable(True)
    window.act_draw_surface.setChecked(True)
    window.act_draw_orthogonal = QAction("Trace orthogonale", None)
    window.act_draw_orthogonal.setCheckable(True)
    window.act_draw_orthogonal.setChecked(False)
    window.act_draw_node = QAction("Dessiner un nœud", None)
    window.act_draw_node.setCheckable(True)
    window.act_draw_bars = QAction("Dessiner une barre", None)
    window.act_draw_bars.setCheckable(True)
    window.act_select_tool = QAction("Sélection", None)
    window.act_select_tool.setCheckable(True)
    window._draw_surface_points = []
    window._draw_surface_section_tag = None
    window._draw_start_point = None
    window._draw_mode_kind = None
    window._surface_draw_saved_orthogonal_state = None

    infos: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, text, *_args, **_kwargs: infos.append(text),
    )

    window._ensure_surface_features_available = lambda: True
    window._choose_surface_section_tag = lambda: 1
    window._ensure_work_plane_for_drawing = lambda: None
    window._set_selection_mode_enabled = lambda _enabled: None
    window._set_interactive_drawing_enabled = lambda _enabled: None
    window._refresh_model_management_menus = lambda: None
    window._log = lambda _message: None

    window._toggle_draw_surface(True)

    assert window._draw_mode_kind is None
    assert window.act_draw_surface.isChecked() is False
    assert window.act_draw_orthogonal.isChecked() is False
    assert any("quadrangulaires" in message for message in infos)


def test_copy_selected_surfaces_copies_geometry_and_selects_new_surface(monkeypatch) -> None:
    _app()
    window = _make_window_with_surface_project()
    window.tree = _DummyTree()
    window.properties = _DummyProperties()
    window.model_view = _DummyView()
    window.secondary_view = _DummyView()
    window._selected_node_tags = []
    window._selected_element_tags = []
    window._selected_surface_tags = [1]
    window.project.surface_loads.append(SurfaceLoad(load_tag=1, surface_tag=1, qz=-2.5))

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []
    logs: list[str] = []
    dialog_args: dict[str, int] = {}

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: logs.append(message)
    window._refresh_model_management_menus = lambda: None

    class _AcceptedCopyDialog:
        PICK_ORIGIN_CODE = 2

        def __init__(self, parent=None, **kwargs) -> None:
            dialog_args["node_count"] = kwargs["node_count"]
            dialog_args["element_count"] = kwargs["element_count"]
            dialog_args["surface_count"] = kwargs["surface_count"]
            self._values = dict(kwargs["initial_values"])
            self._values.update({"mode": "delta", "dx": 10.0, "dy": 0.0, "dz": 0.0, "copies": 1})

        def exec(self) -> int:
            return QDialog.Accepted

        def values(self) -> dict[str, float | int | str]:
            return dict(self._values)

    monkeypatch.setattr(copy_selection_dlg, "CopySelectionDialog", _AcceptedCopyDialog)

    window._copy_selected_objects()

    assert dialog_args == {"node_count": 4, "element_count": 0, "surface_count": 1}
    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert 2 in window.project.surface_elements
    copied_surface = window.project.surface_elements[2]
    copied_points = {
        (
            round(window.project.nodes[node_tag].x, 3),
            round(window.project.nodes[node_tag].y, 3),
            round(window.project.nodes[node_tag].z, 3),
        )
        for node_tag in copied_surface.node_tags
    }
    assert copied_points == {
        (10.0, 0.0, 0.0),
        (15.0, 0.0, 0.0),
        (15.0, 4.0, 0.0),
        (10.0, 4.0, 0.0),
    }
    copied_surface_loads = [
        load for load in window.project.surface_loads if load.surface_tag == 2
    ]
    assert len(copied_surface_loads) == 1
    assert copied_surface_loads[0].qz == -2.5
    assert window.tree.selected_surface_tag == 2


def test_add_plate_section_skips_scene_refresh(monkeypatch) -> None:
    _app()
    window = _make_window_with_surface_project()

    refresh_calls: list[tuple[bool, bool]] = []
    mark_calls: list[bool] = []
    logs: list[str] = []

    window._ensure_surface_features_available = lambda: True
    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = (
        lambda preserve_view=False, refresh_scene=True: refresh_calls.append(
            (preserve_view, refresh_scene)
        )
    )
    window._log = lambda message: logs.append(message)

    class _AcceptedPlateDialog:
        Accepted = QDialog.Accepted

        def __init__(self, parent=None, *, materials=None, **_kwargs) -> None:
            self._materials = dict(materials or {})

        def exec(self) -> int:
            return QDialog.Accepted

        def result(self) -> dict[str, object]:
            return {
                "name": "Dalle RDC",
                "section_type": "surface",
                "material_tag": 1,
                "area": 0.0,
                "inertia_y": 0.0,
                "inertia_z": 0.0,
                "properties": {
                    "thickness": 0.22,
                    "element_formulation": "ShellMITC4",
                },
            }

        def result_materials(self) -> dict[int, object]:
            return dict(self._materials)

    monkeypatch.setattr(plate_section_dlg, "PlateSectionDialog", _AcceptedPlateDialog)

    window._add_plate_section()

    assert mark_calls == [True]
    assert refresh_calls == [(True, False)]
    assert any(sec.name == "Dalle RDC" for sec in window.project.sections.values())
    assert any("Section plaque" in message for message in logs)


def test_refresh_model_management_menus_disables_plate_actions_with_pynite() -> None:
    _app()
    window = _make_window_with_surface_project()
    window._solver_manager = _DummySolverManager(SolverEngine.PYNITE)
    window.settings = _DummySettings("pynite")
    window.properties = _DummyProperties()
    window.act_manage_materials = QAction("Matériaux...", None)
    window.act_manage_sections = QAction("Sections...", None)
    window.act_manage_plate_sections = QAction("Sections plaque...", None)
    window.act_add_surface = QAction("Ajouter une surface", None)
    window.act_add_plate_section = QAction("Nouvelle section plaque...", None)
    window.act_draw_surface = QAction("Dessiner une surface", None)
    window.act_copy_selection = QAction("Copier", None)
    window.act_cancel_draw = QAction("Annuler dessin", None)
    window._draw_start_point = None
    window._draw_surface_points = []
    window._selected_existing_node_tags = lambda: [1, 2, 3, 4]
    window._selected_existing_element_tags = lambda: []

    window._refresh_model_management_menus()

    assert window.act_add_surface.isEnabled() is False
    assert window.act_add_plate_section.isEnabled() is False
    assert window.act_manage_plate_sections.isEnabled() is False
    assert window.act_draw_surface.isEnabled() is False
    assert "OpenSeesPy" in window.act_add_surface.toolTip()


def test_add_surface_is_blocked_with_pynite(monkeypatch) -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_node(5.0, 4.0, 0.0)
    project.add_node(0.0, 4.0, 0.0)
    project.add_material("Béton C30", "concrete", "C30/37")
    project.add_section("Dalle 20 cm", "surface", 1, properties={"thickness": 0.20})
    window.project = project
    window._solver_manager = _DummySolverManager(SolverEngine.PYNITE)
    window.settings = _DummySettings("pynite")
    window._selected_existing_node_tags = lambda: [1, 2, 3, 4]

    infos: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: infos.append(str(args[2])) or QMessageBox.Ok,
    )

    window._add_surface()

    assert project.surface_elements == {}
    assert infos
    assert "OpenSeesPy" in infos[0]
