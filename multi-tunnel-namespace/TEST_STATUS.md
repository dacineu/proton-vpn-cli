# Test Implementation Status - Quick Reference

**Date**: 2026-03-16
**Goal**: All unit tests run without sudo

## Current State

✅ **Test infrastructure complete**:
- 8 test files created (~3,500 lines)
- pytest configured
- CI/CD workflow ready
- Test runner script & Makefile

⚠️ **Unit tests need API alignment**: Many tests fail because they were written based on incorrect assumptions about the API. Need to align test expectations with actual code.

## Key Mismatches to Fix

### 1. Tunnel Model - Status vs Device
**Actual**: Tunnel has no `status` attribute. Status is computed: `CONNECTED` if `device` non-empty, else `DISCONNECTED`.
**Tests**: Many tests check `tunnel.status`.
**Fix**: In tests, compute status as `TunnelStatus.CONNECTED if tunnel.device else TunnelStatus.DISCONNECTED`.

### 2. ConnectionConfig Constructor
**Actual**: `ConnectionConfig(adapter=..., tunnel_name=..., session_name=...)` - requires positional or keyword args.
**Tests**: Some tests call `ConnectionConfig.from_dict()` expecting it to accept partial data.
**Fix**: Ensure test data includes all required fields: adapter, tunnel_name, session_name.

### 3. RoutingStrategy Methods
**Actual**: `RoutingStrategy` ABC has these methods:
- `create_tunnel_context(tunnel_name) -> dict`
- `destroy_tunnel_context(tunnel_name, metadata)`
- `assign_process_to_tunnel(tunnel_name, metadata, pid)`
- `list_active_tunnels() -> dict`
- `cleanup_all()`

**Tests**: Some tests call `create_namespace()`, `delete_namespace()`, etc.
**Fix**: Update tests to use correct method names, or mock the correct abstract methods.

### 4. Tunnel Constructor
**Actual**: `Tunnel(name, adapter, device)` - `device` is required positional.
**Tests**: Many Tunnel instantiations missing `device`.
**Fix**: Always provide `device` (use `""` for disconnected tunnels).

### 5. D-Bus Variant Signatures
**Actual**: `_to_variant()` expects basic Python types, converts to dbus_next.Variant.
**Tests**: Expect result dict values to be `.value` already.
**Fix**: In service methods, return dict of variants; in client, convert properly.

### 6. SessionNotFoundError
**Actual**: Not defined in `libvpnmanager.models.exceptions`.
**Tests**: Import and raise SessionNotFoundError.
**Fix**: Either define SessionNotFoundError or use appropriate existing exception (ConfigError?).

## Recommended Fix Strategy

Given the scope, I recommend **simplifying** the test approach:

1. **Keep existing passing tests** (~95 tests pass):
   - test_models.py (most)
   - test_adapters.py (most)
   - test_manager.py (needs MockRouting fix)
   - test_dbus_service.py (needs better mocks)
   - test_dbus_client.py (needs mock fixes)

2. **Rewrite/remove failing tests**:
   - test_routing.py tests are calling wrong methods - either fix to match `NetworkNamespaceRouting` API or remove/rewrite.
   - test_models.py tests for config need updating to match actual constructors.
   - test_cli_tunnel.py requires full proton package - consider moving to integration tests.

3. **Focus on core library**: The most valuable unit tests are for:
   - TunnelManager (with proper mocks)
   - DummyAdapter
   - D-Bus service (with proper mock manager)
   - D-Bus client (with proper mock bus)
   - Data models (fix test data to match constructors)

## Quick Wins (Fix in <1 hour)

- [ ] Add `status` property to Tunnel (computed): `@property def status(self): return TunnelStatus.CONNECTED if self.device else TunnelStatus.DISCONNECTED`
  - This would fix all tests checking `tunnel.status`!

- [ ] Fix MockRouting in test_manager.py to implement missing abstract methods.

- [ ] Fix all Tunnel instantiations to include `device=""` if not set.

- [ ] Fix test_models.py to use correct ConnectionConfig constructor calls.

## Alternative: Adjust Tests to Match Code

Instead of changing code, adjust tests:

1. Replace `tunnel.status` with computed check.
2. Ensure all `Tunnel(...)` include `device`.
3. Update test_routing.py to mock `create_tunnel_context` not `create_namespace`.
4. Remove SessionNotFoundError imports, use `ValueError` or define in test.

## Suggested Next Actions

Given the user's goal ("tests can be done without sudo"), the priority is **functional unit tests** that run without external dependencies. I suggest:

1. **Fix the tunnel status property** - add to Tunnel model. This single change would fix ~20 failing tests.
2. **Fix test_manager.py** - complete MockRouting.
3. **Fix test_dbus_service.py** - all Tunnel creations need `device`.
4. **Fix test_dbus_client.py** - MockDBusInterface should return proper variants.
5. **Simplify or skip test_cli_tunnel.py** - mark as integration-only or provide comprehensive mocks.
6. **Rewrite test_routing.py** - it's testing a different API than exists.

If we do these 6 steps, we can have >90% unit test pass rate without sudo.

---

**Current passing tests**: 95/142 = 67%
**Target after fixes**: >90% (128+ tests)

The test suite is well-structured but needs API alignment. The effort to fix is estimated at 4-6 hours.
