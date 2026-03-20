---
wave: 1
objective: Migrate Proton VPN adapter to dual-server pattern with stdin credentials, Register handshake, CLI request handling, and session reuse
depends_on:
  - 01-daemon-extensions
  - 02-control-protocol
  - 03-dummy-adapter
files_modified:
  - multi-tunnel-namespace/src/adapters/proton_vpn_adapter/cli.py
  - multi-tunnel-namespace/src/adapters/proton_vpn_adapter/adapter.py
autonomous: false
requirements_addressed:
  - ADPT-04
  - ADPT-05
---

<tasks>
<task id="1">
<description>Read and understand existing Proton adapter structure</description>
<read_first>
- multi-tunnel-namespace/src/adapters/proton_vpn_adapter/cli.py
- multi-tunnel-namespace/src/adapters/proton_vpn_adapter/adapter.py
</read_first>
<action>
Review current main() function and ProtonVPNAdapter class. Note env vars: MTM_SESSION_DATA, MTM_CONTROL_SOCKET, MTM_INTERNAL_SOCKET. Identify session reconstruction and UnixAdapterServer usage.
</action>
<acceptance_criteria>
- cli.py contains async def main() that reads MTM_SESSION_DATA env
- adapter.py defines class ProtonVPNAdapter with __init__(self, session=None) and _local_tunnels dict
</acceptance_criteria>
</task>

<task id="2">
<description>Replace environment-based credential loading with stdin payload</description>
<read_first>
- multi-tunnel-namespace/src/adapters/proton_vpn_adapter/cli.py
</read_first>
<action>
1. Remove reading MTM_SESSION_DATA env.
2. Read entire stdin: payload = json.loads(sys.stdin.read()).
3. Extract vpn_credentials dict and reconstruct ProtonSession from it.
4. Extract optional session_token for CLI authentication and store in adapter as self.expected_session_token.
</action>
<acceptance_criteria>
- cli.py contains import sys and reads sys.stdin.read()
- Payload JSON includes keys: vpn_credentials, session_id, vpn_username, optionally session_token
- ProtonSession created from payload['vpn_credentials']
- adapter.expected_session_token set from payload if present
</acceptance_criteria>
</task>

<task id="3">
<description>Implement dual-server: bind CLI socket and connect control socket</description>
<read_first>
- multi-tunnel-namespace/src/adapters/dummy_adapter/cli.py
- multi-tunnel-namespace/src/adapters/proton_vpn_adapter/cli.py
</read_first>
<action>
In main():
1. Get env vars: ADAPTER_ENDPOINT, CONTROL_ENDPOINT, SESSION_ID, VPN_USERNAME.
2. Bind CLI server: server = await asyncio.start_unix_server(handle_cli, ADAPTER_ENDPOINT). Set mode: os.chmod(ADAPTER_ENDPOINT, 0o600).
3. Connect to control: ctrl_reader, ctrl_writer = await asyncio.open_unix_connection(CONTROL_ENDPOINT).
4. Create adapter instance (after credentials loaded).
</action>
<acceptance_criteria>
- ADAPTER_ENDPOINT and CONTROL_ENDPOINT env vars read
- asyncio.start_unix_server called with handler handle_cli
- asyncio.open_unix_connection called to CONTROL_ENDPOINT
- Socket file mode set to 0o600
</acceptance_criteria>
</task>

<task id="4">
<description>Send Register handshake to MTM control socket</description>
<read_first>
- multi-tunnel-namespace/src/adapters/proton_vpn_adapter/cli.py
- multi-tunnel-namespace/src/daemon/daemon.py (control handler)
</read_first>
<action>
After control connection established:
1. Build Register message: {"action": "register", "session_id": SESSION_ID, "adapter_type": "proton", "username": VPN_USERNAME}.
2. If adapter.expected_session_token exists, include {"session_token": adapter.expected_session_token}.
3. Send as NDJSON line (json.dumps + \n).
4. Read response line; if status == "error", log error and exit.
</action>
<acceptance_criteria>
- Register message JSON contains action="register", session_id, adapter_type="proton", username
- Includes session_token if expected_session_token set
- Reads response; on error status, logs and exits
</acceptance_criteria>
</task>

