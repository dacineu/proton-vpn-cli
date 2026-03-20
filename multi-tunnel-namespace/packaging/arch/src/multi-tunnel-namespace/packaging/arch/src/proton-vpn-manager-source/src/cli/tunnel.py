"""
CLI tunnel commands for multi-tunnel VPN management.

This module would be integrated into the main protonvpn CLI.

Usage:
    protonvpn tunnel create <name> --adapter proton --session <session> --country US
    protonvpn tunnel list [--all-users] [--username <user>]
    protonvpn tunnel sessions [--adapter <adapter>] [--all-users]
    protonvpn tunnel login --adapter proton --session <name> --username <email> [--password]
    protonvpn tunnel logout --adapter proton --session <name>
    protonvpn tunnel switch <name>
    protonvpn tunnel exec <name> -- <command>
    protonvpn tunnel disconnect <name>
    protonvpn tunnel destroy <name>
    protonvpn tunnel info <name>

Features:
  - Multi-user support: tunnels are owned by OS user who created them
  - Multi-backend: proton, psiphon, wireguard, etc.
  - Session management: multiple Proton accounts, multiple Psiphon configs, etc.
"""

import asyncio
import os
import sys
import click
import subprocess
import getpass

try:
    from libvpnmanager.client import VPNManagerClient
    from libvpnmanager.models.config import (
        ProtonConnectionConfig,
        PsiphonConnectionConfig,
        WireGuardConnectionConfig,
    )
    from libvpnmanager.models.exceptions import TunnelError, SessionError
    HAS_LIBVPNMANAGER = True
except ImportError:
    HAS_LIBVPNMANAGER = False


def get_current_username() -> str:
    """Get the current OS username."""
    return os.getenv("USER", os.getenv("LOGNAME", "root"))


@click.group(name="tunnel")
def tunnel_group():
    """Manage multi-tunnel VPN connections."""
    if not HAS_LIBVPNMANAGER:
        click.echo("Error: libvpnmanager not available", err=True)
        sys.exit(1)


@tunnel_group.command()
@click.argument("name")
@click.option("--adapter", "adapter_type", default="proton",
              type=click.Choice(["proton", "psiphon", "wireguard"]),
              help="VPN backend to use")
@click.option("--session", "session_name", required=True,
              help="Session identifier (e.g., work, personal)")
@click.option("--country", help="Country code (for Proton/Psiphon)")
@click.option("--exit-country", help="Exit country (for Psiphon)")
@click.option("--protocol", default="wireguard",
              help="Protocol (wireguard, openvpn-udp, openvpn-tcp)")
@click.option("--city", help="City name (Proton)")
@click.option("--config", "config_file",
              help="WireGuard config file path (for wireguard adapter)")
