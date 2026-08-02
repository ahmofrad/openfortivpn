"""Connection manager: config file lifecycle + subprocess supervision.

SPEC.md §3 (architecture), §4.2 (config format), §8 (state machine).
AUTH.md §7 (ephemeral config), §8 (elevation).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from openfortitray.core.elevation import ElevatedProcess, launch_elevated, get_temp_dir
from openfortitray.core.helper import HelperClient
from openfortitray.core.profile import VpnProfile
from openfortitray.core.secret_store import SecretStore
from openfortitray.core.state_machine import StateMachine

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(
        self,
        binary_path: str,
        state_machine: StateMachine,
        secret_store: SecretStore | None = None,
        use_helper: bool = True,
    ) -> None:
        self.binary_path = binary_path
        self.state = state_machine
        self._secret_store = secret_store
        self._proc: ElevatedProcess | None = None
        self._config_path: Path | None = None
        self._seed_path: Path | None = None
        self._log_lines: list[str] = []
        self._on_output: Callable[[str], None] | None = None
        self._reader_thread: threading.Thread | None = None

        # Helper daemon (Windows only, preferred path)
        self._helper: HelperClient | None = None
        self._use_helper = use_helper and sys.platform == "win32"
        self._helper_vpn_running = False
        self._helper_lock = threading.Lock()
        self._helper_start_failed = False

    def try_start_helper(self) -> bool:
        """Try to start the privileged helper daemon (one UAC prompt).

        Returns True if the helper is running and usable.
        Thread-safe and idempotent.
        """
        if not self._use_helper:
            return False
        with self._helper_lock:
            if self._helper is not None and self._helper.is_connected:
                return True
            if self._helper_start_failed:
                return False

            self._helper = HelperClient()
            if self._helper.start_helper():
                self._helper.on_line = self._on_helper_line
                self._helper.on_exit = self._on_helper_exit
                logger.info("Privileged helper daemon connected")
                return True

            logger.warning(
                "Helper daemon unavailable, falling back to per-connect elevation"
            )
            self._helper = None
            self._helper_start_failed = True
            return False

    def shutdown_helper(self) -> None:
        """Shut down the helper daemon (called on app quit)."""
        if self._helper is not None:
            self._helper.shutdown()
            self._helper = None

    @property
    def is_running(self) -> bool:
        if self._helper is not None:
            return self._helper_vpn_running
        return self._proc is not None and self._proc.is_running

    @property
    def log_lines(self) -> list[str]:
        return list(self._log_lines)

    def set_output_callback(self, cb: Callable[[str], None]) -> None:
        self._on_output = cb

    # ── Helper callbacks ────────────────────────────────────────

    def _on_helper_line(self, line: str) -> None:
        """Called when the helper forwards a log line from openfortivpn."""
        self._log_lines.append(line)
        logger.debug("vpn: %s", line)
        if self._on_output:
            self._on_output(line)
        self.state.on_log_line(line)

    def _on_helper_exit(self, returncode: int) -> None:
        """Called when the helper reports the vpn process exited."""
        self._helper_vpn_running = False
        logger.info("openfortivpn exited with code %d", returncode)
        self.state.on_process_exit(returncode)
        self._cleanup_files()

    def connect(
        self,
        profile: VpnProfile,
        password: str | None = None,
        otp_seed: str | None = None,
        otp_code: str | None = None,
        host_override: tuple[str, int] | None = None,
    ) -> bool:
        """Launch openfortivpn for the given profile.

        Args:
            password: VPN password (from keyring or interactive prompt).
            otp_seed: Base32 TOTP seed (from keyring).
            otp_code: One-time OTP code (from interactive prompt, no seed).
            host_override: (host, port) to override the profile's host/port.

        Returns True if the process was started.
        """
        if self.is_running:
            logger.warning("connect() called while a process is already running")
            return False

        # Kill any stale openfortivpn.exe from a previous failed disconnect
        # (only needed without helper; helper owns its children)
        if sys.platform == "win32" and self._helper is None:
            subprocess.run(
                ["taskkill", "/IM", "openfortivpn.exe", "/T", "/F"],
                capture_output=True,
                timeout=5,
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )

        # Resolve secrets from keyring
        if password is None and self._secret_store and profile.password_ref:
            password = self._secret_store.get_password(profile.id)
        if otp_seed is None and self._secret_store and profile.otp_seed_ref:
            otp_seed = self._secret_store.get_otp_seed(profile.id)

        # Apply host override if provided (used for multi-host fallback)
        original_host = profile.host
        original_port = profile.port
        if host_override:
            profile.host = host_override[0]
            profile.port = host_override[1]
            logger.info("Connecting to host override: %s:%d", host_override[0], host_override[1])

        # Write ephemeral config files
        config_path, seed_path = self._write_config(
            profile, password, otp_seed, otp_code
        )

        # Restore original values
        profile.host = original_host
        profile.port = original_port
        self._config_path = config_path
        self._seed_path = seed_path

        self._log_lines.clear()
        self.state.on_connect_requested()

        # Use the helper daemon if available (no per-connect UAC, clean kill)
        if self._helper is not None and self._helper.is_connected:
            ok = self._helper.start_vpn(
                self.binary_path, str(config_path), verbose=True
            )
            if ok:
                self._helper_vpn_running = True
                return True
            logger.warning("Helper start_vpn failed, falling back to direct launch")
            self._helper_vpn_running = False

        try:
            self._proc = launch_elevated(
                self.binary_path, str(config_path), verbose=True
            )
        except FileNotFoundError as e:
            logger.error("openfortivpn binary not found: %s (%s)", self.binary_path, e)
            self._log_lines.append(f"ERROR: openfortivpn binary not found: {self.binary_path}")
            self.state.on_process_exit(-1)
            self._cleanup_files()
            return False
        except OSError as e:
            logger.error("Elevation failed: %s", e)
            self._log_lines.append(f"ERROR: {e}")
            self.state.on_process_exit(-1)
            self._cleanup_files()
            return False

        # Start reading output in a thread
        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()
        return True

    def disconnect(self) -> None:
        """Gracefully stop the subprocess."""
        if not self.is_running:
            return

        self.state.on_disconnect_requested()

        # Helper path: send STOP command (helper has full kill rights)
        if self._helper is not None and self._helper.is_connected:
            self._helper.stop_vpn()
            self._helper_vpn_running = False
            self._cleanup_files()
            return

        if self._proc:
            try:
                self._proc.terminate(timeout=10)
            except Exception as e:
                logger.warning("Error during subprocess termination: %s", e)

            # Verify the process is actually dead
            if self._proc.is_running:
                logger.error("Process still alive after terminate() -- force killing")
                try:
                    self._proc.terminate(timeout=5)
                except Exception:
                    pass

        self._proc = None
        self._cleanup_files()

    def _write_config(
        self,
        profile: VpnProfile,
        password: str | None,
        otp_seed: str | None,
        otp_code: str | None = None,
    ) -> tuple[Path, Path | None]:
        """Write the ephemeral per-connection config file (AUTH.md §7)."""
        tmpdir = get_temp_dir()
        tmpdir.mkdir(parents=True, exist_ok=True)

        # Write OTP seed to its own file (AUTH.md §7)
        seed_path: Path | None = None
        if otp_seed:
            seed_path = tmpdir / f"{profile.id}.seed"
            self._write_secure(seed_path, otp_seed)

        # Build config
        lines: list[str] = []
        lines.append(f"host = {profile.host}")
        lines.append(f"port = {profile.port}")
        lines.append(f"username = {profile.username}")
        if password:
            lines.append(f"password = {password}")
        if profile.realm:
            lines.append(f"realm = {profile.realm}")
        if seed_path:
            lines.append(f"otp-seed-file = {seed_path}")
        if otp_code:
            lines.append(f"otp = {otp_code}")
        if profile.no_ftm_push:
            lines.append("no-ftm-push = 1")
        for digest in profile.trusted_cert_sha256:
            lines.append(f"trusted-cert = {digest}")
        if profile.insecure_ssl:
            lines.append("insecure-ssl = 1")
        if profile.ca_file:
            lines.append(f"ca-file = {profile.ca_file}")
        lines.append(f"set-routes = {'1' if profile.set_routes else '0'}")
        lines.append(
            f"half-internet-routes = {'1' if profile.half_internet_routes else '0'}"
        )
        lines.append(f"set-dns = {'1' if profile.set_dns else '0'}")
        if sys.platform != "win32":
            lines.append(f"use-resolvconf = {'1' if profile.use_resolvconf else '0'}")
            lines.append(
                f"pppd-use-peerdns = {'1' if profile.pppd_use_peerdns else '0'}"
            )
        if profile.ifname:
            lines.append(f"ifname = {profile.ifname}")
        if profile.auto_reconnect:
            lines.append(f"persistent = {profile.reconnect_interval_seconds}")
        else:
            lines.append("persistent = 0")

        config_path = tmpdir / f"{profile.id}.conf"
        self._write_secure(config_path, "\n".join(lines) + "\n")
        return config_path, seed_path

    @staticmethod
    def _write_secure(path: Path, content: str) -> None:
        """Write a file with 0600 permissions (AUTH.md §7)."""
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content.encode("utf-8"))
        finally:
            os.close(fd)

    def _read_output(self) -> None:
        """Read subprocess output and feed the state machine."""
        assert self._proc is not None

        try:
            while self._proc.is_running:
                line = self._proc.read_line()
                if line:
                    self._log_lines.append(line)
                    logger.debug("vpn: %s", line)
                    if self._on_output:
                        self._on_output(line)
                    self.state.on_log_line(line)
                # If line is None, it's a timeout -- loop and keep waiting.

            # Process exited -- drain any remaining output
            while True:
                line = self._proc.read_line()
                if not line:
                    break
                self._log_lines.append(line)
                logger.debug("vpn: %s", line)
                if self._on_output:
                    self._on_output(line)
                self.state.on_log_line(line)

            # Read exit code
            try:
                rc = self._proc.wait(timeout=5)
            except Exception:
                rc = -1
            logger.info("openfortivpn exited with code %d", rc)
            self.state.on_process_exit(rc)
        except Exception as e:
            logger.exception("Error in reader thread: %s", e)
            self.state.on_process_exit(-1)
        self._cleanup_files()
        self._proc = None

    def _cleanup_files(self) -> None:
        """Delete ephemeral config and seed files (AUTH.md §7)."""
        for p in (self._config_path, self._seed_path):
            if p and p.exists():
                try:
                    p.unlink()
                except OSError:
                    logger.warning("Could not delete temp file: %s", p)
        self._config_path = None
        self._seed_path = None
