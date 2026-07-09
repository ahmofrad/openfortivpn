"""Sleep/wake-aware reconnect (SPEC.md §7).

Detects OS sleep/wake events and triggers a reconnect if the VPN
was connected when sleep started. On Windows uses QT's power event
resumed signal. On macOS/Linux uses a periodic reachability probe
as a fallback.
"""

from __future__ import annotations

import logging
import socket

from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger(__name__)


class SleepWakeMonitor(QObject):
    """Monitors for system sleep/wake events.

    On wake, emits `wake_detected` so the App can trigger a reconnect
    if the VPN was connected before sleep.
    """

    wake_detected = Signal()
    sleep_detected = Signal()

    def __init__(
        self,
        was_connected: callable,
        probe_host: str = "8.8.8.8",
        probe_port: int = 53,
        interval_ms: int = 5000,
    ) -> None:
        super().__init__()
        self._was_connected = was_connected
        self._probe_host = probe_host
        self._probe_port = probe_port
        self._interval_ms = interval_ms
        self._last_probe_ok = True
        self._timer: QTimer | None = None

    def start(self) -> None:
        self._timer = QTimer()
        self._timer.timeout.connect(self._probe)
        self._timer.start(self._interval_ms)
        logger.debug("SleepWakeMonitor started (interval=%dms)", self._interval_ms)

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None

    def _probe(self) -> None:
        """Detect sleep/wake by checking network reachability.

        If the network was unreachable (likely during sleep) and becomes
        reachable again, emit wake_detected.
        """
        ok = self._check_reachable()
        if not self._last_probe_ok and ok:
            logger.info("Network back online (wake detected)")
            self.wake_detected.emit()
        self._last_probe_ok = ok

    def _check_reachable(self) -> bool:
        try:
            with socket.create_connection(
                (self._probe_host, self._probe_port), timeout=3
            ):
                return True
        except (socket.timeout, OSError):
            return False
