"""Connection session state: credentials, multi-host fallback, OTP relaunch.

Owns all per-connection session state so app.py stays thin UI wiring.
"""

from __future__ import annotations

import logging

from openfortitray.core.connection_manager import ConnectionManager
from openfortitray.core.profile import VpnProfile
from openfortitray.core.secret_store import SecretStore
from openfortitray.core.state_machine import ConnectionState

logger = logging.getLogger(__name__)


class ConnectionSession:
    """Manages one connection lifecycle including multi-host fallback.

    Tracks the host list, current host index, cached credentials, and
    handles OTP relaunch and host fallback logic.
    """

    def __init__(
        self,
        conn: ConnectionManager,
        secret_store: SecretStore | None,
    ) -> None:
        self.conn = conn
        self.secrets = secret_store

        self.profile: VpnProfile | None = None
        self.host_list: list[tuple[str, int]] = []
        self.host_index: int = 0
        self.current_host: tuple[str, int] | None = None

        self.password: str | None = None
        self.otp_seed: str | None = None

        # Callback for interactive prompts (password, OTP)
        self.on_password_needed = None  # callable(profile) -> str | None
        self.on_otp_needed = None       # callable() -> str | None

    def resolve_credentials(self) -> bool:
        """Resolve password and OTP seed for the active profile.

        Returns False if the user cancelled an interactive prompt.
        """
        assert self.profile is not None
        p = self.profile

        # Password: keyring -> session cache -> interactive prompt
        if self.password is None:
            if self.secrets and p.password_ref:
                self.password = self.secrets.get_password(p.id)
        if self.password is None and self.on_password_needed:
            self.password = self.on_password_needed(p)
            if self.password is None:
                return False

        # OTP seed: keyring only (interactive OTP is handled reactively)
        if self.otp_seed is None:
            if self.secrets and p.otp_seed_ref:
                self.otp_seed = self.secrets.get_otp_seed(p.id)

        return True

    def start(self, profile: VpnProfile) -> bool:
        """Start a new connection for the given profile.

        Resolves credentials, sets up host list, and connects to the
        first host. Returns False if cancelled.
        """
        if self.conn.is_running:
            self.conn.disconnect()

        self.profile = profile
        self.password = None
        self.otp_seed = None

        if not self.resolve_credentials():
            return False

        # Set up host list
        self.host_list = profile.get_host_list()
        self.host_index = 0
        self.current_host = self.host_list[0] if self.host_list else None

        return self.conn.connect(
            profile,
            password=self.password,
            otp_seed=self.otp_seed,
            host_override=self.current_host,
        )

    def try_next_host(self) -> bool:
        """Try the next host in the list. Returns True if a next host was attempted."""
        self.host_index += 1
        if self.host_index >= len(self.host_list):
            return False

        self.current_host = self.host_list[self.host_index]
        logger.info(
            "Trying next host: %s:%d",
            self.current_host[0], self.current_host[1],
        )
        assert self.profile is not None
        return self.conn.connect(
            self.profile,
            password=self.password,
            otp_seed=self.otp_seed,
            host_override=self.current_host,
        )

    def relaunch_with_otp(self, otp_code: str) -> bool:
        """Relaunch the connection with an explicit OTP code (Windows).

        Kills the current process and reconnects with otp = <code> in
        the config. Keeps the same host and credentials.
        """
        assert self.profile is not None
        self.conn.disconnect()
        return self.conn.connect(
            self.profile,
            password=self.password,
            otp_seed=self.otp_seed,
            otp_code=otp_code,
            host_override=self.current_host,
        )

    def stop(self) -> None:
        """Disconnect and clear session state."""
        self.conn.disconnect()
        self.profile = None
        self.host_list = []
        self.current_host = None
        # Keep credentials for re-connect convenience

    def on_state_change(self, state: ConnectionState) -> bool:
        """Handle state transitions. Returns True if a fallback was attempted.

        Called by the UI; on ERROR, tries the next host automatically.
        """
        if state == ConnectionState.ERROR:
            return self.try_next_host()
        return False
