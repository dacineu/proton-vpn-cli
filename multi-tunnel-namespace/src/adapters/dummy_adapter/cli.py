#!/usr/bin/env python3
"""Standalone dummy adapter CLI with dual-server architecture."""

import asyncio
import json
import logging
import os
import random
import struct
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from libvpnmanager.models.tunnel import Tunnel

# Configuration from environment
MTM_CONTROL_SOCKET = os.environ['MTM_CONTROL_SOCKET']
MTM_ADAPTER_TYPE = os.environ['MTM_ADAPTER_TYPE']
MTM_SESSION_NAME = os.environ.get('MTM_SESSION_NAME', '')

# Global state (will be initialized in main)
expected_session_token: Optional[str] = None
adapter_username: Optional[str] = None
adapter_session_id: Optional[str] = None
tunnels: Dict[str, Tunnel] = {}
counter = 0
lock = asyncio.Lock()
shutdown_event = asyncio.Event()
cli_server: Optional[asyncio.Server] = None
control_reader: Optional[asyncio.StreamReader] = None
control_writer: Optional[asyncio.StreamWriter] = None

logger = logging.getLogger(__name__)

async def send_control(writer: asyncio.StreamWriter, msg: Dict[str, Any]) -> None:
    """Send a length-prefixed JSON message to MTM control socket."""
    data = json.dumps(msg).encode('utf-8')
    writer.write(len(data).to_bytes(4, 'big') + data)
    await writer.drain()

async def read_control(reader: asyncio.StreamReader) -> Dict[str, Any]:
    """Read a length-prefixed JSON message from MTM control socket."""
    len_bytes = await reader.readexactly(4)
    msg_len = int.from_bytes(len_bytes, 'big')
    data = await reader.readexactly(msg_len)
    return json.loads(data.decode('utf-8'))

# Handler functions for CLI actions
async def create_tunnel(request: Dict[str, Any], writer: asyncio.StreamWriter) -> None:
    """Handle CreateTunnel action: allocate resources via MTM and simulate tunnel creation."""
    global counter, tunnels, lock, control_writer, adapter_username, adapter_session_id

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

        # Simulate connection delay
        await asyncio.sleep(random.uniform(0.5, 1.0))

        counter += 1
        device = f"dummy{counter}"

        # Prepare AllocateTunnel control message
        config = request.get('config', {})
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

        # Create Tunnel object
        tunnel = Tunnel(
            name=tunnel_name,
            adapter=MTM_ADAPTER_TYPE,
            device=device,
            namespace=namespace,
            endpoint='dummy.example.com',
            connected_at=datetime.utcnow(),
            metadata={'simulated': True},
            session_name=adapter_session_id,
            username=adapter_username
        )
        tunnels[tunnel_name] = tunnel

        response = {'status': 'success', 'tunnel': tunnel.to_dict()}
        writer.write(json.dumps(response).encode() + b'\n')
        await writer.drain()

async def destroy_tunnel(request: Dict[str, Any], writer: asyncio.StreamWriter) -> None:
    # Stub for Task 1; will be implemented in Task 3
    response = {'status': 'error', 'error': 'Not implemented'}
    writer.write(json.dumps(response).encode() + b'\n')
    await writer.drain()

async def list_tunnels(request: Dict[str, Any], writer: asyncio.StreamWriter) -> None:
    # Stub for Task 1; will be implemented in Task 3
    response = {'tunnels': []}
    writer.write(json.dumps(response).encode() + b'\n')
    await writer.drain()

async def get_status(request: Dict[str, Any], writer: asyncio.StreamWriter) -> None:
    # Stub for Task 1; will be implemented in Task 3
    response = {'status': 'disconnected'}
    writer.write(json.dumps(response).encode() + b'\n')
    await writer.drain()

