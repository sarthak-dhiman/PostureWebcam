"""
tracker_daemon.py — Headless posture-tracking daemon with system-tray icon.

Architecture
------------
Main thread   : pystray icon loop (required by pystray on Windows).
Worker thread : 1-FPS camera loop  → MediaPipe Pose → identity lock → posture math → DB write.

CPU budget target: < 5 %.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from math import atan2, degrees
from types import SimpleNamespace

import cv2
import numpy as np
import onnxruntime as ort
import face_recognition
import http.server
import socketserver
import io

# PyQt6 imports for enhanced tray and widget
try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QLabel, QHBoxLayout, QMenu,
        QGraphicsDropShadowEffect, QSystemTrayIcon,
    )
    from PyQt6.QtCore import QTimer, Qt, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal, QObject
    from PyQt6.QtGui import QFont, QColor, QMouseEvent, QPixmap, QPainter, QBrush, QPen, QIcon
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False
    # Create dummy classes for fallback
    class QObject:
        pass
    def pyqtSignal(*args):
        return lambda *args: None
    class QPixmap:
        pass
    class QPainter:
        pass
    class QBrush:
        pass
    class QPen:
        pass
    class QFont:
        pass
    class QColor:
        pass
    class QMouseEvent:
        pass
    class QPoint:
        pass
    class QPropertyAnimation:
        pass
    class QEasingCurve:
        pass
    class QTimer:
        pass
    class Qt:
        pass
    class QHBoxLayout:
        pass
    class QLabel:
        pass
    class QWidget:
        pass
    class QMenu:
        pass
    class QGraphicsDropShadowEffect:
        pass
try:
    from core.constants import APP_NAME
except Exception:
    APP_NAME = "Posture Tracker"
    class QSystemTrayIcon:
        pass

try:
    import importlib

    # mediapipe can be packaged with different APIs. Prefer the classic
    # `mediapipe.solutions`, but if it's not available (some builds expose
    # the newer `mediapipe.tasks` API) we leave `mp_solutions` as None and
    # handle that case at runtime.
    mp_solutions = None
    try:
        _mp = importlib.import_module("mediapipe")
        if hasattr(_mp, "solutions"):
            mp_solutions = _mp.solutions
        else:
            mp_solutions = None
    except Exception:
        mp_solutions = None

    # Also detect the newer Tasks API (used by some mediapipe wheels)
    mp_tasks = None
    try:
        from mediapipe import tasks as mp_tasks_root  # type: ignore
        from mediapipe.tasks.python import vision as mp_tasks_vision  # type: ignore
        from mediapipe.tasks.python.core.base_options import BaseOptions  # type: ignore
        import mediapipe as _mediapipe_top
        mp_tasks = {
            "root": mp_tasks_root,
            "vision": mp_tasks_vision,
            "BaseOptions": BaseOptions,
            "mp": _mediapipe_top,
        }
    except Exception:
        mp_tasks = None
except Exception:
    # Some mediapipe distributions expose submodules differently; import solutions directly
    from mediapipe import solutions as mp_solutions
import pystray
from PIL import Image, ImageDraw
from plyer import notification

import camera_perms
import database

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load configuration from file
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "app_config.json")
_AUTH_CACHE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "auth_cache.json")
# App icon used in system notifications
_APP_ICON    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "office.png")

def load_config():
    """Load app configuration, return defaults if file doesn't exist."""
    try:
        with open(_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "alert_timing_seconds": 30,
            "notifications_enabled": True,
            "sound_enabled": True
        }

# Global config object
_config = load_config()


def _user_signed_in() -> bool:
    """Return True if an auth cache with a token exists (simple check)."""
    try:
        if not os.path.exists(_AUTH_CACHE):
            return False
        with open(_AUTH_CACHE, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return bool(data.get('token'))
    except Exception:
        return False

def reload_config():
    """Reload configuration from file."""
    global _config
    _config = load_config()
    # Update the global BAD_STREAK_LIMIT
    global BAD_STREAK_LIMIT
    BAD_STREAK_LIMIT = _config.get("alert_timing_seconds", 30)

OWNER_IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "owner.jpg")
FACE_TOLERANCE = 0.6          # lower = stricter match
BODY_GONE_TIMEOUT = 5.0       # seconds before identity lock resets
BAD_STREAK_LIMIT = _config.get("alert_timing_seconds", 30)  # consecutive bad frames before notification

# ONNX posture model — small MLP trained on 5 MediaPipe keypoints (24 features → 2 classes).
# Input:  [batch, 24]  — nose, l_shoulder, r_shoulder, l_hip, r_hip (x,y) + zero-padding
# Output: [batch, 2]   — logits for [Good, Bad]
POSTURE_ONNX_PATH = r"D:\Disease Prediction\saved_models_onnx\posture.onnx"
# Confidence threshold below which model result is ignored (falls back to heuristic)
ONNX_CONF_THRESHOLD = 0.65

# Fallback heuristic thresholds — Y-coordinate only (Z is unreliable on a flat webcam)
# All ratios are normalised by shoulder width so they are camera-distance-independent.
#
#  EAR_SHO_THRESHOLD   : min (sho_y - ear_y) / sho_width.
#                        Upright posture typically gives 0.55–0.75.
#                        Slouching (head forward/down) drops this to 0.35–0.45.
#                        Threshold at 0.40 catches real bad posture without
#                        false-positives when sitting straight.
#  SHO_ASYM_THRESHOLD  : max |left_sho_y - right_sho_y| / sho_width.
#                        Only flag obvious one-sided lean.
#
EAR_SHO_THRESHOLD   = 0.45   # increased sensitivity: smaller head drop flags as slouch
SHO_ASYM_THRESHOLD  = 0.18   # shoulder asymmetry limit
SHO_ROLL_THRESHOLD  = 8.0    # degrees tilt between shoulders considered rolled
SHO_DEPTH_THRESHOLD = 0.06   # normalized Z difference indicating one shoulder nearer

# Chin-forward (forward-head protrusion via z-axis).
# MediaPipe z: negative = closer to camera. If nose_z < mid_shoulder_z by more
# than this value the chin is jutting forward.
# NOTE: webcam depth (z) is estimated, not measured, and is noisy.
# Threshold raised to 0.18 to avoid constant false-positives; only sustained,
# obvious protrusion (leaning face right into the camera) will trigger.
CHIN_FORWARD_Z_THRESHOLD = 0.18
# Min consecutive frames before chin/shoulder specific alert fires
# At ~1 fps this means the chin must be forward for 25+ seconds continuously.
CHIN_STREAK_LIMIT     = 25
SHOULDER_STREAK_LIMIT = 8

# Lateral head tilt — ear-to-ear line angle from horizontal.
# 0° = perfectly level head; increases as head tilts left/right.
HEAD_TILT_THRESHOLD   = 12.0   # degrees; below this is normal head movement
HEAD_TILT_STREAK_LIMIT = 8     # consecutive bad frames before alert fires

# Lean-back torso recline — shoulder z relative to hip z.
# MediaPipe z: negative = closer to camera, positive = further away.
# When upright the shoulder midpoint sits at roughly the same depth as the
# hip midpoint.  A difference > LEAN_BACK_Z_THRESHOLD means the shoulders
# have been pushed noticeably behind the hips, i.e. the torso is reclined.
LEAN_BACK_Z_THRESHOLD  = 0.10   # normalised depth units; tune down for more sensitivity
LEAN_BACK_STREAK_LIMIT = 8      # consecutive bad frames before alert fires

# ── Time-based health rules ──────────────────────────────────────────────────
# Follow the 30-5 rule: after 30 min sitting fire a break reminder.
SIT_BREAK_INTERVAL  = 30 * 60   # seconds
# 20-20-20 rule: every 20 min look 20 ft away for 20 s.
EYE_BREAK_INTERVAL  = 20 * 60   # seconds
# Minimum re-alert gap for each timer so the same alert doesn't spam.
BREAK_COOLDOWN      = 10 * 60   # seconds

# ── Sitting-distance health check ───────────────────────────────────────────
# Average adult shoulder width in cm (used with a pinhole model to estimate
# how far the person is sitting from the camera / screen).
SHOULDER_WIDTH_CM      = 40.0   # cm — adjust if consistently over/under-estimated
# Typical webcam effective focal length at 640 px width ≈ 550–650 px.
# You can calibrate this: sit exactly 70 cm from the camera, note the
# shoulder pixel width, then set FOCAL = 70 * shoulder_px / 40.
WEBCAM_FOCAL_LENGTH_PX = 600.0
# Consecutive bad-distance frames before a notification fires (1 fps → 10 s).
DISTANCE_STREAK_LIMIT  = 10
# Min time between distance alerts.
DISTANCE_COOLDOWN      = 5 * 60   # seconds

