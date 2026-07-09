# WIREFRAMES.md -- Screen Layouts

Text-based layout sketches for each screen.

---

## Main Window (fixed 360x105)

```
┌──────────────────────────────────────────────────┐
│  OpenFortiTray                             [_][X] │
├──────────────────────────────────────────────────┤
│  VPN: [ Snapp HQ VPN          ▾ ]  [ Connect ]    │
│  [Add] [Edit] [Delete] [Import] [Export] [⚙] [Log]│
│  Status: Disconnected                             │
└──────────────────────────────────────────────────┘
```

Expands to 360x300 when Log is toggled:
```
┌──────────────────────────────────────────────────┐
│  ...main window content...                        │
│  ┌──────────────────────────────────────────────┐ │
│  │ Diagnostics         [√ Auto-scroll] [Copy]   │ │
│  │ INFO: Gateway IP: 79.127.120.184             │ │
│  │ INFO: Connected to gateway.                  │ │
│  │ ...                                          │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

## Profile Editor -- Basic Tab

```
┌──────────────────────────────────────────────────┐
│  Edit Profile                               [X]   │
├──────────────────────────────────────────────────┤
│  [ Basic ]  Advanced                              │
│                                                   │
│  Name *     [ Snapp HQ VPN                 ]      │
│                                                   │
│  Host(s):  [ ict-hq1.snapp.cab         ] [+]     │
│            [ ict-hq2.snapp.cab:8443    ] [-]     │
│            [ ict-hq3.snapp.cab          ] [-]     │
│                                                   │
│  Port       [ 10443 ]                             │
│  Username   [ alireza                     ]       │
│  Password   [ ************    ] [√ Remember]      │
│             [√] Use OTP (TOTP seed)               │
│  OTP Seed   [ ************                       ]│
│             Stored encrypted. Auto-generated.     │
│                                                   │
│  [Create Shortcut]              [Cancel] [Save]   │
└──────────────────────────────────────────────────┘
```

## Profile Editor -- Advanced Tab

```
┌──────────────────────────────────────────────────┐
│  Edit Profile                               [X]   │
├──────────────────────────────────────────────────┤
│   Basic  [ Advanced ]                             │
│                                                   │
│  Realm      [                   ]                 │
│  [√] Allow insecure TLS ciphers                   │
│  CA bundle  [                   ]                 │
│                                                   │
│  Routing & DNS                                    │
│  [√] Set routes through VPN                       │
│  [ ] Half-internet routes                         │
│  [√] Set DNS from gateway                         │
│  [ ] Use pppd peer DNS                            │
│  Bind interface  [              ]                 │
│                                                   │
│  Reconnect                                        │
│  [√] Reconnect automatically                      │
│  Retry interval [ 5 ] seconds                     │
│  [ ] Disable FTM push                             │
│  [ ] Connect automatically when app starts        │
│                                                   │
│  [Create Shortcut]              [Cancel] [Save]   │
└──────────────────────────────────────────────────┘
```

## Settings Dialog

```
┌──────────────────────────────────────────────────┐
│  Settings                                   [X]   │
├──────────────────────────────────────────────────┤
│  [ ] Launch at startup                            │
│  [ ] Start minimized to tray                      │
│  [√] Minimize to tray on close                    │
│                                                   │
│  Theme:     [ System      ▾ ]                     │
│  Log level: [ Info        ▾ ]                     │
│                                                   │
│                                    [ Close ]      │
└──────────────────────────────────────────────────┘
```

## Password Prompt Dialog

```
┌──────────────────────────────────────┐
│  VPN Credentials               [X]   │
├──────────────────────────────────────┤
│  Connecting to: Snapp HQ VPN         │
│                                       │
│  Username: [ alireza           ]      │
│  Password: [ ********         ]      │
│                                       │
│                   [Cancel]  [  OK  ]  │
└──────────────────────────────────────┘
```

## OTP Prompt Dialog

```
┌──────────────────────────────────────┐
│  OTP Required                  [X]   │
├──────────────────────────────────────┤
│  Please enter one-time password:     │
│  [ ********                          ]│
│                                       │
│                   [Cancel]  [  OK  ]  │
└──────────────────────────────────────┘
```

## Tray Icon -- Context Menu

```
  🟢 OpenFortiTray -- Connected (Snapp HQ VPN)
  ─────────────────────────────
  Disconnect
  ─────────────────────────────
  Snapp HQ VPN        ✓ (connected)
  Home Office
  ─────────────────────────────
  Open OpenFortiTray
  Quit
```

Double-click on tray icon shows the main window.
