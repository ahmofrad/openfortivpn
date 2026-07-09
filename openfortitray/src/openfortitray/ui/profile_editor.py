"""Profile editor dialog with Basic + Advanced tabs."""

from __future__ import annotations

import logging
import subprocess
import sys

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from openfortitray.core.cert_fetch import fetch_certificate
from openfortitray.core.profile import VpnProfile

logger = logging.getLogger(__name__)


class ProfileEditor(QDialog):
    """Add/edit a VPN profile. Two tabs: Basic and Advanced."""

    def __init__(
        self,
        profile: VpnProfile | None = None,
        secret_store=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Profile")
        self.setMinimumWidth(480)
        self._secret_store = secret_store
        self._profile = profile or VpnProfile()
        self._is_new = profile is None

        if self._is_new:
            self.setWindowTitle("Add Profile")

        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(self._build_basic_tab(), "Basic")
        tabs.addTab(self._build_advanced_tab(), "Advanced")

        # Bottom buttons: Create Shortcut | Cancel | Save
        bottom_row = QHBoxLayout()
        self.btn_shortcut = QPushButton("Create Shortcut")
        self.btn_shortcut.clicked.connect(self._on_create_shortcut)
        bottom_row.addWidget(self.btn_shortcut)
        bottom_row.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Save
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        bottom_row.addWidget(buttons)
        layout.addLayout(bottom_row)

    # ── Basic tab ───────────────────────────────────────────────

    def _build_basic_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Required")
        form.addRow("Name *:", self.edit_name)

        # Host(s) with add/remove buttons
        host_row = QHBoxLayout()
        self.host_inputs: list[QLineEdit] = []
        self._host_container = QVBoxLayout()
        self._host_container.setSpacing(2)
        host_row.addLayout(self._host_container)

        # Add host button
        self.btn_add_host = QPushButton("+")
        self.btn_add_host.setMaximumWidth(24)
        self.btn_add_host.setMaximumHeight(24)
        self.btn_add_host.setToolTip("Add another host")
        self.btn_add_host.clicked.connect(lambda: self._add_host_field(""))
        host_row.addWidget(self.btn_add_host)
        form.addRow("Host(s):", host_row)

        # Port (no spin buttons, numbers only)
        self.edit_port = QLineEdit()
        self.edit_port.setText("443")
        self.edit_port.setPlaceholderText("443")
        from PySide6.QtGui import QIntValidator

        self.edit_port.setValidator(QIntValidator(1, 65535))
        self.edit_port.setMaximumWidth(80)
        form.addRow("Port:", self.edit_port)

        self.edit_username = QLineEdit()
        form.addRow("Username:", self.edit_username)

        # Password
        pwd_row = QHBoxLayout()
        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)
        self.edit_password.setPlaceholderText(
            "(unchanged)" if not self._is_new else ""
        )
        pwd_row.addWidget(self.edit_password)
        self.chk_remember = QCheckBox("Remember")
        self.chk_remember.setChecked(True)
        pwd_row.addWidget(self.chk_remember)
        form.addRow("Password:", pwd_row)

        # OTP checkbox
        self.chk_otp = QCheckBox("Use OTP (TOTP seed)")
        self.chk_otp.toggled.connect(self._on_otp_toggled)
        form.addRow("", self.chk_otp)

        # OTP seed row (hidden until checkbox is checked)
        self.edit_seed = QLineEdit()
        self.edit_seed.setPlaceholderText("Paste Base32 seed or otpauth:// URI")
        self.edit_seed.setEchoMode(QLineEdit.Password)
        self.lbl_seed = QLabel("OTP Seed:")
        form.addRow(self.lbl_seed, self.edit_seed)

        self.lbl_seed_hint = QLabel(
            "Stored encrypted in OS keyring. Codes generated automatically (RFC 6238)."
        )
        self.lbl_seed_hint.setStyleSheet("color: gray; font-size: 11px;")
        self.lbl_seed_hint.setWordWrap(True)
        form.addRow("", self.lbl_seed_hint)

        return tab

    def _add_host_field(self, value: str = "") -> None:
        """Add a host input row with a remove button."""
        row = QHBoxLayout()
        inp = QLineEdit()
        inp.setText(value)
        inp.textChanged.connect(self._on_host_input_changed)
        row.addWidget(inp)
        self.host_inputs.append(inp)

        # Remove button (only show if more than 1 field)
        btn_rm = QPushButton("-")
        btn_rm.setMaximumWidth(24)
        btn_rm.setMaximumHeight(24)
        btn_rm.setToolTip("Remove this host")

        def remove_self():
            self._host_container.removeItem(row)
            inp.deleteLater()
            btn_rm.deleteLater()
            self.host_inputs.remove(inp)
            self._on_host_input_changed()

        btn_rm.clicked.connect(remove_self)
        row.addWidget(btn_rm)
        self._host_container.addLayout(row)
        self._on_host_input_changed()

    def _on_host_input_changed(self) -> None:
        """Update placeholders based on number of host fields."""
        multi = len(self.host_inputs) > 1
        placeholder = "IP:port or FQDN:port" if multi else "IP or FQDN"
        for inp in self.host_inputs:
            if not inp.text():
                inp.setPlaceholderText(placeholder)

    # ── Advanced tab ────────────────────────────────────────────

    def _build_advanced_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        # Realm
        self.edit_realm = QLineEdit()
        self.edit_realm.setPlaceholderText("(usually empty)")
        form.addRow("Realm:", self.edit_realm)

        self.chk_insecure = QCheckBox("Allow insecure TLS ciphers")
        form.addRow("", self.chk_insecure)

        self.edit_ca_file = QLineEdit()
        self.edit_ca_file.setPlaceholderText("(optional)")
        form.addRow("CA bundle file:", self.edit_ca_file)

        # Routing & DNS
        routing_label = QLabel("<b>Routing & DNS</b>")
        form.addRow("", routing_label)

        self.chk_routes = QCheckBox("Set routes through VPN")
        form.addRow("", self.chk_routes)

        self.chk_half = QCheckBox("Half-internet routes (split default)")
        form.addRow("", self.chk_half)

        self.chk_dns = QCheckBox("Set DNS from gateway")
        form.addRow("", self.chk_dns)

        self.chk_peerdns = QCheckBox("Use pppd peer DNS (Linux/macOS)")
        form.addRow("", self.chk_peerdns)

        self.edit_ifname = QLineEdit()
        self.edit_ifname.setPlaceholderText("(optional)")
        form.addRow("Bind interface:", self.edit_ifname)

        # Reconnect
        recon_label = QLabel("<b>Reconnect</b>")
        form.addRow("", recon_label)

        self.chk_reconnect = QCheckBox("Reconnect automatically")
        form.addRow("", self.chk_reconnect)

        recon_row = QHBoxLayout()
        recon_row.addWidget(QLabel("Retry interval:"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 3600)
        self.spin_interval.setSuffix(" seconds")
        recon_row.addWidget(self.spin_interval)
        recon_row.addStretch()
        form.addRow("", recon_row)

        self.chk_no_ftm_push = QCheckBox("Disable FTM push (force manual OTP)")
        form.addRow("", self.chk_no_ftm_push)

        self.chk_connect_on_launch = QCheckBox(
            "Connect automatically when app starts"
        )
        form.addRow("", self.chk_connect_on_launch)

        return tab

    # ── Load/Save ───────────────────────────────────────────────

    def _load_values(self) -> None:
        p = self._profile
        self.edit_name.setText(p.name)

        # Load hosts: split comma-separated host field into individual inputs
        hosts = [h.strip() for h in p.host.split(",") if h.strip()]
        if not hosts:
            hosts = [""]
        for h in hosts:
            self._add_host_field(h)

        self.edit_port.setText(str(p.port))
        self.edit_username.setText(p.username)
        self.edit_realm.setText(p.realm)

        has_otp = p.auth_mode == "password_otp_seed"
        self.chk_otp.setChecked(has_otp)

        self.chk_remember.setChecked(p.password_ref is not None)

        self.chk_insecure.setChecked(p.insecure_ssl)
        self.edit_ca_file.setText(p.ca_file or "")
        self.chk_routes.setChecked(p.set_routes)
        self.chk_half.setChecked(p.half_internet_routes)
        self.chk_dns.setChecked(p.set_dns)
        self.chk_peerdns.setChecked(p.pppd_use_peerdns)
        self.edit_ifname.setText(p.ifname or "")
        self.chk_reconnect.setChecked(p.auto_reconnect)
        self.spin_interval.setValue(p.reconnect_interval_seconds)
        self.chk_no_ftm_push.setChecked(p.no_ftm_push)
        self.chk_connect_on_launch.setChecked(p.connect_on_launch)

        self._on_otp_toggled()

    def _on_otp_toggled(self) -> None:
        checked = self.chk_otp.isChecked()
        self.lbl_seed.setVisible(checked)
        self.edit_seed.setVisible(checked)
        self.lbl_seed_hint.setVisible(checked)
        self.chk_no_ftm_push.setEnabled(checked)
        if not checked:
            self.edit_seed.clear()

    def _on_save(self) -> None:
        errors = self._collect_errors()
        if errors:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Validation", "\n".join(errors))
            return
        self._write_values()
        self._store_secrets()
        self.accept()

    def _collect_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.edit_name.text().strip():
            errors.append("Name is required.")
        has_host = any(inp.text().strip() for inp in self.host_inputs)
        if not has_host:
            errors.append("At least one host is required.")
        return errors

    def _write_values(self) -> None:
        p = self._profile
        p.name = self.edit_name.text().strip()

        # Collect hosts into comma-separated string
        hosts = [inp.text().strip() for inp in self.host_inputs if inp.text().strip()]
        p.host = ", ".join(hosts)

        # Parse port from text input
        try:
            p.port = int(self.edit_port.text().strip())
        except ValueError:
            p.port = 443

        p.username = self.edit_username.text().strip()
        p.realm = self.edit_realm.text().strip()

        if self.chk_otp.isChecked():
            p.auth_mode = "password_otp_seed"
        else:
            p.auth_mode = "password"

        p.insecure_ssl = self.chk_insecure.isChecked()
        p.ca_file = self.edit_ca_file.text().strip() or None
        p.set_routes = self.chk_routes.isChecked()
        p.half_internet_routes = self.chk_half.isChecked()
        p.set_dns = self.chk_dns.isChecked()
        p.pppd_use_peerdns = self.chk_peerdns.isChecked()
        p.ifname = self.edit_ifname.text().strip() or None
        p.auto_reconnect = self.chk_reconnect.isChecked()
        p.reconnect_interval_seconds = self.spin_interval.value()
        p.no_ftm_push = self.chk_no_ftm_push.isChecked()
        p.connect_on_launch = self.chk_connect_on_launch.isChecked()

        if self.chk_remember.isChecked():
            p.password_ref = f"{p.id}:password"
        else:
            p.password_ref = None

        if p.auth_mode == "password_otp_seed" and self.edit_seed.text().strip():
            p.otp_seed_ref = f"{p.id}:otp_seed"
        elif p.auth_mode != "password_otp_seed":
            p.otp_seed_ref = None

        p.touch()

    def _store_secrets(self) -> None:
        if not self._secret_store:
            return
        p = self._profile

        pwd = self.edit_password.text()
        if pwd:
            self._secret_store.set_password(p.id, pwd)
            p.password_ref = f"{p.id}:password"
        elif not self.chk_remember.isChecked():
            self._secret_store.delete_password(p.id)
            p.password_ref = None

        if p.auth_mode == "password_otp_seed":
            seed = self.edit_seed.text().strip()
            if seed:
                self._secret_store.set_otp_seed(p.id, seed)
                p.otp_seed_ref = f"{p.id}:otp_seed"
        else:
            self._secret_store.delete_otp_seed(p.id)
            p.otp_seed_ref = None

    # ── Create Shortcut ─────────────────────────────────────────

    def _on_create_shortcut(self) -> None:
        """Save the profile and create a .lnk / .desktop shortcut."""
        # Save current values first
        errors = self._collect_errors()
        if errors:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Validation", "\n".join(errors))
            return
        self._write_values()
        self._store_secrets()

        safe_name = "".join(
            c for c in self._profile.name if c.isalnum() or c in "-_ "
        ).strip() or "VPN"
        default_name = f"{safe_name}.lnk"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Create Shortcut",
            default_name,
            "Shortcuts (*.lnk);;All Files (*)",
        )
        if not path:
            return

        # The shortcut launches the app with --connect <profile_id>
        if sys.platform == "win32":
            if getattr(sys, "frozen", False):
                target = sys.executable
                args = f"--connect {self._profile.id}"
            else:
                target = sys.executable
                args = f"-m openfortitray --connect {self._profile.id}"

            ps_script = (
                f'$ws = New-Object -ComObject WScript.Shell; '
                f'$lnk = $ws.CreateShortcut("{path}"); '
                f'$lnk.TargetPath = "{target}"; '
                f'$lnk.Arguments = "{args}"; '
                f'$lnk.Description = "Connect to {safe_name}"; '
                f'$lnk.Save()'
            )
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                    check=True,
                    capture_output=True,
                    timeout=10,
                    creationflags=0x08000000,  # CREATE_NO_WINDOW
                )
            except Exception as e:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(
                    self, "Error", f"Could not create shortcut:\n{e}"
                )
            else:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    self, "Shortcut Created", f"Shortcut saved to:\n{path}"
                )

    # ── Cert auto-fetch (called from app.py on connect) ─────────

    @staticmethod
    def auto_fetch_cert(profile: VpnProfile) -> bool:
        """Fetch the gateway cert and add it to trusted_cert_sha256 if not present.

        Returns True if a new cert was added.
        """
        if not profile.host:
            return False
        try:
            cert = fetch_certificate(profile.host, profile.port)
        except Exception as e:
            logger.warning("Auto cert fetch failed for %s: %s", profile.host, e)
            return False
        if cert.sha256_digest_raw not in profile.trusted_cert_sha256:
            profile.trusted_cert_sha256.append(cert.sha256_digest_raw)
            return True
        return False

    @property
    def profile(self) -> VpnProfile:
        return self._profile
