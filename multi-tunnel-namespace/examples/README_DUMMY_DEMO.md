# DummyAdapter Multi-Tunnel Demo

This demo shows the multi-tunnel VPN manager using the `DummyAdapter`. It does **not** require a real VPN subscription.

## What It Does

- Starts the `proton-vpn-manager` D-Bus daemon (or uses an existing one)
- Logs in with a dummy session (accepts any credentials)
- Creates a tunnel (in a real environment, this would also create a network namespace)
- Lists tunnels, checks status and traffic stats
- Destroys the tunnel and logs out

## Requirements

- Linux with Python 3.9+
- Virtual environment already created and `libvpnmanager` installed (`pip install -e src/`)
- **Non-root demo:** The Python interpreter in `.venv/` must have `CAP_NET_ADMIN` and `CAP_SYS_ADMIN`. Run once (as sudo):

      sudo examples/set_capabilities.sh

- **Root demo:** Alternatively, just run the daemon with `sudo` and skip the capability step.

## Quick Start (Non-Root)

1. Grant capabilities (one-time):

      sudo examples/set_capabilities.sh

2. Start daemon:

      examples/start_demo.sh

3. In another terminal, run the demo script:

      .venv/bin/python examples/demo_dummy_adapter.py

## Expected Output

```
Connected to D-Bus daemon as dacineu
Logged in: session=demo-session adapter=dummy
Created tunnel: demo-tunnel (namespace: vpn_demo-tunnel)
Your tunnels: ['demo-tunnel']
Tunnel status: name=demo-tunnel, ns=vpn_demo-tunnel, device=dummy1, state=connected
Traffic: rx=12345, tx=67890
Destroy tunnel: True
Logout: True
Disconnected from D-Bus
```

Note: If you did **not** grant capabilities, `CreateTunnel` will fail at the connection step (namespace error) but the tunnel will still be listed in a disconnected state. The demo will continue anyway.

## Files

- `demo_dummy_adapter.py` – Python demo using `libvpnmanager.client`
- `start_demo.sh` – Start the daemon in the background
- `set_capabilities.sh` – One-time capability grant for the venv Python
- `README_DUMMY_DEMO.md` – This file

## Advanced

To run the daemon as a systemd service (so it starts on boot), see the service file in `packaging/systemd/usr/lib/systemd/system/proton-vpn-manager.service`. After installing the package, enable with:

      sudo systemctl enable --now proton-vpn-manager

For development, the manual start is more convenient.
