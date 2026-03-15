# Proton VPN CLI - Codebase Analysis

**Date**: 2026-03-15
**Version**: 0.1.7
**Repository**: https://github.com/ProtonMail/python-protonvpn-cli
**License**: GPLv3
**Language**: Python 3.9+
**Codebase size**: ~3,934 lines of Python (excluding tests)

---

## Executive Summary

This is the official **Proton VPN CLI client** for Linux, developed by Proton AG. It's a Python-based command-line interface that provides core VPN functionality with WireGuard protocol support. The project is currently in **early access/alpha** (v0.1.7) and under active development.

The codebase demonstrates solid engineering practices with clear separation of concerns, async/await patterns, and comprehensive error handling. However, there are opportunities for refactoring to improve maintainability as the project grows.

---

## Architecture

### Design Pattern
- **CLI Framework**: `Click` for command-line interface and argument parsing
- **Async/Await**: Extensive use of `asyncio` for non-blocking I/O operations
- **Controller Pattern**: Central `Controller` class manages business logic
- **Command Pattern**: Each CLI command is a separate module under `commands/`
- **Service Layer**: Relies on external Proton packages for core functionality

### Directory Structure
```
proton/vpn/cli/
├── __init__.py                    # Entry point, main CLI group
├── commands/
│   ├── account.py                # signin, signout, info
│   ├── server.py                 # connect, disconnect
│   ├── location_discovery.py     # countries, cities
│   ├── settings.py               # config subcommands
│   └── command_utils.py          # Shared utilities
└── core/
    ├── controller.py             # Main business logic (584 lines)
    ├── exceptions.py             # Custom exception types
    ├── exception_handler.py      # Global exception handling + Sentry
    ├── run_async.py              # Async decorator for Click commands
    └── wait_for_current_tasks.py # Async task synchronization
```

---

## Key Components

### 1. Controller (`core/controller.py`)

The heart of the application with primary responsibilities:

- Manages `ProtonVPNAPI` instance
- Handles authentication (login/logout with 2FA)
- Server discovery and filtering (by country, city, features)
- Connection management (connect/disconnect with event waiting)
- Settings persistence with connection-aware behavior
- Tier-based feature restrictions (free vs paid)
- Country code/name validation

**Notable implementation details:**
- Connection event synchronization using `_wait_for_event()` context manager
- Settings changes that require restart (IPv6, Custom DNS) are marked with `requires_restart=True`
- When connected and saving settings, waits for CONNECTED event to confirm feature application
- Server filtering excludes SECURE_CORE and TOR by default unless explicitly requested
- Free tier (tier 0) restrictions enforced across multiple operations

### 2. CLI Commands

#### Authentication & Info
- `protonvpn signin <username>` - Interactive auth with 2FA prompt
- `protonvpn signout` - Logout, disconnects if active
- `protonvpn info` - Display account name

#### Connection
- `protonvpn connect [server_name]` - Connect with optional filters:
  - `--country <code|name>` - Connect to fastest server in country
  - `--city <name>` - Connect to fastest server in city
  - `--p2p` - Connect to fastest P2P server
  - `--securecore` / `-sc` - Connect to fastest Secure Core server
  - `--tor` - Connect to fastest Tor server
  - `--random` - Connect to random available server
- `protonvpn disconnect` - Terminate VPN connection

#### Discovery (require authentication)
- `protonvpn countries list` - List all available countries with codes
- `protonvpn cities list <country>` - List cities in specified country with available features

#### Configuration
- `protonvpn config` - Configuration command group
  - **Boolean toggles** (`protonvpn config set <feature> <off|on>`):
    - `vpn-accelerator` (requires subscription)
    - `moderate-nat` (requires subscription)
    - `ipv6` (free tier, requires restart)
    - `anonymous-crash-reports` (free tier)
    - `port-forwarding` (requires subscription)
  - **Special settings**:
    - `kill-switch` (`off|standard`) (free tier)
    - `netshield` (`off|malware-only|malware-ads-trackers`) (requires subscription)
    - `custom-dns` (`off|on [--dns <ips>]`) (requires subscription, requires restart when enabled)
  - `protonvpn config list` - Show current configuration

