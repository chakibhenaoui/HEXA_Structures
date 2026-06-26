from __future__ import annotations

import logging
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QSettings
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


def test_english_catalog_has_no_unfinished_entries() -> None:
    catalog = Path(__file__).resolve().parents[1] / "i18n" / "hexa_en.ts"

    text = catalog.read_text(encoding="utf-8")

    assert 'type="unfinished"' not in text
    assert "<translation></translation>" not in text


def test_english_catalog_translates_high_visibility_labels(tmp_path) -> None:
    _app()
    manager = LanguageManager(
        i18n_dir=Path(__file__).resolve().parents[1] / "i18n",
        settings=_settings(tmp_path),
    )

    try:
        assert manager.load_language("en") is True
        assert QCoreApplication.translate("MainWindow", "&Fichier") == "&File"
        assert QCoreApplication.translate("MainWindow", "&Vue") == "&View"
        assert (
            QCoreApplication.translate("DiagramWindow", "Diagramme de barre")
            == "Bar diagram"
        )
        assert QCoreApplication.translate("DiagramWindow", "Diagramme :") == "Diagram:"
        assert (
            QCoreApplication.translate("EurocodeSettingsDialog", "B — Bureaux")
            == "B - Offices"
        )
        assert (
            QCoreApplication.translate("LoadCaseManagerDialog", "Cliquer pour :")
            == "Click to:"
        )
        assert QCoreApplication.translate("SectionDialog", "Apercu") == "Preview"
        assert (
            QCoreApplication.translate("SectionDialog", "I / H parametrique")
            == "Parametric I / H"
        )
        assert (
            QCoreApplication.translate("SectionDialog", "Geometrie de section invalide")
            == "Invalid section geometry"
        )
        assert (
            QCoreApplication.translate("SectionBuilderDialog", "Section Builder HEXA")
            == "HEXA Section Builder"
        )
        assert (
            QCoreApplication.translate(
                "SectionBuilderDialog",
                "Calculer avec sectionproperties",
            )
            == "Calculate with sectionproperties"
        )
        assert (
            QCoreApplication.translate(
                "SectionBuilderDialog",
                "Appliquer la forme",
            )
            == "Apply shape"
        )
        assert (
            QCoreApplication.translate(
                "SectionBuilderDialog",
                "Ajouter à la bibliothèque standard",
            )
            == "Add to standard library"
        )
        assert (
            QCoreApplication.translate("SectionBuilderDialog", "Afficher contrainte")
            == "Show stress"
        )
        assert (
            QCoreApplication.translate("SectionBuilderDialog", "Exporter PDF...")
            == "Export PDF..."
        )
        assert (
            QCoreApplication.translate("SectionCalculationNoteDialog", "Exporter PDF")
            == "Export PDF"
        )
        assert (
            QCoreApplication.translate(
                "SectionBuilderDialog",
                "Maillage : {nodes} nœuds, {triangles} triangles",
            )
            == "Mesh: {nodes} nodes, {triangles} triangles"
        )
        assert (
            QCoreApplication.translate("PropertyPanel", "Tube rectangulaire")
            == "Rectangular tube"
        )
        assert QCoreApplication.translate("MainWindow", "Repère local") == "Local axes"
    finally:
        manager.reset_to_default_language(save=False)


def test_english_catalog_rejects_known_residual_translations(tmp_path) -> None:
    _app()
    manager = LanguageManager(
        i18n_dir=Path(__file__).resolve().parents[1] / "i18n",
        settings=_settings(tmp_path),
    )

    try:
        assert manager.load_language("en") is True
        translated = {
            QCoreApplication.translate(
                "DiagramWindow",
                "Aucun diagramme n'est disponible pour l'export.",
            ),
            QCoreApplication.translate(
                "MainWindow",
                "Aucune barre compatible pour ce diagramme.",
            ),
            QCoreApplication.translate("MainWindow", "Aucune vue compatible"),
            QCoreApplication.translate("PropertyPanel", "Calcul :"),
        }
    finally:
        manager.reset_to_default_language(save=False)

    assert "No diagramme n'est available pour l'export." not in translated
    assert "Noe bar compatible pour ce diagramme." not in translated
    assert "Noe vue compatible" not in translated
    assert "Calcul :" not in translated
