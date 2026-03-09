"""
dial_widget.py — Circular countdown dial (pie-arc style).

Usage:
    dial = DialWidget(title="Eye Break", total_seconds=1200, color="#4F8CFF")
    dial.set_remaining(840)   # 14 min left → arc fills 70 % of the circle
"""

import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QConicalGradient

from core.constants import C


class DialWidget(QWidget):
    """Draws a thick-arc countdown dial with a MM:SS label inside."""

    def __init__(self, title: str, total_seconds: int,
                 color: str = C.ACCENT_BLUE, parent=None):
        super().__init__(parent)
        self._title = title
        self._total = max(1, total_seconds)
        self._remaining = total_seconds
        self._base_color = color   # original color — never overwritten
        self._color = color

        self.setMinimumSize(110, 135)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # ── public API ──────────────────────────────────────────────────────

    def set_total(self, total_seconds: int):
        self._total = max(1, total_seconds)
        self.update()

    def set_remaining(self, remaining_seconds: int):
        self._remaining = max(0, min(remaining_seconds, self._total))
        # Only shift to warn colours in the final 25 % of time.
        # Above that threshold keep the original colour the caller chose.
        frac = self._remaining / self._total
        if frac > 0.25:
            self._color = self._base_color
        elif frac > 0.0:
            self._color = C.ACCENT_AMBER
        else:
            self._color = C.ACCENT_RED
        self.update()

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        title_h = 24          # reserved for title row at the bottom
        diam = min(w, h - title_h) - 12
        if diam < 20:
            return

        cx = w / 2
        # Centre the circle in the upper portion
        cy = (h - title_h) / 2
        arc_rect = QRectF(cx - diam / 2, cy - diam / 2, diam, diam)

        pen_w = max(10, diam * 0.14)

        # ── track (background ring) ─────────────────────────────────
        track_pen = QPen(QColor(C.BG_INPUT))
        track_pen.setWidth(int(pen_w))
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(arc_rect, 0, 360 * 16)

        # ── value arc (foreground) ───────────────────────────────────
        frac = self._remaining / self._total
        span_deg = frac * 360
        start_angle = 90 * 16      # 12 o'clock
        span_int = int(span_deg * 16)

        arc_pen = QPen(QColor(self._color))
        arc_pen.setWidth(int(pen_w))
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)

        if span_int > 0:
            painter.drawArc(arc_rect, start_angle, span_int)
        else:
            # Remaining = 0: draw a full red ring to signal "alert active"
            # rather than leaving an empty dark circle that looks broken.
            alert_pen = QPen(QColor(C.ACCENT_RED))
            alert_pen.setWidth(int(pen_w))
            alert_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(alert_pen)
            painter.drawArc(arc_rect, 0, 360 * 16)

        # ── centre label MM:SS ───────────────────────────────────────
        mins = self._remaining // 60
        secs = self._remaining % 60
        time_str = f"{mins}:{secs:02d}"

        font = QFont("Segoe UI", int(diam * 0.18), QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(QColor(C.TEXT_PRIMARY)))
        painter.drawText(arc_rect, Qt.AlignmentFlag.AlignCenter, time_str)

        # ── title label below the circle ─────────────────────────────
        title_rect = QRectF(0, h - title_h, w, title_h)
        title_font = QFont("Segoe UI", 9)
        title_font.setWeight(QFont.Weight.Medium)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(C.TEXT_SECONDARY)))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self._title)

        painter.end()
