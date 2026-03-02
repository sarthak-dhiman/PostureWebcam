"""
system_tray_widget.py — Enhanced system tray widget for posture status.

Improved version of the system tray icon with better visual design and functionality.
"""

import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer, pyqtSignal, QObject, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QFont, QBrush
from core.icons import icon
from core.workers import SubscriptionMonitor, PostureTrackerThread
from core.constants import APP_NAME

# Import live stats path
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_LIVE_STATS_PATH = os.path.join(_APP_DIR, "live_stats.json")


class PostureStatusUpdater(QObject):
    """Worker object that emits status updates."""
    status_changed = pyqtSignal(str, str, dict)  # status, reason, stats
    
    def __init__(self):
        super().__init__()
        self._last_status = "unknown"
        self._last_reason = ""
        
    def check_status(self):
        """Check live stats and emit status if changed."""
        try:
            if os.path.exists(_LIVE_STATS_PATH):
                with open(_LIVE_STATS_PATH, 'r', encoding='utf-8') as f:
                    stats = json.load(f)
                
                label = stats.get("label", "unknown")
                reason = stats.get("reason", "")
                body_detected = stats.get("body_detected", True)
                
                if not body_detected:
                    status = "no_body"
                elif label == "good":
                    status = "good"
                elif label == "bad":
                    status = "bad"
                else:
                    status = "unknown"
                
                # Only emit if status changed
                if status != self._last_status or reason != self._last_reason:
                    self.status_changed.emit(status, reason, stats)
                    self._last_status = status
                    self._last_reason = reason
            else:
                if self._last_status != "no_tracker":
                    self.status_changed.emit("no_tracker", "", {})
                    self._last_status = "no_tracker"
                    
        except Exception:
            if self._last_status != "error":
                self.status_changed.emit("error", "", {})
                self._last_status = "error"


def create_enhanced_status_icon(status: str, size: int = 32) -> QIcon:
    """Create an enhanced QIcon with better visual design."""
    # For no_tracker / app idle state use the office.png app icon directly
    if status == "no_tracker":
        try:
            _o = os.path.join(_APP_DIR, "office.png")
            if os.path.isfile(_o):
                _pm = QPixmap(_o).scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if not _pm.isNull():
                    return QIcon(_pm)
        except Exception:
            pass
    # Prefer an SVG asset named after the status if available.
    try:
        from core.icons import icon as _svg_icon
        svg_candidate = _svg_icon(status)
        if svg_candidate and not svg_candidate.isNull():
            return svg_candidate
    except Exception:
        pass
    # Create larger canvas for better quality
    canvas_size = size * 2  # 2x for retina displays
    pixmap = QPixmap(canvas_size, canvas_size)
    pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Define colors and symbols
    if status == "good":
        bg_color = QColor(76, 175, 80)      # Material Green
        symbol = "✓"
        text_color = QColor(255, 255, 255)
    elif status == "bad":
        bg_color = QColor(244, 67, 54)      # Material Red
        symbol = "✗"
        text_color = QColor(255, 255, 255)
    elif status == "no_body":
        bg_color = QColor(158, 158, 158)    # Material Gray
        symbol = "?"
        text_color = QColor(255, 255, 255)
    elif status == "no_tracker":
        bg_color = QColor(117, 117, 117)    # Darker Gray
        symbol = "○"
        text_color = QColor(255, 255, 255)
    else:  # unknown/error
        bg_color = QColor(158, 158, 158)    # Material Gray
        symbol = "○"
        text_color = QColor(255, 255, 255)
    
    # Draw outer circle with gradient effect
    center = canvas_size // 2
    radius = canvas_size // 2 - 4
    
    # Main circle
    painter.setBrush(QBrush(bg_color))
    painter.setPen(QPen(bg_color.darker(150), 3))
    painter.drawEllipse(center - radius, center - radius, radius * 2, radius * 2)
    
    # Inner highlight for depth
    highlight_color = bg_color.lighter(130)
    painter.setBrush(QBrush(highlight_color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(center - radius + 4, center - radius + 4, 
                    (radius - 4) * 2, (radius - 4) * 2)
    
    # Draw symbol
    painter.setPen(QPen(text_color, 4))
    font = QFont("Segoe UI Emoji", int(canvas_size * 0.3), QFont.Weight.Bold)
    painter.setFont(font)
    
    # Center the symbol
    rect = pixmap.rect()
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, symbol)
    
    painter.end()
    
    # Scale down to actual size
    scaled_pixmap = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, 
                                   Qt.TransformationMode.SmoothTransformation)
    
    return QIcon(scaled_pixmap)


