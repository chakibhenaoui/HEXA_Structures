from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from core.model_data import ProjectModel
from gui.main_window import MainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _AcceptedNodeDialog:
    last_kwargs: dict | None = None
    result_data: dict[str, float | int] = {"tag": 2, "x": 1.0, "y": 2.0, "z": 3.0}

    def __init__(self, _parent=None, **kwargs) -> None:
        type(self).last_kwargs = kwargs

    def exec(self) -> int:
        return QDialog.Accepted

    def result(self) -> dict[str, float | int]:
        return dict(type(self).result_data)


def _make_add_node_window() -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window.project = ProjectModel()
    window.project.add_node(0.0, 0.0, 0.0)
    window._selected_node_tags = [1]
    return window


def test_add_node_creates_new_node_even_when_node_is_selected(monkeypatch) -> None:
    from gui.dialogs import node_dlg

    _app()
    _AcceptedNodeDialog.result_data = {"tag": 7, "x": 5.0, "y": 0.0, "z": 0.0}
    monkeypatch.setattr(node_dlg, "NodeDialog", _AcceptedNodeDialog)

    window = _make_add_node_window()
    mark_calls: list[bool] = []
    refresh_calls: list[bool] = []
    selected_after: list[int] = []

    window._mark_project_modified = lambda: mark_calls.append(True)
    window._refresh = lambda preserve_view=False: refresh_calls.append(preserve_view)
    window._select_node_after_change = lambda tag: selected_after.append(tag)
    window._log = lambda _message: None

    window._add_node()

    assert sorted(window.project.nodes) == [1, 7]
    assert (window.project.nodes[1].x, window.project.nodes[1].y, window.project.nodes[1].z) == (
        0.0,
        0.0,
        0.0,
    )
    assert (window.project.nodes[7].x, window.project.nodes[7].y, window.project.nodes[7].z) == (
        5.0,
        0.0,
        0.0,
    )
    assert _AcceptedNodeDialog.last_kwargs == {
        "node_tag": 2,
        "allow_tag_edit": True,
        "forbidden_tags": {1},
    }
    assert mark_calls == [True]
    assert refresh_calls == [True]
    assert selected_after == [7]


def test_add_node_rejects_existing_tag_without_overwriting(monkeypatch) -> None:
    from gui.dialogs import node_dlg

    _app()
    _AcceptedNodeDialog.result_data = {"tag": 1, "x": 5.0, "y": 0.0, "z": 0.0}
    monkeypatch.setattr(node_dlg, "NodeDialog", _AcceptedNodeDialog)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, text, *args: warnings.append(text),
    )

    window = _make_add_node_window()
    window._mark_project_modified = lambda: pytest.fail("project should not be marked modified")
    window._refresh = lambda preserve_view=False: pytest.fail("view should not refresh")
    window._select_node_after_change = lambda tag: pytest.fail("selection should not change")
    window._log = lambda _message: None

    window._add_node()

    assert sorted(window.project.nodes) == [1]
    assert (window.project.nodes[1].x, window.project.nodes[1].y, window.project.nodes[1].z) == (
        0.0,
        0.0,
        0.0,
    )
    assert warnings == ["Le numéro N1 existe déjà. Choisissez un autre numéro."]
