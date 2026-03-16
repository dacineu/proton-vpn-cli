# Packaging & Distribution - Implementation Status

**Subproject**: DEB, RPM, and Arch Packages
**Status**: 🟡 **STRUCTURE EXISTS** (Needs build scripts and testing)
**Last Updated**: 2026-03-16

---

## 📊 Completion Summary

| Package Type | Service File | Polkit Rules | Build Scripts | Status |
|--------------|--------------|--------------|---------------|--------|
| DEB (Debian/Ubuntu) | ✅ | ✅ | 🔴 | 30% |
| RPM (Fedora/RHEL) | ✅ | ✅ | 🔴 | 30% |
| Arch (PKGBUILD) | ✅ | ✅ | 🟡 | 50% |
| **TOTAL** | **✅** | **✅** | **🔴** | **35%** |

---

## ✅ Completed Tasks

### Systemd Service File
- [x] Created: `packaging/systemd/usr/lib/systemd/system/proton-vpn-manager.service`
- [x] Full security hardening
- [x] CapabilityBoundingSet configured
- [x] Type=dbus with BusName=org.protonvpn.Manager
- [x] Ready for installation to `/usr/lib/systemd/system/`

### Polkit Rules
- [x] Created: `packaging/polkit/60-protonvpn-manager.rules`
- [x] Configured for wheel/sudo/admin groups
- [x] Detailed comments explaining each rule
- [x] Ready for installation to `/etc/polkit-1/rules.d/`

### Package Structure
- [x] Created directory structure:
  ```
  packaging/
  ├── systemd/usr/lib/systemd/system/
  │   └── proton-vpn-manager.service
  ├── polkit/
  │   └── 60-protonvpn-manager.rules
  ├── deb/ (created, empty)
  ├── rpm/ (created, empty)
  └── arch/ (may exist in separate location)
  ```

---

## 🟡 Incomplete / Partially Complete

### Arch Linux Packaging (PKGBUILD)
**Status**: 🟡 Some work done (see git history)

- [x] **References exist**: Recent commits mention Arch packaging
- [x] **PKGBUILD may exist**: Check if `packaging/arch/` or separate location
- [ ] **Verify PKGBUILD completeness**:
  - [ ] pkgname, pkgver, pkgrel
  - [ ] source=(git clone or tarball)
  - [ ] depends=(python, dbus-fast, ...)
  - [ ] Install service to `/usr/lib/systemd/system/`
  - [ ] Install polkit rules to `/etc/polkit-1/rules.d/`
  - [ ] Install Python package (libvpnmanager) via pip or setup.py
  - [ ] Install daemon script
  - [ ] Install CLI script (protonvpn)
  - [ ] `package()` function correct
  - [ ] `check()` function (optional)
- [ ] **Test build**: `makepkg -si`
- [ ] **Test install/uninstall**: `pacman -Q` and removal
- [ ] **Test functionality**: Daemon starts, CLI works

⚠️ **Action**: Locate PKGBUILD files. They may be in a separate branch or directory (`../multi-tunnel-policy-routing/` or elsewhere based on git status).

---

## 🔴 Not Started (Critical)

### Debian/Ubuntu Packaging (DEB)

#### 1. Create debian/ Directory Structure
```
debian/
├── control              # Package metadata, dependencies
├── rules                # Build script (make-based or python)
├── changelog            # Debian changelog format
├── compat               # Debhelper compatibility level
├── install              # File installation mappings (if not in rules)
├── proton-vpn-manager.systemd   # systemd service installation
├── proton-vpn-manager.polkit   # polkit rules installation
├── libvpnmanager.install        # Python package install
├── protonvpn.install           # CLI script install
├── proton-vpn-manager.docs     # Documentation files
├── proton-vpn-manager.links    # Create symlinks if needed
├── copyright             # Copyright information
├── watch                 # uscan watch file (optional)
├── source/format         # Source format (3.0 quadt)
└── patches/              # Any patches needed
```

#### 2. debian/control
```
Source: proton-vpn-multitunnel
Section: net
Priority: optional
Maintainer: Proton VPN Team <team@protonvpn.com>
Build-Depends: debhelper (>= 13), python3, python3-setuptools, python3-dbus-fast, python3-pydantic2, python3-asyncio, python3-pytest
Standards-Version: 4.6.0

Package: proton-vpn-manager
Architecture: any
Pre-Depends: ${misc:Pre-Depends}
Depends: ${shlibs:Depends}, ${misc:Depends}, python3, python3-libvpnmanager, dbus, policykit-1, systemd
Description: Multi-tunnel VPN daemon with network namespace isolation
 Provides the proton-vpn-manager daemon for managing multiple concurrent VPN tunnels.

Package: proton-vpn-cli
Architecture: any
Depends: ${shlibs:Depends}, ${misc:Depends}, python3, python3-libvpnmanager, proton-vpn-manager
Description: Proton VPN CLI with multi-tunnel support
 Extended protonvpn command with tunnel management commands.

Package: libvpnmanager0
Architecture: any
Section: python
Depends: ${shlibs:Depends}, ${misc:Depends}, python3, python3-dbus-fast, python3-pydantic2, python3-asyncio
Description: Library for managing multi-tunnel VPN connections
 Reusable Python library for multi-tunnel VPN with network namespace isolation.
```