# Temporal smoothing: majority over this many frames before issuing a verdict
LABEL_SMOOTH_WINDOW = 3      # frames

# MediaPipe Pose landmark indices
L_EAR, R_EAR = 7, 8
L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24

# Live feed files (written by daemon, polled by dashboard live panel)
_APP_DIR         = os.path.dirname(os.path.abspath(__file__))
_LIVE_FRAME_PATH = os.path.join(_APP_DIR, "live_frame.jpg")
_LIVE_STATS_PATH = os.path.join(_APP_DIR, "live_stats.json")
_STREAM_FRAME_BYTES = None  # latest scaled JPEG bytes for MJPEG streaming

# ── PyQt6 Tray and Widget Classes ────────────────────────────────────────

if PYQT6_AVAILABLE:
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
    
    class SimpleTrayIcon(QSystemTrayIcon):
        """Simple, reliable system tray icon."""
        
        def __init__(self, parent=None, stop_event=None):
            super().__init__(parent)
            self._stop_event = stop_event
            
            # Status updater
            self._updater = PostureStatusUpdater()
            self._updater.status_changed.connect(self._on_status_changed)
            
            # Timer for periodic updates
            self._timer = QTimer()
            self._timer.timeout.connect(self._updater.check_status)
            self._timer.start(1000)  # Check every second
            
            # Current status and stats
            self._current_status = "unknown"
            self._current_reason = ""
            self._current_stats = {}
            
            # Create simple context menu
            self._create_menu()
            
            # Set initial icon
            self._update_icon()
            
            # Show tray icon
            self.show()
            
            # Initial status check
            self._updater.check_status()
            
            # Enable tooltips
            self.setToolTip(f"{APP_NAME} - Checking...")
        
        def _create_menu(self):
            """Create simple context menu."""
            menu = QMenu()
            
            # Status info
            self._status_action = menu.addAction("Status: Checking...")
            self._status_action.setEnabled(False)
            
            menu.addSeparator()
            
            # Actions
            try:
                from core.icons import icon
            except Exception:
                icon = lambda name: QIcon()

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
            quit_action.triggered.connect(self._quit_app)
            
            self.setContextMenu(menu)

        def _quit_app(self):
            """Signal the daemon to stop and exit."""
            if self._stop_event is not None:
                self._stop_event.set()
            self.hide()
            app = QApplication.instance()
            if app:
                app.quit()
        
        def _update_icon(self):
            """Update tray icon and tooltip based on current status."""
            # Create icon
            try:
                from core.icons import icon as _svg_icon
                svg_icon = _svg_icon(self._current_status)
                if not svg_icon.isNull():
                    self.setIcon(svg_icon)
                else:
                    self.setIcon(self._create_simple_icon(self._current_status))
            except Exception:
                self.setIcon(self._create_simple_icon(self._current_status))
            
            # Update tooltip
            if self._current_status == "good":
                tooltip = "Posture: GOOD\\nSitting correctly!"
            elif self._current_status == "bad":
                reason_text = f"\\nReason: {self._current_reason}" if self._current_reason else ""
                tooltip = f"Posture: BAD{reason_text}\\nPlease adjust your posture"
            elif self._current_status == "no_body":
                tooltip = "No body detected\\nPosition yourself in camera view"
            elif self._current_status == "no_tracker":
                tooltip = "Tracker offline\\nStart the posture tracker"
            else:
                tooltip = "Status unknown\\nChecking posture..."
            
            # Add confidence if available
            if self._current_stats:
                conf = self._current_stats.get("confidence")
                if conf:
                    tooltip += f"\\nConfidence: {conf:.0%}"
            
            self.setToolTip(tooltip)
            
            # Update menu status text
            status_text = tooltip.split('\\n')[0]
            self._status_action.setText(status_text)
        
        def _create_simple_icon(self, status: str):
            """Create a single, clean icon design."""
            # Prefer an SVG asset named after the status if available.
            try:
                from core.icons import icon as _svg_icon
                svg_candidate = _svg_icon(status)
                if svg_candidate and not svg_candidate.isNull():
                    return svg_candidate
            except Exception:
                pass
            canvas_size = 64  # For high DPI displays
            pixmap = QPixmap(canvas_size, canvas_size)
            pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background
            
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Single clean color scheme
            if status == "good":
                bg_color = QColor(46, 125, 50)      # Nice green
                symbol = "✓"
            elif status == "bad":
                bg_color = QColor(198, 40, 40)       # Nice red
                symbol = "!"
            elif status == "no_body":
                bg_color = QColor(117, 117, 117)    # Nice gray
                symbol = "?"
            elif status == "no_tracker":
                bg_color = QColor(66, 66, 66)       # Dark gray
                symbol = "○"
            else:  # unknown/error
                bg_color = QColor(117, 117, 117)    # Nice gray
                symbol = "?"
            
            # Draw clean rounded rectangle
            painter.setBrush(QBrush(bg_color))
            painter.setPen(QPen(bg_color.darker(150), 2))
            rect_size = canvas_size - 6
            painter.drawRoundedRect(3, 3, rect_size, rect_size, 6, 6)
            
            # Draw ellipse with status color
            painter.setBrush(QBrush(QColor(0, 200, 80, 255)))
            painter.setPen(QPen(QColor(0, 0, 0, 0), 4))
            painter.drawEllipse(4, 4, canvas_size - 8, canvas_size - 8)
            
            # Draw symbol
            painter.setPen(QPen(QColor(255, 255, 255), 3))
            font = QFont("Segoe UI", int(canvas_size * 0.25), QFont.Weight.Bold)
            painter.setFont(font)
            
            rect = pixmap.rect()
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, symbol)
            
            painter.end()
            
            # Scale to actual size
            scaled_pixmap = pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, 
                                       Qt.TransformationMode.SmoothTransformation)
            
            return QIcon(scaled_pixmap)
        
        def _on_status_changed(self, status: str, reason: str, stats: dict):
            """Handle status change from updater."""
            self._current_status = status
            self._current_reason = reason
            self._current_stats = stats
            self._update_icon()

        @staticmethod
        def _find_main_window():
            try:
                from app_window import MainWindow
                for w in QApplication.topLevelWidgets():
                    if isinstance(w, MainWindow):
                        return w
            except Exception:
                pass
            return None

        def _open_dashboard(self):
            """Raise the existing MainWindow on the Dashboard page."""
            try:
                from core.constants import PAGE_DASHBOARD
                win = self._find_main_window()
                if win is None:
                    return
                win.showNormal()
                win.raise_()
                win.activateWindow()
                if win._sidebar.isVisible():
                    win._navigate_to(PAGE_DASHBOARD)
            except Exception as e:
                print(f"Failed to open dashboard: {e}")

        def _open_settings(self):
            """Raise the existing MainWindow on the Account page."""
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

# Distance-calibration file — overrides WEBCAM_FOCAL_LENGTH_PX when present.

# Posture snapshot storage — one JPEG saved per SNAPSHOT_EVERY_N seconds.
# Snapshots older than SNAPSHOT_RETENTION seconds are auto-pruned so the
# folder never grows beyond ~1 hour of frames.
SNAPSHOTS_DIR      = os.path.join(_APP_DIR, "data", "snapshots")
SNAPSHOT_RETENTION = 3600   # keep last 1 hour
_SNAPSHOT_EVERY_N  = 60     # save every N inference-frames (~6 Hz => every ~10 s)
_snapshot_counter: int = 0

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("posture")

# ---------------------------------------------------------------------------
# Try to reuse the shared inference module from Disease Prediction project.
# It handles its own ONNX session lifecycle and has the same label mapping.
# ---------------------------------------------------------------------------
_infer_predict_posture = None
try:
    _DISEASE_PRED_DIR = r"D:\Disease Prediction"
    if _DISEASE_PRED_DIR not in sys.path:
        sys.path.insert(0, _DISEASE_PRED_DIR)
    from inference_new_models import predict_posture_from_landmarks as _infer_predict_posture  # noqa: E402
    log.info("Posture: using inference_new_models.predict_posture_from_landmarks")
except Exception as _ie:
    log.warning("inference_new_models not importable (%s) — using built-in ONNX classifier.", _ie)

# ---------------------------------------------------------------------------
# Helper: load owner face encoding once at startup
# ---------------------------------------------------------------------------


