"""Non-secret profile persistence to JSON (SPEC.md §5).

Secrets (passwords, OTP seeds) are never stored here -- only references
to OS keyring entries. See AUTH.md §3/§4.

Supports schema versioning: profiles.json is a versioned envelope
{"schema_version": N, "profiles": [...]}. Legacy bare-list files
(version 0) are migrated transparently.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from openfortitray.core.profile import AppSettings, VpnProfile

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1


def _default_config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(base) / "OpenFortiTray"
    return Path.home() / ".config" / "openfortitray"


def _migrate_profile_dict(d: dict, from_version: int) -> dict:
    """Migrate a single profile dict from an older schema version.

    from_version 0 = legacy bare-list format (no envelope).
    Each migration step is one-way; new fields get defaults.
    """
    migrated = dict(d)

    if from_version < 1:
        # v0 -> v1: auth_mode "password_otp_manual" is no longer used;
        # treat as "password" (OTP prompt is now reactive).
        if migrated.get("auth_mode") == "password_otp_manual":
            migrated["auth_mode"] = "password"

    return migrated


class ProfileStore:
    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or _default_config_dir()
        self.profiles_file = self.config_dir / "profiles.json"
        self.settings_file = self.config_dir / "settings.json"
        self._profiles: list[VpnProfile] = []
        self._settings = AppSettings()

    @property
    def profiles(self) -> list[VpnProfile]:
        return self._profiles

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def load(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._profiles = self._load_profiles()
        self._settings = self._load_json_obj(
            self.settings_file, AppSettings, "settings"
        )

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._save_profiles()
        self._save_json_obj(self.settings_file, self._settings)

    def get_profile(self, profile_id: str) -> VpnProfile | None:
        for p in self._profiles:
            if p.id == profile_id:
                return p
        return None

    def add_profile(self, profile: VpnProfile) -> None:
        self._profiles.append(profile)
        self.save()

    def update_profile(self, profile: VpnProfile) -> None:
        for i, p in enumerate(self._profiles):
            if p.id == profile.id:
                profile.touch()
                self._profiles[i] = profile
                self.save()
                return
        self._profiles.append(profile)
        self.save()

    def delete_profile(self, profile_id: str) -> None:
        self._profiles = [p for p in self._profiles if p.id != profile_id]
        self.save()

    # ── internals ──────────────────────────────────────────────

    def _load_profiles(self) -> list[VpnProfile]:
        """Load profiles, handling legacy (bare list) and versioned formats."""
        if not self.profiles_file.exists():
            return []
        try:
            data = json.loads(self.profiles_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read profiles.json: %s", e)
            return []

        # Detect format
        if isinstance(data, list):
            # Legacy v0: bare list of profiles
            version = 0
            raw_profiles = data
        elif isinstance(data, dict) and "profiles" in data:
            version = data.get("schema_version", 0)
            raw_profiles = data["profiles"]
            if not isinstance(raw_profiles, list):
                logger.warning("profiles.json: 'profiles' is not a list")
                return []
        else:
            logger.warning("profiles.json: unrecognized format")
            return []

        if version > CURRENT_SCHEMA_VERSION:
            logger.warning(
                "profiles.json schema version %d is newer than supported %d; "
                "loading best-effort",
                version, CURRENT_SCHEMA_VERSION,
            )

        result: list[VpnProfile] = []
        for item in raw_profiles:
            if not isinstance(item, dict):
                continue
            try:
                migrated = _migrate_profile_dict(item, version)
                result.append(self._dict_to_profile(migrated))
            except Exception as e:
                logger.warning("Skipping malformed profile entry: %s", e)

        return result

    def _save_profiles(self) -> None:
        data = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "profiles": [self._profile_to_dict(p) for p in self._profiles],
        }
        self.profiles_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _profile_to_dict(p: VpnProfile) -> dict:
        d: dict = {}
        for f in p.__dataclass_fields__:
            val = getattr(p, f)
            if isinstance(val, datetime):
                d[f] = val.isoformat()
            else:
                d[f] = val
        return d

    @staticmethod
    def _dict_to_profile(d: dict) -> VpnProfile:
        kwargs: dict = {}
        for f in VpnProfile.__dataclass_fields__:
            if f in d:
                val = d[f]
                if f in ("created_at", "updated_at") and isinstance(val, str):
                    val = datetime.fromisoformat(val)
                kwargs[f] = val
        return VpnProfile(**kwargs)

    @staticmethod
    def _settings_to_dict(s: AppSettings) -> dict:
        return {f: getattr(s, f) for f in s.__dataclass_fields__}

    @staticmethod
    def _dict_to_settings(d: dict) -> AppSettings:
        kwargs = {k: v for k, v in d.items() if k in AppSettings.__dataclass_fields__}
        return AppSettings(**kwargs)

    def _load_json_obj(
        self, path: Path, cls: type, label: str
    ) -> AppSettings:
        if not path.exists():
            return AppSettings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return AppSettings()
        if not isinstance(data, dict):
            return AppSettings()
        return self._dict_to_settings(data)

    def _save_json_obj(self, path: Path, settings: AppSettings) -> None:
        data = self._settings_to_dict(settings)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