<task id="5">
<description>Implement CLI request handler with session token validation</description>
<read_first>
- multi-tunnel-namespace/src/adapters/dummy_adapter/cli.py (handle_cli)
- multi-tunnel-namespace/src/adapters/proton_vpn_adapter/adapter.py
</read_first>
<action>
Create async def handle_cli(reader, writer):
1. Read NDJSON line, parse JSON request.
2. Check session_token: if missing or != adapter.expected_session_token, send error {"status": "error", "error": "INVALID_SESSION", "code": "INVALID_SESSION"} and close.
3. Dispatch based on method: CreateTunnel, DestroyTunnel, ListTunnels, GetStatus.
4. For CreateTunnel: call await adapter.create_tunnel(name, config).
5. Serialize response as JSON + newline, write to writer, await writer.drain().
</action>
<acceptance_criteria>
- handle_cli reads line, parses JSON
- Validates session_token against stored expected value; rejects mismatches
- Routes CreateTunnel to adapter.create_tunnel
- Writes JSON response followed by newline
</acceptance_criteria>
</task>

<task id="6">
<description>Implement tunnel operations on adapter (create, destroy, list, status)</description>
<read_first>
- multi-tunnel-namespace/src/adapters/proton_vpn_adapter/adapter.py
</read_first>
<action>
1. In ProtonVPNAdapter, ensure create_tunnel(name, config) method:
   - Call self._ensure_api()
   - Use Proton VPN core to create connection with tunnel_name
   - Store in self._local_tunnels[name] and self._connections[name]
   - Return {"status": "connected", "tunnel": {"name": name, "device": device}}
2. Implement destroy_tunnel(name): disconnect, remove from dicts, send ReleaseTunnel control message to MTM (via control socket writer stored in adapter), return {"status": "disconnected"}.
3. Implement list_tunnels(): return list of tunnel info dicts.
4. Implement get_status(): return overall adapter status dict.
</action>
<acceptance_criteria>
- adapter.create_tunnel stores tunnel in self._local_tunnels
- adapter.destroy_tunnel removes from self._local_tunnels and disconnects
- adapter.list_tunnels returns list of tunnel info
- adapter.get_status returns status dict
</acceptance_criteria>
</task>

<task id="7">
<description>Add asyncio.Lock for concurrent connection safety</description>
<read_first>
- multi-tunnel-namespace/src/adapters/proton_vpn_adapter/adapter.py
- multi-tunnel-namespace/src/adapters/dummy_adapter/adapter.py
</read_first>
<action>
1. In ProtonVPNAdapter.__init__, add self._lock = asyncio.Lock().
2. Wrap modifications to self._local_tunnels and self._connections in create_tunnel and destroy_tunnel with async with self._lock:.
</action>
<acceptance_criteria>
- self._lock is an asyncio.Lock instance
- create_tunnel uses async with self._lock around critical section
- destroy_tunnel uses async with self._lock
</acceptance_criteria>
</task>

<task id="8">
<description>Implement graceful shutdown</description>
<read_first>
- multi-tunnel-namespace/src/adapters/dummy_adapter/cli.py (signal handling)
</read_first>
<action>
In main():
1. Register signal handlers for SIGTERM and SIGINT.
2. On signal: cancel server, call adapter.cleanup() (iterate all tunnels, call destroy_tunnel), close control writer, exit.
</action>
<acceptance_criteria>
- signal.signal(SIGTERM, handler) and SIGINT set up
- Shutdown calls destroy_tunnel for all active tunnels
- Control socket closed before exit
</acceptance_criteria>
</task>
</tasks>

---
wave: 2
objective: Update CLI tunnel commands to use direct adapter flow, implement credential prompt logic, preserve legacy API
depends_on:
  - 02-proton-migration
files_modified:
  - multi-tunnel-namespace/src/cli/tunnel.py
  - multi-tunnel-namespace/src/libvpnmanager/client.py
autonomous: false
requirements_addressed:
  - CLI-03
  - CLI-04
---