async def handle_cli(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Handle incoming CLI connections with newline-delimited JSON."""
    peer = writer.get_extra_info('peername')
    addr = getattr(peer, 'unix_socket', str(peer)) if peer else "unix"
    logger.debug(f"Client connected from {addr}")
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                request = json.loads(line.decode().strip())
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON from client {addr}: {e}")
                continue

            # Session token validation will be added in Task 4

            action = request.get('action')
            if action == 'CreateTunnel':
                await create_tunnel(request, writer)
            elif action == 'DestroyTunnel':
                await destroy_tunnel(request, writer)
            elif action == 'ListTunnels':
                await list_tunnels(request, writer)
            elif action == 'GetStatus':
                await get_status(request, writer)
            else:
                response = {'status': 'error', 'error': f'Unknown action: {action}'}
                writer.write(json.dumps(response).encode() + b'\n')
                await writer.drain()
    except asyncio.IncompleteReadError:
        pass
    except Exception as e:
        logger.error(f"Error handling client {addr}: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.debug(f"Client {addr} disconnected")

async def main() -> None:
    global expected_session_token, cli_server, control_reader, control_writer, tunnels, counter

    # Read startup payload from stdin (bytes)
    stdin_reader = asyncio.get_reader()
    startup_bytes = await stdin_reader.readuntil(b'\n')
    # Zeroize the buffer after reading
    for i in range(len(startup_bytes)):
        startup_bytes[i] = 0
    startup_str = startup_bytes.decode().strip()
    try:
        data = json.loads(startup_str)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid startup payload: {e}")
        sys.exit(1)

    session_id = data.get('session_id')
    vpn_creds = data.get('vpn_credentials', {})
    totp_secret = data.get('totp_secret')
    session_token = data.get('session_token')

    if not session_id or not isinstance(vpn_creds, dict):
        logger.error("Missing required startup data")
        sys.exit(1)

    # Store expected session token for CLI validation (from stdin)
    expected_session_token = session_token

    # Store globally for handlers
    global adapter_username, adapter_session_id
    adapter_username = vpn_creds.get('username')
    adapter_session_id = session_id

    username = adapter_username
    if not username:
        logger.error("Missing username in vpn_credentials")
        sys.exit(1)

    # Derive CLI socket path
    cli_socket_path = f"/run/mtm/adapters/{username}_{MTM_ADAPTER_TYPE}.sock"

    # Ensure parent directory exists
    socket_dir = Path(cli_socket_path).parent
    socket_dir.mkdir(parents=True, exist_ok=True)

    # Remove stale socket if exists
    try:
        Path(cli_socket_path).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Could not remove stale socket: {e}")

    # Start CLI server
    cli_server = await asyncio.start_unix_server(handle_cli, cli_socket_path)
    try:
        os.chmod(cli_socket_path, 0o600)
    except Exception as e:
        logger.warning(f"Could not set socket permissions: {e}")
    logger.info(f"CLI server listening on {cli_socket_path}")

    # Connect to MTM control socket
    try:
        control_reader, control_writer = await asyncio.open_unix_connection(MTM_CONTROL_SOCKET)
    except Exception as e:
        logger.error(f"Failed to connect to control socket {MTM_CONTROL_SOCKET}: {e}")
        sys.exit(1)

    # Send Register message
    register = {
        'msg_type': 'register',
        'session_id': session_id,
        'adapter_type': MTM_ADAPTER_TYPE,
        'username': username,
        'session_token': session_token
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

    # Simulate VPN login (dummy)
    await asyncio.sleep(0.5)

    # Zeroize credential buffers: clear the dict and try to delete references
    vpn_creds.clear()
    # Also clear other sensitive data
    if totp_secret:
        # We can't zero a string, but we can drop reference
        totp_secret = None
    # Overwrite session_id? Not needed

    # Initialize state
    tunnels = {}
    counter = 0
    # Lock already created globally

    logger.info("Dummy adapter ready")

    # Wait for shutdown event (will be set by signal handler in Task 5)
    await shutdown_event.wait()

    # Note: shutdown handling will be added in Task 5

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)]
    )
    asyncio.run(main())
