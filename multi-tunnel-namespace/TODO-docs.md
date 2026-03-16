# Documentation - Implementation Status

**Subproject**: User Guides, Man Pages, API Reference
**Status**: 🟡 **SPECIFICATION COMPLETE** (User docs missing)
**Last Updated**: 2026-03-16

---

## 📊 Completion Summary

| Doc Type | Status | Files | Audience | Ready? |
|----------|--------|-------|----------|--------|
| Technical Specification | ✅ Complete | SPECIFICATION.md (24KB) | Developers/Architects | Yes |
| Adapter Integration Design | ✅ Complete | ADAPTER_INTEGRATION.md (13KB) | Developers | Yes |
| MultiTunnel Connector Design | ✅ Complete | MULTITUNNEL Connector_Design.md (24KB) | Daemon team | Yes |
| Proton API Analysis | ✅ Complete | PROTON_API_ANALYSIS.md (24KB) | Daemon team | Yes |
| Multi-User System Design | ✅ Complete | MULTIUSER_SYSTEM.md (17KB) | Architects | Yes |
| Implementation Report | ✅ Complete | IMPLEMENTATION_REPORT.md (19KB) | Stakeholders | Yes |
| Progress Summary | ✅ Complete | PROGRESS_SUMMARY.md (11KB) | Team | Yes |
| Master README | ✅ Complete | MASTER_README.md (16KB) | All | Yes |
| Library README | ✅ Complete | libvpnmanager/README.md | Library users | Yes |
| Inline docstrings | ✅ Complete | All public APIs | Developers | Yes |
| User Guide | 🔴 Missing | - | End users | No |
| Man pages | 🔴 Missing | - | All (CLI) | No |
| CLI Reference | 🔴 Missing | - | CLI users | No |
| Installation Guide | 🔴 Missing | - | Admins | No |
| Troubleshooting Guide | 🔴 Missing | - | Support | No |
| **TOTAL** | **🟡 60%** | **10+ files** | | **Specs done, user docs no** |

---

## ✅ Completed Documentation

### Design & Specification Documents (Technical)

1. **SPECIFICATION.md** (24KB)
   - Complete technical specification for Option 1 (network namespaces)
   - System requirements: Linux kernel 3.9+, capabilities
   - Full data model (Tunnel, ConnectionConfig, TunnelStatus)
   - D-Bus interface specification (XML introspectable)
   - NetworkNamespaceRouting algorithm
   - Polkit rules design
   - Systemd service configuration
   - Success criteria

2. **ADAPTER_INTEGRATION.md** (13KB)
   - How to integrate Proton VPN into libvpnmanager
   - Current Proton daemon architecture
   - Required daemon changes (MultiTunnelVPNConnector)
   - ProtonVPNAdapter implementation details
   - Gap analysis

3. **MULTITUNNEL Connector_Design.md** (24KB)
   - Detailed design of MultiTunnelVPNConnector
   - API design
   - Implementation plan
   - Code examples
   - Error handling

4. **PROTON_API_ANALYSIS.md** (24KB)
   - Analysis of proton-vpn-api-core
   - Key classes and their roles
   - Current limitations (single-tunnel)
   - Required modifications
   - Integration strategy

5. **MULTIUSER_MULTIADAPTER_DESIGN.md** (36KB)
   - Multi-user considerations
   - Session management
   - Security model
   - Adapter architecture extensions

6. **IMPLEMENTATION_REPORT.md** (19KB)
   - Comprehensive status report
   - What was built (Phases 0-3)
   - Code quality metrics
   - Validation results
   - Next steps

7. **PROGRESS_SUMMARY.md** (11KB)
   - Quick reference for current status
   - Completion percentages
   - Dependencies/blockers
   - Timeline estimates

8. **MASTER_README.md** (16KB)
   - Project overview
   - Quick start
   - Architecture diagram
   - Feature list
   - Navigation to all docs

9. **README.md** (in repo root)
   - 6KB overview
   - Quick start for developers
   - File tree
   - Next steps

10. **libvpnmanager/README.md**
    - Library-specific documentation
    - Installation
    - API examples
    - Adapter writing guide

### Inline Documentation
- [x] **Docstrings**: Google style on all public APIs
  - Classes: purpose, init params
  - Methods: args, returns, raises, examples