### 3. Exception Handling

Custom exceptions provide clear user-facing error messages:

| Exception | Purpose |
|-----------|---------|
| `AuthenticationRequiredError` | User must sign in |
| `AuthenticationFailedError` | Invalid credentials |
| `Authentication2FAFailedError` | Invalid 2FA code |
| `SignoutRequiredError` | Must sign out before operation |
| `RequiresHigherTierError` | Free user accessing paid feature |
| `VPNConnectionError` | Connection establishment failed |
| `CountryCodeError` / `CountryNameError` | Invalid country specification |
| `InvalidDNS` | Invalid DNS IP address provided |

Global exception handler integrates with **Sentry** for crash reporting and suppresses expected cancellations.

### 4. Async Infrastructure

- **`run_async` decorator**: Wraps Click command callbacks to run async functions via `asyncio.run()`
- **`_wait_for_event()`**: Context manager that registers a state subscriber, waits for specific connection states, times out after 10s default
- **`wait_for_current_tasks()`**: Used during disconnect to wait for background tasks to complete (10s timeout)

---

## Data Flow: Connect Operation

1. CLI parses arguments via Click
2. `Controller.create()` initializes controller, loads settings
3. `find_logical_server()` fetches server list and applies filters:
   - Auth check
   - Tier check for paid features
   - Server name lookup OR country/city + feature + availability filtering
   - Selects fastest or random server
4. `Controller.connect(server)`:
   - Refreshes certificate if necessary
   - Disconnects if already connected
   - Calls `_connect()`:
     - Gets VPN server configuration from local agent
     - Loads current settings (protocol)
     - Calls `connector.connect(vpn_server, protocol)`
   - Waits for CONNECTED event (or timeout/error)
5. On success, displays server name, location, and IP address
6. Shows OpenVPN warning if using OpenVPN protocol (not fully supported)

---

## Dependencies

### Runtime (`setup.py:install_requires`)
- `proton-core` - Proton core library (authentication, logging)
- `proton-vpn-api-core` - API client and data refresher
- `proton-keyring-linux` - Secure credential storage
- `proton-vpn-local-agent` - Local VPN agent (handles actual connection)
- `click` - CLI framework
- `dbus-fast` - DBus communication (GUI detection, possibly agent comms)
- `tabulate` - Table formatting for output

### Development (`extras_require["development"]`)
- `pytest`, `pytest-asyncio`, `pytest-coverage` - Testing framework
- `flake8`, `pylint` - Linting
- `proton-core-internal` - Internal testing APIs
- `packaging` - Version handling

**Note**: Proton packages are not available on PyPI; require internal package index configuration.

---

## Testing

**Framework**: pytest with asyncio support
**Configuration**: `setup.cfg` enables coverage: `--cov=proton`
**Test Locations**: `tests/unit/` mirroring source structure

### Test Files
- `test_controller.py` - Core controller logic (connection flow, tier checks, settings)
- `test_exception_handler.py` - Exception handling behavior
- `commands/test_account.py` - Authentication commands
- `commands/test_server.py` - Connect/disconnect commands
- `commands/test_settings.py` - Configuration commands
- `commands/test_location_discovery.py` - Countries/cities commands
- `commands/conftest.py` - Shared fixtures

### Coverage Highlights
- Authentication flows (including 2FA)
- Free vs paid tier enforcement
- Connection lifecycle (auto-disconnect before reconnect, error cleanup)
- Settings save behavior (with/without active connection)
- Server filtering logic
- Country validation

---

## Build & Packaging

### Package Formats
- **DEB** (Debian/Ubuntu) - Controlled by `debian/` directory
- **RPM** (Fedora/RHEL) - Controlled by `rpmbuild/` directory

