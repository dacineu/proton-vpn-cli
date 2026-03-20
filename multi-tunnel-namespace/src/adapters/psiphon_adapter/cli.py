"""Entry point for Psiphon adapter as a subprocess (two‑tier)."""

import asyncio
import json
import logging
import os

from libvpnmanager.adapters.unix_adapter_server import UnixAdapterServer
from .adapter import PsiphonAdapter
from libvpnmanager.sessions.psiphon import PsiphonSession

logger = logging.getLogger(__name__)

async def main():
    session_json = os.getenv('MTM_SESSION_DATA')
    if not session_json:
        logger.error("MTM_SESSION_DATA not set")
        return
    try:
        session_dict = json.loads(session_json)
        session = PsiphonSession.from_dict(session_dict)
    except Exception as e:
        logger.error(f"Failed to reconstruct session: {e}")
        return

    adapter = PsiphonAdapter(session)
    control_socket = os.getenv('MTM_CONTROL_SOCKET')
    internal_socket = os.getenv('MTM_INTERNAL_SOCKET')
    if not control_socket or not internal_socket:
        logger.error("MTM_CONTROL_SOCKET and MTM_INTERNAL_SOCKET must be set")
        return

    server = UnixAdapterServer(adapter, control_socket, internal_socket)
    try:
        await server.run()
    finally:
        await server.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(main())
