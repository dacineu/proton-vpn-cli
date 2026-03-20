"""Entry point for Proton VPN adapter as a subprocess (two‑tier)."""

import asyncio
import json
import logging
import os
import sys
import signal
from pathlib import Path
from typing import Optional, Dict, Any

from libvpnmanager.adapters.unix_adapter_server import UnixAdapterServer
from .adapter import ProtonVPNAdapter
from libvpnmanager.sessions.proton import ProtonSession
from libvpnmanager.models.tunnel import Tunnel

logger = logging.getLogger(__name__)

# Global state (mirrors dummy adapter pattern)
expected_session_token: Optional[str] = None
adapter_username: Optional[str] = None
adapter_session_id: Optional[str] = None
adapter_instance: Optional[ProtonVPNAdapter] = None
control_reader: Optional[asyncio.StreamReader] = None
control_writer: Optional[asyncio.StreamWriter] = None
cli_server: Optional[asyncio.Server] = None
lock = asyncio.Lock()
shutdown_event = asyncio.Event()
tunnels: Dict[str, Tunnel] = {}

async def send_control(writer: asyncio.StreamWriter, msg: dict) -> None:
    """Send a length-prefixed JSON message to MTM control socket."""
    data = json.dumps(msg).encode('utf-8')
    writer.write(len(data).to_bytes(4, 'big') + data)
    await writer.drain()

async def read_control(reader: asyncio.StreamReader) -> dict:
    """Read a length-prefixed JSON message from MTM control socket."""
    len_bytes = await reader.readexactly(4)
    msg_len = int.from_bytes(len_bytes, 'big')
    data = await reader.readexactly(msg_len)
    return json.loads(data.decode('utf-8'))

async def create_tunnel(request: dict, writer: asyncio.StreamWriter) -> None:
    """Handle CreateTunnel action: allocate resources via MTM and create tunnel via adapter."""
    global tunnels, adapter_instance, control_writer, control_reader, adapter_username

    tunnel_name = request.get('tunnel_name')
    if not tunnel_name:
        writer.write(json.dumps({'status': 'error', 'error': 'Missing tunnel_name'}).encode() + b'\n')
        await writer.drain()
        return

    async with lock:
        if tunnel_name in tunnels:
            writer.write(json.dumps({'status': 'error', 'error': 'Tunnel already exists'}).encode() + b'\n')
            await writer.drain()
            return

        config = request.get('config', {})

        # Call adapter.create_tunnel to establish VPN connection
        try:
            tunnel = await adapter_instance.create_tunnel(name=tunnel_name, config=config)
        except Exception as e:
            logger.error(f"Adapter create_tunnel failed: {e}")
            writer.write(json.dumps({'status': 'error', 'error': f'Create failed: {e}'}).encode() + b'\n')
            await writer.drain()
            return

        # Send AllocateTunnel to MTM for namespace/resource allocation
        allocate_req = {
            'msg_type': 'allocate',
            'tunnel_name': tunnel_name,
            'config': config,
            'username': adapter_username
        }
        try:
            await send_control(control_writer, allocate_req)
            resp = await read_control(control_reader)
        except Exception as e:
            logger.error(f"Control communication error during allocate: {e}")
            writer.write(json.dumps({'status': 'error', 'error': 'Allocation failed'}).encode() + b'\n')
            await writer.drain()
            return

        if resp.get('msg_type') != 'allocated':
            err = resp.get('error', 'Resource allocation failed')
            logger.error(f"Allocate failed: {err}")
            writer.write(json.dumps({'status': 'error', 'error': err}).encode() + b'\n')
            await writer.drain()
            return

        namespace = resp.get('namespace')
        if not namespace:
            logger.error("Allocation response missing namespace")
            writer.write(json.dumps({'status': 'error', 'error': 'Allocation missing namespace'}).encode() + b'\n')
            await writer.drain()
            return

        # Update tunnel with allocated namespace
        tunnel.namespace = namespace
        # Store tunnel globally
        tunnels[tunnel_name] = tunnel

        # Success response to CLI
        response = {'status': 'success', 'tunnel': tunnel.to_dict()}
        writer.write(json.dumps(response).encode() + b'\n')
        await writer.drain()

async def destroy_tunnel(request: dict, writer: asyncio.StreamWriter) -> None:
    """Handle DestroyTunnel: release resources via MTM and disconnect tunnel."""
    global tunnels, control_writer, control_reader, adapter_instance

    tunnel_name = request.get('tunnel_name')
    if not tunnel_name:
        writer.write(json.dumps({'status': 'error', 'error': 'Missing tunnel_name'}).encode() + b'\n')
        await writer.drain()
        return

    async with lock:
        if tunnel_name not in tunnels:
            writer.write(json.dumps({'status': 'error', 'error': 'Tunnel not found'}).encode() + b'\n')
            await writer.drain()
            return

        # Remove from our tunnels dict before destroying
        tunnels.pop(tunnel_name)

        # Disconnect via adapter by name
        try:
            await adapter_instance.destroy_tunnel(tunnel_name)
        except Exception as e:
            logger.warning(f"Error disconnecting tunnel {tunnel_name}: {e}")
            # Continue to release anyway

        # Send ReleaseTunnel control message
        release_req = {'msg_type': 'release', 'tunnel_name': tunnel_name}
        try:
            await send_control(control_writer, release_req)
            resp = await read_control(control_reader)
        except Exception as e:
            logger.error(f"Control communication error during release: {e}")
            writer.write(json.dumps({'status': 'error', 'error': 'Release failed'}).encode() + b'\n')
            await writer.drain()
            return

        if resp.get('msg_type') != 'released':
            err = resp.get('error', 'Release failed')
            logger.error(f"Release failed: {err}")
            writer.write(json.dumps({'status': 'error', 'error': err}).encode() + b'\n')
            await writer.drain()
            return

        writer.write(json.dumps({'status': 'success'}).encode() + b'\n')
        await writer.drain()