- [x] **Type hints**: PEP 484 throughout (100%)
- [x] **Comments**: In complex sections (network namespace lifecycle, D-Bus serialization)

---

## 🔴 Missing Documentation (High Priority)

### 1. User Guide (End-User Documentation)

**Target**: End users who will use `protonvpn tunnel` commands

**Required sections**:
- [ ] **Introduction**
  - What is multi-tunnel VPN?
  - Why use network namespaces?
  - Benefits: isolation, per-app routing, different countries

- [ ] **Installation**
  - Supported distributions (Ubuntu 22.04+, Fedora 38+, Arch)
  - Package installation (DEB, RPM, PKGBUILD)
  - Starting the daemon (`systemctl start proton-vpn-manager`)
  - Polkit configuration (sudo/wheel groups)
  - Verifying installation (`protonvpn tunnel list`)

- [ ] **Getting Started**
  - Creating your first tunnel: `protonvpn tunnel create us --country US`
  - Connecting: `protonvpn tunnel connect us`
  - Checking status: `protonvpn tunnel info us`
  - Testing: `protonvpn tunnel exec us -- curl ifconfig.me`

- [ ] **Common Workflows**
  - **Using multiple tunnels simultaneously**
    - Create US tunnel for Netflix
    - Create Japan tunnel for gaming
    - Run Firefox in US namespace: `protonvpn tunnel switch us` → firefox
    - Run Steam in Japan namespace: `protonvpn tunnel exec japan -- steam`
  - **Per-application routing**
    - Route only specific apps through VPN
    - Keep rest of system on default route
  - **Isolating different identities**
    - Work tunnel (corporate)
    - Personal tunnel (privacy)
    - Development tunnel (geo-testing)

- [ ] **Command Reference**
  - Complete listing of `protonvpn tunnel *` commands
  - Options and arguments
  - Examples for each command
  - Exit codes

- [ ] **Troubleshooting**
  - "Daemon not running" - how to start
  - "Permission denied" - polkit configuration
  - "Namespace not found" - tunnel not connected
  - "nsenter: command not found" - install util-linux
  - "Connection failed" - check daemon logs (`journalctl -u proton-vpn-manager -f`)
  - "Tunnel already exists" - use different name
  - "Cannot destroy connected tunnel" - disconnect first
  - "No internet in namespace" - check NAT/iptables

- [ ] **Advanced Topics**
  - Manual namespace inspection (`ip netns exec`)
  - Debugging with `tcpdump` inside namespace
  - Viewing namespace routing tables
  - Custom DNS configuration
  - Performance tuning

- [ ] **FAQ**
  - Does this replace the old protonvpn CLI? (No, adds on)
  - Can I use without root? (Yes, polkit elevates)
  - How much memory per tunnel? (~5MB)
  - Maximum tunnels? ~50-100
  - Can I use different VPN providers? (Yes, via adapters)
  - Is it secure? (Yes, full isolation)

- [ ] **Migration from Single-Tunnel**
  - Old `protonvpn connect` still works
  - New commands are additional
  - No automatic migration
  - Differences in UX

---

### 2. Man Pages

**Format**: reStructuredText (RST) or Markdown (pandoc → groff)

**Required pages**:

#### `protonvpn-tunnel.1` (or part of protonvpn.1)

```
.TH "protonvpn-tunnel" "1" "March 2026" "0.1.0" "User Commands"
.SH NAME
protonvpn-tunnel \- manage multiple VPN tunnels with network namespaces
.SH SYNOPSIS
.B protonvpn tunnel
.RI [ COMMAND " " OPTIONS " " ...]
.SH DESCRIPTION
The
.B protonvpn tunnel
commands manage multiple concurrent VPN tunnels. Each tunnel is isolated
in its own network namespace, providing complete separation: separate
routing tables, DNS, and firewall.
.PP
Tunnels can be created, connected, and then applications run inside the
tunnel's namespace using
.B "tunnel switch"
or
.BR "tunnel exec" .
.SH COMMANDS
.TP
.B create
Create a new tunnel configuration.
.TP
.B list
List all tunnels and their status.
.TP
.B connect
Connect a tunnel to a VPN server.
.TP
.B disconnect
Disconnect a tunnel.
.TP
.B destroy
Delete a tunnel configuration.
.TP
.B switch
Start a new shell inside the tunnel's namespace.
.TP
.B exec
Run a command inside the tunnel's namespace.
.TP
.B info
Show detailed information about a tunnel.
.TP
.B mark
(Multi-tunnel only, not applicable to namespace isolation)
.SH EXAMPLES
Create a US tunnel:
.IP
$ sudo protonvpn tunnel create us \-\-country US
.PP
Connect it:
.IP
$ protonvpn tunnel connect us
.PP
Run Firefox in the US tunnel:
.IP
$ protonvpn tunnel switch us
$ firefox &
.IP
.B "(inside namespace)"
$ exit
.PP
Or run a single command:
.IP
$ protonvpn tunnel exec us \-\- curl https://ifconfig.me
.SH SEE ALSO
.BR protonvpn (1),
.BR proton-vpn-manager (8),
.BR ip-netns (8),
.BR nsenter (1)
.SH AUTHOR
Proton VPN Team <https://protonvpn.com>
```

