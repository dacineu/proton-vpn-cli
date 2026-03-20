# Project Index: Multi-Tunnel VPN Design & TODO Lists

**Date**: 2026-03-15
**Status**: Planning phase (no implementation yet)

---

## 📦 What Was Created

### For Current Release (0.1.8)
- ✅ `TODO_0.1.8.md` - Completed achievements and future backlog
  - Free tier selection, servers list command, daemon integration, Arch packaging
  - All marked as completed
  - Future improvements listed

### For Multi-Tunnel Feature (Options 1 & 2)

#### 1. **Network Namespaces Approach** (Complete Isolation)
- 📁 `multi-tunnel-namespace/`
  - `TODO_OPTION1.md` - **44,813 bytes** of comprehensive planning
  - `docs/` - Placeholder for architecture docs
  - `src/` - Skeleton for libvpnmanager, daemon, CLI
  - `packaging/` - DEB/RPM packaging structure
  - `tests/` - Test structure

#### 2. **Policy Routing Approach** (Simpler)
- 📁 `multi-tunnel-policy-routing/`
  - `TODO_OPTION2.md` - **19,324 bytes** of comprehensive planning
  - `docs/`
  - `src/`
  - `packaging/`
  - `tests/`

### Documentation
- 📄 `MULTI_TUNNEL_ARCHITECTURE.md` - Main overview comparing both approaches
- 📄 `QUICK_REFERENCE.md` - Side-by-side comparison and decision matrix

---

## 📊 Comparison Summary

| Feature | Namespaces (Option 1) | Policy Routing (Option 2) |
|---------|----------------------|--------------------------|
| **Implementation Time** | ~6 months | ~4 months |
| **Memory Overhead** | 2-10 MB/tunnel | <100 KB/tunnel |
| **DNS Isolation** | ✅ Yes (native) | ⚠️ Shared (needs DoH) |
| **Debugging** | Hard (nsenter) | Easy (direct tools) |
| **Max Tunnels** | ~50-100 | ~200-250 |
| **Complexity** | Higher | Medium |
| **Security** | Strong isolation | Weaker (shared stack) |
| **User Command** | `tunnel switch` | `tunnel mark` |
| **Recommended?** | If DNS isolation critical | ✅ **Yes, simpler & faster** |

---

## 📋 TODO File Sizes & Scope

### `TODO_OPTION1.md` (44 KB)
**8,300+ words** covering:
- ✅ Phases 0-9 + Future
- ✅ Complete directory structure
- ✅ Code examples for all major classes
- ✅ Testing strategy (unit, integration, system)
- ✅ Packaging for DEB/RPM/Arch
- ✅ Security hardening
- ✅ Polkit integration
- ✅ Adapter implementations (Proton, Psiphon, WireGuard)
- ✅ Timeline: ~24 weeks (6 months)

### `TODO_OPTION2.md` (19 KB)
**3,500+ words** covering:
- ✅ Phases 0-5 (condensed)
- ✅ Policy routing specifics
- ✅ cgroup + iptables integration
- ✅ Comparison table
- ✅ Implementation differences from Option 1
- ✅ Timeline: ~13 weeks (3.25 months)

**Both files include**:
- Ready-to-copy code snippets
- Error handling examples
- Package configuration snippets
- Success criteria checklists
- Risk analysis

---

## 🎯 How to Use These Documents

### Step 1: Read the Overview
```bash
cat MULTI_TUNNEL_ARCHITECTURE.md
```
Understand the two approaches, their trade-offs, and which might be right.

### Step 2: Compare Details
```bash
cat QUICK_REFERENCE.md
```
See side-by-side comparison table and decision matrix.

### Step 3: Dive Into Chosen Option
```bash
less multi-tunnel-namespace/TODO_OPTION1.md
# OR
less multi-tunnel-policy-routing/TODO_OPTION2.md
```

The TODO is **your implementation roadmap**. It includes:
- What to build (tasks with checkboxes)
- How to build it (code examples)
- When to build it (estimated timelines)
- What to watch out for (risks & mitigations)

