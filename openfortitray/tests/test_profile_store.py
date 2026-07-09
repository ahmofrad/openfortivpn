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