async def list_tunnels(request: dict, writer: asyncio.StreamWriter) -> None:
    """Handle ListTunnels: return list of all tunnels."""
    async with lock:
        tunnel_list = [t.to_dict() for t in tunnels.values()]
    writer.write(json.dumps({'tunnels': tunnel_list}).encode() + b'\n')
    await writer.drain()

async def get_status(request: dict, writer: asyncio.StreamWriter) -> None:
    """Handle GetStatus: return connection status for a tunnel."""
    tunnel_name = request.get('tunnel_name')
    if not tunnel_name:
        writer.write(json.dumps({'status': 'error', 'error': 'Missing tunnel_name'}).encode() + b'\n')
        await writer.drain()
        return
    async with lock:
        exists = tunnel_name in tunnels
    status_str = 'connected' if exists else 'disconnected'
    writer.write(json.dumps({'status': status_str}).encode() + b'\n')
    await writer.drain()

async def handle_cli(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Handle incoming CLI connections (to be implemented in Task 5)."""
    # For now, just close connection
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass

async def main():
    global expected_session_token, adapter_username, adapter_session_id, adapter_instance
    global control_reader, control_writer, cli_server

    # 1. Read payload from stdin (MTM daemon spawns us with JSON on stdin)
    payload_json = sys.stdin.read()
    if not payload_json:
        logger.error("No payload received on stdin")
        return
    try:
        payload = json.loads(payload_json)
        vpn_credentials = payload['vpn_credentials']
        session_id = payload['session_id']
        # Username is inside vpn_credentials, not top-level
        vpn_username = vpn_credentials.get('username')
        if not vpn_username:
            raise KeyError('username')
        session_token = payload.get('session_token')
    except KeyError as e:
        logger.error(f"Missing required field in payload: {e}")
        return
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON payload: {e}")
        return
    except Exception as e:
        logger.error(f"Failed to parse payload: {e}")
        return

    # 2. Reconstruct ProtonSession from credentials
    try:
        session = ProtonSession.from_dict(vpn_credentials)
    except Exception as e:
        logger.error(f"Failed to create ProtonSession: {e}")
        return

    # 3. Create adapter instance and set expected session token for CLI auth
    adapter = ProtonVPNAdapter(session)
    if session_token is not None:
        adapter.expected_session_token = session_token

    # Store globals for later use (Register, handler)
    expected_session_token = session_token
    adapter_username = vpn_username
    adapter_session_id = session_id
    adapter_instance = adapter

    # 4. Get endpoints from environment (set by MTM)
    adapter_endpoint = os.getenv('ADAPTER_ENDPOINT')
    control_endpoint = os.getenv('CONTROL_ENDPOINT')
    if not adapter_endpoint or not control_endpoint:
        logger.error("ADAPTER_ENDPOINT and CONTROL_ENDPOINT must be set")
        return

    # Ensure parent directory for adapter endpoint exists
    socket_dir = Path(adapter_endpoint).parent
    socket_dir.mkdir(parents=True, exist_ok=True)

    # Remove stale socket if exists
    try:
        Path(adapter_endpoint).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Could not remove stale socket: {e}")

    # 5. Bind CLI server (dual-server pattern)
    cli_server = await asyncio.start_unix_server(handle_cli, adapter_endpoint)
    try:
        os.chmod(adapter_endpoint, 0o600)
    except Exception as e:
        logger.warning(f"Could not set socket permissions: {e}")
    logger.info(f"CLI server listening on {adapter_endpoint}")

    # 6. Connect to MTM control socket
    try:
        control_reader, control_writer = await asyncio.open_unix_connection(control_endpoint)
    except Exception as e:
        logger.error(f"Failed to connect to control socket {control_endpoint}: {e}")
        sys.exit(1)

    # 7. Send Register handshake to MTM
    register = {
        'msg_type': 'register',
        'session_id': adapter_session_id,
        'adapter_type': 'proton',
        'username': adapter_username,
        'session_token': expected_session_token
    }
    try:
        await send_control(control_writer, register)
        resp = await read_control(control_reader)
        if resp.get('msg_type') != 'registered':
            logger.error(f"Registration failed: {resp}")
            sys.exit(1)
        logger.info("Adapter registered with MTM")
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        sys.exit(1)

    # At this point, dual-server is fully set up: CLI server running, control connection established, registered.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    await shutdown_event.wait()

    # Begin graceful shutdown
    logger.info("Shutting down adapter")
    # Clean up adapter first (disconnect tunnels, logout)
    if adapter_instance:
        try:
            await adapter_instance.cleanup()
        except Exception as e:
            logger.error(f"Error during adapter cleanup: {e}")
    if cli_server:
        cli_server.close()
        await cli_server.wait_closed()
    if control_writer:
        control_writer.close()
        try:
            await control_writer.wait_closed()
        except Exception:
            pass
    # Remove socket file
    try:
        Path(adapter_endpoint).unlink(missing_ok=True)
    except Exception:
        pass
    logger.info("Adapter stopped")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(main())
