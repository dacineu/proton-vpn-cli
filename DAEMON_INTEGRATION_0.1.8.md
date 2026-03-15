# Daemon Integration for Non-Root Operation

## Overview

This document describes the changes made to ensure the Proton VPN CLI works without superuser privileges by integrating with the `protonvpn.service` systemd daemon.

**Release**: 0.1.8 (extended)
**Date**: 2026-03-15

---

## Problem

Previously, the CLI might have been assumed to require root privileges for operations, or users might have been unclear about the daemon requirement. The goal is to:

1. Ensure the CLI itself never requires superuser privileges
2. Provide clear guidance when the daemon is not running
3. Integrate systemd service management

---

## Solution

### 1. Daemon Check Utility

Added to `proton/vpn/cli/commands/command_utils.py`:

```python
def is_daemon_running() -> bool:
    """Check if the protonvpn daemon is active via systemd."""
    if not shutil.which("systemctl"):
        return True  # Non-systemd systems - assume OK
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "protonvpn.service"],
            capture_output=True, check=False
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return True  # If check fails, assume daemon available

def raise_daemon_not_running_error() -> None:
    """Raises a ClickException with instructions to start the daemon."""
    raise click.ClickException(
        "Proton VPN daemon is not running.\n"
        "Please start and enable it:\n"
        "  sudo systemctl start protonvpn.service\n"
        "  sudo systemctl enable protonvpn.service"
    )
```

**Behavior**:
- Uses `systemctl is-active` to check daemon status
- If `systemctl` not found (non-systemd), assumes daemon is managed differently
- On inactive/failed daemon, raises a user-friendly error with start/enable instructions

### 2. Integration in Connection Commands

Modified `proton/vpn/cli/commands/server.py`:

- `connect`: Check daemon at the very beginning
- `disconnect`: Check daemon at the very beginning

```python
async def connect(...):
    if not is_daemon_running():
        raise_daemon_not_running_error()
    controller = await Controller.create(...)
    ...
```

This provides immediate, actionable feedback before any other work is done.

### 3. Systemd Service File

Created `service/protonvpn.service`:

```ini
[Unit]
Description=Proton VPN Daemon
Documentation=man:protonvpn(1)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m proton.vpn.daemon
Restart=on-failure
RestartSec=5s
TimeoutStartSec=30s

[Install]
WantedBy=multi-user.target
```

**Notes**:
- The daemon is provided by the `proton-vpn-api-core` package (module `proton.vpn.daemon`)
- This service file can be installed by package maintainers to `/lib/systemd/system/`
- Relies on `python3` being available in PATH

### 4. Documentation Updates

Updated `README.md`:

- Added **Daemon Service** section explaining how to check, start, and enable the service
- Added **Non-root operation** section clarifying that the CLI runs as regular user and daemon handles privileges
- Updated Current functionality/limitations to reflect new features (free tier location selection, servers list command)

---

## Testing

### Unit Test Adjustments

All existing tests for `connect` and `disconnect` now mock `is_daemon_running` to return `True` via autouse fixture:

```python
@pytest.fixture(autouse=True)
def mock_daemon_running():
    with patch('proton.vpn.cli.commands.server.is_daemon_running', return_value=True):
        yield
```

This ensures tests remain focused on command logic rather than daemon state.

### Test Results

```
============================== 74 passed in 2.07s ==============================
```

All tests pass with the new daemon check in place.

---

## User Experience

### Before

Running `protonvpn connect` as a regular user might have produced unclear errors if the daemon wasn't running, or potentially required `sudo` in some setups.

### After

```bash
$ protonvpn connect
Error: Proton VPN daemon is not running.
Please start and enable it:
  sudo systemctl start protonvpn.service
  sudo systemctl enable protonvpn.service
```

Clear, actionable instructions.

### Normal Operation

When daemon is running (or on non-systemd where check is skipped), the CLI works normally without any sudo prompts.

---

## Distribution Considerations

### Debian Packaging

To automatically install and enable the service:

1. Place `service/protonvpn.service` into `debian/` directory
2. Ensure `debian/rules` uses `--with systemd` (dh will handle activation)
3. The package should `Depends: proton-vpn-api-core` (which provides the daemon module)

Example additions to `debian/rules`:

```make
%:
    dh $@ --with python3,systemd
```

And create `debian/protonvpn.service` with appropriate permissions.

### RPM Packaging

Similarly, for RPM, the service file should be installed to `/lib/systemd/system/` and `%post` script should run `systemctl enable protonvpn.service`.

---

## Backward Compatibility

✅ No breaking changes for end users
✅ CLI continues to work if daemon is already running
✅ Clear error message improves first-time setup
✅ Non-systemd systems are gracefully handled (check skipped)

---

## Security

- The daemon runs with necessary privileges (likely as root via systemd)
- CLI communicates via D-Bus with appropriate Polkit rules (provided by daemon package)
- Users don't need to use `sudo` for daily operations
- Systemd service runs with `Restart=on-failure` for reliability

---

## Future Work

- Add unit tests specifically for daemon check logic (test systemctl call, handling)
- Add integration test that verifies proper error when daemon not running
- Consider adding a `--skip-daemon-check` flag for advanced debugging
- Possibly auto-enable the service on first install via package maintainer scripts

---

## Summary

The CLI is now fully non-root with proper daemon integration. Users get clear guidance if the service is not running, and all existing functionality remains intact.
