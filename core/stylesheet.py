"""
stylesheet.py — Master QSS string for Posture Webcam Analyzer.

Returns a single stylesheet applied via QApplication.setStyleSheet().
"""

from core.constants import C


def build_stylesheet() -> str:
    return f"""
    /* ================================================================
       GLOBAL
       ================================================================ */
    * {{
        font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
        color: {C.TEXT_PRIMARY};
    }}

    QMainWindow, QWidget#centralRoot {{
        background-color: {C.BG_PRIMARY};
    }}

    QToolTip {{
        background-color: {C.BG_SECONDARY};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 6px;
        padding: 6px 10px;
    }}

    /* ================================================================
       SCROLLBAR  (thin, minimal)
       ================================================================ */
    QScrollBar:vertical {{
        background: {C.BG_PRIMARY};
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {C.BORDER_SUBTLE};
        min-height: 30px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {C.TEXT_DISABLED};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    /* ================================================================
       SIDEBAR
       ================================================================ */
    QFrame#sidebar {{
        background-color: {C.BG_SIDEBAR};
        border-right: 1px solid {C.BORDER_SUBTLE};
    }}

    QPushButton.nav-btn {{
        background: transparent;
        color: {C.TEXT_SECONDARY};
        text-align: left;
        padding: 12px 18px;
        border: none;
        border-radius: 10px;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton.nav-btn:hover {{
        background-color: {C.BG_HOVER};
        color: {C.TEXT_PRIMARY};
    }}
    QPushButton.nav-btn[active="true"] {{
        background-color: {C.BG_HOVER};
        color: {C.ACCENT_BLUE};
        font-weight: 600;
    }}

    QLabel#sidebarBrand {{
        font-size: 15px;
        font-weight: 700;
        color: {C.TEXT_PRIMARY};
        padding: 0;
    }}
    QLabel#sidebarEmail {{
        font-size: 11px;
        color: {C.TEXT_SECONDARY};
        padding: 0;
    }}

    /* ================================================================
       INPUTS
       ================================================================ */
    QLineEdit {{
        background-color: {C.BG_INPUT};
        border: 2px solid {C.BORDER_SUBTLE};
        border-radius: 10px;
        padding: 12px 16px;
        font-size: 14px;
        color: {C.TEXT_PRIMARY};
        selection-background-color: {C.ACCENT_BLUE};
    }}
    QLineEdit:focus {{
        border: 2px solid {C.BORDER_FOCUS};
    }}
    QLineEdit:disabled {{
        color: {C.TEXT_DISABLED};
    }}

    /* ================================================================
       BUTTONS
       ================================================================ */
    QPushButton#primaryBtn {{
        background-color: {C.ACCENT_BLUE};
        color: {C.WHITE};
        border: none;
        border-radius: 10px;
        padding: 13px 0;
        font-size: 14px;
        font-weight: 600;
    }}
    QPushButton#primaryBtn:hover {{
        background-color: {C.ACCENT_BLUE_HV};
    }}
    QPushButton#primaryBtn:pressed {{
        background-color: {C.ACCENT_BLUE};
    }}
    QPushButton#primaryBtn:disabled {{
        background-color: {C.BG_HOVER};
        color: {C.TEXT_DISABLED};
    }}

    QPushButton#secondaryBtn {{
        background-color: {C.BG_INPUT};
        color: {C.TEXT_PRIMARY};
        border: 2px solid {C.BORDER_SUBTLE};
        border-radius: 10px;
        padding: 13px 0;
        font-size: 14px;
        font-weight: 500;
    }}
    QPushButton#secondaryBtn:hover {{
        border-color: {C.ACCENT_BLUE};
        color: {C.ACCENT_BLUE};
    }}

    QPushButton#dangerBtn {{
        background-color: transparent;
        color: {C.ACCENT_RED};
        border: 2px solid {C.ACCENT_RED};
        border-radius: 10px;
        padding: 13px 0;
        font-size: 14px;
        font-weight: 500;
    }}
    QPushButton#dangerBtn:hover {{
        background-color: {C.ACCENT_RED};
        color: {C.WHITE};
    }}

    QPushButton#googleBtn {{
        background-color: {C.WHITE};
        color: #3c4043;
        border: none;
        border-radius: 10px;
        padding: 13px 0;
        font-size: 14px;
        font-weight: 600;
    }}
    QPushButton#googleBtn:hover {{
        background-color: #e8eaed;
    }}

    QPushButton#toggleBtn {{
        background-color: {C.ACCENT_EMERALD};
        color: {C.BG_PRIMARY};
        border: none;
        border-radius: 10px;
        padding: 14px 32px;
        font-size: 15px;
        font-weight: 700;
    }}
    QPushButton#toggleBtn:hover {{
        background-color: #4AE6A9;
    }}
    QPushButton#toggleBtn[tracking="true"] {{
        background-color: {C.ACCENT_RED};
        color: {C.WHITE};
    }}
    QPushButton#toggleBtn[tracking="true"]:hover {{
        background-color: #FF8A8A;
    }}

    /* ================================================================
       KPI CARDS
       ================================================================ */
    QFrame#kpiCard {{
        background-color: {C.BG_SECONDARY};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 14px;
        padding: 0;
    }}
    QLabel#kpiTitle {{
        font-size: 12px;
        font-weight: 500;
        color: {C.TEXT_SECONDARY};
    }}
    QLabel#kpiValue {{
        font-size: 28px;
        font-weight: 700;
        color: {C.TEXT_PRIMARY};
    }}
    QLabel#kpiSub {{
        font-size: 11px;
        color: {C.TEXT_DISABLED};
    }}

    /* ================================================================
       AUTH CARD (login / join-org wrapper)
       ================================================================ */
    QFrame#authCard {{
        background-color: {C.BG_SECONDARY};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 18px;
    }}

    QLabel#authTitle {{
        font-size: 26px;
        font-weight: 700;
        color: {C.TEXT_PRIMARY};
    }}
    QLabel#authSubtitle {{
        font-size: 13px;
        color: {C.TEXT_SECONDARY};
    }}
    QLabel#errorLabel {{
        font-size: 12px;
        color: {C.ACCENT_RED};
        font-weight: 500;
    }}
    QLabel#dividerText {{
        font-size: 12px;
        color: {C.TEXT_DISABLED};
    }}

    /* ================================================================
       TABLE (reports)
       ================================================================ */
    QTableWidget {{
        background-color: {C.BG_SECONDARY};
        gridline-color: {C.BORDER_SUBTLE};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 12px;
        font-size: 13px;
    }}
    QTableWidget::item {{
        padding: 10px 14px;
        border-bottom: 1px solid {C.BORDER_SUBTLE};
    }}
    QTableWidget::item:selected {{
        background-color: {C.BG_HOVER};
        color: {C.ACCENT_BLUE};
    }}
    QHeaderView::section {{
        background-color: {C.BG_SIDEBAR};
        color: {C.TEXT_SECONDARY};
        font-weight: 600;
        font-size: 12px;
        padding: 10px 14px;
        border: none;
        border-bottom: 2px solid {C.BORDER_SUBTLE};
    }}

    /* ================================================================
       ACCOUNT / PLAN CARD
       ================================================================ */
    QFrame#planCard {{
        background-color: {C.BG_SECONDARY};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 16px;
    }}
    QLabel#planBadge {{
        background-color: {C.ACCENT_EMERALD};
        color: {C.BG_PRIMARY};
        font-size: 11px;
        font-weight: 700;
        border-radius: 8px;
        padding: 4px 14px;
    }}

    /* ================================================================
       STATUS LED (subscription indicator in sidebar)
       ================================================================ */
    QLabel#ledOnline {{
        background-color: {C.ACCENT_EMERALD};
        border-radius: 5px;
    }}
    QLabel#ledOffline {{
        background-color: {C.ACCENT_AMBER};
        border-radius: 5px;
    }}
    QLabel#ledExpired {{
        background-color: {C.ACCENT_RED};
        border-radius: 5px;
    }}

    /* ================================================================
       WEBCAM PLACEHOLDER
       ================================================================ */
    QFrame#webcamPlaceholder {{
        background-color: #000000;
        border: 2px dashed {C.BORDER_SUBTLE};
        border-radius: 14px;
    }}

    /* ================================================================
       PAGE HEADER
       ================================================================ */
    QLabel#pageHeader {{
        font-size: 22px;
        font-weight: 700;
        color: {C.TEXT_PRIMARY};
    }}
    QLabel#pageSubheader {{
        font-size: 13px;
        color: {C.TEXT_SECONDARY};
    }}

    /* ================================================================
       MISC DIVIDER LINE
       ================================================================ */
    QFrame#hDivider {{
        background-color: {C.BORDER_SUBTLE};
        max-height: 1px;
    }}
    """