#### `proton-vpn-manager.8` (daemon man page)

```
.TH "proton-vpn-manager" "8" "March 2026" "0.1.0" "System Administration"
.SH NAME
proton-vpn-manager \- multi-tunnel VPN daemon with network namespace isolation
.SH SYNOPSIS
.B proton-vpn-manager
.RI [ OPTIONS ]
.SH DESCRIPTION
.B proton-vpn-manager
is a system daemon that manages multiple concurrent VPN tunnels. It runs
as root (or with capabilities) and exposes a D-Bus interface
.B org.protonvpn.Manager.
.PP
The daemon is normally started by systemd. Tunnel configuration,
connection management, and namespace isolation are handled by the daemon.
Client tools (the
.B protonvpn
command) communicate with the daemon over D-Bus.
.SH OPTIONS
None. The daemon reads configuration from /etc/proton-vpn-manager.conf (if present).
.SH SIGNALS
.TP
.B SIGTERM, SIGINT
Graceful shutdown. All tunnels are disconnected and cleaned up.
.SH FILES
.TP
.I /usr/lib/systemd/system/proton-vpn-manager.service
Systemd service unit.
.TP
.I /etc/polkit-1/rules.d/60-protonvpn-manager.rules
Polkit authorization rules.
.TP
.I /var/run/netns/
Directory where network namespace references are stored.
.TP
.I /etc/proton-vpn-manager.conf
Optional configuration file (not yet implemented).
.SH "DBUS INTERFACE"
.B org.protonvpn.Manager
.PP
Methods:
.BR CreateTunnel(),
.BR DestroyTunnel(),
.BR ConnectTunnel(),
.BR DisconnectTunnel(),
.BR ListTunnels(),
.BR GetTunnelStatus(),
.BR GetTrafficStats(),
.BR ListAdapters(),
.BR GetAdapterCapabilities(),
.BR Ping().
.PP
Signals:
.BR TunnelStateChanged(),
.BR TunnelCreated(),
.BR TunnelDestroyed(),
.BR AdapterRegistered().
.SH "SECURITY"
The daemon runs with:
.IP \(bu 4
CapabilityBoundingSet=CAP_NET_ADMIN, CAP_SYS_ADMIN
.IP \(bu
NoNewPrivileges=true
.IP \(bu
PrivateTmp, ProtectSystem, ProtectHome
.IP \(bu
RestrictNamespaces=net
.PP
See systemd service file for full security profile.
.SH AUTHOR
Proton VPN Team <https://protonvpn.com>
.SH "SEE ALSO"
.BR protonvpn (1),
.BR ip-netns (8),
.BR nsenter (1),
.BR polkit (8)
```

#### `libvpnmanager.3` (library API man page) - Optional

- API reference for libvpnmanager
- Could be auto-generated with Sphinx

---

### 3. Installation Guide

**Target**: System administrators

**Required content**:
- [ ] **Prerequisites**: Linux distribution, Python 3.9+, root/sudo
- [ ] **From source (development)**:
  - Clone repo
  - `pip install -e src/libvpnmanager`
  - Copy daemon and service files
  - `systemctl enable --now proton-vpn-manager`
- [ ] **From packages (production)**:
  - Ubuntu/Debian: `apt install proton-vpn-multitunnel`
  - Fedora/RHEL: `dnf install proton-vpn-multitunnel`
  - Arch: `pacman -S proton-vpn-multitunnel` (from AUR)
