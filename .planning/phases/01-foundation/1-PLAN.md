# Phase 1 Plan: Foundation — Adapter Lifecycle & Core Protocol

**Created:** 2025-03-20
**Status:** Ready for execution
**Requirements:** 13 total (DAEM-01, DAEM-02, ADPT-01, ADPT-02, ADPT-03, ADPT-06, CLI-01, CLI-02, TST-04, SEC-04, SEC-05, SEC-06, SEC-07)

---

## Wave 1: Daemon Adapter Pool & Spawn Infrastructure

### Plan 01-W1: Implement Adapter Process Pool and StartAdapter D-Bus Method

**Objective:** Create the core daemon infrastructure for spawning and managing adapter processes, including adapter_pool tracking, socket creation, and D-Bus API.

**Requirements:** DAEM-01, DAEM-02

**Dependencies:** None

**Files Modified:**
- `src/daemon/daemon.py`
- `src/libvpnmanager/dbus/service.py`
- `src/libvpnmanager/dbus/client.py`

**Tasks:**

1. **Read and understand existing daemon structure**
   - `<read_first>`: `src/daemon/daemon.py`, `src/libvpnmanager/dbus/service.py`
   - `<action>`: Review current `VPNDaemon` class, existing D-Bus methods, and `TunnelManager` integration. Identify where to add `adapter_pool` dict and `StartAdapter` method.
   - `<acceptance_criteria>`:
     - `daemon.py` contains `class VPNDaemon` with `__init__` method
     - `service.py` defines D-Bus service interface with existing methods like `CreateTunnel`

2. **Add adapter_pool tracking to VPNDaemon**
   - `<read_first>`: `src/daemon/daemon.py`
   - `<action>`: In `VPNDaemon.__init__`, add `self.adapter_pool: Dict[Tuple[str, str], AdapterProcess] = {}`. Create `AdapterProcess` dataclass with fields: `process: asyncio.subprocess.Process`, `endpoint: str`, `control_socket: str`, `username: str`, `adapter_type: str`, `session_id: str`, `started_at: datetime`, `tunnels: Dict[str, Any]`.
   - `<acceptance_criteria>`:
     - `daemon.py` contains `self.adapter_pool = {}` initialization
     - `AdapterProcess` class/namedtuple defined with exactly these 7 fields

3. **Implement StartAdapter D-Bus method**
   - `<read_first>`: `src/libvpnmanager/dbus/service.py`, `src/daemon/daemon.py`
   - `<action>`: Add `async def StartAdapter(self, adapter_type: str, credentials: dict, totp_code: str = "")` to `ManagerService` class. In implementation:
     - Derive `vpn_username = credentials.get('username')`
     - Check `key = (adapter_type, vpn_username)`. If `key in self.daemon.adapter_pool` and process alive, return `{"endpoint": existing.endpoint, "status": "already_running"}`
     - Generate `session_id = str(uuid.uuid4())`
     - Call `self.daemon._spawn_adapter(adapter_type, vpn_username, session_id, credentials)` (you will implement next)
     - Wait for adapter CLI socket: `socket_path = f"/run/mtm/adapters/{vpn_username}_{adapter_type}.sock"`. Use `await wait_for_socket(socket_path, timeout=10)`
     - Return `{"endpoint": f"unix://{socket_path}", "status": "started", "session_id": session_id}`
   - `<acceptance_criteria>`:
     - `service.py` contains `async def StartAdapter(self, adapter_type: str, credentials: dict, totp_code: str = "")` method
     - Method checks `adapter_pool` for existing adapter and returns early
     - Method generates UUID for `session_id`
     - Method calls `_spawn_adapter` and waits for socket with 10s timeout
     - Method returns JSON with `endpoint`, `status`, and `session_id`

