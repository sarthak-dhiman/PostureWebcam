"""
login_page.py — Centred authentication form with threaded login.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QSpacerItem, QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

from core.constants import C, APP_NAME
from core.icons import icon
from core.workers import LoginWorker
from core.workers import OAuthInitWorker, OAuthPollWorker


class LoginPage(QWidget):
    """Full-bleed login page (sidebar is hidden while this is shown).

    Signals
    -------
    login_success(dict)  – emitted with user payload on successful auth
    """

    login_success = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: LoginWorker | None = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        # ── Card ────────────────────────────────────────────────────
        card = QFrame()
        card.setObjectName("authCard")
        card.setFixedWidth(420)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(36, 44, 36, 40)
        card_lay.setSpacing(0)

        # Title
        title = QLabel("Welcome Back")
        title.setObjectName("authTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(title)
        card_lay.addSpacing(6)

        subtitle = QLabel(f"Sign in to {APP_NAME}")
        subtitle.setObjectName("authSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(subtitle)
        card_lay.addSpacing(28)

        # Email
        self._email = QLineEdit()
        self._email.setPlaceholderText("Email address")
        card_lay.addWidget(self._email)
        card_lay.addSpacing(12)

        # Password
        self._password = QLineEdit()
        self._password.setPlaceholderText("Password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        card_lay.addWidget(self._password)
        card_lay.addSpacing(8)

        # Error label (hidden by default)
        self._error = QLabel("")
        self._error.setObjectName("errorLabel")
        self._error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error.setVisible(False)
        card_lay.addWidget(self._error)
        card_lay.addSpacing(18)

        # Login button
        self._login_btn = QPushButton("Sign In")
        self._login_btn.setObjectName("primaryBtn")
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.clicked.connect(self._on_login_clicked)
        card_lay.addWidget(self._login_btn)
        card_lay.addSpacing(16)

        # ── Divider ─────────────────────────────────────────────────
        div_row = QHBoxLayout()
        line_l = QFrame(); line_l.setObjectName("hDivider"); line_l.setFrameShape(QFrame.Shape.HLine)
        line_r = QFrame(); line_r.setObjectName("hDivider"); line_r.setFrameShape(QFrame.Shape.HLine)
        or_lbl = QLabel("or")
        or_lbl.setObjectName("dividerText")
        or_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        or_lbl.setFixedWidth(30)
        div_row.addWidget(line_l, 1)
        div_row.addWidget(or_lbl)
        div_row.addWidget(line_r, 1)
        card_lay.addLayout(div_row)
        card_lay.addSpacing(16)

        # Google button
        self._google_btn = QPushButton("  Sign in with Google")
        self._google_btn.setIcon(icon("google"))
        self._google_btn.setObjectName("googleBtn")
        self._google_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._google_btn.setToolTip("Sign in with Google")
        self._google_btn.clicked.connect(self._on_google_clicked)
        card_lay.addWidget(self._google_btn)
        card_lay.addSpacing(10)

        # Signup row
        signup_row = QHBoxLayout()
        signup_row.addStretch()
        signup_lbl = QLabel("No account?")
        signup_lbl.setObjectName("mutedText")
        signup_row.addWidget(signup_lbl)
        signup_btn = QPushButton("Sign up")
        signup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        signup_btn.setObjectName("linkBtn")
        signup_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("http://localhost:3000/signup")))
        signup_row.addWidget(signup_btn)
        signup_row.addStretch()
        card_lay.addLayout(signup_row)
        card_lay.addSpacing(12)

        # Footer links (includes app name)
        links = QLabel(f'<a href="http://localhost:3000">{APP_NAME}</a> • <a href="http://localhost:3000/privacy">Privacy</a> • <a href="http://localhost:3000/terms">Terms</a>')
        links.setObjectName("mutedText")
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links.setOpenExternalLinks(True)
        card_lay.addWidget(links)

        # Vertically centre the card
        col = QVBoxLayout()
        col.addStretch()
        col.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addStretch()

        outer.addLayout(col, 0)
        outer.addStretch()

        # Allow Enter key to submit
        self._password.returnPressed.connect(self._on_login_clicked)
        self._email.returnPressed.connect(lambda: self._password.setFocus())

    # ── Handlers ────────────────────────────────────────────────────────
    def _on_login_clicked(self):
        self._error.setVisible(False)
        self._login_btn.setEnabled(False)
        self._login_btn.setText("Signing in...")

        self._worker = LoginWorker(
            email=self._email.text().strip(),
            password=self._password.text(),
        )
        self._worker.login_success.connect(self._handle_success)
        self._worker.login_failed.connect(self._handle_failure)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _on_google_clicked(self):
        self._error.setVisible(False)
        self._google_btn.setEnabled(False)
        self._google_btn.setText("Connecting...")

        self._oauth_init_worker = OAuthInitWorker()
        self._oauth_init_worker.init_success.connect(self._on_oauth_init_success)
        self._oauth_init_worker.init_failed.connect(self._on_oauth_init_failed)
        self._oauth_init_worker.finished.connect(lambda: setattr(self, '_oauth_init_worker', None))
        self._oauth_init_worker.start()

    def _on_oauth_init_success(self, url: str, session: str):
        self._google_btn.setText("Opening browser...")
        # Open the provider URL in the system browser
        QDesktopServices.openUrl(QUrl(url))

        # Start polling worker
        self._oauth_worker = OAuthPollWorker(session_id=session, timeout_s=120)
        self._oauth_worker.oauth_success.connect(self._handle_oauth_success)
        self._oauth_worker.oauth_failed.connect(self._handle_oauth_failure)
        self._oauth_worker.finished.connect(self._cleanup_oauth)
        self._oauth_worker.start()

    def _on_oauth_init_failed(self, msg: str):
        self._error.setText(msg)
        self._error.setVisible(True)
        self._google_btn.setEnabled(True)
        self._google_btn.setText("  Sign in with Google")

    def _handle_oauth_success(self, user: dict):
        self.login_success.emit(user)

    def _handle_oauth_failure(self, msg: str):
        self._error.setText(msg)
        self._error.setVisible(True)

    def _cleanup_oauth(self):
        self._google_btn.setEnabled(True)
        self._google_btn.setText("  Sign in with Google")
        self._oauth_worker = None

    def _handle_success(self, user: dict):
        self.login_success.emit(user)

    def _handle_failure(self, msg: str):
        self._error.setText(msg)
        self._error.setVisible(True)
        self._login_btn.setEnabled(True)
        self._login_btn.setText("Sign In")

    def _cleanup_worker(self):
        self._login_btn.setEnabled(True)
        self._login_btn.setText("Sign In")
        self._worker = None

    def reset(self):
        """Clear fields for next use."""
        self._email.clear()
        self._password.clear()
        self._error.setVisible(False)
        self._login_btn.setEnabled(True)
        self._login_btn.setText("Sign In")
