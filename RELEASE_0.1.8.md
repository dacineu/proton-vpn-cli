# Release 0.1.8

## Release Information
- **Version**: 0.1.8
- **Release Date**: 2026-03-15
- **Branch**: stable
- **Commit**: 1dbcbcc
- **Tag**: v0.1.8
- **Author**: dacineu <dacineu@pm.me>

---

## What's New

### Major Features

#### 1. Free Tier Server Selection by Location
Free tier users can now specify server locations using `--country` and `--city` flags:

```bash
# Connect to fastest free server in US
protonvpn connect --country US

# Connect to fastest free server in Tokyo
protonvpn connect --city "Tokyo"
```

Previously, free users could only run `protonvpn connect` with no arguments (fastest free server globally). This enhancement gives free users more flexibility while maintaining tier-based restrictions on paid-only features.

#### 2. New `servers list` Command
Introducing `protonvpn servers list` - a powerful command to browse available servers with filtering:

```bash
# List all available servers
protonvpn servers list

# Filter by country
protonvpn servers list --country DE

# Filter by city
protonvpn servers list --city "New York"

# Filter by features (paid only)
protonvpn servers list --country US --p2p

# Combine filters
protonvpn servers list --country JP --securecore --tor
```

The command displays a table with:
- Server name
- Country
- City
- Features (P2P, Secure Core, Tor)

Free users see only free-tier servers; paid users see all servers they have access to.

---

## Changes Summary

### Code Changes (11 files modified, 561 insertions, 76 deletions)

| File | Changes |
|------|---------|
| `proton/vpn/cli/commands/servers.py` | **NEW**: Complete implementation of servers list command |
| `proton/vpn/cli/core/controller.py` | Modified: Removed country/city from free tier restrictions |
| `proton/vpn/cli/commands/command_utils.py` | Refactor: Moved shared constants and added helper |
| `proton/vpn/cli/commands/location_discovery.py` | Refactor: Use shared FEATURES_TO_DISPLAY |
| `proton/vpn/cli/commands/server.py` | Refactor: Use shared helper, removed duplicate code |
| `proton/vpn/cli/__init__.py` | Register new `servers` command |
| `tests/unit/test_controller.py` | Removed tests for country/city free tier restrictions |
| `tests/unit/commands/test_server.py` | Updated tests to reflect new behavior |
| `tests/unit/commands/test_location_discovery.py` | Updated imports for shared constant |
| `versions.yml` | Added version 0.1.8 entry |
| `CODEBASE_ANALYSIS.md` | **NEW**: Comprehensive codebase analysis |

---

## Technical Notes

### Free Tier Behavior Changes
- **Before**: Free users could not use `--country` or `--city` options (raised `RequiresHigherTierError`)
- **After**: Free users can now use these location filters, connecting to the fastest server in that location from the free server pool

The server-side API still enforces tier-based access, so free users only see free servers regardless of filters.

### Backward Compatibility
✅ All existing commands continue to work as before.
✅ Free tier still restricted from paid features (server_name, p2p, securecore, tor, random).
✅ All 74 unit tests passing.

---

## Testing

### Test Results
```
============================= test session starts ==============================
platform linux -- Python 3.14.3, pytest-8.4.2, pluggy-1.6.0
collected 74 items

tests/unit/commands/test_account.py .................... PASSED [ 20%]
tests/unit/commands/test_location_discovery.py ........ PASSED [ 38%]
tests/unit/commands/test_server.py .................... PASSED [ 65%]
tests/unit/commands/test_settings.py .................. PASSED [ 75%]
tests/unit/test_controller.py ......................... PASSED [ 90%]
tests/unit/test_exception_handler.py .................. PASSED [100%]

============================== 74 passed in 1.74s ==============================
```

---

## Installation & Upgrade

### From Source (Development)
```bash
git clone https://github.com/ProtonMail/python-protonvpn-cli.git
cd python-protonvpn-cli
git checkout v0.1.8
git submodule update --init --recursive  # Required for build scripts

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .[development]
```

### Package Build
To build Debian/RPM packages:

```bash
# Generate changelog and spec files (requires devtools submodule)
python3 scripts/create_changelogs.py

# Build packages (example for Debian)
dpkg-buildpackage -us -uc -b

# Or for RPM
rpmbuild -bb rpmbuild/SPECS/package.spec
```

**Note**: The `scripts/devtools` submodule must be initialized for `create_changelogs.py` to work.

---

## Known Issues & Limitations

See README.md for current limitations:
- OpenVPN protocol not fully supported (warning displayed)
- Cannot run alongside Proton VPN GUI app
- Advanced features like split tunneling may be in development

---

## Credits

Thanks to:
- Richard Paterson
- Elena Svilpe
- Alexandru Cheltuitor
- Pep Llaneras
- dacineu (release 0.1.8 contributions)

---

## License

GPLv3 - See LICENSE and COPYING.md files.
