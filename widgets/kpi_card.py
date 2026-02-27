"""
kpi_card.py — Reusable KPI stat card.
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt


class KpiCard(QFrame):
    """Displays a single metric: title, large value, and optional subtitle."""

    def __init__(
        self,
        title: str = "",
        value: str = "—",
        subtitle: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setMinimumHeight(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(4)

        self._title = QLabel(title)
        self._title.setObjectName("kpiTitle")
        layout.addWidget(self._title)

        self._value = QLabel(value)
        self._value.setObjectName("kpiValue")
        layout.addWidget(self._value)

        self._sub = QLabel(subtitle)
        self._sub.setObjectName("kpiSub")
        layout.addWidget(self._sub)

        layout.addStretch()

    # ── Public setters ──────────────────────────────────────────────────
    def set_value(self, text: str):
        self._value.setText(text)

    def set_subtitle(self, text: str):
        self._sub.setText(text)

    def set_title(self, text: str):
        self._title.setText(text)