def _softmax(x):
    e = np.exp(x - np.max(x))
    return e / e.sum()


def _load_calibrated_focal() -> float:
    """
    Return the user-calibrated focal length in pixels if a calibration file
    exists, otherwise fall back to WEBCAM_FOCAL_LENGTH_PX.
    The calibration file stores a correction multiplier applied on top of
    WEBCAM_FOCAL_LENGTH_PX, so the value is always relative to the current
    default and stays valid even if the constant is changed.
    """
    try:
        with open(_CALIBRATION_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        multiplier = float(data.get("multiplier", 1.0))
        if 0.05 < multiplier < 20.0:     # sanity bounds
            return WEBCAM_FOCAL_LENGTH_PX * multiplier
    except Exception:
        pass
    return WEBCAM_FOCAL_LENGTH_PX


def _get_screen_info() -> dict:
    """
    Detect the primary display resolution and physical size (Windows only).
    Uses GDI32 GetDeviceCaps which reads the EDID-reported size — no WMI needed.

    Returns a dict with:
        width_px, height_px          — screen resolution in pixels
        width_mm, height_mm          — physical dimensions in mm
        diagonal_inches              — diagonal screen size in inches
        recommended_min_cm           — 1.5 × diagonal (minimum safe distance)
        recommended_max_cm           — 2.5 × diagonal (maximum comfortable distance)
    """
    info: dict = {
        "width_px": 1920, "height_px": 1080,
        "width_mm": 527,  "height_mm": 296,
        "diagonal_inches": 23.8,
        "recommended_min_cm": 60,
        "recommended_max_cm": 100,
    }
    try:
        import ctypes
        user32 = ctypes.windll.user32
        info["width_px"]  = user32.GetSystemMetrics(0)
        info["height_px"] = user32.GetSystemMetrics(1)

        # GetDeviceCaps HORZSIZE / VERTSIZE return physical mm via EDID
        gdi32 = ctypes.windll.gdi32
        dc    = gdi32.CreateDCW("DISPLAY", None, None, None)
        if dc:
            w_mm = gdi32.GetDeviceCaps(dc, 4)   # HORZSIZE
            h_mm = gdi32.GetDeviceCaps(dc, 6)   # VERTSIZE
            gdi32.DeleteDC(dc)
            if w_mm > 50 and h_mm > 30:   # sanity: ignore obviously wrong values
                info["width_mm"]  = w_mm
                info["height_mm"] = h_mm
                diag_mm = (w_mm ** 2 + h_mm ** 2) ** 0.5
                info["diagonal_inches"] = round(diag_mm / 25.4, 1)
    except Exception as exc:
        log.warning("Screen size detection failed (%s) — using 24\" defaults.", exc)

    diag_cm = info["diagonal_inches"] * 2.54
    info["recommended_min_cm"] = int(round(diag_cm * 1.5))
    info["recommended_max_cm"] = int(round(diag_cm * 2.5))
    log.info(
        "Screen: %dx%d px  %.1f\"  recommended distance %d-%d cm",
        info["width_px"], info["height_px"],
        info["diagonal_inches"],
        info["recommended_min_cm"], info["recommended_max_cm"],
    )
    return info


def _load_posture_model():
    """Load the ONNX posture classifier. Returns session or None."""
    if not os.path.isfile(POSTURE_ONNX_PATH):
        log.warning("Posture ONNX model not found at %s — ONNX classifier disabled.", POSTURE_ONNX_PATH)
        return None
    try:
        sess = ort.InferenceSession(POSTURE_ONNX_PATH, providers=["CPUExecutionProvider"])
        log.info("Posture ONNX model loaded from %s", POSTURE_ONNX_PATH)
        return sess
    except Exception as exc:
        log.error("Failed to load posture ONNX model: %s", exc)
        return None


def _classify_posture_onnx(sess, lm):
    """
    Run posture inference on MediaPipe pose landmarks.

    Feature layout — 5 body midpoints (nose + 4 centred pairs), matches the
    MMPose training distribution:
      kp0: nose          → MP 0
      kp1: mid-shoulder  → avg(MP11, MP12)
      kp2: mid-hip       → avg(MP23, MP24)
      kp3: mid-knee      → avg(MP25, MP26)
      kp4: mid-ankle     → avg(MP27, MP28)
    Zero-padded to 24 features (training format).

    Delegates to inference_new_models.predict_posture_from_landmarks when
    available; falls back to direct ONNX if that import failed.

    Returns (label, confidence) where label is 'good' or 'bad'.
    """
    def _xy(pt):
        try:
            return float(getattr(pt, "x", 0.0)), float(getattr(pt, "y", 0.0))
        except Exception:
            return float(pt.get("x", 0.0)), float(pt.get("y", 0.0))

    def _mid(a, b):
        ax, ay = _xy(a); bx, by = _xy(b)
        return (ax + bx) * 0.5, (ay + by) * 0.5

    nose_x,  nose_y  = _xy(lm[0])
    msho_x,  msho_y  = _mid(lm[11], lm[12])   # mid-shoulder
    mhip_x,  mhip_y  = _mid(lm[23], lm[24])   # mid-hip
    mkne_x,  mkne_y  = _mid(lm[25], lm[26])   # mid-knee
    mank_x,  mank_y  = _mid(lm[27], lm[28])   # mid-ankle

    # Five [x, y] pairs — predict_posture_from_landmarks flattens these to
    # 10 floats and zero-pads to 24, matching the training format exactly.
    keypoints = [
        [nose_x,  nose_y],
        [msho_x,  msho_y],
        [mhip_x,  mhip_y],
        [mkne_x,  mkne_y],
        [mank_x,  mank_y],
    ]

    # ── Primary: shared inference module ─────────────────────────────────
    if _infer_predict_posture is not None:
        lbl, conf, _ = _infer_predict_posture(keypoints)
        # Module returns "Good Form" / "Bad Form"; normalise to 'good' / 'bad'
        label = "good" if lbl.lower().startswith("good") else "bad"
        return label, float(conf)

    # ── Fallback: direct ONNX ─────────────────────────────────────────────
    features = np.array(
        [nose_x, nose_y, msho_x, msho_y, mhip_x, mhip_y,
         mkne_x, mkne_y, mank_x, mank_y] + [0.0] * 14,
        dtype=np.float32,
    ).reshape(1, 24)

    input_name = sess.get_inputs()[0].name
    logits = sess.run(None, {input_name: features})[0][0]
    probs  = _softmax(logits)
    idx    = int(np.argmax(probs))
    conf   = float(probs[idx])
    label  = "good" if idx == 0 else "bad"
    return label, conf


def _load_owner_encoding():
    """Return the 128-d face encoding for the reference image, or None."""
    if not os.path.isfile(OWNER_IMAGE_PATH):
        log.warning("owner.jpg not found at %s — identity lock disabled.", OWNER_IMAGE_PATH)
        return None
    img = face_recognition.load_image_file(OWNER_IMAGE_PATH)
    encodings = face_recognition.face_encodings(img)
    if not encodings:
        log.warning("No face detected in owner.jpg — identity lock disabled.")
        return None
    log.info("Owner face encoding loaded successfully.")
    return encodings[0]


# ---------------------------------------------------------------------------
# Posture math
# ---------------------------------------------------------------------------


def _midpoint(a, b):
    """Average two landmarks (y, z only)."""
    return ((a.y + b.y) / 2.0, (a.z + b.z) / 2.0)


def compute_posture(landmarks):
    """
    Return (posture_label, ear_y, shoulder_y, hip_y, fwd_angle).

    posture_label: 'good' | 'bad'
    fwd_angle:     degrees; positive means head is forward of torso line.
    """
    lm = landmarks

    ear_y, ear_z = _midpoint(lm[L_EAR], lm[R_EAR])
    sho_y, sho_z = _midpoint(lm[L_SHOULDER], lm[R_SHOULDER])
    hip_y, hip_z = _midpoint(lm[L_HIP], lm[R_HIP])

    # Vectors in the (Z, Y) plane — Z is depth, Y is vertical
    vec_torso = (sho_z - hip_z, sho_y - hip_y)
    vec_neck = (ear_z - sho_z, ear_y - sho_y)

    cross = vec_neck[0] * vec_torso[1] - vec_neck[1] * vec_torso[0]
    dot = vec_neck[0] * vec_torso[0] + vec_neck[1] * vec_torso[1]
    angle = degrees(atan2(cross, dot))

    label = "bad" if abs(angle) > BAD_POSTURE_THRESHOLD else "good"
    return label, ear_y, sho_y, hip_y, angle


# ---------------------------------------------------------------------------
# Notification helper (throttled by caller)
# ---------------------------------------------------------------------------


def save_config(config):
    """Save app configuration to file."""
    try:
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        with open(_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as exc:
        log.error("Failed to save config: %s", exc)


def _notify_camera_busy() -> None:
    """Alert: another app has grabbed the camera — tracking paused."""
    if not _config.get("notifications_enabled", True):
        return
    if not _user_signed_in():
        return
    try:
            notification.notify(
            title="Camera In Use — Tracking Paused",
            message=(
                "Another application has taken over the camera.\n"
                "Posture tracking will automatically resume once it is available again."
            ),
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=15,
        )
    except Exception as exc:
        log.error("Camera-busy notification failed: %s", exc)


def _notify_camera_resumed() -> None:
    """Alert: camera is free again — tracking resumed."""
    if not _config.get("notifications_enabled", True):
        return
    if not _user_signed_in():
        return
    try:
        notification.notify(
            title="Camera Available — Tracking Resumed",
            message="The camera is free again. Posture tracking has resumed.",
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=10,
        )
    except Exception as exc:
        log.error("Camera-resumed notification failed: %s", exc)


def _notify_bad_posture():
    """General slouch alert."""
    if not _config.get("notifications_enabled", True):
        return
    if not _user_signed_in():
        return
    try:
        alert_msg = f"You've been slouching for {_config.get('alert_timing_seconds', 30)} seconds. Sit up straight!"
        notification.notify(
            title="Posture Alert",
            message=alert_msg,
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=10,
        )
    except Exception as exc:
        log.error("Notification failed: %s", exc)


def _notify_take_break():
    """30-5 rule: take a movement break after 30 min of continuous sitting."""
    if not _user_signed_in():
        return
    try:
        notification.notify(
            title="Time to Move! (⏱ 30 min)",
            message="You've been sitting for 30 minutes. Stand up and move or stretch for at least 5 minutes.",
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=20,
        )
    except Exception as exc:
        log.error("Break notification failed: %s", exc)


def _notify_eye_break():
    """20-20-20 rule: rest eyes every 20 minutes."""
    if not _user_signed_in():
        return
    try:
        notification.notify(
            title="Eye Break — 20-20-20",
            message="Look at something 20 feet away for 20 seconds to reduce eye strain.",
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=15,
        )
    except Exception as exc:
        log.error("Eye-break notification failed: %s", exc)


def _notify_chin_forward():
    """Chin / forward-head protrusion alert."""
    if not _user_signed_in():
        return
    try:
        notification.notify(
            title="Head Posture Alert",
            message="Tuck your chin in slightly — your head is protruding forward.",
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=10,
        )
    except Exception as exc:
        log.error("Chin-forward notification failed: %s", exc)


def _notify_head_tilt(deg: float) -> None:
    """Lateral head tilt alert — head dropped to one side."""
    side = "left" if deg > 0 else "right"   # positive = right ear lower
    if not _user_signed_in():
        return
    try:
        notification.notify(
            title="Head Tilt Detected",
            message=(
                f"Your head is tilted ~{abs(deg):.0f}° to the {side}. "
                "Level your head and relax your neck muscles."
            ),
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=10,
        )
    except Exception as exc:
        log.error("Head-tilt notification failed: %s", exc)


def _notify_lean_back() -> None:
    """Torso recline alert — leaning back too far in the chair."""
    if not _user_signed_in():
        return
    try:
        notification.notify(
            title="Posture Alert — Leaning Back",
            message=(
                "You're reclining too far. Sit upright with your lower back "
                "supported and your feet flat on the floor."
            ),
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=10,
        )
    except Exception as exc:
        log.error("Lean-back notification failed: %s", exc)


def _notify_shoulder_uneven():
    """One shoulder significantly closer to or lower than the other."""
    if not _user_signed_in():
        return
    try:
        notification.notify(
            title="Shoulder Alignment Alert",
            message="Your shoulders are uneven or rolled. Sit evenly and relax your shoulders down.",
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=10,
        )
    except Exception as exc:
        log.error("Shoulder notification failed: %s", exc)


def _notify_too_close(dist_cm: int, min_cm: int) -> None:
    """Alert when the user is sitting closer than the recommended minimum distance."""
    if not _user_signed_in():
        return
    try:
        notification.notify(
            title="Too Close to Screen!",
            message=(
                "You are sitting too close to your screen.  "
                "Move your chair back or push the monitor further away."
            ),
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=10,
        )
    except Exception as exc:
        log.error("Too-close notification failed: %s", exc)


def _notify_too_far(dist_cm: int, max_cm: int) -> None:
    """Alert when the user is sitting further than the recommended maximum distance."""
    if not _user_signed_in():
        return
    try:
        notification.notify(
            title="Too Far from Screen",
            message=(
                "You are sitting too far from your screen.  "
                "Lean in slightly or move your chair forward."
            ),
            app_name=APP_NAME,
            app_icon=_APP_ICON,
            timeout=12,
        )
    except Exception as exc:
        log.error("Too-far notification failed: %s", exc)


# ---------------------------------------------------------------------------
# Live feed writers
# ---------------------------------------------------------------------------


def _write_live_frame(bgr_frame) -> None:
    """Atomically write the latest camera frame as JPEG for the dashboard."""
    try:
        ok, buf = cv2.imencode(".jpg", bgr_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            tmp = _LIVE_FRAME_PATH + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(buf.tobytes())
            os.replace(tmp, _LIVE_FRAME_PATH)
    except Exception:
        pass


def _write_live_stats(stats: dict) -> None:
    """Atomically write the latest posture stats as JSON for the dashboard."""
    try:
        tmp = _LIVE_STATS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(stats, fh)
        os.replace(tmp, _LIVE_STATS_PATH)
    except Exception:
        pass


def _save_snapshot(bgr_frame, label: str) -> None:
    """
    Save a labelled posture frame to SNAPSHOTS_DIR every _SNAPSHOT_EVERY_N calls.
    Files are named  YYYYMMDD_HHMMSS_{label}.jpg  and auto-pruned when older
    than SNAPSHOT_RETENTION seconds so the folder never exceeds ~1 hour.
    """
    global _snapshot_counter
    _snapshot_counter += 1
    if _snapshot_counter % _SNAPSHOT_EVERY_N != 0:
        return
    try:
        os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
        fname = f"{time.strftime('%Y%m%d_%H%M%S')}_{label}.jpg"
        ok, buf = cv2.imencode(".jpg", bgr_frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if ok:
            with open(os.path.join(SNAPSHOTS_DIR, fname), "wb") as fh:
                fh.write(buf.tobytes())
        # Prune snapshots older than SNAPSHOT_RETENTION
        cutoff = time.time() - SNAPSHOT_RETENTION
        for fn in os.listdir(SNAPSHOTS_DIR):
            fp = os.path.join(SNAPSHOTS_DIR, fn)
            try:
                if os.path.getmtime(fp) < cutoff:
                    os.remove(fp)
            except Exception:
                pass
    except Exception as exc:
        log.debug("Snapshot save failed: %s", exc)


# ---------------------------------------------------------------------------
# Tracking loop (runs in worker thread)
# ---------------------------------------------------------------------------


def tracking_loop(stop_event: threading.Event, owner_encoding, posture_sess):
    """
    Capture one frame per second, run MediaPipe Pose, verify identity once,
    compute posture, log to DB, and conditionally notify.
    """
    # ── Camera open (DirectShow on Windows for reliable auto-exposure) ──────
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(0, backend)
    if not cap.isOpened():
        log.error("Cannot open camera — tracking aborted.")
        return

    # Request a sensible resolution so the driver initialises properly.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # ── Warm-up: give the camera 2 seconds to settle ────────────────────────
    log.info("Camera opened — warming up for 2 seconds…")
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        cap.read()

    # Prefer the classic solutions API when available
    if mp_solutions is not None:
        mp_pose = mp_solutions.pose
        pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=0,       # lightest model
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        use_tasks = False
    elif mp_tasks is not None:
        # Tasks API is available; prefer to use a .task model (lite first,
        # then full). If none found, fall back to a lightweight OpenCV
        # face-based heuristic so the tracker can still run in degraded mode.
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(base_dir, "pose_landmarker_lite.task"),
            os.path.join(base_dir, "pose_landmarker_full.task"),
            os.path.join(base_dir, "pose_landmarker.task"),
        ]
        found_model = next((p for p in candidates if os.path.isfile(p)), None)
        if found_model:
            # Import classes from the tasks API
            BaseOptions = mp_tasks["BaseOptions"]
            vision = mp_tasks["vision"]
            PoseLandmarker = vision.PoseLandmarker
            PoseLandmarkerOptions = vision.PoseLandmarkerOptions
            RunningMode = vision.RunningMode

            base_options = BaseOptions(model_asset_path=found_model)
            options = PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            pose = PoseLandmarker.create_from_options(options)
            use_tasks = True
            log.info("Using MediaPipe Tasks model: %s", found_model)
        else:
            log.warning(
                "mediapipe Tasks API available but no .task model found in %s.\n"
                "Falling back to OpenCV face-based heuristic (degraded accuracy).",
                base_dir,
            )
            pose = None
            use_tasks = False
            # Setup face detector fallback
            try:
                face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            except Exception:
                face_cascade = None
    else:
        log.error(
            "mediapipe.solutions API not found in installed mediapipe.\n"
            "Please install a mediapipe build that provides `mediapipe.solutions` (e.g. a compatible pip wheel),\n"
            "or provide a PoseLandmarker .task model for the Tasks API. Tracking will not start."
        )
        cap.release()
        return

    # State
    is_owner = False
    body_gone_since: float | None = None
    bad_streak_start:  float | None = None  # monotonic time when current bad streak began
    last_bad_notify    = 0.0               # last time bad-posture notification fired
    identity_checked_this_session = False
    label_history: deque = deque(maxlen=LABEL_SMOOTH_WINDOW)  # temporal smoothing
    # Fallback baseline for face-based heuristic (width in pixels)
    baseline_face_width = None
    baseline_face_center_y = None
    # Reference ear-shoulder ratio for camera-specific neutral posture.
    # If None, defaults to 0.70 (upright). We set this once after owner
    # verification to compensate for cameras placed below/above neck level.
    reference_ear_sho_ratio = None
    use_fallback = 'face_cascade' in locals() and locals().get('face_cascade') is not None

    # ── Time-based rule state ────────────────────────────────────────────────
    sit_start_time: float | None = None   # monotonic time when owner was first seen
    last_sit_break_notify  = 0.0          # last time sitting-break alert fired
    last_eye_break_notify  = 0.0          # last time eye-break alert fired
    last_chin_notify       = 0.0          # last time chin-forward alert fired
    last_shoulder_notify   = 0.0          # last time shoulder-uneven alert fired
    chin_bad_streak        = 0            # consecutive frames where chin is forward
    shoulder_bad_streak    = 0            # consecutive frames where shoulders are uneven
    head_tilt_streak       = 0            # consecutive frames where head is laterally tilted
    last_tilt_notify       = 0.0          # last time head-tilt alert fired
    head_tilt_deg_now      = 0.0          # latest tilt angle (signed, degrees)
    lean_back_streak       = 0            # consecutive frames where torso is reclined
    last_lean_back_notify  = 0.0          # last time lean-back alert fired
    torso_lean_z           = 0.0          # latest shoulder-z minus hip-z value
    _screen_info           = _get_screen_info()   # display size for distance recommendations
    last_dist_notify       = 0.0          # last time distance alert (close or far) fired
    dist_close_streak      = 0            # consecutive frames where user is too close
    dist_far_streak        = 0            # consecutive frames where user is too far
    
    # Config reload tracking
    last_config_reload     = time.monotonic()
    CONFIG_RELOAD_INTERVAL = 10.0  # Check config every 10 seconds

    # Frame-skip: update preview buffer every frame; run inference every Nth frame.
    # Camera cap.read() already throttles to camera FPS so no sleep is needed.
    _frame_counter = 0
    INFER_EVERY    = 5   # inference at ~camera_fps/5  (≈6 Hz for a 30fps cam)

    # Camera-busy recovery state
    _consec_failures  = 0
    _BUSY_THRESHOLD   = 10   # consecutive failed reads before declaring camera busy
    _cam_busy_active  = False

    log.info("Tracking loop started.")
    try:
        notification.notify(
            title=f"{APP_NAME} Started",
            message=(
                f"Screen detected: {_screen_info['diagonal_inches']:.1f}\" "
                f"({_screen_info['width_px']}×{_screen_info['height_px']})\n"
                f"Sit {_screen_info['recommended_min_cm']}–{_screen_info['recommended_max_cm']} cm "
                "from your screen for healthy viewing distance."
            ),
            app_name=APP_NAME,
            timeout=12,
        )
    except Exception as exc:
        log.error("Startup notification failed: %s", exc)

    while not stop_event.is_set():
        # Check for config reload periodically
        now = time.monotonic()
        if now - last_config_reload >= CONFIG_RELOAD_INTERVAL:
            reload_config()
            last_config_reload = now
            
        ret, frame = cap.read()
        if not ret:
            _consec_failures += 1
            if _consec_failures >= _BUSY_THRESHOLD:
                # ── Camera grabbed by another application ─────────────────
                if not _cam_busy_active:
                    log.warning(
                        "Camera unavailable after %d consecutive failures — "
                        "another app may have taken it.",
                        _consec_failures,
                    )
                    _write_live_stats({
                        "label":  "camera_busy",
                        "reason": "Camera temporarily held by another application",
                    })
                    _notify_camera_busy()
                    _cam_busy_active = True
                    cap.release()

                # ── Poll every 2 s until the camera is free again ──────────
                while not stop_event.is_set():
                    _write_live_stats({
                        "label":  "camera_busy",
                        "reason": "Waiting for camera to become available…",
                    })
                    time.sleep(2.0)

                    probe = cv2.VideoCapture(0, backend)
                    if probe.isOpened():
                        ok2, _ = probe.read()
                        if ok2:
                            # Camera is free — take over this handle
                            cap = probe
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                            # Brief warm-up
                            for _ in range(6):
                                cap.read()
                            _consec_failures = 0
                            _cam_busy_active = False
                            log.info("Camera recovered — resuming tracking.")
                            _notify_camera_resumed()
                            break
                        else:
                            probe.release()
                    else:
                        probe.release()
            else:
                log.warning(
                    "Frame grab failed — retrying (%d/%d).",
                    _consec_failures,
                    _BUSY_THRESHOLD,
                )
                time.sleep(0.5)
            continue

        # Successful read — reset consecutive-failure counter
        _consec_failures = 0

        # ── Update MJPEG preview buffer on EVERY frame for smooth video ──
        try:
            small = cv2.resize(frame, (320, 240))
            ok, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 65])
            if ok:
                global _STREAM_FRAME_BYTES
                _STREAM_FRAME_BYTES = buf.tobytes()
        except Exception:
            pass

        # ── Skip heavy inference on non-inference frames ──
        _frame_counter += 1
        if _frame_counter % INFER_EVERY != 0:
            continue

        # Write disk fallback frame only on inference frames (reduces I/O)
        _write_live_frame(frame)

        # Convert BGR → RGB for MediaPipe
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Use the appropriate API call depending on which mediapipe backend we're using
        if 'use_tasks' in locals() and use_tasks and pose is not None:
            try:
                _mp_top = mp_tasks['mp']
                mp_image = _mp_top.Image(image_format=_mp_top.ImageFormat.SRGB, data=rgb)
                task_result = pose.detect(mp_image)
            except Exception as exc:
                log.error("PoseLandmarker detect failed: %s", exc)
                task_result = None

            n_poses = len(task_result.pose_landmarks) if task_result is not None else 0
            log.debug("PoseLandmarker: %d pose(s) detected.", n_poses)
            if task_result is not None and getattr(task_result, 'pose_landmarks', None):
                # Take the first detected pose
                pose_landmarks = task_result.pose_landmarks[0]
                if hasattr(pose_landmarks, 'landmark'):
                    lm = pose_landmarks.landmark
                elif hasattr(pose_landmarks, 'landmarks'):
                    lm = pose_landmarks.landmarks
                else:
                    lm = list(pose_landmarks)

                results = SimpleNamespace(pose_landmarks=SimpleNamespace(landmark=lm))
            else:
                results = SimpleNamespace(pose_landmarks=None)
        else:
            results = pose.process(rgb)

        if results.pose_landmarks:
            lm = results.pose_landmarks.landmark

            # Defensive check: ensure shoulder landmarks are present.
            max_sho_idx = max(L_SHOULDER, R_SHOULDER)
            try:
                lm_len = len(lm)
            except Exception:
                lm_len = 0
            if lm_len <= max_sho_idx:
                try:
                    import json
                    dump = []
                    for i, pt in enumerate(lm):
                        try:
                            x = float(getattr(pt, 'x', pt.get('x', None)))
                            y = float(getattr(pt, 'y', pt.get('y', None)))
                            z = float(getattr(pt, 'z', pt.get('z', None)))
                        except Exception:
                            # Fallback: try indexing if pt is a list/tuple
                            try:
                                x = float(pt[0]); y = float(pt[1]); z = float(pt[2]) if len(pt)>2 else None
                            except Exception:
                                x = y = z = None
                        dump.append({'i': i, 'x': x, 'y': y, 'z': z})
                    p = Path('tools') / 'last_landmarks.json'
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(json.dumps({'len': lm_len, 'landmarks': dump}, indent=2))
                    log.error("Shoulder landmarks missing (len=%d). Dumped to %s", lm_len, str(p))
                except Exception as _dump_err:
                    log.exception("Failed to dump landmarks: %s", _dump_err)
                # Skip frame processing when landmark layout is unexpected
                time.sleep(1)
                continue

            # ── Identity lock state machine ──────────────────────────
            body_gone_since = None  # body is present

            if not is_owner and not identity_checked_this_session:
                identity_checked_this_session = True
                if owner_encoding is not None:
                    # Run face_recognition ONCE per session
                    face_encs = face_recognition.face_encodings(rgb)
                    if face_encs:
                        match = face_recognition.compare_faces(
                            [owner_encoding], face_encs[0], tolerance=FACE_TOLERANCE
                        )
                        if match[0]:
                            is_owner = True
                            log.info("Owner verified — identity locked.")
                        else:
                            log.info("Face detected but not the owner — skipping.")
                    else:
                        log.info("No face encoding found in frame — will retry next session.")
                        identity_checked_this_session = False  # allow retry
                else:
                    # No owner image loaded — assume owner (graceful fallback)
                    is_owner = True

                # Calibrate neutral ear-shoulder ratio once when owner is first seen
                if is_owner and reference_ear_sho_ratio is None:
                    try:
                        reference_ear_sho_ratio = ear_sho_ratio_geo
                        log.info("Calibrated reference ear-shoulder ratio: %.3f", reference_ear_sho_ratio)
                    except Exception:
                        pass

            # ── Posture analysis (only for verified owner) ───────────
            if is_owner:
                # Helper: access a landmark attribute safely
                def _lv(pt, attr):
                    try:
                        return float(getattr(pt, attr, 0.0))
                    except Exception:
                        return float(pt.get(attr, 0.0))

                sho_width = abs(_lv(lm[12], "x") - _lv(lm[11], "x"))
                if sho_width < 0.05:   # pose barely visible – skip frame
                    time.sleep(1)
                    continue

                # ── Sitting-distance estimation (pinhole camera model) ────────────
                # shoulder_pixels = sho_width (normalised) × frame_width_px
                # distance_cm     = real_sho_width_cm × focal_px / shoulder_px
                # Focal length is loaded from the calibration file each frame
                # so the dashboard's "Calibrate" button takes effect immediately.
                try:
                    sho_px = sho_width * float(frame.shape[1])
                    _focal  = _load_calibrated_focal()
                    dist_cm = int(
                        (SHOULDER_WIDTH_CM * _focal) / sho_px
                    ) if sho_px > 5 else None
                except Exception:
                    sho_px  = 0.0
                    dist_cm = None

                label = None
                confidence = 0.0
                reason = "unknown"

                # Always compute ear/shoulder Y ratio — used for the stored
                # forward-head angle regardless of which classifier runs.
                ear_y_geo = (_lv(lm[7],  "y") + _lv(lm[8],  "y")) / 2
                sho_y_geo = (_lv(lm[11], "y") + _lv(lm[12], "y")) / 2
                ear_sho_ratio_geo = (sho_y_geo - ear_y_geo) / sho_width
                # Use a session-specific reference ratio (calibrated once after
                # owner verification) to compensate for camera elevation. If not
                # set, default to 0.70 which maps to 0°.
                ref_ratio = reference_ear_sho_ratio if reference_ear_sho_ratio is not None else 0.70
                # Scale to degrees: ref_ratio -> 0°, smaller ratios -> positive forward angle.
                # Use a slightly larger gain so small neck drops produce larger angle estimates.
                fwd_angle_est = max(0.0, min(45.0, (ref_ratio - ear_sho_ratio_geo) * 75.0))

                # ── Chin-forward detection (z-axis) ──────────────────────────
                # In MediaPipe z is negative when a point is closer to the
                # camera. If nose_z is appreciably less than mid-shoulder z the
                # chin / head is protruding forward.
                try:
                    _nose_z  = _lv(lm[0],           'z')
                    _msho_z  = (_lv(lm[L_SHOULDER], 'z') + _lv(lm[R_SHOULDER], 'z')) * 0.5
                    _chin_z_diff = _msho_z - _nose_z   # positive when nose is nearer to camera
                    chin_bad_frame = _chin_z_diff > CHIN_FORWARD_Z_THRESHOLD
                except Exception:
                    chin_bad_frame = False

                # ── Lateral head-tilt detection (ear-to-ear line angle) ──────
                # Compute the signed angle of the line joining R_EAR → L_EAR
                # relative to horizontal. Value is positive when right ear is
                # lower (head tilted right) and negative when left ear is lower.
                # Small values (±5°) are normal head micro-movements; HEAD_TILT_THRESHOLD
                # catches sustained lateral lean.
                try:
                    _lex = _lv(lm[L_EAR], 'x');  _ley = _lv(lm[L_EAR], 'y')
                    _rex = _lv(lm[R_EAR], 'x');  _rey = _lv(lm[R_EAR], 'y')
                    _ear_dx = abs(_rex - _lex)     # always positive — ignore mirror orientation
                    _ear_dy = _rey - _ley          # positive when right ear is lower (head tilts right)
                    head_tilt_deg_now = degrees(atan2(_ear_dy, _ear_dx)) if _ear_dx > 0.01 else 0.0
                    head_tilt_bad_frame = abs(head_tilt_deg_now) > HEAD_TILT_THRESHOLD
                except Exception:
                    head_tilt_deg_now   = 0.0
                    head_tilt_bad_frame = False

                # ── Lean-back torso detection (shoulder z vs hip z) ──────────
                # In MediaPipe's normalised space z increases as the landmark
                # moves away from the camera.  When the torso reclines the
                # shoulders drift behind the hips, so mid_sho_z > mid_hip_z.
                try:
                    _lb_sho_z = (_lv(lm[L_SHOULDER], 'z') + _lv(lm[R_SHOULDER], 'z')) * 0.5
                    _lb_hip_z = (_lv(lm[L_HIP],      'z') + _lv(lm[R_HIP],      'z')) * 0.5
                    torso_lean_z        = _lb_sho_z - _lb_hip_z   # positive = leaning back
                    lean_back_bad_frame = torso_lean_z > LEAN_BACK_Z_THRESHOLD
                except Exception:
                    torso_lean_z        = 0.0
                    lean_back_bad_frame = False

                # ── Shoulder-uneven detection (roll OR depth OR asym) ────────
                # Computed later in the heuristic block; set a flag here so it
                # can be read by the per-notification-cooldown logic below.
                shoulder_bad_frame = False   # updated after heuristic

                # ── Primary: ONNX classifier ──────────────────────────
                if posture_sess is not None:
                    try:
                        label, confidence = _classify_posture_onnx(posture_sess, lm)
                        reason = f"onnx conf={confidence:.2f}"
                    except Exception as exc:
                        log.error("ONNX inference error: %s", exc)
                        label = None

                # ── Fallback: Y-only geometry heuristic ───────────────────
                # Two checks only — both use stable 2-D Y coordinates.
                # Nose check removed: too sensitive to camera elevation.
                if label is None or confidence < ONNX_CONF_THRESHOLD:
                    ear_y   = (_lv(lm[7],  "y") + _lv(lm[8],  "y")) / 2
                    sho_y   = (_lv(lm[11], "y") + _lv(lm[12], "y")) / 2
                    l_sho_y = _lv(lm[11], "y")
                    r_sho_y = _lv(lm[12], "y")

                    # Y increases downward in image space.
                    # ear_sho_ratio > 0 means ears are above shoulders (good).
                    ear_sho_ratio = (sho_y - ear_y) / sho_width
                    sho_asym      = abs(l_sho_y - r_sho_y) / sho_width

                    # Shoulder roll (tilt) in degrees: positive when right shoulder
                    # is lower than left. Compute from delta-y / delta-x.
                    try:
                        l_sho_x = _lv(lm[L_SHOULDER], 'x')
                        r_sho_x = _lv(lm[R_SHOULDER], 'x')
                        dx = r_sho_x - l_sho_x
                        dy = r_sho_y - l_sho_y
                        sho_roll_rad = atan2(dy, dx) if dx != 0 else (1.5708 if dy > 0 else -1.5708)
                        sho_roll_deg = abs(degrees(sho_roll_rad))
                    except Exception:
                        sho_roll_deg = 0.0

                    # Depth asymmetry using landmark 'z' coordinates (normalized).
                    try:
                        l_sho_z = _lv(lm[L_SHOULDER], 'z')
                        r_sho_z = _lv(lm[R_SHOULDER], 'z')
                        sho_depth_diff = abs(l_sho_z - r_sho_z)
                    except Exception:
                        sho_depth_diff = 0.0

                    log.debug(
                        "Heuristic | ear_sho=%.3f asym=%.3f "
                        "(thresholds ear>%.2f asym<%.2f)",
                        ear_sho_ratio, sho_asym,
                        EAR_SHO_THRESHOLD, SHO_ASYM_THRESHOLD,
                    )

                    neck_bad  = ear_sho_ratio  < EAR_SHO_THRESHOLD
                    lean_bad  = sho_asym       > SHO_ASYM_THRESHOLD
                    roll_bad  = sho_roll_deg   > SHO_ROLL_THRESHOLD
                    depth_bad = sho_depth_diff > SHO_DEPTH_THRESHOLD
                    tilt_bad  = head_tilt_bad_frame   # computed above, always available
                    back_bad  = lean_back_bad_frame   # computed above, always available

                    raw_label = "bad" if (neck_bad or lean_bad or roll_bad or depth_bad or tilt_bad or back_bad) else "good"
                    parts = []
                    if neck_bad:  parts.append(f"ear_sho={ear_sho_ratio:.2f}<{EAR_SHO_THRESHOLD}")
                    if lean_bad:  parts.append(f"asym={sho_asym:.2f}>{SHO_ASYM_THRESHOLD}")
                    if roll_bad:  parts.append(f"roll={sho_roll_deg:.1f}\u00b0>{SHO_ROLL_THRESHOLD}")
                    if depth_bad: parts.append(f"depth_diff={sho_depth_diff:.3f}>{SHO_DEPTH_THRESHOLD}")
                    if tilt_bad:  parts.append(f"head_tilt={head_tilt_deg_now:.1f}\u00b0>{HEAD_TILT_THRESHOLD}")
                    reason = "fallback: " + (", ".join(parts) or "OK")

                    # Compute a combined pseudo-confidence from the strongest signal.
                    ear_margin   = abs(ear_sho_ratio - EAR_SHO_THRESHOLD) / max(EAR_SHO_THRESHOLD, 0.01)
                    roll_margin  = abs(sho_roll_deg - SHO_ROLL_THRESHOLD)  / max(SHO_ROLL_THRESHOLD, 1.0)
                    depth_margin = sho_depth_diff / max(SHO_DEPTH_THRESHOLD, 1e-6)
                    back_margin  = torso_lean_z   / max(LEAN_BACK_Z_THRESHOLD, 1e-6)
                    combined = max(ear_margin, roll_margin, depth_margin, back_margin)
                    confidence = float(min(1.0, combined))

                    # Mark shoulder-uneven for the cooldown notifier below
                    shoulder_bad_frame = roll_bad or depth_bad or lean_bad

                    # ── Temporal smoothing: majority vote over last N frames ────
                    label_history.append(raw_label)
                    bad_count  = label_history.count("bad")
                    good_count = label_history.count("good")
                    if len(label_history) >= LABEL_SMOOTH_WINDOW:
                        label = "bad" if bad_count > good_count else "good"
                    else:
                        label = raw_label  # not enough history yet — use raw

                # User rule: if forward-head angle (fd) is very small, consider it good.
                try:
                    if fwd_angle_est <= 3.0:
                        label = 'good'
                        confidence = max(confidence, 0.99)
                        reason = (reason + '; fd<=3 override') if reason else 'fd<=3 override'
                except Exception:
                    pass

                # Lateral tilt overrides a good verdict regardless of forward angle.
                # A visibly tilted head is always bad posture.
                if head_tilt_bad_frame and label == 'good':
                    label = 'bad'
                    confidence = min(1.0, abs(head_tilt_deg_now) / HEAD_TILT_THRESHOLD)
                    reason = (reason + f'; head_tilt={head_tilt_deg_now:.1f}\u00b0') if reason else f'head_tilt={head_tilt_deg_now:.1f}\u00b0'

                log.info("Posture: %s | %s (fwd≈%.1f°)", label, reason, fwd_angle_est)
                # Update per-issue streak counters for the current frame so the
                # live stats reflect the most recent values (used by the UI dials).
                if chin_bad_frame:
                    chin_bad_streak += 1
                else:
                    chin_bad_streak = 0

                if shoulder_bad_frame:
                    shoulder_bad_streak += 1
                else:
                    shoulder_bad_streak = 0

                if head_tilt_bad_frame:
                    head_tilt_streak += 1
                else:
                    head_tilt_streak = 0

                if lean_back_bad_frame:
                    lean_back_streak += 1
                else:
                    lean_back_streak = 0

                _snap_now = time.monotonic()
                _write_live_stats({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "body_detected": True,
                    "is_owner": True,
                    "label": label,
                    "confidence": round(float(confidence), 3),
                    "reason": reason,
                    "fwd_angle": round(float(fwd_angle_est), 1),
                    "chin_streak": chin_bad_streak,
                    "shoulder_streak": shoulder_bad_streak,
                    "head_tilt_deg": round(float(head_tilt_deg_now), 1),
                    "head_tilt_streak": head_tilt_streak,
                    "torso_lean_z": round(float(torso_lean_z), 3),
                    "lean_back_streak": lean_back_streak,
                    # elapsed seconds in current consecutive bad-posture streak
                    "bad_streak_sec": int(_snap_now - bad_streak_start) if (bad_streak_start is not None and label == "bad") else 0,
                    "sit_elapsed_sec": int(_snap_now - sit_start_time) if sit_start_time is not None else 0,
                    "eye_elapsed_sec": int(_snap_now - last_eye_break_notify),
                    "dist_cm":      dist_cm,
                    "shoulder_px":  round(float(sho_px), 1),
                    "dist_min_cm":  _screen_info["recommended_min_cm"],
                    "dist_max_cm":  _screen_info["recommended_max_cm"],
                    "screen_in":    _screen_info["diagonal_inches"],
                    "screen_res":   f"{_screen_info['width_px']}x{_screen_info['height_px']}",
                })
                _save_snapshot(frame, label)
                # ── Bad-posture streak: wall-clock seconds, cooldown-gated ──────
                _now = time.monotonic()
                if label == "bad":
                    if bad_streak_start is None:
                        bad_streak_start = _now
                    _bad_elapsed = _now - bad_streak_start
                    # Fire when the streak has lasted the configured interval AND
                    # we haven't fired again within that same interval (hard floor 30 s)
                    _bad_cooldown = max(float(BAD_STREAK_LIMIT), 30.0)
                    if _bad_elapsed >= BAD_STREAK_LIMIT and (_now - last_bad_notify) >= _bad_cooldown:
                        _notify_bad_posture()
                        last_bad_notify  = _now
                        bad_streak_start = _now   # reset window so next alert needs another full interval
                else:
                    bad_streak_start = None   # good/no-body frame resets the streak

                # ── Per-issue cooldown notifications ─────────────────────────

                if chin_bad_streak >= CHIN_STREAK_LIMIT and (_now - last_chin_notify) > BREAK_COOLDOWN:
                    _notify_chin_forward()
                    last_chin_notify = _now
                    chin_bad_streak = 0

                if shoulder_bad_streak >= SHOULDER_STREAK_LIMIT and (_now - last_shoulder_notify) > BREAK_COOLDOWN:
                    _notify_shoulder_uneven()
                    last_shoulder_notify = _now
                    shoulder_bad_streak = 0

                if head_tilt_streak >= HEAD_TILT_STREAK_LIMIT and (_now - last_tilt_notify) > BREAK_COOLDOWN:
                    _notify_head_tilt(head_tilt_deg_now)
                    last_tilt_notify = _now
                    head_tilt_streak = 0

                if lean_back_streak >= LEAN_BACK_STREAK_LIMIT and (_now - last_lean_back_notify) > BREAK_COOLDOWN:
                    _notify_lean_back()
                    last_lean_back_notify = _now
                    lean_back_streak = 0

                # Sitting-break timer (30-5 rule)
                if sit_start_time is None:
                    sit_start_time = _now
                    last_eye_break_notify = _now   # sync eye timer to session start
                sit_elapsed = _now - sit_start_time
                if sit_elapsed >= SIT_BREAK_INTERVAL and (_now - last_sit_break_notify) > BREAK_COOLDOWN:
                    _notify_take_break()
                    last_sit_break_notify = _now
                    log.info("Sitting break reminder fired (%.0f min sitting).", sit_elapsed / 60)

                # Eye-break timer (20-20-20)
                if (_now - last_eye_break_notify) >= EYE_BREAK_INTERVAL:
                    _notify_eye_break()
                    last_eye_break_notify = _now
                    log.info("Eye break fired.")

                # ── Sitting-distance check ──────────────────────────────────────
                if dist_cm is not None:
                    _d_min = _screen_info["recommended_min_cm"]
                    _d_max = _screen_info["recommended_max_cm"]
                    if dist_cm < _d_min:
                        dist_close_streak += 1
                        dist_far_streak    = 0
                    elif dist_cm > _d_max:
                        dist_far_streak   += 1
                        dist_close_streak  = 0
                    else:
                        dist_close_streak = 0
                        dist_far_streak   = 0
                    if dist_close_streak >= DISTANCE_STREAK_LIMIT and (_now - last_dist_notify) > DISTANCE_COOLDOWN:
                        _notify_too_close(dist_cm, _d_min)
                        last_dist_notify  = _now
                        dist_close_streak = 0
                        log.info("Too-close alert: ~%d cm (min %d cm)", dist_cm, _d_min)
                    elif dist_far_streak >= DISTANCE_STREAK_LIMIT and (_now - last_dist_notify) > DISTANCE_COOLDOWN:
                        _notify_too_far(dist_cm, _d_max)
                        last_dist_notify = _now
                        dist_far_streak  = 0
                        log.info("Too-far alert: ~%d cm (max %d cm)", dist_cm, _d_max)

        else:
            # No body detected
            # Try face-based fallback when available
            if use_fallback:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
                if len(faces) > 0:
                    # take largest face
                    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
                    # identity check (lazy per session)
                    if not is_owner and not identity_checked_this_session:
                        identity_checked_this_session = True
                        if owner_encoding is not None:
                            face_crop = cv2.cvtColor(frame[y : y + h, x : x + w], cv2.COLOR_BGR2RGB)
                            encs = face_recognition.face_encodings(face_crop)
                            if encs:
                                match = face_recognition.compare_faces([owner_encoding], encs[0], tolerance=FACE_TOLERANCE)
                                if match[0]:
                                    is_owner = True
                                    log.info("Owner verified (face fallback) — identity locked.")
                                else:
                                    log.info("Face detected but not the owner — skipping (fallback).")
                            else:
                                identity_checked_this_session = False
                    if is_owner:
                        # establish baseline on first seen
                        if baseline_face_width is None:
                            baseline_face_width = w
                            baseline_face_center_y = y + h / 2
                        # simple heuristic: if face appears significantly larger (closer), mark as forward head
                        ratio = w / baseline_face_width if baseline_face_width else 1.0
                        angle_est = (ratio - 1.0) * 30.0  # heuristic scaling
                        label = "bad" if ratio > 1.12 else "good"
                        database.insert_record(label, None, None, None, float(angle_est), is_owner=True)
                        _write_live_stats({
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "body_detected": True,
                            "is_owner": True,
                            "label": label,
                            "confidence": None,
                            "reason": f"face fallback (angle\u2248{angle_est:.1f}\u00b0)",
                        })
                        if label == "bad":
                            bad_streak += 1
                            if bad_streak == BAD_STREAK_LIMIT:
                                _notify_bad_posture()
                                bad_streak = 0
                        else:
                            bad_streak = 0
                        # reset body_gone timer since we see face
                        body_gone_since = None
                        time.sleep(1)
                        continue

            if is_owner or identity_checked_this_session:
                if body_gone_since is None:
                    body_gone_since = time.monotonic()
                elif time.monotonic() - body_gone_since > BODY_GONE_TIMEOUT:
                    log.info("Body absent >%ds — identity lock reset.", int(BODY_GONE_TIMEOUT))
                    is_owner = False
                    identity_checked_this_session = False
                    bad_streak = 0
                    # Body has left — treat as a break; reset sitting timer so
                    # the 30-min clock restarts when they return.
                    if sit_start_time is not None:
                        log.info("Break detected — sitting timer reset.")
                    sit_start_time = None

        # When no pose was classified this frame, update live stats feed.
        if not (results.pose_landmarks if results is not None else None):
            _write_live_stats({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "body_detected": False,
                "is_owner": is_owner,
                "label": "no_body",
                "confidence": None,
                "reason": "no body detected",
            })

    # Cleanup
    pose.close()
    cap.release()
    log.info("Tracking loop stopped.")


# ---------------------------------------------------------------------------
# MJPEG server (serves _STREAM_FRAME_BYTES as multipart/x-mixed-replace)
# ---------------------------------------------------------------------------

class _MJPEGHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        if self.path not in ('/stream', '/mjpeg'):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=--frame')
        self.end_headers()
        try:
            while True:
                frame = globals().get('_STREAM_FRAME_BYTES')
                if frame:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                time.sleep(0.033)  # ~30 FPS stream pacing
        except Exception:
            pass


def start_mjpeg_server(port: int = 8765):
    """Start a background ThreadingHTTPServer serving MJPEG on localhost."""
    try:
        class _ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            allow_reuse_address = True

        server = _ThreadedTCPServer(('127.0.0.1', port), _MJPEGHandler)

        def _serve():
            try:
                server.serve_forever()
            except Exception:
                pass

        t = threading.Thread(target=_serve, name='MJPEGServer', daemon=True)
        t.start()
        log.info("MJPEG server started on http://127.0.0.1:%d/stream", port)
        return server
    except Exception as exc:
        log.warning("Failed to start MJPEG server: %s", exc)
        return None


# ---------------------------------------------------------------------------
# System tray icon (main thread)
# ---------------------------------------------------------------------------


def _create_icon_image() -> Image.Image:
    """Generate a simple 64x64 tray icon (green circle)."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=(0, 200, 80, 255))
    return img


def main():
    import sys as _sys
    _no_tray = "--no-tray" in _sys.argv or os.environ.get("POSTURE_NO_TRAY") == "1"

    database.init_db()

    # Ensure Windows grants this process camera consent. Writes registry keys;
    # spawns a UAC-elevated subprocess for the HKLM keys if not already admin.
    camera_perms.ensure_camera_perms()

    owner_encoding = _load_owner_encoding()
    posture_sess   = _load_posture_model()

    stop_event = threading.Event()

    # Start MJPEG server early so the UI can connect for preview frames.
    try:
        _mjpeg_server = start_mjpeg_server(port=8765)
    except Exception:
        _mjpeg_server = None

    # Spawn the tracking worker thread (daemon=True so it dies with the process)
    worker = threading.Thread(
        target=tracking_loop,
        args=(stop_event, owner_encoding, posture_sess),
        daemon=True,
        name="PostureWorker",
    )
    worker.start()

    # ── Integrated PyQt6 tray and widget setup (must run on main thread) ──────────────────
    if PYQT6_AVAILABLE and not _no_tray:
        try:
            log.info(f"PyQt6 available: {PYQT6_AVAILABLE}")
            # Create Qt application if not exists
            qt_app = QApplication.instance()
            if qt_app is None:
                qt_app = QApplication(["PostureTracker"])  # Use app name to avoid conflicts
                log.info("Qt application created")
            
            # Create simple tray icon
            tray_icon = SimpleTrayIcon(stop_event=stop_event)
            log.info("System tray icon created")
            
            log.info("Starting integrated PyQt6 system tray.")
            
            # Simple event loop - just wait for stop event
            while not stop_event.is_set():
                time.sleep(0.1)
                qt_app.processEvents()
            
            # Cleanup
            tray_icon.hide()
            
        except Exception as e:
            log.warning(f"PyQt6 tray/widget failed: {e}")
            # Exit gracefully instead of falling back to pystray
            log.info("Application exited due to PyQt6 errors.")
            return
    else:
        # Headless mode (--no-tray): just wait until the worker finishes
        worker.join()
    log.info("Application exited.")


if __name__ == "__main__":
    main()