4. **Implement _spawn_adapter in VPNDaemon**
   - `<read_first>`: `src/daemon/daemon.py`
   - `<action>`: Add `async def _spawn_adapter(self, adapter_type: str, vpn_username: str, session_id: str, credentials: dict) -> asyncio.subprocess.Process`:
     - Find executable: `exe = self._find_adapter_executable(adapter_type)`. Raise `AdapterError` if not found.
     - Create socket paths: `cli_socket = f"/run/mtm/adapters/{vpn_username}_{adapter_type}.sock"`, `control_socket = f"/run/mtm/control/{vpn_username}_{adapter_type}.sock"`
     - Ensure parent dirs exist with `mkdir -p /run/mtm/adapters /run/mtm/control`, set mode `0755`, owned by root
     - Create adapter CLI socket placeholder: `Path(cli_socket).unlink(missing_ok=True)`
     - Build env: `env = { "ADAPTER_ENDPOINT": cli_socket, "CONTROL_ENDPOINT": control_socket, "SESSION_ID": session_id, **credentials }` (For SEC-05: Do NOT pass TOTP secret yet; Phase 1 uses dummy tokens)
     - Spawn: `process = await asyncio.create_subprocess_exec(exe, env=env)`
     - Store in `adapter_pool[(adapter_type, vpn_username)] = AdapterProcess(process, cli_socket, control_socket, vpn_username, adapter_type, session_id, {})`
     - Start background monitor: `asyncio.create_task(self._monitor_adapter(adapter_type, vpn_username, process))`
   - `<acceptance_criteria>`:
     - `daemon.py` contains `_spawn_adapter` method with exact env keys `ADAPTER_ENDPOINT`, `CONTROL_ENDPOINT`, `SESSION_ID`
     - Method creates `/run/mtm/adapters` and `/run/mtm/control` directories if missing
     - Method stores process in `self.adapter_pool[(adapter_type, vpn_username)]`
     - Method calls `asyncio.create_subprocess_exec` with the adapter executable
     - Method creates a background task `_monitor_adapter`

5. **Implement adapter process monitor**
   - `<read_first>`: `src/daemon/daemon.py`
   - `<action>`: Add `async def _monitor_adapter(self, adapter_type: str, vpn_username: str, process: asyncio.subprocess.Process)`:
     - `await process.wait()`
     - On exit, remove from `adapter_pool`: `self.adapter_pool.pop((adapter_type, vpn_username), None)`
     - Log adapter exit with `logger.info(f"Adapter {adapter_type}/{vpn_username} exited with code {process.returncode}")`
   - `<acceptance_criteria>`:
     - `daemon.py` contains `_monitor_adapter` method that `await process.wait()` and pops the adapter from pool
     - Method logs exit with adapter type, username, and returncode

6. **Implement ListAdapters D-Bus method**
   - `<read_first>`: `src/libvpnmanager/dbus/service.py`
   - `<action>`: Add `async def ListAdapters(self)` that returns list of dicts: iterate `self.daemon.adapter_pool.values()`, for each include `{"type": adapter_type, "username": vpn_username, "endpoint": endpoint, "session_id": session_id, "tunnel_count": len(tunnels), "status": "running"}`.
   - `<acceptance_criteria>`:
     - `service.py` contains `async def ListAdapters(self)` method
     - Returns list with keys: `type`, `username`, `endpoint`, `session_id`, `tunnel_count`, `status`

7. **Implement control socket server in daemon**
   - `<read_first>`: `src/daemon/daemon.py`
   - `<action>`: In `VPNDaemon.__init__`, add `self.control_socket_path = "/run/mtm/control.sock"`. In `start()` method (or new `start_control_server()`), create Unix socket server: `server = await asyncio.start_unix_server(self._handle_control_connection, self.control_socket_path)`. Set socket permissions: `os.chmod(self.control_socket_path, 0o600)`. Handle incoming connections in `_handle_control_connection(reader, writer)`: read NDJSON lines, parse JSON, dispatch to `_handle_control_message(msg, writer)`.
   - `<acceptance_criteria>`:
     - `daemon.py` has `self.control_socket_path = "/run/mtm/control.sock"`
     - `daemon.py` calls `asyncio.start_unix_server` with `_handle_control_connection` handler
     - Socket file has mode `0o600` set via `os.chmod`

---

## Wave 2: Dummy Adapter with Dual-Server and Token Validation

### Plan 02-W1: Create Dummy Adapter CLI with Dual-Server Pattern

**Objective:** Build the dummy adapter executable that demonstrates the full lifecycle: CLI socket server, control connection to MTM, Register handshake, and tunnel creation with token validation.

**Requirements:** ADPT-01, ADPT-02, ADPT-03, ADPT-06, SEC-06

**Dependencies:** Wave 1 complete (daemon can spawn adapters)

