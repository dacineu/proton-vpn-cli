#!/usr/bin/env python3
"""
proton-vpn-manager daemon

D-Bus service that manages multiple VPN tunnels with network namespace isolation.

Run as:
    python -m daemon.daemon
or:
    proton-vpn-manager (installed entry point)

This daemon:
  - Runs as root (or with appropriate capabilities)
  - Creates network namespaces for each tunnel
  - Manages TUN devices and routing
  - Exposes D-Bus interface for CLI control
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from libvpnmanager import TunnelManager
from libvpnmanager.routing import NetworkNamespaceRouting
from libvpnmanager.sessions import SessionManager
from libvpnmanager.dbus.service import start_service

# For now, we'll add the real Proton adapter later
# from libvpnmanager.adapters.proton import ProtonVPNAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("proton-vpn-manager")


class VPNDaemon:
    """Main daemon class."""

    def __init__(self):
        self.manager: Optional[TunnelManager] = None
        self.bus = None
        self.running = False
        self._shutdown_event = asyncio.Event()

    async def start(self):
        """Start the daemon."""
        logger.info("Starting Proton VPN Manager daemon...")

        # Create manager with namespace routing and session manager
        routing = NetworkNamespaceRouting()
        session_manager = SessionManager()
        self.manager = TunnelManager(routing, session_manager)

        # NOTE: Adapters are created on-demand per session, not pre-registered
        # The manager will instantiate the appropriate adapter when a tunnel
        # is created with a specific (adapter, session_name) combination.

        # Start D-Bus service
        try:
            self.bus, service = await start_service(self.manager)
            logger.info("D-Bus service started successfully")
        except Exception as e:
            logger.error(f"Failed to start D-Bus service: {e}")
            raise

        # Handle shutdown signals
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig, lambda s=sig: asyncio.create_task(self._handle_signal(s))
            )

        self.running = True
        logger.info("Daemon ready and accepting requests")

        # Wait for shutdown
        await self._shutdown_event.wait()

        # Shutdown
        await self.shutdown()

    async def _handle_signal(self, sig: int):
        """Handle shutdown signal."""
        logger.info(f"Received signal {sig}, shutting down...")
        self._shutdown_event.set()

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down daemon...")

        if self.manager:
            await self.manager.shutdown()
            logger.info("Manager shutdown complete")

        if self.bus:
            # Disconnect from bus
            try:
                self.bus.disconnect()
            except Exception:
                pass

        logger.info("Daemon stopped")


async def main():
    """Entry point."""
    daemon = VPNDaemon()
    try:
        await daemon.start()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error(f"Daemon failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
