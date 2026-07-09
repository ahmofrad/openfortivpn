"""Unit tests for secret store (AUTH.md §3/§4).

Uses keyring's built-in test backend to avoid touching real OS keyrings.
"""

import keyring.backend
from openfortitray.core.secret_store import SecretStore, parse_seed_input


class InMemoryKeyring(keyring.backend.KeyringBackend):
    """A simple in-memory keyring for testing."""

    priority = 1

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, servicename, username, password):
        self._store[(servicename, username)] = password

    def get_password(self, servicename, username):
        return self._store.get((servicename, username))

    def delete_password(self, servicename, username):
        try:
            del self._store[(servicename, username)]
        except KeyError:
            raise keyring.errors.PasswordDeleteError


def setup_keyring():
    """Install the in-memory keyring backend."""
    kr = InMemoryKeyring()
    keyring.set_keyring(kr)
    return kr


PROFILE_ID = "test-profile-123"


def test_set_and_get_password():
    setup_keyring()
    store = SecretStore()
    store.set_password(PROFILE_ID, "s3cret")
    assert store.get_password(PROFILE_ID) == "s3cret"


def test_get_password_none_if_not_set():
    setup_keyring()
    store = SecretStore()
    assert store.get_password(PROFILE_ID) is None


def test_delete_password():
    setup_keyring()
    store = SecretStore()
    store.set_password(PROFILE_ID, "s3cret")
    store.delete_password(PROFILE_ID)
    assert store.get_password(PROFILE_ID) is None


def test_delete_password_idempotent():
    setup_keyring()
    store = SecretStore()
    store.delete_password(PROFILE_ID)  # should not raise


def test_set_and_get_otp_seed():
    setup_keyring()
    store = SecretStore()
    store.set_otp_seed(PROFILE_ID, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")
    assert store.get_otp_seed(PROFILE_ID) == "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def test_delete_otp_seed():
    setup_keyring()
    store = SecretStore()
    store.set_otp_seed(PROFILE_ID, "GEZDGNBVGY3TQOJQ")
    store.delete_otp_seed(PROFILE_ID)
    assert store.get_otp_seed(PROFILE_ID) is None


def test_delete_all_for_profile():
    setup_keyring()
    store = SecretStore()
    store.set_password(PROFILE_ID, "pass")
    store.set_otp_seed(PROFILE_ID, "seed")
    store.delete_all_for_profile(PROFILE_ID)
    assert store.get_password(PROFILE_ID) is None
    assert store.get_otp_seed(PROFILE_ID) is None


def test_parse_raw_base32():
    assert parse_seed_input("GEZDGNBVGY3TQOJQ") == "GEZDGNBVGY3TQOJQ"


def test_parse_otpauth_uri():
    uri = "otpauth://totp/Snapp:alice?secret=GEZDGNBVGY3TQOJQ&issuer=Snapp"
    assert parse_seed_input(uri) == "GEZDGNBVGY3TQOJQ"


def test_parse_otpauth_missing_secret():
    import pytest

    uri = "otpauth://totp/Snapp:alice?issuer=Snapp"
    with pytest.raises(ValueError):
        parse_seed_input(uri)


def test_parse_trims_whitespace():
    assert parse_seed_input("  GEZDGNBVGY3TQOJQ  ") == "GEZDGNBVGY3TQOJQ"