### Version Management

Single source of truth: `versions.yml` (YAML format with version history)

```yaml
version: 0.1.7
time: 2026/02/17 13:56
author: Richard Paterson
email: richard.paterson@proton.ch
urgency: low
stability: unstable
description:
- "feat: simplify cities listing command"
- "fix: recover from manually deleted cache (Elena Svilpe)"
...
```

**Build script**: `scripts/create_changelogs.py` generates:
- `debian/changelog` (Debian format)
- `rpmbuild/SPECS/package.spec` (RPM spec file from template)
- `CHANGELOG.md` (Markdown changelog)

### CI/CD

`.gitlab-ci.yml` includes external pipeline from:
```yaml
include:
  - project: 'ProtonVPN/Linux/integration/ci-libraries'
    ref: develop
    file: 'develop-pipeline.yml'
```

Uses git submodule for `scripts/devtools` (versioning utilities).

---

## Current Feature Set (v0.1.7)

### Implemented Features
- ✅ Connect/disconnect with WireGuard protocol
- ✅ Server selection by name, country, city, or feature flags
- ✅ Free tier support (limited to available free servers only)
- ✅ Account management with 2FA
- ✅ Settings: kill switch, NetShield, custom DNS, IPv6, port forwarding, VPN accelerator, moderate NAT
- ✅ Country and city discovery (requires authentication)
- ✅ Configuration listing
- ✅ OpenVPN protocol warning (not fully supported, recommends WireGuard)

### Known Limitations (from README)
- Cannot run alongside Proton VPN GUI app (checked via DBus)
- No server list command (use connection filters instead)
- Advanced features like split tunneling may be pending

---

## Code Quality Observations

### Strengths
- ✅ Clean separation of concerns (commands, core logic, utilities)
- ✅ Consistent error handling with purpose-built exceptions
- ✅ Good test coverage for controller logic (mocked dependencies)
- ✅ Proper async patterns with event waiting and timeouts
- ✅ User-friendly output with `tabulate` for tables
- ✅ Sensible tier-based access control
- ✅ Connection state awareness (waits for CONNECTED event)
- ✅ Comprehensive docstrings with copyright headers

### Areas for Improvement
- ⚠️ **Controller size**: 584 lines; may benefit from decomposition (e.g., server filtering, settings management)
- ⚠️ **Complexity**: Some methods have high cyclomatic complexity (`find_logical_server`: ~50 lines with many branches)
- ⚠️ **Magic numbers**: Timeout values (10s) hard-coded in multiple places (`controller.py`, `wait_for_current_tasks.py`)
- ⚠️ **Pylint suppressions**: `# pylint: disable=too-many-arguments`, `too-many-locals`, `too-many-branches` indicate complexity issues
- ⚠️ **Logic leakage**: Free user limitation messages are in `server.py`而不是 encapsulated in controller/exceptions
- ⚠️ **Type hints**: Incomplete (some `Any`, missing return types)
- ⚠️ **External submodule**: `scripts/devtools` dependency for versioning

### Style Guide
- PEP 8 with **100 character line length** (from `setup.cfg`)
- Copyright headers in every file
- Google-style docstrings
- Mixed use of `# noqa` comments and pylint suppressions

---

## Integration Points

- **Local Agent** (`proton-vpn-local-agent`): Handles actual VPN connection, likely via NetworkManager or wpa_supplicant
- **Keyring** (`proton-keyring-linux`): Secure credential storage
- **API** (`proton-vpn-api-core`): Communication with Proton VPN servers, certificate management, server list fetching
- **DBus**: Session bus used to detect if GUI app is running (`org.freedesktop.DBus.ListNames`)

---

## Security Considerations

