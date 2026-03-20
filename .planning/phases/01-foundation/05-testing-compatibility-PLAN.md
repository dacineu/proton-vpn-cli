---
wave: 3
objective: Write integration tests for end-to-end Phase 1 flow and ensure legacy D-Bus API works with adapter pooling; verify all success criteria
depends_on:
  - 1
  - 2
  - 3
  - 4
files_modified:
  - multi-tunnel-namespace/tests/integration/test_phase1_foundation.py (new)
  - multi-tunnel-namespace/src/daemon/daemon.py (legacy compatibility fixes)
  - multi-tunnel-namespace/src/libvpnmanager/client.py (test helpers)
autonomous: false
---

<tasks>
<task id="1">
<description>Set up test infrastructure: fixtures for daemon, adapter, and client</description>
<read_first>
- Existing test structure (pytest, pytest-asyncio?) in project\n- multi-tunnel-namespace/tests/ directory if exists\n</read_first>
<action>
1. Determine test layout: likely using pytest. Create multi-tunnel-namespace/tests/integration/ if not exists\n2. Create conftest.py with fixtures:\n   - `daemon_process`: starts VPNDaemon in subprocess with test config (temp dirs for /run/mtm). Use asyncio to spawn? Better: use pytest fixture with subprocess.Popen and yield, then terminate.\n   - `manager_client`: ManagerClient connected to daemon's D-Bus socket (test config should set IPC to unix-socket path in temp dir).\n   - `adapter_endpoint`: from start_adapter\n3. Fixture should ensure cleanup: stop adapter, terminate daemon, remove temp dirs\n4. Use tmp_path fixture for temporary /run/mtm equivalent\n5. Provide helper to wait for socket availability\n</action>
<acceptance_criteria>\n- tests/integration/conftest.py exists with fixtures: daemon_process, manager_client\n- daemon_process fixture starts daemon with environment variable PROTONVPN_IPC=unix-socket and custom socket paths in tmp dir\n- daemon_process fixture terminates daemon after test\n- manager_client fixture returns connected ManagerClient instance\n</acceptance_criteria>
</task>

<task id="2">
<description>Write integration test: adapter startup returns endpoint and process is running</description>
<read_first>
- conftest.py fixtures\n- client.py ManagerClient.start_adapter\n</read_first>
<action>
1. Create test_phase1_foundation.py\n2. Test function: `test_adapter_startup(manager_client)`\n   - creds = {'username': 'testuser', 'password': 'testpass'}\n   - totp = await manager_client.verify_2fa('123456')  # dummy accepts\n   - endpoint = await manager_client.start_adapter('dummy', creds, session_token=totp['session_token'])\n   - assert endpoint.startswith('unix://')\n   - socket_path = endpoint.replace('unix://', '')\n   - assert Path(socket_path).exists() and os.stat(socket_path).st_mode & 0o777 == 0o600\n   - Check daemon's adapter_pool includes the adapter (via manager_client.list_adapters())\n   - assert any(a['adapter_type']=='dummy' and a['username']=='testuser' for a in adapters)\n</action>
<acceptance_criteria>\n- tests/integration/test_phase1_foundation.py contains test_adapter_startup\n- test calls verify_2fa then start_adapter\n- asserts endpoint string and socket file exists with 0600 perms\n- asserts adapter appears in list_adapters\n- test passes with real daemon and dummy adapter process\n</acceptance_criteria>
</task>

<task id="3">
<description>Write integration test: create tunnel via AdapterClient</description>
<read_first>
- test file and fixtures\n</read_first>
<action>
1. In test_phase1_foundation.py, add async def test_create_tunnel(manager_client):\n   - Use pattern: endpoint = await manager_client.start_adapter(...)\n   - async with AdapterClient(endpoint, session_token=token) as adapter:\n       config = ConnectionConfig(...)  # need minimal config; can use DummyConnectionConfig or just dict\n       tunnel = await adapter.create_tunnel('tunnel1', config)\n       assert tunnel.name == 'tunnel1'\n       assert tunnel.adapter == 'dummy'\n       assert tunnel.device.startswith('dummy')\n       assert tunnel.namespace.startswith('vpn_')\n   - Also verify namespace exists? ResourceAllocator creates it; can check via routing or just rely on test passing if no exception\n</action>
<acceptance_criteria>\n- test_create_tunnel creates tunnel via AdapterClient\n- verifies tunnel object fields (device, namespace)\n- test passes\n</acceptance_criteria>
</task>

