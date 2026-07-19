from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from core.model_data import ProjectModel
from gui.main_window import MainWindow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_section_builder_loading_page_is_first_use_only(monkeypatch) -> None:
    _app()
    previous = MainWindow._section_builder_first_launch_done
    MainWindow._section_builder_first_launch_done = False

    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.project = ProjectModel()
    window.project.add_material("Acier", "steel", "S355")

    calls: list[tuple[str, str]] = []

    class FakeSectionBuilderDialog:
        Accepted = QDialog.Accepted

        def __init__(self, parent=None, *, materials=None):
            self.parent = parent
            self.materials = materials

    def fake_create_loading():
        calls.append(("create", ""))
        return object()

    def fake_update(_loading, message):
        if _loading is None:
            return
        calls.append(("update", message))

    def fake_close(_loading):
        if _loading is None:
            return
        calls.append(("close", ""))

    monkeypatch.setattr(window, "_create_section_builder_loading_dialog", fake_create_loading)
    monkeypatch.setattr(window, "_update_section_builder_loading_dialog", fake_update)
    monkeypatch.setattr(window, "_close_section_builder_loading_dialog", fake_close)
    monkeypatch.setattr(
        window,
        "_load_section_builder_dialog_class",
        lambda: FakeSectionBuilderDialog,
    )

    try:
        _dialog_cls, dialog = window._prepare_section_builder_dialog()
        assert isinstance(dialog, FakeSectionBuilderDialog)
        assert dialog.materials == window.project.materials

        _dialog_cls, dialog = window._prepare_section_builder_dialog()
        assert isinstance(dialog, FakeSectionBuilderDialog)
    finally:
        MainWindow._section_builder_first_launch_done = previous

    assert calls == [
        ("create", ""),
        ("update", "Chargement des bibliothèques..."),
        ("update", "Initialisation de l'atelier..."),
        ("close", ""),
    ]