**Files Modified:**
- `src/adapters/dummy_adapter/cli.py` (new or modify existing)
- `src/adapters/dummy_adapter/adapter.py` (new or modify existing)
- `src/libvpnmanager/adapters/base.py` (if needed)

**Tasks:**

8. **Create dummy adapter base class (if not exists)**
   - `<read_first>`: `src/libvpnmanager/adapters/base.py`
   - `<action>`: Ensure `VPNAdapter` base class exists with:
     - `self.tunnels: Dict[str, Any] = {}`
     - `async def handle_cli(self, reader, writer)` method signature
     - `async def handle_control(self, reader, writer)` method signature
     - Abstract `async def create_tunnel(self, name, config)` method
   - `<acceptance_criteria>`:
     - `base.py` defines `class VPNAdapter` with `tunnels` dict attribute
     - Base class has stub methods `handle_cli`, `handle_control`, `create_tunnel`

9. **Implement DummyAdapter CLI with dual-server**
   - `<read_first>`: `src/adapters/dummy_adapter/cli.py` (if exists), `src/adapters/dummy_adapter/adapter.py`
   - `<action>`: Create `main()` function that:
     - Reads env: `ADAPTER_ENDPOINT`, `CONTROL_ENDPOINT`, `SESSION_ID`, `VPN_USERNAME` (no TOTP secret in Phase 1; dummy token via env `SESSION_TOKEN` for testing)
     - Binds CLI Unix socket: `server = await asyncio.start_unix_server(handle_cli, ADAPTER_ENDPOINT)`, set mode `0o600`
     - Connects to MTM control socket: `ctrl_reader, ctrl_writer = await asyncio.open_unix_connection(CONTROL_ENDPOINT)`
     - Creates `DummyAdapter` instance, stores in global or passes to handlers
     - Sends `Register` message: `{"action": "register", "session_id": SESSION_ID, "adapter_type": "dummy", "username": VPN_USERNAME}` to control socket, waits for ack
     - Serves concurrently: `async with server: await asyncio.gather(server.serve_forever(), handle_control_loop(ctrl_reader, ctrl_writer))`
   - `<acceptance_criteria>`:
     - `cli.py` has `async def main()` that reads required env vars
     - Binds CLI socket at `ADAPTER_ENDPOINT` and sets mode `0o600`
     - Connects to control socket at `CONTROL_ENDPOINT`
     - Sends NDJSON `Register` message with `session_id`, `adapter_type`, `username`
     - Runs both `serve_forever()` and control handler concurrently with `asyncio.gather`

10. **Implement DummyAdapter tunnel creation and token validation**
    - `<read_first>`: `src/adapters/dummy_adapter/adapter.py`
    - `<action>`: In `DummyAdapter` class:
      - Add `expected_session_token: Optional[str] = None` set from MTM during Register response or env var `SESSION_TOKEN` (for Phase 1 dummy)
      - In `handle_cli`, read first message from CLI must include `session_token`. If `msg.get("session_token") != self.expected_session_token`, close connection with error.
      - For `CreateTunnel`: increment counter to generate `device = f"dummy{i}"`, store in `self.tunnels[name] = {"device": device, "status": "connected"}`, send response `{"status": "connected", "tunnel": {"name": name, "device": device}}`
      - Implement `ListTunnels`, `DestroyTunnel`, `GetStatus` appropriately.
    - `<acceptance_criteria>`:
      - `adapter.py` contains `expected_session_token` attribute
      - `handle_cli` checks `msg["session_token"]` against `expected_session_token` before processing
      - `CreateTunnel` returns `device: "dummy0"` etc. and stores in `self.tunnels`
      - All CLI messages require `session_token` field

11. **Implement control message handler in adapter**
    - `<read_first>`: `src/adapters/dummy_adapter/cli.py`
    - `<action>`: Implement `async def handle_control_loop(reader, writer)` that reads NDJSON messages. Handle:
      - `AllocateTunnel`: Parse JSON with `tunnel_name`, `device`, `gateway`, `dns`. Respond `{"status": "allocated", "namespace": f"vpn_{tunnel_name}"}` (dummy: no real namespace creation).
      - `ReleaseTunnel`: Respond `{"status": "released"}`.
      - `Shutdown`: Respond `{"status": "shutting_down"}`, then gracefully shut down adapter (stop server, exit).
    - `<acceptance_criteria>`:
      - `handle_control_loop` recognizes `AllocateTunnel`, `ReleaseTunnel`, `Shutdown` actions
      - Sends proper response JSON for each
      - On `Shutdown`, triggers adapter exit (set shutdown flag or call `loop.stop()`)

