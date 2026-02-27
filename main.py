"""
main.py — Entry point for Posture Webcam Analyzer.

Creates the QApplication, applies the master stylesheet, and shows MainWindow.
"""

import sys
import os

# Ensure the project root is on sys.path so relative imports work
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QLinearGradient, QPen
from PyQt6.QtCore import Qt, QRect


# ---------------------------------------------------------------------------
# Styled splash screen
# ---------------------------------------------------------------------------

def _build_splash(app: QApplication) -> QSplashScreen:
    W, H = 480, 280
    pix = QPixmap(W, H)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background
    bg = QLinearGradient(0, 0, 0, H)
    bg.setColorAt(0.0, QColor("#1A1D2E"))
    bg.setColorAt(1.0, QColor("#12141F"))
    p.fillRect(0, 0, W, H, bg)

    # Accent top bar
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#6C63FF"))
    p.drawRect(0, 0, W, 4)

    # App name
    title_font = QFont("Segoe UI", 26, QFont.Weight.Bold)
    p.setFont(title_font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRect(0, 40, W, 60), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "Posture Tracker")

    # Tag line
    sub_font = QFont("Segoe UI", 11)
    p.setFont(sub_font)
    p.setPen(QColor("#A0A3B1"))
    p.drawText(QRect(0, 100, W, 30), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "Real-time posture monitoring")

    # Progress bar track
    bar_x, bar_y, bar_w, bar_h = 60, 190, W - 120, 6
    p.setBrush(QColor("#2A2D3E"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)

    # Progress bar fill (start at 0 — will be updated via repaint)
    p.setBrush(QColor("#6C63FF"))
    p.drawRoundedRect(bar_x, bar_y, 0, bar_h, 3, 3)

    # Status text placeholder
    status_font = QFont("Segoe UI", 9)
    p.setFont(status_font)
    p.setPen(QColor("#6B6F82"))
    p.drawText(QRect(0, 210, W, 24), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "Initialising…")

    p.end()

    splash = QSplashScreen(pix, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
    splash.setFixedSize(W, H)
    return splash


def _update_splash(splash: QSplashScreen, message: str, progress: int):
    """Redraw the splash with updated progress bar and status text."""
    W, H = 480, 280
    pix = QPixmap(W, H)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    bg = QLinearGradient(0, 0, 0, H)
    bg.setColorAt(0.0, QColor("#1A1D2E"))
    bg.setColorAt(1.0, QColor("#12141F"))
    p.fillRect(0, 0, W, H, bg)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#6C63FF"))
    p.drawRect(0, 0, W, 4)

    title_font = QFont("Segoe UI", 26, QFont.Weight.Bold)
    p.setFont(title_font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRect(0, 40, W, 60), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "Posture Tracker")

    sub_font = QFont("Segoe UI", 11)
    p.setFont(sub_font)
    p.setPen(QColor("#A0A3B1"))
    p.drawText(QRect(0, 100, W, 30), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "Real-time posture monitoring")

    bar_x, bar_y, bar_w, bar_h = 60, 190, W - 120, 6
    p.setBrush(QColor("#2A2D3E"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)

    fill_w = int(bar_w * max(0, min(100, progress)) / 100)
    if fill_w > 0:
        p.setBrush(QColor("#6C63FF"))
        p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 3, 3)

    status_font = QFont("Segoe UI", 9)
    p.setFont(status_font)
    p.setPen(QColor("#6B6F82"))
    p.drawText(QRect(0, 210, W, 24), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, message)

    p.end()

    splash.setPixmap(pix)
    splash.repaint()
    QApplication.processEvents()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)

    # Global default font — set early so splash uses it
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    # Show splash BEFORE any heavy imports so the screen isn't blank
    try:
        splash = _build_splash(app)
        splash.show()
        QApplication.processEvents()
    except Exception:
        splash = None

    def step(msg: str, pct: int):
        if splash:
            _update_splash(splash, msg, pct)

    step("Loading constants and styles…", 10)
    from core.constants import APP_NAME
    from core.stylesheet import build_stylesheet

    step("Applying stylesheet…", 22)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(build_stylesheet())

    step("Loading views…", 38)
    # Import all page modules now — this is where most time is spent
    import views.dashboard_page   # noqa: F401
    import views.reports_page     # noqa: F401
    import views.login_page       # noqa: F401
    import views.account_page     # noqa: F401

    step("Building main window…", 60)
    from app_window import MainWindow
    window = MainWindow()

    step("Starting background services…", 82)
    EnhancedTrayIcon = None
    try:
        from system_tray_widget import EnhancedTrayIcon as _Tray
        EnhancedTrayIcon = _Tray
    except Exception:
        pass

    step("Almost ready…", 95)
    window.show()

    # Drain the paint queue so the window renders its first frame before
    # the splash disappears — prevents the blank/frozen-looking transition.
    import time as _time
    for _i in range(6):
        QApplication.processEvents()
        _time.sleep(0.05)   # 6 × 50 ms = ~300 ms total

    step("Ready.", 100)
    QApplication.processEvents()

    if splash is not None:
        try:
            splash.finish(window)
        except Exception:
            pass

    # Create system tray icon
    tray_icon = None
    if EnhancedTrayIcon is not None:
        try:
            tray_icon = EnhancedTrayIcon(parent=None)
            window._tray_icon = tray_icon
        except Exception:
            tray_icon = None

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
