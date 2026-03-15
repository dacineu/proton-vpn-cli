# Arch Linux Packaging Summary

**Date**: 2026-03-15
**Commit**: f3f5c2e
**Version**: 0.1.8 (with daemon integration)

---

## Overview

Added complete Arch Linux packaging support for proton-vpn-cli. The package integrates seamlessly with systemd, automatically handling the daemon setup.

---

## Files Added

```
packaging/arch/
├── PKGBUILD                 # Main build script
├── protonvpn-cli.install    # systemd service enable/start hooks
├── .SRCINFO                 # AUR metadata
├── ARCH_LINUX_PACKAGING.md  # Detailed packaging documentation
└── update_checksums.sh      # Helper to update source checksums
```

---

## PKGBUILD Highlights

### Dependencies
- **Runtime**: python, python-click, python-dbus-fast, python-tabulate, proton-vpn-api-core (>=4.14.3), proton-keyring-linux, proton-vpn-local-agent
- **Build**: python-setuptools, python-pip
- **Architecture**: `any` (pure Python)

### Key Features
1. **Automatic source directory handling** - `prepare()` renames extracted GitHub tarball to consistent name
2. **Systemd service installation** - Installs `service/protonvpn.service` to `/usr/lib/systemd/system/`
3. **Automatic service activation** - `.install` script enables and starts the daemon on package installation
4. **Documentation included** - README, LICENSE, COPYING installed to `/usr/share/doc/`

### Installation Flow
```bash
makepkg -si
# ↓
# Downloads source
# Builds Python package with pip
# Installs service file
# Runs post-install: systemctl daemon-reload, enable, start
```

---

## .install Script

The `protonvpn-cli.install` file contains:

```bash
post_install() {
    systemctl daemon-reload
    systemctl enable protonvpn.service
    systemctl start protonvpn.service
}

pre_remove() {
    systemctl stop protonvpn.service
    systemctl disable protonvpn.service
}

post_remove() {
    systemctl daemon-reload
}
```

This ensures the daemon is properly managed during package lifecycle.

---

## Usage for Arch Users

### Quick Install

```bash
# 1. Clone the repo
git clone https://github.com/ProtonMail/python-protonvpn-cli.git
cd python-protonvpn-cli

# 2. Ensure base-devel is installed
sudo pacman -S --needed base-devel python python-pip

# 3. Build and install from packaging/arch
cd packaging/arch
./update_checksums.sh   # Optional: fetch correct SHA256
makepkg -si
```

### Verify Installation

```bash
# Check daemon is running
systemctl status protonvpn.service

# Test CLI
protonvpn --help
protonvpn version
```

---

## AUR Submission

To submit to AUR:

1. Create a new AUR repository named `proton-vpn-cli`
2. Push these files:
   - `PKGBUILD`
   - `protonvpn-cli.install`
   - `.SRCINFO`
3. (Optional) Keep `ARCH_LINUX_PACKAGING.md` and `update_checksums.sh` for reference

**Before uploading**: Run `makepkg -f` to verify build, and update `.SRCINFO`:
```bash
makepkg --printsrcinfo > .SRCINFO
```

---

## Differences from Other Package Formats

| Feature | Arch | Debian | RPM |
|---------|------|--------|-----|
| Build tool | `makepkg` | `dh` | `rpmbuild` |
| Service handling | `.install` script + manual | `dh_installinit` | `%post` script |
| Dependencies | `depends=(...)` array | `${python3:Depends}` | `Requires:` |
| Metadata | `.SRCINFO` | `debian/control` | `spec` file |

All formats install the same `protonvpn.service` file from the source tree.

---

## Testing

### Build Test
```bash
cd packaging/arch
makepkg -df  # Download dependencies and prepare, but don't install
```

Expected output:
- Source tarball downloaded
- `prepare()` renames directory to `proton-vpn-cli-0.1.8`
- Python package built via pip
- Service file copied
- Documentation installed
- Package `.pkg.tar.zst` created

### Install Test
```bash
sudo makepkg -si
```

Expected:
- Package installs without errors
- `systemctl daemon-reload` runs
- `protonvpn.service` enabled and started
- `protonvpn` command available in PATH

### Functional Test
```bash
protonvpn servers list  # After login should work
```

---

## Notes

- The daemon module (`proton.vpn.daemon`) is provided by `proton-vpn-api-core`
- The `proton-vpn-local-agent` package must also be installed (dependency)
- Service file runs as: `/usr/bin/python3 -m proton.vpn.daemon`
- Package is architecture-independent (`arch=('any')`)

---

## Update Process

When upstream releases a new version:

1. Update `pkgver` in PKGBUILD
2. Run `./update_checksums.sh` or manually compute:
   ```bash
   curl -sL "https://github.com/ProtonMail/python-protonvpn-cli/archive/refs/tags/v${pkgver}.tar.gz" | sha256sum
   ```
3. Update `sha256sums` in PKGBUILD
4. Rebuild: `makepkg -si`
5. Update `.SRCINFO`: `makepkg --printsrcinfo > .SRCINFO`
6. Commit and push to AUR

---

## Rollback

If issues arise after installation:

```bash
# Remove package
sudo pacman -R proton-vpn-cli

# Optionally remove daemon (if not needed by other packages)
sudo systemctl disable protonvpn.service
sudo systemctl stop protonvpn.service

# Downgrade to previous version if needed (from cache)
sudo pacman -U /var/cache/pacman/pkg/proton-vpn-cli-0.1.7-1-any.pkg.tar.zst
```

---

## Conclusion

The Arch Linux package provides a seamless installation experience with automatic daemon setup, matching the behavior of Debian and RPM packages. PKGBUILD follows Arch packaging standards and can be submitted to AUR for community use.