12. **Handle Register handshake with token exchange**
    - `<read_first>`: `src/adapters/dummy_adapter/cli.py`
    - `<action>`: After sending `Register`, wait for MTM response `{"status": "registered", "session_token": "xyz"}`. Store that in adapter's `expected_session_token`. If MTM sends error, exit with failure.
    - `<acceptance_criteria>`:
      - Adapter waits for `Register` response containing `session_token`
      - Adapter sets `self.expected_session_token = response["session_token"]` before serving requests

---

## Wave 3: Client Library — AdapterClient and start_adapter

### Plan 03-W1: Implement AdapterClient and ManagerClient.start_adapter

**Objective:** Add client-side support for starting adapters and direct communication with adapter Unix sockets, including session token propagation.

**Requirements:** CLI-01, CLI-02, SEC-04 (partial), SEC-05 (partial), SEC-06 (partial), SEC-07 (partial)

**Dependencies:** Wave 1 and Wave 2 complete

**Files Modified:**
- `src/libvpnmanager/client.py`
- `src/libvpnmanager/ipc/unix_socket.py` (if needed)

**Tasks:**

13. **Add start_adapter method to ManagerClient**
    - `<read_first>`: `src/libvpnmanager/client.py`
    - `<action>`: Add `async def start_adapter(self, adapter_type: str, credentials: dict, totp_code: str = "") -> dict`:
      - Call `await self._call("StartAdapter", {"adapter_type": adapter_type, "credentials": credentials, "totp_code": totp_code})`
      - Return result dict containing `endpoint`, `status`, `session_id`
    - `<acceptance_criteria>`:
      - `client.py` contains `async def start_adapter(self, adapter_type, credentials, totp_code="")` method
      - Method calls `self._call("StartAdapter", ...)` with proper parameters
      - Returns dict with at least `endpoint` key

14. **Create AdapterClient class for direct adapter communication**
    - `<read_first>`: `src/libvpnmanager/client.py` (existing), `src/adapters/dummy_adapter/adapter.py` (to understand message format)
    - `<action>`: Define `class AdapterClient`:
      - `__init__(self, endpoint: str, session_token: str)`: store `self.endpoint`, `self.session_token`
      - `async def connect(self)`: open Unix socket connection to `self.endpoint`; store `self.reader, self.writer`
      - `async def send(self, action: str, **params)`: construct message `{"action": action, "session_token": self.session_token, **params}`; send as NDJSON line; read response; return parsed JSON
      - `async def disconnect(self)`: close writer if open
      - Support async context manager: `__aenter__` calls `connect()`, `__aexit__` calls `disconnect()`
    - `<acceptance_criteria>`:
      - `client.py` contains `class AdapterClient` with `__init__(endpoint, session_token)`
      - `connect()` establishes Unix socket connection to endpoint
      - `send(action, **params)` includes `session_token` in every message
      - `send()` writes NDJSON line and reads response
      - Class implements `__aenter__` and `__aexit__` for context manager

15. **Implement AdapterClient convenience methods**
    - `<read_first>`: `src/adapters/dummy_adapter/adapter.py` (to know expected actions)
    - `<action>`: Add methods: `async def create_tunnel(self, name: str, config: dict)`, `async def destroy_tunnel(self, name: str)`, `async def list_tunnels(self)`, `async def get_status(self, name: str)`. Each calls `self.send("create_tunnel", tunnel_name=name, config=config)` etc. and returns result.
    - `<acceptance_criteria>`:
      - `AdapterClient` has methods `create_tunnel(name, config)`, `destroy_tunnel(name)`, `list_tunnels()`, `get_status(name)`
      - Each method calls `self.send()` with appropriate action name and returns response

---

## Wave 4: Integration Tests and Smoke Test

### Plan 04-W1: Integration Test for Full Flow with Token Validation

