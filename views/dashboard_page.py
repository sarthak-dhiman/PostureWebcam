"""
dashboard_page.py — Main dashboard with webcam placeholder and KPI cards.

Changes:
- tracking_toggled(bool) signal so app_window can wire toggle → tracker
- on_posture_update(dict) slot driven by PostureTrackerThread
- show_subscription_gate(bool) shows/hides a lock overlay
- KPI cards updated from real tracker data (score, time, alerts)
"""

from datetime import datetime, timezone
import json as _json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QStackedWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread
import urllib.request
from PyQt6.QtGui import QPixmap

from core.constants import C
from core.icons import icon
from widgets.kpi_card import KpiCard
from widgets.dial_widget import DialWidget
import os as _os

_LIVE_FRAME   = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "live_frame.jpg")
_CONFIG_PATH  = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "app_config.json")


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}

try:
    import database as _db
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False


class DashboardPage(QWidget):
    """Primary view shown after login — webcam feed + KPIs + toggle."""

    # Emitted when user clicks Start/Stop; True = wants tracking ON
    tracking_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        # MJPEG client thread (started when tracking starts)
        self._mjpeg_thread: QThread | None = None
        self._tracking = False

        # KPI counters updated from tracker
        self._good_count = 0
        self._bad_count  = 0
        self._alert_count = 0
        self._session_start: datetime | None = None

        # load interval settings for dials
        cfg = _load_config()
        self._sit_total_sec  = int(cfg.get("sit_break_interval_min",  30)) * 60
        self._eye_total_sec  = int(cfg.get("eye_break_interval_min",  20)) * 60
        self._bad_total_sec  = int(cfg.get("alert_timing_seconds",     30))

        # ── Outer stack: subscription gate vs normal content ─────────
        self._outer_stack = QStackedWidget(self)
        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addWidget(self._outer_stack)

        # ── Main content page ────────────────────────────────────────
        content_widget = QWidget()
        root = QVBoxLayout(content_widget)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        hdr = QLabel("Dashboard")
        hdr.setObjectName("pageHeader")
        root.addWidget(hdr)

        sub = QLabel("Monitor your posture in real time.")
        sub.setObjectName("pageSubheader")
        root.addWidget(sub)
        root.addSpacing(24)

        # ── Live status bar ─────────────────────────────────────────
        self._status_bar = QLabel("Status: Idle")
        self._status_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_bar.setObjectName("statusBar")
        self._status_bar.setStyleSheet(
            f"font-size: 13px; font-weight: 600; padding: 6px 14px; "
            f"background: {C.BG_INPUT}; border-radius: 8px; color: {C.TEXT_SECONDARY};"
        )
        root.addWidget(self._status_bar)
        root.addSpacing(14)

        # ── Webcam live feed ─────────────────────────────────────────
        cam_frame = QFrame()
        cam_frame.setObjectName("webcamPlaceholder")
        cam_frame.setMinimumHeight(240)
        cam_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        cam_lay = QVBoxLayout(cam_frame)
        cam_lay.setContentsMargins(0, 0, 0, 0)
        cam_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_lbl = QLabel()
        self._cam_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_lbl.setStyleSheet("background: transparent; border: none;")
        self._cam_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._cam_placeholder = QLabel("Camera will appear here when tracking starts")
        self._cam_placeholder.setStyleSheet(
            f"font-size: 13px; color: {C.TEXT_DISABLED}; background: transparent; border: none;"
        )
        self._cam_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cam_lay.addWidget(self._cam_lbl)
        cam_lay.addWidget(self._cam_placeholder, alignment=Qt.AlignmentFlag.AlignCenter)

        # Frame refresh timer (fires when tracking is active)
        # Poll more frequently for a smoother UI; actual file updates
        # still come from the daemon at ~1 FPS unless preview streaming
        # is implemented.
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(250)  # 4 fps display polling
        self._frame_timer.timeout.connect(self._refresh_cam_frame)

        root.addWidget(cam_frame, 3)
        root.addSpacing(20)

        # ── KPI cards row ───────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        self._score_card = KpiCard(title="Posture Score", value="—", subtitle="Good / total samples")
        self._time_card  = KpiCard(title="Time Tracked", value="0 min", subtitle="This session")
        self._alert_card = KpiCard(title="Alerts", value="0", subtitle="Bad posture detections")

        for card in (self._score_card, self._time_card, self._alert_card):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            cards_row.addWidget(card)

        root.addLayout(cards_row)
        root.addSpacing(20)

        # ── Countdown dials row ────────────────────────────────────────
        dials_section = QLabel("NEXT BREAK REMINDERS")
        dials_section.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {C.TEXT_DISABLED}; letter-spacing: 1px;"
        )
        root.addWidget(dials_section)
        root.addSpacing(8)

        dials_row = QHBoxLayout()
        dials_row.setSpacing(12)
        dials_row.setContentsMargins(0, 0, 0, 0)
        dials_row.addStretch(1)

        self._eye_dial  = DialWidget("Eye Break",         self._eye_total_sec,  C.ACCENT_BLUE)
        self._sit_dial  = DialWidget("Sit Break",         self._sit_total_sec,  C.ACCENT_EMERALD)
        self._bad_dial  = DialWidget("Bad Posture Alert", self._bad_total_sec,  C.ACCENT_AMBER)

        for dial in (self._eye_dial, self._sit_dial, self._bad_dial):
            # allow dials to expand/shrink while capping maximum size
            dial.setMaximumSize(140, 160)
            dial.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            dials_row.addWidget(dial)
            dials_row.addSpacing(8)

        dials_row.addStretch(1)
        root.addLayout(dials_row)
        root.addSpacing(20)

        # ── Toggle button ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._toggle_btn = QPushButton("  Start Tracking")
        self._toggle_btn.setIcon(icon("play"))
        self._toggle_btn.setObjectName("toggleBtn")
        self._toggle_btn.setProperty("tracking", "false")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # make the button adapt to available space
        self._toggle_btn.setMinimumWidth(180)
        self._toggle_btn.clicked.connect(self._on_toggle)
        btn_row.addWidget(self._toggle_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── Subscription gate page ──────────────────────────────────
        gate_widget = QWidget()
        gate_widget.setStyleSheet(f"background: {C.BG_PRIMARY};")
        gate_lay = QVBoxLayout(gate_widget)
        gate_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_lay.setSpacing(16)

        gate_icon_lbl = QLabel()
        gate_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        try:
            _lock_icon = icon("stop")
            if _lock_icon and not _lock_icon.isNull():
                pix = _lock_icon.pixmap(64, 64)
                gate_icon_lbl.setPixmap(pix)
        except Exception:
            pass

        gate_title = QLabel("No Active Subscription")
        gate_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_title.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {C.TEXT_PRIMARY};"
        )
        gate_body = QLabel(
            "Your account does not have an active subscription.\n"
            "Please upgrade to start posture tracking."
        )
        gate_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_body.setStyleSheet(f"font-size: 14px; color: {C.TEXT_SECONDARY};")
        gate_body.setWordWrap(True)

        upgrade_btn = QPushButton("  Upgrade / Activate Subscription")
        upgrade_btn.setObjectName("primaryBtn")
        upgrade_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        upgrade_btn.setFixedWidth(300)
        upgrade_btn.clicked.connect(self._open_billing)

        gate_lay.addStretch()
        gate_lay.addWidget(gate_icon_lbl)
        gate_lay.addWidget(gate_title)
        gate_lay.addWidget(gate_body)
        gate_lay.addSpacing(10)
        gate_lay.addWidget(upgrade_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        gate_lay.addStretch()

        self._outer_stack.addWidget(content_widget)  # index 0
        self._outer_stack.addWidget(gate_widget)      # index 1

        # Start with gate hidden (will be shown if subscription missing)
        self._outer_stack.setCurrentIndex(0)

    def _refresh_cam_frame(self):
        """Load the latest live_frame.jpg written by tracker_daemon and display it."""
        try:
            if not _os.path.exists(_LIVE_FRAME):
                return
            pix = QPixmap(_LIVE_FRAME)
            if pix.isNull():
                return
            size = self._cam_lbl.size()
            if size.width() > 10 and size.height() > 10:
                pix = pix.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            self._cam_lbl.setPixmap(pix)
            self._cam_placeholder.setVisible(False)
        except Exception:
            pass

    # ── MJPEG client support ─────────────────────────────────────────
    def _on_mjpeg_bytes(self, jpg: bytes):
        try:
            pm = QPixmap()
            pm.loadFromData(jpg)
            size = self._cam_lbl.size()
            if size.width() > 10 and size.height() > 10:
                pm = pm.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._cam_lbl.setPixmap(pm)
            self._cam_placeholder.setVisible(False)
        except Exception:
            pass


 

    def update_score(self, value: str):
        self._score_card.set_value(value)

    def update_time(self, value: str):
        self._time_card.set_value(value)

    def update_alerts(self, value: str):
        self._alert_card.set_value(value)

    def show_subscription_gate(self, show: bool):
        """Toggle between normal content (False) and the subscription lock screen (True)."""
        self._outer_stack.setCurrentIndex(1 if show else 0)

    def showEvent(self, event):
        super().showEvent(event)
        self._load_today_db_stats()

    def _load_today_db_stats(self):
        """Populate KPI cards from today's DB records (between live updates)."""
        if not _DB_AVAILABLE:
            return
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            s = _db.get_daily_summary(today)
            total = s.get("total", 0)
            if total > 0:
                self._score_card.set_value(f"{s.get('good_pct', 0):.0f}%")
                self._time_card.set_value(f"{s.get('total_minutes', 0)} min")
                self._alert_card.set_value(str(s.get("bad", 0)))
        except Exception:
            pass

    def on_posture_update(self, sample: dict):
        """Slot wired to PostureTrackerThread.posture_update.

        Always updates the status bar so the user sees live feedback.
        KPI counters (score, alerts) are only incremented when actively tracking.
        """
        label  = sample.get("label", "unknown")
        reason = sample.get("reason", "")

        # ── Status bar — always live, even before the button is clicked ──
        if label == "good":
            color = C.ACCENT_EMERALD
            text  = "Good Posture"
        elif label == "bad":
            color = C.ACCENT_RED
            text  = f"Bad Posture — {reason}" if reason else "Bad Posture"
        elif label == "camera_busy":
            color = C.ACCENT_RED
            text  = "Camera in use by another app — tracking paused"
        elif label in ("no_tracker", "no_body"):
            color = C.TEXT_DISABLED
            text  = "No body detected"
        else:
            color = C.TEXT_SECONDARY
            text  = "Detecting..."

        self._status_bar.setText(f"Status: {text}")
        self._status_bar.setStyleSheet(
            f"font-size: 13px; font-weight: 600; padding: 6px 14px; "
            f"background: {C.BG_INPUT}; border-radius: 8px; color: {color};"
        )

        # ── Everything below only matters when a session is running ──
        if not self._tracking:
            return

        # Count samples for posture score
        if label == "good":
            self._good_count += 1
        elif label == "bad":
            self._bad_count  += 1
            self._alert_count += 1

        total = self._good_count + self._bad_count
        if total > 0:
            score_pct = int(self._good_count / total * 100)
            self._score_card.set_value(f"{score_pct}%")
        self._alert_card.set_value(str(self._alert_count))

        # Session time
        if self._session_start:
            elapsed = (datetime.now(timezone.utc) - self._session_start).seconds // 60
            self._time_card.set_value(f"{elapsed} min")

        # Update countdown dials
        eye_elapsed = int(sample.get("eye_elapsed_sec", 0) or 0)
        sit_elapsed = int(sample.get("sit_elapsed_sec", 0) or 0)
        bad_elapsed = int(sample.get("bad_streak_sec",  0) or 0)
        self._eye_dial.set_remaining(max(0, self._eye_total_sec - eye_elapsed))
        self._sit_dial.set_remaining(max(0, self._sit_total_sec - sit_elapsed))
        self._bad_dial.set_remaining(max(0, self._bad_total_sec - bad_elapsed))

    def reload_dial_config(self):
        """Re-read interval settings from disk and update the dials immediately."""
        try:
            cfg = _load_config()
            self._sit_total_sec = int(cfg.get("sit_break_interval_min", 30)) * 60
            self._eye_total_sec = int(cfg.get("eye_break_interval_min", 20)) * 60
            self._bad_total_sec = int(cfg.get("alert_timing_seconds",    30))
            # Update each dial's total so the arc and countdown reflect the new period
            self._sit_dial.set_total(self._sit_total_sec)
            self._eye_dial.set_total(self._eye_total_sec)
            self._bad_dial.set_total(self._bad_total_sec)
            # If not currently tracking, reset remaining to the new full period
            if not self._tracking:
                self._sit_dial.set_remaining(self._sit_total_sec)
                self._eye_dial.set_remaining(self._eye_total_sec)
                self._bad_dial.set_remaining(self._bad_total_sec)
        except Exception:
            pass

    def auto_start_tracking(self):
        """Programmatically start tracking (called on login if subscription active)."""
        try:
            if not self._tracking:
                self._on_toggle()
        except Exception:
            pass

    # ── Internal ────────────────────────────────────────────────────────

    def _on_toggle(self):
        self._tracking = not self._tracking
        if self._tracking:
            self._toggle_btn.setText("  Stop Tracking")
            self._toggle_btn.setIcon(icon("stop"))
            self._toggle_btn.setProperty("tracking", "true")
            self._session_start = datetime.now(timezone.utc)
            self._good_count = 0
            self._bad_count  = 0
            self._alert_count = 0
            self._status_bar.setText("Status: Starting...")
            self._frame_timer.start()
            # start MJPEG client for smooth preview (best-effort)
            try:
                self._mjpeg_thread = MJPEGStreamThread()
                self._mjpeg_thread.frame_available.connect(self._on_mjpeg_bytes)
                self._mjpeg_thread.start()
            except Exception:
                self._mjpeg_thread = None
            # reset dials to full
            self._eye_dial.set_remaining(self._eye_total_sec)
            self._sit_dial.set_remaining(self._sit_total_sec)
            self._bad_dial.set_remaining(self._bad_total_sec)
        else:
            self._toggle_btn.setText("  Start Tracking")
            self._toggle_btn.setIcon(icon("play"))
            self._toggle_btn.setProperty("tracking", "false")
            self._session_start = None
            self._status_bar.setText("Status: Idle")
            self._frame_timer.stop()
            # stop MJPEG client if running
            try:
                if self._mjpeg_thread is not None:
                    self._mjpeg_thread.stop()
                    self._mjpeg_thread.wait(1000)
            except Exception:
                pass
            self._mjpeg_thread = None
            self._cam_lbl.clear()
            self._cam_placeholder.setVisible(True)
            # reset dials
            self._eye_dial.set_remaining(self._eye_total_sec)
            self._sit_dial.set_remaining(self._sit_total_sec)
            self._bad_dial.set_remaining(self._bad_total_sec)

        # Force QSS refresh for dynamic property
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)

        self.tracking_toggled.emit(self._tracking)

    @staticmethod
    def _open_billing():
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        from core.constants import BILLING_URL
        QDesktopServices.openUrl(QUrl(BILLING_URL))


class MJPEGStreamThread(QThread):
    """Background thread that connects to the local MJPEG stream and emits
    complete JPEG frames via a callback into the UI thread.
    """
    frame_available = pyqtSignal(bytes)

    def __init__(self, url: str = "http://127.0.0.1:8765/stream", parent=None):
        super().__init__(parent)
        self._url = url
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        buffer = b""
        try:
            req = urllib.request.Request(self._url, headers={"User-Agent": "PostureApp/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                while self._running:
                    chunk = resp.read(1024)
                    if not chunk:
                        break
                    buffer += chunk
                    # find JPEG start/end markers
                    while True:
                        start = buffer.find(b'\xff\xd8')
                        end = buffer.find(b'\xff\xd9')
                        if start != -1 and end != -1 and end > start:
                            jpg = buffer[start:end+2]
                            buffer = buffer[end+2:]
                            try:
                                self.frame_available.emit(jpg)
                            except Exception:
                                pass
                        else:
                            break
        except Exception:
            pass
