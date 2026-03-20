"""Network namespace-based routing strategy.

This implements Option 1: each tunnel gets its own network namespace
with complete isolation (routing, DNS, firewall).
"""

import asyncio
import subprocess
from typing import Dict, Set, Optional
from pathlib import Path

from ..models.exceptions import (
    NamespaceError,
    NamespaceExistsError,
    NamespaceNotFoundError,
    NamespacePermissionError,
    DeviceError,
    DeviceNotFoundError,
)
from .base import RoutingStrategy


class NetworkNamespaceRouting(RoutingStrategy):
    """
    Network namespace isolation strategy.

    Features:
      - Each tunnel in separate network namespace
      - Complete routing isolation
      - Per-namespace DNS configuration
      - Strong security boundary

    Namespace naming: vpn_{tunnel_name}
    """

    def __init__(self):
        # tunnel_name -> namespace_name
        self._namespaces: Dict[str, str] = {}
        # namespace_name -> Set of tunnel devices in that namespace
        self._tunnels_in_ns: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def create_tunnel_context(self, tunnel_name: str) -> dict:
        """
        Create a network namespace for the tunnel.

        Args:
            tunnel_name: Unique tunnel identifier

        Returns:
            {"namespace": "vpn_<tunnel_name>"}

        Raises:
            NamespaceExistsError: If namespace already exists
            NamespacePermissionError: If ip netns fails
        """
        async with self._lock:
            ns_name = f"vpn_{tunnel_name}"

            # Check if namespace already exists
            existing = await self._list_namespaces()
            if ns_name in existing:
                raise NamespaceExistsError(f"Namespace {ns_name} already exists")

            # Create namespace
            try:
                await self._run_command(["ip", "netns", "add", ns_name])
            except subprocess.CalledProcessError as e:
                raise NamespacePermissionError(
                    f"Failed to create namespace (need CAP_SYS_ADMIN): {e}"
                ) from e

            self._namespaces[tunnel_name] = ns_name
            self._tunnels_in_ns[ns_name] = set()

            return {"namespace": ns_name}

    async def destroy_tunnel_context(self, tunnel_name: str, metadata: Optional[dict] = None) -> None:
        """
        Destroy a namespace and clean up references.

        Args:
            tunnel_name: Tunnel to destroy
            metadata: Optional dict containing 'namespace' key. If not provided,
                      the namespace is looked up from internal state.
        """
        if metadata is None:
            metadata = {}
        async with self._lock:
            ns_name = metadata.get("namespace")
            if not ns_name:
                # Fallback to stored namespace for this tunnel
                ns_name = self._namespaces.get(tunnel_name)
                if not ns_name:
                    return  # Nothing to clean up

            try:
                await self._run_command(["ip", "netns", "delete", ns_name], check=False)
            except Exception as e:
                # Log but don't raise - we're cleaning up
                print(f"Warning: failed to delete namespace {ns_name}: {e}")

            # Cleanup internal state
            self._namespaces.pop(tunnel_name, None)
            self._tunnels_in_ns.pop(ns_name, None)

    async def assign_process_to_tunnel(
        self, tunnel_name: str, metadata: dict, pid: int
    ) -> None:
        """
        Move a process into a tunnel's namespace.

        This is used for `protonvpn tunnel switch` or `tunnel exec` commands.

        Args:
            tunnel_name: Tunnel name
            metadata: Must contain 'namespace' key
            pid: Process ID to move (usually current shell's PID)

        Raises:
            NamespaceNotFoundError: If namespace doesn't exist
        """
        ns_name = metadata.get("namespace")
        if not ns_name:
            raise NamespaceError("No namespace associated with tunnel")

        # Verify namespace exists
        existing = await self._list_namespaces()
        if ns_name not in existing:
            raise NamespaceNotFoundError(f"Namespace {ns_name} not found")

        # Move process to namespace using setns via /proc
        # This requires the process to have the CAP_SYS_ADMIN capability in its user namespace
        # Typically done by calling nsenter from user space, not setns directly
        # The CLI will use `nsenter` binary instead of this method
        #
        # But we can validate the namespace is accessible:
        ns_path = Path(f"/var/run/netns/{ns_name}")
        if not ns_path.exists():
            # Fallback: ip netns exec to test
            try:
                await self._run_command(
                    ["ip", "netns", "exec", ns_name, "true"], check=True
                )
            except subprocess.CalledProcessError as e:
                raise NamespacePermissionError(
                    f"Cannot access namespace {ns_name}: {e}"
                ) from e

    async def list_active_tunnels(self) -> Dict[str, dict]:
        """
        List all VPN namespaces and return their metadata.

        Returns:
            Dict mapping tunnel_name to {"namespace": ns_name}
        """
        result = {}
        for tunnel_name, ns_name in self._namespaces.items():
            result[tunnel_name] = {"namespace": ns_name}
        return result

    async def cleanup_all(self) -> None:
        """Delete all managed namespaces (called on daemon shutdown)."""
        async with self._lock:
            for tunnel_name in list(self._namespaces.keys()):
                try:
                    await self.destroy_tunnel_context(tunnel_name, {})
                except Exception as e:
                    print(f"Error cleaning up namespace for {tunnel_name}: {e}")

    # Helper methods

    async def _run_command(
        self, cmd: list, check: bool = True, capture_output: bool = False
    ) -> subprocess.CompletedProcess:
        """Run a subprocess command asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                check=check,
                capture_output=capture_output,
                text=True,
            ),
        )

    async def _list_namespaces(self) -> Set[str]:
        """Get set of all network namespace names on system."""
        try:
            result = await self._run_command(
                ["ip", "netns", "list"], capture_output=True
            )
            namespaces = set()
            for line in result.stdout.strip().split("\n"):
                if line:
                    # ip netns list output: "vpn_work (id: 2)"
                    ns_name = line.split()[0]
                    namespaces.add(ns_name)
            return namespaces
        except subprocess.CalledProcessError:
            return set()

    # Additional methods for adapter integration

    async def configure_namespace_network(
        self,
        namespace: str,
        device: str,
        vpn_ip: str,
        vpn_gateway: str,
        dns_servers: Optional[list] = None,
    ) -> None:
        """
        Configure network inside a namespace.

        Args:
            namespace: Network namespace name
            device: TUN device name (already in namespace)
            vpn_ip: Client IP assigned by VPN
            vpn_gateway: Gateway IP
            dns_servers: Optional list of DNS server IPs
        """
        # Bring up loopback
        await self._run_command_in_ns(
            namespace, ["ip", "link", "set", "lo", "up"]
        )

        # Configure TUN device IP
        await self._run_command_in_ns(
            namespace, ["ip", "addr", "add", f"{vpn_ip}/32", "dev", device]
        )

        # Bring up device
        await self._run_command_in_ns(
            namespace, ["ip", "link", "set", device, "up"]
        )

        # Set default route
        await self._run_command_in_ns(
            namespace, ["ip", "route", "add", "default", "via", vpn_gateway, "dev", device]
        )

        # Configure DNS if provided
        if dns_servers:
            await self._configure_namespace_dns(namespace, dns_servers)

    async def _run_command_in_ns(self, namespace: str, cmd: list):
        """Run a command inside the namespace via `ip netns exec`."""
        full_cmd = ["ip", "netns", "exec", namespace] + cmd
        await self._run_command(full_cmd)

    async def _configure_namespace_dns(self, namespace: str, dns_servers: list):
        """Configure DNS resolution inside the namespace."""
        # Create resolv.conf content
        lines = [f"nameserver {server}" for server in dns_servers]
        resolv_content = "\n".join(lines) + "\n"

        # Use a temporary file and copy into namespace
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(resolv_content)
            temp_path = f.name

        try:
            # Copy into namespace's /etc/resolv.conf
            # We use /bin/cp because /etc might be read-only bind mount
            await self._run_command_in_ns(
                namespace, ["cp", temp_path, "/etc/resolv.conf"]
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    async def move_device_to_namespace(
        self, device: str, namespace: str
    ) -> None:
        """
        Move a network device into a namespace.

        Args:
            device: Device name (e.g., "tun0")
            namespace: Target namespace name

        Raises:
            DeviceNotFoundError: If device doesn't exist
            NamespaceNotFoundError: If namespace doesn't exist
        """
        # Verify device exists in host namespace
        try:
            await self._run_command(
                ["ip", "link", "show", device], check=True, capture_output=True
            )
        except subprocess.CalledProcessError:
            raise DeviceNotFoundError(f"Device {device} not found")

        # Verify namespace exists
        existing = await self._list_namespaces()
        if namespace not in existing:
            raise NamespaceNotFoundError(f"Namespace {namespace} not found")

        # Move device
        try:
            await self._run_command(["ip", "link", "set", device, "netns", namespace])
        except subprocess.CalledProcessError as e:
            raise NamespacePermissionError(
                f"Failed to move device to namespace (need CAP_NET_ADMIN): {e}"
            ) from e

        # Track
        if namespace in self._tunnels_in_ns:
            self._tunnels_in_ns[namespace].add(device)

    async def get_namespace_for_tunnel(self, tunnel_name: str) -> Optional[str]:
        """Get namespace name for a tunnel, if it exists."""
        return self._namespaces.get(tunnel_name)

    # Compatibility methods for legacy tests
    async def create_namespace(self, tunnel_name: str) -> str:
        """Create a namespace for the tunnel (alias for create_tunnel_context)."""
        result = await self.create_tunnel_context(tunnel_name)
        return result["namespace"]

    async def destroy_namespace(self, tunnel_name: str, metadata: Optional[dict] = None) -> None:
        """Destroy a tunnel's namespace (alias for destroy_tunnel_context)."""
        await self.destroy_tunnel_context(tunnel_name, metadata)
