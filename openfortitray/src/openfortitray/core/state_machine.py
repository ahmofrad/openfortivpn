"""Connection state machine (SPEC.md §8).

Drives the tray icon and main-window status from parsed log lines
emitted by the openfortivpn subprocess (SPEC.md §4.3).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    AUTH_ERROR = auto()
    PERMISSION_ERROR = auto()
    ERROR = auto()


# Log-line substrings that trigger state transitions (SPEC.md §4.3).
# Matched case-sensitively as substrings of combined stdout+stderr.
TRIGGERS = {
    # Connected triggers -- different on Unix vs Windows
    "Tunnel is up and running.": "connected",
    "Tunnel interface is UP.": "connected",
    "Negotiation complete.": "connected",
    # Disconnected
    "Closed connection to gateway.": "disconnected",
    # Auth errors
    "Authentication failed": "auth_error",
    "No OTP specified": "auth_error",
    "Failed to generate TOTP from otp-seed.": "auth_error",
    # Permission errors
    "This process requires administrator privileges.": "permission_error",
    "This process was not spawned with root privileges, which are required.": "permission_error",
    # Connecting progress
    "Connected to gateway.": "connecting",
    "Authenticated.": "connecting",
    "Remote gateway has allocated a VPN.": "connecting",
    "Establishing TLS connection": "connecting",
    "DELAYING OTP": "connecting",
}

# Terminal states -- auth errors mean retrying is pointless.
TERMINAL_TRIGGERS = {"auth_error", "permission_error"}


class StateMachine:
    def __init__(self) -> None:
        self.state: ConnectionState = ConnectionState.DISCONNECTED
        self._listeners: list[Callable[[ConnectionState], None]] = []

    def add_listener(self, cb: Callable[[ConnectionState], None]) -> None:
        self._listeners.append(cb)

    def _set_state(self, new_state: ConnectionState) -> None:
        if new_state == self.state:
            return
        self.state = new_state
        for cb in self._listeners:
            cb(new_state)

    def on_connect_requested(self) -> None:
        self._set_state(ConnectionState.CONNECTING)

    def on_disconnect_requested(self) -> None:
        self._set_state(ConnectionState.DISCONNECTED)

    def on_log_line(self, line: str) -> None:
        """Parse a subprocess output line and transition state."""
        for trigger, action in TRIGGERS.items():
            if trigger in line:
                self._apply_trigger(action)
                return

    def _apply_trigger(self, action: str) -> None:
        match action:
            case "connected":
                self._set_state(ConnectionState.CONNECTED)
            case "disconnected":
                self._set_state(ConnectionState.DISCONNECTED)
            case "connecting":
                if self.state == ConnectionState.CONNECTING:
                    pass  # stay connecting
            case "auth_error":
                self._set_state(ConnectionState.AUTH_ERROR)
            case "permission_error":
                self._set_state(ConnectionState.PERMISSION_ERROR)

    def on_process_exit(self, returncode: int) -> None:
        """Called when the subprocess terminates."""
        if self.state in (ConnectionState.CONNECTED, ConnectionState.RECONNECTING):
            # Unexpected exit while connected/reconnecting
            self._set_state(ConnectionState.ERROR)
        elif self.state == ConnectionState.CONNECTING:
            self._set_state(ConnectionState.ERROR)
        elif self.state not in (
            ConnectionState.DISCONNECTED,
            ConnectionState.AUTH_ERROR,
            ConnectionState.PERMISSION_ERROR,
        ):
            self._set_state(ConnectionState.DISCONNECTED)

    @property
    def is_connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED

    @property
    def is_connecting(self) -> bool:
        return self.state in (ConnectionState.CONNECTING, ConnectionState.RECONNECTING)

    @property
    def is_error(self) -> bool:
        return self.state in (
            ConnectionState.AUTH_ERROR,
            ConnectionState.PERMISSION_ERROR,
            ConnectionState.ERROR,
        )

    @property
    def should_retry(self) -> bool:
        """Whether a process exit in this state warrants a GUI backstop retry.

        Auth/permission errors are terminal (SPEC.md §6.2) -- a wrong
        password won't fix itself. Other errors are network-level and
        safe to retry.
        """
        return self.state == ConnectionState.ERROR
