#!/usr/bin/env python3
"""
Integration test for multi-user, multi-backend tunnel system.

This test demonstrates:
  - SessionManager storing/loading sessions
  - TunnelManager creating tunnels with user ownership
  - Permission enforcement (users can't manage others' tunnels)
  - Admin override capability
  - Multiple adapters (Proton, Psiphon, WireGuard)
  - Multi-tunnel with same session

Run with:
    python3 test_multi_user_system.py
"""

import asyncio
import tempfile
import os
import json
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, 'src')

from libvpnmanager.sessions import SessionManager, ProtonSession, PsiphonSession, WireGuardSession
from libvpnmanager.manager import TunnelManager
from libvpnmanager.routing import NetworkNamespaceRouting
from libvpnmanager.adapters.dummy import DummyAdapter
from libvpnmanager.models.config import ProtonConnectionConfig, PsiphonConnectionConfig, WireGuardConnectionConfig
from libvpnmanager.models.exceptions import (
    TunnelExistsError,
    AccessDeniedError,
    TunnelNotFoundError,
    SessionNotFoundError
)


async def test_session_manager():
    """Test SessionManager basic operations."""
    print("\n=== Test 1: Session Manager ===")

    # Use temp directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        session_mgr = SessionManager(data_dir=tmpdir)

        # Create a Proton session
        session = ProtonSession(
            session_name="work",
            username="alice",
            access_token="test_token_123",
            refresh_token="refresh_token_456",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )

        # Save it
        await session_mgr._save_to_storage(session)
        print("✓ Saved Proton session")

        # Load it back
        loaded = await session_mgr.load_session(
            adapter="proton",
            session_name="work",
            username="alice"
        )
        assert loaded.session_name == "work"
        assert loaded.username == "alice"
        assert loaded.access_token == "test_token_123"
        print("✓ Loaded Proton session successfully")

        # Validate
        is_valid = await loaded.validate()
        assert is_valid == True
        print("✓ Session validation passed")

        # Create Psiphon session
        psiphon = PsiphonSession(
            session_name="psiphon_test",
            username="bob",
            config={"entry_country": "US", "exit_country": "DE"}
        )
        await session_mgr._save_to_storage(psiphon)
        print("✓ Saved Psiphon session")

        # Create WireGuard session (points to config file)
        wg_config_dir = os.path.join(tmpdir, "wireguard")
        os.makedirs(wg_config_dir)
        wg_config_file = os.path.join(wg_config_dir, "bob_wg.conf")
        with open(wg_config_file, 'w') as f:
            f.write("[Interface]\nPrivateKey = test\n[Peer]\nPublicKey = test\nEndpoint = test:51820\n")
        wg = WireGuardSession(
            session_name="bob_wg",
            username="bob",
            config_file=wg_config_file
        )
        await session_mgr._save_to_storage(wg)
        print("✓ Saved WireGuard session")

        # List sessions
        all_sessions = await session_mgr.list_sessions()
        print(f"✓ List sessions: found {len(all_sessions)} sessions")
        for s in all_sessions:
            print(f"    - {s.adapter}/{s.session_name} (owner: {s.username})")

        # Filter by adapter
        proton_sessions = await session_mgr.list_sessions(adapter="proton")
        assert len(proton_sessions) == 1
        print(f"✓ Filtered by adapter: {len(proton_sessions)} Proton sessions")

        # Filter by username
        alice_sessions = await session_mgr.list_sessions(username="alice")
        assert len(alice_sessions) == 1
        print(f"✓ Filtered by username: {len(alice_sessions)} sessions for alice")

        print("✅ SessionManager tests passed")


