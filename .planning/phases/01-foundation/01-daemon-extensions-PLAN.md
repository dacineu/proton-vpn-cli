---
wave: 1
objective: Implement daemon-side adapter lifecycle management: StartAdapter, ListAdapters, StopAdapter, adapter_pool tracking, and token infrastructure
depends_on: []
files_modified:
  - multi-tunnel-namespace/src/daemon/daemon.py
  - multi-tunnel-namespace/src/daemon/adapter_registry.py
autonomous: false
---

<tasks>
<task id="1">
<description>Add adapter_pool tracking to VPNDaemon and initialize in __init__</description>
<read_first>
- multi-tunnel-namespace/src/daemon/daemon.py (VPNDaemon class)
- multi-tunnel-namespace/src/daemon/adapter_registry.py (AdapterRegistry)
</read_first>
<action>
1. In VPNDaemon.__init__ (daemon.py), after `self.adapter_registry = AdapterRegistry()`, add: `self.adapter_pool: Dict[tuple[str, str], str] = {}`  # key: (adapter_type, vpn_username) -> endpoint\n2. Also add token store: `self.session_tokens: Dict[str, tuple[float, str]] = {}`  # token -> (expiry, username)\n3. Add `import uuid, secrets` at top of daemon.py if not present
</action>
<acceptance_criteria>
- grep "self.adapter_pool" daemon/daemon.py shows dictionary definition in __init__
- grep "self.session_tokens" daemon/daemon.py shows dictionary definition
- Type hints present: Dict[tuple[str, str], str] for adapter_pool
</acceptance_criteria>
</task>

