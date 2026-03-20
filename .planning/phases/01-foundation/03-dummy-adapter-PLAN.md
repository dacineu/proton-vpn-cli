---
wave: 2
objective: Create standalone dummy adapter executable with dual-server (CLI + control), stdin credential reading, Register to MTM, tunnel simulation, and session token validation
depends_on:
  - 2
files_modified:
  - multi-tunnel-namespace/src/adapters/dummy/cli.py (new)
  - multi-tunnel-namespace/src/adapters/dummy/__init__.py (maybe)
autonomous: false
---

<tasks>
<task id="1">
<description>Create dummy adapter CLI module structure with async main</description>
<read_first>
- multi-tunnel-namespace/src/libvpnmanager/adapters/dummy.py (existing DummyAdapter logic)\n- multi-tunnel-namespace/src/daemon/resource_allocator.py (control protocol example)\n</read_first>
<action>
1. Create new file: multi-tunnel-namespace/src/adapters/dummy/cli.py\n2. Add shebang: #!/usr/bin/env python3\n3. Imports: asyncio, json, os, logging, uuid, sys, Path from pathlib, struct, socket\n4. Define config globals from env:\n   - MTM_CONTROL_SOCKET = os.environ['MTM_CONTROL_SOCKET']\n   - MTM_ADAPTER_TYPE = os.environ['MTM_ADAPTER_TYPE'] (should be 'dummy')\n   - MTM_SESSION_NAME = os.environ['MTM_SESSION_NAME'] (OS username)\n5. Set up logging: logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', handlers=[logging.StreamHandler(sys.stderr)])\n6. async def main():\n   - Read startup stdin: line = await asyncio.get_reader().readline(); data = json.loads(line)\n   - Extract: session_id = data['session_id']; vpn_creds = data['vpn_credentials']; totp_secret = data.get('totp_secret')\n   - Zeroize credential buffer (if reading as bytes, overwrite with zeros; but we read as string → can't zeroize perfectly; in Python, use bytearray: cred_bytes = await read_all_of_stdin(); data = json.loads(cred_bytes); overwrite cred_bytes with zeros)\n   - Determine CLI socket path: from environment? Could derive: f'/run/mtm/adapters/{MTM_SESSION_NAME}_{MTM_ADAPTER_TYPE}.sock'. Or pass via env MTM_CLI_SOCKET. Simpler: derive same as daemon.\n   - Ensure parent dir exists (should already)\n   - Start CLI server: cli_server = await asyncio.start_unix_server(handle_cli, cli_socket_path)\n   - Set socket permissions: os.chmod(cli_socket_path, 0o600)\n   - Connect to MTM control socket: control_reader, control_writer = await asyncio.open_unix_connection(MTM_CONTROL_SOCKET)\n   - Send Register message with length-prefixed framing:\n     ```python\n     register = {'msg_type': 'register', 'session_id': session_id, 'adapter_type': MTM_ADAPTER_TYPE, 'username': MTM_SESSION_NAME, 'session_token': None}  # Phase 1: no token yet\n     await send_control(control_writer, register)\n     resp = await read_control(control_reader)\n     if resp.get('msg_type') != 'registered':\n         logger.error('Registration failed'); sys.exit(1)\n     ```\n   - Simulate VPN login: await asyncio.sleep(0.5); on success, zeroize vpn_creds (overwrite dict values)\n   - Set state: tunnels = {}; adapter.lock = asyncio.Lock()\n   - Log ready; await shutdown event (signal handler)\n7. Implement send_control and read_control using 4-byte big-endian length prefix\n8. Implement handle_cli(reader, writer): read newline-delimited JSON, parse request['action'], check session_token if present, route to create_tunnel/destroy_tunnel/list_tunnels/get_status handlers, send response line\n9. Add signal handlers for SIGTERM/SIGINT to gracefully shutdown\n10. if __name__ == '__main__': asyncio.run(main())\n</action>\n<acceptance_criteria>\n- adapters/dummy/cli.py exists and is executable (shebang present)\n- main() reads stdin startup payload with json.loads(readline())\n- main() binds CLI socket with asyncio.start_unix_server and sets mode 0o600\n- main() connects to MTM_CONTROL_SOCKET and sends register message (length-prefixed)\n- send_control/read_control implement 4-byte length prefix\n- handle_cli reads newline-delimited JSON and responds\n- handles CreateTunnel, DestroyTunnel, ListTunnels, GetStatus actions\n- has asyncio.Lock for protecting tunnels dict on concurrent connections\n</acceptance_criteria>
</task>

