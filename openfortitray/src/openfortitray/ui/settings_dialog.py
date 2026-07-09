"""Settings dialog (WIREFRAMES.md settings section)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
)

from openfortitray.core.profile import AppSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._settings = settings
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Startup
        self.chk_launch = QCheckBox("Launch at startup")
        self.chk_launch.setChecked(self._settings.launch_at_startup)
        form.addRow(self.chk_launch)

        self.chk_minimize = QCheckBox("Start minimized to tray")
        self.chk_minimize.setChecked(self._settings.start_minimized)
        form.addRow(self.chk_minimize)

        self.chk_tray_close = QCheckBox("Minimize to tray on close")
        self.chk_tray_close.setChecked(self._settings.minimize_to_tray)
        form.addRow(self.chk_tray_close)

        # Theme
        self.combo_theme = QComboBox()
        self.combo_theme.addItem("System", "system")
        self.combo_theme.addItem("Light", "light")
        self.combo_theme.addItem("Dark", "dark")
        idx = self.combo_theme.findData(self._settings.theme)
        if idx >= 0:
            self.combo_theme.setCurrentIndex(idx)
        form.addRow("Theme:", self.combo_theme)

        # Log level
        self.combo_log_level = QComboBox()
        self.combo_log_level.addItem("Error", "error")
        self.combo_log_level.addItem("Warning", "warn")
        self.combo_log_level.addItem("Info", "info")
        self.combo_log_level.addItem("Debug", "debug")
        idx = self.combo_log_level.findData(self._settings.log_level)
        if idx >= 0:
            self.combo_log_level.setCurrentIndex(idx)
        form.addRow("Log level:", self.combo_log_level)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self) -> None:
        self._settings.launch_at_startup = self.chk_launch.isChecked()
        self._settings.start_minimized = self.chk_minimize.isChecked()
        self._settings.minimize_to_tray = self.chk_tray_close.isChecked()
        self._settings.theme = self.combo_theme.currentData()
        self._settings.log_level = self.combo_log_level.currentData()
        self.accept()

    @property
    def settings(self) -> AppSettings:
        return self._settings
