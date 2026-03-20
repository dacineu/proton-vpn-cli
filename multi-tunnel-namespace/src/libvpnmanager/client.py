"""High-level VPN Manager client.

This client works with any IPC transport (unix-socket, dbus, websocket).
It provides a convenient interface for CLI tools to communicate with the daemon.
"""

import asyncio
import json
import os
from typing import Dict, Any, List, Optional

from .ipc import get_client_transport, TransportConfig, list_transports
from .models.tunnel import Tunnel
from .models.status import TunnelStatus
from .models.config import ConnectionConfig
from .models.exceptions import TunnelError, DBusError


class ManagerClient:
    """
    Async client for the proton-vpn-manager daemon using configurable IPC transport.

    Usage:
        client = ManagerClient(transport='unix-socket')  # or from env PROTONVPN_IPC
        await client.connect()
        try:
            tunnels = await client.list_tunnels(username)
            ...
        finally:
            await client.disconnect()
    """

    def __init__(self, transport: Optional[str] = None):
        """
        Initialize client.

        Args:
            transport: IPC transport type ('unix-socket', 'dbus', 'websocket').
                      If None, read from PROTONVPN_IPC env var or default to 'unix-socket'.
        """
        self.transport_type = transport or os.getenv('PROTONVPN_IPC', 'unix-socket')
        self._client = None
        self.connected = False

    async def connect(self) -> None:
        """Connect to the daemon."""
        config = TransportConfig(self.transport_type)
        self._client = get_client_transport(self.transport_type, config)
        await self._client.connect()
        self.connected = True

    async def disconnect(self) -> None:
        """Disconnect from the daemon."""
        if self._client:
            await self._client.disconnect()
            self._client = None
        self.connected = False

    # Tunnel management methods

    async def create_tunnel(
        self,
        config: ConnectionConfig,
        username: str,
        connect: bool = True
    ) -> Tunnel:
        """
        Create a new tunnel.

        Args:
            config: Connection configuration (ProtonConnectionConfig, etc.)
            username: OS username of tunnel owner
            connect: If True, connect immediately after creation

        Returns:
            Tunnel object
        """
        params = config.to_dict()
        params['username'] = username
        result = await self._call('CreateTunnel', params)
        tunnel = Tunnel.from_dict(result)

        if connect:
            await self.connect_tunnel(tunnel.name, username)

        return tunnel

    async def destroy_tunnel(self, name: str, username: str) -> bool:
        """Completely destroy a tunnel."""
        result = await self._call('DestroyTunnel', {'name': name, 'username': username})
        return bool(result) if result is not None else True

    async def connect_tunnel(self, name: str, username: str) -> bool:
        """Connect an existing tunnel."""
        result = await self._call('ConnectTunnel', {'name': name, 'username': username})
        return bool(result) if result is not None else True

    async def disconnect_tunnel(self, name: str, username: str) -> bool:
        """Disconnect a tunnel."""
        result = await self._call('DisconnectTunnel', {'name': name, 'username': username})
        return bool(result) if result is not None else True

    async def list_tunnels(
        self,
        username: str,
        all_users: bool = False
    ) -> List[Tunnel]:
        """List tunnels."""
        results = await self._call('ListTunnels', {'username': username, 'all_users': all_users})
        tunnels = []
        for d in results:
            tunnels.append(Tunnel.from_dict(d))
        return tunnels

    async def get_tunnel(self, name: str, username: str) -> Optional[Tunnel]:
        """Get a specific tunnel."""
        tunnels = await self.list_tunnels(username)
        for t in tunnels:
            if t.name == name:
                return t
        return None

    async def get_status(self, name: str, username: str) -> TunnelStatus:
        """Get status for a tunnel."""
        result = await self._call('GetTunnelStatus', {'name': name, 'username': username})
        # result should be like {'status': 'connected', ...}
        status_val = result.get('status', 'unknown')
        return TunnelStatus(status_val)

    async def get_traffic_stats(
        self,
        name: str,
        username: str
    ) -> tuple[int, int]:
        """Get traffic stats for a tunnel."""
        result = await self._call('GetTrafficStats', {'name': name, 'username': username})
        # Might return as list [in, out] or tuple - IPC likely returns array
        if isinstance(result, (list, tuple)) and len(result) == 2:
            return (int(result[0]), int(result[1]))
        return (0, 0)

    async def list_adapters(self) -> List[str]:
        """List registered adapter names."""
        return await self._call('ListAdapters', {})

    async def get_adapter_capabilities(self, adapter: str) -> Dict[str, Any]:
        """Get capabilities for an adapter."""
        return await self._call('GetAdapterCapabilities', {'adapter': adapter})

    async def start_adapter(
        self,
        adapter_type: str,
        credentials: Dict[str, Any],
        session_token: Optional[str] = None,
        totp_code: Optional[str] = None
    ) -> str:
        """
        Ensure adapter is running and return its CLI endpoint.

        If totp_code is provided, first call verify_2fa to obtain a session_token.

        Example:
            async with ManagerClient() as mgr:
                endpoint = await mgr.start_adapter(
                    'dummy',
                    {'username': 'alice', 'password': 'pw'},
                    totp_code='123456'
                )
                async with AdapterClient(endpoint) as adapter:
                    tunnel = await adapter.create_tunnel('personal', config)

        Returns:
            Endpoint string (e.g., 'unix:///run/mtm/adapters/alice_dummy.sock')

        Raises:
            TunnelError: If adapter startup fails or authentication is invalid.
        """
        if totp_code:
            result = await self.verify_2fa(totp_code)
            session_token = result.get('session_token')
            if not session_token:
                raise TunnelError("Failed to obtain session token from 2FA verification")

        params = {
            'adapter_type': adapter_type,
            'credentials': credentials,
        }
        if session_token:
            params['session_token'] = session_token

        result = await self._call('StartAdapter', params)
        return result['endpoint']

    async def stop_adapter(self, adapter_type: str, username: str) -> bool:
        """Stop a running adapter instance."""
        return await self._call('StopAdapter', {
            'adapter_type': adapter_type,
            'username': username,
        })

    async def ping(self) -> bool:
        """Health check."""
        return bool(await self._call('Ping', {}))

    # Session management

    async def list_sessions(
        self,
        username: str,
        adapter: str = "",
        all_users: bool = False
    ) -> List[Dict[str, Any]]:
        """List available VPN sessions."""
        result = await self._call('ListSessions', {
            'username': username,
            'adapter': adapter,
            'all_users': all_users
        })
        # result is list of dicts
        return result if isinstance(result, list) else []

    async def login(
        self,
        adapter: str,
        session_name: str,
        username: str,
        password: str,
        twofa_code: str = ""
    ) -> Dict[str, Any]:
        """Create a new session by logging in."""
        result = await self._call('Login', {
            'adapter': adapter,
            'session_name': session_name,
            'username': username,
            'password': password,
            'twofa_code': twofa_code,
        })
        return result if isinstance(result, dict) else {}

    async def logout(
        self,
        adapter: str,
        session_name: str,
        username: str
    ) -> bool:
        """Logout and remove a session."""
        result = await self._call('Logout', {
            'adapter': adapter,
            'session_name': session_name,
            'username': username,
        })
        return bool(result) if result is not None else True

    async def verify_2fa(self, totp_code: str) -> Dict[str, Any]:
        """Verify TOTP code and obtain a session token."""
        return await self._call('Verify2FA', {'totp_code': totp_code})

    # Helper

    async def _call(self, method: str, params: Dict[str, Any]) -> Any:
        """Make an IPC call."""
        if not self.connected or not self._client:
            raise TunnelError("Not connected to daemon")
        try:
            return await self._client.call_method(method, params)
        except Exception as e:
            raise TunnelError(f"IPC call failed: {e}") from e

    # Context manager support

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


