# Code Conventions

## Style Guide

### Formatting
- **Tool:** `black` (enforced, non-negotiable)
- **Line length:** 88 characters (Black default)
- **Target Python:** 3.9+
- **String quotes:** Black handles automatically (single vs double)

Example:
```python
# Black reformats as needed
def long_function_name(
    param_one: str,
    param_two: int,
    param_three: bool,
) -> Optional[Tunnel]:
    ...
```

### Linting
- **Tool:** `ruff` (replaces flake8, isort, and others)
- **Enabled rules:**
  - `E` - pycodestyle errors (PEP 8 violations)
  - `W` - pycodestyle warnings
  - `F` - pyflakes (undefined names, unused imports)
  - `I` - isort (import ordering)
  - `B` - flake8-bugbear (common bugs)
  - `C4` - flake8-comprehensions (list/dict/set comprehensions)
  - `UP` - pyupgrade (modern Python syntax)

- **Import sorting:** Known first-party: `libvpnmanager`
- **Line length:** 88 (matches black)

### Type Checking
- **Tool:** `mypy` in **strict mode**
- **Key strict options:**
  - `disallow_untyped_defs = true` - All functions must have annotations
  - `disallow_incomplete_defs = true` - Annotations must be complete
  - `check_untyped_defs = true` - Type-check even unannotated functions
  - `disallow_untyped_decorators = true`
  - `no_implicit_optional = true` - Explicit `Optional` required
  - `warn_return_any = true`
  - `warn_unused_configs = true`
  - `warn_redundant_casts = true`
  - `warn_unused_ignores = true`
  - `warn_no_return = true`
  - `warn_unreachable = true`
  - `strict_equality = true`

- **Exempt modules:** `pyroute2.*`, `systemd.*` (external C extensions without stubs)

## Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Packages | `lowercase` | `libvpnmanager`, `adapters` |
| Modules | `lowercase` or `lowercase_with_underscores` | `tunnel.py`, `resource_allocator.py` |
| Classes | `PascalCase` | `TunnelManager`, `VPNAdapter`, `NetworkNamespaceRouting` |
| Functions | `snake_case` | `create_tunnel`, `allocate_namespace` |
| Variables | `snake_case` | `session_manager`, `adapter_registry` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Methods | `snake_case` | Same as functions |
| Entry points | `kebab-case` | `proton-vpn-manager`, `mtm-adapter-proton` |

## Documentation

### Docstrings
- **Style:** Google style or reST (consistent within codebase)
- **Required for:** All public classes, methods, functions, modules
- **Sections:** `Args:`, `Returns:`, `Raises:`, `Example:` (as needed)

Example:
```python
async def connect(
    self,
    config: ConnectionConfig,
    progress_callback: Optional[callable] = None,
) -> Tunnel:
    """
    Establish a VPN connection.

    Args:
        config: Connection configuration (type-specific subclass)
        progress_callback: Optional callable(status: str) for progress updates

    Returns:
        Tunnel object with populated fields (device, namespace, etc.)

    Raises:
        ConfigurationError: If config is invalid
        AuthenticationError: If credentials are invalid
        ConnectionError: If network/server unreachable
        CapabilityError: If feature not supported
    """
```

### Module Docstrings
Every module should have a top-level docstring describing its purpose.

Example from `daemon/daemon.py`:
```python
"""Enhanced Tunnel Manager with multi-user and session support.

This version extends the original TunnelManager to support:
  - Multiple adapters per session (different Proton accounts, Psiphon, WireGuard)
  - Session management through SessionManager
  - User ownership and permissions
  - Listing tunnels across users (for admins)
"""
```

## Error Handling

### Exception Hierarchy
Root: `VPNManagerError`

```
VPNManagerError
├── TunnelError
│   ├── TunnelNotFoundError
│   └── TunnelExistsError
├── AdapterError
│   ├── AdapterNotFoundError
│   ├── ConnectionError
│   │   └── AuthenticationError
│   ├── ConfigurationError
│   └── CapabilityError
├── RoutingError
│   ├── NamespaceError
│   │   ├── NamespaceExistsError
│   │   ├── NamespaceNotFoundError
│   │   └── NamespacePermissionError
│   └── DeviceError
│       ├── DeviceNotFoundError
│       └── DeviceExistsError
├── DBusError
├── AccessDeniedError
└── SessionError
    └── SessionNotFoundError
```

### Raising Exceptions
- Use specific exception types (never bare `Exception`)
- Include helpful error messages
- Preserve original exceptions when wrapping

```python
# Good
if not adapter_type:
    raise ConfigurationError("adapter_type is required")

try:
    tunnel = await self._adapters[key].connect(config)
except TunnelError as e:
    logger.error(f"Tunnel operation failed: {e}")
    raise
```

## Async Conventions

- **Async all the way:** I/O operations should be `async`
- **Async context managers:** Use `async with` for resource management
- **Async fixtures:** pytest tests use `@pytest.mark.asyncio`
- **Task creation:** Use `asyncio.create_task()` for background tasks
- **Locking:** Use `asyncio.Lock()` for shared mutable state

## Imports

Order (enforced by ruff isort):
1. Standard library
2. Third-party libraries
3. First-party (project) imports

Within each group, alphabetize.

```python
# Standard library
import asyncio
import json
import logging
from typing import Dict, List, Optional

# Third-party
from pydantic import BaseModel
import websockets

# First-party
from libvpnmanager.adapters.base import VPNAdapter
from libvpnmanager.models.tunnel import Tunnel
```

## Type Hints

- **Required** on all public APIs (functions, methods)
- **Prefer** explicit imports: `from typing import List, Dict, Optional`
- **Generics:** Use `list[str]` over `List[str]` when possible (Python 3.9+)
- **`Any`** avoided unless truly necessary
- **`Optional[T]`** for nullable values (never `T | None` for Python <3.10 compat)

## Logging

- **Library:** Standard `logging` module
- **Logger name:** `__name__` (module-level)
- **Levels:** DEBUG for verbose, INFO for normal ops, WARNING for recoverable issues, ERROR for failures
- **Format:** Include context (tunnel name, user, adapter type)

```python
logger = logging.getLogger(__name__)
logger.debug("Connecting tunnel %s for user %s", tunnel_name, username)
logger.info("Tunnel %s connected", tunnel_name)
logger.warning("Adapter %s not found, falling back", adapter_type)
logger.error("Connection failed: %s", error)
```

## Testing Conventions

See `TESTING.md` for full testing practices.

### Test File Naming
`test_<module>.py` - mirrors source module

### Test Structure
```python
"""Module docstring explaining test coverage."""

import pytest
from unittest.mock import patch, MagicMock

class TestClassName:
    """Test suite for ClassName."""

    @pytest.fixture
    def instance(self):
        return MyClass()

    def test_feature_success(self, instance):
        """One-line description of test case."""
        # Arrange
        ...

    def test_feature_failure(self):
        """Test error handling."""
        with pytest.raises(ExpectedError):
            ...
```

### Async Tests
Use `@pytest.mark.asyncio` on async test methods.

---

*Generated by codebase mapper (quality focus)*
