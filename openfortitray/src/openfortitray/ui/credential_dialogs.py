"""Credential prompt dialogs for interactive password/OTP entry."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class PasswordPromptDialog(QDialog):
    """Small dialog asking for VPN username and password."""

    def __init__(self, username: str = "", host: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VPN Credentials")
        self.setMinimumWidth(320)
        self._build_ui(username, host)

    def _build_ui(self, username: str, host: str) -> None:
        layout = QVBoxLayout(self)
        if host:
            layout.addWidget(QLabel(f"Connecting to: {host}"))

        form = QFormLayout()
        self.edit_username = QLineEdit()
        self.edit_username.setText(username)
        form.addRow("Username:", self.edit_username)

        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)
        form.addRow("Password:", self.edit_password)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def username(self) -> str:
        return self.edit_username.text().strip()

    @property
    def password(self) -> str:
        return self.edit_password.text()


class OtpPromptDialog(QDialog):
    """Small dialog asking for an OTP code."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OTP Required")
        self.setMinimumWidth(280)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Please enter one-time password:"))

        self.edit_otp = QLineEdit()
        self.edit_otp.setEchoMode(QLineEdit.Password)
        self.edit_otp.setPlaceholderText("6-digit code")
        self.edit_otp.returnPressed.connect(self.accept)
        layout.addWidget(self.edit_otp)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def otp(self) -> str:
        return self.edit_otp.text().strip()