<tasks>
<task id="1">
<description>Read existing tunnel create command</description>
<read_first>
- multi-tunnel-namespace/src/cli/tunnel.py (create function)
</read_first>
<action>
Understand current flow: client = ManagerClient(); await client.connect(); tunnel = await client.create_tunnel(config, username). Identify credential source (likely from session or keyring). Note output format.
</action>
<acceptance_criteria>
- create function uses ManagerClient().create_tunnel()
- Current credential source identified for later modification
</acceptance_criteria>
</task>

<task id="2">
<description>Add helper function ensure_adapter_running()</description>
<read_first>
- multi-tunnel-namespace/src/libvpnmanager/client.py (ManagerClient.verify_2fa, start_adapter)
</read_first>
<action>
Create async def ensure_adapter_running(adapter_type, credentials, totp_code=None):
1. client = ManagerClient(); await client.connect()
2. If totp_code provided: await client.verify_2fa(totp_code)
3. resp = await client.start_adapter(adapter_type, credentials)
4. Return resp['endpoint']
Ensure client.disconnect() in finally.
</action>
<acceptance_criteria>
- Function calls ManagerClient.verify_2fa() and start_adapter()
- Returns adapter endpoint string
- Properly manages client connection lifecycle
</acceptance_criteria>
</task>

<task id="3">
<description>Add credential prompt logic with adapter reuse check</description>
<read_first>
- multi-tunnel-namespace/src/cli/tunnel.py
</read_first>
<action>
Implement async def prompt_credentials_if_needed(adapter_type):
1. client = ManagerClient(); await client.connect()
2. adapters = await client.list_adapters()
3. If any adapter matches adapter_type and current username, return None (reuse, no prompt)
4. Else: username = click.prompt("Username"); password = click.prompt("Password", hide_input=True); return {"username": username, "password": password}
5. Finally: await client.disconnect()
</action>
<acceptance_criteria>
- Calls list_adapters() to check existing adapter
- Uses click.prompt for interactive username/password
- Returns credentials dict or None
- Properly disconnects client
</acceptance_criteria>
</task>

<task id="4">
<description>Refactor tunnel create command to use new adapter flow</description>
<read_first>
- multi-tunnel-namespace/src/cli/tunnel.py
- multi-tunnel-namespace/src/libvpnmanager/client.py (AdapterClient)
</read_first>
<action>
Replace old flow in create command:
1. creds = await prompt_credentials_if_needed(adapter_type)
2. endpoint = await ensure_adapter_running(adapter_type, creds)
3. adapter_client = AdapterClient(endpoint, session_token)  # session_token from verify_2fa earlier or None
4. await adapter_client.connect()
5. tunnel = await adapter_client.create_tunnel(name=session_name, config=config)
6. Print success output (same format as before)
7. Finally: adapter_client.disconnect()
</action>
<acceptance_criteria>
- create command uses prompt_credentials_if_needed(), ensure_adapter_running(), AdapterClient
- Does NOT call ManagerClient.create_tunnel()
- Success output displays tunnel details (name, adapter, session, device, namespace, endpoint)
</acceptance_criteria>
</task>

<task id="5">
<description>Preserve legacy ManagerClient.create_tunnel for backward compatibility</description>
<read_first>
- multi-tunnel-namespace/src/libvpnmanager/client.py
</read_first>
<action>
Ensure ManagerClient.create_tunnel(config, username) method exists:
- It should call the daemon's legacy D-Bus CreateTunnel API (which internally uses adapter via StartAdapter + control channel, as implemented in Phase 1).
- Must not raise NotImplementedError.
- Document as deprecated but maintained.
</action>
<acceptance_criteria>
- ManagerClient.create_tunnel() method present and callable
- Old code using this method continues to work
- Implementation uses daemon's legacy D-Bus path
</acceptance_criteria>
</task>
</tasks>

---
wave: 3
objective: Add adapter list and stop subcommands to CLI for managing running adapters
depends_on:
  - 02-proton-migration
files_modified:
  - multi-tunnel-namespace/src/cli/adapter.py (new)
  - multi-tunnel-namespace/src/cli/main.py
autonomous: false
requirements_addressed:
  - CLI-05
---

