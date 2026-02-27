"""
sidebar.py — Left-hand navigation sidebar with subscription LED.
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpacerItem,
    QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QIcon

from core.constants import C, SIDEBAR_WIDTH, PAGE_DASHBOARD, PAGE_REPORTS, PAGE_ACCOUNT
from core.icons import icon


class Sidebar(QFrame):
    """Fixed-width sidebar with nav buttons and a subscription status LED.

    Signals
    -------
    nav_requested(int)  –  page index the user clicked
    """

    nav_requested = pyqtSignal(int)

    # (icon_name, label, page_index)
    _NAV_ITEMS = [
        ("home",     "Dashboard",  PAGE_DASHBOARD),
        ("chart",    "Reports",    PAGE_REPORTS),
        ("user",     "Account",    PAGE_ACCOUNT),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        self._buttons: list[QPushButton] = []
        self._current_index = PAGE_DASHBOARD

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 24, 14, 18)
        root.setSpacing(0)

        # ── Brand ────────────────────────────────────────────────────
        brand = QLabel("Posture Webcam\nAnalyzer")
        brand.setObjectName("sidebarBrand")
        brand.setWordWrap(True)
        root.addWidget(brand)
        root.addSpacing(4)

        self._email_label = QLabel("")
        self._email_label.setObjectName("sidebarEmail")
        root.addWidget(self._email_label)

        root.addSpacing(28)

        # ── Nav buttons ──────────────────────────────────────────────
        for icon_name, label, page_idx in self._NAV_ITEMS:
            btn = QPushButton(f"  {label}")
            btn.setIcon(icon(icon_name))
            btn.setProperty("class", "nav-btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=page_idx: self._on_nav(idx))
            root.addWidget(btn)
            root.addSpacing(4)
            self._buttons.append(btn)

        root.addStretch()

        # ── Subscription LED row ─────────────────────────────────────
        led_row = QHBoxLayout()
        led_row.setSpacing(8)

        self._led = QLabel()
        self._led.setFixedSize(10, 10)
        self._led.setObjectName("ledOffline")
        led_row.addWidget(self._led)

        self._status_text = QLabel("Checking...")
        self._status_text.setObjectName("sidebarEmail")
        self._status_text.setWordWrap(True)
        led_row.addWidget(self._status_text, 1)

        root.addLayout(led_row)

        # Set initial highlight
        self._highlight(PAGE_DASHBOARD)

    # ── Public API ──────────────────────────────────────────────────────
    def set_user_email(self, email: str):
        self._email_label.setText(email)

    def set_subscription_status(self, status: str, detail: str):
        """status: 'online' | 'offline' | 'expired'"""
        id_map = {
            "online":  "ledOnline",
            "offline": "ledOffline",
            "expired": "ledExpired",
        }
        self._led.setObjectName(id_map.get(status, "ledOffline"))
        # Force QSS re-evaluation after objectName change
        self._led.style().unpolish(self._led)
        self._led.style().polish(self._led)
        self._status_text.setText(detail)

    def set_active_page(self, index: int):
        self._highlight(index)

    # ── Internal ────────────────────────────────────────────────────────
    def _on_nav(self, page_idx: int):
        self._highlight(page_idx)
        self.nav_requested.emit(page_idx)

    def _highlight(self, active_idx: int):
        self._current_index = active_idx
        for btn, (_, _, idx) in zip(self._buttons, self._NAV_ITEMS):
            btn.setProperty("active", "true" if idx == active_idx else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
