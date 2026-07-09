# SPEC.md -- Functional & Technical Specification

---

## 1. Overview

A desktop application (Windows, Linux, macOS) that wraps the `openfortivpn` binary
from the `ahmofrad/openfortivpn` fork with a minimal GUI: manage VPN profiles, store
credentials encrypted, connect/disconnect with one click, live in the system tray,
and reconnect automatically on drop.

The app is a **supervisor and credential vault around the CLI binary**. All protocol
work stays inside `openfortivpn`.

## 2. Architecture

Two processes, separated by privilege level:

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│   GUI process (unprivileged) │         │  openfortivpn subprocess       │
│                               │         │  (elevated: root/sudo/Admin)   │
│  - Qt main window + tray     │  spawn  │                                │
│  - Profile dropdown + CRUD    │────────▶│  reads a per-connection        │
│  - keyring read/write         │  via    │  temp config file, opens the   │
│  - builds temp config file    │ platform│  tunnel, manages routes/DNS    │
│  - state machine + signal     │ (AUTH   │  natively                      │
│    bridge (thread-safe)       │  §8)    │                                │
│  - multi-host fallback        │◀────────│                                │
└─────────────────────────────┘         └──────────────────────────────┘
```

All UI updates from the reader thread go through a `SignalBridge` (Qt signals) to
ensure thread safety.

## 3. VPN Engine Integration

### 3.1 Config file format

Always invoked via `-c <file>` (never CLI args for secrets). Example:

```ini
host = vpn.example.com
port = 443
username = alireza
password = ***decrypted at connect time***
otp-seed-file = ***ephemeral path***
trusted-cert = e46d4aff08ba6914e64daa85bc6112a422fa7ce16631bff0b592a28556f993db
insecure-ssl = 1
set-dns = 1
set-routes = 1
persistent = 5
```

### 3.2 Log line triggers (state machine)

| String | State |
|---|---|
| `Tunnel is up and running.` / `Tunnel interface is UP.` / `Negotiation complete.` | Connected |
| `Closed connection to gateway.` | Disconnected |
| `Authentication failed` | AuthError |
| `This process requires administrator privileges.` | PermissionError |
| `Connected to gateway.` / `Authenticated.` / `Remote gateway has allocated a VPN.` | Connecting (progress) |
| `Please enter one-time password:` | Triggers OTP dialog |

### 3.3 Multi-host fallback

Profiles support comma-separated hosts. Each host can optionally include `:port`. On
connection error (not auth error), the app tries the next host automatically.

## 4. Data Model

```python
@dataclass
class VpnProfile:
    id: str                          # uuid4
    name: str                        # display name (required)
    host: str                        # comma-separated, e.g. "host1, host2:8443"
    port: int = 443                  # default port for hosts without explicit port
    username: str = ""
    realm: str = ""
    auth_mode: Literal["password", "password_otp_seed"] = "password"
    password_ref: str | None = None
    otp_seed_ref: str | None = None
    no_ftm_push: bool = False
    trusted_cert_sha256: list[str] = field(default_factory=list)
    insecure_ssl: bool = True        # defaults to True
    ca_file: str | None = None
    set_routes: bool = True
    half_internet_routes: bool = False
    set_dns: bool = True
    use_resolvconf: bool = True
    pppd_use_peerdns: bool = False
    ifname: str | None = None
    auto_reconnect: bool = True
    reconnect_interval_seconds: int = 5  # defaults to 5
    connect_on_launch: bool = False
    created_at: datetime
    updated_at: datetime

@dataclass
class AppSettings:
    minimize_to_tray: bool = True
    launch_at_startup: bool = False
    start_minimized: bool = False      # defaults to False
    theme: Literal["system", "light", "dark"] = "system"
    last_connected_profile_id: str | None = None
    vpn_binary_path: str | None = None
    log_level: Literal["error", "warn", "info", "debug"] = "info"
```

## 5. Features

- **Profile dropdown** -- single selection, one active connection at a time
- **Multi-host support** -- +/- buttons in editor, sequential fallback on error
- **OTP checkbox** -- if checked, seed field appears; if unchecked, fully hidden
- **Reactive OTP prompt** -- dialog appears only when gateway requests 2FA
- **Certificate auto-fetch** -- SHA-256 digest auto-pinned on first connect
- **Profile import/export** -- JSON backup with credentials
- **Create shortcut** -- `.lnk` that launches with `--connect <profile_id>`
- **Desktop notifications** -- tray messages on state change
- **Log panel** -- toggleable, with severity filter (Error/Warn/Info/Debug)
- **Sleep/wake reconnect** -- network reachability probe detects system wake
- **Single instance** -- second launch signals existing instance
- **Autostart** -- per-OS registration (Linux .desktop, macOS LaunchAgent, Windows shortcut)

## 6. Connection State Machine

```
Disconnected ──(Connect)──▶ Connecting
Connecting ──("Tunnel interface is UP.")──▶ Connected
Connecting ──(auth error)──▶ AuthError
Connecting ──(privilege error)──▶ PermissionError
Connecting ──(connection error + more hosts)──▶ Connecting (next host)
Connected ──("Closed connection.")──▶ Disconnected
```

## 7. Project Structure

```
openfortitray/
├── README.md  AGENTS.md  SPEC.md  AUTH.md  DESIGN.md  WIREFRAMES.md  DECISIONS.md
├── pyproject.toml
├── src/openfortitray/
│   ├── __main__.py
│   ├── app.py                       # QApplication bootstrap
│   ├── ui/
│   │   ├── main_window.py           # dropdown + buttons + status + log panel
│   │   ├── profile_editor.py        # Basic + Advanced tabs
│   │   ├── settings_dialog.py
│   │   ├── tray.py                  # tray icon with state colors
│   │   ├── log_viewer.py
│   │   ├── notifications.py
│   │   ├── credential_dialogs.py   # password + OTP prompts
│   │   ├── cert_trust_dialog.py
│   │   ├── signal_bridge.py        # thread-safe Qt signal bridge
│   │   └── resources/
│   ├── core/
│   │   ├── profile.py              # VpnProfile + AppSettings dataclasses
│   │   ├── profile_store.py        # JSON persistence
│   │   ├── secret_store.py         # keyring wrapper
│   │   ├── connection_manager.py   # subprocess lifecycle + config file
│   │   ├── elevation.py            # per-OS elevation dispatch
│   │   ├── state_machine.py
│   │   ├── vpn_binary.py
│   │   ├── cert_fetch.py
│   │   ├── autostart.py
│   │   ├── sleep_wake.py
│   │   └── single_instance.py
│   └── platform/
├── packaging/
│   ├── openfortitray-windows.spec   # single-file PyInstaller
│   ├── openfortitray-linux.spec
│   ├── openfortitray-macos.spec
│   ├── build.py
│   ├── generate_icon.py
│   └── vendor/
└── tests/
    ├── test_state_machine.py
    ├── test_profile_store.py
    └── test_secret_store.py
```

## 8. Dependencies

```
PySide6>=6.7
keyring>=25.0
```

No TOTP library. No HTTP libraries for core flow.

## 9. Packaging

Single-file PyInstaller (`--onefile`) with aggressive excludes for unused PySide6
modules. Produces `OpenFortiTray.exe`. Vendored binaries (`openfortivpn.exe`,
`wintun.dll`, MinGW DLLs) are placed alongside the exe after build.
