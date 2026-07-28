"""Unit tests for profile store round-trips (SPEC.md §12)."""

from pathlib import Path
from tempfile import TemporaryDirectory

from openfortitray.core.profile import VpnProfile
from openfortitray.core.profile_store import ProfileStore


def test_save_and_load_profile():
    with TemporaryDirectory() as tmpdir:
        store = ProfileStore(Path(tmpdir))
        profile = VpnProfile(
            name="Test VPN",
            host="vpn.example.com",
            port=8443,
            username="alice",
        )
        store.add_profile(profile)

        store2 = ProfileStore(Path(tmpdir))
        store2.load()
        assert len(store2.profiles) == 1
        p = store2.profiles[0]
        assert p.name == "Test VPN"
        assert p.host == "vpn.example.com"
        assert p.port == 8443
        assert p.username == "alice"
        assert p.id == profile.id


def test_update_profile():
    with TemporaryDirectory() as tmpdir:
        store = ProfileStore(Path(tmpdir))
        profile = VpnProfile(name="Old Name", host="vpn.example.com")
        store.add_profile(profile)

        profile.name = "New Name"
        store.update_profile(profile)

        store2 = ProfileStore(Path(tmpdir))
        store2.load()
        assert len(store2.profiles) == 1
        assert store2.profiles[0].name == "New Name"


def test_delete_profile():
    with TemporaryDirectory() as tmpdir:
        store = ProfileStore(Path(tmpdir))
        p1 = VpnProfile(name="VPN 1", host="vpn1.example.com")
        p2 = VpnProfile(name="VPN 2", host="vpn2.example.com")
        store.add_profile(p1)
        store.add_profile(p2)

        store.delete_profile(p1.id)

        store2 = ProfileStore(Path(tmpdir))
        store2.load()
        assert len(store2.profiles) == 1
        assert store2.profiles[0].id == p2.id


def test_secrets_not_in_json():
    with TemporaryDirectory() as tmpdir:
        store = ProfileStore(Path(tmpdir))
        profile = VpnProfile(
            name="Test VPN",
            host="vpn.example.com",
            password_ref="some-keyring-key",
            otp_seed_ref="another-keyring-key",
        )
        store.add_profile(profile)

        json_content = store.profiles_file.read_text()
        assert "some-keyring-key" in json_content
        # But no actual secrets (password_ref is just a reference, not the secret)
        assert "password =" not in json_content.replace("password_ref", "")
        assert "mypassword" not in json_content


def test_validate_profile():
    p = VpnProfile(name="", host="")
    errors = p.validate()
    assert len(errors) == 2

    p2 = VpnProfile(name="OK", host="vpn.example.com", port=99999)
    errors2 = p2.validate()
    assert len(errors2) == 1


def test_legacy_format_migration():
    """Legacy bare-list profiles.json (v0) loads and migrates transparently."""
    import json

    with TemporaryDirectory() as tmpdir:
        legacy = [{
            "id": "abc-123",
            "name": "Legacy VPN",
            "host": "vpn.old.com",
            "port": 443,
            "username": "bob",
            "auth_mode": "password_otp_manual",
            "password_ref": None,
            "otp_seed_ref": None,
        }]
        store = ProfileStore(Path(tmpdir))
        store.profiles_file.write_text(json.dumps(legacy))

        store.load()
        assert len(store.profiles) == 1
        p = store.profiles[0]
        assert p.id == "abc-123"
        assert p.name == "Legacy VPN"
        # password_otp_manual migrated to password
        assert p.auth_mode == "password"


def test_versioned_format_roundtrip():
    """New versioned envelope saves and loads correctly."""
    import json

    with TemporaryDirectory() as tmpdir:
        store = ProfileStore(Path(tmpdir))
        store.add_profile(VpnProfile(name="Test", host="vpn.example.com"))

        # Check the file has the version envelope
        data = json.loads(store.profiles_file.read_text())
        assert data["schema_version"] == 1
        assert isinstance(data["profiles"], list)
        assert len(data["profiles"]) == 1

        store2 = ProfileStore(Path(tmpdir))
        store2.load()
        assert len(store2.profiles) == 1
        assert store2.profiles[0].name == "Test"


def test_future_version_best_effort():
    """A file from a newer version loads best-effort with a warning."""
    import json

    with TemporaryDirectory() as tmpdir:
        future = {
            "schema_version": 99,
            "profiles": [{"id": "x", "name": "Future", "host": "vpn.new.com"}],
        }
        store = ProfileStore(Path(tmpdir))
        store.profiles_file.write_text(json.dumps(future))

        store.load()
        assert len(store.profiles) == 1
        assert store.profiles[0].name == "Future"


def test_malformed_profile_skipped():
    """Malformed entries are skipped without failing the whole load."""
    import json

    with TemporaryDirectory() as tmpdir:
        data = {
            "schema_version": 1,
            "profiles": [
                {"id": "ok", "name": "Good", "host": "vpn.example.com"},
                "not-a-dict",
                {"id": "also-ok", "name": "Good2", "host": "vpn2.example.com"},
            ],
        }
        store = ProfileStore(Path(tmpdir))
        store.profiles_file.write_text(json.dumps(data))

        store.load()
        assert len(store.profiles) == 2
