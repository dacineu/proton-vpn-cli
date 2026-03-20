---
wave: 2
objective: Extend control protocol to handle Register from adapters, session token validation, and track tunnel allocations per adapter
depends_on:
  - 1
files_modified:
  - multi-tunnel-namespace/src/daemon/resource_allocator.py
  - multi-tunnel-namespace/src/daemon/daemon.py
autonomous: false
---

<tasks>
<task id="1">
<description>Add Register message handling to ResourceAllocator</description>
<read_first>
- multi-tunnel-namespace/src/daemon/resource_allocator.py (_dispatch, _handle_client)\n</read_first>
<action>
1. In ResourceAllocator class, add handler method:\n   ```python\n   async def _handle_register(self, request: Dict[str, Any], adapter: AdapterInstance) -> Dict[str, Any]:\n       session_id = request.get('session_id')\n       adapter_type = request.get('adapter_type')\n       username = request.get('username')\n       if not all([session_id, adapter_type, username]):\n           return {'msg_type': 'error', 'error': 'Missing register fields'}\n       # Store mapping: adapter.session_id = session_id\n       adapter.session_id = session_id  # need to add field to AdapterInstance\n       adapter.username = username\n       # Also init tunnel set\n       adapter.tunnels = set()\n       logger.info(f'Adapter registered: {adapter_type} user={username} session={session_id}')\n       return {'msg_type': 'registered', 'control_socket': self.socket_path}\n   ```\n2. Before this, modify AdapterInstance dataclass in adapter_registry.py to add:\n   - session_id: Optional[str] = None\n   - username: Optional[str] = None\n   - tunnels: Set[str] = field(default_factory=set)\n3. In _dispatch(), add:\n   ```python\n   elif msg_type == 'register':\n       return await self._handle_register(request, adapter)\n   ```\n4. Ensure ResourceAllocator.set_adapter_registry() is called so allocator can access registry (it already is in daemon.py start())\n</action>\n<acceptance_criteria>\n- resource_allocator.py contains async def _handle_register(self, request, adapter)\n- _handle_register validates session_id, adapter_type, username presence\n- _handle_register sets adapter.session_id, adapter.username, adapter.tunnels = set()\n- _dispatch in resource_allocator.py handles 'register' msg_type\n- adapter_registry.py AdapterInstance has fields: session_id (str or None), username (str or None), tunnels (set)\n</acceptance_criteria>
</task>

<task id="2">
<description>Implement session token validation on control messages (optional for Phase 1)</description>
<read_first>
- multi-tunnel-namespace/src/daemon/resource_allocator.py (_dispatch)\n- 1-CONTEXT.md (token model)\n</read_first>
<action>
1. Phase 1 token validation is simplified: adapter includes 'session_token' in control messages; MTM checks it matches adapter's stored token (if token auth is enabled). But Phase 1 may use dummy tokens. For completeness, add:\n   - In AdapterInstance, add expected_session_token: Optional[str] = None\n   - In _handle_register, read request.get('session_token'). If present, set adapter.expected_session_token = session_token\n   - In _dispatch, before handling allocate/release, check if adapter.expected_session_token is set and request contains 'session_token', and compare. If mismatch, return error {'msg_type': 'error', 'error': 'INVALID_SESSION', 'code': 'INVALID_SESSION'}.\n2. Modify daemon.start_adapter to include session_token in the stdin payload (already added in Plan 1 task 3). Adapter will forward it in AllocateTunnel/ReleaseTunnel.\n3. Alternatively, skip full token validation for Phase 1 and just log a warning if missing. But tests expect token validation. Implement simple equality check.\n</action>\n<acceptance_criteria>\n- AdapterInstance has expected_session_token field\n- _handle_register extracts session_token from request and stores it\n- _dispatch checks session_token on allocate/release requests if expected_session_token is set\n- Returns error if token missing or mismatched\n</acceptance_criteria>
</task>

