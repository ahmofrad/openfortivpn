"""Single-instance guard using a named mutex (Windows) or lock file (POSIX).

If another instance is already running, signals the first instance to
bring its window to the foreground.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Global signal name for "show existing window"
SHOW_WINDOW_EVENT = "OpenFortiTray_ShowWindow"


def acquire_single_instance(name: str = "OpenFortiTray") -> bool:
    """Try to acquire a single-instance lock.

    Returns True if this is the first instance (lock acquired),
    False if another instance is already running.
    """
    if sys.platform == "win32":
        return _win_acquire(name)
    return _posix_acquire(name)


def signal_existing_instance() -> None:
    """Signal the running instance to show its window."""
    if sys.platform == "win32":
        _win_signal()
    else:
        _posix_signal()


# ── Windows ──────────────────────────────────────────────────────


def _win_acquire(name: str) -> bool:
    try:
        import ctypes

        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexExW(
            None, f"Global\\{name}_Mutex", 0, 0x1F0001
        )
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
        return True
    except Exception as e:
        logger.warning("Single-instance check failed: %s", e)
        return True


def _win_signal() -> None:
    """Pulse the show-window event so the existing instance brings itself forward."""
    try:
        import ctypes

        # Set the event (the main instance polls it or uses SetEvent)
        handle = ctypes.windll.kernel32.OpenEventW(
            0x1F0003,  # EVENT_ALL_ACCESS
            False,
            f"Global\\{SHOW_WINDOW_EVENT}",
        )
        if handle:
            ctypes.windll.kernel32.SetEvent(handle)
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        pass


# ── POSIX ────────────────────────────────────────────────────────


_lock_file: Path | None = None


def _posix_acquire(name: str) -> bool:
    global _lock_file
    lock_path = Path(tempfile.gettempdir()) / f"{name}.lock"
    try:
        _lock_file = Path(lock_path)
        if _lock_file.exists():
            try:
                old_pid = int(_lock_file.read_text().strip())
                os.kill(old_pid, 0)
                return False
            except (ValueError, OSError, ProcessLookupError):
                pass
        _lock_file.write_text(str(os.getpid()))
        return True
    except OSError:
        return True


def _posix_signal() -> None:
    """Touch a signal file that the main instance checks."""
    signal_file = Path(tempfile.gettempdir()) / "openfortitray_show.signal"
    try:
        signal_file.touch()
    except OSError:
        pass
