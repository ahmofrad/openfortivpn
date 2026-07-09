# Vendored Binaries

Place the pre-built `openfortivpn` binary (and platform-specific runtime
dependencies) in the appropriate subdirectory before running
`python packaging/build.py`.

## Structure

```
packaging/vendor/
├── windows/
│   ├── openfortivpn.exe      # built from the ahmofrad/openfortivpn fork
│   ├── wintun.dll             # from https://www.wintun.net/
│   ├── libssl-*.dll           # MinGW runtime (if built with MinGW)
│   ├── libcrypto-*.dll
│   ├── libwinpthread-*.dll
│   └── libgcc_s_seh-*.dll
├── linux/
│   └── openfortivpn           # built with autotools
└── macos/
    └── openfortivpn           # built with autotools
```

## Downloading Pre-built Binaries

Pre-built binaries are available from the
[GitHub Releases](https://github.com/ahmofrad/openfortivpn/releases) page:

1. Download `openfortivpn-windows-x64.zip` (or the Linux tarball)
2. Extract `openfortivpn.exe` (+ DLLs) into `packaging/vendor/windows/`
3. Download `wintun.dll` separately from https://www.wintun.net/

## Building from Source

See the main repo's [README](../../README.md) for build instructions.