class EnhancedTrayIcon(QSystemTrayIcon):
    """Enhanced system tray icon with better visual design."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Subscription monitor — prefer reusing the app's monitor to avoid
        # duplicate background threads emitting conflicting hold signals.
        try:
            win = self._find_main_window()
            # Reuse the app's monitor if available; do NOT start a separate monitor
            # while the user is signed out — subscription checks should start
            # when the main app starts monitoring after login.
            if win is not None and hasattr(win, "_sub_monitor") and win._sub_monitor is not None:
                self._sub_monitor = win._sub_monitor
                self._sub_monitor.status_changed.connect(self._on_subscription_status)
            else:
                # No app monitor available; avoid starting a background monitor
                self._sub_monitor = None
        except Exception:
            self._sub_monitor = None

        # Posture tracker — reuse the main app's tracker if available; do not
        # create a local tracker while signed out to avoid alerts and daemon
        # activity. If the main window exposes a tracker, subscribe to its signals.
        win = self._find_main_window()
        if win is not None and hasattr(win, "_tracker") and win._tracker is not None:
            self._tracker = win._tracker
            try:
                self._tracker.posture_update.connect(self._on_tracker_update)
                self._tracker.status_changed.connect(lambda s, d: self._on_status_changed(s, d, {}))
            except Exception:
                pass
        else:
            self._tracker = None

        # Ensure clean shutdown when the QApplication quits
        app = QApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.connect(self._cleanup_threads)
            except Exception:
                pass

        # Keep legacy updater as a fallback for file-based polling
        self._updater = PostureStatusUpdater()
        self._updater.status_changed.connect(self._on_status_changed)

        # Timer for periodic updates (fallback)
        self._timer = QTimer()
        self._timer.timeout.connect(self._updater.check_status)
        self._timer.start(1000)  # Check every second
        
        # Current status and stats
        self._current_status = "unknown"
        self._current_reason = ""
        self._current_stats = {}
        
        # Create context menu
        self._create_menu()
        
        # Set initial icon to office.png so the tray is recognisable before
        # the first posture-status update fires.
        try:
            _o = os.path.join(_APP_DIR, "office.png")
            if os.path.isfile(_o):
                self.setIcon(QIcon(QPixmap(_o).scaled(
                    32, 32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )))
        except Exception:
            pass
        
        # Set initial icon (colour-coded status)
        self._update_icon()
        
        # Show tray icon
        self.show()
        
        # Initial status check
        self._updater.check_status()
        # If no user is logged in, show no-tracker state to avoid implying
        # the tracker is running when the app is signed out.
        win = self._find_main_window()
        is_logged_in = bool(win and getattr(win, "_user", None))
        if not is_logged_in:
            self._current_status = "no_tracker"
            self._current_stats = {}
            self._update_icon()

        # Enable tooltips
        self.setToolTip(f"{APP_NAME} - Checking...")
    
    def _create_menu(self):
        """Create enhanced context menu."""
        menu = QMenu()
        
        # Status info (non-clickable)
        self._status_action = menu.addAction("Status: Checking...")
        self._status_action.setEnabled(False)
        
        # Detailed stats submenu
        stats_menu = menu.addMenu("Details")
        stats_menu.setIcon(icon("chart"))
        self._posture_detail = stats_menu.addAction("Posture: --")
        self._confidence_detail = stats_menu.addAction("Confidence: --")
        self._distance_detail = stats_menu.addAction("Distance: --")
        self._angle_detail = stats_menu.addAction("Angle: --")
        
        # Make all detail items non-clickable
        for action in [self._posture_detail, self._confidence_detail, 
                     self._distance_detail, self._angle_detail]:
            action.setEnabled(False)
        
        menu.addSeparator()
        
        # Actions
        dashboard_action = menu.addAction("Open Dashboard")
        dashboard_action.setIcon(icon("home"))
        dashboard_action.triggered.connect(self._open_dashboard)
        settings_action = menu.addAction("Settings")
        settings_action.setIcon(icon("user"))
        settings_action.triggered.connect(self._open_settings)
        
        menu.addSeparator()
        
        # Quit
        quit_action = menu.addAction("Quit")
        quit_action.setIcon(icon("stop"))
        quit_action.triggered.connect(QApplication.instance().quit)
        
        self.setContextMenu(menu)
    
    def _update_icon(self):
        """Update tray icon and tooltip based on current status."""
        icon = create_enhanced_status_icon(self._current_status)
        self.setIcon(icon)
        
        # Update tooltip with detailed information (no emoji glyphs)
        if self._current_status == "good":
            tooltip = "Posture: GOOD\\nSitting correctly!"
        elif self._current_status == "bad":
            reason_text = f"\\n{self._current_reason}" if self._current_reason else ""
            tooltip = f"Posture: BAD{reason_text}\\nPlease adjust your posture"
        elif self._current_status == "no_body":
            tooltip = "No body detected\\nPosition yourself in camera view"
        elif self._current_status == "no_tracker":
            tooltip = "Tracker offline\\nStart the posture tracker"
        else:
            tooltip = "Status unknown\\nChecking posture..."
        
        # Add additional stats if available
        if self._current_stats:
            conf = self._current_stats.get("confidence")
            if conf:
                tooltip += f"\\nConfidence: {conf:.0%}"
            
            dist = self._current_stats.get("dist_cm")
            if dist:
                tooltip += f"\\nDistance: {dist} cm"
            
            angle = self._current_stats.get("head_tilt_deg")
            if angle:
                tooltip += f"\\nHead Tilt: {angle:.1f}°"
        
        self.setToolTip(tooltip)
        
        # Update menu status text
        status_text = tooltip.split('\\n')[0]  # First line only
        self._status_action.setText(status_text)
        
        # Update detail items
        self._update_detail_items()
    
    def _update_detail_items(self):
        """Update the detail menu items with current stats."""
        if not self._current_stats:
            return
            
        # Posture status
        posture_text = f"Posture: {self._current_status.upper()}"
        if self._current_reason:
            posture_text += f" ({self._current_reason})"
        self._posture_detail.setText(posture_text)
        
        # Confidence
        conf = self._current_stats.get("confidence")
        if conf is not None:
            self._confidence_detail.setText(f"Confidence: {conf:.0%}")
        else:
            self._confidence_detail.setText("Confidence: --")
        
        # Distance
        dist = self._current_stats.get("dist_cm")
        if dist is not None:
            self._distance_detail.setText(f"Distance: {dist} cm")
        else:
            self._distance_detail.setText("Distance: --")
        
        # Angle
        angle = self._current_stats.get("head_tilt_deg")
        if angle is not None:
            self._angle_detail.setText(f"Head Tilt: {angle:.1f}°")
        else:
            self._angle_detail.setText("Angle: --")
    
    def _on_status_changed(self, status: str, reason: str, stats: dict):
        """Handle status change from updater."""
        self._current_status = status
        self._current_reason = reason
        self._current_stats = stats
        self._update_icon()

    def _on_tracker_update(self, payload: dict):
        """Adapter for tracker `posture_update` signal to the tray status handler.

        Expected payload keys: label, reason, body_detected, confidence, dist_cm, head_tilt_deg
        """
        label = payload.get("label", "unknown")
        reason = payload.get("reason", "")
        body = payload.get("body_detected", True)

        if not body:
            status = "no_body" if label != "no_tracker" else "no_tracker"
        elif label == "good":
            status = "good"
        elif label == "bad":
            status = "bad"
        elif label == "error":
            status = "error"
        else:
            status = "unknown"

        # Prepare stats dict for UI
        stats = {
            "confidence": payload.get("confidence"),
            "dist_cm": payload.get("dist_cm"),
            "head_tilt_deg": payload.get("head_tilt_deg"),
        }

        self._on_status_changed(status, reason, stats)

    def _on_subscription_status(self, status: str, detail: str):
        """Respond to subscription monitor changes by toggling the tracker."""
        # status values: online | offline | expired
        # Only release the tracker when there is an authenticated user.
        win = self._find_main_window()
        is_logged_in = bool(win and getattr(win, "_user", None))

        if status == "expired":
            try:
                if self._tracker is not None:
                    self._tracker.set_hold(True)
            except Exception:
                pass
            # inform the user
            self.showMessage("Subscription", "Subscription expired — tracker paused.", QIcon(), 3000)
        elif status == "online":
            # Backend verifies subscription; only unhold if the app has a user session
            try:
                if self._tracker is not None:
                    if is_logged_in:
                        self._tracker.set_hold(False)
                    else:
                        self._tracker.set_hold(True)
            except Exception:
                pass
        else:  # offline
            # When offline, keep tracker held if no user is logged in; otherwise preserve current session
            try:
                if self._tracker is not None:
                    should_hold = not is_logged_in
                    self._tracker.set_hold(should_hold)
            except Exception:
                pass
    
    @staticmethod
    def _find_main_window():
        """Return the running MainWindow instance, or None."""
        try:
            from app_window import MainWindow
            for w in QApplication.topLevelWidgets():
                if isinstance(w, MainWindow):
                    return w
        except Exception:
            pass
        return None

    def _open_dashboard(self):
        """Bring the existing MainWindow to the front on the Dashboard page."""
        try:
            from core.constants import PAGE_DASHBOARD
            win = self._find_main_window()
            if win is None:
                return
            win.showNormal()
            win.raise_()
            win.activateWindow()
            # Only navigate if already past login (sidebar visible)
            if win._sidebar.isVisible():
                win._navigate_to(PAGE_DASHBOARD)
        except Exception as e:
            print(f"Failed to open dashboard: {e}")

    def _open_settings(self):
        """Bring the existing MainWindow to the front on the Account page."""
        try:
            from core.constants import PAGE_ACCOUNT
            win = self._find_main_window()
            if win is None:
                return
            win.showNormal()
            win.raise_()
            win.activateWindow()
            if win._sidebar.isVisible():
                win._navigate_to(PAGE_ACCOUNT)
        except Exception as e:
            print(f"Failed to open settings: {e}")

    def _cleanup_threads(self):
        try:
            if hasattr(self, "_tracker") and self._tracker is not None:
                try:
                    self._tracker.shutdown()
                except Exception:
                    pass
                try:
                    self._tracker.wait(1000)
                except Exception:
                    pass
        finally:
            try:
                if hasattr(self, "_sub_monitor") and self._sub_monitor is not None:
                    try:
                        self._sub_monitor.stop()
                    except Exception:
                        pass
                    try:
                        self._sub_monitor.wait(1000)
                    except Exception:
                        pass
            except Exception:
                pass


def main():
    """Run enhanced system tray widget as a standalone application."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Don't quit when windows close
    
    # Create and show enhanced tray icon
    tray_icon = EnhancedTrayIcon()
    
    # Show startup notification
    try:
        from core.icons import icon as _svg_icon
        good_icon = _svg_icon("good")
    except Exception:
        good_icon = QIcon(create_enhanced_status_icon("good"))

    tray_icon.showMessage(
        APP_NAME,
        f"{APP_NAME} monitoring started\nRight-click the tray icon for options",
        good_icon,
        3000  # 3 seconds
    )
    
    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
