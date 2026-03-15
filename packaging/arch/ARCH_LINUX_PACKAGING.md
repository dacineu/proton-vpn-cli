# Arch Linux Packaging for Proton VPN CLI

This directory contains files for packaging Proton VPN CLI on Arch Linux.

## Files

| File | Purpose |
|------|---------|
| `PKGBUILD` | Main Arch Linux package build script |
| `protonvpn-cli.install` | Post-install/pre-remove script for systemd service |
| `.SRCINFO` | Metadata for AUR submission |
| `protonvpn.service` | Systemd service unit file (included in source) |

## Building the Package

### Prerequisites

Ensure you have the base-devel package group installed:
```bash
sudo pacman -S --needed base-devel
```

Also required dependencies (will be pulled automatically):
- `python`
- `python-setuptools`
- `proton-vpn-api-core` (from AUR or community?)
- `proton-keyring-linux` (from AUR)
- `proton-vpn-local-agent` (from AUR or community)

### Build Command

From this directory:
```bash
makepkg -si
```

This will:
1. Download the source tarball from GitHub (v0.1.8)
2. Build the Python package
3. Install to package directory
4. Install the systemd service file
5. Install documentation
6. Install the package to your system
7. Enable and start the `protonvpn.service`

### Clean Build

```bash
makepkg -Ccfr  # Clean, force, skip checks, remove dependencies after
```

## What the Package Does

### Installation
- Installs Python module to `/usr/lib/python3.X/site-packages/`
- Installs `protonvpn` CLI script to `/usr/bin/`
- Installs systemd service to `/usr/lib/systemd/system/protonvpn.service`
- Installs documentation to `/usr/share/doc/proton-vpn-cli/`

### Post-Installation
- Reloads systemd daemon
- Enables `protonvpn.service` to start on boot
- Attempts to start the service immediately

### Removal
- Stops the service
- Disables the service
- Removes all files

## Dependencies

### Runtime Dependencies

| Package | Purpose |
|---------|---------|
| `python` | Python interpreter (>=3.9) |
| `python-click` | CLI framework |
| `python-dbus-fast` | D-Bus communication |
| `python-tabulate` | Table formatting |
| `proton-vpn-api-core>=4.14.3` | Proton API and core functionality |
| `proton-keyring-linux` | Credential storage |
| `proton-vpn-local-agent` | Local VPN daemon |

**Note**: The `proton-vpn-api-core` and `proton-keyring-linux` packages may need to be built from AUR if not available in official repositories.

### Optional: proton-vpn-daemon

Historically, there was a separate `proton-vpn-daemon` package. The daemon functionality is now in `proton-vpn-local-agent`. Make sure `proton-vpn-local-agent` provides the `proton.vpn.daemon` module.

If needed, you can create an AUR package for `proton-vpn-local-agent` following similar structure.

## Service File

The package installs `protonvpn.service` as defined in the source repository. The service:

- Type: simple
- Restart: on-failure
- Starts automatically on boot (WantedBy=multi-user.target)
- ExecStart: `/usr/bin/python3 -m proton.vpn.daemon`

### Manual Service Management

```bash
# Check status
systemctl status protonvpn.service

# Start
sudo systemctl start protonvpn.service

# Enable on boot
sudo systemctl enable protonvpn.service

# Stop
sudo systemctl stop protonvpn.service

# Disable
sudo systemctl disable protonvpn.service

# View logs
journalctl -u protonvpn.service -f
```

## Testing the Package

After installation:

1. Ensure daemon is running:
   ```bash
   systemctl status protonvpn
   ```

2. Test CLI:
   ```bash
   protonvpn --help
   protonvpn servers list  # Should work after login
   ```

3. Check that it works without sudo:
   ```bash
   # Should not require root
   protonvpn version
   ```

## Updating the PKGBUILD

When a new version is released:

1. Update `pkgver` in PKGBUILD
2. Update the tarball URL if version changes (it follows the pattern)
3. Optionally update `sha256sums` by running:
   ```bash
   upgpkg -m
   ```
   Or manually:
   ```bash
   curl -sL "https://github.com/ProtonMail/python-protonvpn-cli/archive/refs/tags/v${pkgver}.tar.gz" | sha256sum
   ```
4. Update `.SRCINFO`:
   ```bash
   makepkg --printsrcinfo > .SRCINFO
   ```

## Submitting to AUR

1. Create a new repository named `proton-vpn-cli`
2. Push these files:
   - PKGBUILD
   - protonvpn-cli.install
   - .SRCINFO
   - ( optionally an actual service file in the repo, but it's in the source tarball )
3. Submit via AUR web interface or `aur-cli` tools

**Note**: The `protonvpn.service` file is included in the upstream source tarball under `service/protonvpn.service`. The PKGBUILD copies it from the source. The `source` array includes the upstream tarball which contains the service file, so we don't need a separate source entry for it.

However, if you want to use the service file from this packaging directory instead of the upstream source, you would add a separate source entry and patch the install path. But the upstream-included service file is preferred.

## Troubleshooting

### Daemon not found

If you get "Python module not found: proton.vpn.daemon", ensure `proton-vpn-api-core` is installed and provides that module:

```bash
python3 -c "import proton.vpn.daemon"  # Should succeed
```

### Permission denied

The CLI should not require root. If you see permission errors, ensure your user is in the appropriate groups:
- `network` (for network operations)
- `input` (optional, for some features)

But the daemon handles privileged operations via polkit, so groups shouldn't matter if polkit rules are set up correctly.

### Service fails to start

Check logs:
```bash
sudo journalctl -u protonvpn.service -e
```

Common issues:
- Missing Python dependencies
- Network not available yet (should be fixed by `After=network-online.target`)

## Differences from DEB/RPM

| Aspect | Arch | Debian | RPM |
|--------|------|--------|-----|
| Build system | `makepkg` + `setup.py` | `dh_python` | `%pyproject_wheel` |
| Service install | `.install` script + PKGBUILD | `dh_installinit` | `%post` script |
| Dependency syntax | `depends=(...)` | `Depends: ${python3:Depends}` | `Requires:` |
| Post-install script | `.install` file | `postinst` script | `%post` script |

## Architecture Support

Arch Linux is rolling release and primarily supports x86_64. This package is architecture-independent (`arch=('any')`) because it's pure Python.

## Maintenance

Check upstream for new releases:
- https://github.com/ProtonMail/python-protonvpn-cli/releases
- versions.yml in source repository

Update this PKGBUILD promptly after releases to provide users with latest features and security updates.
