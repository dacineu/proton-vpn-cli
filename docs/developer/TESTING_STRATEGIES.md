# Testing Strategies

This guide covers testing practices for the Multi-Tunnel Adapter Architecture, including unit, integration, and system tests.

---

## Test Types

### Unit Tests (`tests/unit/`)

Target individual classes and functions in isolation. Mock external dependencies:

- **Subprocesses** (`asyncio.create_subprocess_exec`) — use `unittest.mock.patch` to return fake `Process` objects.
- **Sockets** — use in-memory streams or mock `asyncio.start_unix_server`.
- **pyroute2/network operations** — mock `NetworkNamespaceRouting` methods.

**Example:** Test `ResourceAllocator._handle_allocate` by mocking `self.routing.create_tunnel_context` and verifying namespace creation logic without touching real kernel.

### Integration Tests (`tests/integration/`)

Spin up real daemon and adapter processes with temporary sockets and temporary network namespaces (lightweight, real kernel ops). These tests verify end-to-end flows.

**Fixtures** (see `tests/integration/conftest.py`):

- `daemon` — starts `VPNDaemon` with temporary socket paths.
- `manager_client` — `ManagerClient` connected to daemon.
- `dummy_credentials`, `proton_credentials`.

**Pattern:**

```python
@pytest.mark.asyncio
async def test_adapter_startup(manager_client):
    creds = {'username': 'test', 'password': 'pass'}
    totp = await manager_client.verify_2fa('123456')
    endpoint = await manager_client.start_adapter('dummy', creds, session_token=totp['session_token'])
    assert endpoint.startswith('unix://')
    socket = Path(endpoint.replace('unix://', ''))
    assert socket.exists()
    assert stat.S_IMODE(socket.stat().st_mode) == 0o600
```

### System Tests (`tests/system/`)

Full system-level tests, including real VPN connections (if available) and network configuration verification. These may be environment-specific and require root.

---

## Test Coverage Goals

- **Critical path:** adapter startup, tunnel create/destroy, namespace allocation.
- **Security:** socket permissions, `SO_PEERCRED` verification, credential zeroization (if detectable).
- **Error handling:** invalid messages, missing fields, namespace conflicts.
- **Crash recovery:** simulate adapter `SIGKILL` and verify MTM cleans namespaces.

Phase 4 specifically requires stubs for:

- `test_phase4_security.py` — security audit properties
- `test_phase4_legacy_api.py` — D-Bus CreateTunnel forwarding to adapter
- `test_phase4_totp_encryption.py` — encryption/decryption on control and CLI channels

---

## Mocking External Services

The `proton.vpn.core.api` module is external and heavy. Use the `tests/integration/mocks/proton/` directory to provide a fake implementation that satisfies imports. Add to `sys.path` before tests:

```python
MOCKS_PATH = Path(__file__).parent / "mocks"
sys.path.insert(0, str(MOCKS_PATH))
```

The mock should define at least:

```python
from proton.vpn.core.api import ProtonVPN, VPNConnection
class DummyVPNConnection:
    def get_tun_device_name(self): return "dummy0"
    def get_connection_state(): return "CONNECTED"
```

---

## Running Tests

```bash
# Unit tests
pytest tests/unit

# Integration tests (requires root)
sudo pytest tests/integration

# All
pytest
```

---

## Writing a New Test

1. Choose the appropriate directory (`unit` or `integration`).
2. Use descriptive test function names: `test_<what_under_test>_<condition>_<expected>`.
3. Include docstrings.
4. For async tests, use `@pytest.mark.asyncio`.
5. Use fixtures for common setup (daemon, client, credentials).
6. Assert on concrete outputs: return values, exit codes, filesystem state (`ip netns list`), socket permissions.

---

*Back to [INDEX.md](../INDEX.md)*
