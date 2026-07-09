"""Non-secret profile persistence to JSON (SPEC.md §5).

Secrets (passwords, OTP seeds) are never stored here -- only references
to OS keyring entries. See AUTH.md §3/§4.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from openfortitray.core.profile import AppSettings, VpnProfile


def _default_config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(base) / "OpenFortiTray"
    return Path.home() / ".config" / "openfortitray"


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
        self._profiles = self._load_json_list(
            self.profiles_file, VpnProfile, "profiles"
        )
        self._settings = self._load_json_obj(
            self.settings_file, AppSettings, "settings"
        )

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._save_json_list(self.profiles_file, self._profiles)
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

    def _load_json_list(
        self, path: Path, cls: type, label: str
    ) -> list[VpnProfile]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        result: list[VpnProfile] = []
        for item in data:
            if isinstance(item, dict):
                result.append(self._dict_to_profile(item))
        return result

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

    def _save_json_list(self, path: Path, profiles: list[VpnProfile]) -> None:
        data = [self._profile_to_dict(p) for p in profiles]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _save_json_obj(self, path: Path, settings: AppSettings) -> None:
        data = self._settings_to_dict(settings)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