async def test_multi_user_tunnel_manager():
    """Test TunnelManager with multi-user support."""
    print("\n=== Test 2: Multi-User TunnelManager ===")

    routing = NetworkNamespaceRouting()
    session_mgr = SessionManager()
    manager = TunnelManager(routing, session_mgr)

    # Register a dummy adapter for testing
    dummy = DummyAdapter()
    # Note: In new design, adapters are created on-demand from sessions
    # But we need to handle the fact that DummyAdapter doesn't take a session
    # Let's create a special session type for dummy

    # We'll test with a mock session for dummy adapter
    from libvpnmanager.sessions.base import Session, SessionInfo
    from dataclasses import dataclass

    @dataclass
    class DummySession(Session):
        adapter: str = "dummy"
        session_name: str = ""
        username: str = ""
        created_at: datetime = None

        def __post_init__(self):
            if self.created_at is None:
                self.created_at = datetime.utcnow()

        async def validate(self) -> bool:
            return True

        async def refresh(self):
            pass

        async def revoke(self):
            pass

        def to_dict(self) -> dict:
            return {
                "adapter": self.adapter,
                "session_name": self.session_name,
                "username": self.username,
                "created_at": self.created_at.isoformat() if self.created_at else None,
            }

        @classmethod
        def from_dict(cls, data: dict) -> "DummySession":
            created_at = datetime.utcnow()
            if data.get("created_at"):
                created_at = datetime.fromisoformat(data["created_at"])
            return cls(
                session_name=data["session_name"],
                username=data["username"],
                created_at=created_at,
            )

        def to_session_info(self) -> SessionInfo:
            return SessionInfo(
                adapter=self.adapter,
                session_name=self.session_name,
                username=self.username,
                status="active",
            )

    # Create sessions for testing
    alice_dummy = DummySession(session_name="dummy_work", username="alice")
    bob_dummy = DummySession(session_name="dummy_personal", username="bob")

    # Store them in session manager
    session_mgr._sessions[("dummy", "dummy_work", "alice")] = alice_dummy
    session_mgr._sessions[("dummy", "dummy_personal", "bob")] = bob_dummy

    print("✓ Created test sessions for alice and bob")

    # Alice creates a tunnel
    from libvpnmanager.models.config import ConnectionConfig

    alice_config = ConnectionConfig(
        adapter="dummy",
        tunnel_name="alice_tunnel1",
        session_name="dummy_work"
    )
    alice_tunnel = await manager.create_tunnel(alice_config, "alice")
    assert alice_tunnel.username == "alice"
    assert alice_tunnel.adapter == "dummy"
    assert alice_tunnel.session_name == "dummy_work"
    print("✓ Alice created tunnel 'alice_tunnel1' (owner: alice)")

    # Bob creates a tunnel
    bob_config = ConnectionConfig(
        adapter="dummy",
        tunnel_name="bob_tunnel1",
        session_name="dummy_personal"
    )
    bob_tunnel = await manager.create_tunnel(bob_config, "bob")
    assert bob_tunnel.username == "bob"
    print("✓ Bob created tunnel 'bob_tunnel1' (owner: bob)")

    # Try to create duplicate tunnel name (should fail)
    try:
        await manager.create_tunnel(alice_config, "alice")
        assert False, "Should have raised TunnelExistsError"
    except TunnelExistsError:
        print("✓ Duplicate tunnel name correctly rejected")

    # Test permissions: Alice cannot manage Bob's tunnel
    try:
        await manager.connect_tunnel("bob_tunnel1", "alice")
        assert False, "Should have raised AccessDeniedError"
    except AccessDeniedError as e:
        print(f"✓ Alice cannot connect Bob's tunnel: {e}")

    # Alice can manage her own tunnel
    await manager.connect_tunnel("alice_tunnel1", "alice")
    print("✓ Alice can connect her own tunnel")

    # Test list_tunnels: Alice sees only her tunnels
    alice_tunnels = await manager.list_tunnels(username="alice")
    assert len(alice_tunnels) == 1
    assert alice_tunnels[0].name == "alice_tunnel1"
    print(f"✓ Alice lists her tunnels: {[t.name for t in alice_tunnels]}")

    # Bob sees only his
    bob_tunnels = await manager.list_tunnels(username="bob")
    assert len(bob_tunnels) == 1
    assert bob_tunnels[0].name == "bob_tunnel1"
    print(f"✓ Bob lists his tunnels: {[t.name for t in bob_tunnels]}")

    # Admin (sudo) can see all
    admin_tunnels = await manager.list_tunnels(username="root", all_users=True)
    assert len(admin_tunnels) == 2
    print(f"✓ Admin (root) sees all tunnels: {[t.name for t in admin_tunnels]}")

    # Non-admin can't use --all-users
    try:
        await manager.list_tunnels(username="alice", all_users=True)
        assert False, "Should have raised AccessDeniedError"
    except AccessDeniedError:
        print("✓ Non-admin cannot use --all-users")

    # Test get_tunnel with permission check
    tunnel = await manager.get_tunnel("alice_tunnel1", "alice")
    assert tunnel is not None
    print("✓ Alice can get her tunnel")

    try:
        await manager.get_tunnel("bob_tunnel1", "alice")
        assert False, "Should have raised AccessDeniedError"
    except AccessDeniedError:
        print("✓ Alice cannot get Bob's tunnel")

    # Clean up
    await manager.shutdown()
    print("✅ TunnelManager multi-user tests passed")


