from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.model_data import LoadData, ProjectModel
from gui.main_window import MainWindow


class _AcceptedLoadEntryDialog:
    Accepted = 1

    def __init__(self, *args, **kwargs) -> None:
        pass

    def exec(self) -> int:
        return self.Accepted


class _AcceptedLoadCaseManagerDialog:
    Accepted = 1

    def __init__(self, *args, project: ProjectModel, **kwargs) -> None:
        self._project = project

    def exec(self) -> int:
        return self.Accepted

    def result_loads(self):
        return self._project.loads

    def result_nodal_loads(self):
        return self._project.nodal_loads

    def result_element_loads(self):
        return self._project.element_loads

    def result_surface_loads(self):
        return self._project.surface_loads

    def result_plate_surface_loads(self):
        return self._project.plate_surface_loads

    def result_combinations(self):
        return self._project.combinations

    def switch_to_combinations_requested(self) -> bool:
        return False


class _DummyModelView:
    def __init__(self) -> None:
        self.isometric_called = False
        self.model_calls: list[bool] = []
        self.deformed_calls: list[float] = []
        self.selection_modes: list[bool] = []
        self.drawing_modes: list[bool] = []
        self.preview_start = None

    def set_view_isometric(self) -> None:
        self.isometric_called = True

    def capture_view_state(self):
        return {"camera": "dummy"}

    def restore_view_state(self, _state) -> None:
        pass

    def display_model(self, _project, preserve_camera: bool = False) -> None:
        self.model_calls.append(preserve_camera)

    def display_deformed(
        self,
        _project,
        _displacements,
        scale: float = 10.0,
        preserve_camera: bool = False,
    ) -> None:
        _ = preserve_camera
        self.deformed_calls.append(scale)

    def set_selection_mode(self, enabled: bool) -> None:
        self.selection_modes.append(enabled)

    def set_drawing_mode(self, enabled: bool) -> None:
        self.drawing_modes.append(enabled)

    def set_preview_start(self, point) -> None:
        self.preview_start = point


class _DummySettings:
    class _Gui:
        show_node_tags = True
        show_section_names = False
        show_grid = True
        show_extruded_sections = False
        show_local_axes = False

    def __init__(self) -> None:
        self.gui = self._Gui()


class _Disp:
    def __init__(self, ux: float = 0.0, uy: float = 0.0, uz: float = 0.0) -> None:
        self.ux = ux
        self.uy = uy
        self.uz = uz


class _DummyToggleAction:
    def __init__(self) -> None:
        self._checked = False

    def setCheckable(self, _checkable: bool) -> None:
        pass

    def setChecked(self, checked: bool) -> None:
        self._checked = bool(checked)

    def isChecked(self) -> bool:
        return self._checked


class _RefreshTarget:
    def __init__(self) -> None:
        self.calls = 0

    def refresh(self, _project) -> None:
        self.calls += 1


class _DummyRunAction:
    def __init__(self) -> None:
        self.enabled = None
        self.tooltip = ""
        self.status_tip = ""

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def setToolTip(self, text: str) -> None:
        self.tooltip = text

    def setStatusTip(self, text: str) -> None:
        self.status_tip = text

    def text(self) -> str:
        return "Analyser"


def test_assign_loads_to_selection_preserves_view(monkeypatch) -> None:
    from gui.dialogs import load_dlg

    monkeypatch.setattr(load_dlg, "LoadEntryDialog", _AcceptedLoadEntryDialog)

    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.loads[1] = LoadData(tag=1, name="Q", load_type="variable")
    window.project = project

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []

    window._selected_existing_node_tags = lambda: [1]
    window._selected_existing_element_tags = lambda: []
    window._choose_editable_load_case = lambda title, prompt: 1
    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: None

    window._assign_loads_to_selection()

    assert mark_calls == [True]
    assert refresh_calls == [True]


