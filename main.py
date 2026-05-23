"""HEXA Structures application entry point."""

import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from config.settings import APP_VERSION, Settings
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


def main():
    _configure_qt_opengl()
    app = QApplication(sys.argv)
    app.setApplicationName("HEXA Structures")
    app_icon = QIcon(app_resource_path("resources", "icons", "hexa_structures.ico"))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    splash = _create_startup_splash()
    splash.show()
    _update_splash(splash, "Chargement des paramètres...")

    settings = Settings.load()
    _update_splash(splash, "Chargement des modules graphiques...")

    from gui.main_window import MainWindow

    _update_splash(splash, "Construction de l'interface...")
    window = MainWindow(settings)
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    _update_splash(splash, "Ouverture de HEXA Structures...")
    window.show()
    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
