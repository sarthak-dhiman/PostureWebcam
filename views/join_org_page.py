"""
join_org_page.py — Join an organisation by invite code (reusable, on-demand).

Can be opened both after first-time login and at any time from the
Dashboard or Account page via the "Join Organisation" button.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt

from core.constants import C
from core.workers import OrgJoinWorker, _read_local_auth


class JoinOrgPage(QWidget):
    """User enters an invite code; the code is validated server-side.

    Signals
    -------
    org_joined()   – emitted on successful join or workspace creation
    cancelled()    – emitted when the user clicks the back / cancel button
    """

    org_joined = pyqtSignal()
    cancelled  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: OrgJoinWorker | None = None

        # ── Root layout ─────────────────────────────────────────────
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # Back / cancel button (top-left, always visible)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(16, 12, 16, 0)
        self._back_btn = QPushButton("← Back")
        self._back_btn.setObjectName("linkBtn")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setFixedWidth(80)
        self._back_btn.clicked.connect(self._on_cancel)
        top_bar.addWidget(self._back_btn)
        top_bar.addStretch()
        page_layout.addLayout(top_bar)

        # Centre the card
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        card = QFrame()
        card.setObjectName("authCard")
        card.setFixedWidth(460)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(36, 44, 36, 40)
        lay.setSpacing(0)

        # Title
        title = QLabel("Join Your Organisation")
        title.setObjectName("authTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(6)

        sub = QLabel("Paste the invite code sent by your administrator,\nor create a new personal workspace.")
        sub.setObjectName("authSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addSpacing(28)

        # Invite code input
        self._code_input = QLineEdit()
        self._code_input.setPlaceholderText("Organisation invite code")
        lay.addWidget(self._code_input)
        lay.addSpacing(12)

        # Error / success label
        self._msg = QLabel("")
        self._msg.setObjectName("errorLabel")
        self._msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg.setVisible(False)
        self._msg.setWordWrap(True)
        lay.addWidget(self._msg)
        lay.addSpacing(10)

        # Join button
        self._join_btn = QPushButton("Join Organisation")
        self._join_btn.setObjectName("primaryBtn")
        self._join_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._join_btn.clicked.connect(self._on_join)
        lay.addWidget(self._join_btn)
        lay.addSpacing(16)

        # Divider
        div_row = QHBoxLayout()
        line_l = QFrame()
        line_l.setObjectName("hDivider")
        line_l.setFrameShape(QFrame.Shape.HLine)
        line_r = QFrame()
        line_r.setObjectName("hDivider")
        line_r.setFrameShape(QFrame.Shape.HLine)
        or_lbl = QLabel("or")
        or_lbl.setObjectName("dividerText")
        or_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        or_lbl.setFixedWidth(30)
        div_row.addWidget(line_l, 1)
        div_row.addWidget(or_lbl)
        div_row.addWidget(line_r, 1)
        lay.addLayout(div_row)
        lay.addSpacing(16)

        # Create workspace
        self._create_btn = QPushButton("Create New Workspace")
        self._create_btn.setObjectName("secondaryBtn")
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.clicked.connect(self._on_create)
        lay.addWidget(self._create_btn)

        # Centre card vertically
        col = QVBoxLayout()
        col.addStretch()
        col.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addStretch()

        outer.addLayout(col, 0)
        outer.addStretch()
        page_layout.addLayout(outer)

        self._code_input.returnPressed.connect(self._on_join)

    # ── Public helpers ───────────────────────────────────────────────────
    def reset(self):
        """Clear the input and any messages — call before opening the page."""
        self._code_input.clear()
        self._msg.setVisible(False)
        self._set_busy(False)

    # ── Handlers ────────────────────────────────────────────────────────
    def _on_join(self):
        code = self._code_input.text().strip()
        if not code:
            self._show_error("Please enter an invite code.")
            return

        # Read token on the main thread before handing off to the worker —
        # this guarantees we use the live session token rather than relying
        # on a disk read inside the background thread.
        cached = _read_local_auth()
        token = (cached or {}).get("token") or ""

        self._show_error("")
        self._set_busy(True)

        self._worker = OrgJoinWorker(invite_code=code, token=token)
        self._worker.join_success.connect(self._handle_success)
        self._worker.join_failed.connect(self._handle_failure)
        self._worker.finished.connect(lambda: setattr(self, "_worker", None))
        self._worker.start()

    def _on_create(self):
        """Skip the invite-code flow and create a personal workspace."""
        self._show_error("")
        self._set_busy(True)
        self._create_btn.setText("Creating…")
        # No server round-trip needed for solo workspace creation;
        # emit immediately so the caller can navigate away.
        self.org_joined.emit()

    def _on_cancel(self):
        if self._worker is not None:
            try:
                self._worker.terminate()
            except Exception:
                pass
            self._worker = None
        self._set_busy(False)
        self._msg.setVisible(False)
        self.cancelled.emit()

    def _handle_success(self, org_name: str):
        self._set_busy(False)
        self._show_success(f"Joined \"{org_name}\" successfully!")
        # Brief pause so the user can read the message, then emit.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(900, self.org_joined.emit)

    def _handle_failure(self, msg: str):
        self._set_busy(False)
        self._show_error(msg)

    # ── Internal helpers ─────────────────────────────────────────────────
    def _set_busy(self, busy: bool):
        self._join_btn.setEnabled(not busy)
        self._create_btn.setEnabled(not busy)
        self._code_input.setEnabled(not busy)
        self._back_btn.setEnabled(not busy)
        if busy:
            self._join_btn.setText("Verifying…")
        else:
            self._join_btn.setText("Join Organisation")
            self._create_btn.setText("Create New Workspace")

    def _show_error(self, text: str):
        if not text:
            self._msg.setVisible(False)
            return
        self._msg.setStyleSheet(f"color: {C.ACCENT_RED}; font-size: 13px;")
        self._msg.setText(text)
        self._msg.setVisible(True)

    def _show_success(self, text: str):
        self._msg.setStyleSheet(f"color: {C.ACCENT_EMERALD}; font-size: 13px;")
        self._msg.setText(text)
        self._msg.setVisible(True)

    def _show_join_form(self):
        """Reveal the invite-code form below the preferences."""
        self._reveal_join_btn.setVisible(False)
        self._join_container.setVisible(True)
        self._code_input.setFocus()