<task id="4">
<description>Write integration test: concurrent connections to same adapter</description>
<read_first>
- test file\n</read_first>
<action>
1. async def test_concurrent_connections(manager_client):\n   - endpoint = await manager_client.start_adapter('dummy', creds, token)\n   - async with AdapterClient(endpoint, token) as adapter1:\n       async with AdapterClient(endpoint, token) as adapter2:\n           # Both connect to same adapter\n           config1 = ConnectionConfig(tunnel_name='conc1'); config2 = ConnectionConfig(tunnel_name='conc2')\n           # Create tunnels concurrently\n           results = await asyncio.gather(\n               adapter1.create_tunnel('conc1', config1),\n               adapter2.create_tunnel('conc2', config2),\n           )\n           assert len(results) == 2\n           assert results[0].name == 'conc1'\n           assert results[1].name == 'conc2'\n           # Verify both tunnels exist in adapter's internal list\n           tunnels = await adapter1.list_tunnels()\n           assert len(tunnels) == 2\n   - Ensure no race conditions; adapter's asyncio.Lock protects self.tunnels\n</action>
<acceptance_criteria>\n- test_concurrent_connections spawns two AdapterClient instances sharing same endpoint\n- both create tunnels concurrently via asyncio.gather\n- asserts both tunnels created and listed\n- test passes without exceptions\n</acceptance_criteria>
</task>

<task id="5">
<description>Write integration test: token validation (reject invalid token)</description>
<read_first>
- test file\n</read_first>
<action>
1. async def test_token_validation(manager_client):\n   - Get valid endpoint and token\n   - Try create_tunnel with wrong token: adapter = AdapterClient(endpoint, session_token='wrong')\n   - with pytest.raises(TunnelError) or AdapterConnectionError, or check response error\n   - assert 'INVALID_SESSION' in error message\n   - With correct token should succeed\n</action>
<acceptance_criteria>\n- test creates AdapterClient with invalid session_token\n- attempt to create_tunnel raises error (TunnelError or specific)\n- correct token works\n</acceptance_criteria>
</task>

<task id="6">
<description>Implement legacy D-Bus CreateTunnel compatibility: forward to adapter</description>
<read_first>
- multi-tunnel-namespace/src/daemon/daemon.py (existing CreateTunnel method if any)\n</read_first>
<action>
1. Locate existing CreateTunnel D-Bus method in daemon.py. It likely uses in-process adapter. Replace or wrap:\n   - Old code probably does: adapter = self._get_adapter(); return await adapter.connect(config)\n   - New behavior: Ensure adapter is running via get_adapter_endpoint (which calls start_adapter internally), then use AdapterClient to send CreateTunnel directly.\n   - Implementation steps:\n     a. In create_tunnel method, after obtaining tunnel config, call `endpoint = await self.get_adapter_endpoint(adapter_type, session_name, username)` (need to derive adapter_type from config? maybe config.adapter_type). The existing method parameters: likely (tunnel_name, config, username). Need to know adapter_type — could be in config.adapter or default to 'dummy'.\n     b. Create AdapterClient(endpoint, session_token?) — but legacy D-Bus caller doesn't provide session_token. Phase 1: legacy API should still work without 2FA? Or require token via some mechanism. Simpler: legacy path bypasses token requirement (old API doesn't use token). But adapter expects session_token. Workaround: when adapter spawned by get_adapter_endpoint, store the expected session_token in adapter instance, and legacy path needs to include it. But legacy caller doesn't have token. Options:\n        - Legacy CreateTunnel accepts session_token from caller? Break compatibility.\n        - MTM internally injects session_token when forwarding to adapter: MTM knows adapter's expected_session_token from registration. So when forwarding, MTM should include that token in the AdapterClient request.\n     c. Implementation: after getting endpoint, retrieve adapter from self.adapter_registry by key; get adapter.expected_session_token; then create AdapterClient(endpoint, session_token=expected_token); call create_tunnel and return result.\n   - This preserves legacy D-Bus API signature unchanged while internally using direct adapter communication.\n2. Update get_adapter_endpoint to use new start_adapter logic (already done in Plan 1). Ensure it returns endpoint suitable.\n3. Test that legacy CreateTunnel still works (can be part of integration tests or separate test)\n</action>
<acceptance_criteria>\n- daemon.py's create_tunnel method (or equivalent) now calls get_adapter_endpoint and uses AdapterClient to forward request\n- AdapterClient includes session_token retrieved from adapter registry\n- Old D-Bus signature unchanged\n- Integration test: call ManagerClient.create_tunnel (which calls D-Bus) and verify tunnel created\n</acceptance_criteria>
</task>

