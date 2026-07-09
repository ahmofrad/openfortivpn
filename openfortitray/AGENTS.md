# AGENTS.md

Orientation file for AI coding agents working in this repository. Read this file
first, in full -- it's short on purpose.

## What this is

A minimalist, cross-platform (Windows/Linux/macOS) GUI wrapper around the
`openfortivpn` CLI binary, built from the [`ahmofrad/openfortivpn`](https://github.com/ahmofrad/openfortivpn)
fork. The GUI manages VPN profiles and encrypted credentials; all VPN protocol work
(TLS, PPP, routing, DNS, TOTP generation) stays inside the binary. See `SPEC.md` §1
for the full framing.

The app is **fully built and working**. These docs describe the existing codebase,
not a future plan.

## Read next, in this order

1. **`SPEC.md`** -- architecture, VPN engine CLI integration, data model, feature
   specs, state machine, project structure, packaging.
2. **`AUTH.md`** -- how secrets, certificates, and privilege elevation are handled.
   **Read this before modifying any code that touches a password, an OTP seed, a
   certificate, or a subprocess that needs to run elevated.**
3. **`DESIGN.md`** and **`WIREFRAMES.md`** -- UI/UX design language and screen layouts.
4. **`DECISIONS.md`** -- why things are the way they are. Check here before
   overriding an existing decision.

## Non-negotiables

- Never pass a password or OTP seed as a CLI argument or in a log line -- always via
  the ephemeral config file (`AUTH.md` §7).
- The GUI process itself never runs elevated. Only the `openfortivpn` invocation
  does, via the per-OS mechanisms in `AUTH.md` §8.
- If you build the optional v2 privileged helper daemon, it must never forward
  arbitrary `--pppd-plugin` / `--pppd-log` values from an unprivileged request --
  this is a known privilege-escalation vector.

## Ground truth

This spec is grounded in the actual source of `ahmofrad/openfortivpn` -- flag names,
config syntax, log strings, and privilege requirements come from reading the source.
If the fork changes, re-verify against `doc/openfortivpn.1.in` and `src/main.c`.
