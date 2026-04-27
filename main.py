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

# ── Windows taskbar icon fix ─────────────────────────────────────────────────
# Setting an explicit App User Model ID causes Windows to group this process
# under its own taskbar button and use the window's QIcon instead of the
# generic python/pythonw.exe icon.  Must be called BEFORE QApplication().
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "PostureWebcamAnalyzer.App.1"
        )
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)

    # Global default font — set early so splash uses it
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    from core.constants import APP_NAME
    from core.stylesheet import build_stylesheet

    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    # Set the application icon (shown in taskbar, window title-bar, notifications)
    try:
        from PyQt6.QtGui import QIcon as _QIcon
        _icon_path = os.path.join(_ROOT, "office.png")
        if os.path.isfile(_icon_path):
            app.setWindowIcon(_QIcon(_icon_path))
    except Exception:
        pass
    app.setStyleSheet(build_stylesheet())

    # Do not start the tracker daemon while the user is signed out.
    # The daemon and tracker thread will be started after successful login.
    # Import all page modules now — this is where most time is spent
    import views.dashboard_page   # noqa: F401
    import views.reports_page     # noqa: F401
    import views.login_page       # noqa: F401
    import views.account_page     # noqa: F401

    from app_window import MainWindow
    window = MainWindow()

    # Ensure the tracker daemon is running before we show the dashboard so the
    # UI can immediately read live stats from the background process.
    try:
        window.ensure_tracker_daemon()
    except Exception:
        pass

    EnhancedTrayIcon = None
    try:
        from system_tray_widget import EnhancedTrayIcon as _Tray
        EnhancedTrayIcon = _Tray
    except Exception:
        pass

    # ── --minimized: boot directly to tray (used by auto-start registry key) ──
    _minimized_boot = "--minimized" in sys.argv
    if _minimized_boot:
        # Don't show the main window; the tray icon will be the only presence.
        window.hide()
    else:
        window.show()

    # Create system tray icon
    tray_icon = None
    if EnhancedTrayIcon is not None:
        try:
            # Clear any stale live stats while signed out so the tray doesn't
            # show an active tracker when no user is logged in.
            try:
                auth_path = os.path.join(_ROOT, "data", "auth_cache.json")
                live_stats = os.path.join(_ROOT, "live_stats.json")
                live_frame = os.path.join(_ROOT, "live_frame.jpg")
                if not (os.path.exists(auth_path) and os.path.getsize(auth_path) > 0):
                    try:
                        if os.path.exists(live_stats):
                            os.remove(live_stats)
                    except Exception:
                        pass
                    try:
                        if os.path.exists(live_frame):
                            os.remove(live_frame)
                    except Exception:
                        pass
            except Exception:
                pass

            tray_icon = EnhancedTrayIcon(parent=None)
            window._tray_icon = tray_icon
        except Exception:
            tray_icon = None

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
