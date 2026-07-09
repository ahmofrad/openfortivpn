"""QApplication bootstrap -- Phase 5: full CRUD + cert trust + elevation + tray."""

from __future__ import annotations

import json
import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from openfortitray.core.autostart import disable_autostart, enable_autostart
from openfortitray.core.connection_manager import ConnectionManager
from openfortitray.core.profile import VpnProfile
from openfortitray.core.profile_store import ProfileStore
from openfortitray.core.secret_store import NoKeyringBackendError, SecretStore
from openfortitray.core.single_instance import (
    acquire_single_instance,
    signal_existing_instance,
)
from openfortitray.core.sleep_wake import SleepWakeMonitor
from openfortitray.core.state_machine import ConnectionState, StateMachine
from openfortitray.core.vpn_binary import find_binary
from openfortitray.ui.main_window import MainWindow
from openfortitray.ui.notifications import NotificationManager
from openfortitray.ui.profile_editor import ProfileEditor
from openfortitray.ui.settings_dialog import SettingsDialog
from openfortitray.ui.signal_bridge import get_bridge
from openfortitray.ui.tray import TrayController

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class App:
    def __init__(self) -> None:
        self.store = ProfileStore()
        self.store.load()
        self.state_machine = StateMachine()

        # Secure secret storage (AUTH.md §2)
        try:
            self.secrets = SecretStore()
            if self.secrets.is_fallback:
                logger.warning(
                    "Keyring is using an encrypted-file fallback. "
                    "Consider installing gnome-keyring/kwallet."
                )
        except NoKeyringBackendError:
            logger.error(
                "No keyring backend available. Passwords/seeds cannot be stored."
            )
            self.secrets = None

        binary = find_binary(self.store.settings.vpn_binary_path)
        if not binary:
            logger.error("openfortivpn binary not found")
            binary = "openfortivpn"

        self.conn = ConnectionManager(
            binary_path=binary,
            state_machine=self.state_machine,
            secret_store=self.secrets,
        )

        self.window = MainWindow()

        # Tray (must be created before _refresh_profiles references it)
        self.tray = TrayController()

        # Session-level credential cache for interactive prompts
        self._session_password: str | None = None

        self._refresh_profiles()

        # Wire main window signals
        self.window.connect_requested.connect(self._on_connect)
        self.window.disconnect_requested.connect(self._on_disconnect)
        self.window.settings_requested.connect(self._on_settings)
        self.window.quit_requested.connect(self._on_quit)
        self.window.add_profile.connect(self._on_add_profile)
        self.window.edit_profile.connect(self._on_edit_profile)
        self.window.delete_profile.connect(self._on_delete_profile)
        self.window.export_profile.connect(self._on_export_profile)
        self.window.import_profile.connect(self._on_import_profile)

        # Wire tray signals
        self.tray.connect_profile.connect(self._on_tray_connect)
        self.tray.disconnect.connect(self._on_disconnect)
        self.tray.show_window.connect(self._show_window)
        self.tray.quit_app.connect(self._on_quit)

        # State machine -> UI (via signal bridge for thread safety)
        self.bridge = get_bridge()
        self.state_machine.add_listener(self._on_state_change_threadsafe)
        self.conn.set_output_callback(self._on_vpn_output_threadsafe)

        # Connect bridge signals to UI slots (these run on the main thread)
        self.bridge.state_changed.connect(self._on_state_change_ui)
        self.bridge.state_changed.connect(self._on_notification_ui)
        self.bridge.vpn_output.connect(self._on_vpn_output_ui)

        # Notifications (routed through bridge for thread safety)
        self.notifications = NotificationManager(self.tray.tray)

        # Sleep/wake reconnect
        self.sleep_wake = SleepWakeMonitor(
            was_connected=lambda: self.state_machine.is_connected,
        )
        self.sleep_wake.wake_detected.connect(self._on_wake)
        self.sleep_wake.start()

    def _refresh_profiles(self, selected_id: str | None = None) -> None:
        self.window.set_profiles(self.store.profiles, selected_id=selected_id)
        self.window.set_minimize_to_tray(self.store.settings.minimize_to_tray)
        self.tray.set_profiles(self.store.profiles)

    def _find_profile(self, profile_id: str) -> VpnProfile | None:
        for p in self.store.profiles:
            if p.id == profile_id:
                return p
        return None

    # ── Connection ──────────────────────────────────────────────

    def _on_connect(self, profile: VpnProfile) -> None:
        self._connect_profile(profile)

    def _on_tray_connect(self, profile_id: str) -> None:
        profile = self._find_profile(profile_id)
        if profile:
            self._connect_profile(profile)

    def _connect_profile(self, profile: VpnProfile) -> None:
        if self.conn.is_running:
            self.conn.disconnect()

        # Auto-fetch cert hash if not already trusted (no user prompt)
        from openfortitray.ui.profile_editor import ProfileEditor

        if not profile.trusted_cert_sha256:
            ProfileEditor.auto_fetch_cert(profile)
            self.store.save()

        password = None
        otp_seed = None
        if self.secrets:
            if profile.auth_mode in (
                "password", "password_otp_manual", "password_otp_seed"
            ):
                password = self.secrets.get_password(profile.id)
            if profile.auth_mode == "password_otp_seed":
                otp_seed = self.secrets.get_otp_seed(profile.id)

        # If no password saved, prompt interactively before connecting
        if not password:
            if self._session_password:
                password = self._session_password
            else:
                from openfortitray.ui.credential_dialogs import PasswordPromptDialog

                dlg = PasswordPromptDialog(
                    username=profile.username,
                    host=profile.name,
                    parent=self.window,
                )
                if dlg.exec():
                    password = dlg.password
                    if dlg.username:
                        profile.username = dlg.username
                    self._session_password = password
                else:
                    return  # user cancelled

        # Cache for relaunch (OTP prompt triggers a relaunch on Windows)
        self._session_password = password
        self._session_otp_seed = otp_seed

        # Get host list for fallback
        self._host_list = profile.get_host_list()
        self._host_index = 0
        self._connect_creds = {"password": password, "otp_seed": otp_seed}
        self._current_host_override = (
            self._host_list[0] if self._host_list else None
        )

        self.tray.set_active_profile(profile)
        self.notifications.set_active_profile(profile)

        # Start with first host
        self.conn.connect(
            profile,
            password=password,
            otp_seed=otp_seed,
            host_override=self._current_host_override,
        )

    def _on_disconnect(self) -> None:
        self.conn.disconnect()
        self.tray.set_active_profile(None)

    def _on_state_change_threadsafe(self, state: ConnectionState) -> None:
        """Called from the reader thread -- emit signal to main thread."""
        self.bridge.state_changed.emit(state.value)

    def _on_state_change_ui(self, state_value: int) -> None:
        """Runs on main thread via Qt signal."""
        state = ConnectionState(state_value)
        self.window.update_state(state)
        self.tray.update_state(state)

        # Multi-host fallback: on connection error, try next host
        if state == ConnectionState.ERROR:
            self._try_next_host()

    def _try_next_host(self) -> None:
        """If there are more hosts to try, connect to the next one."""
        self._host_index += 1
        if hasattr(self, "_host_list") and self._host_index < len(self._host_list):
            host_port = self._host_list[self._host_index]
            self._current_host_override = host_port
            profile = self.tray._active_profile
            if profile:
                logger.info("Trying next host: %s:%d", host_port[0], host_port[1])
                self.window.append_log_line(
                    f"--- Trying next host: {host_port[0]}:{host_port[1]} ---"
                )
                self.conn.connect(
                    profile,
                    password=self._connect_creds.get("password"),
                    otp_seed=self._connect_creds.get("otp_seed"),
                    host_override=host_port,
                )

    def _on_notification_ui(self, state_value: int) -> None:
        """Runs on main thread via Qt signal."""
        state = ConnectionState(state_value)
        self.notifications.on_state_change(state)

    def _show_window(self) -> None:
        self.window.show()
        self.window.force_foreground()

    def _on_vpn_output_threadsafe(self, line: str) -> None:
        """Called from the reader thread -- emit signal to main thread."""
        self.bridge.vpn_output.emit(line)

    def _on_vpn_output_ui(self, line: str) -> None:
        """Runs on main thread via Qt signal."""
        logger.debug("vpn output: %s", line)
        # Filter based on log level setting
        level = self.store.settings.log_level
        upper = line.upper()
        if level == "error" and not upper.startswith("ERROR:"):
            return
        if level == "warn" and not (upper.startswith("ERROR:") or upper.startswith("WARN:")):
            return
        if level == "info" and upper.startswith("DEBUG:"):
            return
        self.window.append_log_line(line)

        # React to OTP prompt from the gateway
        if "Please enter one-time password:" in line or "enter one-time password" in line.lower():
            self._handle_otp_prompt()

    def _handle_otp_prompt(self) -> None:
        """Show OTP dialog and feed the code back to the VPN process."""
        from openfortitray.ui.credential_dialogs import OtpPromptDialog

        dlg = OtpPromptDialog(parent=self.window)
        if not dlg.exec():
            self.conn.disconnect()
            return

        otp_code = dlg.otp
        if not otp_code:
            self.conn.disconnect()
            return

        # Try writing to stdin first (Linux)
        if self.conn._proc and self.conn._proc.write_input(otp_code):
            return

        # Windows: can't write stdin to elevated process.
        # Kill, add otp to config, and relaunch.
        profile = self.tray._active_profile
        if not profile:
            return

        # Reuse credentials from the session
        password = self._session_password
        otp_seed = getattr(self, "_session_otp_seed", None)
        if self.secrets:
            if not password:
                password = self.secrets.get_password(profile.id)
            if not otp_seed:
                otp_seed = self.secrets.get_otp_seed(profile.id)

        self.conn.disconnect()
        self.conn.connect(
            profile,
            password=password,
            otp_seed=otp_seed,
            otp_code=otp_code,
            host_override=getattr(self, "_current_host_override", None),
        )

    def _on_wake(self) -> None:
        """Called when system wakes from sleep -- reconnect if needed."""
        if not self.state_machine.is_connected and self.tray._active_profile:
            logger.info("Reconnecting after wake...")
            profile = self.tray._active_profile
            self._connect_profile(profile)

    # ── Profile CRUD ────────────────────────────────────────────

    def _on_add_profile(self) -> None:
        dlg = ProfileEditor(
            profile=None,
            secret_store=self.secrets,
            parent=self.window,
        )
        if dlg.exec():
            # Prevent duplicate names
            existing_names = {p.name.lower() for p in self.store.profiles}
            if dlg.profile.name.lower() in existing_names:
                QMessageBox.warning(
                    self.window, "Duplicate",
                    f"A profile named '{dlg.profile.name}' already exists.",
                )
                return
            self.store.add_profile(dlg.profile)
            self._refresh_profiles(selected_id=dlg.profile.id)

    def _on_edit_profile(self, profile: VpnProfile) -> None:
        dlg = ProfileEditor(
            profile=profile,
            secret_store=self.secrets,
            parent=self.window,
        )
        if dlg.exec():
            # Prevent duplicate names (excluding self)
            existing_names = {
                p.name.lower() for p in self.store.profiles if p.id != profile.id
            }
            if dlg.profile.name.lower() in existing_names:
                QMessageBox.warning(
                    self.window, "Duplicate",
                    f"A profile named '{dlg.profile.name}' already exists.",
                )
                return
            self.store.update_profile(dlg.profile)
            self._refresh_profiles(selected_id=dlg.profile.id)

    def _on_delete_profile(self, profile: VpnProfile) -> None:
        reply = QMessageBox.question(
            self.window,
            "Delete Profile",
            f"Delete \"{profile.name}\"?\n"
            "This will also remove stored credentials.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if self.secrets:
                self.secrets.delete_all_for_profile(profile.id)
            self.store.delete_profile(profile.id)
            self._refresh_profiles()

    # ── Export / Import ─────────────────────────────────────────

    def _on_export_profile(self, profile: VpnProfile) -> None:
        from PySide6.QtWidgets import QFileDialog

        safe_name = "".join(
            c for c in profile.name if c.isalnum() or c in "-_ "
        ).strip() or "VPN"
        path, _ = QFileDialog.getSaveFileName(
            self.window,
            "Export Profile",
            f"{safe_name}.json",
            "JSON (*.json);;All Files (*)",
        )
        if not path:
            return

        # Export profile + secrets together
        data: dict = {}
        for f in profile.__dataclass_fields__:
            val = getattr(profile, f)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            data[f] = val

        if self.secrets:
            pwd = self.secrets.get_password(profile.id)
            seed = self.secrets.get_otp_seed(profile.id)
            data["_export_password"] = pwd or ""
            data["_export_otp_seed"] = seed or ""

        try:
            from pathlib import Path

            Path(path).write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
            QMessageBox.information(
                self.window, "Export", f"Profile exported to:\n{path}"
            )
        except OSError as e:
            QMessageBox.critical(self.window, "Error", f"Export failed:\n{e}")

    def _on_import_profile(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        from datetime import datetime

        path, _ = QFileDialog.getOpenFileName(
            self.window,
            "Import Profile",
            "",
            "JSON (*.json);;All Files (*)",
        )
        if not path:
            return

        try:
            from pathlib import Path

            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            QMessageBox.critical(self.window, "Error", f"Import failed:\n{e}")
            return

        # Create a new profile with imported data
        profile = VpnProfile()
        for f in VpnProfile.__dataclass_fields__:
            if f in data and f not in ("_export_password", "_export_otp_seed"):
                val = data[f]
                if f in ("created_at", "updated_at") and isinstance(val, str):
                    val = datetime.fromisoformat(val)
                setattr(profile, f, val)

        # Give it a new ID so it doesn't clash
        import uuid

        profile.id = str(uuid.uuid4())

        # Check for duplicate names -- error, don't auto-append
        existing_names = {p.name.lower() for p in self.store.profiles}
        if profile.name.lower() in existing_names:
            QMessageBox.critical(
                self.window,
                "Duplicate Name",
                f"A profile named '{profile.name}' already exists.\n"
                "Please rename it first or delete the existing one.",
            )
            return

        profile.touch()

        # Store secrets
        if self.secrets:
            pwd = data.get("_export_password", "")
            seed = data.get("_export_otp_seed", "")
            if pwd:
                self.secrets.set_password(profile.id, pwd)
                profile.password_ref = f"{profile.id}:password"
            if seed:
                self.secrets.set_otp_seed(profile.id, seed)
                profile.otp_seed_ref = f"{profile.id}:otp_seed"

        self.store.add_profile(profile)
        self._refresh_profiles(selected_id=profile.id)
        QMessageBox.information(
            self.window, "Import", f"Profile '{profile.name}' imported."
        )

    # ── Settings & autostart ────────────────────────────────────

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self.store.settings, parent=self.window)
        if dlg.exec():
            self.store.save()
            self.window.set_minimize_to_tray(self.store.settings.minimize_to_tray)
            self._sync_autostart()

    def _sync_autostart(self) -> None:
        if self.store.settings.launch_at_startup:
            enable_autostart()
        else:
            disable_autostart()

    # ── Quit ────────────────────────────────────────────────────

    def _on_quit(self) -> None:
        if self.conn.is_running:
            self.conn.disconnect()
        self.store.save()
        self.window.force_quit()
        QApplication.quit()


def main() -> int:
    # Parse --connect <profile_id> argument (from shortcuts)
    connect_profile_id: str | None = None
    args = sys.argv[1:]
    if "--connect" in args:
        idx = args.index("--connect")
        if idx + 1 < len(args):
            connect_profile_id = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    # If another instance is running, signal it to connect (don't show window)
    if not acquire_single_instance():
        signal_existing_instance()
        # For shortcuts: the existing instance will handle the connect
        # via the show-window signal. We can't pass the profile ID to it
        # through the mutex, so we write it to a file.
        if connect_profile_id:
            import tempfile
            from pathlib import Path

            connect_file = Path(tempfile.gettempdir()) / "openfortitray_connect.signal"
            connect_file.write_text(connect_profile_id)
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("OpenFortiTray")
    app.setQuitOnLastWindowClosed(False)

    # Set application icon
    from pathlib import Path
    from PySide6.QtGui import QIcon
    icon_candidates = []
    if hasattr(sys, "_MEIPASS"):
        icon_candidates.append(Path(sys._MEIPASS) / "app_icon.png")
    icon_candidates.append(Path(sys.executable).parent / "app_icon.png")
    icon_candidates.append(Path(sys.executable).parent / "_internal" / "app_icon.png")
    for ic in icon_candidates:
        if ic.exists():
            app.setWindowIcon(QIcon(str(ic)))
            break

    gui = App()

    # Create a show-window event on Windows so second instances can signal us
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.CreateEventExW(
                None,
                "Global\\OpenFortiTray_ShowWindow",
                0x7F000000,  # CREATE_EVENT_MANUAL_RESET | GMLE_READ | GMLE_WRITE
                0x1F0003,
            )
        except Exception:
            pass

    # Poll for show-window signal (every 500ms)
    import tempfile
    from pathlib import Path

    show_signal_path = Path(tempfile.gettempdir()) / "openfortitray_show.signal"
    connect_signal_path = Path(tempfile.gettempdir()) / "openfortitray_connect.signal"

    from PySide6.QtCore import QTimer

    def check_signals():
        # Check for connect signal (from shortcuts)
        if connect_signal_path.exists():
            try:
                pid = connect_signal_path.read_text().strip()
                connect_signal_path.unlink(missing_ok=True)
                profile = gui._find_profile(pid)
                if profile:
                    # Just connect, don't show window
                    gui._connect_profile(profile)
            except Exception:
                connect_signal_path.unlink(missing_ok=True)

        # Check for show-window signal
        if sys.platform == "win32":
            try:
                import ctypes

                handle = ctypes.windll.kernel32.OpenEventW(
                    0x100000, False, "Global\\OpenFortiTray_ShowWindow"
                )
                if handle:
                    result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
                    if result == 0:
                        ctypes.windll.kernel32.ResetEvent(handle)
                        gui.window.show()
                        gui.window.force_foreground()
                    ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                pass
        else:
            if show_signal_path.exists():
                show_signal_path.unlink(missing_ok=True)
                gui.window.show()
                gui.window.force_foreground()

    show_timer = QTimer()
    show_timer.timeout.connect(check_signals)
    show_timer.start(500)

    # On first run (no settings file), always show the window.
    settings_file = gui.store.settings_file
    is_first_run = not settings_file.exists() or not settings_file.stat().st_size

    tray_ok = False
    if TrayController.is_available():
        gui.tray.show()
        tray_ok = True

    # If launched via shortcut with --connect <id>, auto-connect without showing window
    if connect_profile_id:
        profile = gui._find_profile(connect_profile_id)
        if profile:
            gui.window.set_profiles(gui.store.profiles, selected_id=connect_profile_id)
            from PySide6.QtCore import QTimer as QTimer2

            QTimer2.singleShot(1000, lambda: gui._connect_profile(profile))
        else:
            gui.window.show()
            gui.window.force_foreground()
            QMessageBox.warning(
                gui.window,
                "Profile Not Found",
                f"No profile with ID '{connect_profile_id}' was found.",
            )
    elif is_first_run or not gui.store.settings.start_minimized or not tray_ok:
        gui.window.show()
        gui.window.force_foreground()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
