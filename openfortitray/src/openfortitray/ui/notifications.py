"""Desktop notifications on connection state change (SPEC.md §7).

Uses QSystemTrayIcon.showMessage for native notifications -- no extra
dependency needed since the tray icon already exists.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QSystemTrayIcon

from openfortitray.core.profile import VpnProfile
from openfortitray.core.state_machine import ConnectionState

logger = logging.getLogger(__name__)

NOTIFICATIONS = {
    ConnectionState.CONNECTED: (
        "VPN Connected",
        "Tunnel is up and running.",
        QSystemTrayIcon.Information,
    ),
    ConnectionState.DISCONNECTED: (
        "VPN Disconnected",
        "Connection closed.",
        QSystemTrayIcon.Information,
    ),
    ConnectionState.AUTH_ERROR: (
        "VPN Authentication Error",
        "Check your username, password, or OTP.",
        QSystemTrayIcon.Critical,
    ),
    ConnectionState.PERMISSION_ERROR: (
        "VPN Permission Denied",
        "Administrator/root privileges are required.",
        QSystemTrayIcon.Critical,
    ),
    ConnectionState.ERROR: (
        "VPN Connection Error",
        "The connection was lost or failed.",
        QSystemTrayIcon.Warning,
    ),
    ConnectionState.RECONNECTING: (
        "VPN Reconnecting",
        "Attempting to reconnect...",
        QSystemTrayIcon.Warning,
    ),
}


class NotificationManager:
    def __init__(
        self,
        tray: QSystemTrayIcon,
        timeout_ms: int = 5000,
    ) -> None:
        self._tray = tray
        self._timeout = timeout_ms
        self._enabled = True
        self._profile: VpnProfile | None = None

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_active_profile(self, profile: VpnProfile | None) -> None:
        self._profile = profile

    def on_state_change(self, state: ConnectionState) -> None:
        if not self._enabled:
            return
        if state not in NOTIFICATIONS:
            return

        title, message, icon = NOTIFICATIONS[state]

        if self._profile:
            title = f"{self._profile.name}: {title.replace('VPN ', '')}"

        if self._tray.supportsMessages():
            self._tray.showMessage(title, message, icon, self._timeout)
        else:
            logger.info("Notification (no tray support): %s -- %s", title, message)