async def create(name, adapter_type, session_name, country, exit_country, protocol, city, config_file):
    """Create and connect a new tunnel."""
    client = VPNManagerClient()
    try:
        await client.connect()
        username = get_current_username()

        # Build config based on adapter
        if adapter_type == "proton":
            if not country:
                click.echo("Error: --country is required for Proton adapter", err=True)
                sys.exit(1)
            config = ProtonConnectionConfig(
                adapter="proton",
                tunnel_name=name,
                session_name=session_name,
                country=country.upper(),
                protocol=protocol,
                city=city,
            )
        elif adapter_type == "psiphon":
            config = PsiphonConnectionConfig(
                adapter="psiphon",
                tunnel_name=name,
                session_name=session_name,
                entry_country=country.upper() if country else None,
                exit_country=exit_country.upper() if exit_country else None,
                transport_protocol=protocol,
            )
        elif adapter_type == "wireguard":
            if not config_file:
                click.echo("Error: --config is required for WireGuard adapter", err=True)
                sys.exit(1)
            config = WireGuardConnectionConfig(
                adapter="wireguard",
                tunnel_name=name,
                session_name=session_name,
                config_file=config_file,
            )
        else:
            click.echo(f"Error: Unknown adapter '{adapter_type}'", err=True)
            sys.exit(1)

        click.echo(f"Creating tunnel '{name}' (adapter={adapter_type}, session={session_name})...")
        tunnel = await client.create_tunnel(config, username)

        click.echo(f"✓ Tunnel '{tunnel.name}' created and connected")
        click.echo(f"  Adapter: {tunnel.adapter}")
        click.echo(f"  Session: {tunnel.session_name}")
        click.echo(f"  Owner: {tunnel.username}")
        click.echo(f"  Device: {tunnel.device}")
        if tunnel.namespace:
            click.echo(f"  Namespace: {tunnel.namespace}")
        if tunnel.endpoint:
            click.echo(f"  Endpoint: {tunnel.endpoint}")

    except (TunnelError, SessionError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        await client.disconnect()


@tunnel_group.command(name="list")
@click.option("--all-users", is_flag=True, help="List all users' tunnels (admin only)")
@click.option("--username", help="Filter by username (for admins)")
async def list_tunnels(all_users, username):
    """List tunnels."""
    client = VPNManagerClient()
    try:
        await client.connect()
        current_user = get_current_username()

        # If --username not specified, default to current user unless --all-users
        if not username and not all_users:
            username = current_user

        tunnels = await client.list_tunnels(username, all_users)

        if not tunnels:
            click.echo("No tunnels found")
            return

        click.echo(f"{'Name':<20} {'Adapter':<12} {'Session':<15} {'Owner':<12} {'Status':<12} {'Endpoint':<30}")
        click.echo("-" * 100)
        for tunnel in tunnels:
            # Get status for each tunnel
            try:
                status = await client.get_status(tunnel.name, current_user)
                status_str = status.value
            except Exception:
                status_str = "?"

            click.echo(
                f"{tunnel.name:<20} "
                f"{tunnel.adapter:<12} "
                f"{tunnel.session_name:<15} "
                f"{tunnel.username:<12} "
                f"{status_str:<12} "
                f"{tunnel.endpoint or '':<30}"
            )
    finally:
        await client.disconnect()


@tunnel_group.command(name="sessions")
@click.option("--adapter", help="Filter by adapter type (proton, psiphon, wireguard)")
@click.option("--all-users", is_flag=True, help="List all users' sessions (admin only)")
async def sessions(adapter, all_users):
    """List available VPN sessions."""
    client = VPNManagerClient()
    try:
        await client.connect()
        current_user = get_current_username()

        session_list = await client.list_sessions(
            username=current_user if not all_users else "",
            adapter=adapter or "",
            all_users=all_users
        )

        if not session_list:
            click.echo("No sessions found")
            return

        click.echo(f"{'Adapter':<12} {'Session':<20} {'Owner':<12} {'Status':<12} {'Details':<30}")
        click.echo("-" * 90)
        for sess in session_list:
            details = []
            if sess.get("user_id"):
                details.append(f"ID:{sess['user_id']}")
            if sess.get("expires_at"):
                details.append(f"exp:{sess['expires_at'][:10]}")
            if "protocols" in sess:
                details.append(f"proto:{','.join(sess['protocols'][:3])}")
            if sess.get("config_file"):
                details.append(f"config:{os.path.basename(sess['config_file'])}")

            click.echo(
                f"{sess['adapter']:<12} "
                f"{sess['session_name']:<20} "
                f"{sess['username']:<12} "
                f"{sess['status']:<12} "
                f"{' '.join(details):<30}"
            )
    finally:
        await client.disconnect()


@tunnel_group.command()
@click.argument("name")
@click.option("--username", help="Username (for admin actions)")
async def disconnect(name, username):
    """Disconnect a tunnel."""
    client = VPNManagerClient()
    try:
        await client.connect()
        current_user = get_current_username()
        user = username or current_user

        await client.disconnect_tunnel(name, user)
        click.echo(f"✓ Tunnel '{name}' disconnected")
    except TunnelError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        await client.disconnect()


@tunnel_group.command()
@click.argument("name")
@click.option("--username", help="Username (for admin actions)")
async def destroy(name, username):
    """Completely destroy a tunnel."""
    client = VPNManagerClient()
    try:
        await client.connect()
        current_user = get_current_username()
        user = username or current_user

        # Confirm
        if not click.confirm(f"Destroy tunnel '{name}'?"):
            return

        await client.destroy_tunnel(name, user)
        click.echo(f"✓ Tunnel '{name}' destroyed")
    except TunnelError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        await client.disconnect()


@tunnel_group.command()
@click.argument("name")
async def switch(name):
    """
    Switch current shell to a tunnel's network namespace.

    Example: protonvpn tunnel switch work
    """
    client = VPNManagerClient()
    try:
        await client.connect()
        current_user = get_current_username()

        tunnel = await client.get_tunnel(name, current_user)
        if not tunnel:
            click.echo(f"Error: Tunnel '{name}' not found", err=True)
            sys.exit(1)

        if not tunnel.namespace:
            click.echo(f"Error: Tunnel '{name}' has no namespace", err=True)
            sys.exit(1)

        click.echo(f"Switching to namespace '{tunnel.namespace}' (tunnel: {name})")
        click.echo("Type 'exit' to return to default namespace.\n")

        # Use nsenter to replace current process
        ns_name = tunnel.namespace
        shell = os.environ.get("SHELL", "/bin/bash")
        os.execlp(
            "nsenter",
            "nsenter", "-t", str(os.getpid()), "-n", "-m", "-u", "-i", "-p",
            ns_name,
            shell, "-i"
        )

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@tunnel_group.command()
@click.argument("name")
@click.argument("command", nargs=-1, required=True)
async def exec_(name, command):
    """
    Run a command in a tunnel's namespace.

    Example: protonvpn tunnel exec work -- firefox
    """
    client = VPNManagerClient()
    try:
        await client.connect()
        current_user = get_current_username()

        tunnel = await client.get_tunnel(name, current_user)
        if not tunnel:
            click.echo(f"Error: Tunnel '{name}' not found", err=True)
            sys.exit(1)

        if not tunnel.namespace:
            click.echo(f"Error: Tunnel '{name}' has no namespace", err=True)
            sys.exit(1)

        cmd = ["nsenter", "-t", str(os.getpid()), "-n", "-m", "-u", "-i", "-p",
               tunnel.namespace] + list(command)
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@tunnel_group.command()
@click.argument("name")
async def info(name):
    """Show detailed information about a tunnel."""
    client = VPNManagerClient()
    try:
        await client.connect()
        current_user = get_current_username()

        tunnel = await client.get_tunnel(name, current_user)
        if not tunnel:
            click.echo(f"Tunnel '{name}' not found")
            return

        click.echo(f"Tunnel: {tunnel.name}")
        click.echo(f"  Adapter: {tunnel.adapter}")
        click.echo(f"  Session: {tunnel.session_name}")
        click.echo(f"  Owner: {tunnel.username}")
        click.echo(f"  Device: {tunnel.device}")
        click.echo(f"  Namespace: {tunnel.namespace or 'N/A'}")
        click.echo(f"  Endpoint: {tunnel.endpoint or 'N/A'}")
        if tunnel.connected_at:
            click.echo(f"  Connected: {tunnel.connected_at}")
        click.echo(f"  Traffic: {tunnel.bytes_in} in, {tunnel.bytes_out} out")
    finally:
        await client.disconnect()


@tunnel_group.command(name="login")
@click.option("--adapter", "adapter_type", default="proton",
              type=click.Choice(["proton", "psiphon"]),
              help="VPN backend")
@click.option("--session", "session_name", required=True,
              help="Session name to create")
@click.option("--username", "vpn_username", required=True,
              help="VPN account username (email for Proton)")
@click.option("--password", is_flag=True, help="Prompt for password")
@click.option("--twofa", help="2FA code (if required)")
async def login(adapter_type, session_name, vpn_username, password, twofa):
    """Login to VPN service and create a session."""
    client = VPNManagerClient()
    try:
        await client.connect()
        current_user = get_current_username()

        # Get password if --password flag or if not provided
        pwd = password
        if pwd is None or pwd == "":
            pwd = getpass.getpass(f"Password for {vpn_username}: ")

        click.echo(f"Logging in to {adapter_type} as {vpn_username}...")
        session_info = await client.login(
            adapter=adapter_type,
            session_name=session_name,
            username=vpn_username,
            password=pwd,
            twofa_code=twofa or ""
        )

        click.echo(f"✓ Session '{session_name}' created successfully")
        click.echo(f"  Adapter: {session_info['adapter']}")
        click.echo(f"  Owner: {session_info['username']}")
        click.echo(f"  Status: {session_info['status']}")
        if "valid_until" in session_info and session_info["valid_until"]:
            click.echo(f"  Expires: {session_info['valid_until']}")

    except Exception as e:
        click.echo(f"Login failed: {e}", err=True)
        sys.exit(1)
    finally:
        await client.disconnect()


@tunnel_group.command(name="logout")
@click.option("--adapter", "adapter_type", default="proton",
              type=click.Choice(["proton", "psiphon"]),
              help="VPN backend")
@click.option("--session", "session_name", required=True,
              help="Session to logout")
@click.option("--username", help="Username (for admin)")
async def logout(adapter_type, session_name, username):
    """Logout and remove a session."""
    client = VPNManagerClient()
    try:
        await client.connect()
        current_user = get_current_username()
        user = username or current_user

        # Confirm
        if not click.confirm(f"Logout session '{session_name}' ({adapter_type})?"):
            return

        success = await client.logout(adapter_type, session_name, user)
        if success:
            click.echo(f"✓ Session '{session_name}' logged out and removed")
        else:
            click.echo(f"Session '{session_name}' not found or already removed")

    finally:
        await client.disconnect()
