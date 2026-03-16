"""Unit tests for libvpnmanager models."""

import pytest
from datetime import datetime

from libvpnmanager.models import (
    Tunnel,
    TunnelStatus,
    ConnectionConfig,
    ProtonConnectionConfig,
    PsiphonConnectionConfig,
    WireGuardConnectionConfig,
)


def test_tunnel_creation():
    """Test Tunnel dataclass."""
    tunnel = Tunnel(
        name="test",
        adapter="proton",
        device="tun0",
        namespace="vpn_test",
        endpoint="server.example.com",
    )
    assert tunnel.name == "test"
    assert tunnel.adapter == "proton"
    assert tunnel.device == "tun0"
    assert tunnel.namespace == "vpn_test"
    assert tunnel.status == TunnelStatus.CONNECTED
    assert tunnel.bytes_in == 0
    assert tunnel.bytes_out == 0


def test_tunnel_to_dict():
    """Test Tunnel serialization."""
    now = datetime.utcnow()
    tunnel = Tunnel(
        name="work",
        adapter="proton",
        device="tun1",
        namespace="vpn_work",
        endpoint="us-proton.example.com",
        connected_at=now,
        bytes_in=12345,
        bytes_out=67890,
        metadata={"protocol": "wireguard"},
    )
    d = tunnel.to_dict()
    assert d["name"] == "work"
    assert d["adapter"] == "proton"
    assert d["device"] == "tun1"
    assert d["namespace"] == "vpn_work"
    assert d["endpoint"] == "us-proton.example.com"
    assert d["bytes_in"] == 12345
    assert d["bytes_out"] == 67890
    assert d["connected_at"] == now.isoformat()
    assert d["metadata"]["protocol"] == "wireguard"

    # Test round-trip
    tunnel2 = Tunnel.from_dict(d)
    assert tunnel2.name == tunnel.name
    assert tunnel2.connected_at == now


def test_tunnel_status_enum():
    """Test TunnelStatus values."""
    assert TunnelStatus.DISCONNECTED.value == "disconnected"
    assert TunnelStatus.CONNECTING.value == "connecting"
    assert TunnelStatus.CONNECTED.value == "connected"
    assert TunnelStatus.ERROR.value == "error"


def test_proton_config():
    """Test ProtonConnectionConfig."""
    config = ProtonConnectionConfig(
        tunnel_name="myvpn",
        country="US",
        protocol="wireguard",
    )
    assert config.adapter == "proton"  # auto-set
    assert config.tunnel_name == "myvpn"
    assert config.country == "US"
    assert config.protocol == "wireguard"

    d = config.to_dict()
    assert d["adapter"] == "proton"
    assert d["config_type"] == "proton"
    assert d["country"] == "US"


def test_psiphon_config():
    """Test PsiphonConnectionConfig."""
    config = PsiphonConnectionConfig(
        tunnel_name="psiphon1",
        entry_country="US",
        exit_country="DE",
        transport_protocol="tcp",
    )
    assert config.adapter == "psiphon"
    assert config.entry_country == "US"
    assert config.exit_country == "DE"
    assert config.transport_protocol == "tcp"


def test_wireguard_config():
    """Test WireGuardConnectionConfig."""
    config = WireGuardConnectionConfig(
        tunnel_name="wg1",
        config_file="/etc/wireguard/wg0.conf",
        interface_name="wg0",
    )
    assert config.adapter == "wireguard"
    assert config.config_file == "/etc/wireguard/wg0.conf"
    assert config.interface_name == "wg0"


def test_connection_config_from_dict():
    """Test ConnectionConfig.from_dict polymorphism."""
    proton_data = {
        "adapter": "proton",
        "tunnel_name": "test",
        "country": "JP",
        "protocol": "openvpn-tcp",
    }
    config = ConnectionConfig.from_dict(proton_data)
    assert isinstance(config, ProtonConnectionConfig)
    assert config.country == "JP"

    psiphon_data = {
        "adapter": "psiphon",
        "tunnel_name": "test2",
        "entry_country": "GB",
    }
    config2 = ConnectionConfig.from_dict(psiphon_data)
    assert isinstance(config2, PsiphonConnectionConfig)
    assert config2.entry_country == "GB"
