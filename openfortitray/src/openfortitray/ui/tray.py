"""Tray icon with state-based colors (DESIGN.md §2, WIREFRAMES.md tray section)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from openfortitray.core.profile import VpnProfile
from openfortitray.core.state_machine import ConnectionState

# DESIGN.md §2 state color-coding
STATE_COLORS = {
    ConnectionState.DISCONNECTED: QColor("#808080"),    # neutral gray
    ConnectionState.CONNECTING: QColor("#FFA500"),      # amber
    ConnectionState.CONNECTED: QColor("#00AA00"),       # green
    ConnectionState.RECONNECTING: QColor("#FFA500"),    # amber
    ConnectionState.AUTH_ERROR: QColor("#CC0000"),      # red
    ConnectionState.PERMISSION_ERROR: QColor("#CC0000"),  # red
    ConnectionState.ERROR: QColor("#CC0000"),            # red
}

STATE_LABELS = {
    ConnectionState.DISCONNECTED: "Disconnected",
    ConnectionState.CONNECTING: "Connecting...",
    ConnectionState.CONNECTED: "Connected",
    ConnectionState.RECONNECTING: "Reconnecting...",
    ConnectionState.AUTH_ERROR: "Auth error",
    ConnectionState.PERMISSION_ERROR: "Permission denied",
    ConnectionState.ERROR: "Connection error",
}


def create_tray_icon(color: QColor, size: int = 32) -> QIcon:
    """Draw a simple colored circle as the tray icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # transparent
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QBrush(color))
    painter.setPen(QColor(0, 0, 0, 80))
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    """Manages the QSystemTrayIcon, context menu, and state-based icon swaps."""

    connect_profile = Signal(str)   # profile_id
    disconnect = Signal()
    show_window = Signal()
    quit_app = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.tray = QSystemTrayIcon()
        self.tray.setToolTip("OpenFortiTray")
        self.tray.activated.connect(self._on_activated)

        # Set an initial icon immediately
        color = STATE_COLORS[ConnectionState.DISCONNECTED]
        self.tray.setIcon(create_tray_icon(color))

        self._menu: QMenu | None = None
        self._profiles: list[VpnProfile] = []
        self._active_profile: VpnProfile | None = None
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._build_menu()

    def set_profiles(self, profiles: list[VpnProfile]) -> None:
        self._profiles = profiles
        self._build_menu()

    def set_active_profile(self, profile: VpnProfile | None) -> None:
        self._active_profile = profile
        self._build_menu()

    def update_state(self, state: ConnectionState) -> None:
        self._state = state
        color = STATE_COLORS.get(state, STATE_COLORS[ConnectionState.DISCONNECTED])
        self.tray.setIcon(create_tray_icon(color))

        profile_name = self._active_profile.name if self._active_profile else ""
        status = STATE_LABELS.get(state, str(state))
        self.tray.setToolTip(f"OpenFortiTray -- {status}" +
                             (f" ({profile_name})" if profile_name else ""))
        self._build_menu()

    def show(self) -> None:
        # Ensure menu is set before showing
        if self._menu:
            self.tray.setContextMenu(self._menu)
        self.tray.show()

    def _build_menu(self) -> None:
        """Rebuild the context menu (WIREFRAMES.md)."""
        menu = QMenu(None)
        menu.setTearOffEnabled(False)

        # Status label (disabled)
        status_text = STATE_LABELS.get(self._state, "Unknown")
        if self._active_profile and self._state == ConnectionState.CONNECTED:
            label = f"{status_text} ({self._active_profile.name})"
        else:
            label = status_text
        status_action = menu.addAction(label)
        status_action.setEnabled(False)

        menu.addSeparator()

        # Connect/Disconnect
        if self._state in (ConnectionState.CONNECTED, ConnectionState.CONNECTING,
                           ConnectionState.RECONNECTING):
            disc = menu.addAction("Disconnect")
            disc.triggered.connect(lambda: self.disconnect.emit())
        else:
            if self._active_profile:
                conn = menu.addAction(f"Connect to {self._active_profile.name}")
                conn.triggered.connect(
                    lambda: self.connect_profile.emit(self._active_profile.id)
                )

        menu.addSeparator()

        # Quick profile switch list
        for p in self._profiles:
            is_active = (
                self._active_profile
                and self._active_profile.id == p.id
                and self._state == ConnectionState.CONNECTED
            )
            prefix = "\u2713 " if is_active else "  "
            action = menu.addAction(f"{prefix}{p.name}")
            if is_active:
                action.setEnabled(False)
            else:
                action.triggered.connect(
                    lambda checked, pid=p.id: self.connect_profile.emit(pid)
                )

        menu.addSeparator()

        # Open main window
        show = menu.addAction("Open OpenFortiTray")
        show.triggered.connect(lambda: self.show_window.emit())

        # Quit
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(lambda: self.quit_app.emit())

        # Replace the old menu
        old = self.tray.contextMenu()
        self._menu = menu
        self.tray.setContextMenu(menu)
        if old:
            old.deleteLater()

    def _on_activated(self, reason) -> None:
        """Double-click on tray icon shows the window."""
        from PySide6.QtWidgets import QSystemTrayIcon as Tray

        if reason == Tray.DoubleClick:
            self.show_window.emit()

    @staticmethod
    def is_available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()
