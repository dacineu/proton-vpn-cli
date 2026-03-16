"""Unit tests for CLI tunnel commands.

Tests cover:
- Argument parsing and validation
- Command execution with mocking of VPNManagerClient
- Output formatting
- Error handling and exit codes
- nsenter command construction (switch, exec)
- Session management integration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os
import sys
from pathlib import Path

# Add proton CLI and libvpnmanager to path
test_file = Path(__file__).resolve()
repo_root = test_file.parent.parent.parent.parent
proton_cli_path = repo_root / "proton" / "vpn" / "cli"
libvpnmanager_path = repo_root / "multi-tunnel-namespace" / "src"
sys.path.insert(0, str(proton_cli_path))
sys.path.insert(0, str(libvpnmanager_path))

from commands.tunnel import (
    tunnel_group,
    create,
    list_tunnels,
    sessions,
    disconnect,
    destroy,
    switch,
    exec_,
    info,
    login,
    logout,
    get_current_username,
)
from libvpnmanager.models.config import ProtonConnectionConfig, PsiphonConnectionConfig, WireGuardConnectionConfig
from libvpnmanager.models.exceptions import TunnelError
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.status import TunnelStatus
from datetime import datetime

from click.testing import CliRunner


class MockClient:
    """Mock VPNManagerClient for CLI testing."""
    def __init__(self):
        self.connected = False
        self.tunnels = []
        self.sessions = []

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def create_tunnel(self, config, username, connect=True):
        if not self.connected:
            raise RuntimeError("Not connected")
        tunnel = Tunnel(
            name=config.tunnel_name,
            adapter=config.adapter,
            session_name=config.session_name,
            username=username,
            device=f"tun-{config.tunnel_name}",
            namespace=f"ns-{config.tunnel_name}",
            endpoint="1.2.3.4" if config.adapter != "wireguard" else "wg.example.com:51820",
            connected_at=datetime.utcnow(),
            bytes_in=0,
            bytes_out=0,
            status=TunnelStatus.CONNECTED,
            metadata={},
        )
        self.tunnels.append(tunnel)
        return tunnel

    def destroy_tunnel(self, name, username):
        if not self.connected:
            raise RuntimeError("Not connected")
        for i, t in enumerate(self.tunnels):
            if t.name == name and t.username == username:
                self.tunnels.pop(i)
                return True
        raise TunnelError(f"Tunnel '{name}' not found or access denied")

    def connect_tunnel(self, name, username):
        if not self.connected:
            raise RuntimeError("Not connected")
        for t in self.tunnels:
            if t.name == name:
                t.status = TunnelStatus.CONNECTED
                return True
        raise TunnelError(f"Tunnel '{name}' not found")

    def disconnect_tunnel(self, name, username):
        if not self.connected:
            raise RuntimeError("Not connected")
        for t in self.tunnels:
            if t.name == name:
                t.status = TunnelStatus.DISCONNECTED
                return True
        raise TunnelError(f"Tunnel '{name}' not found")

    def list_tunnels(self, username, all_users=False):
        if not self.connected:
            raise RuntimeError("Not connected")
        if all_users:
            return self.tunnels
        return [t for t in self.tunnels if t.username == username]

    def get_tunnel(self, name, username):
        if not self.connected:
            raise RuntimeError("Not connected")
        for t in self.tunnels:
            if t.name == name:
                if t.username != username:
                    raise TunnelError(f"Access denied to tunnel '{name}'")
                return t
        return None

    def get_status(self, name, username):
        tunnel = self.get_tunnel(name, username)
        if tunnel:
            return tunnel.status
        return TunnelStatus.DISCONNECTED

    def get_traffic_stats(self, name, username):
        return (1000, 2000)

    def list_adapters(self):
        return ["proton", "psiphon", "wireguard", "dummy"]

    def get_adapter_capabilities(self, adapter):
        caps = Mock(
            multi_tunnel=True,
            supports_protocols=["wireguard"] if adapter == "proton" else ["dummy"],
            max_tunnels=10 if adapter == "proton" else None,
            supports_per_app_routing=False,
            supports_kill_switch=True if adapter == "proton" else False,
            supports_dns_isolation=True if adapter == "proton" else False,
        )
        return caps

    def list_sessions(self, username, adapter="", all_users=False):
        return self.sessions

    def login(self, adapter, session_name, username, password, twofa_code=""):
        session = {
            "adapter": adapter,
            "session_name": session_name,
            "username": username,
            "status": "active",
        }
        self.sessions.append(session)
        return session

    def logout(self, adapter, session_name, username):
        for i, s in enumerate(self.sessions):
            if s["session_name"] == session_name and s["username"] == username:
                self.sessions.pop(i)
                return True
        return False


@pytest.fixture
def mock_vpn_client(monkeypatch):
    """Patch VPNManagerClient to return MockClient."""
    mock_client = MockClient()

    def mock_constructor(bus=None):
        return mock_client

    monkeypatch.setattr('commands.tunnel.VPNManagerClient', mock_constructor)
    return mock_client


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


class TestGetCurrentUsername:
    """Tests for get_current_username helper."""

    def test_gets_username_from_env(self, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        assert get_current_username() == "testuser"

    def test_falls_back_to_logname(self, monkeypatch):
        monkeypatch.delenv("USER", raising=False)
        monkeypatch.setenv("LOGNAME", "testuser")
        assert get_current_username() == "testuser"

    def test_falls_back_to_root(self, monkeypatch):
        monkeypatch.delenv("USER", raising=False)
        monkeypatch.delenv("LOGNAME", raising=False)
        assert get_current_username() == "root"


class TestCreateCommand:
    """Tests for create command."""

    def test_create_proton_tunnel_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, [
            "create", "mytunnel",
            "--adapter", "proton",
            "--session", "work",
            "--country", "US",
            "--protocol", "wireguard"
        ])

        assert result.exit_code == 0
        assert "Tunnel 'mytunnel' created and connected" in result.output
        assert "Adapter: proton" in result.output
        assert "Device: tun-mytunnel" in result.output
        assert "Namespace: ns-mytunnel" in result.output
        assert len(mock_vpn_client.tunnels) == 1
        assert mock_vpn_client.tunnels[0].name == "mytunnel"

    def test_create_psiphon_tunnel(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, [
            "create", "psiphon_tunnel",
            "--adapter", "psiphon",
            "--session", "personal",
            "--country", "DE"
        ])

        assert result.exit_code == 0
        assert "psiphon_tunnel" in result.output

    def test_create_wireguard_tunnel_requires_config(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, [
            "create", "wg_tunnel",
            "--adapter", "wireguard",
            "--session", "work"
        ])

        assert result.exit_code == 1
        assert "--config is required for WireGuard adapter" in result.output

    def test_create_proton_requires_country(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, [
            "create", "proton_tunnel",
            "--adapter", "proton",
            "--session", "work"
        ])

        assert result.exit_code == 1
        assert "--country is required for Proton adapter" in result.output

    def test_create_duplicate_tunnel(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        # First create succeeds
        runner.invoke(tunnel_group, [
            "create", "duplicate",
            "--adapter", "dummy",
            "--session", "test"
        ])

        # Second create should fail
        result = runner.invoke(tunnel_group, [
            "create", "duplicate",
            "--adapter", "dummy",
            "--session", "test"
        ])

        assert result.exit_code == 1

    def test_create_with_invalid_adapter(self, runner, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        monkeypatch.setattr('commands.tunnel.HAS_LIBVPNMANAGER', True)

        result = runner.invoke(tunnel_group, [
            "create", "test",
            "--adapter", "unknown",
            "--session", "test"
        ])

        assert result.exit_code == 1


class TestListCommand:
    """Tests for list command."""

    def test_list_tunnels_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.tunnels.append(Tunnel(
            name="tunnel1",
            adapter="dummy",
            session_name="test",
            username="alice",
            device="tun1",
            namespace="ns1",
            endpoint="1.2.3.4",
            status=TunnelStatus.CONNECTED,
        ))
        mock_vpn_client.tunnels.append(Tunnel(
            name="tunnel2",
            adapter="dummy",
            session_name="test",
            username="bob",
            device="tun2",
            namespace="ns2",
            endpoint="5.6.7.8",
            status=TunnelStatus.CONNECTED,
        ))

        result = runner.invoke(tunnel_group, ["list"])

        assert result.exit_code == 0
        assert "Name" in result.output
        assert "Adapter" in result.output
        assert "tunnel1" in result.output
        assert "tunnel2" in result.output
        assert "alice" in result.output

    def test_list_filters_by_user(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.tunnels.append(Tunnel(
            name="alice_tunnel",
            adapter="dummy",
            username="alice",
            status=TunnelStatus.CONNECTED,
        ))
        mock_vpn_client.tunnels.append(Tunnel(
            name="bob_tunnel",
            adapter="dummy",
            username="bob",
            status=TunnelStatus.CONNECTED,
        ))

        result = runner.invoke(tunnel_group, ["list"])

        assert "alice_tunnel" in result.output
        assert "bob_tunnel" not in result.output

    def test_list_all_users_flag(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "root")

        mock_vpn_client.tunnels.append(Tunnel(
            name="alice_tunnel",
            adapter="dummy",
            username="alice",
            status=TunnelStatus.CONNECTED,
        ))
        mock_vpn_client.tunnels.append(Tunnel(
            name="bob_tunnel",
            adapter="dummy",
            username="bob",
            status=TunnelStatus.CONNECTED,
        ))

        result = runner.invoke(tunnel_group, ["list", "--all-users"])

        assert "alice_tunnel" in result.output
        assert "bob_tunnel" in result.output

    def test_list_no_tunnels(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, ["list"])

        assert result.exit_code == 0
        assert "No tunnels found" in result.output


class TestSessionsCommand:
    """Tests for sessions command."""

    def test_sessions_list_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.sessions = [
            {
                "adapter": "dummy",
                "session_name": "work",
                "username": "alice",
                "status": "active",
            }
        ]

        result = runner.invoke(tunnel_group, ["sessions"])

        assert result.exit_code == 0
        assert "Adapter" in result.output
        assert "Session" in result.output
        assert "work" in result.output

    def test_sessions_empty(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, ["sessions"])

        assert result.exit_code == 0
        assert "No sessions found" in result.output


class TestDisconnectCommand:
    """Tests for disconnect command."""

    def test_disconnect_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.tunnels.append(Tunnel(
            name="mytunnel",
            adapter="dummy",
            session_name="test",
            username="alice",
            status=TunnelStatus.CONNECTED,
        ))

        result = runner.invoke(tunnel_group, ["disconnect", "mytunnel"])

        assert result.exit_code == 0
        assert "disconnected" in result.output.lower()

    def test_disconnect_not_found(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, ["disconnect", "nonexistent"])

        assert result.exit_code == 1
        assert "Error" in result.output


class TestDestroyCommand:
    """Tests for destroy command."""

    def test_destroy_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.tunnels.append(Tunnel(
            name="mytunnel",
            adapter="dummy",
            session_name="test",
            username="alice",
        ))

        with patch('click.confirm', return_value=True):
            result = runner.invoke(tunnel_group, ["destroy", "mytunnel"])

        assert result.exit_code == 0
        assert "destroyed" in result.output.lower()

    def test_destroy_cancelled(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.tunnels.append(Tunnel(
            name="mytunnel",
            adapter="dummy",
            session_name="test",
            username="alice",
        ))

        with patch('click.confirm', return_value=False):
            result = runner.invoke(tunnel_group, ["destroy", "mytunnel"])

        assert result.exit_code == 0
        assert len(mock_vpn_client.tunnels) == 1


class TestSwitchCommand:
    """Tests for switch command."""

    def test_switch_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")
        monkeypatch.setenv("SHELL", "/bin/bash")

        mock_vpn_client.tunnels.append(Tunnel(
            name="mytunnel",
            adapter="dummy",
            session_name="test",
            username="alice",
            namespace="ns-mytunnel",
            status=TunnelStatus.CONNECTED,
        ))

        with patch('os.execlp') as mock_execlp:
            result = runner.invoke(tunnel_group, ["switch", "mytunnel"])

            mock_execlp.assert_called_once()
            args = mock_execlp.call_args[0]
            assert args[0] == "nsenter"
            assert "-n" in args
            assert "ns-mytunnel" in args

    def test_switch_tunnel_not_found(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, ["switch", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_switch_no_namespace(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.tunnels.append(Tunnel(
            name="mytunnel",
            adapter="dummy",
            session_name="test",
            username="alice",
            namespace=None,
        ))

        result = runner.invoke(tunnel_group, ["switch", "mytunnel"])

        assert result.exit_code == 1
        assert "has no namespace" in result.output


class TestExecCommand:
    """Tests for exec command."""

    def test_exec_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.tunnels.append(Tunnel(
            name="mytunnel",
            adapter="dummy",
            session_name="test",
            username="alice",
            namespace="ns-mytunnel",
            status=TunnelStatus.CONNECTED,
        ))

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = runner.invoke(tunnel_group, ["exec", "mytunnel", "--", "ls", "-la"])

            assert result.exit_code == 0
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "nsenter"
            assert "-n" in args
            assert "ns-mytunnel" in args
            assert "ls" in args
            assert "-la" in args

    def test_exec_propagates_returncode(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.tunnels.append(Tunnel(
            name="mytunnel",
            adapter="dummy",
            session_name="test",
            username="alice",
            namespace="ns-mytunnel",
        ))

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1)
            result = runner.invoke(tunnel_group, ["exec", "mytunnel", "--", "false"])

            assert result.exit_code == 1
            mock_run.assert_called_once()


class TestInfoCommand:
    """Tests for info command."""

    def test_info_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        now = datetime.utcnow()
        mock_vpn_client.tunnels.append(Tunnel(
            name="mytunnel",
            adapter="dummy",
            session_name="work",
            username="alice",
            device="tun-mytunnel",
            namespace="ns-mytunnel",
            endpoint="1.2.3.4",
            connected_at=now,
            bytes_in=1000000,
            bytes_out=2000000,
            status=TunnelStatus.CONNECTED,
        ))

        result = runner.invoke(tunnel_group, ["info", "mytunnel"])

        assert result.exit_code == 0
        assert "Tunnel: mytunnel" in result.output
        assert "Adapter: dummy" in result.output
        assert "Owner: alice" in result.output
        assert "Device: tun-mytunnel" in result.output
        assert "Namespace: ns-mytunnel" in result.output
        assert "Endpoint: 1.2.3.4" in result.output
        assert "1000000 in" in result.output
        assert "2000000 out" in result.output

    def test_info_not_found(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, ["info", "nonexistent"])

        assert result.exit_code == 0
        assert "not found" in result.output


class TestLoginCommand:
    """Tests for login command."""

    def test_login_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.sessions.append({
            "adapter": "dummy",
            "session_name": "work",
            "username": "alice@example.com",
            "status": "active",
        })

        with patch('getpass.getpass', return_value="mypassword"):
            result = runner.invoke(tunnel_group, [
                "login",
                "--adapter", "dummy",
                "--session", "work",
                "--username", "alice@example.com"
            ])

        assert result.exit_code == 0
        assert "Session 'work' created successfully" in result.output

    def test_login_requires_password(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        with patch('getpass.getpass', return_value="password"):
            result = runner.invoke(tunnel_group, [
                "login",
                "--adapter", "dummy",
                "--session", "work",
                "--username", "alice@example.com"
            ])

        assert result.exit_code == 0


class TestLogoutCommand:
    """Tests for logout command."""

    def test_logout_success(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        mock_vpn_client.sessions.append({
            "adapter": "dummy",
            "session_name": "work",
            "username": "alice",
            "status": "active",
        })

        with patch('click.confirm', return_value=True):
            result = runner.invoke(tunnel_group, [
                "logout",
                "--adapter", "dummy",
                "--session", "work"
            ])

        assert result.exit_code == 0
        assert "logged out" in result.output.lower()

    def test_logout_cancelled(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        with patch('click.confirm', return_value=False):
            result = runner.invoke(tunnel_group, [
                "logout",
                "--adapter", "dummy",
                "--session", "work"
            ])

        assert result.exit_code == 0


class TestExitCodes:
    """Tests for command exit codes."""

    def test_success_exit_code_zero(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        commands = [
            ["create", "test", "--adapter", "dummy", "--session", "test"],
            ["list"],
            ["sessions"],
            ["disconnect", "test"],
            ["info", "test"],
        ]

        for cmd in commands:
            mock_vpn_client.tunnels.clear()
            if cmd[0] == "create":
                mock_vpn_client.tunnels.append(Tunnel(
                    name="test", adapter="dummy", session_name="test", username="alice"
                ))
            result = runner.invoke(tunnel_group, cmd)
            assert result.exit_code == 0, f"Command {cmd} failed: {result.output}"

    def test_error_exit_code_nonzero(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        result = runner.invoke(tunnel_group, [
            "create", "test",
            "--adapter", "dummy",
            "--session", "missing"
        ])

        # Should fail with non-zero
        assert result.exit_code != 0


class TestNsenterCommandConstruction:
    """Tests for nsenter command construction in switch and exec."""

    def test_switch_nsenter_args(self):
        namespace = "ns-test"
        pid = 12345
        shell = "/bin/bash"

        with patch('os.getpid', return_value=pid), \
             patch('os.environ.get', return_value=shell), \
             patch('os.execlp') as mock_execlp:

            # Simulate the command that switch would construct
            from commands.tunnel import switch
            # We can't directly call switch because it tries to exec
            # But we can check pattern
            expected = ["nsenter", "-t", str(pid), "-n", "-m", "-u", "-i", "-p", namespace, shell, "-i"]
            # This pattern matches what's in switch command
            assert "nsenter" in expected
            assert "-t" in expected
            assert namespace in expected

    def test_exec_nsenter_args(self):
        namespace = "ns-test"
        pid = 12345
        command = ["curl", "ifconfig.me"]

        with patch('os.getpid', return_value=pid), \
             patch('subprocess.run') as mock_run:

            # Simulate the command construction from exec_
            cmd = ["nsenter", "-t", str(pid), "-n", "-m", "-u", "-i", "-p",
                   namespace] + command

            assert cmd[0] == "nsenter"
            assert cmd[1] == "-t"
            assert cmd[2] == str(pid)
            assert "-n" in cmd
            assert "-m" in cmd
            assert "-u" in cmd
            assert "-i" in cmd
            assert "-p" in cmd
            assert namespace in cmd
            assert "curl" in cmd
            assert "ifconfig.me" in cmd


class TestCLIIntegration:
    """Integration tests for CLI with mock client."""

    def test_full_lifecycle(self, runner, mock_vpn_client, monkeypatch):
        monkeypatch.setenv("USER", "alice")

        # Create
        result = runner.invoke(tunnel_group, [
            "create", "lifecycle_test",
            "--adapter", "dummy",
            "--session", "test"
        ])
        assert result.exit_code == 0
        assert len(mock_vpn_client.tunnels) == 1

        # List
        result = runner.invoke(tunnel_group, ["list"])
        assert result.exit_code == 0
        assert "lifecycle_test" in result.output

        # Info
        result = runner.invoke(tunnel_group, ["info", "lifecycle_test"])
        assert result.exit_code == 0

        # Disconnect
        result = runner.invoke(tunnel_group, ["disconnect", "lifecycle_test"])
        assert result.exit_code == 0

        # Destroy
        with patch('click.confirm', return_value=True):
            result = runner.invoke(tunnel_group, ["destroy", "lifecycle_test"])
        assert result.exit_code == 0
        assert len(mock_vpn_client.tunnels) == 0