<task id="2">
<description>Implement CreateTunnel handler with AllocateTunnel control message</description>
<read_first>
- multi-tunnel-namespace/src/libvpnmanager/adapters/dummy.py (connect method returns Tunnel with device name)\n- 1-CONTEXT.md (dummy adapter behavior: varying device names, 500ms-1s delay)\n</read_first>
<action>
1. In cli.py, define global or instance state: `tunnels: Dict[str, Tunnel] = {}`; `_counter = 0`\n2. async def handle_create_tunnel(request):\n   - tunnel_name = request['tunnel_name']\n   - if tunnel_name in tunnels: return error 'Tunnel already exists'\n   - Simulate delay: await asyncio.sleep(random.uniform(0.5, 1.0))\n   - _counter += 1; device = f'dummy{_counter}'\n   - Build config object from request['config'] (use ConnectionConfig.from_dict if available, or ignore for dummy)\n   - Prepare AllocateTunnel control message:\n     ```json\n     {'msg_type': 'allocate', 'tunnel_name': tunnel_name, 'config': request.get('config', {}), 'username': MTM_SESSION_NAME}\n     ```\n   - Send via control channel and await response. If response['msg_type'] == 'allocated', namespace = response['namespace']\n   - Create Tunnel object (define minimal Tunnel dataclass locally or import from libvpnmanager.models.tunnel). Fields: name=tunnel_name, adapter='dummy', device=device, namespace=namespace, endpoint='dummy.example.com', connected_at=datetime.utcnow(), metadata={}\n   - tunnels[tunnel_name] = tunnel\n   - Return tunnel as JSON\n3. Return format: {'status': 'success', 'tunnel': tunnel.to_dict()} or just tunnel dict\n</action>\n<acceptance_criteria>\n- handle_create_tunnel checks for duplicate tunnel name (grep for "if tunnel_name in tunnels")\n- creates tunnel with device='dummy{_counter}' and increments counter\n- sends allocate control message with msg_type='allocate' including tunnel_name and username\n- waits for response and extracts namespace\n- stores tunnel in tunnels dict\n- returns tunnel dict with device, namespace fields\n</acceptance_criteria>
</task>

<task id="3">
<description>Implement DestroyTunnel and ListTunnels handlers</description>
<read_first>
- 1-CONTEXT.md (full API requirements)\n</read_first>
<action>
1. async def handle_destroy_tunnel(request):\n   - tunnel_name = request['tunnel_name']\n   - if tunnel_name not in tunnels: return error 'Tunnel not found'\n   - Send ReleaseTunnel control message: {'msg_type': 'release', 'tunnel_name': tunnel_name}\n   - await response\n   - del tunnels[tunnel_name]\n   - return {'status': 'success'}\n2. async def handle_list_tunnels(request):\n   - return {'tunnels': [t.to_dict() for t in tunnels.values()]}\n3. async def handle_get_status(request):\n   - tunnel_name = request['tunnel_name']\n   - if not in tunnels: return {'status': 'disconnected'}\n   - return {'status': 'connected'}\n4. Register these handlers in handle_cli via action routing\n</action>
<acceptance_criteria>\n- cli.py has functions handling 'DestroyTunnel', 'ListTunnels', 'GetStatus'\n- DestroyTunnel sends release control message\n- ListTunnels returns list of tunnel dicts\n- GetStatus returns connected if exists\n</acceptance_criteria>
</task>

