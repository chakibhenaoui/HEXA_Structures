from __future__ import annotations

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gui.i18n.language_manager import LanguageManager
from gui.main_window import MainWindow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "qt_settings.ini"), QSettings.IniFormat)


def test_language_manager_accepts_french_without_qm(tmp_path) -> None:
    _app()
    settings = _settings(tmp_path)
    manager = LanguageManager(i18n_dir=tmp_path, settings=settings)

    assert manager.load_language("fr") is True
    assert manager.current_language_code == "fr"
    assert settings.value(LanguageManager.SETTINGS_KEY) == "fr"


def test_language_manager_missing_qm_returns_false(tmp_path, caplog) -> None:
    _app()
    manager = LanguageManager(i18n_dir=tmp_path, settings=_settings(tmp_path))

    with caplog.at_level(logging.WARNING):
        assert manager.load_language("xx") is False

    assert "Translation file not found" in caplog.text


def test_language_manager_available_languages_are_extensible(tmp_path) -> None:
    manager = LanguageManager(
        i18n_dir=tmp_path,
        settings=_settings(tmp_path),
        available_languages={"fr": "Français", "it": "Italiano"},
    )

    assert manager.list_available_languages()["it"] == "Italiano"
    assert manager.translation_path("it").name == "hexa_it.qm"


def test_default_language_list_hides_unfinished_translations(tmp_path) -> None:
    manager = LanguageManager(i18n_dir=tmp_path, settings=_settings(tmp_path))

    assert manager.list_available_languages() == {
        "fr": "Français",
        "en": "English",
    }


def test_main_window_exposes_retranslate_ui() -> None:
    assert callable(getattr(MainWindow, "retranslate_ui", None))
