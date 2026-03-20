"""Adapter management commands."""

import click
from libvpnmanager.client import ManagerClient
from .tunnel import get_current_username  # reuse username helper


@click.group(name="adapter")
def adapter_group():
    """Manage adapter lifecycle."""
    pass


@adapter_group.command(name="list")
async def list_adapters():
    """List running adapters."""
    client = ManagerClient()
    try:
        await client.connect()
        adapters = await client.list_adapters()
        for a in adapters:
            click.echo(f"{a['type']}/{a['username']} {a['endpoint']} (tunnels: {a['tunnel_count']}, status: {a['status']})")
    finally:
        await client.disconnect()


@adapter_group.command(name="stop")
@click.argument("adapter_type", type=click.Choice(["proton", "psiphon", "wireguard", "dummy"]))
async def stop_adapter(adapter_type):
    """Stop a running adapter."""
    client = ManagerClient()
    try:
        await client.connect()
        username = get_current_username()
        await client.stop_adapter(adapter_type, username)
        click.echo(f"Adapter '{adapter_type}' stopped.")
    finally:
        await client.disconnect()


