"""Privileged helper daemon for Windows (AUTH.md §8 v2).

Launched once per app session with a single UAC prompt. Runs elevated,
owns all openfortivpn child processes, and communicates with the
unprivileged GUI over a named pipe.

Protocol (newline-delimited text):
  GUI -> helper:  START <binary> <config_path> [verbose]
                  STOP
                  SHUTDOWN
  helper -> GUI:  LINE <log line>
                  EXIT <code>
                  PID <pid>
                  READY
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PIPE_NAME = r"\\.\pipe\OpenFortiTrayHelper"

# Windows CREATE_NO_WINDOW
_WIN_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Module-level handle on the currently running openfortivpn child process
# so the shutdown watchdog can kill it before hard-exiting.
_vpn_proc: "subprocess.Popen | None" = None


def _kill_vpn_now() -> None:
    """Force-kill the tracked VPN child process (best effort)."""
    global _vpn_proc
    try:
        if _vpn_proc is not None and _vpn_proc.poll() is None:
            _vpn_proc.kill()
    except Exception:
        pass


# ── Helper side (runs elevated) ─────────────────────────────────


def _helper_main(pipe_name: str = PIPE_NAME) -> int:
    """Run the helper daemon. This process must be elevated."""
    global _vpn_proc
    import win32file
    import win32pipe
    import win32api
    import pywintypes
    import winerror

    proc: subprocess.Popen | None = None
    proc_lock = threading.Lock()

    def kill_proc() -> None:
        nonlocal proc
        global _vpn_proc
        with proc_lock:
            if proc is not None and proc.poll() is None:
                logger.debug("Helper: killing openfortivpn")
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            proc = None
            _vpn_proc = None

    def reader_thread(p: subprocess.Popen, pipe) -> None:
        """Read openfortivpn output and forward to pipe."""
        try:
            assert p.stdout is not None
            for raw in p.stdout:
                line = raw.rstrip("\r\n")
                _pipe_write_line(pipe, f"LINE {line}")
            rc = p.wait()
        except Exception:
            rc = -1
        _pipe_write_line(pipe, f"EXIT {rc}")

    while True:
        # Create the pipe (fresh instance per client)
        try:
            pipe = win32pipe.CreateNamedPipe(
                pipe_name,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                1, 65536, 65536, 0, None,
            )
        except pywintypes.error as e:
            if e.winerror == winerror.ERROR_PIPE_BUSY:
                # Another helper instance already owns the pipe.
                # Exit silently -- the GUI will connect to the existing one.
                logger.debug("Helper: pipe already owned by another instance, exiting")
                return 0
            raise
        logger.debug("Helper: waiting for GUI connection...")
        try:
            win32pipe.ConnectNamedPipe(pipe, None)
        except win32api.error:
            win32file.CloseHandle(pipe)
            continue

        logger.debug("Helper: GUI connected")
        _pipe_write_line(pipe, "READY")

        buf = b""
        try:
            while True:
                hr, chunk = win32file.ReadFile(pipe, 4096, None)
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    cmd = line.decode("utf-8", errors="replace").strip()
                    if not cmd:
                        continue

                    logger.debug("Helper: received: %s", cmd[:80])
                    parts = cmd.split(" ", 1)
                    verb = parts[0].upper()

                    if verb == "START":
                        kill_proc()
                        args = parts[1].split("\t") if len(parts) > 1 else []
                        if len(args) < 2:
                            _pipe_write_line(pipe, "EXIT 1")
                            continue
                        binary, config_path = args[0], args[1]
                        verbose = len(args) > 2 and args[2] == "1"
                        cmdline = [binary, "-c", config_path]
                        if verbose:
                            cmdline.append("-v")
                        proc = subprocess.Popen(
                            cmdline,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                            creationflags=_WIN_NO_WINDOW,
                        )
                        _vpn_proc = proc
                        _pipe_write_line(pipe, f"PID {proc.pid}")
                        threading.Thread(
                            target=reader_thread, args=(proc, pipe), daemon=True
                        ).start()

                    elif verb == "STOP":
                        kill_proc()
                        _pipe_write_line(pipe, "EXIT 0")

                    elif verb == "SHUTDOWN":
                        kill_proc()
                        return 0

        except win32api.error as e:
            # Client disconnected
            logger.debug("Helper: client disconnected: %s", e)
            kill_proc()
            win32file.CloseHandle(pipe)


def _pipe_write_line(pipe, text: str) -> None:
    import win32file

    try:
        win32file.WriteFile(pipe, (text + "\n").encode("utf-8"))
    except win32file.error:
        pass


# ── Client side (GUI, unprivileged) ─────────────────────────────


class HelperClient:
    """Client for the privileged helper daemon.

    Falls back to direct launch if the helper can't be started
    (e.g. non-Windows, or UAC cancelled).
    """

    def __init__(self, pipe_name: str = PIPE_NAME) -> None:
        self.pipe_name = pipe_name
        self._pipe = None
        self._lock = threading.Lock()
        self._read_buffer = b""
        self.on_line = None      # callable(str)
        self.on_exit = None      # callable(int)
        self.on_pid = None       # callable(int)
        self._reader: threading.Thread | None = None
        self._connected = False

    def start_helper(self) -> bool:
        """Connect to the helper daemon, launching it elevated if needed.

        First tries to connect to an already-running helper (no UAC
        prompt). Only launches a new elevated helper if none exists.
        """
        if self._connected:
            return True

        # 1. Try to reuse an already-running helper (no UAC prompt).
        if self._connect_to_pipe(attempts=1):
            logger.info("Helper: connected to existing helper daemon")
            return True

        # 2. No helper running -- launch one elevated.
        if not self._launch_elevated():
            return False

        # 3. Connect to the newly launched helper.
        if self._connect_to_pipe(attempts=30):  # ~6s
            logger.info("Helper: connected")
            return True

        logger.error("Helper: could not connect to pipe")
        return False

    def _launch_elevated(self) -> bool:
        """Launch the helper elevated via ShellExecuteEx(runas)."""
        # Write a small helper launcher script to temp
        tmp = Path(os.environ.get("TEMP", ".")) / "openfortitray"
        tmp.mkdir(parents=True, exist_ok=True)
        launcher = tmp / "helper_launcher.bat"

        if getattr(sys, "frozen", False):
            helper_cmd = f'"{sys.executable}" --run-helper'
        else:
            helper_cmd = f'"{sys.executable}" -m openfortitray.helper --run-helper'
        launcher.write_text(f"@echo off\r\n{helper_cmd}\r\n", encoding="ascii")

        import ctypes

        SW_HIDE = 0

        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong), ("fMask", ctypes.c_ulong),
                ("hwnd", ctypes.c_void_p), ("lpVerb", ctypes.c_wchar_p),
                ("lpFile", ctypes.c_wchar_p), ("lpParameters", ctypes.c_wchar_p),
                ("lpDirectory", ctypes.c_wchar_p), ("nShow", ctypes.c_int),
                ("hInstApp", ctypes.c_void_p), ("lpIDList", ctypes.c_void_p),
                ("lpClass", ctypes.c_wchar_p), ("hkeyClass", ctypes.c_void_p),
                ("dwHotKey", ctypes.c_ulong), ("hIcon", ctypes.c_void_p),
                ("hProcess", ctypes.c_void_p),
            ]

        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
        sei.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
        sei.lpVerb = "runas"
        sei.lpFile = str(launcher)
        sei.nShow = SW_HIDE

        ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
        if not ok:
            err = ctypes.get_last_error()
            logger.warning("Helper: ShellExecuteEx failed (error %d)", err)
            return False
        return True

    def _connect_to_pipe(self, attempts: int) -> bool:
        """Try to connect to the helper's named pipe and handshake.

        Returns True if connected and READY received.
        """
        import win32file
        import winerror
        import pywintypes

        self._pipe = None
        for _ in range(attempts):
            try:
                self._pipe = win32file.CreateFile(
                    self.pipe_name,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0, None, win32file.OPEN_EXISTING, 0, None,
                )
                break
            except pywintypes.error as e:
                if e.winerror in (
                    winerror.ERROR_PIPE_BUSY,
                    winerror.ERROR_FILE_NOT_FOUND,
                ):
                    time.sleep(0.2)
                    continue
                time.sleep(0.2)

        if self._pipe is None:
            return False

        # Wait for READY
        line = self._read_line(timeout=5.0)
        if line != "READY":
            logger.error("Helper: expected READY, got: %r", line)
            self.disconnect()
            return False

        self._connected = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return True

    @property
    def is_connected(self) -> bool:
        return self._connected

    def start_vpn(self, binary: str, config_path: str, verbose: bool = True) -> bool:
        """Tell the helper to start openfortivpn."""
        if not self._connected:
            return False
        self._send(f"START {binary}\t{config_path}\t{'1' if verbose else '0'}")
        return True

    def stop_vpn(self) -> None:
        """Tell the helper to stop openfortivpn."""
        if self._connected:
            self._send("STOP")

    def shutdown(self) -> None:
        """Tell the helper to exit."""
        if self._connected:
            self._send("SHUTDOWN")
            time.sleep(0.3)
        self.disconnect()

    def disconnect(self) -> None:
        self._connected = False
        if self._pipe is not None:
            try:
                import win32file

                win32file.CloseHandle(self._pipe)
            except Exception:
                pass
            self._pipe = None

    def _send(self, text: str) -> None:
        import win32file

        with self._lock:
            if self._pipe is not None:
                win32file.WriteFile(self._pipe, (text + "\n").encode("utf-8"))

    def _read_line(self, timeout: float = 5.0) -> str | None:
        """Read one line from the pipe (blocking with timeout)."""
        import win32file

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if b"\n" in self._read_buffer:
                line, self._read_buffer = self._read_buffer.split(b"\n", 1)
                return line.decode("utf-8", errors="replace").strip()
            try:
                _, chunk = win32file.ReadFile(self._pipe, 4096, 100)
                self._read_buffer += chunk
            except Exception:
                time.sleep(0.05)
        return None

    def _read_loop(self) -> None:
        """Background reader: dispatch LINE/EXIT/PID messages."""
        while self._connected:
            line = self._read_line(timeout=0.5)
            if line is None:
                continue
            if line.startswith("LINE "):
                if self.on_line:
                    self.on_line(line[5:])
            elif line.startswith("EXIT "):
                try:
                    rc = int(line[5:])
                except ValueError:
                    rc = -1
                if self.on_exit:
                    self.on_exit(rc)
            elif line.startswith("PID "):
                try:
                    pid = int(line[4:])
                except ValueError:
                    pid = -1
                if self.on_pid:
                    self.on_pid(pid)


# ── CLI entry point ─────────────────────────────────────────────


def main() -> int:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s helper: %(message)s",
    )
    _install_shutdown_watcher()
    try:
        return _helper_main()
    except Exception:
        # Never crash with a traceback dialog -- exit silently.
        logger.exception("Helper daemon fatal error")
        return 1


def _install_shutdown_watcher() -> None:
    """Hard-exit on Windows session end to avoid shutdown crash dialogs.

    A message-only window receives WM_QUERYENDSESSION / WM_ENDSESSION
    during logoff/shutdown; we os._exit() immediately so Python
    finalizers and the blocking pipe loop can't fault during teardown.
    """
    if sys.platform != "win32":
        return

    def _watch() -> None:
        try:
            import win32con
            import win32gui

            def wndproc(hwnd, msg, wparam, lparam):
                if msg in (win32con.WM_QUERYENDSESSION, win32con.WM_ENDSESSION):
                    _kill_vpn_now()
                    os._exit(0)
                return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

            wc = win32gui.WNDCLASS()
            wc.lpfnWndProc = wndproc
            wc.lpszClassName = "OFTHelperWatchdog"
            wc.hInstance = win32gui.GetModuleHandle(None)
            win32gui.RegisterClass(wc)
            win32gui.CreateWindow(
                wc.lpszClassName, "watcher", 0, 0, 0, 0, 0,
                win32con.HWND_MESSAGE, 0, wc.hInstance, None,
            )
            win32gui.PumpMessages()
        except Exception:
            pass

    threading.Thread(target=_watch, daemon=True).start()


if __name__ == "__main__":
    if "--run-helper" in sys.argv:
        sys.exit(main())
