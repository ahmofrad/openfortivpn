"""Certificate trust dialog -- TOFU flow (AUTH.md §6, WIREFRAMES.md cert dialog)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from openfortitray.core.cert_fetch import CertInfo


class CertTrustDialog(QDialog):
    """Shows cert details and asks the user to trust it (TOFU)."""

    def __init__(self, host: str, port: int, cert: CertInfo, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trust Gateway Certificate?")
        self._cert = cert
        self._build_ui(host, port)

    def _build_ui(self, host: str, port: int) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"{host}:{port} presented:"))

        info = QLabel(
            f"<b>Subject:</b>  {self._cert.subject}<br>"
            f"<b>Issuer:</b>   {self._cert.issuer}<br>"
            f"<b>Valid:</b>    {self._cert.not_before} -> {self._cert.not_after}<br>"
            f"<b>SHA-256:</b>  {self._cert.sha256_digest[:47]}..."
        )
        info.setWordWrap(True)
        info.setStyleSheet("padding: 8px;")
        layout.addWidget(info)

        warning = QLabel(
            "\u26a0 Only trust this if you can verify the fingerprint through a "
            "separate channel (ask your network admin, or you manage this gateway)."
        )
        warning.setStyleSheet("color: #CC6600; padding: 8px;")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Save
        )
        buttons.button(QDialogButtonBox.Save).setText("Trust & Save")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def digest_raw(self) -> str:
        """The continuous-hex SHA-256 digest (for trusted-cert config)."""
        return self._cert.sha256_digest_raw