#### 3. debian/rules (simplified)
```makefile
#!/usr/bin/make -f
%:
	dh $@ --with python3

override_dh_auto_install:
	# Install libvpnmanager
	cd src/libvpnmanager && pip3 install . --destdir=$(CURDIR)/debian/libvpnmanager0/ --no-deps
	# Install daemon
	install -D -m 755 src/daemon/daemon.py debian/proton-vpn-manager/usr/bin/proton-vpn-manager
	# Install CLI
	install -D -m 755 src/cli/tunnel.py debian/protonvpn-cli/usr/bin/protonvpn-tunnel (or integrate)
```

#### 4. Install systemd service
- `debian/proton-vpn-manager.install`: `usr/lib/systemd/system/proton-vpn-manager.service`
- Or in rules: `dh_installsystemd --no-start proton-vpn-manager.service`

#### 5. Install polkit rules
- `debian/proton-vpn-manager.install`: `etc/polkit-1/rules.d/60-protonvpn-manager.rules`

#### 6. debian/changelog
- Use `dch` to create initial entry
- Version: `0.1.0-1` (or match project version)
- Distribution: `unstable` or `ubuntu`

#### 7. debian/copyright
- License: GPL-3.0+
- Upstream: Proton VPN Team
- Source: GitHub URL

#### 8. Build and test
```bash
dpkg-buildpackage -us -uc -b
# or
debuild -us -uc
```

#### 9. Install locally
```bash
sudo dpkg -i ../proton-vpn-multitunnel_0.1.0-1_amd64.deb
sudo dpkg -i ../libvpnmanager0_0.1.0-1_all.deb
```

#### 10. Lintian check
```bash
lintian ../proton-vpn-multitunnel_0.1.0-1_*.deb
```

### Red Hat/Fedora Packaging (RPM)

#### 1. Create .spec file
`packaging/rpm/proton-vpn-multitunnel.spec`

```
Name:           proton-vpn-multitunnel
Version:        0.1.0
Release:        1%{?dist}
Summary:        Multi-tunnel VPN daemon with network namespace isolation
License:        GPLv3+
URL:            https://github.com/ProtonVPN/proton-vpn-cli
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-dbus-fast
BuildRequires:  python3-pydantic
BuildRequires:  python3-asyncio

Requires:       python3-libvpnmanager
Requires:       dbus-python
Requires:       systemd
Requires:       polkit

# Systemd service
%{?systemd_requires}
%{?systemd_post}
%{?systemd_preun}
%{?systemd_postun}

%description
The proton-vpn-multitunnel package provides a daemon and CLI for managing
multiple concurrent VPN tunnels using Linux network namespaces.

%package        cli
Summary:        CLI for multi-tunnel VPN management
Requires:       proton-vpn-multitunnel = %{version}-%{release}

%description    cli
Extended protonvpn command with tunnel management commands.

%prep
%autosetup -n %{name}-%{version}

%build
# Nothing to build, pure Python

%install
# Install libvpnmanager
cd src/libvpnmanager && python3 setup.py install --root=%{buildroot} --optimize=1
# Install daemon
install -D -m 755 src/daemon/daemon.py %{buildroot}%{_bindir}/proton-vpn-manager
# Install CLI (or integrate into main protonvpn)
install -D -m 755 src/cli/tunnel.py %{buildroot}%{_bindir}/protonvpn-tunnel

# Install systemd service
install -D -m 644 packaging/systemd/usr/lib/systemd/system/proton-vpn-manager.service \
  %{buildroot}%{_unitdir}/proton-vpn-manager.service

# Install polkit rules
install -D -m 644 packaging/polkit/60-protonvpn-manager.rules \
  %{buildroot}%{_sysconfdir}/polkit-1/rules.d/60-protonvpn-manager.rules

%post
%systemd_post proton-vpn-manager.service

%preun
%systemd_preun proton-vpn-manager.service

%postun
%systemd_postun_with_restart proton-vpn-manager.service

%files
%license LICENSE
%doc README.md
%{_bindir}/proton-vpn-manager
%{_unitdir}/proton-vpn-manager.service
%{_sysconfdir}/polkit-1/rules.d/60-protonvpn-manager.rules
%{python3_sitelib}/libvpnmanager

%files cli
%{_bindir}/protonvpn-tunnel
%{python3_sitelib}/libvpnmanager/cli

%changelog
* Mon Mar 16 2026 Proton VPN Team <team@protonvpn.com> - 0.1.0-1
- Initial release of multi-tunnel VPN support
```

