"""Keyring-backed secret storage (AUTH.md §2/§3/§4).

Stores passwords and OTP seeds in the OS's native credential store:
  - Windows Credential Locker
  - macOS Keychain
  - Linux Secret Service (gnome-keyring / kwallet)

Detects the "no backend available" fallback and warns explicitly (AUTH.md §2).
"""

from __future__ import annotations

import logging
from typing import Literal

import keyring

logger = logging.getLogger(__name__)

SERVICE_NAME = "OpenFortiTray"


class SecretStoreError(Exception):
    """Raised when secret storage is unavailable or an operation fails."""


class NoKeyringBackendError(SecretStoreError):
    """Raised when no usable keyring backend is available (AUTH.md §2)."""


def check_backend() -> Literal["ok", "failback", "null"]:
    """Check the active keyring backend.

    Returns:
        "ok" -- a real backend (Windows Credential Locker, macOS Keychain, etc.)
        "failback" -- the encrypted-file chainer fallback
        "null" -- the no-op null backend (plaintext refused)
    """
    kr = keyring.get_keyring()
    name = type(kr).__module__ + "." + type(kr).__qualname__

    if "fail.Keyring" in name or "chainer" in name.lower():
        logger.warning("Keyring is using the encrypted-file fallback backend.")
        return "failback"
    if "backends.null" in name or type(kr).__name__ == "NullKeyring":
        logger.error("No usable keyring backend found (null backend active).")
        return "null"
    return "ok"


class SecretStore:
    """Thin wrapper around the keyring library for password/OTP seed storage."""

    def __init__(self) -> None:
        backend_status = check_backend()
        if backend_status == "null":
            raise NoKeyringBackendError(
                "No usable keyring backend found. On Linux, install "
                "gnome-keyring or kwallet. Secrets cannot be stored safely."
            )
        self._backend_status = backend_status

    @property
    def backend_status(self) -> str:
        return self._backend_status

    @property
    def is_fallback(self) -> bool:
        return self._backend_status == "failback"

    # ── Password ───────────────────────────────────────────────

    @staticmethod
    def _password_key(profile_id: str) -> str:
        return f"{profile_id}:password"

    def set_password(self, profile_id: str, password: str) -> str:
        """Store a password and return the keyring reference key."""
        key = self._password_key(profile_id)
        keyring.set_password(SERVICE_NAME, key, password)
        return key

    def get_password(self, profile_id: str) -> str | None:
        """Retrieve a stored password, or None if not set."""
        return keyring.get_password(SERVICE_NAME, self._password_key(profile_id))

    def delete_password(self, profile_id: str) -> None:
        """Delete a stored password. No-op if not found."""
        try:
            keyring.delete_password(SERVICE_NAME, self._password_key(profile_id))
        except keyring.errors.PasswordDeleteError:
            pass

    # ── OTP Seed ───────────────────────────────────────────────

    @staticmethod
    def _seed_key(profile_id: str) -> str:
        return f"{profile_id}:otp_seed"

    def set_otp_seed(self, profile_id: str, seed: str) -> str:
        """Store an OTP seed (Base32 string) and return the keyring reference."""
        key = self._seed_key(profile_id)
        keyring.set_password(SERVICE_NAME, key, seed)
        return key

    def get_otp_seed(self, profile_id: str) -> str | None:
        """Retrieve a stored OTP seed, or None if not set."""
        raw = keyring.get_password(SERVICE_NAME, self._seed_key(profile_id))
        if raw is None:
            return None
        return parse_seed_input(raw)

    def delete_otp_seed(self, profile_id: str) -> None:
        """Delete a stored OTP seed. No-op if not found."""
        try:
            keyring.delete_password(SERVICE_NAME, self._seed_key(profile_id))
        except keyring.errors.PasswordDeleteError:
            pass

    # ── Bulk cleanup ───────────────────────────────────────────

    def delete_all_for_profile(self, profile_id: str) -> None:
        """Remove all secrets associated with a profile (for deletion)."""
        self.delete_password(profile_id)
        self.delete_otp_seed(profile_id)


def parse_seed_input(raw: str) -> str:
    """Extract the Base32 seed from user input.

    Accepts:
      - A raw Base32 string (e.g., GEZDGNBVGY3TQOJQ...)
      - An otpauth:// URI with a secret= parameter (AUTH.md §4)
    """
    raw = raw.strip()

    if raw.lower().startswith("otpauth://"):
        from urllib.parse import parse_qs, urlsplit

        qs = parse_qs(urlsplit(raw).query)
        secrets = qs.get("secret", [])
        if secrets:
            return secrets[0]
        raise ValueError("otpauth:// URI missing 'secret' parameter")

    return raw
