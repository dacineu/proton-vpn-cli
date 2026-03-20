# Arch Linux Packages for Proton VPN CLI with Multi-Tunnel Support

**Date**: 2026-03-16
**Version**: 0.1.8
**Branch**: stable

---

## 📦 Available Packages

### 1. proton-vpn-manager (0.1.8-1)
**Size**: 142 KB
**Location**: `multi-tunnel-namespace/packaging/arch/pkg/proton-vpn-manager-0.1.8-1-any.pkg.tar.zst`

The multi-tunnel VPN daemon that runs as a systemd service.

**Contents**:
- `/usr/bin/proton-vpn-manager` - D-Bus daemon
- `/usr/lib/systemd/system/proton-vpn-manager.service` - systemd unit
- `/etc/polkit-1/rules.d/60-protonvpn-manager.rules` - Polkit rules
- Python library: `libvpnmanager` (all modules)
- Documentation in `/usr/share/doc/proton-vpn-manager/`
- Install script to auto-enable/start the service

**Dependencies**: python, python-dbus-fast, python-pydantic, python-asyncstdlib, python-pyroute2, iproute2, nsenter

### 2. proton-vpn-cli (0.1.8-2)
**Size**: 104 KB
**Location**: `packaging/arch/pkg/proton-vpn-cli-0.1.8-2-any.pkg.tar.zst`

The main Proton VPN CLI with multi-tunnel command integration.

**Contents**:
- `/usr/bin/protonvpn` - CLI executable
- `/usr/lib/systemd/system/protonvpn.service` - systemd unit for the existing daemon
- Python modules: `proton.vpn.cli` with tunnel commands
- Documentation in `/usr/share/doc/proton-vpn-cli/`

**Dependencies**:
- Core: python, python-click, python-dbus-fast, python-tabulate, proton-vpn-api-core (>=4.14.3), proton-keyring-linux, proton-vpn-local-agent
- Multi-tunnel: python-asyncstdlib, python-pydantic, python-pyroute2, iproute2, nsenter

**Optdepends**: proton-vpn-manager (for tunnel commands)

---

## 🚀 Installation

### Option 1: Install Pre-built Packages

```bash
# Install from the repo's packaging/arch/pkg/ directory
cd /home/dacineu/dev/proton-vpn-cli

# Install the daemon first
sudo pacman -U multi-tunnel-namespace/packaging/arch/pkg/proton-vpn-manager-0.1.8-1-any.pkg.tar.zst

# Install the CLI (or update existing)
sudo pacman -U packaging/arch/pkg/proton-vpn-cli-0.1.8-2-any.pkg.tar.zst
```

### Option 2: Build from PKGBUILD

```bash
# Build proton-vpn-manager (the add-on daemon)
cd multi-tunnel-namespace/packaging/arch
makepkg -s --nodeps  # Uses local source tree
# Or: ./build-addon.sh  # Convenience script

# Build proton-vpn-cli (the main CLI)
cd ../../../packaging/arch
makepkg -s --nodeps
```

---

## ✅ Verification

After installation:

```bash
# Check daemon is running
systemctl status proton-vpn-manager

# Check CLI has tunnel commands
protonvpn --help
protonvpn tunnel --help

# Test with dummy adapter (doesn't require Proton account)
protonvpn tunnel create test --adapter dummy --session test
protonvpn tunnel list
protonvpn tunnel disconnect test
```

---

## 🔧 Rebuilding

**proton-vpn-manager**:
```bash
cd multi-tunnel-namespace/packaging/arch
makepkg -f --nodeps  # or: ./build-addon.sh
```

**proton-vpn-cli**:
```bash
cd packaging/arch
makepkg -f --nodeps
```

---

## 📝 Notes

- The packages are built for **Arch Linux** only.
- Dependencies must be installed (some may be from AUR).
- The `proton-vpn-manager` daemon requires `CAP_NET_ADMIN` and `CAP_SYS_ADMIN` capabilities.
- Polkit rules allow privileged users to manage tunnels.
- Multi-tunnel support is **optional**; existing single-tunnel functionality remains unchanged.

---

## 🎯 What's New in 0.1.8

- Multi-tunnel VPN with network namespace isolation
- `protonvpn tunnel` command group (create, list, sessions, disconnect, destroy, switch, exec, info, login, logout)
- Support for Proton, Psiphon, and WireGuard adapters
- Per-user tunnel ownership
- Session management for multiple VPN accounts

---

**Your fork**: https://github.com/dacineu/proton-vpn-cli (branch: stable)
