"""
user_settings_page.py — Solo user settings shown after first login.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt


class UserSettingsPage(QWidget):
    """A simple preferences-style page for solo users.

    Signals
    -------
    go_to_join()     – emitted when user wants to open the join org page
    solo_continue()  – emitted when user chooses to continue without an org
    """

    go_to_join    = pyqtSignal()
    solo_continue = pyqtSignal()

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

        title = QLabel("Your Account")
        title.setObjectName("authTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(6)

        sub = QLabel("Manage your personal settings and preferences.")
        sub.setObjectName("authSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addSpacing(18)

        # Display name
        self._display_name = QLineEdit()
        self._display_name.setPlaceholderText("Display name")
        lay.addWidget(self._display_name)
        lay.addSpacing(8)

        # Small gap before actions
        lay.addSpacing(18)

        # Primary action — continue without an org
        solo_btn = QPushButton("Continue as Solo User")
        solo_btn.setObjectName("primaryBtn")
        solo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        solo_btn.clicked.connect(lambda: self.solo_continue.emit())
        lay.addWidget(solo_btn)
        lay.addSpacing(10)

        # Secondary action — join an organisation
        join_btn = QPushButton("Join an organization")
        join_btn.setObjectName("secondaryBtn")
        join_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        join_btn.clicked.connect(lambda: self.go_to_join.emit())
        lay.addWidget(join_btn)

        # Centre vertically
        col = QVBoxLayout()
        col.addStretch()
        col.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addStretch()

        outer.addLayout(col, 0)
        outer.addStretch()

    def set_user(self, email: str | None, display_name: str | None = None):
        # For solo onboarding we don't ask for or show the email address;
        # only set the display name if provided.
        if display_name:
            self._display_name.setText(display_name)
