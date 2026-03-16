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


async def main():
    print("=" * 60)
    print("libvpnmanager Integration Test")
    print("=" * 60)

    # Create manager with namespace routing
    routing = NetworkNamespaceRouting()
    manager = TunnelManager(routing)
    print("✓ Created TunnelManager with NetworkNamespaceRouting")

    # Register DummyAdapter
    dummy = DummyAdapter()
    manager.register_adapter(dummy)
    print(f"✓ Registered adapter: {dummy.get_adapter_name()}")

    # Create a tunnel using DummyAdapter
    # Note: DummyAdapter doesn't use config fields, just tunnel_name
    config = ConnectionConfig(
        adapter="dummy",  # Use the registered dummy adapter
        tunnel_name="test_tunnel",
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
    status = await manager.get_status(tunnel.name)
    print(f"  Status: {status.value}")

    # Get traffic stats
    stats = await manager.get_traffic_stats(tunnel.name)
    print(f"  Traffic: {stats[0]} in, {stats[1]} out")

    # List all tunnels
    tunnels = await manager.list_tunnels()
    print(f"\nActive tunnels: {len(tunnels)}")
    for t in tunnels:
        print(f"  - {t.name} ({t.adapter}) on {t.device}")

    # Create a second tunnel (demonstrates multi-tunnel capability)
    config2 = ConnectionConfig(
        adapter="dummy",
        tunnel_name="second_tunnel",
    )
    print(f"\nCreating second tunnel '{config2.tunnel_name}'...")
    tunnel2 = await manager.create_tunnel(config2)
    tunnel2 = await manager.connect_tunnel(tunnel2.name)
    print(f"  ✓ Connected!")
    print(f"    Device: {tunnel2.device}")
    print(f"    Namespace: {tunnel2.namespace}")

    tunnels = await manager.list_tunnels()
    print(f"\nNow have {len(tunnels)} active tunnels")

    # Disconnect first tunnel
    print(f"\nDisconnecting '{tunnel.name}'...")
    await manager.disconnect_tunnel(tunnel.name)
    print("  ✓ Disconnected")

    # Destroy second tunnel
    print(f"\nDestroying '{tunnel2.name}'...")
    await manager.destroy_tunnel(tunnel2.name)
    print("  ✓ Destroyed")

    # Final check
    tunnels = await manager.list_tunnels()
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