#### 2. Build and test
```bash
rpmbuild -ba packaging/rpm/proton-vpn-multitunnel.spec
```

#### 3. Install locally
```bash
sudo rpm -i ~/rpmbuild/RPMS/noarch/proton-vpn-multitunnel-0.1.0-1.noarch.rpm
```

#### 4. Test with dnf/yum
```bash
sudo dnf localinstall ~/rpmbuild/RPMS/noarch/proton-vpn-multitunnel-*.rpm
```

### Additional Distribution Notes

#### NixOS
- [ ] Create nix expression
- [ ] Package Python dependencies
- [ ] Overlay for systemd/polkit

#### macOS (Not supported)
- Network namespaces differ; not in scope

---

## 🧪 Packaging Testing Checklist

For **each** package type (DEB, RPM, Arch):

- [ ] **Build successful** without errors or warnings (lintian/rpmlint)
- [ ] **Install successful** (`dpkg -i`, `rpm -i`, `pacman -U`)
- [ ] **Files in correct locations**:
  - [ ] Daemon: `/usr/bin/proton-vpn-manager`
  - [ ] Systemd: `/usr/lib/systemd/system/proton-vpn-manager.service`
  - [ ] Polkit: `/etc/polkit-1/rules.d/60-protonvpn-manager.rules`
  - [ ] Python lib: `/usr/lib/python3.X/site-packages/libvpnmanager/`
  - [ ] CLI: `/usr/bin/protonvpn` or `/usr/bin/protonvpn-tunnel`
- [ ] **Dependencies installed** automatically
- [ ] **Systemd service enabled/started**:
  - [ ] `systemctl status proton-vpn-manager`
  - [ ] `systemctl start proton-vpn-manager`
  - [ ] Service loads without errors
  - [ ] D-Bus name registered: `gdbus list --system | grep org.protonvpn`
- [ ] **Polkit rules loaded**: `pkaction --action-id org.protonvpn.manager.tunnel.create --verbose`
- [ ] **CLI invokable**: `protonvpn tunnel --help` (or `protonvpn-tunnel --help`)
- [ ] **End-to-end test**: Create and connect tunnel (with DummyAdapter or real)
- [ ] **Uninstall cleanly**: `apt remove`, `dnf remove`, `pacman -R`
- [ ] **No leftover files** in /var/run/netns, /etc, etc.
- [ ] **Upgrade test**: New version installs over old cleanly
- [ ] **Rollback test**: Downgrade works (if needed)

---

## 📦 Package Dependencies

### Runtime Dependencies (End User)
- python3 >= 3.9
- python3-dbus-fast >= 1.90.0
- python3-pydantic >= 2.0.0
- python3-asyncio (usually stdlib)
- dbus (system or session bus)
- policykit-1 (polkit)
- systemd (for service)
- iproute2 (for `ip` command)
- util-linux (for `nsenter` command)
- Optional: pyroute2 (for advanced routing, not currently used)

### Build Dependencies
- debhelper (DEB)
- dh-python (DEB)
- python3-setuptools
- python3-wheel
- rpm-build (RPM)
- systemd (RPM)
- polkit (RPM)

### Python Dependencies (from pyproject.toml)
```
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "libvpnmanager"
dependencies = [
    "dbus-fast>=1.90.0",
    "pydantic>=2.0.0",
    "asyncstdlib>=3.10.0",
]
```

---

## 🔄 Distribution Strategy

### Debian/Ubuntu
- **Target releases**: Ubuntu 22.04+, Debian 12+
- **Channel**: Proposed PPA (ppa:protonvpn/stable) or direct .deb download
- **Signing**: GPG sign packages (optional but recommended)
- **Repository**: If publishing, need apt repo (Cloudsmith, Packagecloud, or self-hosted)
- **Backports**: Not needed initially (Python 3.9+ is standard)

### Fedora/RHEL/CentOS
- **Target**: Fedora 38+, RHEL 9+, CentOS Stream
- **Channel**: COPR (fedorapeople) or direct .rpm download
- **EPEL**: Consider for CentOS/RHEL
- **SIG**: Consider Fedora SIG packaging

