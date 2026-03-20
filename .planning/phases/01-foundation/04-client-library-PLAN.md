---
wave: 2
objective: Extend ManagerClient with start_adapter() and create AdapterClient for direct tunnel operations; ensure session token propagation
depends_on:
  - 1
  - 3
files_modified:
  - multi-tunnel-namespace/src/libvpnmanager/client.py
autonomous: false
---

<tasks>
<task id="1">
<description>Add verify_2fa() method to ManagerClient</description>
<read_first>
- multi-tunnel-namespace/src/libvpnmanager/client.py (ManagerClient class)\n</read_first>
<action>
1. In ManagerClient class, add:\n   ```python\n   async def verify_2fa(self, totp_code: str) -> Dict[str, Any]:\n       return await self._call('Verify2FA', {'totp_code': totp_code})\n   ```\n2. Ensure _call method exists (it does)\n</action>\n<acceptance_criteria>\n- client.py contains async def verify_2fa(self, totp_code)\n- method calls self._call('Verify2FA', {'totp_code': totp_code})\n</acceptance_criteria>
</task>

<task id="2">
<description>Add start_adapter() method to ManagerClient</description>
<read_first>
- multi-tunnel-namespace/src/libvpnmanager/client.py\n- 1-CONTEXT.md (socket paths)\n</read_first>
<action>
1. In ManagerClient class, add:\n   ```python\n   async def start_adapter(self, adapter_type: str, credentials: Dict[str, Any], session_token: Optional[str] = None, totp_code: Optional[str] = None) -> str:\n       \"\"\"\n       Ensure adapter is running and return its CLI endpoint.\n       If totp_code provided, first call verify_2fa to get session_token.\n       \"\"\"\n       if totp_code:\n           result = await self.verify_2fa(totp_code)\n           session_token = result['session_token']\n       params = {\n           'adapter_type': adapter_type,\n           'credentials': credentials,\n       }\n       if session_token:\n           params['session_token'] = session_token\n       result = await self._call('StartAdapter', params)\n       return result['endpoint']\n   ```\n2. Document that endpoint is like 'unix:///run/mtm/adapters/alice_dummy.sock'\n</action>\n<acceptance_criteria>\n- client.py contains async def start_adapter(self, adapter_type, credentials, session_token=None, totp_code=None)\n- If totp_code provided, calls verify_2fa and uses returned session_token\n- Calls self._call('StartAdapter', params) with adapter_type, credentials, and optional session_token\n- Returns result['endpoint']\n</acceptance_criteria>
</task>

<task id="3">
<description>Create AdapterClient class for direct adapter communication</description>
<read_first>
- 1-CONTEXT.md (AdapterClient connection pattern, NDJSON protocol)\n- multi-tunnel-namespace/src/daemon/resource_allocator.py (length-prefixed example for contrast)\n</read_first>
<action>
1. In client.py, add new class `AdapterClient`:\n   ```python\n   class AdapterClient:\n       def __init__(self, endpoint: str, session_token: Optional[str] = None):\n           self.endpoint = endpoint\n           self.session_token = session_token\n           self._reader: Optional[asyncio.StreamReader] = None\n           self._writer: Optional[asyncio.StreamWriter] = None\n\n       async def connect(self):\n           path = self.endpoint.replace('unix://', '')\n           self._reader, self._writer = await asyncio.open_unix_connection(path)\n\n       async def disconnect(self):\n           if self._writer:\n               self._writer.close()\n               await self._writer.wait_closed()\n               self._writer = None\n\n       async def create_tunnel(self, tunnel_name: str, config: ConnectionConfig, totp_code: Optional[str] = None) -> Tunnel:\n           request = {\n               'action': 'CreateTunnel',\n               'tunnel_name': tunnel_name,\n               'config': config.to_dict(),\n           }\n           if self.session_token:\n               request['session_token'] = self.session_token\n           if totp_code:\n               request['totp_code'] = totp_code\n           self._writer.write(json.dumps(request).encode() + b'\\n')\n           await self._writer.drain()\n           response_line = await self._reader.readline()\n           response = json.loads(response_line.decode())\n           if response.get('status') == 'error':\n               raise TunnelError(response.get('error', 'Unknown error'))\n           return Tunnel.from_dict(response['tunnel'])\n\n       async def destroy_tunnel(self, tunnel_name: str) -> bool:\n           request = {'action': 'DestroyTunnel', 'tunnel_name': tunnel_name}\n           if self.session_token:\n               request['session_token'] = self.session_token\n           self._writer.write(json.dumps(request).encode() + b'\\n')\n           await self._writer.drain()\n           response_line = await self._reader.readline()\n           response = json.loads(response_line.decode())\n           return response.get('status') == 'success'\n\n       async def list_tunnels(self) -> List[Tunnel]:\n           request = {'action': 'ListTunnels'}\n           if self.session_token:\n               request['session_token'] = self.session_token\n           self._writer.write(json.dumps(request).encode() + b'\\n')\n           await self._writer.drain()\n           response_line = await self._reader.readline()\n           response = json.loads(response_line.decode())\n           tunnels = [Tunnel.from_dict(t) for t in response.get('tunnels', [])]\n           return tunnels\n\n       async def get_status(self, tunnel_name: str) -> TunnelStatus:\n           request = {'action': 'GetStatus', 'tunnel_name': tunnel_name}\n           if self.session_token:\n               request['session_token'] = self.session_token\n           self._writer.write(json.dumps(request).encode() + b'\\n')\n           await self._writer.drain()\n           response_line = await self._reader.readline()\n           response = json.loads(response_line.decode())\n           status_val = response.get('status', 'unknown')\n           return TunnelStatus(status_val)\n\n       async def __aenter__(self):\n           await self.connect()\n           return self\n\n       async def __aexit__(self, exc_type, exc_val, exc_tb):\n           await self.disconnect()\n   ```\n2. Import necessary types: from .models.tunnel import Tunnel; from .models.status import TunnelStatus; from .models.exceptions import TunnelError\n3. Ensure ConnectionConfig imported for type hint in create_tunnel\n</action>\n<acceptance_criteria>\n- client.py contains class AdapterClient with __init__(endpoint, session_token=None)\n- AdapterClient has connect(), disconnect(), async context manager methods\n- create_tunnel, destroy_tunnel, list_tunnels, get_status methods implemented\n- Each method sends NDJSON line (json.dumps + '\\n') and reads response line\n- session_token included in request if present\n- Raises TunnelError on error responses\n- Uses Tunnel.from_dict to construct Tunnel objects\n</acceptance_criteria>
</task>