**Objective:** Create an integration test that exercises the full Phase 1 flow: StartAdapter → Dummy adapter startup with token → CLI→Adapter CreateTunnel with token → AllocateTunnel → namespace (mocked) verification.

**Requirements:** TST-04, SEC-04, SEC-05, SEC-06, SEC-07

**Dependencies:** Waves 1-3 complete

**Files Modified:**
- `tests/integration/test_phase1_dummy_adapter.py` (new)
- `tests/conftest.py` (update if needed)

**Tasks:**

16. **Create integration test fixture for daemon**
    - `<read_first>`: `src/daemon/daemon.py`, `src/libvpnmanager/dbus/client.py`
    - `<action>`: Write pytest fixture `daemon()` that:
      - Creates `VPNDaemon` instance with test configuration (test socket paths under `/tmp/test-mtm-*`)
      - Starts daemon via `await daemon.start()` (ensure IPC server and control server)
      - Yields daemon
      - After test, shuts down daemon: `await daemon.stop()` and cleans up socket files
    - `<acceptance_criteria>`:
      - `tests/integration/conftest.py` (or new file) defines `async def daemon()` fixture
      - Fixture starts `VPNDaemon` and cleans up after test
      - Socket paths use `/tmp/test-mtm-*` prefix to avoid `/run` permission issues

17. **Create integration test for adapter startup with token**
    - `<read_first>`: `src/daemon/daemon.py`, `src/libvpnmanager/client.py`
    - `<action>`: Write test `test_adapter_startup_with_token(daemon)`:
      - Create `ManagerClient`, connect
      - Call `await client.start_adapter("dummy", {"username": "testuser"}, totp_code="dummy123456")`
      - Assert result `status == "started"` and `endpoint` starts with `unix://`
      - Verify adapter CLI socket exists at path without `unix://` prefix
      - Verify adapter process is running (`psutil.process_iter()` find child of daemon or check daemon.adapter_pool)
    - `<acceptance_criteria>`:
      - `test_phase1_dummy_adapter.py` contains `test_adapter_startup_with_token` async test
      - Test asserts returned `endpoint` is `unix:///run/mtm/adapters/testuser_dummy.sock` (or test variant)
      - Test verifies socket file exists on disk
      - Test verifies daemon.adapter_pool contains key `("dummy", "testuser")`

18. **Create integration test for token-protected CreateTunnel**
    - `<read_first>`: `src/libvpnmanager/client.py` (AdapterClient)
    - `<action>`: Write test `test_create_tunnel_with_token(daemon)`:
      - After `start_adapter` returns `session_id` and `endpoint`, create `AdapterClient(endpoint, session_token=session_id)`
      - `await client.connect()`
      - `result = await client.create_tunnel("tunnel1", {"country": "US", "protocol": "dummy"})`
      - Assert `result["status"] == "connected"` and `result["tunnel"]["device"] == "dummy0"`
      - Verify adapter's `tunnels` dict (via daemon or direct adapter introspection) contains `tunnel1`
    - `<acceptance_criteria>`:
      - Test calls `AdapterClient.create_tunnel` with `session_token`
      - Asserts response contains connected status and device name
      - Verifies tunnel was created successfully

19. **Create integration test for token rejection**
    - `<read_first>`: `src/adapters/dummy_adapter/adapter.py`
    - `<action>`: Write test `test_invalid_token_rejected(daemon)`:
      - Start adapter with valid totp_code → get endpoint and valid session_id
      - Create `AdapterClient(endpoint, session_token="invalid_token")`
      - Call `await client.create_tunnel("tunnel1", {})` should raise `AdapterConnectionError` or receive error response
      - Assert that tunnel was NOT created in adapter's `self.tunnels`
    - `<acceptance_criteria>`:
      - Test demonstrates that using wrong `session_token` fails
      - Failure is clean (connection closed or error response)
      - Adapter's `tunnels` dict remains empty after failed attempt

