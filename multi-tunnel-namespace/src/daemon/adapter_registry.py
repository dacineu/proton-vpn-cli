"""Adapter Registry: tracks running adapter processes and their control sockets."""

import asyncio
import logging
import os
import shutil
import socket as _socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AdapterInstance:
    """Information about a running adapter process."""
    adapter_type: str
    session_name: str
    process: asyncio.subprocess.Process
    control_socket: str  # Unix socket path for CLI connections
    registered_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    last_used: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    # Extended fields for Phase 1:
    session_id: Optional[str] = None
    username: Optional[str] = None
    tunnels: set = field(default_factory=set)
    expected_session_token: Optional[str] = None


class AdapterRegistry:
    """Global registry of adapter instances managed by the daemon."""

    def __init__(self, adapter_dir: str = "/run/mtm/adapters"):
        """
        Initialize registry.

        Args:
            adapter_dir: Directory where adapter control sockets are placed.
        """
        self.adapter_dir = Path(adapter_dir)
        self.adapters: Dict[tuple[str, str], AdapterInstance] = {}  # key = (adapter_type, session_name)
        self._by_pid: Dict[int, AdapterInstance] = {}
        self._lock = asyncio.Lock()
        self._idle_timeout = 300.0  # seconds of inactivity before terminating adapter
        self._cleanup_task: Optional[asyncio.Task] = None

        # Ensure adapter_dir exists
        self.adapter_dir.mkdir(parents=True, exist_ok=True)

    async def start_cleanup_task(self):
        """Start background task that cleans up idle adapters."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self):
        """Stop cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self):
        """Periodically check for idle adapters and terminate them."""
        while True:
            try:
                await asyncio.sleep(60.0)
                now = asyncio.get_event_loop().time()
                idle_keys = []
                async with self._lock:
                    for key, adapter in self.adapters.items():
                        if now - adapter.last_used > self._idle_timeout:
                            idle_keys.append(key)
                for key in idle_keys:
                    await self.terminate_adapter(key[0], key[1])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in adapter cleanup: {e}")

    def register(self, pid: int, adapter_type: str, session_name: str, process: asyncio.subprocess.Process, control_socket: str):
        """Register a new adapter instance (called by daemon after spawn)."""
        key = (adapter_type, session_name)
        instance = AdapterInstance(
            adapter_type=adapter_type,
            session_name=session_name,
            process=process,
            control_socket=control_socket,
        )
        # Schedule a task to wait for process exit and auto-unregister
        asyncio.create_task(self._wait_for_process(pid, process))
        async def do_register():
            async with self._lock:
                if key in self.adapters:
                    logger.warning(f"Adapter {key} already registered, replacing")
                self.adapters[key] = instance
                self._by_pid[pid] = instance
                logger.info(f"Registered adapter {adapter_type} (session={session_name}) at {control_socket} (pid={pid})")
        asyncio.create_task(do_register())

    async def _wait_for_process(self, pid: int, process: asyncio.subprocess.Process):
        """Wait for process to exit and unregister."""
        try:
            await process.wait()
            logger.info(f"Adapter process {pid} exited with code {process.returncode}")
        except Exception as e:
            logger.debug(f"Error waiting for process {pid}: {e}")
        finally:
            await self._unregister_by_pid(pid)

    async def unregister(self, adapter_type: str, session_name: str) -> bool:
        """Unregister an adapter (and terminate if running)."""
        key = (adapter_type, session_name)
        async with self._lock:
            instance = self.adapters.pop(key, None)
            if instance:
                self._by_pid.pop(instance.process.pid, None)
                logger.info(f"Unregistered adapter {adapter_type} (session={session_name})")
                # Terminate process if still running
                if instance.process.returncode is None:
                    try:
                        instance.process.terminate()
                        await asyncio.wait_for(instance.process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        instance.process.kill()
                        await instance.process.wait()
                    except Exception as e:
                        logger.warning(f"Error terminating adapter {key}: {e}")
                return True
            return False

    async def _unregister_by_pid(self, pid: int) -> bool:
        """Unregister by PID (called when process exits)."""
        async with self._lock:
            instance = self._by_pid.pop(pid, None)
            if instance:
                key = (instance.adapter_type, instance.session_name)
                self.adapters.pop(key, None)
                logger.info(f"Adapter {instance.adapter_type} (session={instance.session_name}) exited (pid={pid})")
                return True
            return False

    def get_by_pid(self, pid: int) -> Optional[AdapterInstance]:
        """Get adapter instance by PID (non‑async, for quick lookup)."""
        return self._by_pid.get(pid)

    async def get_adapter_endpoint(self, adapter_type: str, session_name: str) -> Optional[str]:
        """Get the control socket path for a running adapter, if any."""
        key = (adapter_type, session_name)
        async with self._lock:
            instance = self.adapters.get(key)
            if instance:
                # Update last_used
                instance.last_used = asyncio.get_event_loop().time()
                return instance.control_socket
            return None

    async def mark_adapter_used(self, adapter_type: str, session_name: str):
        """Mark adapter as used (update last_used)."""
        key = (adapter_type, session_name)
        async with self._lock:
            instance = self.adapters.get(key)
            if instance:
                instance.last_used = asyncio.get_event_loop().time()

    async def terminate_adapter(self, adapter_type: str, session_name: str) -> bool:
        """Terminate an adapter process and remove from registry."""
        key = (adapter_type, session_name)
        async with self._lock:
            instance = self.adapters.pop(key, None)
            if instance:
                self._by_pid.pop(instance.process.pid, None)
                try:
                    if instance.process.returncode is None:
                        instance.process.terminate()
                        try:
                            await asyncio.wait_for(instance.process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            instance.process.kill()
                            await instance.process.wait()
                    logger.info(f"Terminated adapter {adapter_type} (session={session_name})")
                    # Clean up socket file
                    try:
                        Path(instance.control_socket).unlink(missing_ok=True)
                    except Exception as e:
                        logger.debug(f"Error removing socket {instance.control_socket}: {e}")
                    return True
                except Exception as e:
                    logger.error(f"Error terminating adapter {key}: {e}")
                    return False
        return False

    async def terminate_all(self):
        """Terminate all registered adapters."""
        async with self._lock:
            keys = list(self.adapters.keys())
        for adapter_type, session_name in keys:
            await self.terminate_adapter(adapter_type, session_name)

    def list_adapters(self) -> list[tuple[str, str]]:
        """List all currently registered adapters."""
        return list(self.adapters.keys())