<tasks>
<task id="1">
<description>Create adapter command group (new file)</description>
<read_first>
- multi-tunnel-namespace/src/cli/tunnel.py (click.group pattern)
</read_first>
<action>
Create multi-tunnel-namespace/src/cli/adapter.py with:
import click
from libvpnmanager.client import ManagerClient
@click.group(name="adapter")
def adapter_group():
    """Manage adapter lifecycle."""
</action>
<acceptance_criteria>
- File src/cli/adapter.py exists with @click.group function adapter_group
</acceptance_criteria>
</task>

<task id="2">
<description>Implement adapter list command</description>
<read_first>
- multi-tunnel-namespace/src/cli/tunnel.py (list_tunnels)
- multi-tunnel-namespace/src/cli/adapter.py
</read_first>
<action>
In adapter.py add:
@adapter_group.command(name="list")
async def list_adapters():
    client = ManagerClient()
    await client.connect()
    try:
        adapters = await client.list_adapters()
        for a in adapters:
            click.echo(f"{a['type']}/{a['username']} {a['endpoint']} (tunnels: {a['tunnel_count']}, status: {a['status']})")
    finally:
        await client.disconnect()
</action>
<acceptance_criteria>
- Command protonvpn adapter list available
- Calls ManagerClient.list_adapters()
- Outputs lines with type/username, endpoint, tunnel count, status
</acceptance_criteria>
</task>

<task id="3">
<description>Implement adapter stop command</description>
<read_first>
- multi-tunnel-namespace/src/cli/tunnel.py
- multi-tunnel-namespace/src/libvpnmanager/client.py (stop_adapter)
</read_first>
<action>
In adapter.py add:
@adapter_group.command(name="stop")
@click.argument("adapter_type", type=click.Choice(["proton", "psiphon", "wireguard", "dummy"]))
async def stop_adapter(adapter_type):
    client = ManagerClient()
    await client.connect()
    try:
        await client.stop_adapter(adapter_type)
        click.echo(f"Adapter '{adapter_type}' stopped.")
    finally:
        await client.disconnect()
</action>
<acceptance_criteria>
- Command protonvpn adapter stop proton available
- Calls ManagerClient.stop_adapter(adapter_type)
- Prints confirmation message
</acceptance_criteria>
</task>

<task id="4">
<description>Register adapter group in main CLI</description>
<read_first>
- multi-tunnel-namespace/src/cli/main.py (or equivalent entry point)
</read_first>
<action>
1. Import adapter_group from cli.adapter
2. Add to main command group: protonvpn.add_command(adapter_group) or similar
3. Ensure package __init__ exports it if needed
</action>
<acceptance_criteria>
- protonvpn adapter ... commands work (verify with --help)
- Command group properly registered under root CLI
</acceptance_criteria>
</task>
</tasks>

---
wave: 4
objective: Integration tests for Phase 2 success criteria: adapter startup, tunnel creation/reuse, adapter management, legacy compatibility
depends_on:
  - 02-proton-migration
  - 02-cli-integration
  - 02-adapter-subcommands
files_modified:
  - multi-tunnel-namespace/tests/integration/test_phase2_proton_adapter.py (new)
  - multi-tunnel-namespace/tests/integration/conftest.py (extend)
autonomous: false
requirements_addressed:
  - CLI-03
  - CLI-04
  - CLI-05
---

<tasks>
<task id="1">
<description>Set up test fixtures for Proton adapter</description>
<read_first>
- multi-tunnel-namespace/tests/integration/conftest.py
- multi-tunnel-namespace/tests/integration/test_phase1_foundation.py
</read_first>
<action>
1. Add fixture daemon_with_temp_dirs (or reuse existing) that starts VPNDaemon with temporary /run dirs.
2. Add fixture manager_client that connects to test daemon.
3. Add mock for Proton VPN core API using unittest.mock to simulate multi-tunnel behavior (since real credentials not available).
</action>
<acceptance_criteria>
- Fixtures exist and provide working daemon instance
- Tests can import and use daemon and manager_client fixtures
- Mock Proton API provides create_connection, disconnect, etc.
</acceptance_criteria>
</task>

