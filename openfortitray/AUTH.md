# AUTH.md -- Credentials, Certificate Trust & Privilege Elevation

This file documents how secrets, trust, and elevated privileges are handled in the
built app. Read it before modifying any code that touches a password, an OTP seed,
a certificate, or a subprocess that needs to run elevated.

---

## 1. Overview

Three secrets/trust concerns, each handled differently:
- **Password** -- stored encrypted in OS keyring, decrypted only in memory at connect
  time (§3).
- **OTP seed** -- stored encrypted; TOTP code generation happens natively inside the
  `openfortivpn` binary, not in this app (§4). Interactive OTP prompts appear
  reactively when the gateway requests 2FA.
- **Gateway certificate trust** -- auto-fetched on first connect, pinned by SHA-256
  digest. No TOFU dialog or user confirmation needed (§6).

Plus the mechanics: how secrets reach the subprocess (§7) and how the subprocess
gets elevated privileges (§8).

## 2. Threat Model

What this design protects against: another user on a shared machine reading your
VPN password off disk; a stolen backup of the app's config directory leaking secrets
(it won't contain any); casual inspection via `ps`/Task Manager while connecting
(secrets never appear there).

What it does **not** protect against: a malicious or compromised process running as
*your own* OS user while your session is unlocked. OS keyring backends generally
scope access by OS user, not by sandboxing every individual process. This protects
secrets at rest, not from every possible process running as you.

If a keyring backend isn't available (common on headless Linux), the `keyring`
library falls back to an encrypted-file backend, and ultimately to a no-op `null`
backend. **This is detected explicitly at startup** (`check_backend()`) and the user
is warned.

## 3. Password Storage

Uses the `keyring` PyPI package, service name `OpenFortiTray`, key
`f"{profile.id}:password"`. Store/retrieve with `keyring.set_password()` /
`keyring.get_password()`. Delete the entry when its profile is deleted.

A "Remember" checkbox per profile; unchecked means the password is not saved to
keyring and the user is prompted interactively at connect time via a dialog.

Password is decrypted from keyring into memory only when a connection attempt
starts, written into the ephemeral config file (§7), and never held in memory longer
than that scope needs.

## 4. OTP Seed Storage & TOTP Generation

Same keyring pattern as §3, key `f"{profile.id}:otp_seed"`.

TOTP generation is native to the fork's binary (`src/totp.c` -- RFC 6238, HMAC-SHA1,
30-second step, 6 digits). This app does **not** need its own TOTP library. It stores
the Base32 seed and hands it to the binary via `--otp-seed-file` at connect time.

The OTP checkbox in the profile editor controls whether OTP is used. If checked and
a seed is saved, codes are generated automatically. If the gateway requests OTP but
no seed is configured, a reactive dialog appears (see §4b).

Accepts either a raw Base32 string or an `otpauth://` URI (parses out `secret=`).

### 4b. Interactive OTP Prompt

When the gateway sends `"Please enter one-time password:"` in its log output, the app
shows an `OtpPromptDialog`. On Linux, the entered code is written to the process
stdin. On Windows (where stdin can't reach the elevated process), the current process
is killed, `otp = <code>` is written into the config, and the process relaunches.

## 5. The Tradeoff of Storing an OTP Seed

Storing a TOTP seed lets the app auto-generate 2FA codes indefinitely. Anyone with
access to both the keyring and the unlocked OS session has a durable bypass of the
"something you have" property. This is a reasonable tradeoff for a personal, trusted
machine.

## 6. Certificate Trust -- Auto-Fetch

Certificates are **auto-fetched on first connect** with no user dialog. The app opens
a raw TLS connection to `host:port` (Python `ssl` module, verification disabled for
this inspection only), reads the peer certificate, computes its SHA-256 digest, and
adds it to `trusted_cert_sha256`. On subsequent connects, the stored digest is used
directly.

`--insecure-ssl` defaults to True (enabled) and is exposed as an Advanced toggle.
This relaxes TLS protocol/cipher restrictions, which is separate from certificate
trust.

## 7. Secret Handling at Connect Time -- The Ephemeral Config File

Never passes `--password=` or `--otp-seed=` as CLI arguments. Always writes a
per-connection config file with mode `0600` and invokes with `-c <file>`.

**OTP seed gets its own file.** The decrypted seed is written to its own `0600` temp
file, referenced from the main config via `otp-seed-file = <path>`, and deleted when
the subprocess exits.

On Windows, the temp directory path is converted to its long (non-8.3) form via
`GetLongPathNameW` to ensure the elevated process can find the files.

## 8. Privilege Elevation Architecture

`openfortivpn` requires root/Administrator. The GUI process itself never runs
elevated -- only the `openfortivpn` invocation does.

| OS | Elevation | Output capture |
|---|---|---|
| Linux | `pkexec` | Direct pipe (stdout preserved) |
| macOS | `osascript "with administrator privileges"` | Log file + PID file polling |
| Windows | `ShellExecuteEx(runas)` via batch wrapper | Log file + exit-code file polling |

On Windows, the wrapper batch file writes its own PID, runs `openfortivpn.exe` with
output redirected to a log file, then writes the exit code. The GUI determines
process liveness by checking whether the exit-code file exists (not by querying the
PID, which may be inaccessible cross-user).

Termination uses `taskkill /IM openfortivpn.exe /F` (kill by image name) with
`CREATE_NO_WINDOW` to avoid flashing console windows.

**v2 option (future):** a privileged helper daemon (systemd/launchd/Task Scheduler)
to eliminate per-connection prompts. Not yet built.

## 9. Security Checklist

- [x] Secrets live only in the OS keyring -- never in the profile JSON, logs, or
      crash reports.
- [x] Config files are per-connection, `0600`, deleted when the subprocess exits.
- [x] OTP seed written to its own ephemeral file.
- [x] GUI process never runs elevated.
- [x] "No keyring backend available" is detected and surfaced.
- [x] No auto-update mechanism.
- [x] Process liveness on Windows uses exit-code file, not PID queries.
- [x] Thread-safe signal bridge prevents UI access from background threads.