<task id="3">
<description>Modify AllocateTunnel handler to track tunnels per adapter</description>
<read_first>
- multi-tunnel-namespace/src/daemon/resource_allocator.py (_handle_allocate)\n</read_first>
<action>
1. In ResourceAllocator._handle_allocate, after successful allocation:\n   ```python\n   adapter.tunnels.add(tunnel_name)\n   ```\n2. Ensure adapter has .tunnels set (from Register)\n3. Return response includes namespace\n</action>\n<acceptance_criteria>\n- _handle_allocate contains adapter.tunnels.add(tunnel_name)\n- allocate response returns 'namespace' field\n- release handler removes from adapter.tunnels (verify in next task)\n</acceptance_criteria>
</task>

<task id="4">
<description>Modify ReleaseTunnel handler to remove from adapter.tunnels</description>
<read_first>
- multi-tunnel-namespace/src/daemon/resource_allocator.py (_handle_release)\n</read_first>
<action>
1. In _handle_release, after successful release: `adapter.tunnels.discard(tunnel_name)`\n2. Ensure adapter.tunnels exists (safe if Register always called)\n</action>\n<acceptance_criteria>\n- _handle_release contains adapter.tunnels.discard(tunnel_name)\n- uses discard to avoid KeyError\n</acceptance_criteria>
</task>

<task id="5">
<description>Add adapter crash cleanup: iterate adapter.tunnels and release</description>
<read_first>
- multi-tunnel-namespace/src/daemon/adapter_registry.py (_wait_for_process, _unregister_by_pid)\n</read_first>
<action>
1. In AdapterRegistry._unregister_by_pid, after finding instance but before removing, need to trigger resource cleanup. But ResourceAllocator is separate. Options:\n   - Store reference to resource_allocator in AdapterRegistry (self._resource_allocator)\n   - Call self._resource_allocator.release_adapter_tunnels(adapter)\n2. Extend ResourceAllocator with:\n   ```python\n   async def release_adapter_tunnels(self, adapter: AdapterInstance):\n       for tunnel_name in list(adapter.tunnels):\n           try:\n               await self.routing.destroy_tunnel_context(tunnel_name, {})\n               logger.info(f'Released tunnel {tunnel_name} from crashed adapter {adapter.adapter_type}/{adapter.session_name}')\n           except Exception as e:\n               logger.error(f'Failed to release tunnel {tunnel_name}: {e}')\n   ```\n3. In AdapterRegistry, after instantiating self._resource_allocator = None in __init__, add method set_resource_allocator(allocator). Call this from daemon.start(): self.resource_allocator.set_adapter_registry(self.adapter_registry) and self.adapter_registry.set_resource_allocator(self.resource_allocator) (bidirectional).\n4. In AdapterRegistry._unregister_by_pid, before removing adapter from dicts:\n   ```python\n   if self._resource_allocator and instance.session_id:\n       asyncio.create_task(self._resource_allocator.release_adapter_tunnels(instance))\n   ```\n   Use create_task to avoid blocking unregister.\n</action>\n<acceptance_criteria>\n- adapter_registry.py has set_resource_allocator method\n- daemon.py calls adapter_registry.set_resource_allocator(self.resource_allocator) during start\n- resource_allocator.py defines async def release_adapter_tunnels(self, adapter)\n- release_adapter_tunnels iterates adapter.tunnels and calls routing.destroy_tunnel_context\n- _unregister_by_pid creates task to call release_adapter_tunnels\n</acceptance_criteria>
</task>
</tasks>

<verification>
After Plan 1 and Plan 2 complete:
1. Start daemon and spawn dummy adapter (via StartAdapter)\n2. Verify adapter can register (control socket connection) and adapter registry shows it\n3. Adapter sends AllocateTunnel → namespace created and adapter.tunnels updated\n4. Kill adapter process (SIGTERM) → verify logs show tunnel cleanup, namespace deleted\n5. grep for 'msg_type': 'register' in resource_allocator.py\n6. grep for 'adapter.tunnels' in resource_allocator.py and adapter_registry.py\n</verification>

<must_haves>
- Control protocol extends with Register message\n- AdapterRegistry tracks session_id, username, tunnels per adapter\n- ResourceAllocator assigns tunnel ownership and tracks allocations\n- Crash cleanup releases all tunnels belonging to crashed adapter\n- SO_PEERCRED authentication already exists (reused from existing code)\n</must_haves>
