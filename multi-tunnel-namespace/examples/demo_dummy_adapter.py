#!/usr/bin/env python3
"""
Demo: Multi-tunnel VPN using DummyAdapter via proton-vpn-manager daemon.

Prerequisites:
- Daemon running (see start_demo.sh)
- libvpnmanager installed in venv

This script:
1. Logs in with a dummy session
2. Creates a tunnel (will fail to connect if not root, but still created)
3. Lists tunnels
4. Gets tunnel status and traffic stats
5. Destroys the tunnel
6. Logs out

Run:
    .venv/bin/python examples/demo_dummy_adapter.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path so we can import libvpnmanager from the local checkout.
# This is only needed if running from the repository without installing.
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

from libvpnmanager.client import VPNManagerClient
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.exceptions import TunnelError, SessionError

async def main():
    username = os.getenv("USER", "testuser")
    session_name = "demo-session"
    tunnel_name = "demo-tunnel"

    client = VPNManagerClient()
    try:
        await client.connect()
        print(f"Connected to D-Bus daemon as {username}")
    except Exception as e:
        print(f"Could not connect to D-Bus daemon. Is it running? {e}")
        return

    # Login (dummy adapter accepts any credentials)
    try:
        sess_info = await client.login("dummy", session_name, username, "dummy_pass", "")
        print(f"Logged in: session={sess_info.session_name} adapter={sess_info.adapter}")
    except SessionError as e:
        print(f"Login note: {e} (session might already exist)")

    # Create tunnel
    config = ConnectionConfig(adapter="dummy", tunnel_name=tunnel_name, session_name=session_name)
    try:
        tunnel = await client.create_tunnel(config, username)
        print(f"Created tunnel: {tunnel.name} (namespace: {tunnel.namespace})")
    except TunnelError as e:
        print(f"Create tunnel error: {e}")
        # Continue anyway – tunnel might exist partially

    # List tunnels
    try:
        tunnels = await client.list_tunnels(username)
        print(f"Your tunnels: {[t.name for t in tunnels]}")
    except Exception as e:
        print(f"List tunnels failed: {e}")
        tunnels = []

    # Get status of our tunnel (if exists)
    if any(t.name == tunnel_name for t in tunnels):
        try:
            status = await client.get_tunnel_status(tunnel_name, username)
            print(f"Tunnel status: name={status.get('name')}, ns={status.get('namespace')}, device={status.get('device')}, state={status.get('status')}")
        except Exception as e:
            print(f"GetTunnelStatus failed: {e}")
        try:
            stats = await client.get_traffic_stats(tunnel_name, username)
            print(f"Traffic: rx={stats[0]}, tx={stats[1]}")
        except Exception as e:
            print(f"GetTrafficStats failed: {e}")
    else:
        print(f"Tunnel {tunnel_name} not found (maybe creation failed).")

    # Destroy tunnel
    try:
        destroyed = await client.destroy_tunnel(tunnel_name, username)
        print(f"Destroy tunnel: {destroyed}")
    except TunnelError as e:
        print(f"Destroy error: {e}")

    # Logout
    try:
        logged_out = await client.logout("dummy", session_name, username)
        print(f"Logout: {logged_out}")
    except SessionError as e:
        print(f"Logout error: {e}")

    await client.disconnect()
    print("Disconnected from D-Bus")

if __name__ == "__main__":
    asyncio.run(main())
