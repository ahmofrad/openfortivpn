"""Connection manager: config file lifecycle + subprocess supervision.

SPEC.md §3 (architecture), §4.2 (config format), §8 (state machine).
AUTH.md §7 (ephemeral config), §8 (elevation).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Callable

from openfortitray.core.elevation import ElevatedProcess, launch_elevated, get_temp_dir
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

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.is_running

    @property
    def log_lines(self) -> list[str]:
        return list(self._log_lines)

    def set_output_callback(self, cb: Callable[[str], None]) -> None:
        self._on_output = cb

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

        if self._proc:
            try:
                self._proc.terminate(timeout=10)
            except Exception:
                logger.warning("Error during subprocess termination")

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
