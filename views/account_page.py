"""
account_page.py — Subscription status + billing management + tracker settings.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QSpacerItem, QSpinBox, QCheckBox, QScrollArea,
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices

from core.constants import C, BILLING_URL

import json, os, sys

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app_config.json")
_STARTUP_KEY  = "PostureApp"
_STARTUP_HIVE = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _startup_exe_cmd() -> str:
    """Build the command written to the Run registry key."""
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return f'"{pythonw}" "{script}"'


def _is_startup_enabled() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_HIVE, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _STARTUP_KEY)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _set_startup(enabled: bool) -> None:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_HIVE, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, _STARTUP_KEY, 0, winreg.REG_SZ, _startup_exe_cmd())
        else:
            try:
                winreg.DeleteValue(key, _STARTUP_KEY)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass

def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"alert_timing_seconds": 30, "notifications_enabled": True, "sound_enabled": True}

def _save_config(cfg: dict):
    try:
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        with open(_CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


class AccountPage(QWidget):
    settings_changed = pyqtSignal()   # emitted whenever tracker settings are saved
    """Displays current plan info, tracker settings, and billing redirect."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._plan_name = "—"
        self._plan_status = "Active"
        self._user_email = ""
        self._next_billing = "—"

        # Scroll wrapper so the page doesn't clip on small windows
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        hdr = QLabel("Account & Subscription")
        hdr.setObjectName("pageHeader")
        root.addWidget(hdr)

        sub = QLabel("Manage your plan, billing, and tracker settings.")
        sub.setObjectName("pageSubheader")
        root.addWidget(sub)
        root.addSpacing(28)

        # ── Plan card ────────────────────────────────────────────────
        plan_card = QFrame()
        plan_card.setObjectName("planCard")
        plan_lay = QVBoxLayout(plan_card)
        plan_lay.setContentsMargins(30, 28, 30, 28)
        plan_lay.setSpacing(0)

        row1 = QHBoxLayout()
        self._plan_label = QLabel(f"{self._plan_name} Plan")
        self._plan_label.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {C.TEXT_PRIMARY};")
        row1.addWidget(self._plan_label)
        row1.addStretch()
        self._badge = QLabel(self._plan_status)
        self._badge.setObjectName("planBadge")
        row1.addWidget(self._badge)
        plan_lay.addLayout(row1)
        plan_lay.addSpacing(18)

        details_grid = QVBoxLayout()
        details_grid.setSpacing(10)
        self._email_row    = self._detail_row("Account",             self._user_email or "—")
        self._billing_row  = self._detail_row("Next Billing Date",   self._next_billing)
        self._sub_status_row = self._detail_row("Subscription Status", "Checking...")
        details_grid.addLayout(self._email_row[0])
        details_grid.addLayout(self._billing_row[0])
        details_grid.addLayout(self._sub_status_row[0])
        plan_lay.addLayout(details_grid)
        plan_lay.addSpacing(26)

        btn_row = QHBoxLayout()
        manage_btn = QPushButton("Manage Subscription")
        manage_btn.setObjectName("primaryBtn")
        manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_btn.setFixedWidth(220)
        manage_btn.clicked.connect(self._open_billing)
        btn_row.addWidget(manage_btn)
        btn_row.addSpacing(12)
        logout_btn = QPushButton("Log Out")
        logout_btn.setObjectName("dangerBtn")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setFixedWidth(140)
        btn_row.addWidget(logout_btn)
        btn_row.addStretch()
        plan_lay.addLayout(btn_row)
        self.logout_btn = logout_btn
        root.addWidget(plan_card)
        root.addSpacing(24)

        # ── Tracker Settings card ────────────────────────────────────
        settings_card = QFrame()
        settings_card.setObjectName("planCard")
        s_lay = QVBoxLayout(settings_card)
        s_lay.setContentsMargins(30, 24, 30, 24)
        s_lay.setSpacing(16)

        s_title = QLabel("Tracker Settings")
        s_title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {C.TEXT_PRIMARY};")
        s_lay.addWidget(s_title)

        cfg = _load_config()

        # Notifications enabled
        notif_row = QHBoxLayout()
        notif_lbl = QLabel("Desktop Notifications")
        notif_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_SECONDARY}; font-weight: 500;")
        notif_row.addWidget(notif_lbl)
        notif_row.addStretch()
        self._notif_check = QCheckBox()
        self._notif_check.setChecked(bool(cfg.get("notifications_enabled", True)))
        self._notif_check.stateChanged.connect(self._save_settings)
        notif_row.addWidget(self._notif_check)
        s_lay.addLayout(notif_row)

        # Sound enabled
        sound_row = QHBoxLayout()
        sound_lbl = QLabel("Sound Alerts")
        sound_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_SECONDARY}; font-weight: 500;")
        sound_row.addWidget(sound_lbl)
        sound_row.addStretch()
        self._sound_check = QCheckBox()
        self._sound_check.setChecked(bool(cfg.get("sound_enabled", True)))
        self._sound_check.stateChanged.connect(self._save_settings)
        sound_row.addWidget(self._sound_check)
        s_lay.addLayout(sound_row)

        # Alert timing
        timing_row = QHBoxLayout()
        timing_lbl = QLabel("Alert after bad posture for (seconds)")
        timing_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_SECONDARY}; font-weight: 500;")
        timing_row.addWidget(timing_lbl)
        timing_row.addStretch()
        self._alert_spin = QSpinBox()
        self._alert_spin.setRange(5, 300)
        self._alert_spin.setSingleStep(5)
        self._alert_spin.setValue(int(cfg.get("alert_timing_seconds", 30)))
        self._alert_spin.setFixedWidth(80)
        self._alert_spin.setStyleSheet(
            f"background: {C.BG_INPUT}; color: {C.TEXT_PRIMARY}; border: 1px solid {C.BORDER_SUBTLE}; "
            f"border-radius: 6px; padding: 4px 8px; font-size: 13px;"
        )
        self._alert_spin.valueChanged.connect(self._save_settings)
        timing_row.addWidget(self._alert_spin)
        s_lay.addLayout(timing_row)

        # Sit-break interval
        sb_row = QHBoxLayout()
        sb_lbl = QLabel("Sit-break reminder every (minutes)")
        sb_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_SECONDARY}; font-weight: 500;")
        sb_row.addWidget(sb_lbl)
        sb_row.addStretch()
        self._sit_spin = QSpinBox()
        self._sit_spin.setRange(5, 120)
        self._sit_spin.setSingleStep(5)
        self._sit_spin.setValue(int(cfg.get("sit_break_interval_min", 30)))
        self._sit_spin.setFixedWidth(80)
        self._sit_spin.setStyleSheet(
            f"background: {C.BG_INPUT}; color: {C.TEXT_PRIMARY}; border: 1px solid {C.BORDER_SUBTLE}; "
            f"border-radius: 6px; padding: 4px 8px; font-size: 13px;"
        )
        self._sit_spin.valueChanged.connect(self._save_settings)
        sb_row.addWidget(self._sit_spin)
        s_lay.addLayout(sb_row)

        # Eye-break interval
        eye_row = QHBoxLayout()
        eye_lbl = QLabel("Eye-break reminder (20-20-20) every (minutes)")
        eye_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_SECONDARY}; font-weight: 500;")
        eye_row.addWidget(eye_lbl)
        eye_row.addStretch()
        self._eye_spin = QSpinBox()
        self._eye_spin.setRange(5, 60)
        self._eye_spin.setSingleStep(5)
        self._eye_spin.setValue(int(cfg.get("eye_break_interval_min", 20)))
        self._eye_spin.setFixedWidth(80)
        self._eye_spin.setStyleSheet(
            f"background: {C.BG_INPUT}; color: {C.TEXT_PRIMARY}; border: 1px solid {C.BORDER_SUBTLE}; "
            f"border-radius: 6px; padding: 4px 8px; font-size: 13px;"
        )
        self._eye_spin.valueChanged.connect(self._save_settings)
        eye_row.addWidget(self._eye_spin)
        s_lay.addLayout(eye_row)

        save_hint = QLabel("Settings are saved automatically.")
        save_hint.setStyleSheet(f"font-size: 11px; color: {C.TEXT_DISABLED};")
        s_lay.addWidget(save_hint)

        # Start at Windows startup
        startup_row = QHBoxLayout()
        startup_lbl = QLabel("Start app when Windows starts")
        startup_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_SECONDARY}; font-weight: 500;")
        startup_row.addWidget(startup_lbl)
        startup_row.addStretch()
        self._startup_check = QCheckBox()
        self._startup_check.setChecked(_is_startup_enabled())
        self._startup_check.stateChanged.connect(self._toggle_startup)
        startup_row.addWidget(self._startup_check)
        s_lay.addLayout(startup_row)

        startup_hint = QLabel("Adds an entry to Windows startup registry (HKCU).")
        startup_hint.setStyleSheet(f"font-size: 11px; color: {C.TEXT_DISABLED};")
        s_lay.addWidget(startup_hint)

        root.addWidget(settings_card)
        root.addStretch()

    # ── Public setters ──────────────────────────────────────────────────
    def set_user(self, email: str, plan: str = "Solo"):
        self._user_email = email
        self._plan_name = plan or "—"
        self._plan_label.setText(f"{self._plan_name} Plan")
        self._email_row[1].setText(email)

    def set_subscription_status(self, status: str, detail: str):
        """status: 'online' | 'offline' | 'expired'"""
        color_map = {
            "online":  C.ACCENT_EMERALD,
            "offline": C.ACCENT_AMBER,
            "expired": C.ACCENT_RED,
        }
        color = color_map.get(status, C.TEXT_SECONDARY)
        self._sub_status_row[1].setText(detail)
        self._sub_status_row[1].setStyleSheet(f"font-size: 14px; font-weight: 500; color: {color};")

        badge_text = {"online": "Active", "offline": "Offline", "expired": "Expired"}.get(status, "Unknown")
        self._badge.setText(badge_text)
        if status == "online":
            self._badge.setStyleSheet(f"background-color: {C.ACCENT_EMERALD}; color: {C.BG_PRIMARY}; font-size: 11px; font-weight: 700; border-radius: 8px; padding: 4px 14px;")
        elif status == "offline":
            self._badge.setStyleSheet(f"background-color: {C.ACCENT_AMBER}; color: {C.BG_PRIMARY}; font-size: 11px; font-weight: 700; border-radius: 8px; padding: 4px 14px;")
        else:
            self._badge.setStyleSheet(f"background-color: {C.ACCENT_RED}; color: {C.WHITE}; font-size: 11px; font-weight: 700; border-radius: 8px; padding: 4px 14px;")

    # ── Internal helpers ────────────────────────────────────────────────
    @staticmethod
    def _detail_row(label_text: str, value_text: str) -> tuple:
        """Return (QHBoxLayout, value_QLabel) for a key-value row."""
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_SECONDARY}; font-weight: 500;")
        lbl.setFixedWidth(180)
        val = QLabel(value_text)
        val.setStyleSheet(f"font-size: 14px; font-weight: 500; color: {C.TEXT_PRIMARY};")
        row.addWidget(lbl)
        row.addWidget(val, 1)
        return row, val

    # ── Tracker settings save ───────────────────────────────────────────
    def _save_settings(self):
        cfg = {
            "notifications_enabled": self._notif_check.isChecked(),
            "sound_enabled": self._sound_check.isChecked(),
            "alert_timing_seconds": self._alert_spin.value(),
            "sit_break_interval_min": self._sit_spin.value(),
            "eye_break_interval_min": self._eye_spin.value(),
        }
        _save_config(cfg)
        self.settings_changed.emit()

    def _toggle_startup(self):
        _set_startup(self._startup_check.isChecked())

    @staticmethod
    def _open_billing():
        """Open the billing page in the user's default browser."""
        QDesktopServices.openUrl(QUrl(BILLING_URL))
