# Testing Analysis

## Test Framework

**Primary Framework:** `pytest>=7.0.0`

### Configuration (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = [
    "--strict-markers",
    "--strict-config",
    "--tb=short",
    "--cov=libvpnmanager",
    "--cov-report=term-missing",
]
```

**Options:**
- `testpaths` - Tests discovered in `tests/`
- `python_files` - Pattern: `test_*.py`
- `--strict-markers` - Warn on unknown markers
- `--strict-config` - Strict config parsing
- `--tb=short` - Short traceback format
- `--cov=libvpnmanager` - Coverage for libvpnmanager package
- `--cov-report=term-missing` - Show missing lines in terminal

### Additional Dependencies
- `pytest-asyncio>=0.21.0` - Async test support
- `pytest-cov>=4.0.0` - Coverage measurement

## Test Structure

```
tests/
└── unit/
    ├── test_adapters.py
    ├── test_cli_tunnel.py
    ├── test_dbus_client.py
    ├── test_dbus_service.py
    └── test_routing.py
```

**Naming:** `test_<module>.py` mirrors source structure.

## Test Patterns

### Async Tests

Async tests use `@pytest.mark.asyncio` decorator:

```python
import pytest

class TestDummyAdapter:
    @pytest.fixture
    def dummy_adapter(self):
        return DummyAdapter()

    @pytest.mark.asyncio
    async def test_connect_success(self, dummy_adapter):
        tunnel = await dummy_adapter.connect(config)
        assert tunnel.name == "expected"
```

### Fixtures

**Scope:** Function (default) unless otherwise needed

Example fixtures:
```python
@pytest.fixture
def dummy_config():
    return ConnectionConfig(
        adapter="dummy",
        tunnel_name="test_tunnel",
        session_name="test_session"
    )

@pytest.fixture
def tunnel_manager():
    routing = NetworkNamespaceRouting()
    return TunnelManager(routing)
```

### Mocking

**Library:** `unittest.mock` (standard library)

Common patterns:
```python
from unittest.mock import patch, MagicMock, AsyncMock

# Patch a function
@patch("libvpnmanager.routing.namespace.pyroute2.IPRoute")
def test_namespace_creation(mock_ipr):
    mock_ipr.return_value.__enter__ = MagicMock()
    ...

# Async mock
mock_adapter = AsyncMock()
mock_adapter.connect.return_value = tunnel
```

## Test Coverage

**Tool:** `pytest-cov`

**Command:** `pytest --cov=libvpnmanager --cov-report=html`

**Current config:** coverage report shows missing lines in terminal.

**Target:** Aim for high coverage on critical paths:
- Adapter implementations
- TunnelManager orchestration
- Routing namespace operations
- Exception handling flows

## Test Types

### Unit Tests (current)
- Isolated component tests
- Heavy use of mocking for external dependencies (pyroute2, dbus-next)
- Focus on business logic

### What's NOT Currently Tested
- Integration tests (real daemon, multiple processes)
- End-to-end tunnels (requires network config, privileges)
- D-Bus service discovery and signals
- IPC layer (unix socket, websocket)
- Multi-user session scenarios
- Systemd service startup

## Running Tests

```bash
# All tests with coverage
pytest --cov=libvpnmanager

# Specific test file
pytest tests/unit/test_adapters.py

# Specific test
pytest tests/unit/test_adapters.py::TestDummyAdapter::test_connect_success

# With verbose output
pytest -v

# Without coverage (faster)
pytest -p no:cov

# With debug logging
pytest --log-cli-level=DEBUG
```

## CI/CD Integration

`.gitlab-ci.yml` likely defines test pipeline stages. Tests run on:
- Multiple Python versions (3.9, 3.10, 3.11)
- Linux environment (pyroute2 requires Linux kernel features)

## Mocking Strategy

### External Dependencies to Mock
- `pyroute2.IPRoute` - Network namespace and interface management
- `dbus-next` - D-Bus communication
- `websockets` - WebSocket connections
- Subprocess calls (adapter spawning)
- File system operations (socket files, PID files)

### Example: Testing Routing Without Root

```python
@patch("libvpnmanager.routing.namespace.pyroute2.IPRoute")
def test_namespace_create(mock_ipr):
    # Configure mock to simulate namespace operations
    mock_ns = MagicMock()
    mock_ipr.return_value.__enter__ = MagicMock(return_value=mock_ns)
    mock_ns.link_lookup.return_value = [1]

    routing = NetworkNamespaceRouting()
    routing.create_namespace("test_ns")

    mock_ns.link_create.assert_called_with(ifname="vpn-test_ns", kind="dummy")
```

## Test Data Management

- **Fixtures:** Defined in test files or `conftest.py` (none currently)
- **Temporary resources:** Use `tmp_path` fixture for filesystem
- **Network isolation:** Tests should not touch real network interfaces
- **Cleanup:** Teardown in fixtures or `yield` fixtures

## Known Testing Gaps

1. **Integration tests missing** - No tests of daemon + adapter + routing together
2. **D-Bus service testing** - Would need `dbus-daemon` running
3. **Multi-process scenarios** - Adapter spawning, IPC messaging
4. **Real network namespace ops** - Requires root/CAP_NET_ADMIN
5. **Cross-transport IPC** - Unix socket, D-Bus, WebSocket variations
6. **Session management** - Multi-user scenarios
7. **Security/authorization** - Permission checks

## Proposed Test Improvements

- Add `conftest.py` with shared fixtures (mock config, common tunnels)
- Create `tests/integration/` directory for multi-component tests
- Use pytest-xdist for parallel test execution (speed)
- Add property-based tests with `hypothesis` for fuzzing edge cases
- Add performance benchmarks (e.g., tunnel creation latency)
- Set up coverage thresholds in CI (e.g., `--cov-fail-under=80`)

## Debugging Tests

```bash
# Drop into debugger on failure
pytest --pdb

# Show local variables in traceback
pytest -l

# Run last failed tests only
pytest --last-failed

# Run with print statements visible
pytest -s
```

---

*Generated by codebase mapper (quality focus)*