<task id="4">
<description>Update ManagerClient to expose adapter-related methods (list_adapters, get_adapter_capabilities already exist? add stop_adapter)</description>
<read_first>
- multi-tunnel-namespace/src/libvpnmanager/client.py (existing methods)\n</read_first>
<action>
1. Check if list_adapters and get_adapter_capabilities already exist — from earlier inspection, they do exist (lines 141-147). Good.\n2. Add stop_adapter method if missing:\n   ```python\n   async def stop_adapter(self, adapter_type: str, username: str) -> bool:\n       return await self._call('StopAdapter', {'adapter_type': adapter_type, 'username': username})\n   ```\n3. Ensure these methods are documented and follow same pattern\n</action>\n<acceptance_criteria>\n- client.py has async def stop_adapter(self, adapter_type, username)\n- stop_adapter calls self._call('StopAdapter', ...)\n- list_adapters and get_adapter_capabilities exist (already present)\n</acceptance_criteria>
</task>

<task id="5">
<description>Add integration: ManagerClient.start_adapter returns endpoint suitable for AdapterClient</description>
<read_first>
- client.py (start_adapter implementation from task 2)\n</read_first>
<action>
1. Ensure start_adapter returns string endpoint without wrapper dict (client passes through). Already returns result['endpoint'].\n2. Document usage pattern:\n   ```python\n   async with ManagerClient() as mgr:\n       endpoint = await mgr.start_adapter('dummy', {'username': 'alice', 'password': 'pw'}, totp_code='123456')\n       async with AdapterClient(endpoint, session_token=token) as adapter:\n           tunnel = await adapter.create_tunnel('personal', config)\n   ```\n</action>
<acceptance_criteria>
- start_adapter returns endpoint string (unix://...)\n- README or docstring example shows usage with AdapterClient\n</acceptance_criteria>
</task>
</tasks>

<verification>
After this plan:\n1. Unit tests: mock daemon D-Bus, verify start_adapter constructs correct call\n2. Unit tests: AdapterClient create_tunnel sends correct JSON with action and session_token\n3. grep -r "class AdapterClient" client.py\n4. grep -r "async def start_adapter" client.py\n5. Integration test from Plan 5 will use these methods end-to-end\n</verification>

<must_haves>
- ManagerClient.verify_2fa() method\n- ManagerClient.start_adapter() method that can accept totp_code to get token and returns endpoint\n- AdapterClient class with NDJSON protocol, session_token handling, and Tunnel models\n- AdapterClient connection lifecycle (connect/disconnect/context manager)\n- Integration pattern: start_adapter → AdapterClient → tunnel operations\n</must_haves>
