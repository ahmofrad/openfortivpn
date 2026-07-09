# DESIGN.md -- UI/UX Design Language

See `WIREFRAMES.md` for concrete screen layouts.

## 1. Design Principles

- **One click for the common path.** Pick a profile from the dropdown, click Connect.
- **Progressive disclosure.** Basic fields visible by default; realm, routing/DNS,
  reconnect tuning behind an "Advanced" tab.
- **No blocking modals during connect.** Status shows in the status line. The only
  modal interruptions are OS elevation prompts and credential/OTP dialogs when needed.
- **Native look and feel.** Qt's platform styling per OS.

## 2. Visual Language

- **Palette:** Qt's native system palette (light/dark aware). State color-coding:

  | State | Color |
  |---|---|
  | Disconnected | Gray |
  | Connecting / Reconnecting | Amber |
  | Connected | Green |
  | Error / Auth failure | Red |

- **Window:** Fixed size (360x105, no resize, no maximize). Expands to 360x300 when
  log panel is toggled.
- **Typography:** System default font per OS.
- **Iconography:** App icon is a dark blue shield with teal padlock. Tray icon uses
  dynamically drawn colored circles per state.

## 3. Screen Inventory

- Main window (profile dropdown + buttons + status)
- Profile editor -- Basic tab (name, hosts, port, username, password, OTP)
- Profile editor -- Advanced tab (realm, cert, routing/DNS, reconnect)
- Settings dialog (startup, theme, log level)
- Tray icon + context menu
- Password prompt dialog (interactive)
- OTP prompt dialog (reactive)

## 4. Interaction Patterns

- Profile dropdown selects the active VPN. Add/Edit/Delete buttons manage profiles.
- Import/Export buttons for backup/restore.
- Settings button opens settings dialog.
- Log button toggles a diagnostics panel.
- Confirm before deleting a profile.
- Create Shortcut button in profile editor creates a `.lnk` that launches with
  `--connect <profile_id>`.

## 5. Platform-Native Considerations

- **Windows:** tray icon in notification area. `ShellExecuteEx(runas)` for elevation.
  `taskkill /IM` with `CREATE_NO_WINDOW` for disconnect.
- **macOS:** tray icon in menu bar (monochrome template).
- **Linux/GNOME:** may need AppIndicator extension for tray visibility.
