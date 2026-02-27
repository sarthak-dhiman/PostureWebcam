"""
reports_page.py — Historical posture data with tabs:
  Tab 0 – Daily Overview  (live stats + today's DB summary)
  Tab 1 – Deep Analytics  (DB history table, per-day summaries)
"""

from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QSizePolicy, QProgressBar, QPushButton,
)
from PyQt6.QtWidgets import QScrollArea
from PyQt6.QtWidgets import QComboBox
from PyQt6.QtGui import QPixmap
import os as _os
from PyQt6.QtCore import Qt
import time

from core.constants import C

# Safe database import — runs without DB if tracker hasn't run yet
try:
    import database as _db
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

_LABEL_STYLE = f"font-size: 12px; color: {C.TEXT_SECONDARY}; font-weight: 500;"
_VALUE_STYLE = f"font-size: 28px; font-weight: 700; color: {C.TEXT_PRIMARY};"
_UNIT_STYLE  = f"font-size: 13px; color: {C.TEXT_SECONDARY};"


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 11px; font-weight: 700; color: {C.TEXT_DISABLED}; letter-spacing: 1px;"
    )
    return lbl


def _stat_card(title: str, init_value: str = "—", unit: str = "") -> tuple:
    card = QFrame()
    card.setObjectName("kpiCard")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(4)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(_LABEL_STYLE)
    val_lbl = QLabel(init_value)
    val_lbl.setStyleSheet(_VALUE_STYLE)
    unit_lbl = QLabel(unit)
    unit_lbl.setStyleSheet(_UNIT_STYLE)
    lay.addWidget(title_lbl)
    lay.addWidget(val_lbl)
    if unit:
        lay.addWidget(unit_lbl)
    return card, val_lbl


_HIST_HEADERS = ["Date", "Score", "Tracked (min)", "Alerts", "Avg Angle", "Rating"]


def _rating(good_pct: float) -> str:
    if good_pct >= 90: return "Excellent"
    if good_pct >= 75: return "Good"
    if good_pct >= 60: return "Needs work"
    return "Poor"