- [ ] **Post-install**:
  - Verify daemon is running: `systemctl status proton-vpn-manager`
  - Check polkit: ensure user in wheel/sudo/admin
  - Test: `protonvpn tunnel list`
- [ ] **Upgrading**:
  - Package upgrades preserve configurations
  - Daemon will restart automatically
  - Tunnels preserved across restarts (stored in memory only currently, need persistence? **TBD**)
- [ ] **Uninstalling**:
  - `systemctl disable --now proton-vpn-manager`
  - Remove package
  - Note: tunnels in memory are lost (no persistence yet)

---

### 4. Troubleshooting Guide

**Organization**: By symptom → cause → solution

**Template**:

```
## Symptom: "Daemon not running"

**Error message**:
```
DBusError: org.freedesktop.DBus.Error.ServiceUnknown
```

**Cause**: The proton-vpn-manager daemon is not running.

**Solution**:
1. Start the daemon:
   ```bash
   sudo systemctl start proton-vpn-manager
   ```
2. Enable for automatic start:
   ```bash
   sudo systemctl enable proton-vpn-manager
   ```
3. Check status:
   ```bash
   systemctl status proton-vpn-manager
   ```
4. View logs:
   ```bash
   journalctl -u proton-vpn-manager -f
   ```

**Additional notes**: If daemon fails to start, check logs for specific errors (permissions, port conflicts).
```

**Common symptoms to document**:
- Daemon not running
- Permission denied (polkit)
- Tunnel already exists
- Tunnel not found
- Namespace not found (tunnel not connected)
- No internet in namespace (NAT issue)
- nsenter command not found
- Connection failed to VPN server
- High memory usage (too many tunnels)
- Daemon crashes on startup
- Cannot create more tunnels (resource limit)
- IP forwarding disabled
- DNS resolution failure inside namespace

---

### 5. Developer Guide

**Target**: Contributors to libvpnmanager or adapter writers

**Required content**:
- [ ] **Architecture overview**
  - Components: TunnelManager, adapters, routing, D-Bus
  - Data flow: CLI → D-Bus → Daemon → Adapter → Kernel
- [ ] **Writing a custom adapter**
  - Subclass `VPNAdapter`
  - Implement required methods
  - Define `ConnectionConfig` subclass
  - Register with TunnelManager
  - Example: Minimal adapter skeleton
- [ ] **Adding a new routing strategy**
  - Subclass `RoutingStrategy`
  - Implement create/delete/move/configure methods
  - Example: Policy routing implementation
- [ ] **Testing**
  - Running unit tests
  - Writing integration tests
  - Mocking strategies
- [ ] **Debugging**
  - Enable debug logging
  - Inspect D-Bus with `gdbus`
  - Inspect namespaces with `ip netns`
  - Trace packets with `tcpdump -i any`
- [ ] **Contributing**
  - Code style (black, ruff, mypy)
  - PR process
  - Testing requirements
  - Documentation updates

---

## 📚 Documentation Format & Tooling

### Tool Choice

For **user documentation** (guides, man pages):
- **Option 1**: Markdown → pandoc → groff (for man pages)
- **Option 2**: reStructuredText (RST) → Sphinx → multiple formats
- **Option 3**: Simple Markdown with `md2man` → man pages

**Recommendation**: Use **Markdown** for simplicity:
- Write guides in Markdown
- Convert to HTML for website/GitHub Pages
- Convert to man pages using `pandoc` in packaging scripts

### Documentation Structure

```
docs/
├── user-guide/              # End-user documentation
│   ├── installation.md
│   ├── getting-started.md
│   ├── commands.md
│   ├── workflows.md
│   ├── troubleshooting.md
│   ├── faq.md
│   └── advanced.md
├── man/                     # Man pages (source)
│   ├── protonvpn-tunnel.1.md
│   ├── proton-vpn-manager.8.md
│   └── libvpnmanager.3.md
├── developer/               # Developer documentation
│   ├── architecture.md
│   ├── adapter-development.md
│   ├── testing.md
│   └── contributing.md
└── api/                     # API reference (auto-gen from docstrings)
    └── index.html (Sphinx output)
```

---

## 🎯 Next Actions

### Immediate (Week 1)