class AdapterClient:
    """
    Direct client for communicating with a VPN adapter via its CLI endpoint.

    Uses newline-delimited JSON (NDJSON) protocol over a Unix socket.
    """

    def __init__(self, endpoint: str, session_token: Optional[str] = None):
        self.endpoint = endpoint
        self.session_token = session_token
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def connect(self) -> None:
        """Connect to the adapter's CLI socket."""
        path = self.endpoint.replace('unix://', '')
        self._reader, self._writer = await asyncio.open_unix_connection(path)

    async def disconnect(self) -> None:
        """Disconnect from the adapter."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    async def create_tunnel(
        self,
        tunnel_name: str,
        config: ConnectionConfig,
        totp_code: Optional[str] = None
    ) -> Tunnel:
        """Create a new tunnel via the adapter."""
        request = {
            'action': 'CreateTunnel',
            'tunnel_name': tunnel_name,
            'config': config.to_dict(),
        }
        if self.session_token:
            request['session_token'] = self.session_token
        if totp_code:
            request['totp_code'] = totp_code

        self._writer.write(json.dumps(request).encode() + b'\n')
        await self._writer.drain()

        response_line = await self._reader.readline()
        if not response_line:
            raise TunnelError("No response from adapter")
        response = json.loads(response_line.decode())

        if response.get('status') == 'error':
            raise TunnelError(response.get('error', 'Unknown error'))

        return Tunnel.from_dict(response['tunnel'])

    async def destroy_tunnel(self, tunnel_name: str) -> bool:
        """Destroy a tunnel via the adapter."""
        request = {'action': 'DestroyTunnel', 'tunnel_name': tunnel_name}
        if self.session_token:
            request['session_token'] = self.session_token

        self._writer.write(json.dumps(request).encode() + b'\n')
        await self._writer.drain()

        response_line = await self._reader.readline()
        if not response_line:
            raise TunnelError("No response from adapter")
        response = json.loads(response_line.decode())

        return response.get('status') == 'success'

    async def list_tunnels(self) -> List[Tunnel]:
        """List all tunnels from the adapter."""
        request = {'action': 'ListTunnels'}
        if self.session_token:
            request['session_token'] = self.session_token

        self._writer.write(json.dumps(request).encode() + b'\n')
        await self._writer.drain()

        response_line = await self._reader.readline()
        if not response_line:
            raise TunnelError("No response from adapter")
        response = json.loads(response_line.decode())

        tunnels = [Tunnel.from_dict(t) for t in response.get('tunnels', [])]
        return tunnels

    async def get_status(self, tunnel_name: str) -> TunnelStatus:
        """Get status of a specific tunnel."""
        request = {'action': 'GetStatus', 'tunnel_name': tunnel_name}
        if self.session_token:
            request['session_token'] = self.session_token

        self._writer.write(json.dumps(request).encode() + b'\n')
        await self._writer.drain()

        response_line = await self._reader.readline()
        if not response_line:
            raise TunnelError("No response from adapter")
        response = json.loads(response_line.decode())

        status_val = response.get('status', 'unknown')
        return TunnelStatus(status_val)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
