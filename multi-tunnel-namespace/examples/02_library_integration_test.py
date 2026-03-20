#!/usr/bin/env python3
"""
Integration test: libvpnmanager with DummyAdapter.

This demonstrates the library working without requiring root.
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from libvpnmanager import (
    TunnelManager,
    NetworkNamespaceRouting,
    DummyAdapter,
    ConnectionConfig,
    TunnelStatus,
)
from libvpnmanager.sessions.dummy import DummySession


async def main():
    print("=" * 60)
    print("libvpnmanager Integration Test")
    print("=" * 60)

    # Create manager with namespace routing
    routing = NetworkNamespaceRouting()
    manager = TunnelManager(routing)
    print("✓ Created TunnelManager with NetworkNamespaceRouting")

    # Register DummyAdapter class (new registry pattern)
    manager.register_adapter_type("dummy", DummyAdapter)
    print("✓ Registered DummyAdapter class")

    # Register DummySession class with the session manager
    manager.session_manager.register_adapter("dummy", DummySession)
    print("✓ Registered DummySession class")

    # Create a dummy session for testing
    # We need to have a session in the manager's session_manager
    await manager.session_manager.load_session(
        adapter="dummy",
        session_name="test_session",
        username="testuser",
        password="ignored"  # DummySession.create ignores this
    )
    print("✓ Created dummy session (test_session)")

    # Create a tunnel using DummyAdapter
    config = ConnectionConfig(
        adapter="dummy",
        tunnel_name="test_tunnel",
        session_name="test_session",
    )
    print(f"\nCreating tunnel '{config.tunnel_name}'...")
    tunnel = await manager.create_tunnel(config)
    print(f"  Tunnel created: name={tunnel.name}, device initially empty")

    # Connect the tunnel
    print("Connecting tunnel...")
    tunnel = await manager.connect_tunnel(tunnel.name)
    print(f"  ✓ Connected!")
    print(f"    Device: {tunnel.device}")
    print(f"    Namespace: {tunnel.namespace}")
    print(f"    Endpoint: {tunnel.endpoint}")
    print(f"    Connected at: {tunnel.connected_at}")

    # Check status
    status = await manager.get_status(tunnel.name, username="testuser")
    print(f"  Status: {status.value}")

    # Get traffic stats
    stats = await manager.get_traffic_stats(tunnel.name, username="testuser")
    print(f"  Traffic: {stats[0]} in, {stats[1]} out")

    # List all tunnels
    tunnels = await manager.list_tunnels(username="testuser")
    print(f"\nActive tunnels: {len(tunnels)}")
    for t in tunnels:
        print(f"  - {t.name} ({t.adapter}) on {t.device}")

    # Create a second tunnel (demonstrates multi-tunnel capability)
    config2 = ConnectionConfig(
        adapter="dummy",
        tunnel_name="second_tunnel",
        session_name="test_session",
    )
    print(f"\nCreating second tunnel '{config2.tunnel_name}'...")
    tunnel2 = await manager.create_tunnel(config2)
    tunnel2 = await manager.connect_tunnel(tunnel2.name, username="testuser")
    print(f"  ✓ Connected!")
    print(f"    Device: {tunnel2.device}")
    print(f"    Namespace: {tunnel2.namespace}")

    tunnels = await manager.list_tunnels(username="testuser")
    print(f"\nNow have {len(tunnels)} active tunnels")

    # Disconnect first tunnel
    print(f"\nDisconnecting '{tunnel.name}'...")
    await manager.disconnect_tunnel(tunnel.name, username="testuser")
    print("  ✓ Disconnected")

    # Destroy second tunnel
    print(f"\nDestroying '{tunnel2.name}'...")
    await manager.destroy_tunnel(tunnel2.name, username="testuser")
    print("  ✓ Destroyed")

    # Final check
    tunnels = await manager.list_tunnels(username="testuser")
    print(f"\nRemaining tunnels: {len(tunnels)}")

    # Clean shutdown
    print("\nShutting down manager...")
    await manager.shutdown()
    print("✓ Done!")

    print("\n" + "=" * 60)
    print("Integration test passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
