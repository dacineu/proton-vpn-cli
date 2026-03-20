# libvpnmanager

Multi-tunnel VPN management library with network namespace isolation.

## Overview

`libvpnmanager` provides a reusable library and daemon for managing multiple concurrent VPN tunnels, each isolated in its own network namespace. It supports multiple VPN backends (Proton VPN, Psiphon, WireGuard) through a pluggable adapter architecture.

## Features

- Create and manage multiple VPN tunnels simultaneously
- Complete network isolation via Linux network namespaces
- Per-application routing using `nsenter`
- D-Bus control interface for CLI and GUI tools
- Vendor-neutral adapter pattern

## Installation

```bash
cd multi-tunnel-namespace/src/libvpnmanager
pip install -e .
```

## Quick Example

```python
from libvpnmanager import TunnelManager, ProtonConnectionConfig
from libvpnmanager.routing import NetworkNamespaceRouting

# Create manager with namespace routing
routing = NetworkNamespaceRouting()
manager = TunnelManager(routing)

# Create and connect a tunnel
config = ProtonConnectionConfig(
    adapter="proton",
    tunnel_name="work",
    country="US"
)
tunnel = await manager.create_tunnel(config)
await manager.connect_tunnel(tunnel.name)

print(f"Tunnel {tunnel.name} connected, namespace: {tunnel.namespace}")
```

## Components

- `libvpnmanager.models` - Data structures (Tunnel, Config, Status)
- `libvpnmanager.adapters` - VPN backend implementations (Proton, Psiphon, etc.)
- `libvpnmanager.routing` - Routing strategies (NetworkNamespaceRouting, PolicyRouting)
- `libvpnmanager.manager` - TunnelManager orchestrator
- `libvpnmanager.dbus` - D-Bus service and client
- `libvpnmanager.exceptions` - Custom exception types

## Documentation

See `docs/SPECIFICATION.md` for full API specification and architecture.

## License

GPLv3+
