"""Main window with profile dropdown."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openfortitray.core.profile import VpnProfile
from openfortitray.core.state_machine import ConnectionState
from openfortitray.ui.log_viewer import LogPanel

STATUS_TEXT = {
    ConnectionState.DISCONNECTED: "Disconnected",
    ConnectionState.CONNECTING: "Connecting...",
    ConnectionState.CONNECTED: "Connected",
    ConnectionState.RECONNECTING: "Reconnecting...",
    ConnectionState.AUTH_ERROR: "Authentication error",
    ConnectionState.PERMISSION_ERROR: "Permission denied (need admin/root)",
    ConnectionState.ERROR: "Connection error",
}


class MainWindow(QMainWindow):
    connect_requested = Signal(VpnProfile)
    disconnect_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()
    add_profile = Signal()
    edit_profile = Signal(VpnProfile)
    delete_profile = Signal(VpnProfile)
    export_profile = Signal(VpnProfile)
    import_profile = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpenFortiTray")
        self._profiles: list[VpnProfile] = []

        # Set app icon
        from PySide6.QtGui import QIcon
        from pathlib import Path

        icon_path = None
        candidates = []
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "app_icon.png")
            candidates.append(Path(sys.executable).parent / "app_icon.png")
            candidates.append(Path(sys.executable).parent / "_internal" / "app_icon.png")
        else:
            candidates.append(Path(__file__).parent / "resources" / "app_icon.png")
        for c in candidates:
            if c.exists():
                icon_path = c
                break
        if icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))
        self._selected_profile: VpnProfile | None = None
        self._current_state: ConnectionState = ConnectionState.DISCONNECTED
        self._minimize_to_tray: bool = True
        self._force_quit: bool = False

        # Fixed size, no maximize button
        self.setFixedSize(360, 105)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint
        )

        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2,
        )
        self.setWindowState(Qt.WindowActive)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        # Row 1: Dropdown + Connect
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("VPN:"))
        self.combo_profiles = QComboBox()
        self.combo_profiles.setMinimumWidth(160)
        self.combo_profiles.currentIndexChanged.connect(self._on_selection)
        row1.addWidget(self.combo_profiles, stretch=1)
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self._on_connect_click)
        row1.addWidget(self.btn_connect)
        layout.addLayout(row1)

        # Row 2: Action buttons (under dropdown row)
        row2 = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_add.clicked.connect(lambda: self.add_profile.emit())
        row2.addWidget(self.btn_add)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self._on_edit_click)
        row2.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self._on_delete_click)
        row2.addWidget(self.btn_delete)

        self.btn_import = QPushButton("Import")
        self.btn_import.clicked.connect(lambda: self.import_profile.emit())
        row2.addWidget(self.btn_import)

        self.btn_export = QPushButton("Export")
        self.btn_export.clicked.connect(self._on_export_click)
        row2.addWidget(self.btn_export)

        self.btn_settings = QPushButton("\u2699")
        self.btn_settings.setMaximumWidth(32)
        self.btn_settings.setToolTip("Settings")
        self.btn_settings.clicked.connect(lambda: self.settings_requested.emit())
        row2.addWidget(self.btn_settings)

        self.btn_log = QPushButton("Log")
        self.btn_log.setCheckable(True)
        self.btn_log.toggled.connect(self._on_log_toggle)
        row2.addWidget(self.btn_log)
        layout.addLayout(row2)

        # Row 3: Status (under buttons)
        self.status_label = QLabel(
            f"Status: {STATUS_TEXT[ConnectionState.DISCONNECTED]}"
        )
        layout.addWidget(self.status_label)

        # Diagnostics log panel (hidden by default, expands window when shown)
        self.log_panel = LogPanel()

    def set_profiles(
        self, profiles: list[VpnProfile], selected_id: str | None = None
    ) -> None:
        self._profiles = profiles
        self.combo_profiles.clear()
        for p in profiles:
            self.combo_profiles.addItem(p.name, p)
        if selected_id:
            for i in range(self.combo_profiles.count()):
                data = self.combo_profiles.itemData(i)
                if data and data.id == selected_id:
                    self.combo_profiles.setCurrentIndex(i)
                    return
        if profiles:
            self.combo_profiles.setCurrentIndex(0)
            self._selected_profile = profiles[0]
        else:
            self._selected_profile = None

    def update_state(self, state: ConnectionState) -> None:
        self._current_state = state
        text = STATUS_TEXT.get(state, str(state))
        self.status_label.setText(f"Status: {text}")

        if state == ConnectionState.CONNECTED:
            self.btn_connect.setText("Disconnect")
        elif state in (ConnectionState.CONNECTING, ConnectionState.RECONNECTING):
            self.btn_connect.setText("Cancel")
        else:
            self.btn_connect.setText("Connect")

    def _on_selection(self, index: int) -> None:
        if index < 0 or index >= len(self._profiles):
            self._selected_profile = None
            return
        self._selected_profile = self.combo_profiles.itemData(index)

    def _on_connect_click(self) -> None:
        if self._current_state in (
            ConnectionState.CONNECTED,
            ConnectionState.CONNECTING,
            ConnectionState.RECONNECTING,
        ):
            self.disconnect_requested.emit()
            return
        if self._selected_profile is None:
            QMessageBox.information(self, "No profile", "Please select a VPN profile.")
            return
        self.connect_requested.emit(self._selected_profile)

    def _on_edit_click(self) -> None:
        if self._selected_profile:
            self.edit_profile.emit(self._selected_profile)

    def _on_delete_click(self) -> None:
        if self._selected_profile:
            self.delete_profile.emit(self._selected_profile)

    def _on_export_click(self) -> None:
        if self._selected_profile:
            self.export_profile.emit(self._selected_profile)

    def append_log_line(self, line: str) -> None:
        self.log_panel.append_line(line)

    def _on_log_toggle(self, checked: bool) -> None:
        if checked:
            self.btn_log.setText("Hide")
            self.setFixedSize(360, 300)
            self.centralWidget().layout().addWidget(self.log_panel)
            self.log_panel.show_panel()
        else:
            self.btn_log.setText("Log")
            self.log_panel.hide_panel()
            self.centralWidget().layout().removeWidget(self.log_panel)
            self.setFixedSize(360, 105)

    def set_minimize_to_tray(self, enabled: bool) -> None:
        self._minimize_to_tray = enabled

    def force_foreground(self) -> None:
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            try:
                import ctypes

                hwnd = int(self.winId())
                ctypes.windll.user32.ShowWindow(hwnd, 9)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._minimize_to_tray and not self._force_quit:
            event.ignore()
            self.hide()
        else:
            event.accept()

    def force_quit(self) -> None:
        self._force_quit = True
        self.close()