def test_manage_loads_and_combinations_preserves_view(monkeypatch) -> None:
    from gui.dialogs import load_dlg

    monkeypatch.setattr(load_dlg, "LoadCaseManagerDialog", _AcceptedLoadCaseManagerDialog)

    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.loads[1] = LoadData(tag=1, name="Q", load_type="variable")
    window.project = project

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []

    window._selected_existing_node_tags = lambda: []
    window._selected_existing_element_tags = lambda: []
    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._log = lambda message: None

    window._manage_loads_and_combinations(start_page="loads")

    assert mark_calls == [True]
    assert refresh_calls == [True]


def test_property_panel_model_change_preserves_view() -> None:
    window = MainWindow.__new__(MainWindow)

    refresh_calls: list[bool] = []
    mark_calls: list[bool] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)

    window._on_model_changed()

    assert mark_calls == [True]
    assert refresh_calls == [True]


def test_refresh_skips_scene_when_only_loads_change() -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0, fixities=(1, 1, 1, 1, 1, 1))
    project.add_node(5.0, 0.0, 0.0)
    project.add_material("Acier S235", "steel", "S235")
    project.add_section(
        "HEA 200",
        "rectangular",
        1,
        properties={"b": 0.20, "h": 0.30},
        area=0.06,
        inertia_y=1e-4,
        inertia_z=1e-4,
    )
    project.add_element(1, 2, section_tag=1)
    window.project = project
    window.settings = _DummySettings()
    window.model_view = _DummyModelView()
    window.secondary_view = None
    window.tree = _RefreshTarget()
    window.node_table = _RefreshTarget()
    window.combo_table = _RefreshTarget()
    window._active_parallel_plane = "3D"
    window._active_parallel_value = None
    window._secondary_parallel_plane = "3D"
    window._secondary_parallel_value = None
    window._last_scene_signature = None
    window._deformed_visible = False
    window._current_case = None
    window._all_results = {}
    window._selection_mode_active = True
    window._draw_mode_kind = None
    window._draw_start_point = None
    window.act_run = _DummyRunAction()
    window._refresh_model_management_menus = lambda: None
    window._refresh_diagram_actions = lambda: None
    window._refresh_draw_section_controls = lambda: None
    window._refresh_parallel_view_controls = lambda apply_view=True: None
    window._record_history_snapshot_if_needed = lambda: None
    window._sync_modified_with_saved_state = lambda: None
    window._update_history_actions = lambda: None
    window._update_statusbar = lambda: None
    window._update_title = lambda: None
    window._refresh_load_diagram_if_open = lambda: None
    window._refresh_element_diagram_if_open = lambda: None
    window._surface_features_enabled = lambda: True
    window._interactive_drawing_enabled = lambda: False

    window._refresh(preserve_view=True)
    assert window.model_view.model_calls == [True]

    project.loads[1] = LoadData(tag=1, name="Q", load_type="live")
    window._refresh(preserve_view=True)

    assert window.model_view.model_calls == [True]


def test_mark_project_modified_invalidates_existing_results() -> None:
    window = MainWindow.__new__(MainWindow)
    window._all_results = {"G": {"displacements": {}}}

    clear_calls: list[bool] = []
    log_messages: list[str] = []

    window._clear_results_state = lambda: clear_calls.append(True)
    window._log = lambda message: log_messages.append(message)

    window._mark_project_modified()

    assert window._modified is True
    assert window._pending_project_change is True
    assert clear_calls == [True]
    assert log_messages


def test_plan_view_change_does_not_trigger_refresh() -> None:
    window = MainWindow.__new__(MainWindow)

    plane_calls: list[str] = []
    refresh_calls: list[bool] = []

    window._set_primary_view_plane = lambda plane: plane_calls.append(plane)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)

    window._on_view_xy()

    assert plane_calls == ["XY"]
    assert refresh_calls == []


def test_isometric_view_change_does_not_trigger_refresh() -> None:
    window = MainWindow.__new__(MainWindow)
    window.model_view = _DummyModelView()

    plane_calls: list[str] = []
    refresh_calls: list[bool] = []

    window._set_primary_view_plane = lambda plane: plane_calls.append(plane)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)

    window._on_view_iso()

    assert plane_calls == ["3D"]
    assert window.model_view.isometric_called is False
    assert refresh_calls == []


