# TASKS.md -- Build Checklist

All phases complete. This file is retained as a record of the build process.

## Phase 0 -- Scaffolding [x]
- [x] Project skeleton, pyproject.toml, requirements.txt
- [x] Build openfortivpn from the fork, confirmed it runs

## Phase 1 -- Core loop [x]
- [x] VpnProfile dataclass + JSON store
- [x] Minimal window: profile list + Connect button
- [x] Connection manager: temp config file, launch, state machine
- [x] State machine wired to log-line triggers
- [x] Verified against a real gateway

## Phase 2 -- Secure storage [x]
- [x] Keyring integration for passwords
- [x] OTP seed storage + `--otp-seed-file` wiring
- [x] No-keyring-backend detection and warning
- [x] No plaintext secret code paths

## Phase 3 -- Tray & lifecycle [x]
- [x] QSystemTrayIcon with state-based colored icons
- [x] Minimize-to-tray on close
- [x] Startup/autostart registration (Linux .desktop, macOS, Windows)
- [x] Settings dialog

## Phase 4 -- Cross-platform elevation [x]
- [x] Linux: pkexec with direct pipe
- [x] macOS: osascript with log-file polling
- [x] Windows: ShellExecute runas with log-file polling
- [x] Windows graceful shutdown via taskkill /IM with CREATE_NO_WINDOW

## Phase 5 -- Certificate trust & advanced settings [x]
- [x] Certificate auto-fetch on connect (no TOFU dialog)
- [x] trusted-cert, insecure-ssl, ca-file in Advanced tab
- [x] Routing/DNS advanced fields
- [x] Reconnect: --persistent mapping + GUI backstop retry

## Phase 6 -- Packaging [x]
- [x] Single-file PyInstaller spec (--onefile, no _internal folder)
- [x] Aggressive PySide6 module excludes
- [x] Vendored binary placement alongside exe
- [x] App icon (shield + padlock)

## Phase 7 -- Nice-to-haves [x]
- [x] Desktop notifications on state change
- [x] Diagnostics/log panel with severity filter
- [x] Sleep/wake-aware reconnect
- [x] Profile export/import
- [x] Create shortcut button
- [x] Multi-host support with sequential fallback
- [x] Single-instance guard (named mutex + signal file)
- [x] Interactive password/OTP prompts
- [x] Thread-safe signal bridge

## Future / Not built
- [ ] Privileged helper daemon (v2 elevation)
- [ ] SAML/SSO login
- [ ] Persian/RTL localization
- [ ] Code signing / notarization