- Credentials handled via `getpass` (no echo) and stored in system keyring
- Certificate freshness checked before connection (`refresher.update_certificate_if_necessary()`)
- Error reporting to Sentry can be disabled by not enabling `ExceptionHandler`
- Connection features validated against user tier to prevent unauthorized access
- Custom DNS IPs validated via `CustomDNSEntry.new_from_string()`

---

## Recent Development Activity

From `git log` and `versions.yml`:

| Version | Date | Highlights |
|---------|------|------------|
| **0.1.7** | 2026-02-17 | Simplify cities listing, reformat countries, recover from deleted cache, add config listing, connection settings without reconnection fix, OpenVPN warning, expanded tests, custom DNS+IPv6 restart behavior |
| 0.1.6 | 2026-01-22 | Update connection info for secure core |
| 0.1.5 | 2026-01-06 | Multiple bugfixes, add complex features (kill switch, netshield, custom dns), toggle-able features |
| 0.1.4 | 2025-12-10 | Server connection filtering, list countries, list cities |
| 0.1.3 | 2025-11-20 | Remove deprecated network manager dependency |
| 0.1.2 | 2025-11-14 | Update README |
| 0.1.1 | 2025-11-06 | Add daemon dependency, prepare for public, server ID case-insensitivity fix |
| 0.1.0 | 2025-10-27 | First release |

**Contributors**: Richard Paterson, Elena Svilpe, Alexandru Cheltuitor, Pep Llaneras

---

## Potential Risks & Technical Debt

1. **Package Dependencies**: Internal Proton packages not on PyPI; requires private index setup, making contribution harder for outsiders
2. **GUI Conflict**: Hard dependency on GUI not running; could be made optional with warning instead of exit
3. **Error Message Mixing**: Some `click.ClickException` raised directly in command files instead of bubbling from controller
4. **Tier Logic Scattering**: Free tier checks appear in both controller (`find_logical_server`) and commands (`_display_free_user_limitation` in `server.py`)
5. **Timeouts Hard-coded**: 10-second timeout in multiple locations; should be configurable constant
6. **Test Isolation**: Heavy use of mocks may not catch integration issues with real APIs

---

## Recommendations

### Short-term
1. Extract timeout constants (e.g., `DEFAULT_TIMEOUT = 10`) to avoid magic numbers
2. Consolidate tier-check logic into controller methods (remove `_display_free_user_limitation` from `server.py`)
3. Add type hints to public methods in `Controller` for better IDE support
4. Move `FEATURES_TO_DISPLAY` from `location_discovery.py` to shared constants module

### Medium-term
1. Consider breaking `Controller` into smaller classes:
   - `ServerFinder` (server filtering logic)
   - `SettingsManager` (settings CRUD with restart awareness)
   - `ConnectionManager` (connect/disconnect orchestration)
2. Create integration tests that exercise full flow with test doubles for local agent
3. Add config validation for settings before saving
4. Implement structured logging instead of print statements in `wait_for_current_tasks.py`

### Long-term
1. Evaluate if custom DNS, IPv6 restart behavior should use explicit migration logic rather than blanket "requires restart"
2. Feature flags for CLI-only vs GUI-available features to reduce coupling
3. Consider plugin architecture for settings to make adding new features easier
4. Document async state machine (connection states: Disconnected → Connecting → Connected, etc.)

---

## Execution Environment

- **Python**: 3.9+
- **Entry point**: `protonvpn=proton.vpn.cli:main` (console script)
- **Logs**: `~/.cache/Proton/VPN/logs/`
- **User config**: `~/.config/Proton/VPN/`
- **GUI concurrency check**: Checks DBus session for `proton.vpn.app.gtk` and exits if found (unless help requested)

---

## Conclusion

The Proton VPN CLI is a well-structured, functional application suitable for its alpha status. The codebase follows solid engineering practices with clear separation, async patterns, and good test coverage. The main areas for improvement center on managing complexity as features grow—particularly around the central `Controller` class and tier-based logic. With incremental refactoring, this codebase can scale nicely to a full-featured, stable product.
