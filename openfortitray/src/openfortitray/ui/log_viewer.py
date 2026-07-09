"""Diagnostics log panel -- tail the last N lines of openfortivpn output (SPEC.md §7).

A collapsible panel at the bottom of the main window that shows live
VPN subprocess output, with a copy-to-clipboard button.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LogPanel(QWidget):
    """Collapsible diagnostics log viewer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._visible = False
        self._max_lines = 500
        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("Diagnostics"))

        self.chk_autoscroll = QCheckBox("Auto-scroll")
        self.chk_autoscroll.setChecked(True)
        header.addWidget(self.chk_autoscroll)

        header.addStretch()

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        header.addWidget(self.btn_copy)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self._clear)
        header.addWidget(self.btn_clear)

        layout.addLayout(header)

        # Log text area
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(self._monospace_font())
        self.text_edit.setMaximumHeight(180)
        layout.addWidget(self.text_edit)

    @staticmethod
    def _monospace_font():
        from PySide6.QtGui import QFont

        font = QFont("Monospace")
        font.setStyleHint(QFont.TypeWriter)
        font.setPointSize(9)
        return font

    def append_line(self, line: str) -> None:
        """Append a log line and trim to max_lines."""
        self.text_edit.append(line)
        # Trim old lines
        doc = self.text_edit.document()
        if doc.blockCount() > self._max_lines:
            cursor = self.text_edit.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.movePosition(
                cursor.Down,
                cursor.KeepAnchor,
                doc.blockCount() - self._max_lines,
            )
            cursor.removeSelectedText()
            cursor.deleteChar()

        if self.chk_autoscroll.isChecked():
            self.text_edit.verticalScrollBar().setValue(
                self.text_edit.verticalScrollBar().maximum()
            )

    def toggle_visibility(self) -> None:
        self._visible = not self._visible
        self.setVisible(self._visible)

    def show_panel(self) -> None:
        self._visible = True
        self.show()

    def hide_panel(self) -> None:
        self._visible = False
        self.hide()

    def _clear(self) -> None:
        self.text_edit.clear()

    def _copy_to_clipboard(self) -> None:
        text = self.text_edit.toPlainText()
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
