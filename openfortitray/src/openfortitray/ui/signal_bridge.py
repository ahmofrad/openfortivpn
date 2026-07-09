"""Thread-safe bridge for emitting state/output from background threads to Qt.

Qt requires all UI operations to happen on the main thread. The VPN reader
thread runs in the background and must not touch widgets directly. This
class provides Qt signals that safely marshal calls to the main thread.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal



class SignalBridge(QObject):
    """Emits signals that are safe to connect to Qt slots."""

    state_changed = Signal(int)       # ConnectionState value
    vpn_output = Signal(str)          # log line


# Singleton -- created once on the main thread
_bridge: SignalBridge | None = None


def get_bridge() -> SignalBridge:
    global _bridge
    if _bridge is None:
        _bridge = SignalBridge()
    return _bridge
