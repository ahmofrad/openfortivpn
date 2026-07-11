"""Per-OS privilege elevation for the openfortivpn subprocess (AUTH.md §8).

Three strategies:
  - Linux: pkexec (preserves stdio -> direct pipe)
  - macOS: osascript "with administrator privileges" (synchronous, no pipe -> log file)
  - Windows: ShellExecuteW "runas" (no pipe to parent -> log file)

Returns an ElevatedProcess abstraction that the ConnectionManager uses
regardless of platform.
"""

from __future__ import annotations

import logging
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from typing import IO

logger = logging.getLogger(__name__)

# Windows: CREATE_NO_WINDOW flag to prevent CMD window flashing
_WIN_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def get_temp_dir() -> pathlib.Path:
    """Return a temp directory with a long (non-8.3) path.

    On Windows, tempfile.gettempdir() may return a short path like
    C:\\Users\\A58A4~1\\... which elevated processes can't resolve.
    This converts it to the full long path.
    """
    tmp = pathlib.Path(tempfile.gettempdir()) / "openfortitray"

    if sys.platform == "win32":
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.kernel32.GetLongPathNameW(str(tmp), buf, 260)
            if buf.value:
                tmp = pathlib.Path(buf.value)
        except Exception:
            pass

    return tmp


class ElevatedProcess(ABC):
    """Platform-agnostic handle on a running elevated subprocess."""

    @property
    @abstractmethod
    def is_running(self) -> bool: ...

    @abstractmethod
    def read_line(self) -> str | None:
        """Return the next stdout line, or None at EOF."""
        ...

    @abstractmethod
    def write_input(self, text: str) -> bool:
        """Write text to the process stdin. Returns True on success."""
        ...

    @abstractmethod
    def terminate(self, timeout: float = 10.0) -> int:
        """Signal graceful shutdown, then kill if needed. Return exit code."""
        ...

    @abstractmethod
    def wait(self, timeout: float | None = None) -> int:
        """Wait for the process to exit. Return exit code."""
        ...


# ── Linux: pkexec with direct pipe ──────────────────────────────


