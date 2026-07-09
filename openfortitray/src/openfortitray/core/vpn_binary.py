"""Locate the openfortivpn binary (SPEC.md §11).

Priority:
  1. Explicit override (from AppSettings)
  2. Bundled alongside this app (PyInstaller output / next to exe)
  3. Current working directory
  4. System PATH lookup
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def find_binary(override: str | None = None) -> str | None:
    """Locate the openfortivpn binary."""
    exe_name = "openfortivpn.exe" if sys.platform == "win32" else "openfortivpn"

    # 1. Explicit override
    if override and Path(override).is_file():
        return override

    # 2. PyInstaller frozen: binary next to the exe
    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).parent
        candidates = [
            app_dir / exe_name,
            app_dir / "_internal" / exe_name,
        ]
    else:
        # 3. Dev mode: check packaging/vendor/<os>/ and alongside __file__
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        os_name = "windows" if sys.platform == "win32" else (
            "macos" if sys.platform == "darwin" else "linux"
        )
        candidates = [
            repo_root / "packaging" / "vendor" / os_name / exe_name,
            repo_root / "packaging" / "vendor" / os_name / "bin" / exe_name,
        ]

    # Also check current working directory
    candidates.append(Path.cwd() / exe_name)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    # 4. System PATH
    return shutil.which("openfortivpn")