1. [ ] **Write User Guide Getting Started** (2 pages)
   - Install
   - Create first tunnel
   - Connect
   - Run command in namespace
   - Verify

2. [ ] **Write Command Reference** (3 pages)
   - All `protonvpn tunnel` commands
   - Options and examples
   - Structured like man page but in Markdown

3. [ ] **Write Troubleshooting Guide** (2 pages)
   - Top 10 common issues
   - Solutions with commands
   - Log interpretation

4. [ ] **Install guide** (1 page)
   - Package repos (when available)
   - From source (for developers)
   - Post-install steps

### Week 2

5. [ ] **Write man pages** (3 pages)
   - `protonvpn-tunnel.1`
   - `proton-vpn-manager.8`
   - `libvpnmanager.3` (optional)
   - Use Markdown with pandoc

6. [ ] **Write Developer Guide**
   - Architecture overview
   - Writing adapters (with example)
   - Testing guide

7. [ ] **Write FAQ** (1 page)
   - Top questions
   - Concise answers

### Week 3

8. [ ] **Review and edit** all docs
   - Ensure clarity
   - Add screenshots if helpful
   - Verify commands work as documented
   - Check formatting

9. [ ] **Polish README.md** in repo root
   - Add link to full docs
   - Quick start for developers
   - Installation quick summary

10. [ ] **Create docs website** (optional)
    - GitHub Pages with MkDocs or Sphinx
    - Host at https://protonvpn.github.io/proton-vpn-cli/multi-tunnel/

---

## 📦 Packaging Documentation

- [ ] Include man pages in packages:
  - DEB: `debian/install` or `dh_installman`
  - RPM: `%{_mandir}/man1/` etc.
  - Arch: `man/` directory in PKGBUILD

- [ ] Include user guide in:
  - DEB: `/usr/share/doc/proton-vpn-multitunnel/`
  - RPM: `%{_defaultdocdir}/proton-vpn-multitunnel/`
  - Arch: `/usr/share/doc/proton-vpn-multitunnel/`

- [ ] Online docs: Publish to GitHub Pages or Proton website

---

## 🐛 Documentation Gaps

1. **No user-facing docs** - Only technical specs exist
2. **No man pages** - CLI lacks traditional documentation
3. **No installation guide** - Users don't know how to install
4. **No troubleshooting** - Support will be overwhelmed
5. **No developer guide** - Contributors need onboarding
6. **No API reference website** - Library users need searchable docs
7. **No examples of real usage** - Just PoC, not end-user workflows

---

## 🔄 Documentation Workflow

1. Write in Markdown in `docs/user-guide/`, `docs/man/`, etc.
2. Review by team (technical accuracy + clarity)
3. Convert man pages: `pandoc -s man.md -t man > protonvpn-tunnel.1`
4. Package in DEB/RPM/Arch
5. Deploy to GitHub Pages (optional)
6. Announce in release notes

---

## 📊 Timeline

| Doc Type | Duration | Priority | Dependencies |
|----------|----------|----------|--------------|
| User Guide (getting started + commands) | 3-4 days | High | CLI working |
| Troubleshooting Guide | 2 days | High | Experience common issues |
| Installation Guide | 1 day | Medium | Packages built |
| Man pages | 2 days | High | Commands stable |
| Developer Guide | 3 days | Medium | Architecture stable |
| FAQ | 1 day | Low | Common questions known |
| API reference (Sphinx auto-gen) | 1 day | Low | Docstrings complete |
| **Total** | **~2 weeks** | | **CLI integrated first** |

---

## 🎯 Success Criteria

Documentation complete when:
- [ ] End users can install and use the system from README alone
- [ ] CLI has comprehensive `--help` and man page
- [ ] Troubleshooting guide covers top 20 issues
- [ ] Developer guide enables new contributors
- [ ] All docs published online (GitHub Pages)
- [ ] Docs included in packages (DEB/RPM/Arch)
- [ ] No "TODO" or "FIXME" in docs
- [ ] Proofread for grammar and clarity
- [ ] Screenshots/examples validated (commands actually work)

---

**Conclusion**: Excellent technical specification foundation exists, but end-user documentation is entirely missing. Major effort needed: ~2 weeks of writing. Should begin once CLI stabilizes and packages are ready for testing. Prioritize: User Guide, Man Pages, Troubleshooting.
