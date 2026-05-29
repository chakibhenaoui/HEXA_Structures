"""HEXA Structures application entry point."""

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from config.settings import APP_VERSION, Settings
from gui.i18n.language_manager import LanguageManager
from gui.resources import app_resource_path


def _configure_qt_opengl() -> None:
    """Configure Qt opengl."""
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    if os.name == "nt":
        os.environ["QT_OPENGL"] = "desktop"
        QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)


def _create_startup_splash() -> QSplashScreen:
    """Create startup splash."""

    pixmap = QPixmap(520, 300)
    pixmap.fill(QColor("#f7f9fb"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    painter.setPen(QColor("#d7dde5"))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(12, 12, 496, 276, 10, 10)

    painter.setPen(QColor("#0f172a"))
    title_font = QFont("Segoe UI", 24, QFont.Bold)
    painter.setFont(title_font)
    painter.drawText(42, 92, "HEXA Structures")

    painter.setPen(QColor("#475569"))
    subtitle_font = QFont("Segoe UI", 10)
    painter.setFont(subtitle_font)
    painter.drawText(44, 122, f"Version {APP_VERSION}")

    painter.setPen(QColor("#334155"))
    painter.drawText(44, 188, "Démarrage de l'application...")

    painter.setPen(QColor("#94a3b8"))
    painter.drawText(44, 216, "Chargement des composants, veuillez patienter.")
    _draw_startup_logo(painter)
    painter.end()

    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    splash.setWindowFlag(Qt.FramelessWindowHint, True)
    return splash


def _draw_startup_logo(painter: QPainter) -> None:
    """Draw startup logo."""

    points = [
        (410, 58),
        (456, 84),
        (456, 136),
        (410, 162),
        (364, 136),
        (364, 84),
    ]

    outer_pen = QPen(QColor("#1e3a8a"), 2)
    inner_pen = QPen(QColor("#64748b"), 1)
    node_color = QColor("#2563eb")

    painter.setPen(outer_pen)
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        painter.drawLine(x1, y1, x2, y2)

    painter.setPen(inner_pen)
    for x, y in (points[0], points[1], points[3], points[4]):
        painter.drawLine(x, y, 410, 110)
    painter.drawLine(364, 84, 456, 136)
    painter.drawLine(456, 84, 364, 136)

    painter.setPen(Qt.NoPen)
    painter.setBrush(node_color)
    for x, y in [*points, (410, 110)]:
        painter.drawEllipse(x - 4, y - 4, 8, 8)


def _update_splash(splash: QSplashScreen, message: str) -> None:
    splash.showMessage(
        message,
        Qt.AlignLeft | Qt.AlignBottom,
        QColor("#334155"),
    )
    QApplication.processEvents()


def _argument_value(name: str, default: str = "") -> str:
    """Return a command-line option value without adding argparse to startup."""
    if name not in sys.argv:
        return default
    index = sys.argv.index(name)
    if index + 1 >= len(sys.argv):
        return default
    return sys.argv[index + 1]


def _run_smoke_test() -> int:
    """Run a non-interactive packaged-build smoke test."""
    _configure_qt_opengl()
    app = QApplication([sys.argv[0]])
    app.setOrganizationName("HEXA Structures")
    app.setApplicationName("HEXA Structures")

    requested_language = _argument_value(
        "--smoke-language",
        os.environ.get("HEXA_SMOKE_LANGUAGE", "en"),
    )
    allow_language_fallback = (
        "--smoke-allow-language-fallback" in sys.argv
        or os.environ.get("HEXA_SMOKE_ALLOW_LANGUAGE_FALLBACK") == "1"
    )

    language_manager = LanguageManager(app=app)
    language_applied = language_manager.load_language(requested_language, save=False)
    if not language_applied:
        language_manager.reset_to_default_language(save=False)

    file_menu = QCoreApplication.translate("MainWindow", "&Fichier")
    diagram_label = QCoreApplication.translate("DiagramWindow", "Diagramme de barre")
    i18n_dir = language_manager.i18n_dir
    payload = {
        "success": True,
        "requested_language": requested_language,
        "language_applied": language_applied,
        "current_language": language_manager.current_language_code,
        "allow_language_fallback": allow_language_fallback,
        "i18n_dir": str(i18n_dir),
        "i18n_dir_exists": i18n_dir.exists(),
        "english_qm_exists": language_manager.translation_path("en").exists(),
        "file_menu": file_menu,
        "diagram_label": diagram_label,
    }

    if not i18n_dir.exists():
        payload["success"] = False
        payload["error"] = "i18n directory not found"
    elif (
        requested_language != LanguageManager.DEFAULT_LANGUAGE
        and not language_applied
        and not allow_language_fallback
    ):
        payload["success"] = False
        payload["error"] = "requested language was not applied"
    elif language_applied and requested_language == "en" and file_menu != "&File":
        payload["success"] = False
        payload["error"] = "english translations were not active"

    output_path = _argument_value(
        "--smoke-output",
        os.environ.get("HEXA_SMOKE_OUTPUT", ""),
    )
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    app.quit()
    return 0 if payload["success"] else 2


def main():
    if "--smoke-test" in sys.argv or os.environ.get("HEXA_SMOKE_TEST") == "1":
        return _run_smoke_test()

    _configure_qt_opengl()
    app = QApplication(sys.argv)
    app.setOrganizationName("HEXA Structures")
    app.setApplicationName("HEXA Structures")
    app_icon = QIcon(app_resource_path("resources", "icons", "hexa_structures.ico"))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    splash = _create_startup_splash()
    splash.show()
    _update_splash(splash, "Chargement des paramètres...")

    settings = Settings.load()
    language_manager = LanguageManager(app=app)
    if not language_manager.load_language(settings.gui.language, save=False):
        language_manager.reset_to_default_language(save=False)
    app._language_manager = language_manager
    _update_splash(splash, "Chargement des modules graphiques...")

    from gui.main_window import MainWindow

    _update_splash(splash, "Construction de l'interface...")
    window = MainWindow(settings, language_manager=language_manager)
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    _update_splash(splash, "Ouverture de HEXA Structures...")
    window.show()
    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    sys.exit(main())
