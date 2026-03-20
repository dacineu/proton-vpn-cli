"""Mock implementation of proton.vpn.session.dataclasses.servers.LogicalServer."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class LogicalServer:
    """Mock LogicalServer representing a VPN server."""
    server_name: str
    id: str
    country: str
    entry_country: Optional[str] = None
    exit_country: Optional[str] = None
    load: int = 0


class ServerList:
    """Mock server list with filtering capabilities."""

    def __init__(self, servers):
        self._servers = list(servers)

    def filter_by_country(self, country_code):
        """Return servers matching the country code (case-insensitive)."""
        code = country_code.upper()
        return [s for s in self._servers if s.country.upper() == code]

    def get_by_id(self, server_id):
        """Find server by ID."""
        for s in self._servers:
            if s.id == server_id:
                return s
        return None

    def __iter__(self):
        return iter(self._servers)

    def __len__(self):
        return len(self._servers)

    def __getitem__(self, idx):
        return self._servers[idx]