20. **Create integration test for concurrent connections**
    - `<read_first>`: `src/adapters/dummy_adapter/adapter.py` (check for `asyncio.Lock`)
    - `<action>`: Write test `test_concurrent_cli_connections(daemon)`:
      - Start adapter, get endpoint and session_id
      - Create 5 concurrent `AdapterClient(endpoint, session_token)` instances
      - Have each call `create_tunnel` with different names concurrently using `asyncio.gather`
      - Assert all succeed and devices are `dummy0` through `dummy4`
      - Verify adapter's `tunnels` dict has 5 entries
    - `<acceptance_criteria>`:
      - Test creates 5 adapters concurrent connections to same adapter
      - All 5 `create_tunnel` calls succeed
      - No race conditions (devices numbered correctly)
      - Demonstrates adapter serializes access correctly (code should use `asyncio.Lock` around `self.tunnels` modifications)

---

## Verification Criteria

**Phase 1 Complete When:**

1. **DAEM-01**: Adapter process spawning works with dual Unix sockets (CLI + control). Verified by `test_adapter_startup_with_token` showing adapter binds CLI socket and connects to control socket.
2. **DAEM-02**: Adapter pooling by `(adapter_type, vpn_username)` works. Verified by calling `StartAdapter` twice with same credentials returns existing endpoint; `ListAdapters` shows correct info.
3. **ADPT-01**: Adapter base class provides dual-server pattern. Verified by `DummyAdapter` code structure: one server for CLI, one client for control, both running concurrently.
4. **ADPT-02**: Control protocol works (Register, AllocateTunnel, ReleaseTunnel). Verified by `test_create_tunnel_with_token` showing AllocateTunnel exchange.
5. **ADPT-03**: Adapter reads credentials from stdin on startup. Verified by adapter code showing `sys.stdin.read()` or `await asyncio.stdin.read()`; test ensures credentials passed via spawn env are not in adapter's environment after startup.
6. **ADPT-06**: Adapter handles multiple concurrent CLI connections. Verified by `test_concurrent_cli_connections` passing.
7. **CLI-01**: `ManagerClient.start_adapter()` method exists and works. Verified by `test_adapter_startup_with_token` calling it successfully.
8. **CLI-02**: `AdapterClient` class exists, connects to adapter socket, sends JSON-RPC. Verified by `test_create_tunnel_with_token` using `AdapterClient` directly.
9. **TST-04**: Dummy adapter implementation exists and passes smoke test. Verified by all integration tests passing with dummy adapter.
10. **SEC-04**: CLI-level 2FA mandatory: `StartAdapter` accepts `totp_code` parameter (dummy in Phase 1). Verified by `test_adapter_startup_with_token` passing totp_code and adapter receiving it via env or control message.
11. **SEC-05**: MTM stores/stub TOTP secret securely: Phase 1 uses dummy token passed through; no real TOTP yet. Verified by code showing `SESSION_TOKEN` env passed to adapter; no TOTP secret in logs.
12. **SEC-06**: Adapter validates `session_token` on every CLI request. Verified by `test_invalid_token_rejected` failing with wrong token, `test_create_tunnel_with_token` succeeding with correct token.
13. **SEC-07**: Session token lifecycle: token passed in all messages, stored in adapter memory. Verified by code paths: `StartAdapter`→adapter env→AdapterClient→adapter validation.

**must_haves for Phase 1 goal:**
- Adapter startup works (dual sockets, control connection)
- Dummy tunnel creation works (CreateTunnel → AllocateTunnel flow)
- Concurrent connections handled
- Token infrastructure in place (dummy tokens flow through all layers)

---

## Implementation Notes

- **Token Model (Phase 1)**: Use a simple random string `session_token` generated by daemon and passed to adapter via environment variable `SESSION_TOKEN` or as part of first control message (`Register` response). Adapter stores and validates against this. No actual TOTP verification yet (that's Phase 4).
- **Socket Paths**: Use `/run/mtm/adapters/{username}_{adapter_type}.sock` in production; tests should use `/tmp/test-mtm-*` to avoid permission issues.
- **Permission Setup**: Daemon (running as root) creates `/run/mtm` dirs with `0755` and sets socket file mode to `0o600` after binding.
- **Control Protocol**: NDJSON lines. Errors return `{"status": "error", "error": "...", "code": "ERROR_CODE"}`.
- **Adapter Base**: If `libvpnmanager/adapters/base.py` doesn't already provide a good base, create one that implements `handle_control_loop` boilerplate and leaves `create_tunnel` abstract.

---

*Plan generated:* 2025-03-20 (manual fallback after agent credit error)
*Phase:* 01 — Foundation: Adapter Lifecycle & Core Protocol