class _PopenProcess(ElevatedProcess):
    """Wraps a subprocess.Popen -- used on Linux where pkexec preserves stdio."""

    def __init__(self, popen: subprocess.Popen) -> None:
        self._popen = popen

    @property
    def is_running(self) -> bool:
        return self._popen.poll() is None

    def read_line(self) -> str | None:
        assert self._popen.stdout is not None
        line = self._popen.stdout.readline()
        if line == "":
            return None
        return line.rstrip("\r\n")

    def write_input(self, text: str) -> bool:
        if self._popen.poll() is not None:
            return False
        try:
            assert self._popen.stdin is not None
            self._popen.stdin.write(text + "\n")
            self._popen.stdin.flush()
            return True
        except (OSError, BrokenPipeError):
            return False

    def terminate(self, timeout: float = 10.0) -> int:
        if self._popen.poll() is not None:
            return self._popen.returncode

        if sys.platform == "win32":
            # Use TerminateProcess directly via Popen.kill() -- this uses
            # the handle from CreateProcess which always has
            # PROCESS_TERMINATE access, regardless of UAC elevation.
            # This is more reliable than taskkill which may get Access Denied.
            try:
                self._popen.kill()
            except Exception as e:
                logger.warning("Popen.kill() failed: %s, trying taskkill", e)
                subprocess.run(
                    ["taskkill", "/PID", str(self._popen.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                    creationflags=_WIN_NO_WINDOW,
                )
        else:
            self._popen.send_signal(signal.SIGTERM)

        try:
            return self._popen.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Final resort
            try:
                self._popen.kill()
            except Exception:
                pass
            return self._popen.wait(timeout=5)

    def wait(self, timeout: float | None = None) -> int:
        return self._popen.wait(timeout=timeout)


def _launch_linux(binary: str, config_path: str, verbose: bool = True) -> ElevatedProcess:
    """Launch via pkexec (AUTH.md §8)."""
    cmd = ["pkexec", binary, "-c", config_path]
    if verbose:
        cmd.append("-v")
    logger.debug("Launching (pkexec): %s", cmd)
    popen = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=_WIN_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return _PopenProcess(popen)


# ── Windows: ShellExecuteW runas + log file polling ─────────────


class _LogPollingProcess(ElevatedProcess):
    """Wraps a detached process whose output goes to a log file.

    Used on Windows (ShellExecute runas) and macOS (osascript),
    where we can't get a direct pipe to the elevated process.

    Liveness is determined by checking for the exit-code file written
    by the wrapper script, not by querying the PID (which may run as
    a different user and be inaccessible).
    """

    def __init__(
        self,
        pid: int,
        log_path: pathlib.Path,
        pid_path: pathlib.Path,
    ) -> None:
        self._pid = pid
        self._log_path = log_path
        self._pid_path = pid_path
        self._exit_path = log_path.parent / "vpn_exitcode.txt"
        self._log_file: IO[str] | None = None
        self._exit_code: int | None = None
        self._opened = False
        self._log_lines_buffer: list[str] = []
        self._terminated = False

    def write_input(self, text: str) -> bool:
        """Write to process stdin -- not supported for log-polling processes."""
        return False

    def _ensure_log_open(self) -> None:
        if not self._opened:
            # Wait for the elevated process to create the log file
            for _ in range(50):  # up to 5 seconds
                if self._log_path.exists():
                    break
                if self._terminated:
                    return
                time.sleep(0.1)
            if not self._log_path.exists():
                self._exit_code = -1
                return
            self._log_file = open(self._log_path, "r", encoding="utf-8", errors="replace")
            self._opened = True

    @property
    def is_running(self) -> bool:
        if self._exit_code is not None or self._terminated:
            return False
        # The process is running if the exit-code file doesn't exist yet.
        return not self._exit_path.exists()

    def read_line(self) -> str | None:
        # Return buffered lines first
        if self._log_lines_buffer:
            return self._log_lines_buffer.pop(0)

        self._ensure_log_open()
        if self._log_file is None:
            return None

        # Poll for new data with short timeout
        for _ in range(5):
            line = self._log_file.readline()
            if line:
                return line.rstrip("\r\n")
            if not self.is_running:
                # Process exited -- drain remaining lines from the log
                remaining = self._log_file.read()
                self._log_file.close()
                self._log_file = None
                if remaining:
                    lines = remaining.splitlines()
                    for line in lines[1:]:
                        self._log_lines_buffer.append(line)
                    return lines[0] if lines else None
                return None
            time.sleep(0.2)
        return None  # timeout, no new data

    def terminate(self, timeout: float = 10.0) -> int:
        """Signal the process to stop."""
        self._terminated = True

        if sys.platform == "win32":
            # Try multiple approaches to kill the elevated openfortivpn.exe:
            # 1. taskkill /IM (kill by image name)
            # 2. wmic process delete (WMI-based, works cross-privilege)
            # 3. PowerShell Stop-Process (.NET based)
            killed = False

            # Approach 1: taskkill
            result = subprocess.run(
                ["taskkill", "/IM", "openfortivpn.exe", "/T", "/F"],
                capture_output=True,
                timeout=10,
                creationflags=_WIN_NO_WINDOW,
            )
            if result.returncode == 0:
                killed = True
            else:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                logger.warning("taskkill /IM failed: %s", stderr)

            # Approach 2: wmic (works cross-privilege on some configs)
            if not killed:
                result = subprocess.run(
                    ["wmic", "process", "where", "name='openfortivpn.exe'", "delete"],
                    capture_output=True,
                    timeout=10,
                    creationflags=_WIN_NO_WINDOW,
                )
                if result.returncode == 0:
                    killed = True
                else:
                    logger.warning("wmic delete failed: %s",
                                   result.stderr.decode("utf-8", errors="replace").strip())

            # Approach 3: PowerShell Stop-Process
            if not killed:
                try:
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                         "-Command",
                         "Get-Process -Name openfortivpn -ErrorAction SilentlyContinue | "
                         "Stop-Process -Force"],
                        capture_output=True,
                        timeout=10,
                        creationflags=_WIN_NO_WINDOW,
                    )
                    if result.returncode == 0:
                        killed = True
                except Exception as e:
                    logger.warning("PowerShell Stop-Process failed: %s", e)

            # Kill the wrapper cmd.exe PID too
            if self._pid > 0:
                subprocess.run(
                    ["taskkill", "/PID", str(self._pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                    creationflags=_WIN_NO_WINDOW,
                )
        else:
            try:
                os.kill(self._pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass

        return self.wait(timeout=timeout)

    def wait(self, timeout: float | None = None) -> int:
        deadline = time.monotonic() + timeout if timeout else None
        while self.is_running:
            if deadline and time.monotonic() > deadline:
                # Force kill already done in terminate()
                break
            time.sleep(0.3)

        # Read exit code from the file written by the wrapper script
        if self._exit_code is None:
            if self._exit_path.exists():
                try:
                    self._exit_code = int(self._exit_path.read_text().strip())
                except (ValueError, OSError):
                    self._exit_code = -1
            else:
                self._exit_code = -1

        self._cleanup()
        return self._exit_code

    def _cleanup(self) -> None:
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        # Clean up pid file
        if self._pid_path.exists():
            try:
                self._pid_path.unlink()
            except OSError:
                pass


def _is_pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # PROCESS_QUERY_LIMITED_INFORMATION (0x1000) works across privilege
        # boundaries -- our non-elevated GUI can query the elevated process.
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return exit_code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _launch_windows(
    binary: str, config_path: str, verbose: bool = True
) -> ElevatedProcess:
    """Launch via ShellExecuteW with 'runas' verb (AUTH.md §8).

    Creates a wrapper batch file that:
      1. Writes its PID to a pid file
      2. Runs openfortivpn.exe with output redirected to a log file
      3. Writes the exit code

    The wrapper is launched elevated via ShellExecuteEx(runas).
    """
    tmpdir = get_temp_dir()
    tmpdir.mkdir(parents=True, exist_ok=True)

    log_path = tmpdir / "vpn_output.log"
    pid_path = tmpdir / "vpn.pid"
    exit_path = tmpdir / "vpn_exitcode.txt"

    # Clear old files
    for p in (log_path, pid_path, exit_path):
        p.unlink(missing_ok=True)

    verbosity = "-v" if verbose else ""

    # Write a batch wrapper -- runs the binary, captures output, writes PID
    wrapper_lines = [
        "@echo off",
        "echo %~f0 > nul",
        "echo %PID% > nul",
        # Write the PID of this cmd.exe process via PowerShell
        f'powershell -NoProfile -Command "Set-Content -Path \'{pid_path}\' -Value $PID"',
        # Run openfortivpn with output capture
        f'"{binary}" {verbosity} -c "{config_path}" > "{log_path}" 2>&1',
        # Write exit code
        f'echo %ERRORLEVEL% > "{exit_path}"',
    ]
    wrapper_path = tmpdir / "vpn_wrapper.bat"
    wrapper_path.write_text("\r\n".join(wrapper_lines) + "\r\n", encoding="ascii")

    import ctypes

    SW_HIDE = 0

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("fMask", ctypes.c_ulong),
            ("hwnd", ctypes.c_void_p),
            ("lpVerb", ctypes.c_wchar_p),
            ("lpFile", ctypes.c_wchar_p),
            ("lpParameters", ctypes.c_wchar_p),
            ("lpDirectory", ctypes.c_wchar_p),
            ("nShow", ctypes.c_int),
            ("hInstApp", ctypes.c_void_p),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", ctypes.c_wchar_p),
            ("hkeyClass", ctypes.c_void_p),
            ("dwHotKey", ctypes.c_ulong),
            ("hIcon", ctypes.c_void_p),
            ("hProcess", ctypes.c_void_p),
        ]

    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = "runas"
    sei.lpFile = str(wrapper_path)
    sei.lpParameters = None
    sei.lpDirectory = str(tmpdir)
    sei.nShow = SW_HIDE

    logger.debug("Launching elevated: %s", wrapper_path)
    ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
    if not ok:
        err = ctypes.get_last_error()
        if err == 1223:  # ERROR_CANCELLED -- user clicked No on UAC
            raise OSError("Elevation cancelled by user.")
        raise OSError(f"ShellExecuteEx failed (error {err}).")

    # Wait for the PID file to appear (the batch writes it immediately)
    pid = 0
    for _ in range(100):  # up to 10 seconds
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text().strip())
            except (ValueError, OSError):
                pass
            if pid > 0:
                break
        time.sleep(0.1)

    if pid == 0:
        logger.error("Could not obtain VPN process PID from %s", pid_path)
        pid = -1

    return _LogPollingProcess(pid, log_path, pid_path)


# ── macOS: osascript + log file polling ─────────────────────────


def _launch_macos(
    binary: str, config_path: str, verbose: bool = True
) -> ElevatedProcess:
    """Launch via osascript 'with administrator privileges' (AUTH.md §8)."""
    tmpdir = get_temp_dir()
    tmpdir.mkdir(parents=True, exist_ok=True)

    log_path = tmpdir / "vpn_output.log"
    pid_path = tmpdir / "vpn.pid"

    log_path.unlink(missing_ok=True)
    pid_path.unlink(missing_ok=True)

    verbosity = "-v" if verbose else ""
    # The shell script runs the binary, captures output, and writes PID
    shell_cmd = (
        f'{binary} {verbosity} -c "{config_path}" '
        f'> "{log_path}" 2>&1 & echo $! > "{pid_path}"'
    )

    applescript = f'do shell script "{shell_cmd}" with administrator privileges'

    # osascript is synchronous, so run it in a thread
    def _run_osascript() -> None:
        subprocess.run(["osascript", "-e", applescript], check=False)

    thread = threading.Thread(target=_run_osascript, daemon=True)
    thread.start()

    # Wait for PID file
    pid = 0
    for _ in range(50):
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text().strip())
            except (ValueError, OSError):
                pass
            break
        time.sleep(0.1)

    if pid == 0:
        logger.error("Could not obtain VPN process PID")
        pid = -1

    return _LogPollingProcess(pid, log_path, pid_path)