class ReportsPage(QWidget):
    """Shows posture reports with a Daily Overview and a Deep Analytics tab."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Runtime state ───────────────────────────────────────────
        self._samples: list[dict] = []
        self._live_good  = 0
        self._live_bad   = 0
        self._live_alerts = 0
        self._last_pdf_path: str | None = None

        # ── Outer layout ────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        hdr = QLabel("Reports")
        hdr.setObjectName("pageHeader")
        root.addWidget(hdr)

        sub = QLabel("Review your posture history and live session stats.")
        sub.setObjectName("pageSubheader")
        root.addWidget(sub)
        root.addSpacing(20)

        # ── Tabs ────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setObjectName("reportsTabs")
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {C.BORDER_SUBTLE};
                border-radius: 10px;
                background: {C.BG_SECONDARY};
            }}
            QTabBar::tab {{
                background: {C.BG_INPUT};
                color: {C.TEXT_SECONDARY};
                padding: 8px 24px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
                font-size: 13px;
                font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background: {C.BG_SECONDARY};
                color: {C.TEXT_PRIMARY};
                border-bottom: 2px solid {C.ACCENT_BLUE};
            }}
        """)

        self._tabs.addTab(self._build_daily_overview(), "Daily Overview")
        self._tabs.addTab(self._build_deep_analytics(), "Deep Analytics")
        self._tabs.addTab(self._build_monthly_report(), "Monthly Report")
        self._tabs.addTab(self._build_export_pdf(), "Export PDF")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        root.addWidget(self._tabs, 1)

    # ── Page lifecycle ──────────────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_from_db()

    def _on_tab_changed(self, idx: int):
        self._refresh_from_db()

    # ── Builder helpers ─────────────────────────────────────────────────

    def _build_daily_overview(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(18)

        # Live session banner
        self._live_banner = QLabel("No active session")
        self._live_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._live_banner.setStyleSheet(
            f"font-size: 13px; font-weight: 600; padding: 8px 14px; "
            f"background: {C.BG_INPUT}; border-radius: 8px; color: {C.TEXT_SECONDARY};"
        )
        lay.addWidget(self._live_banner)

        # Today DB summary row header
        today_hdr = QHBoxLayout()
        today_hdr.addWidget(_section_label("TODAY'S SUMMARY"))
        today_hdr.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("secondaryBtn")
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._refresh_from_db)
        today_hdr.addWidget(self._refresh_btn)
        lay.addLayout(today_hdr)

        # Stat cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        c1, self._score_val  = _stat_card("Posture Score",  "—",  "")
        c2, self._good_val   = _stat_card("Good Frames",    "0",  "samples")
        c3, self._bad_val    = _stat_card("Bad Frames",     "0",  "samples")
        c4, self._tracked_val = _stat_card("Tracked",       "0",  "minutes")
        for c in (c1, c2, c3, c4):
            c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            cards_row.addWidget(c)
        lay.addLayout(cards_row)

        # Progress bar
        lay.addWidget(_section_label("GOOD POSTURE RATIO — TODAY"))
        self._ratio_bar = QProgressBar()
        self._ratio_bar.setRange(0, 100)
        self._ratio_bar.setValue(0)
        self._ratio_bar.setTextVisible(True)
        self._ratio_bar.setFormat("%p%  good posture")
        self._ratio_bar.setFixedHeight(26)
        self._ratio_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {C.BG_INPUT};
                border-radius: 6px;
                text-align: center;
                font-size: 12px;
                color: {C.TEXT_PRIMARY};
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {C.ACCENT_EMERALD}, stop:1 {C.ACCENT_BLUE});
                border-radius: 6px;
            }}
        """)
        lay.addWidget(self._ratio_bar)

        # Peak bad hour
        self._peak_lbl = QLabel("")
        self._peak_lbl.setStyleSheet(f"font-size: 12px; color: {C.TEXT_SECONDARY};")
        lay.addWidget(self._peak_lbl)

        # Live session sub-header
        lay.addWidget(_section_label("LIVE SESSION"))
        cards2 = QHBoxLayout()
        cards2.setSpacing(14)
        c5, self._live_good_val  = _stat_card("Good (live)",  "0", "samples")
        c6, self._live_bad_val   = _stat_card("Bad (live)",   "0", "samples")
        c7, self._live_alert_val = _stat_card("Alerts (live)","0", "detections")
        for c in (c5, c6, c7):
            c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            cards2.addWidget(c)
        lay.addLayout(cards2)
        lay.addSpacing(16)
        # Snapshot gallery (last hour)
        lay.addWidget(_section_label("COLLECTED FRAMES — last hour"))
        gallery_row = QHBoxLayout()
        self._gallery_area = QScrollArea()
        self._gallery_area.setWidgetResizable(True)
        self._gallery_area.setMinimumHeight(300)  # enough room for 240px thumbnails + scrollbar
        gallery_container = QFrame()
        self._gallery_layout = QHBoxLayout(gallery_container)
        self._gallery_layout.setContentsMargins(6, 6, 6, 6)
        self._gallery_layout.setSpacing(8)
        self._gallery_area.setWidget(gallery_container)
        gallery_row.addWidget(self._gallery_area)
        # refresh gallery button
        self._gallery_refresh = QPushButton("Refresh Gallery")
        self._gallery_refresh.setObjectName("secondaryBtn")
        self._gallery_refresh.setFixedWidth(140)
        self._gallery_refresh.clicked.connect(self._refresh_gallery)
        gallery_row.addWidget(self._gallery_refresh)
        lay.addLayout(gallery_row)
        lay.addSpacing(8)

        # Wrap the daily overview page in a scroll area so long content
        # (charts, gallery, table) can be scrolled on smaller windows.
        container = QWidget()
        container_lay = QVBoxLayout(container)
        container_lay.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        container_lay.addWidget(scroll)
        return container

    def _build_deep_analytics(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(18)

        # ── Pyqtgraph trend chart ────────────────────────────────────
        try:
            import pyqtgraph as pg
            pg.setConfigOption("background", C.BG_SECONDARY)
            pg.setConfigOption("foreground", C.TEXT_SECONDARY)
            self._chart = pg.PlotWidget()
            self._chart.setMinimumHeight(170)
            self._chart.setLabel("left", "Score %")
            self._chart.setLabel("bottom", "Date")
            self._chart.showGrid(x=False, y=True, alpha=0.3)
            self._chart.setYRange(0, 100)
            self._chart.getAxis("bottom").setTicks([])  # updated in refresh
            self._chart.setMouseEnabled(x=False, y=False)
            self._chart.setMenuEnabled(False)
            lay.addWidget(self._chart)
        except Exception:
            self._chart = None
            chart_frame = QFrame()
            chart_frame.setObjectName("webcamPlaceholder")
            chart_frame.setMinimumHeight(140)
            cf_lay = QVBoxLayout(chart_frame)
            cf_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cf_lay.addWidget(QLabel("Posture Trend Chart (install pyqtgraph)"),
                             alignment=Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(chart_frame)

        # History table
        hdr_row = QHBoxLayout()
        hdr_row.addWidget(_section_label("HISTORY (ALL SESSIONS FROM DB)"))
        hdr_row.addStretch()
        lay.addLayout(hdr_row)

        self._table = QTableWidget(0, len(_HIST_HEADERS))
        self._table.setHorizontalHeaderLabels(_HIST_HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        # Ensure table has a sensible minimum height so it's visible
        # when window is moderately sized.
        self._table.setMinimumHeight(220)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._table, 1)

        return page

    def _build_monthly_report(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        hdr = QLabel("Monthly Report")
        hdr.setObjectName("pageHeader")
        lay.addWidget(hdr)

        sub = QLabel("Summary for the current month.")
        sub.setObjectName("pageSubheader")
        lay.addWidget(sub)

        # Month selector row
        sel_row = QHBoxLayout()
        sel_row.addWidget(_section_label("Month"))
        self._month_combo = QComboBox()
        months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        self._month_combo.addItems(months)
        sel_row.addWidget(self._month_combo)
        sel_row.addStretch()
        sel_row.addWidget(_section_label("Year"))
        self._year_combo = QComboBox()
        import datetime as _dt
        cur_year = _dt.datetime.now().year
        years = [str(cur_year - i) for i in range(0, 4)]
        self._year_combo.addItems(years)
        self._year_combo.setCurrentIndex(0)
        sel_row.addWidget(self._year_combo)
        self._month_combo.setCurrentIndex(_dt.datetime.now().month - 1)
        root_sel = QHBoxLayout()
        root_sel.addLayout(sel_row)
        root_sel.addStretch()
        lay.addLayout(root_sel)

        # Summary cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._month_days_lbl = QLabel("—")
        self._month_avg_lbl = QLabel("—")
        self._month_alerts_lbl = QLabel("—")
        self._month_details_lbl = QLabel("")
        self._month_details_lbl.setStyleSheet(f"font-size:12px; color: {C.TEXT_SECONDARY};")
        for lbl in (self._month_days_lbl, self._month_avg_lbl, self._month_alerts_lbl):
            lbl.setStyleSheet(_VALUE_STYLE)

        stats_row.addWidget(_section_label("Tracked Days"))
        stats_row.addWidget(self._month_days_lbl)
        stats_row.addStretch()
        stats_row.addWidget(_section_label("Avg Score"))
        stats_row.addWidget(self._month_avg_lbl)
        stats_row.addStretch()
        stats_row.addWidget(_section_label("Total Alerts"))
        stats_row.addWidget(self._month_alerts_lbl)
        lay.addLayout(stats_row)
        lay.addWidget(self._month_details_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._month_refresh_btn = QPushButton("Refresh")
        self._month_refresh_btn.setObjectName("secondaryBtn")
        self._month_refresh_btn.setFixedWidth(100)
        self._month_refresh_btn.clicked.connect(self._refresh_monthly_report)
        btn_row.addWidget(self._month_refresh_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Charts preview
        charts_row = QHBoxLayout()
        self._month_donut_lbl = QLabel()
        self._month_donut_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_timeline_lbl = QLabel()
        self._month_timeline_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_angle_lbl = QLabel()
        self._month_angle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for lbl in (self._month_donut_lbl, self._month_timeline_lbl, self._month_angle_lbl):
            lbl.setMinimumSize(180, 140)
            lbl.setStyleSheet("background: transparent;")
            charts_row.addWidget(lbl)
        lay.addLayout(charts_row)

        lay.addStretch()
        return page

    def _build_export_pdf(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        hdr = QLabel("Generate PDF Reports")
        hdr.setObjectName("pageHeader")
        lay.addWidget(hdr)

        sub = QLabel("Create a printable PDF summary for today or for a full month.")
        sub.setObjectName("pageSubheader")
        lay.addWidget(sub)

        # ── Daily ──────────────────────────────────────────────────────────
        lay.addSpacing(8)
        lay.addWidget(_section_label("DAILY REPORT"))
        daily_desc = QLabel(
            "Today's posture session with posture charts, bad-frame snapshots, and health risk analysis."
        )
        daily_desc.setStyleSheet(f"font-size: 12px; color: {C.TEXT_SECONDARY};")
        daily_desc.setWordWrap(True)
        lay.addWidget(daily_desc)

        daily_row = QHBoxLayout()
        self._pdf_daily_btn = QPushButton("Generate Daily PDF  (Today)")
        self._pdf_daily_btn.setObjectName("primaryBtn")
        self._pdf_daily_btn.setFixedWidth(230)
        self._pdf_daily_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pdf_daily_btn.clicked.connect(self._on_gen_daily_pdf)
        daily_row.addWidget(self._pdf_daily_btn)
        daily_row.addStretch()
        lay.addLayout(daily_row)

        # ── Monthly ────────────────────────────────────────────────────────
        lay.addSpacing(8)
        lay.addWidget(_section_label("MONTHLY REPORT"))
        monthly_desc = QLabel(
            "Full month summary with per-day scores, trends, and aggregate health risk analysis. "
            "Uses the month and year selected in the Monthly Report tab."
        )
        monthly_desc.setStyleSheet(f"font-size: 12px; color: {C.TEXT_SECONDARY};")
        monthly_desc.setWordWrap(True)
        lay.addWidget(monthly_desc)

        monthly_row = QHBoxLayout()
        self._pdf_monthly_btn = QPushButton("Generate Monthly PDF")
        self._pdf_monthly_btn.setObjectName("secondaryBtn")
        self._pdf_monthly_btn.setFixedWidth(200)
        self._pdf_monthly_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pdf_monthly_btn.clicked.connect(self._on_gen_monthly_pdf)
        monthly_row.addWidget(self._pdf_monthly_btn)
        monthly_row.addStretch()
        lay.addLayout(monthly_row)

        # ── Status label ───────────────────────────────────────────────────
        lay.addSpacing(4)
        self._pdf_status = QLabel("")
        self._pdf_status.setStyleSheet(f"font-size: 12px; color: {C.TEXT_SECONDARY};")
        self._pdf_status.setWordWrap(True)
        lay.addWidget(self._pdf_status)

        # ── Divider ────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER_SUBTLE};")
        lay.addWidget(sep)

        # ── Share section ──────────────────────────────────────────────────
        lay.addWidget(_section_label("SHARE LAST GENERATED REPORT"))
        share_desc = QLabel(
            "Share your report via email, open the reports folder, or send a WhatsApp message. "
            "Generate a report above first."
        )
        share_desc.setStyleSheet(f"font-size: 12px; color: {C.TEXT_SECONDARY};")
        share_desc.setWordWrap(True)
        lay.addWidget(share_desc)

        share_row = QHBoxLayout()
        share_row.setSpacing(12)
        self._share_email_btn    = QPushButton("Email")
        self._share_folder_btn   = QPushButton("Open Folder")
        self._share_whatsapp_btn = QPushButton("WhatsApp Web")
        for btn in (self._share_email_btn, self._share_folder_btn, self._share_whatsapp_btn):
            btn.setObjectName("secondaryBtn")
            btn.setFixedWidth(150)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setEnabled(False)
            share_row.addWidget(btn)
        share_row.addStretch()
        self._share_email_btn.clicked.connect(self._on_share_email)
        self._share_folder_btn.clicked.connect(self._on_open_folder)
        self._share_whatsapp_btn.clicked.connect(self._on_share_whatsapp)
        lay.addLayout(share_row)

        lay.addStretch()
        return page

    # ── DB refresh ──────────────────────────────────────────────────────

    def _refresh_from_db(self):
        """Reload data from posture.db into both tab views."""
        if not _DB_AVAILABLE:
            return
        try:
            self._load_today_summary()
            self._load_history_table()
            self._refresh_monthly_report()
            # update snapshot gallery after DB refresh
            try:
                self._refresh_gallery()
            except Exception:
                pass
        except Exception:
            pass

    def _load_today_summary(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            s = _db.get_daily_summary(today)
        except Exception:
            return

        total = s.get("total", 0)
        good  = s.get("good", 0)
        bad   = s.get("bad", 0)
        pct   = s.get("good_pct", 0.0)
        mins  = s.get("total_minutes", 0)
        peak  = s.get("peak_bad_hour")
        avg_a = s.get("avg_angle")

        self._score_val.setText(f"{pct:.0f}%" if total else "—")
        self._good_val.setText(str(good))
        self._bad_val.setText(str(bad))
        self._tracked_val.setText(str(mins))
        self._ratio_bar.setValue(int(pct))

        if peak is not None:
            am_pm = "am" if peak < 12 else "pm"
            hr = peak if peak <= 12 else peak - 12
            self._peak_lbl.setText(f"Peak bad-posture hour: {hr}{am_pm}  |  Avg lean angle: {avg_a}°" if avg_a else f"Peak bad-posture hour: {hr}{am_pm}")
        else:
            self._peak_lbl.setText("No data recorded today yet." if total == 0 else "")

    def _load_history_table(self):
        if not _DB_AVAILABLE:
            return
        try:
            dates = _db.get_all_dates()
        except Exception:
            return
        self._table.setRowCount(0)
        chart_dates: list[str] = []
        chart_scores: list[float] = []

        for date_str in reversed(dates):  # most recent first
            try:
                s = _db.get_daily_summary(date_str)
            except Exception:
                continue
            total = s.get("total", 0)
            if total == 0:
                continue
            pct   = s.get("good_pct", 0.0)
            mins  = s.get("total_minutes", 0)
            bad   = s.get("bad", 0)
            avg_a = s.get("avg_angle")
            angle_str = f"{avg_a}°" if avg_a is not None else "—"

            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, cell in enumerate([
                date_str, f"{pct:.0f}%", str(mins), str(bad), angle_str, _rating(pct),
            ]):
                item = QTableWidgetItem(cell)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)

            chart_dates.append(date_str[-5:])   # MM-DD
            chart_scores.append(pct)

        # Update chart if available
        if self._chart is not None and chart_scores:
            try:
                import pyqtgraph as pg
                self._chart.clear()
                n = len(chart_scores)
                xs = list(range(n))
                colors = [
                    pg.mkBrush("#22c55e") if v >= 75 else
                    pg.mkBrush("#f59e0b") if v >= 50 else
                    pg.mkBrush("#ef4444")
                    for v in chart_scores
                ]
                for i, (x, h, brush) in enumerate(zip(xs, chart_scores, colors)):
                    bar = pg.BarGraphItem(x=[x], height=[h], width=0.7, brush=brush)
                    self._chart.addItem(bar)
                ticks = [[(i, d) for i, d in enumerate(chart_dates)]]
                self._chart.getAxis("bottom").setTicks(ticks)
                self._chart.setXRange(-0.5, n - 0.5)
            except Exception:
                pass
                colors = [
                    pg.mkBrush("#22c55e") if v >= 75 else
                    pg.mkBrush("#f59e0b") if v >= 50 else
                    pg.mkBrush("#ef4444")
                    for v in chart_scores
                ]
                for i, (x, h, brush) in enumerate(zip(xs, chart_scores, colors)):
                    bar = pg.BarGraphItem(x=[x], height=[h], width=0.7, brush=brush)
                    self._chart.addItem(bar)
                ticks = [[(i, d) for i, d in enumerate(chart_dates)]]
                self._chart.getAxis("bottom").setTicks(ticks)
                self._chart.setXRange(-0.5, n - 0.5)
            except Exception:
                pass

    def _refresh_monthly_report(self, year: int | None = None, month: int | None = None):
        if not _DB_AVAILABLE:
            return
        try:
            from datetime import datetime
            now = datetime.now()
            year = year or now.year
            month = month or now.month
            # collect all dates in this month
            dates = _db.get_all_dates()
            month_dates = [d for d in dates if d.startswith(f"{year:04d}-{month:02d}-")]
            total_days = 0
            total_score = 0.0
            total_alerts = 0
            for d in month_dates:
                s = _db.get_daily_summary(d)
                if not s or s.get("total", 0) == 0:
                    continue
                total_days += 1
                total_score += s.get("good_pct", 0.0)
                total_alerts += s.get("bad", 0)
            avg_score = (total_score / total_days) if total_days else 0.0
            # compute additional stats: total minutes, best/worst day, avg angle
            total_minutes = 0
            best_day = None
            best_score = -1.0
            worst_day = None
            worst_score = 101.0
            avg_angle = None
            # collect per-day details
            for d in month_dates:
                try:
                    s = _db.get_daily_summary(d)
                except Exception:
                    continue
                if not s or s.get("total", 0) == 0:
                    continue
                mins = s.get("total_minutes", 0)
                total_minutes += mins
                pct = s.get("good_pct", 0.0)
                if pct > best_score:
                    best_score = pct
                    best_day = d
                if pct < worst_score:
                    worst_score = pct
                    worst_day = d
                a = s.get("avg_angle")
                if a is not None:
                    try:
                        avg_angle = (avg_angle or 0.0) + float(a)
                    except Exception:
                        pass
            if avg_angle is not None and total_days:
                avg_angle = avg_angle / total_days

            # update UI
            try:
                self._month_days_lbl.setText(str(total_days))
                self._month_avg_lbl.setText(f"{avg_score:.0f}%" if total_days else "—")
                self._month_alerts_lbl.setText(str(total_alerts))
                details = []
                if best_day:
                    details.append(f"Best day: {best_day} ({best_score:.0f}%)")
                if worst_day:
                    details.append(f"Worst day: {worst_day} ({worst_score:.0f}%)")
                details.append(f"Total minutes: {total_minutes}")
                if avg_angle is not None:
                    details.append(f"Avg forward angle: {avg_angle:.1f}°")
                self._month_details_lbl.setText("  |  ".join(details))
            except Exception:
                pass
        except Exception:
            pass

    def _refresh_gallery(self):
        """Load snapshot thumbnails from the snapshots folder for the last hour."""
        try:
            snaps_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "snapshots")
            if not _os.path.exists(snaps_dir):
                return
            # clear existing
            while self._gallery_layout.count():
                item = self._gallery_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            files = [
                _os.path.join(snaps_dir, f)
                for f in _os.listdir(snaps_dir)
                if f.lower().endswith('.jpg')
            ]
            # only last hour
            cutoff = time.time() - 3600
            recent = [f for f in files if _os.path.getmtime(f) >= cutoff]
            recent.sort(key=lambda p: _os.path.getmtime(p), reverse=True)

            # limit thumbnails to 12 (larger previews)
            recent = recent[:12]
            for p in recent:
                try:
                    lbl = QLabel()
                    pix = QPixmap(p)
                    if not pix.isNull():
                        # larger thumbnail for better visibility
                        pm = pix.scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        lbl.setPixmap(pm)
                    # caption
                    stem = _os.path.splitext(_os.path.basename(p))[0]
                    parts = stem.split('_')
                    ts = parts[1] if len(parts) > 1 else stem
                    label_txt = parts[2] if len(parts) > 2 else ""
                    cap = QLabel(f"{ts} {label_txt}")
                    cap.setStyleSheet(f"font-size:11px; color: {C.TEXT_SECONDARY};")
                    container = QFrame()
                    v = QVBoxLayout(container)
                    v.setContentsMargins(2,2,2,2)
                    v.addWidget(lbl)
                    v.addWidget(cap)
                    self._gallery_layout.addWidget(container)
                except Exception:
                    continue
        except Exception:
            return

        # build charts for the month using report_generator helpers
        try:
            import report_generator as rg
            ts_list = []
            pos_list = []
            angle_list = []
            good_count = 0
            bad_count = 0
            for d in month_dates:
                try:
                    rows = _db.get_records_range(d, d)
                except Exception:
                    continue
                for row in rows:
                    try:
                        ts_utc = datetime.fromisoformat(str(row.get("timestamp"))).replace(tzinfo=timezone.utc)
                        ts_local = ts_utc.astimezone()
                        ts_list.append(ts_local)
                        p = str(row.get("posture"))
                        pos_list.append(p)
                        a = row.get("fwd_angle")
                        angle_list.append(float(a) if a is not None else None)
                        if p == "good":
                            good_count += 1
                        elif p == "bad":
                            bad_count += 1
                    except Exception:
                        continue

            # donut
            try:
                donut_png = rg._fig_donut(good_count, bad_count)
                pm = QPixmap()
                pm.loadFromData(donut_png)
                self._month_donut_lbl.setPixmap(pm.scaled(self._month_donut_lbl.width(), self._month_donut_lbl.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            except Exception:
                pass

            # timeline
            try:
                timeline_png = rg._fig_timeline(ts_list, pos_list)
                pm2 = QPixmap()
                pm2.loadFromData(timeline_png)
                self._month_timeline_lbl.setPixmap(pm2.scaled(self._month_timeline_lbl.width(), self._month_timeline_lbl.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            except Exception:
                pass

            # angle chart
            try:
                angle_png = rg._fig_angle(ts_list, angle_list)
                pm3 = QPixmap()
                pm3.loadFromData(angle_png)
                self._month_angle_lbl.setPixmap(pm3.scaled(self._month_angle_lbl.width(), self._month_angle_lbl.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            except Exception:
                pass
        except Exception:
            # report_generator unavailable, skip charts
            pass

    # ── PDF generation handlers ─────────────────────────────────────────

    def _on_gen_daily_pdf(self):
        """Generate the daily PDF report for today using report_generator."""
        try:
            import report_generator as rg
        except ImportError:
            self._pdf_status.setText("report_generator module not found.")
            return
        today = datetime.now().strftime("%Y-%m-%d")
        self._pdf_daily_btn.setEnabled(False)
        self._pdf_status.setText(f"Generating daily PDF for {today} ...")
        try:
            path = rg.generate_pdf(today)
            self._last_pdf_path = path
            self._pdf_status.setText(f"Saved: {path}")
            for btn in (self._share_email_btn, self._share_folder_btn, self._share_whatsapp_btn):
                btn.setEnabled(True)
        except Exception as exc:
            self._pdf_status.setText(f"Error: {exc}")
        finally:
            self._pdf_daily_btn.setEnabled(True)

    def _on_gen_monthly_pdf(self):
        """Generate the monthly PDF report using month/year from Monthly Report tab."""
        try:
            import report_generator as rg
        except ImportError:
            self._pdf_status.setText("report_generator module not found.")
            return
        try:
            month_idx = self._month_combo.currentIndex() + 1
            year      = int(self._year_combo.currentText())
        except Exception:
            now       = datetime.now()
            month_idx = now.month
            year      = now.year
        self._pdf_monthly_btn.setEnabled(False)
        self._pdf_status.setText(f"Generating monthly PDF for {year}-{month_idx:02d} ...")
        try:
            path = rg.generate_monthly_pdf(year, month_idx)
            self._last_pdf_path = path
            self._pdf_status.setText(f"Saved: {path}")
            for btn in (self._share_email_btn, self._share_folder_btn, self._share_whatsapp_btn):
                btn.setEnabled(True)
        except Exception as exc:
            self._pdf_status.setText(f"Error: {exc}")
        finally:
            self._pdf_monthly_btn.setEnabled(True)

    def _on_open_folder(self):
        """Open Windows Explorer with the last generated PDF selected."""
        if not self._last_pdf_path:
            return
        try:
            import report_generator as rg
            rg.open_in_explorer(self._last_pdf_path)
        except Exception as exc:
            self._pdf_status.setText(f"Could not open folder: {exc}")

    def _on_share_email(self):
        """Open default email client pre-filled with the report file path."""
        if not self._last_pdf_path:
            return
        try:
            import webbrowser
            import urllib.parse
            subject = urllib.parse.quote("My Posture Report")
            body    = urllib.parse.quote(
                f"Hi,\n\nPlease find my posture report attached.\n"
                f"File: {self._last_pdf_path}\n\n"
                "Generated by Posture Tracker."
            )
            webbrowser.open(f"mailto:?subject={subject}&body={body}")
        except Exception as exc:
            self._pdf_status.setText(f"Could not open email client: {exc}")

    def _on_share_whatsapp(self):
        """Open WhatsApp Web pre-filled with a report message."""
        if not self._last_pdf_path:
            return
        try:
            import report_generator as rg
            rg.share_whatsapp_web(self._last_pdf_path)
        except Exception as exc:
            self._pdf_status.setText(f"Could not open WhatsApp: {exc}")

    # ── Public API — live session updates ───────────────────────────────

    def append_sample(self, sample: dict):
        """Accept a posture sample from the tracker thread and update live view."""
        try:
            sample = dict(sample)
            if "timestamp" not in sample:
                sample["timestamp"] = datetime.utcnow().isoformat()
            self._samples.append(sample)
            if len(self._samples) > 500:
                self._samples.pop(0)
        except Exception:
            return

        label  = sample.get("label", "unknown")
        reason = sample.get("reason", "")

        if label == "good":
            self._live_good += 1
        elif label == "bad":
            self._live_bad += 1
            self._live_alerts += 1

        self._live_good_val.setText(str(self._live_good))
        self._live_bad_val.setText(str(self._live_bad))
        self._live_alert_val.setText(str(self._live_alerts))

        if label == "good":
            color, text = C.ACCENT_EMERALD, "Good posture — keep it up!"
        elif label == "bad":
            text  = f"Bad posture — {reason}" if reason else "Bad posture — please adjust"
            color = C.ACCENT_RED
        elif label == "camera_busy":
            text  = "Camera in use by another app — tracking paused"
            color = C.ACCENT_RED
        elif label in ("no_tracker", "no_body"):
            text, color = "No body detected in frame", C.TEXT_DISABLED
        else:
            text, color = "Detecting...", C.TEXT_SECONDARY

        self._live_banner.setText(text)
        self._live_banner.setStyleSheet(
            f"font-size: 13px; font-weight: 600; padding: 8px 14px; "
            f"background: {C.BG_INPUT}; border-radius: 8px; color: {color};"
        )

