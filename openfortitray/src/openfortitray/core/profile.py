"""VpnProfile dataclass and validation (SPEC.md §5)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class VpnProfile:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    host: str = ""  # comma-separated list of hosts (e.g. "host1,host2:8443")
    port: int = 443
    username: str = ""
    realm: str = ""

    # Auth
    auth_mode: Literal["password", "password_otp_manual", "password_otp_seed"] = "password"
    password_ref: str | None = None
    otp_seed_ref: str | None = None
    no_ftm_push: bool = False

    # Certificate trust
    trusted_cert_sha256: list[str] = field(default_factory=list)
    insecure_ssl: bool = True
    ca_file: str | None = None

    # Routing / DNS -- Advanced, collapsed by default
    set_routes: bool = True
    half_internet_routes: bool = False
    set_dns: bool = True
    use_resolvconf: bool = True
    pppd_use_peerdns: bool = False
    ifname: str | None = None

    # Reconnect
    auto_reconnect: bool = True
    reconnect_interval_seconds: int = 5

    # App-level
    connect_on_launch: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name.strip():
            errors.append("Name is required.")
        if not self.host.strip():
            errors.append("Host is required.")
        if not (1 <= self.port <= 65535):
            errors.append("Port must be between 1 and 65535.")
        return errors

    def get_host_list(self) -> list[tuple[str, int]]:
        """Parse the host field into (host, port) pairs.

        Supports comma-separated entries. Each entry can optionally
        include a port (host:port). Entries without a port use the
        profile's default port.
        """
        result: list[tuple[str, int]] = []
        for part in self.host.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                h, _, p = part.rpartition(":")
                try:
                    port = int(p)
                except ValueError:
                    port = self.port
                result.append((h.strip(), port))
            else:
                result.append((part, self.port))
        return result


@dataclass
class AppSettings:
    minimize_to_tray: bool = True
    launch_at_startup: bool = False
    start_minimized: bool = False
    theme: Literal["system", "light", "dark"] = "system"
    last_connected_profile_id: str | None = None
    vpn_binary_path: str | None = None
    log_level: Literal["error", "warn", "info", "debug"] = "info"
