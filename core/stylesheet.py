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
    QWidget#reportsRoot {{
        background-color: {C.BG_PRIMARY};
    }}
    QFrame#reportsTabPageShell,
    QScrollArea#reportsTabScroll,
    QWidget#reportsTabPage_daily,
    QWidget#reportsTabPage_analytics,
    QWidget#reportsTabPage_monthly,
    QWidget#reportsTabPage_export {{
        background-color: {C.BG_SECONDARY};
    }}
    QScrollArea#reportsTabScroll > QWidget > QWidget {{
        background-color: {C.BG_SECONDARY};
        border: none;
    }}
    QLabel {{
        letter-spacing: 0.1px;
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
        border: none;
        border-right: 1px solid {C.BORDER_SUBTLE};
        border-left: none;
    }}

    QPushButton.nav-btn {{
        background: transparent;
        color: {C.TEXT_SECONDARY};
        text-align: left;
        padding: 12px 14px;
        border: none;
        border-radius: 10px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton.nav-btn:hover {{
        background-color: #E4DCF9;
        color: {C.TEXT_PRIMARY};
    }}
    QPushButton.nav-btn[active="true"] {{
        background-color: #DCD3F8;
        color: #5B21B6;
        font-weight: 600;
        border: 1px solid #CFC4F6;
    }}

    QLabel#sidebarBrand {{
        font-size: 15px;
        font-weight: 700;
        color: {C.TEXT_PRIMARY};
        letter-spacing: 0.1px;
        padding: 0;
    }}
    QLabel#sidebarTagline {{
        font-size: 11px;
        font-weight: 500;
        color: {C.TEXT_DISABLED};
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
        border: 1px solid {C.ACCENT_BLUE};
        border-radius: 12px;
        padding: 12px 0;
        font-size: 14px;
        font-weight: 700;
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
        background-color: {C.BG_SECONDARY};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 12px;
        padding: 12px 0;
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
        border: 1px solid {C.ACCENT_RED};
        border-radius: 12px;
        padding: 12px 0;
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
        color: {C.WHITE};
        border: 1px solid {C.ACCENT_EMERALD};
        border-radius: 14px;
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
        border-radius: 20px;
    }}
    QFrame#authAside {{
        background-color: {C.BG_SECONDARY};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 20px;
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
    QLabel#authAsideTitle {{
        font-size: 22px;
        font-weight: 700;
        color: {C.TEXT_PRIMARY};
    }}
    QLabel#authAsideBody {{
        font-size: 13px;
        color: {C.TEXT_SECONDARY};
        line-height: 1.4;
    }}
    QLabel#authPill {{
        background: {C.BG_INPUT};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 12px;
        font-weight: 600;
        color: {C.TEXT_PRIMARY};
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
    QLabel#mutedText {{
        font-size: 12px;
        color: {C.TEXT_SECONDARY};
    }}
    QPushButton#linkBtn {{
        background: transparent;
        border: none;
        color: {C.ACCENT_BLUE};
        font-size: 12px;
        font-weight: 600;
        padding: 0;
    }}
    QPushButton#linkBtn:hover {{
        color: {C.ACCENT_BLUE_HV};
        text-decoration: underline;
    }}
    QPushButton#backButton {{
        background: {C.BG_INPUT};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 10px;
        color: {C.TEXT_SECONDARY};
        padding: 6px 10px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#backButton:hover {{
        border-color: {C.BORDER_FOCUS};
        color: {C.TEXT_PRIMARY};
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
    QFrame#heroPanel {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 rgba(124, 58, 237, 22),
            stop: 1 rgba(99, 102, 241, 14)
        );
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 14px;
    }}
    QLabel#heroTitle {{
        font-size: 16px;
        font-weight: 700;
        color: {C.TEXT_PRIMARY};
    }}
    QLabel#heroSubtext {{
        font-size: 12px;
        color: {C.TEXT_SECONDARY};
    }}
    QLabel#planBadge {{
        background-color: {C.ACCENT_EMERALD};
        color: {C.WHITE};
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
        background-color: #07090F;
        border: 1px dashed {C.BORDER_SUBTLE};
        border-radius: 14px;
    }}

    QLabel#statusBar {{
        background: #E8EDF5;
        border: 1px solid #CED7E5;
        border-radius: 10px;
        padding: 8px 14px;
        font-size: 13px;
        font-weight: 700;
    }}
    QLabel#quotaBar {{
        background: #E8EDF5;
        border: 1px solid #CED7E5;
        border-radius: 10px;
        padding: 6px 14px;
        font-size: 12px;
        font-weight: 700;
    }}

    QTabWidget#reportsTabs::pane {{
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 12px;
        background: {C.BG_SECONDARY};
        top: 0px;
        margin-top: 0px;
    }}
    QTabWidget#reportsTabs QTabBar::tab {{
        background: {C.BG_INPUT};
        color: {C.TEXT_SECONDARY};
        padding: 10px 20px;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        margin-right: 4px;
        font-size: 12px;
        font-weight: 700;
        border: 1px solid {C.BORDER_SUBTLE};
        border-bottom: 1px solid {C.BORDER_SUBTLE};
    }}
    QTabWidget#reportsTabs QTabBar::tab:selected {{
        background: {C.BG_SECONDARY};
        color: {C.TEXT_PRIMARY};
        border-color: {C.BORDER_SUBTLE};
        border-bottom: 1px solid {C.BG_SECONDARY};
    }}
    QTabWidget#reportsTabs QTabBar::tab:hover {{
        color: {C.TEXT_PRIMARY};
    }}

    QComboBox, QSpinBox {{
        background-color: {C.BG_INPUT};
        color: {C.TEXT_PRIMARY};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 8px;
        padding: 5px 10px;
        font-size: 13px;
    }}
    QComboBox:hover, QSpinBox:hover {{
        border-color: {C.BORDER_FOCUS};
    }}
    QComboBox:focus, QSpinBox:focus {{
        border-color: {C.BORDER_FOCUS};
    }}

    QCheckBox {{
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {C.BORDER_SUBTLE};
        background: {C.BG_INPUT};
    }}
    QCheckBox::indicator:checked {{
        border: 1px solid {C.ACCENT_BLUE};
        background: {C.ACCENT_BLUE};
    }}

    QProgressBar {{
        background: {C.BG_INPUT};
        border: 1px solid {C.BORDER_SUBTLE};
        border-radius: 8px;
        text-align: center;
        font-size: 12px;
        color: {C.TEXT_PRIMARY};
        padding: 1px;
    }}
    QProgressBar::chunk {{
        border-radius: 7px;
    }}

    /* ================================================================
       PAGE HEADER
       ================================================================ */
    QLabel#pageHeader {{
        font-size: 24px;
        font-weight: 700;
        color: {C.TEXT_PRIMARY};
        letter-spacing: -0.3px;
    }}
    QLabel#pageSubheader {{
        font-size: 13px;
        color: {C.TEXT_SECONDARY};
        font-weight: 400;
    }}

    /* ================================================================
       MISC DIVIDER LINE
       ================================================================ */
    QFrame#hDivider {{
        background-color: {C.BORDER_SUBTLE};
        max-height: 1px;
    }}
    """