<task id="4">
<description>Add session token validation to CLI request handler</description>
<read_first>
- 1-CONTEXT.md (Token Authentication Model: adapter validates session_token on CLI requests)\n</read_first>
<action>
1. In cli.py, store expected_session_token from Register response? Wait: Register response from MTM should include session_token if Phase 1 implements it. Update Register handler to extract 'session_token' from response and store globally: `expected_session_token = resp.get('session_token')`.\n2. In handle_cli, before routing action:\n   ```python\n   if expected_session_token is not None:\n       client_token = request.get('session_token')\n       if client_token != expected_session_token:\n           writer.write(json.dumps({'status': 'error', 'error': 'INVALID_SESSION'}).encode() + b'\\n')\n           await writer.drain()\n           return\n   ```\n3. Remove token from request after validation to avoid processing it\n</action>\n<acceptance_criteria>\n- cli.py stores expected_session_token after Register\n- handle_cli checks session_token against expected before processing\n- returns error on mismatch\n</acceptance_criteria>
</task>

<task id="5">
<description>Add graceful shutdown handling</description>
<read_first>
- multi-tunnel-namespace/src/daemon/daemon.py (signal handling pattern)\n</read_first>
<action>
1. Add shutdown Event: `shutdown_event = asyncio.Event()`\n2. Register signal handlers: loop = asyncio.get_event_loop(); for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, shutdown_event.set)\n3. In main, after starting servers, await shutdown_event.wait()\n4. On shutdown:\n   - Close CLI server: cli_server.close(); await cli_server.wait_closed()\n   - For each tunnel in tunnels, send ReleaseTunnel (but adapter exiting, may not matter)\n   - Close control writer\n   - Log shutdown\n5. Ensure sockets cleaned up? MTM may clean; but also try: Path(cli_socket_path).unlink(missing_ok=True)\n</action>\n<acceptance_criteria>\n- cli.py sets up signal handlers for SIGTERM/SIGINT\n- waits on shutdown_event\n- on shutdown, closes cli_server and control writer\n- attempts to unlink CLI socket file\n</acceptance_criteria>
</task>

<task id="6">
<description>Create __init__.py and ensure cli.py is executable; add setup.py entry point if applicable</description>
<read_first>
- Project structure (pyproject.toml or setup.py)\n</read_first>
<action>
1. Check if multi-tunnel-namespace/src/adapters/dummy/__init__.py exists; if not, create empty file\n2. Ensure cli.py has executable permission in repo (git tracks mode; set with chmod +x)\n3. If project uses pyproject.toml with [project.scripts], add entry point: `mtm-adapter-dummy = "adapters.dummy.cli:main"` or similar. Alternatively, the executable can be a symlink or wrapper. For development, ensure setup is such that `pyproject.toml` installs scripts. Update pyproject.toml if needed: in [project.scripts] add 'mtm-adapter-dummy = \"proton_vpn_manager.adapters.dummy.cli:main\"' (adjust import path based on package name). Verify existing script names pattern from adapter_registry._find_adapter_executable (looks for mtm-adapter-{type}). So the installed script should be named mtm-adapter-dummy.\n4. Update pyproject.toml if needed; but Phase 1 may just run python -m adapters.dummy.cli for testing. Document in tests.\n</action>
<acceptance_criteria>\n- adapters/dummy/__init__.py exists\n- cli.py is executable (chmod +x)\n- pyproject.toml contains project.scripts entry 'mtm-adapter-dummy' pointing to cli:main OR documentation indicates how to run adapter\n- _find_adapter_executable in daemon finds 'mtm-adapter-dummy' in PATH (which will be in venv bin)\n</acceptance_criteria>
</task>
</tasks>

<verification>
After Plan 3 completes:\n1. Install package in dev mode: pip install -e multi-tunnel-namespace/\n2. Verify script exists: which mtm-adapter-dummy\n3. Manually test by setting env MTM_CONTROL_SOCKET to a test socket and invoking (can use socat to dummy server)\n4. Integration test from Plan 5 will actually test end-to-end\n5. grep -r "class Tunnel" in libvpnmanager/models to see if we can import; if not, define minimal Tunnel in cli.py for now\n</verification>

<must_haves>
- Standalone dummy adapter executable with main()\n- Dual-server: CLI Unix socket + control client to MTM\n- stdin credential reading with zeroization\n- Register message sent to MTM\n- CreateTunnel/DestroyTunnel/ListTunnels/GetStatus implemented\n- AllocateTunnel/ReleaseTunnel control messages\n- Session token validation on CLI requests\n- Graceful shutdown\n- Executable installed via pyproject.toml entry point\n</must_haves>
