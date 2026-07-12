from __future__ import annotations

import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.model_data import ProjectModel
from gui.main_window import MainWindow


class _DummyAction:
    def __init__(self) -> None:
        self.enabled = False

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)


class _DummyProperties:
    def __init__(self) -> None:
        self.project = None

    def set_project(self, project: ProjectModel) -> None:
        self.project = project


def _history_window(project: ProjectModel | None = None) -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window.project = project or ProjectModel()
    window.project.ensure_self_weight_load_case()
    window._modified = False
    window._pending_project_change = False
    window._history_restoring = False
    window._undo_history = []
    window._redo_history = []
    window._last_history_project = deepcopy(window.project)
    window._saved_project_snapshot = deepcopy(window.project)
    window.act_undo_model = _DummyAction()
    window.act_redo_model = _DummyAction()
    window.properties = _DummyProperties()
    window._clear_project_runtime_state = lambda: None
    window._refresh = lambda preserve_view=False: None
    window._log = lambda _message: None
    return window


def test_history_tracks_edit_undo_and_redo_modified_state() -> None:
    window = _history_window()

    window.project.description = "Modification"
    window._modified = True
    window._pending_project_change = True
    window._record_history_snapshot_if_needed()
    window._sync_modified_with_saved_state()
    window._update_history_actions()

    assert window._modified is True
    assert window.act_undo_model.enabled is True
    assert window.act_redo_model.enabled is False

    window._undo_last_action()

    assert window.project.description == ""
    assert window._modified is False
    assert window.act_undo_model.enabled is False
    assert window.act_redo_model.enabled is True

    window._redo_last_action()

    assert window.project.description == "Modification"
    assert window._modified is True
    assert window.act_undo_model.enabled is True
    assert window.act_redo_model.enabled is False


def test_history_does_not_record_a_marked_no_op() -> None:
    window = _history_window()
    window._modified = True
    window._pending_project_change = True

    window._record_history_snapshot_if_needed()

    assert window._undo_history == []
    assert window._redo_history == []
    assert window._modified is False


def test_reset_history_after_load_marks_project_as_saved() -> None:
    window = _history_window()
    window.project.description = "Projet chargé"
    window._modified = True
    window._pending_project_change = True
    window._undo_history.append(ProjectModel())
    window._redo_history.append(ProjectModel())

    window._reset_project_history(mark_saved=True)

    assert window._undo_history == []
    assert window._redo_history == []
    assert window._modified is False
    assert window._saved_project_snapshot == window.project
    assert window._saved_project_snapshot is not window.project


def test_open_project_keeps_modified_project_when_discard_is_rejected(
    monkeypatch,
) -> None:
    window = MainWindow.__new__(MainWindow)
    window._modified = True
    window._confirm_discard = lambda: False
    dialog_calls: list[bool] = []

    monkeypatch.setattr(
        "gui.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: dialog_calls.append(True),
    )

    window._on_open_project()

    assert dialog_calls == []


def test_saved_state_stays_clean_when_undoing_and_redoing_around_it() -> None:
    window = _history_window()
    initial = deepcopy(window.project)

    window.project.description = "État sauvegardé"
    window._pending_project_change = True
    window._record_history_snapshot_if_needed()
    window._saved_project_snapshot = deepcopy(window.project)
    window._sync_modified_with_saved_state(force_compare=True)

    window.project.description = "Après sauvegarde"
    window._modified = True
    window._pending_project_change = True
    window._record_history_snapshot_if_needed()

    window._undo_last_action()
    assert window.project.description == "État sauvegardé"
    assert window._modified is False

    window._undo_last_action()
    assert window.project == initial
    assert window._modified is True

    window._redo_last_action()
    assert window.project.description == "État sauvegardé"
    assert window._modified is False
