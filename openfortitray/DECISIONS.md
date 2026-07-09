# DECISIONS.md -- Architecture Decision Records

---

## ADR-001: Language & GUI toolkit

**Decision:** Python 3.11+ with PySide6 (Qt 6).

**Alternatives considered:** Electron, Tauri, Go + GTK4/libadwaita.

## ADR-002: Credential storage via OS keyring

**Decision:** Use the `keyring` PyPI package rather than hand-rolled encryption.

## ADR-003: Privilege elevation -- per-session prompt

**Decision:** Per-connection native elevation prompt (`pkexec` / `osascript` / UAC
`runas`). A helper daemon is a future v2 option.

## ADR-004: Certificate trust -- auto-fetch, not TOFU dialog

**Decision:** Certificates are auto-fetched on first connect and pinned by SHA-256
digest. No user-facing TOFU dialog or fingerprint list. `insecure_ssl` defaults to
True.

**Previous approach (superseded):** TOFU with a "Fetch Certificate" button and
confirmation dialog. Replaced because it added friction without meaningful security
benefit for the target users.

## ADR-005: Secrets only via generated config file

**Decision:** Never pass secrets as CLI arguments. Always use ephemeral `0600` config
files with `-c`.

## ADR-006: Single active connection

**Decision:** One profile connects at a time. Multi-host fallback within a profile
tries hosts sequentially on connection error.

## ADR-007: Packaging -- single-file PyInstaller

**Decision:** PyInstaller `--onefile` mode, producing a single `OpenFortiTray.exe`.
Aggressive excludes for unused PySide6 modules (Qt3D, WebEngine, Multimedia, QML,
etc.) to reduce size.

**Previous approach (superseded):** `--onedir` with a `_internal` folder. Replaced
with `--onefile` to eliminate the folder.

## ADR-008: No TOTP library -- generation stays in the binary

**Decision:** The GUI stores the seed; the `openfortivpn` binary generates codes.

## ADR-009: Log-file polling for elevated-process output

**Decision:** On macOS/Windows, elevated process output goes to a log file. Process
liveness is determined by checking for an exit-code file (not PID queries, which fail
cross-user). Linux's `pkexec` preserves stdio directly.

## ADR-010: Thread-safe signal bridge

**Decision:** All UI updates from the VPN reader thread go through Qt signals
(`SignalBridge`), not direct widget calls. Prevents crashes from cross-thread UI
access.

## ADR-011: Single-instance via named mutex

**Decision:** Windows uses `CreateMutexExW` + `GetLastError()`. Second instance
signals the first via a named event or temp file. Shortcuts with `--connect` write a
signal file and exit; the running instance picks it up within 500ms.

## ADR-012: Licensing

**Decision:** GPL-3.0 (matching the bundled `openfortivpn` binary).