### Step 4: Start with Phase 0
Each TODO starts with **Phase 0: Research & PoC**:
1. Build proof-of-concept to validate routing strategy
2. Study existing implementations (docker, systemd-nspawn, mwan3)
3. Formalize API specifications
4. Create empty repository structure

### Step 5: Work Through Phases Sequentially
The TODO is designed to be **dependencies-aware**:
- Phase 1 (Core Library) must precede Phase 2 (Daemon)
- Phase 2 must precede Phase 3 (CLI changes)
- Phase 4-5 can overlap

Check off tasks as you complete them in the TODO file itself.

---

## 📁 Directory Structure Explained

```
/home/dacineu/dev/proton-vpn-cli/
├── CURRENT RELEASE (0.1.8)
│   ├── proton/                    # Current CLI source
│   ├── service/                   # protonvpn.service
│   ├── debian/                    # Debian packaging
│   ├── rpmbuild/                  # RPM packaging
│   ├── versions.yml               # Version history
│   ├── TODO_0.1.8.md              # ✅ What was done for 0.1.8
│   ├── IMPLEMENTATION_DOCUMENTATION_0.1.8.md
│   ├── DAEMON_INTEGRATION_0.1.8.md
│   ├── ARCH_LINUX_SUMMARY.md
│   └── ALL_CHANGES_SUMMARY.md
│
├── MULTI-TUNNEL DESIGN (Not Yet Implemented)
│   ├── MULTI_TUNNEL_ARCHITECTURE.md  # ← START HERE
│   ├── QUICK_REFERENCE.md
│   │
│   ├── multi-tunnel-namespace/       # Option 1: Namespaces
│   │   ├── TODO_OPTION1.md          # Full implementation plan
│   │   ├── docs/
│   │   ├── src/                     # Empty, to be filled
│   │   ├── packaging/
│   │   └── tests/
│   │
│   └── multi-tunnel-policy-routing/ # Option 2: Policy Routing
│       ├── TODO_OPTION2.md          # Implementation plan
│       ├── docs/
│       ├── src/
│       ├── packaging/
│       └── tests/
│
└── This file (MULTI_TUNNEL_INDEX.md)
```

---

## 🎓 Prerequisites & Dependencies

### For Implementation

**Technical knowledge needed**:
- Python async/await (asyncio)
- Linux networking: iproute2, iptables, TUN/TAP
- D-Bus protocol and `dbus-fast` library
- Systemd service files and Polkit rules
- Python packaging (setuptools, pyproject.toml)
- Debian/RPM/Arch packaging basics

**External dependencies**:
- `proton-vpn-api-core` (must support multi-tunnel or be forked/patched)
- `proton-keyring-linux` (for credentials)
- `dbus-fast` (for D-Bus communication)
- `pyroute2` (optional, for programmatic ip/route control)
- `systemd` (for service management)
- `iproute2` package (`ip` command)
- `iptables` or `nftables`

**Access needed**:
- `proton-vpn-api-core` source repository
- Proton VPN daemon documentation
- Possibly forked repository to add multi-tunnel support

---

## 🚦 Current State

### ✅ Completed (v0.1.8)
- Free tier location selection
- `servers list` command
- Daemon existence check
- Arch Linux packaging
- Documentation generation

### 🔜 Next Big Feature: Multi-Tunnel
- **Not started** (only planning documents created)
- Two complete approaches documented
- Ready for implementation decision

---

## ⚖️ Decision Checklist

Before starting implementation, answer:

1. **Can proton-vpn-api-core be patched for multi-tunnel?**
   - [ ] Check codebase for `VPNConnector.get()` (singleton?)
   - [ ] Can we create multiple connectors simultaneously?
   - [ ] How does it manage TUN device names?
   - [ ] Talk to daemon team

2. **Which routing strategy?**
   - [ ] Option 1 if DNS isolation critical
   - [ ] Option 2 if faster implementation desired
   - [ ] Could support both with runtime choice

3. **Resource allocation**:
   - [ ] Dedicated developer(s) for 3-6 months?
   - [ ] Testing environment (VMs with different distros)
   - [ ] CI/CD pipeline for multi-tunnel testing