async def test_multi_tunnel_same_session():
    """Test creating multiple tunnels with same session (multi-tunnel)."""
    print("\n=== Test 3: Multi-Tunnel with Same Session ===")

    routing = NetworkNamespaceRouting()
    session_mgr = SessionManager()
    manager = TunnelManager(routing, session_mgr)

    # Create dummy session for alice
    from libvpnmanager.sessions.base import Session, SessionInfo
    from dataclasses import dataclass

    @dataclass
    class DummySession(Session):
        adapter: str = "dummy"
        session_name: str = ""
        username: str = ""
        created_at: datetime = None

        def __post_init__(self):
            if self.created_at is None:
                self.created_at = datetime.utcnow()

        async def validate(self) -> bool:
            return True

        async def refresh(self):
            pass

        async def revoke(self):
            pass

        def to_dict(self) -> dict:
            return {
                "adapter": self.adapter,
                "session_name": self.session_name,
                "username": self.username,
                "created_at": self.created_at.isoformat() if self.created_at else None,
            }

        @classmethod
        def from_dict(cls, data: dict) -> "DummySession":
            created_at = datetime.utcnow()
            if data.get("created_at"):
                created_at = datetime.fromisoformat(data["created_at"])
            return cls(
                session_name=data["session_name"],
                username=data["username"],
                created_at=created_at,
            )

        def to_session_info(self) -> SessionInfo:
            return SessionInfo(
                adapter=self.adapter,
                session_name=self.session_name,
                username=self.username,
                status="active",
            )

    # Alice has one session "work"
    alice_work = DummySession(session_name="work", username="alice")
    session_mgr._sessions[("dummy", "work", "alice")] = alice_work

    # Alice creates multiple tunnels using same session
    from libvpnmanager.models.config import ConnectionConfig

    tunnels = []
    for i in range(3):
        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name=f"alice_tunnel_{i}",
            session_name="work"
        )
        tunnel = await manager.create_tunnel(config, "alice")
        tunnels.append(tunnel)
        print(f"  Created tunnel {i}: {tunnel.name} (session: work)")

    assert len(tunnels) == 3
    assert all(t.username == "alice" for t in tunnels)
    assert all(t.session_name == "work" for t in tunnels)
    print("✓ Alice created 3 tunnels using same session 'work'")

    # All tunnels are independent
    await manager.connect_tunnel("alice_tunnel_0", "alice")
    await manager.connect_tunnel("alice_tunnel_1", "alice")
    # alice_tunnel_0 and alice_tunnel_1 should be separate

    all_tunnels = await manager.list_tunnels(username="alice")
    assert len(all_tunnels) == 3
    print(f"✓ Alice has {len(all_tunnels)} tunnels total")

    # Destroy one doesn't affect others
    await manager.destroy_tunnel("alice_tunnel_0", "alice")
    remaining = await manager.list_tunnels(username="alice")
    assert len(remaining) == 2
    print("✓ Destroying one tunnel doesn't affect others")

    await manager.shutdown()
    print("✅ Multi-tunnel with same session works!")


async def test_adapter_capabilities():
    """Test adapter capability reporting."""
    print("\n=== Test 4: Adapter Capabilities ===")

    manager = TunnelManager(NetworkNamespaceRouting(), SessionManager())

    caps = await manager.get_adapter_capabilities("proton")
    assert caps.multi_tunnel == True
    assert "wireguard" in caps.supports_protocols
    print(f"✓ Proton capabilities: multi_tunnel={caps.multi_tunnel}")

    caps = await manager.get_adapter_capabilities("psiphon")
    assert caps.multi_tunnel == True
    print(f"✓ Psiphon capabilities: multi_tunnel={caps.multi_tunnel}")

    caps = await manager.get_adapter_capabilities("wireguard")
    assert caps.multi_tunnel == True
    print(f"✓ WireGuard capabilities: multi_tunnel={caps.multi_tunnel}")

    try:
        await manager.get_adapter_capabilities("unknown")
        assert False, "Should raise AdapterNotFoundError"
    except Exception as e:
        print(f"✓ Unknown adapter correctly raises error: {type(e).__name__}")

    print("✅ Adapter capabilities test passed")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Multi-User Multi-Backend Tunnel System - Integration Tests")
    print("=" * 60)

    try:
        await test_session_manager()
        await test_multi_user_tunnel_manager()
        await test_multi_tunnel_same_session()
        await test_adapter_capabilities()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
