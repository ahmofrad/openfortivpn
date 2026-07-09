#!/usr/bin/env python3
"""Build OpenFortiTray with PyInstaller (SPEC.md §11).

Usage:
    python packaging/build.py [--os windows|linux|macos]

Prerequisites:
    pip install pyinstaller
    Place vendored openfortivpn binary + DLLs in packaging/vendor/<os>/

This script:
    1. Verifies vendored binaries exist
    2. Runs PyInstaller with the matching .spec file
    3. Reports the output directory
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = PROJECT_ROOT / "packaging"
VENDOR_BASE = PACKAGING_DIR / "vendor"

SPECS = {
    "windows": "openfortitray-windows.spec",
    "linux": "openfortitray-linux.spec",
    "macos": "openfortitray-macos.spec",
}

EXPECTED_FILES = {
    "windows": ["openfortivpn.exe", "wintun.dll"],
    "linux": ["openfortivpn"],
    "macos": ["openfortivpn"],
}


def detect_os() -> str:
    if sys.platform == "win32":
        return "windows"
    elif sys.platform == "darwin":
        return "macos"
    return "linux"


def check_vendor(target_os: str) -> list[str]:
    """Return list of missing vendored files."""
    vendor_dir = VENDOR_BASE / target_os
    expected = EXPECTED_FILES.get(target_os, [])
    missing = []
    for f in expected:
        if not (vendor_dir / f).is_file():
            missing.append(f)
    return missing


def run_build(target_os: str) -> int:
    spec_file = PACKAGING_DIR / SPECS[target_os]

    if not spec_file.is_file():
        print(f"ERROR: spec file not found: {spec_file}")
        return 1

    missing = check_vendor(target_os)
    if missing:
        print(f"WARNING: missing vendored binaries in packaging/vendor/{target_os}/:")
        for f in missing:
            print(f"  - {f}")
        print("The app will fall back to system PATH lookup at runtime.")
        print()

    if not shutil.which("pyinstaller"):
        print("ERROR: pyinstaller not found. Install with: pip install pyinstaller")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_file),
        "--noconfirm",
        "--distpath",
        str(PROJECT_ROOT / "dist"),
        "--workpath",
        str(PROJECT_ROOT / "build"),
    ]

    print(f"Building for {target_os}: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode == 0:
        output_dir = PROJECT_ROOT / "dist" / "OpenFortiTray"
        print()
        print(f"Build successful! Output: {output_dir}")
        print()
        print("To run:")
        exe = "OpenFortiTray.exe" if target_os == "windows" else "openfortitray"
        print(f"  {output_dir / exe}")

    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Build OpenFortiTray")
    parser.add_argument(
        "--os",
        choices=["windows", "linux", "macos"],
        default=detect_os(),
        help=f"Target OS (default: {detect_os()})",
    )
    args = parser.parse_args()
    return run_build(args.os)


if __name__ == "__main__":
    sys.exit(main())
