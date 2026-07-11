"""Per-OS autostart registration (SPEC.md §6.4).

v1 implements Linux (.desktop). macOS and Windows are Phase 4.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "openfortitray"


def _autostart_path() -> Path:
    """Return the autostart file path for the current platform."""
    if sys.platform == "linux":
        return Path.home() / ".config" / "autostart" / f"{APP_NAME}.desktop"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / f"{APP_NAME}.plist"
    elif sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "~")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{APP_NAME}.lnk"
    return Path.home() / f".{APP_NAME}-autostart"


def is_autostart_enabled() -> bool:
    return _autostart_path().exists()


def enable_autostart() -> bool:
    """Install the autostart entry for the current platform."""
    path = _autostart_path()

    if sys.platform == "linux":
        return _write_linux_desktop(path)
    elif sys.platform == "darwin":
        return _write_macos_launchagent(path)
    elif sys.platform == "win32":
        return _write_windows_startup(path)
    logger.warning("Autostart not yet implemented for %s", sys.platform)
    return False


def disable_autostart() -> bool:
    """Remove the autostart entry."""
    path = _autostart_path()
    if path.exists():
        try:
            path.unlink()
            logger.info("Removed autostart entry: %s", path)
            return True
        except OSError as e:
            logger.error("Could not remove autostart entry: %s", e)
            return False
    return True


def _write_linux_desktop(path: Path) -> bool:
    """Write a .desktop file for XDG autostart."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if getattr(sys, "frozen", False):
        exec_path = sys.executable
    else:
        exec_path = f"{sys.executable} -m openfortitray"

    content = f"""\
[Desktop Entry]
Type=Application
Name=OpenFortiTray
Comment=VPN tray client for openfortivpn
Exec={exec_path}
Icon=openfortitray
Terminal=false
X-GNOME-Autostart-enabled=true
"""
    try:
        path.write_text(content, encoding="utf-8")
        logger.info("Installed autostart entry: %s", path)
        return True
    except OSError as e:
        logger.error("Could not write autostart entry: %s", e)
        return False


def _write_macos_launchagent(path: Path) -> bool:
    """Write a LaunchAgent plist for macOS (SPEC.md §6.4)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if getattr(sys, "frozen", False):
        exec_path = sys.executable
    else:
        exec_path = sys.executable

    label = f"com.snapp.{APP_NAME}"
    content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exec_path}</string>
        <string>-m</string>
        <string>openfortitray</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""
    try:
        path.write_text(content, encoding="utf-8")
        logger.info("Installed LaunchAgent: %s", path)
        return True
    except OSError as e:
        logger.error("Could not write LaunchAgent: %s", e)
        return False


def _write_windows_startup(path: Path) -> bool:
    """Create a shortcut in the Windows Startup folder (SPEC.md §6.4).

    Uses a PowerShell one-liner to create a .lnk file, avoiding a
    dependency on pywin32's win32com at this stage.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if getattr(sys, "frozen", False):
        target = sys.executable
        args = ""
    else:
        target = sys.executable
        args = "-m openfortitray"

    # Build .lnk via PowerShell
    ps_script = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$lnk = $ws.CreateShortcut("{path}"); '
        f'$lnk.TargetPath = "{target}"; '
    )
    if args:
        ps_script += f'$lnk.Arguments = "{args}"; '
    ps_script += f'$lnk.WorkingDirectory = "{path.parent}"; $lnk.Save()'

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            check=True,
            capture_output=True,
            timeout=10,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        logger.info("Installed Windows startup shortcut: %s", path)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.error("Could not create Windows startup shortcut: %s", e)
        return False
