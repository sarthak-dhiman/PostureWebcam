"""
app_window.py — MainWindow: owns sidebar, QStackedWidget, SubscriptionMonitor.
"""

import os as _os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QPushButton, QSpacerItem, QSizePolicy, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from core.constants import (
    APP_NAME,
    PAGE_LOGIN, PAGE_JOIN_ORG, PAGE_DASHBOARD, PAGE_REPORTS, PAGE_ACCOUNT,
)
from core.workers import SubscriptionMonitor, _read_local_auth, _write_local_auth, _clear_local_auth, PostureTrackerThread
from widgets.sidebar import Sidebar
from views.login_page import LoginPage
from views.join_org_page import JoinOrgPage
from views.user_settings_page import UserSettingsPage
from views.dashboard_page import DashboardPage
from views.reports_page import ReportsPage
from views.account_page import AccountPage


class MainWindow(QMainWindow):
    """Root application window.

    Layout
    ------
    ┌────────────┬──────────────────────────────────────┐
    │  Sidebar   │  QStackedWidget (pages)              │
    │  (hidden   │    0 – LoginPage                     │
    │   until    │    1 – JoinOrgPage                   │
    │   authed)  │    2 – DashboardPage                 │
    │            │    3 – ReportsPage                   │
    │            │    4 – AccountPage                   │
    └────────────┴──────────────────────────────────────┘
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        # Set window/taskbar icon
        try:
            _icon_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "office.png")
            if _os.path.isfile(_icon_file):
                self.setWindowIcon(QIcon(_icon_file))
        except Exception:
            pass
        # Responsive default size: prefer ~95% width and limited height (not too tall)
        from PyQt6.QtWidgets import QApplication as _QApp
        _app = _QApp.instance()
        if _app is None:
            self.setMinimumSize(900, 640)
            self.resize(1100, 740)
        else:
            try:
                screen = _QApp.primaryScreen()
                geom = screen.availableGeometry()
                screen_w = geom.width()
                screen_h = geom.height()
                # ~80% of screen width, ~85% of screen height — more square/proportional
                target_w = min(int(screen_w * 0.80), 1200)
                target_h = min(int(screen_h * 0.85), 820)
                self.setMinimumSize(900, 640)
                self.resize(target_w, target_h)
            except Exception:
                self.setMinimumSize(900, 640)
                self.resize(1100, 740)

        self._user: dict | None = None

        # ── Central widget ──────────────────────────────────────────
        central = QWidget()
        central.setObjectName("centralRoot")
        self.setCentralWidget(central)

        # Outer vertical layout: top bar + main content
        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # Top bar: back button on the far left
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(6, 6, 6, 6)
        top_bar.setSpacing(6)
        try:
            from core.icons import icon
        except Exception:
            icon = lambda name: None

        self._back_btn = QPushButton()
        self._back_btn.setObjectName("backButton")
        self._back_btn.setFixedSize(36, 36)
        btn_icon = icon("back")
        if btn_icon:
            self._back_btn.setIcon(btn_icon)
        self._back_btn.setVisible(False)
        self._back_btn.clicked.connect(self._on_logout)

        top_bar.addWidget(self._back_btn)
        top_bar.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self._root_layout.addLayout(top_bar)

        # Main content layout holds sidebar + stacked pages
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ── Sidebar ─────────────────────────────────────────────────
        self._sidebar = Sidebar()
        self._sidebar.nav_requested.connect(self._navigate_to)
        self._sidebar.setVisible(False)
        content_layout.addWidget(self._sidebar)

        # ── Stacked pages ───────────────────────────────────────────
        self._stack = QStackedWidget()
        content_layout.addWidget(self._stack, 1)

        self._root_layout.addLayout(content_layout)

        self._login_page     = LoginPage()
        self._user_settings_page = UserSettingsPage()
        self._join_org_page  = JoinOrgPage()
        self._dashboard_page = DashboardPage()
        self._reports_page   = ReportsPage()
        self._account_page   = AccountPage()

        self._stack.insertWidget(PAGE_LOGIN,     self._login_page)
        # Show user settings by default for first-time users; the join
        # organisation page remains available via the settings button.
        self._stack.insertWidget(PAGE_JOIN_ORG,  self._user_settings_page)
        self._stack.insertWidget(PAGE_DASHBOARD, self._dashboard_page)
        self._stack.insertWidget(PAGE_REPORTS,   self._reports_page)
        # Keep the normal account page at PAGE_ACCOUNT and add the canonical
        # join-org page on the stack (app will navigate to it when needed).
        self._stack.insertWidget(PAGE_ACCOUNT,   self._account_page)
        # Add the join-org page as a secondary widget (index retrieved at runtime)
        self._stack.addWidget(self._join_org_page)

        # ── Wire auth signals ───────────────────────────────────────
        self._login_page.login_success.connect(self._on_login_success)
        self._join_org_page.org_joined.connect(self._on_org_joined)
        # When user requests to join from settings, navigate to the join-org widget
        self._user_settings_page.go_to_join.connect(lambda: self._stack.setCurrentIndex(self._stack.indexOf(self._join_org_page)))
        self._user_settings_page.solo_continue.connect(self._show_main_app)
        self._account_page.logout_btn.clicked.connect(self._on_logout)
        self._account_page.settings_changed.connect(self._dashboard_page.reload_dial_config)

        # ── Subscription monitor and tracker are created only after login
        # They must not run while the user is signed out.
        self._sub_monitor = None
        self._tracker = None
        # Wire dashboard toggle; tracker may be created later
        self._dashboard_page.tracking_toggled.connect(self._on_tracking_toggled)

        # Wire full shutdown to app quit (tray "Quit"), NOT to window close
        from PyQt6.QtWidgets import QApplication as _QApp
        _app = _QApp.instance()
        if _app is not None:
            _app.aboutToQuit.connect(self._full_shutdown)

        # ── Auto-login from cache if available ─────────────────────
        cached = _read_local_auth()
        if cached and cached.get("token") and cached.get("expires_at"):
            try:
                exp = cached.get("expires_at")
                from datetime import datetime, timezone
                if datetime.fromisoformat(exp) > datetime.now(timezone.utc):
                    # Restore user state
                    self._user = cached
                    self._sidebar.set_user_email(cached.get("email", ""))
                    self._account_page.set_user(cached.get("email", ""), cached.get("plan", "—"))

                    # Apply dashboard subscription gate from cached data
                    sub = cached.get("subscription") or {}
                    has_sub = sub.get("status") == "active"
                    try:
                        self._dashboard_page.show_subscription_gate(not has_sub)
                    except Exception:
                        pass

                    if cached.get("first_time", False):
                        # Defer so the window paints its initial blank state first
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(50, lambda: self._stack.setCurrentIndex(PAGE_JOIN_ORG))
                    else:
                        # Defer navigation + DB load so window renders before stats populate
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(50, self._show_main_app)
                else:
                    # expired — show login
                    self._stack.setCurrentIndex(PAGE_LOGIN)
            except Exception:
                self._stack.setCurrentIndex(PAGE_LOGIN)
        else:
            # Default start on login
            self._stack.setCurrentIndex(PAGE_LOGIN)

    # ── Navigation ──────────────────────────────────────────────────────
    def _navigate_to(self, page_idx: int):
        self._stack.setCurrentIndex(page_idx)
        self._sidebar.set_active_page(page_idx)
        # Do not show the back button by default; keep navigation controls in the sidebar.
        self._back_btn.setVisible(False)

    # ── Auth flow ───────────────────────────────────────────────────────
    def _on_login_success(self, user: dict):
        self._user = user
        email = user.get("email", "")
        plan  = user.get("plan") or "—"

        self._sidebar.set_user_email(email)
        self._account_page.set_user(email, plan)

        # Check subscription from login payload and apply gate immediately
        sub = user.get("subscription") or {}
        has_sub = sub.get("status") == "active"
        try:
            self._dashboard_page.show_subscription_gate(not has_sub)
        except Exception:
            pass

        # Start subscription monitoring now that we have a logged-in user
        try:
            if self._sub_monitor is None:
                self._sub_monitor = SubscriptionMonitor(parent=self)
                self._sub_monitor.status_changed.connect(self._on_sub_status)
                self._sub_monitor.start()
        except Exception:
            pass

        # Create and start tracker thread (kept on hold until subscription confirmed)
        try:
            if self._tracker is None:
                self._tracker = PostureTrackerThread(poll_interval_ms=500, parent=self)
                self._tracker.posture_update.connect(self._dashboard_page.on_posture_update)
                self._tracker.posture_update.connect(self._reports_page.append_sample)
                self._tracker.start()
                # Tracker starts on hold — daemon will only be spawned once
                # the subscription monitor confirms an active subscription.
                try:
                    self._tracker.set_hold(True)
                except Exception:
                    pass
        except Exception:
            self._tracker = None

        if user.get("first_time", False):
            self._stack.setCurrentIndex(PAGE_JOIN_ORG)
        else:
            self._show_main_app()

    def _on_org_joined(self):
        # Mark onboarding complete in cache so next launch skips join-org
        cached = _read_local_auth()
        if cached:
            cached["first_time"] = False
            _write_local_auth(cached)
        self._show_main_app()

    def _show_main_app(self):
        # Mark onboarding complete in cache so next launch goes straight to dashboard
        cached = _read_local_auth()
        if cached and cached.get("first_time"):
            cached["first_time"] = False
            _write_local_auth(cached)
        self._sidebar.setVisible(True)
        self._navigate_to(PAGE_DASHBOARD)
        # Always auto-start tracking when navigating to the dashboard —
        # the user is authenticated at this point so there is no reason to
        # block.  Deferred so the page paints its initial state first.
        try:
            # Only auto-start tracking if the user has an active subscription.
            sub = (self._user or {}).get("subscription") or {}
            has_sub = sub.get("status") == "active"
            if has_sub:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(150, self._dashboard_page.auto_start_tracking)
        except Exception:
            pass

    def _on_logout(self):
        self._user = None
        _clear_local_auth()
        # Immediately hold the tracker — don't wait for subscription monitor
        try:
            if hasattr(self, "_tracker") and self._tracker is not None:
                self._tracker.set_hold(True)
        except Exception:
            pass
        self._sidebar.setVisible(False)
        self._login_page.reset()
        self._stack.setCurrentIndex(PAGE_LOGIN)

    def _on_toggle_maximize(self):
        try:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
        except Exception:
            pass

    # ── Subscription status ─────────────────────────────────────────────
    def _on_tracking_toggled(self, want_tracking: bool):
        """Wired to dashboard toggle button; starts or pauses the tracker."""
        try:
            if self._tracker is None:
                return
            if want_tracking:
                self._tracker.start_capture()
            else:
                self._tracker.set_hold(True)
        except Exception:
            pass

    def _on_sub_status(self, status: str, detail: str):
        """Handle subscription monitor changes and toggle tracker accordingly.

        status values: "online" | "offline" | "expired"
        """
        try:
            self._sidebar.set_subscription_status(status, detail)
            self._account_page.set_subscription_status(status, detail)
        except Exception:
            pass

        # Show/hide dashboard subscription gate
        no_sub = (status == "expired")
        try:
            self._dashboard_page.show_subscription_gate(no_sub)
        except Exception:
            pass

        # Determine hold state
        if status == "online":
            should_hold = False
        elif status == "expired":
            should_hold = True
        else:  # offline
            should_hold = self._user is None

        try:
            if hasattr(self, "_tracker") and self._tracker is not None:
                self._tracker.set_hold(should_hold)
        except Exception:
            pass

    # ── Cleanup ─────────────────────────────────────────────────────────
    def closeEvent(self, event):
        """Hide the window instead of quitting — tracker keeps running in the tray."""
        event.ignore()
        self.hide()

    def _full_shutdown(self):
        """Called only when QApplication is about to quit (tray Quit action)."""
        # Stop subscription monitor
        try:
            self._sub_monitor.stop()
            self._sub_monitor.quit()
            self._sub_monitor.wait(3000)
        except Exception:
            pass

        # Shutdown tracker thread and its daemon subprocess
        try:
            if hasattr(self, "_tracker") and self._tracker is not None:
                try:
                    self._tracker.shutdown()
                except Exception:
                    pass
                try:
                    self._tracker.wait(2000)
                except Exception:
                    pass
        except Exception:
            pass

    def ensure_tracker_daemon(self):
        """Ensure the tracker daemon subprocess is running (no capture).

        This is intended to be called once during startup so the dashboard can
        immediately read live stats from the daemon when shown.
        """
        try:
            if hasattr(self, "_tracker") and self._tracker is not None:
                # Do not change hold state; only ensure daemon process exists
                try:
                    self._tracker.ensure_daemon_running()
                except Exception:
                    pass
        except Exception:
            pass