<task id="7">
<description>Write end-to-end smoke test covering all success criteria</description>
<read_first>
- Phase 1 success criteria from ROADMAP\n- test file\n</read_front>
<action>
1. In test_phase1_foundation.py, create async def test_phase1_success_criteria(manager_client):\n   - Verify adapter startup: start_adapter returns endpoint; process running; socket exists\n   - Verify dummy tunnel creation: AdapterClient().create_tunnel returns tunnel with device name\n   - Verify concurrent connections: spawn multiple AdapterClient connections and create tunnels concurrently\n   - Verify token auth: test invalid token rejection and valid token acceptance\n2. Use pytest markers: @pytest.mark.asyncio\n3. Run with: pytest tests/integration/test_phase1_foundation.py -v\n</action>
<acceptance_criteria>\n- test_phase1_success_criteria covers all 4 success criteria\n- test passes with daemon and dummy adapter running\n- Output shows SUCCESS for each criterion\n</acceptance_criteria>
</task>

<task id="8">
<description>Ensure Build and Installation: Update pyproject.toml to include dummy adapter entry point and package data</description>
<read_first>
- multi-tunnel-namespace/pyproject.toml\n</read_first>
<action>
1. In [project.scripts] section, ensure 'mtm-adapter-dummy = \"proton_vpn_manager.adapters.dummy.cli:main\"' exists\n2. If package data needed (nothing), ensure include package data = true\n3. Verify install: pip install -e multi-tunnel-namespace/ and check mtm-adapter-dummy in bin\n4. Update any manifest files if necessary\n</action>
<acceptance_criteria>\n- pyproject.toml contains script entry for mtm-adapter-dummy\n- pip install -e . succeeds and places script in .venv/bin or user bin\n- which mtm-adapter-dummy resolves\n</acceptance_criteria>
</task>
</tasks>

<verification>
After all plans executed:\n1. Run integration test suite: pytest tests/integration/test_phase1_foundation.py -v\n   - All tests must pass\n2. Manually test legacy CLI flow: using ManagerClient.create_tunnel (which internally uses new adapter) returns valid tunnel\n3. Verify socket permissions: /run/mtm/adapters/testuser_dummy.sock has 0600\n4. Verify adapter process appears in process table\n5. Verify crash cleanup: kill adapter, check namespace deleted\n6. grep -r \"verify_2fa\" and \"start_adapter\" in client.py\n7. grep -r \"AdapterClient\" in client.py\n8. grep -r \"mtm-adapter-dummy\" in pyproject.toml\n9. Check that Phase 1 success criteria are demonstrated by tests\n</verification>

<must_haves>
- Integration tests covering adapter startup, tunnel creation, concurrent connections, token validation\n- Legacy D-Bus CreateTunnel works unchanged (transparently uses new adapter)\n- Dummy adapter executable installable via pyproject.toml\n- All 4 success criteria verified via tests\n- Build/install works for adapter standalone script\n</must_haves>
