"""
Utilities to facilitate command implementation.

Copyright (c) 2026 Proton AG

This file is part of Proton VPN.

Proton VPN is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Proton VPN is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with ProtonVPN.  If not, see <https://www.gnu.org/licenses/>.
"""
import shutil
import subprocess
import sys

import click

from proton.vpn.session.servers.types import ServerFeatureEnum
from proton.vpn.cli.core.controller import Controller


# Mapping of server features to human-readable names
FEATURES_TO_DISPLAY = {
    ServerFeatureEnum.P2P: "P2P",
    ServerFeatureEnum.SECURE_CORE: "Secure Core",
    ServerFeatureEnum.TOR: "Tor",
}


def compose_requested_features(p2p: bool, securecore: bool, tor: bool) -> ServerFeatureEnum:
    """Compose the bitmask of requested server features from flags."""
    requested_features: ServerFeatureEnum = 0
    if p2p:
        requested_features |= ServerFeatureEnum.P2P
    if securecore:
        requested_features |= ServerFeatureEnum.SECURE_CORE
    if tor:
        requested_features |= ServerFeatureEnum.TOR
    return requested_features


async def inform_that_expired_serverlist_will_be_updated_if_necessary(controller: Controller):
    """Warns user of server list update if it has expired"""
    if await controller.is_serverlist_expired():
        click.echo("Server list is outdated, updating... This may take a moment.")


def is_daemon_running() -> bool:
    """
    Checks if the protonvpn daemon is active via systemd.

    Returns:
        bool: True if daemon is active, False otherwise.
    """
    # Check if systemctl is available
    if not shutil.which("systemctl"):
        # Non-systemd systems; assume daemon is managed differently
        return True

    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "protonvpn.service"],
            capture_output=True,
            check=False
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        # If we can't check, assume it's okay and let later errors handle it
        return True


def raise_daemon_not_running_error() -> None:
    """Raises a ClickException with instructions to start the daemon."""
    raise click.ClickException(
        "Proton VPN daemon is not running.\n"
        "Please start and enable it:\n"
        "  sudo systemctl start protonvpn.service\n"
        "  sudo systemctl enable protonvpn.service"
    )