def _is_elevated() -> bool:
    """Check if the current process is already running with elevated privileges."""
    if sys.platform == "win32":
        try:
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False
    else:
        return os.geteuid() == 0


# ── Public dispatch ─────────────────────────────────────────────


def launch_elevated(
    binary: str, config_path: str, verbose: bool = True
) -> ElevatedProcess:
    """Launch openfortivpn elevated, per-OS dispatch (AUTH.md §8).

    If the current process is already elevated, launches directly
    (gives us proper process control + stdin for interactive prompts).

    Raises FileNotFoundError if the binary doesn't exist.
    Raises OSError if the elevation itself fails (e.g. user cancels UAC).
    """
    if not os.path.isfile(binary):
        raise FileNotFoundError(f"Binary not found: {binary}")

    # If we're already elevated, skip the elevation dance entirely
    # and use a direct Popen (gives us stdin + real process control)
    if _is_elevated():
        logger.info("Process is already elevated -- launching directly")
        cmd = [binary, "-c", config_path]
        if verbose:
            cmd.append("-v")
        popen = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            creationflags=_WIN_NO_WINDOW,
        )
        return _PopenProcess(popen)

    if sys.platform == "linux":
        return _launch_linux(binary, config_path, verbose)
    elif sys.platform == "win32":
        return _launch_windows(binary, config_path, verbose)
    elif sys.platform == "darwin":
        return _launch_macos(binary, config_path, verbose)
    else:
        logger.warning("Unknown platform %s, launching without elevation", sys.platform)
        cmd = [binary, "-c", config_path]
        if verbose:
            cmd.append("-v")
        popen = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=_WIN_NO_WINDOW,
        )
        return _PopenProcess(popen)
