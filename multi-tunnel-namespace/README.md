# Multi-Tunnel VPN with Network Namespaces (Option 1)

Implementation plan and code for Option 1: network namespace isolation for concurrent multi-tunnel VPNs.

## Project Status

**Phase: Early Implementation (0.1.0-dev)**

Current progress:
- ✅ Phase 0: Specification & PoC
  - SPECIFICATION.md written
  - Proof-of-concept examples/01_namespace_tunnel_poc.py
- ✅ Phase 1: Core Library (libvpnmanager)
  - Data models (Tunnel, Configs, Status, Exceptions)
  - Adapter base class & DummyAdapter
  - NetworkNamespaceRouting strategy
  - TunnelManager orchestrator
  - D-Bus service & client (skeleton)
  - Package setup (pyproject.toml)
- ✅ Phase 2: Daemon Integration
  - Daemon entry point (src/daemon/daemon.py)
  - Polkit rules (packaging/polkit/60-protonvpn-manager.rules)
  - Systemd service (packaging/systemd/.../proton-vpn-manager.service)

## Quick Demo (DummyAdapter)

See [examples/README_DUMMY_DEMO.md](examples/README_DUMMY_DEMO.md) for a step-by-step demo using the DummyAdapter. In short:

```bash
# One-time: grant capabilities to the venv Python (requires sudo)
sudo examples/set_capabilities.sh

# Start the daemon
examples/start_demo.sh

# In another terminal, run the demo script
.venv/bin/python examples/demo_dummy_adapter.py
```

This will exercise login, tunnel creation, listing, status, stats, destroy, and logout without needing a real Proton account.

## What's Been Built

### libvpnmanager Library

A reusable Python library that provides:

- `TunnelManager` - Central orchestrator
- `NetworkNamespaceRouting` - Complete isolation via network namespaces
- `VPNAdapter` ABC - Base class for VPN backends
- `DummyAdapter` - Test adapter (simulates VPN)
- D-Bus interface - For remote control

### Architecture

```
+---------------------+
|   CLI (protonvpn)   |  D-Bus calls
+----------+----------+
           |
           v
+------------------------+     +----------------------+
|  TunnelManager         |<--->| VPNAdapter (Proton) |
|  - Tunnels dict        |     +----------------------+
|  - Routing strategy    |
|  - Adapter registry    |     +----------------------+
+----------+-------------+     |  Routing: Namespaces |
           |                  +----------------------+
           v
+------------------------+
|  NetworkNamespace      |
|  - Create/delete ns    |
|  - Move devices        |
|  - Configure inside    |
+------------------------+
```

## Quick Start

### 1. Install Dependencies

```bash
cd src
pip install -e .
```

Requires:
- Python 3.9+
- dbus-fast (for daemon/CLI communication)
- pyroute2 (optional, for advanced routing)

### 2. Run the Daemon (requires root)

```bash
cd src/daemon
sudo python daemon.py
```

The daemon will:
- Start D-Bus service on `org.protonvpn.Manager`
- Register the DummyAdapter
- Wait for commands

### 3. Try the PoC Script (also requires root)

```bash
cd examples
sudo python3 01_namespace_tunnel_poc.py
```

This creates a test namespace with a virtual TUN device and verifies isolation.

### 4. Test the Library

```bash
cd tests/unit
pytest test_models.py test_routing.py -v
```

## Project Structure

```
multi-tunnel-namespace/
├── docs/
│   └── SPECIFICATION.md          # Full technical specification
├── src/
│   ├── libvpnmanager/            # Core library
│   │   ├── __init__.py
│   │   ├── manager.py            # TunnelManager
│   │   ├── models/               # Data models
│   │   │   ├── tunnel.py
│   │   │   ├── config.py
│   │   │   ├── status.py
│   │   │   └── exceptions.py
│   │   ├── adapters/             # VPN backends
│   │   │   ├── base.py           # VPNAdapter ABC
│   │   │   └── dummy.py          # Test adapter
│   │   ├── routing/              # Routing strategies
│   │   │   ├── base.py           # RoutingStrategy ABC
│   │   │   └── namespace.py      # NetworkNamespaceRouting
│   │   ├── dbus/                 # D-Bus layer
│   │   │   ├── service.py
│   │   │   └── client.py
│   │   └── pyproject.toml        # Package definition
│   └── daemon/
│       └── daemon.py             # Daemon entry point
├── packaging/
│   ├── polkit/
│   │   └── 60-protonvpn-manager.rules
│   ├── systemd/
│   │   └── usr/lib/systemd/system/proton-vpn-manager.service
│   ├── deb/
│   └── rpm/
├── tests/
│   ├── unit/
│   │   ├── test_models.py
│   │   └── test_routing.py
│   └── integration/              # (to be written)
├── examples/
│   └── 01_namespace_tunnel_poc.py
├── TODO_OPTION1.md               # Full 6-month implementation plan
└── README.md                     # This file
```

## Design Decisions

### Why Network Namespaces?

- **Complete isolation**: Separate routing tables, DNS, firewall
- **Security boundary**: Strong kernel-enforced separation
- **Any app works**: No marking needed; just run in namespace
- **Clean DNS**: Each namespace can have own resolv.conf

### Trade-offs

- **Memory**: ~2-10 MB per namespace
- **Complexity**: Namespace lifecycle management
- **Debugging**: Requires `nsenter` to inspect
- **Max tunnels**: ~50-100 (limited by resources)

## Next Steps

### Short-term (Week 3-6)
- [ ] Implement real Proton VPN adapter (requires consulting proton-vpn-api-core)
- [ ] Write integration tests for full tunnel lifecycle
- [ ] Create debian/rpm packaging scripts
- [ ] Add logging framework to daemon

### Medium-term (Week 7-16)
- [ ] Implement CLI commands (`protonvpn tunnel create`, `switch`, `exec`)
- [ ] Add shell completion
- [ ] Write man pages
- [ ] Test on multiple distros (Ubuntu, Fedora, Arch)
- [ ] Security audit

### Long-term (Week 17-24)
- [ ] Submit PRs to proton-vpn-api-core for multi-tunnel support
- [ ] Package for Debian/Ubuntu (if accepted)
- [ ] Beta release
- [ ] Consider supporting Option 2 (policy routing) as alternative

## Testing

Run unit tests:

```bash
cd src/libvpnmanager
pip install pytest pytest-asyncio
pytest tests/unit/ -v
```

Run PoC (requires root):

```bash
cd examples
sudo python3 01_namespace_tunnel_poc.py
```

## Key TODO Reference

See `TODO_OPTION1.md` for the complete 24-week implementation plan with detailed tasks and code examples for every phase.

## Dependencies

### Runtime
- Python 3.9+
- iproute2 (`ip` command)
- util-linux (`nsenter` command)
- systemd-resolved (optional, for DNS)
- polkit (for privilege authorization)

### Python Packages
- dbus-fast >= 1.90.0
- pydantic >= 2.0.0
- asyncstdlib >= 3.10.0
- pyroute2 >= 0.7.0 (optional)

## License

GPLv3+ (same as proton-vpn-cli)

## Author

Proton VPN Team
