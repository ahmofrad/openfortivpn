# OpenFortiTray

A minimalist, cross-platform desktop GUI for
[`openfortivpn`](https://github.com/ahmofrad/openfortivpn)
(Windows, Linux, macOS).

Wraps the `openfortivpn` CLI with a small tray-first app: manage multiple VPN
profiles, store passwords and OTP seeds encrypted in your OS's native credential
store, connect with one click, reconnect automatically on drop, and stay out of
the way in the system tray.

## Features

- Multiple VPN profiles with multi-host fallback
- Encrypted password storage (OS keyring)
- Encrypted OTP seed storage with automatic TOTP generation (RFC 6238)
- Interactive OTP prompt when the gateway requires 2FA
- Automatic reconnect with configurable retry interval
- Minimize to tray, launch at startup
- Certificate trust (auto-fetched, pinned)
- Profile import/export for backup
- Create desktop shortcuts for one-click VPN connection
- Diagnostics log panel with adjustable severity

## Requirements

- The `openfortivpn` binary, built from the
  [`ahmofrad/openfortivpn`](https://github.com/ahmofrad/openfortivpn) fork
  (bundled with the app)
- Windows 10+, or a Linux desktop with D-Bus, or macOS
- Administrator/root privileges at connect time

## Development

```shell
pip install -e ".[dev]"
python -m openfortitray
```

## Packaging

```shell
# Place vendored binaries in packaging/vendor/<os>/
python packaging/build.py --os windows
```

Produces a single `OpenFortiTray.exe` in `dist/`. Place `openfortivpn.exe`,
`wintun.dll`, and MinGW runtime DLLs alongside it.

## Documentation

| File | Contents |
|---|---|
| `SPEC.md` | Functional and technical specification |
| `AUTH.md` | Credential storage, certificate trust, and privilege elevation |
| `DESIGN.md` | UI/UX design language |
| `WIREFRAMES.md` | Screen layouts |
| `DECISIONS.md` | Architecture decisions and rationale |
| `TASKS.md` | Build checklist |
| `AGENTS.md` | Orientation for AI coding agents |

## License

GPL-3.0