<task id="2">
<description>Test adapter startup with stdin credentials</description>
<read_first>
- New test file
</read_first>
<action>
Write test test_proton_adapter_startup():
1. Prepare dummy credentials JSON payload (username, password).
2. Use daemon fixture to get daemon instance.
3. Call daemon._spawn_adapter("proton", username, session_id, credentials) with test executable that points to adapted proton cli.
4. Wait for ADAPTER_ENDPOINT socket to appear.
5. Use AdapterClient to connect, send GetStatus, expect success response.
6. Assert adapter in daemon.adapter_pool.
</action>
<acceptance_criteria>
- Test passes: adapter process starts, binds CLI socket, accepts GetStatus
- session_token validated (include token in request, ensure accepted)
</acceptance_criteria>
</task>

<task id="3">
<description>Test tunnel creation and session reuse</description>
<read_first>
- New test file
</read_first>
<action>
Write test test_tunnel_creation_and_reuse():
1. Start adapter as in task 2.
2. AdapterClient create_tunnel(name="tunnel1", config=mock_config). Assert response has device/namespace; check adapter._local_tunnels contains "tunnel1".
3. AdapterClient create_tunnel(name="tunnel2", config=mock_config). Assert success; check adapter._local_tunnels contains both tunnels.
4. Ensure no credential prompts were needed (adapter already running).
</action>
<acceptance_criteria>
- Multiple tunnels created from same adapter instance
- Distinct tunnel info returned
- Adapter reused without respawn
</acceptance_criteria>
</task>

<task id="4">
<description>Test adapter list and stop</description>
<read_first>
- New test file
</read_first>
<action>
Write test test_adapter_list_stop():
1. Start proton adapter.
2. Call ManagerClient.list_adapters(); assert adapter appears in list with type "proton" and correct username.
3. Call ManagerClient.stop_adapter("proton").
4. Wait briefly; verify adapter process exited and no longer in adapter_pool.
5. list_adapters() should not include it.
</action>
<acceptance_criteria>
- list_adapters returns running adapter before stop
- stop_adapter terminates adapter process cleanly
- Adapter removed from list after stop
</acceptance_criteria>
</task>

<task id="5">
<description>Test credential prompt logic</description>
<read_first>
- New test file
</read_first>
<action>
Two tests:
A) test_credential_prompt_shown_when_adapter_missing:
   - Ensure no proton adapter running.
   - Simulate CLI tunnel create command using click.testing.CliRunner or direct function call.
   - Mock click.prompt to provide fake credentials.
   - Assert that prompt was invoked (e.g., via mock call count).
   - Assert adapter starts and tunnel created.
B) test_credential_prompt_skipped_when_adapter_running:
   - Start adapter manually first.
   - Invoke tunnel create; assert click.prompt NOT called (mock returns without prompt).
   - Tunnel created successfully.
</action>
<acceptance_criteria>
- Test A: credentials requested when no adapter running
- Test B: credentials NOT requested when adapter already running
</acceptance_criteria>
</task>

<task id="6">
<description>End-to-end smoke test verifying success criteria</description>
<read_first>
- New test file
</read_first>
<action>
Create test_phase2_success_criteria() that demonstrates full flow:
1. User runs protonvpn tunnel create personal --adapter proton --country US --protocol wireguard.
2. Credentials prompted (simulate with input).
3. Adapter starts.
4. Tunnel created and connected.
5. Second tunnel (work) created without further credentials.
6. protonvpn adapter list shows running proton adapter.
7. protonvpn adapter stop proton stops adapter.
Assert each step produces expected outcomes.
</action>
<acceptance_criteria>
- All three ROADMAP success criteria verified programmatically
- Test passes end-to-end
</acceptance_criteria>
</task>

<task id="7">
<description>Verify legacy D-Bus API still works</description>
<read_first>
- multi-tunnel-namespace/src/libvpnmanager/client.py
</read_first>
<action>
Write test test_legacy_create_tunnel_still_works():
1. Use ManagerClient (not AdapterClient).
2. Call create_tunnel(config, username) old-style.
3. Assert it succeeds and creates a tunnel (likely still uses adapter under the hood via legacy D-Bus).
</action>
<acceptance_criteria>
- Legacy API path does not raise NotImplementedError
- Creates tunnel successfully
</acceptance_criteria>
</task>
</tasks>
