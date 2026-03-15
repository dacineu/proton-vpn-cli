
"""
Server listing commands.

Copyright (c) 2025 Proton AG

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
import click
from tabulate import tabulate

from proton.vpn.cli.core.run_async import run_async
from proton.vpn.cli.core.controller import Controller
from proton.vpn.cli.core.exceptions import AuthenticationRequiredError, CountryCodeError, CountryNameError, RequiresHigherTierError
from proton.vpn.cli.commands.account import SIGNIN_COMMAND
from proton.vpn.cli.commands.command_utils import (
    inform_that_expired_serverlist_will_be_updated_if_necessary,
    compose_requested_features,
    FEATURES_TO_DISPLAY,
)
from proton.vpn.session.servers.types import ServerFeatureEnum
from proton.vpn.session import ServerList


def _print_usage_error(msg: str):
    raise click.UsageError(msg)


@click.group()
def servers():
    """Server listing commands"""
    pass


SERVERS_COMMAND = servers.name
SERVERS_LIST_COMMAND = "list"


@servers.command(name=SERVERS_LIST_COMMAND)
@click.option(
    "--country",
    default=None,
    help="""\b
            Filter by country
            Country code (US, GB, DE) or full name ("United States")"""
)
@click.option(
    "--city",
    default=None,
    help="""\b
            Filter by city name
            Use quotes for multi-word cities: "New York" """
)
@click.option('--p2p', is_flag=True, help="Filter to P2P servers")
@click.option('--securecore', is_flag=True, help="Filter to Secure Core servers")
@click.option('--tor', is_flag=True, help="Filter to Tor servers")
@click.pass_context
@run_async
async def list_servers(ctx, country, city, p2p, securecore, tor):
    """Display available servers matching filters"""
    controller = await Controller.create(params=ctx.obj, click_ctx=ctx)

    # Enforce tier restrictions: free users cannot filter by features
    free_user = controller.user_tier == 0
    if free_user and (p2p or securecore or tor):
        raise RequiresHigherTierError

    await inform_that_expired_serverlist_will_be_updated_if_necessary(controller)

    try:
        server_list = await controller.get_updated_server_list()
    except AuthenticationRequiredError:
        _print_usage_error(
            "Authentication required to view server list. "
            f"Please sign in with '{controller.program_name} {SIGNIN_COMMAND}'"
        )
        return

    servers = server_list.logicals

    # Location filtering
    if city:
        servers = ServerList.get_servers_in_city(servers, city)
    elif country:
        try:
            country_code = controller.validate_country_input(country)
            servers = ServerList.get_servers_in_country_code(servers, country_code)
        except CountryCodeError:
            _print_usage_error(f"Invalid country code '{country}'. Please use a valid country code.")
            return
        except CountryNameError:
            _print_usage_error(f"Invalid country name '{country}'. Please use a valid country name.")
            return

    # Feature filtering
    requested_features = compose_requested_features(p2p, securecore, tor)
    features_excluded_by_default = ServerFeatureEnum.SECURE_CORE | ServerFeatureEnum.TOR
    # Remove explicitly requested features from the exclusion set
    features_excluded_by_default = (features_excluded_by_default & requested_features) ^ features_excluded_by_default
    servers = ServerList.get_servers_with_features(
        servers,
        request_features=requested_features,
        exclude_features=features_excluded_by_default
    )

    # Availability filter (tier, maintenance, etc.)
    servers = ServerList.get_available_servers(servers, controller.user_tier)

    # Prepare table data
    table_data = []
    for s in servers:
        feature_names = [FEATURES_TO_DISPLAY[f] for f in FEATURES_TO_DISPLAY if f in s.features]
        features_str = ', '.join(sorted(feature_names))
        city_name = s.city if s.city else ''
        table_data.append((s.name, s.entry_country_name, city_name, features_str))

    if not table_data:
        click.echo("No servers match the specified criteria.")
        return

    table = tabulate(
        table_data,
        headers=['Server', 'Country', 'City', 'Features'],
        tablefmt='simple',
        stralign='left',
        numalign='right',
    )
    click.echo(f"\nAvailable servers\n{table}\n")
