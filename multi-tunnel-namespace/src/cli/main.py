"""Multi-tunnel VPN manager CLI entry point."""

import click
from .tunnel import tunnel_group
from .adapter import adapter_group


@click.group()
def cli():
    """Multi-tunnel VPN manager."""
    pass


cli.add_command(tunnel_group)
cli.add_command(adapter_group)


if __name__ == "__main__":
    cli()