def test_deformed_toggle_can_restore_initial_model_view() -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_section("HEA 200", "rectangular", 1, area=0.02, inertia_y=1e-4, inertia_z=1e-4)
    project.add_material("Acier S235", "steel", "S235")
    project.elements[1] = project.add_element(1, 2, section_tag=1)
    window.project = project
    window.model_view = _DummyModelView()
    window.secondary_view = None
    window.settings = _DummySettings()
    window._selection_mode_active = True
    window._draw_mode_kind = None
    window._draw_start_point = None
    window._current_case = "LC1"
    window._all_results = {
        "LC1": {
            "displacements": {
                1: _Disp(0.0, 0.0, 0.0),
                2: _Disp(0.01, 0.0, 0.0),
            }
        }
    }
    window._deformed_visible = False
    window.act_res_deformed = _DummyToggleAction()
    window._refresh_deformed_action = lambda: None
    window._interactive_drawing_enabled = lambda: False
    window._apply_parallel_view = lambda refresh_scene=False: None
    window._log = lambda _message: None

    window.act_res_deformed.setChecked(True)
    window._show_deformed_menu()
    assert window.model_view.deformed_calls
    assert window._deformed_visible is True

    window.act_res_deformed.setChecked(False)
    window._show_deformed_menu()
    assert window.model_view.model_calls == [True]
    assert window._deformed_visible is False


def test_single_element_diagram_file_info_is_limited_to_requested_bar() -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 3.0)
    project.add_node(10.0, 2.0, 3.0)
    project.add_material("Acier S235", "steel", "S235")
    project.add_section(
        "HEA 200",
        "rectangular",
        1,
        area=0.02,
        inertia_y=1e-4,
        inertia_z=1e-4,
    )
    first = project.add_element(1, 2, section_tag=1)
    project.add_element(2, 3, section_tag=1)
    window.project = project

    info = window._single_element_diagram_file_info(first.tag)

    assert info is not None
    assert info["ele_tags"] == [first.tag]
    assert info["local_element"] is True
    assert info["element_tag"] == first.tag
    assert info["plane"] is None
    assert info["axis"] is None
    assert info["value"] is None


def test_element_diagram_menu_requires_existing_results() -> None:
    window = MainWindow.__new__(MainWindow)
    project = ProjectModel()
    project.add_node(0.0, 0.0, 0.0)
    project.add_node(5.0, 0.0, 0.0)
    project.add_section(
        "HEA 200",
        "rectangular",
        1,
        area=0.02,
        inertia_y=1e-4,
        inertia_z=1e-4,
    )
    element = project.add_element(1, 2, section_tag=1)
    window.project = project
    window._all_results = {}

    assert window._element_diagram_available(element.tag) is False

    window._all_results = {"LC1": {"element_forces": {}}}

    assert window._element_diagram_available(element.tag) is True


def test_element_properties_dialog_adds_result_tabs_only_after_analysis() -> None:
    from PySide6.QtWidgets import QApplication

    from core.results import ElementResult, NodalResult
    from gui.dialogs.element_properties_dlg import ElementPropertiesDialog

    app = QApplication.instance() or QApplication([])
    _ = app
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
    element = project.add_element(1, 2, section_tag=1)

    without_results = ElementPropertiesDialog(None, project, element.tag)
    tabs_without = [
        without_results.tabs.tabText(index)
        for index in range(without_results.tabs.count())
    ]

    assert "NTM" not in tabs_without
    assert "Déplacements" not in tabs_without

    with_results = ElementPropertiesDialog(
        None,
        project,
        element.tag,
        case_name="LC1",
        case_results={
            "element_forces": {
                element.tag: ElementResult(tag=element.tag, n_i=1.0, n_j=-1.0),
            },
            "displacements": {
                1: NodalResult(tag=1, ux=0.001),
                2: NodalResult(tag=2, ux=0.002),
            },
        },
    )
    tabs_with = [
        with_results.tabs.tabText(index)
        for index in range(with_results.tabs.count())
    ]

    assert "NTM" in tabs_with
    assert "Déplacements" in tabs_with
