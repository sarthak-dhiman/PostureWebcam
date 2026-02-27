"""
join_org_page.py — Post-signup organization / workspace selection.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt

from core.constants import C


class JoinOrgPage(QWidget):
    """Shown after first-time login.  User either joins an org or creates one.

    Signals
    -------
    org_joined()   – emitted when the user picks an org (or creates a workspace)
    """

    org_joined = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        card = QFrame()
        card.setObjectName("authCard")
        card.setFixedWidth(460)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(36, 44, 36, 40)
        lay.setSpacing(0)

        # Title
        title = QLabel("Join Your Organization")
        title.setObjectName("authTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(6)

        sub = QLabel("Enter an invite code, or create a new workspace.")
        sub.setObjectName("authSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addSpacing(28)

        # Invite code input
        self._code_input = QLineEdit()
        self._code_input.setPlaceholderText("Organization invite code")
        lay.addWidget(self._code_input)
        lay.addSpacing(14)

        # Error label
        self._error = QLabel("")
        self._error.setObjectName("errorLabel")
        self._error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error.setVisible(False)
        lay.addWidget(self._error)
        lay.addSpacing(10)

        # Join button
        join_btn = QPushButton("Join Organization")
        join_btn.setObjectName("primaryBtn")
        join_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        join_btn.clicked.connect(self._on_join)
        lay.addWidget(join_btn)
        lay.addSpacing(16)

        # Divider
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
        lay.addLayout(div_row)
        lay.addSpacing(16)

        # Create workspace
        create_btn = QPushButton("Create New Workspace")
        create_btn.setObjectName("secondaryBtn")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self._on_create)
        lay.addWidget(create_btn)

        # Centre vertically
        col = QVBoxLayout()
        col.addStretch()
        col.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addStretch()

        outer.addLayout(col, 0)
        outer.addStretch()

        self._code_input.returnPressed.connect(self._on_join)

    # ── Handlers ────────────────────────────────────────────────────────
    def _on_join(self):
        code = self._code_input.text().strip()
        if not code:
            self._error.setText("Please enter an invite code.")
            self._error.setVisible(True)
            return
        # Mock: accept any non-empty code
        self._error.setVisible(False)
        self.org_joined.emit()

    def _on_create(self):
        # Mock: instant workspace creation
        self._error.setVisible(False)
        self.org_joined.emit()

    def _show_join_form(self):
        """Reveal the invite-code form below the preferences."""
        self._reveal_join_btn.setVisible(False)
        self._join_container.setVisible(True)
        self._code_input.setFocus()