### Arch Linux
- **Target**: Rolling release
- **Channel**: AUR (User Repository)
- **PKGBUILD**: Maintain in AUR package `proton-vpn-multitunnel-git`
- **Update**: Track git master or tagged releases

---

## 🎯 Next Actions

### Immediate (Week 1)
1. [ ] **Locate existing Arch PKGBUILD** - Check `../multi-tunnel-policy-routing/` or git history
2. [ ] **Create debian/ directory** with full control, rules, changelog
3. [ ] **Create .spec file** for RPM
4. [ ] **Test build** each package locally (no sign/upload yet)

### Week 2
5. [ ] **Fix build issues** - adjust paths, dependencies
6. [ ] **Test install** on VMs (Ubuntu 22.04, Fedora 38, Arch)
7. [ ] **Verify daemon starts** via systemd
8. [ ] **Fix lintian/rpmlint warnings**
9. [ ] **Document build process** in README

### Week 3
10. [ ] **Create PPA** (Ubuntu) or COPR (Fedora) for automated builds
11. [ ] **Submit to AUR** (Arch) if not already there
12. [ ] **Test CI/CD** - automatic builds on git push
13. [ ] **Document installation** for end users

### Week 4
14. [ ] **Package for release** - versioned builds
15. [ ] **Sign packages** (if needed)
16. [ ] **Create release assets** on GitHub (DEB, RPM, PKG.tar.zst)
17. [ ] **Update website/repo README** with install instructions

---

## 🐛 Known Packaging Issues

1. **Python package name**: `libvpnmanager` but system package might be `libvpnmanager0` (soname) or just `python3-libvpnmanager`
2. **Multiple Python versions**: Should support Python 3.9+ but package for 3.11?
3. **Daemon location**: `/usr/bin/proton-vpn-manager` vs `/usr/libexec/` (FHS varies)
4. **CLI integration**: Should tunnel commands be separate `protonvpn-tunnel` or integrated into main `protonvpn`? Likely integrate into main CLI package.
5. **Service enablement**: Should package auto-enable service? Probably not; user should opt-in.
6. **Polkit conflicts**: If main protonvpn also has polkit rules, ensure they don't conflict (use separate action IDs)

---

## 📊 Dependency Graph

```
proton-vpn-multitunnel (meta-package)
├── libvpnmanager (Python library)
│   ├── python3-dbus-fast
│   ├── python3-pydantic
│   └── python3-asyncio
├── proton-vpn-manager (daemon)
│   ├── libvpnmanager
│   ├── systemd
│   └── polkit-1
└── proton-vpn-cli (CLI integration)
    ├── libvpnmanager
    ├── proton-vpn-manager
    └── (main protonvpn CLI)
```

**Note**: In practice, `proton-vpn-cli` likely extends the existing `protonvpn` command, so it's not a separate package but rather an update to the main `proton-vpn-cli` package.

---

## 🎯 Success Criteria

Packaging complete when:
- [ ] DEB builds cleanly on Ubuntu 22.04+
- [ ] RPM builds cleanly on Fedora 38+
- [ ] Arch PKGBUILD works on latest Arch
- [ ] All packages install without errors
- [ ] Dependencies correctly auto-installed
- [ ] Daemon starts via systemd
- [ ] CLI commands work after install
- [ ] No file conflicts with existing protonvpn packages
- [ ] Backward compatibility: old `protonvpn connect` still works
- [ ] Uninstall cleanly, no leftovers
- [ ] Upgrade path works (old → new version)

---

## 🔧 Build Automation (Optional but Recommended)

### GitHub Actions Workflow
```yaml
name: Build Packages
on:
  push:
    tags: ['v*']
jobs:
  deb:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build DEB
        run: |
          sudo apt-get install devscripts debhelper dh-python3 python3-setuptools python3-dbus-fast python3-pydantic
          cd packaging/deb && dpkg-buildpackage -us -uc -b
      - uses: actions/upload-artifact@v3
        with:
          name: deb-package
          path: ../*.deb

  rpm:
    runs-on: fedora-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build RPM
        run: |
          sudo dnf install -y rpm-build python3-devel python3-setuptools python3-dbus-fast python3-pydantic
          rpmbuild -ba packaging/rpm/proton-vpn-multitunnel.spec
      - uses: actions/upload-artifact@v3
        with:
          name: rpm-package
          path: ~/rpmbuild/RPMS/**/*.rpm
```

---

**Conclusion**: Package scaffolding exists (service, polkit), but actual build scripts ( debian/, .spec, PKGBUILD) need creation or completion. This is straightforward mechanical work once the codebase stabilizes. Prioritize after core integration testing.