4. **Distribution readiness**:
   - [ ] Will Debian/RPM/Arch accept daemon with CAP_NET_ADMIN?
   - [ ] Polkit rules acceptable?
   - [ ] Need separate package or part of existing?

---

## 📈 Suggested Path Forward

### Week 1: Research & Decision
1. Read both TODO files (skim, don't deep-dive yet)
2. Build PoC for **both** routing strategies (2-3 days each)
3. Meet with daemon team to assess feasibility
4. Decide: Option 1, Option 2, or hybrid

### Week 2: Setup & API Design
1. Create chosen project repository (or main branch)
2. Define formal interface specification (API + D-Bus)
3. Implement PoC with real proton-vpn-api-core (if possible)
4. Validate approach, adjust design

### Week 3-16: Implementation
Follow Phases 1-5 from chosen TODO:
- Core library
- Daemon
- CLI
- Testing
- Packaging

### Week 17-20: Polish & Release
- Documentation
- Security hardening
- Package for distros
- Beta release

---

## 📚 Document Legend

| Document | Purpose | Audience |
|----------|---------|----------|
| `MULTI_TUNNEL_ARCHITECTURE.md` | Overview of both approaches | Decision-makers, architects |
| `QUICK_REFERENCE.md` | Side-by-side comparison | Anyone evaluating options |
| `TODO_OPTION1.md` | Complete implementation plan | Developers building namespaces |
| `TODO_OPTION2.md` | Complete implementation plan | Developers building policy routing |
| `TODO_0.1.8.md` | What was done in 0.1.8 | Anyone, release notes |
| This file | Index & navigation | Anyone starting |

---

## 🔗 Related Documents

Also see in main repo:
- `CODEBASE_ANALYSIS.md` - Understanding current architecture
- `DAEMON_INTEGRATION_0.1.8.md` - How daemon check works
- `IMPLEMENTATION_DOCUMENTATION_0.1.8.md` - 0.1.8 feature details
- `ARCH_LINUX_PACKAGING.md` - Arch-specific packaging
- `ALL_CHANGES_SUMMARY.md` - Complete change log

---

## ❓ Frequently Asked Questions

**Q: Can I start implementing without Proton daemon changes?**
A: Yes, but you'll hit a wall when trying to create multiple tunnels. The daemon currently supports only one connection. You must either:
   - Fork/patch `proton-vpn-api-core` to allow multiple connectors
   - Create separate daemon instances (complex, port conflicts)
   - Design around single-tunnel limitation (not true multi-tunnel)

**Q: Which option is more future-proof?**
A: Both are viable. Namespaces (Option 1) is more "correct" Linux way, but policy routing (Option 2) is simpler and widely used (Docker, mwan3). Neither is deprecated.

**Q: Can we support both and let user choose?**
A: Yes! The architecture with `RoutingStrategy` abstraction already supports both. Just implement both `NetworkNamespaceRouting` and `PolicyRouting`. Daemon config selects default. CLI could have `--routing=` flag. Slightly more code but maximum flexibility.

**Q: What about Windows/macOS?**
A: This design is Linux-specific (network namespaces, iptables, cgroups). For other OSes, you'd need different backend (Windows: Windows Filtering Platform, macOS: Network Extension framework). The `VPNAdapter` abstraction already allows per-OS implementations.

**Q: When will this be implemented?**
A: Not started yet. Requires:
   1. Decision on approach
   2. Resources allocated (developer time)
   3. Proton daemon team buy-in for multi-tunnel support
   4. Testing on multiple distros

---

## ✉️ Contact & Collaboration

If you're interested in working on this:
1. Read the relevant TODO file
2. Build the PoC from Phase 0
3. Submit a proof-of-concept PR or patch
4. Discuss with Proton VPN team

---

## 📝 License

All planning documents are part of the Proton VPN CLI repository and licensed under GPLv3 same as the codebase.

---

**Bottom line**: Two complete, production-ready plans await. Choose a path and start with Phase 0. The heavy design work is done - now it's implementation.