<task id="2">
<description>Implement Verify2FA D-Bus method (session token issuance)</description>
<read_first>
- multi-tunnel-namespace/src/daemon/daemon.py (existing D-Bus method patterns)
- .planning/REQUIREMENTS.md (SEC-04, SEC-05)
</read_first>
<action>
1. In VPNDaemon class in daemon.py, add async def verify_2fa(self, totp_code: str) -> Dict[str, Any]:\n   - For Phase 1, use dummy validation: accept any 6-digit code (\"^\\d{6}$\")\n   - Generate token: token = secrets.token_urlsafe(32)\n   - expiry = time.time() + 900 (15 minutes)\n   - Store in self.session_tokens[token] = (expiry, username) — but username not yet known; for now store with placeholder\n   - Actually, Phase 1 token flow: CLI calls Verify2FA before StartAdapter, but StartAdapter may not have username yet. Simpler: Verify2FA returns {\"session_token\": token, \"expires_in\": 900}.\n   - Implementation:\n     ```python\n     async def verify_2fa(self, totp_code: str) -> Dict[str, Any]:\n         if not re.match(r'^\\d{6}$', totp_code):\n             raise AuthenticationError(\"Invalid TOTP code\")\n         token = secrets.token_urlsafe(32)\n         expiry = time.time() + 900\n         self.session_tokens[token] = (expiry, \"pending\")\n         return {\"session_token\": token, \"expires_in\": 900}\n     ```\n2. Add D-Bus method registration\n3. Ensure VPNDaemon has access to time module (import time) and re module\n</action>
<acceptance_criteria>
- daemon.py contains async def verify_2fa(self, totp_code: str) method\n- method validates totp_code format (6 digits) using regex\n- method generates token with secrets.token_urlsafe(32)\n- method stores token in self.session_tokens with 900s expiry\n- method returns dict with 'session_token' and 'expires_in'\n- D-Bus method exposed (search for @dbus.service.method or equivalent registration for 'Verify2FA')\n</acceptance_criteria>
</task>

<task id="3">
<description>Extend _spawn_adapter to deliver credentials via stdin instead of environment</description>
<read_first>
- multi-tunnel-namespace/src/daemon/daemon.py (_spawn_adapter method)
</read_first>
<action>
1. Rename existing _spawn_adapter to _spawn_adapter_with_stdio or modify it to accept stdin_data parameter\n2. Change: instead of putting credentials in env, create proc with stdin=PIPE:\n   ```python\n   proc = await asyncio.create_subprocess_exec(\n       exe,\n       stdin=asyncio.subprocess.PIPE,\n       stdout=asyncio.subprocess.PIPE,\n       stderr=asyncio.subprocess.PIPE,\n       env=env,\n   )\n   startup_payload = {\n       \"session_id\": session_id,\n       \"totp_secret\": None,\n       \"vpn_credentials\": credentials,\n   }\n   proc.stdin.write(json.dumps(startup_payload).encode() + b'\\n')\n   await proc.stdin.drain()\n   proc.stdin.close()\n   ```\n3. Keep existing logging of spawn success\n4. Remove MTM_SESSION_DATA from env (no longer needed)\n</action>
<acceptance_criteria>
- daemon.py contains code that writes to proc.stdin\n- startup_payload includes session_id and vpn_credentials\n- env passed to create_subprocess_exec does NOT include MTM_SESSION_DATA\n- proc.stdin.close() called after write\n</acceptance_criteria>
</task>

<task id="4">
<description>Add StartAdapter D-Bus method with session token validation and pool lookup</description>
<read_first>
- multi-tunnel-namespace/src/daemon/daemon.py (VPNDaemon class structure)\n- multi-tunnel-namespace/src/daemon/adapter_registry.py (get_adapter_endpoint pattern)\n</read_first>
<action>
1. In VPNDaemon class, add async def start_adapter(self, adapter_type: str, credentials: Dict[str, Any], session_token: Optional[str] = None) -> Dict[str, Any]:\n2. Validate adapter_type: if adapter_type not in await self.list_adapters(): raise AdapterNotFoundError\n3. Extract vpn_username from credentials['username']\n4. key = (adapter_type, vpn_username)\n5. Check adapter_pool: if key in self.adapter_pool: return {'endpoint': self.adapter_pool[key]}\n6. Validate session_token if provided:\n   - if session_token not in self.session_tokens: raise AuthenticationError('Invalid session token')\n   - expiry, _ = self.session_tokens[session_token]\n   - if time.time() > expiry: del self.session_tokens[session_token]; raise AuthenticationError('Session token expired')\n7. Generate session_id = str(uuid.uuid4())\n8. Create cli_socket_path = f\"/run/mtm/adapters/{vpn_username}_{adapter_type}.sock\"\n9. Ensure directory exists; remove stale socket\n10. Spawn adapter via modified _spawn_adapter with stdin\n11. Wait for socket up to 10s with retry loop\n12. Register with adapter_registry\n13. Add to adapter_pool: self.adapter_pool[key] = f\"unix://{cli_socket_path}\"\n14. Consume session_token: if session_token in self.session_tokens: del self.session_tokens[session_token]\n15. Return {'endpoint': f'unix://{cli_socket_path}'}\n</action>
<acceptance_criteria>
- daemon.py contains async def start_adapter\n- start_adapter validates adapter_type\n- extracts vpn_username and checks adapter_pool\n- validates session_token presence and expiry\n- creates socket path with correct naming\n- spawns adapter with stdin\n- waits for socket with 10s timeout\n- adds to adapter_pool\n- deletes used session_token\n- returns dict with 'endpoint'\n</acceptance_criteria>
</task>

<task id="5">
<description>Add ListAdapters D-Bus method</description>
<read_first>
- multi-tunnel-namespace/src/daemon/daemon.py (existing D-Bus methods)\n</read_first>
<action>
1. In VPNDaemon class, add async def list_adapters(self, username: Optional[str] = None) -> List[Dict[str, Any]]:\n   result = []\n   for (atype, uname), endpoint in self.adapter_pool.items():\n       if username is None or uname == username:\n           result.append({'adapter_type': atype, 'username': uname, 'endpoint': endpoint})\n   return result\n2. Register as D-Bus method 'ListAdapters'\n</action>
<acceptance_criteria>
- daemon.py contains async def list_adapters(self, username=None)\n- method iterates self.adapter_pool and returns list of dicts\n- D-Bus method registered\n</acceptance_criteria>
</task>

<task id="6">
<description>Add StopAdapter D-Bus method</description>
<read_first>
- multi-tunnel-namespace/src/daemon/adapter_registry.py (terminate_adapter method)\n</read_first>
<action>
1. In VPNDaemon class, add async def stop_adapter(self, adapter_type: str, username: Optional[str] = None) -> bool:\n   if username is None: raise ValueError(\"username required\")\n   key = (adapter_type, username)\n   if key not in self.adapter_pool: return False\n   del self.adapter_pool[key]\n   success = await self.adapter_registry.terminate_adapter(adapter_type, username)\n   return success\n2. Register as D-Bus method 'StopAdapter'\n</action>
<acceptance_criteria>
- daemon.py contains async def stop_adapter\n- deletes key from adapter_pool\n- calls adapter_registry.terminate_adapter\n- returns bool\n</acceptance_criteria>
</task>
</tasks>

<verification>
After executing all tasks in this PLAN:\n1. Start daemon and call methods:\n   - Verify2FA('123456') returns {'session_token': '...', 'expires_in': 900}\n   - StartAdapter('dummy', {'username': 'alice', 'password': 'pw'}, session_token) returns {'endpoint': 'unix:///run/mtm/adapters/alice_dummy.sock'}\n   - Socket file exists with 0600\n   - Second StartAdapter returns same endpoint\n   - ListAdapters() includes the adapter\n   - StopAdapter('dummy', 'alice') returns True and removes from pool\n2. grep -r \"async def start_adapter\" daemon/daemon.py\n3. grep -r \"async def verify_2fa\" daemon/daemon.py\n4. grep -r \"session_tokens\" daemon/daemon.py\n</verification>

<must_haves>
- start_adapter with pooling and stdin credentials\n- verify_2fa token issuance\n- ListAdapters and StopAdapter\n- Adapter spawning uses stdin (not env)\n- Socket path: /run/mtm/adapters/{username}_{adapter_type}.sock\n- Token validation before spawn\n</must_haves>
