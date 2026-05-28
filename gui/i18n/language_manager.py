"""Qt translation loading for the GUI layer."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings, QTranslator

from gui.resources import app_resource_path

_LOG = logging.getLogger(__name__)
_LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}(?:_[a-z0-9]{2,8})?$")


class LanguageManager:
    """Manage Qt translators without coupling the core domain to PySide6."""

    DEFAULT_LANGUAGE = "fr"
    SETTINGS_KEY = "gui/language"

    available_languages = {
        "fr": "Français",
        "en": "English",
    }

    def __init__(
        self,
        *,
        app: QCoreApplication | None = None,
        i18n_dir: str | Path | None = None,
        settings: QSettings | None = None,
        available_languages: dict[str, str] | None = None,
    ) -> None:
        self._app = app or QCoreApplication.instance()
        self.i18n_dir = Path(i18n_dir) if i18n_dir is not None else Path(app_resource_path("i18n"))
        self.settings = settings or QSettings()
        self.available_languages = dict(available_languages or self.available_languages)
        self._translator: QTranslator | None = None
        self._current_language_code = self.DEFAULT_LANGUAGE

    @property
    def current_language_code(self) -> str:
        """Return the currently installed language code."""
        return self._current_language_code

    def list_available_languages(self) -> dict[str, str]:
        """Return configured UI languages."""
        return dict(self.available_languages)

    def language_label(self, language_code: str) -> str:
        """Return a display label for a language code."""
        code = self.normalize_language_code(language_code)
        return self.available_languages.get(code, code)

    def translation_path(self, language_code: str) -> Path:
        """Return the expected compiled translation path for a language."""
        code = self.normalize_language_code(language_code)
        return self.i18n_dir / f"hexa_{code}.qm"

    def load_saved_language(self, fallback_language: str | None = None) -> bool:
        """Load the language stored in QSettings, falling back to French."""
        fallback = self.normalize_language_code(fallback_language or self.DEFAULT_LANGUAGE)
        saved = self.normalize_language_code(
            str(self.settings.value(self.SETTINGS_KEY, fallback) or fallback)
        )
        if self.load_language(saved):
            return True
        return self.load_language(fallback)

    def reset_to_default_language(self, *, save: bool = True) -> bool:
        """Switch back to the French source language."""
        return self.load_language(self.DEFAULT_LANGUAGE, save=save)

    def load_language(self, language_code: str, *, save: bool = True) -> bool:
        """Load a language by code and return whether it was applied."""
        code = self.normalize_language_code(language_code)
        if not self.is_valid_language_code(code):
            _LOG.warning("Invalid language code: %s", language_code)
            return False

        if code == self.DEFAULT_LANGUAGE:
            self._remove_translator()
            self._current_language_code = code
            if save:
                self._save_language(code)
            return True

        qm_path = self.translation_path(code)
        if not qm_path.exists():
            _LOG.warning("Translation file not found: %s", qm_path)
            return False

        translator = QTranslator()
        if not translator.load(str(qm_path)):
            _LOG.warning("Unable to load translation file: %s", qm_path)
            return False

        app = self._app or QCoreApplication.instance()
        if app is None:
            _LOG.warning("No QCoreApplication instance available to install translations.")
            return False

        self._remove_translator()
        app.installTranslator(translator)
        self._translator = translator
        self._current_language_code = code
        if save:
            self._save_language(code)
        return True

    @staticmethod
    def normalize_language_code(language_code: str) -> str:
        """Normalize a locale-like language code for file naming."""
        return str(language_code or "").strip().replace("-", "_").lower()

    @staticmethod
    def is_valid_language_code(language_code: str) -> bool:
        """Return True for compact language or locale codes such as fr or pt_br."""
        return bool(_LANGUAGE_CODE_RE.fullmatch(language_code))

    def _remove_translator(self) -> None:
        app = self._app or QCoreApplication.instance()
        if app is not None and self._translator is not None:
            app.removeTranslator(self._translator)
        self._translator = None

    def _save_language(self, language_code: str) -> None:
        self.settings.setValue(self.SETTINGS_KEY, language_code)
        self.settings.sync()
