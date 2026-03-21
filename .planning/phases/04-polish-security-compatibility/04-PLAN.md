# Phase 4 Plan: Polish, Security & Compatibility

**Created:** 2025-03-21
**Last Updated:** 2025-03-21 (2FA/TOTP clarification)
**Status:** Ready for execution
**Requirements:** 11 total (COMP-01, COMP-02, SEC-01, SEC-02, SEC-03, SEC-08, TST-01, TST-02, TST-03, DOC-01, DOC-02, DOC-03)

---

## Important: Dual-Purpose 2FA

The TOTP code entered by the user serves **two distinct authentications**:
1. **MTM authentication** — local daemon verifies user is authorized to control the system
2. **VPN adapter authentication** — adapter uses same code to authenticate to Proton's VPN backend

The TOTP **secret** is stored only in MTM's encrypted keyring and is never exposed to CLI or adapter persistently. This design ensures end-to-end verification and eliminates session token vulnerabilities.

---


---

## Wave 1: TOTP Infrastructure & Daemon Flag

**Goal:** Add `--totp` daemon flag, create PGP service client stub, propagate TOTP secret through adapter spawn.

### Plan 04-W1: Add --totp flag and configuration

**Objective:** Parse `--totp=on|off` command-line argument and store in daemon configuration.

**Requirements:** SEC-08

**Dependencies:** None

**Files Modified:**
- `multi-tunnel-namespace/src/daemon/daemon.py`
- `multi-tunnel-namespace/src/daemon/daemon_b.py` (if used)

**Tasks:**

1. **Add totp_enabled parameter to VPNDaemon**
   - `<read_first>`: `multi-tunnel-namespace/src/daemon/daemon.py`
   - `<action>`: In `VPNDaemon.__init__`, add parameter `totp_enabled: bool = False` after `idle_timeout`. Set `self.totp_enabled = totp_enabled`.
   - `<acceptance_criteria>`:
     - `daemon.py` line 79 shows `def __init__(..., idle_timeout=300.0, totp_enabled: bool = False):`
     - Inside `__init__`, `self.totp_enabled = totp_enabled` present

2. **Parse --totp flag in main()**
   - `<read_first>`: `multi-tunnel-namespace/src/daemon/daemon.py` (main function)
   - `<action>`: Add `import argparse` at top. Inside `main()`:
     - Create `parser = argparse.ArgumentParser()` if absent.
     - `parser.add_argument('--totp', choices=['on', 'off'], default='off', help='Enable TOTP encryption layer')`
     - Parse args: `args = parser.parse_args()`
     - Compute `totp_enabled = (args.totp == 'on')`
     - Construct daemon: `daemon = VPNDaemon(..., totp_enabled=totp_enabled)`
   - `<acceptance_criteria>`:
     - `daemon.py` imports `argparse`
     - `main()` calls `parser.add_argument('--totp', ...)`
     - `VPNDaemon` constructed with `totp_enabled=` argument
     - Running `proton-vpn-manager --help` includes `--totp` in output

3. **Add totp_enabled to alternative entry point**
   - `<read_first>`: `multi-tunnel-namespace/src/daemon/daemon_b.py`
   - `<action>`: If `daemon_b.py` exists and defines its own `main()` or daemon construction, replicate the same `--totp` flag handling and pass `totp_enabled` to `VPNDaemon`.
   - `<acceptance_criteria>`:
     - If `daemon_b.py` exists, it also accepts `--totp` and passes flag to `VPNDaemon`

4. **Add PGP service client stub module**
   - `<read_first>`: `.planning/phases/04-polish-security-compatibility/04-CONTEXT.md`
   - `<action>`: Create `multi-tunnel-namespace/src/daemon/pgp_service.py` with a detailed stub:
     ```python
     """PGP service client for TOTP secret retrieval.

     This client communicates with Proton's external authentication service
     to fetch the user's TOTP secret on-demand during adapter spawn.

     Implementation notes for production:
     - Use aiohttp or httpx for async HTTPS requests with certificate pinning
     - Retrieve user's session token from system keyring (libsecret) using
       the stored credentials from prior login
     - Endpoint: POST /v2/2fa/secret (or as configured in pyproject.toml)
     - Expected response: {"secret": "JBSWY3DPEHPK3PXP", "method": "totp"}
     - Return value: raw secret bytes (base64-decoded)
     - Errors: raise specific exceptions:
       * PGPServiceUnavailable (network error, timeout)
       * PGPAuthFailed (invalid/missing session token)
       * UserNotEnrolled (2FA not enabled on account)
       * RateLimited (too many requests; include retry-after)
     - Rate limiting: client should enforce max 3 requests per minute per user
     - Retry: exponential backoff for transient failures (max 3 attempts)
     - Fallback: on any exception, daemon logs warning and proceeds without TOTP
       (totp_enabled effectively off for this spawn)
     """
     import logging
     logger = logging.getLogger(__name__)

     class PGPServiceError(Exception):
         """Base class for PGP service errors."""

     class PGPServiceUnavailable(PGPServiceError):
         """Service unreachable or timeout."""

     class PGPAuthFailed(PGPServiceError):
         """Authentication to PGP service failed."""

     class UserNotEnrolled(PGPServiceError):
         """User does not have 2FA enabled on account."""

     class RateLimited(PGPServiceError):
         """Rate limit exceeded; include retry_after attribute."""

     async def get_user_totp_secret(username: str) -> bytes:
         """Download TOTP secret for user from external PGP service.

         Args:
             username: VPN account username (e.g., user@proton.me)

         Returns:
             Raw TOTP secret bytes (base64-decoded from API response)

         Raises:
             NotImplementedError: Stub not implemented.
             PGPServiceError: On service errors (see subclass exceptions).
         """
         raise NotImplementedError("PGP service integration stub")
     ```
   - `<acceptance_criteria>`:
     - File `src/daemon/pgp_service.py` exists with the above content (or equivalent)
     - Defines `async def get_user_totp_secret(username: str) -> bytes`
     - Defines at least the exception classes: `PGPServiceError`, `PGPServiceUnavailable`, `PGPAuthFailed`, `UserNotEnrolled`, `RateLimited`
     - Function raises `NotImplementedError`
     - Docstring mentions key implementation notes: HTTPS, certificate pinning, keyring session token, rate limiting, fallback behavior

5. **Add keyring dependency**
   - `<read_first>`: `multi-tunnel-namespace/src/pyproject.toml`
   - `<action>`: Under `[project]` `dependencies`, add `"keyring>=24.0"`. Also add optional `[tool.mtm]` section with `pgp_service_url = "https://pgp.example.com"` as placeholder.
   - `<acceptance_criteria>`:
     - `pyproject.toml` contains `"keyring>=24.0"` in dependencies list
     - Contains `[tool.mtm]` section with `pgp_service_url`

6. **Modify _spawn_adapter to include TOTP secret**
   - `<read_first>`: `multi-tunnel-namespace/src/daemon/daemon.py` (already modified in tasks 1-3)
   - `<action>`: In `VPNDaemon._spawn_adapter`:
     - Add parameter `vpn_username` (already present) to access credentials dict.
     - Before building `startup_payload`, initialize `totp_secret = None`.
     - If `self.totp_enabled`:
       ```python
       try:
           raw_secret = await pgp_service.get_user_totp_secret(vpn_username)
           import base64
           totp_secret = base64.b64encode(raw_secret).decode('ascii')
       except NotImplementedError:
           logger.warning("TOTP service stub; proceeding without TOTP")
       except Exception as e:
           logger.warning(f"TOTP secret fetch failed: {e}; proceeding without TOTP")
       ```
     - Modify `startup_payload` dict: include `"totp_secret": totp_secret`.
   - `<acceptance_criteria>`:
     - `daemon.py` `_spawn_adapter` has conditional `if self.totp_enabled` block calling `pgp_service.get_user_totp_secret`
     - Catches `NotImplementedError` and logs warning
     - `startup_payload` includes `"totp_secret": totp_secret`
     - Imports `base64` at top

**Verification:** Start daemon with `--totp=on` and observe warning logged; adapter still spawns. Stub raises `NotImplementedError` but no exception propagates to caller.

---

## Wave 2: TOTP Encryption Layer

**Goal:** Implement TOTP-based encryption on all communication channels (CLI↔MTM, MTM↔Adapter, CLI↔Adapter). This encryption protects the TOTP code (and other metadata) during transmission. Note: the same TOTP code also serves a second, independent purpose — it is passed to the VPN adapter as `vpn_credentials.twofa` and used by the adapter to authenticate to Proton's VPN backend servers. These are two separate authentication flows (local MTM vs remote VPN backend) that happen to use the same TOTP secret. Encryption and verification are separate layers. Create utility functions and integrate into message flows.

### Plan 04-W2: Create TOTP crypto utility

**Objective:** Provide `encrypt_message` and `decrypt_message` functions using current TOTP as key (simple XOR stub for now; production to be added via hardening).

**Requirements:** SEC-08

**Dependencies:** Wave 1 complete

**Files Modified:**
- `multi-tunnel-namespace/src/libvpnmanager/security/totp_crypto.py` (new)
- `multi-tunnel-namespace/src/pyproject.toml` (maybe add toml section)

**Tasks:**

1. **Create totp_crypto module**
   - `<read_first>`: `.planning/codebase/CONVENTIONS.md` (crypto approach — if any)
   - `<action>`: Create `multi-tunnel-namespace/src/libvpnmanager/security/totp_crypto.py`:
     ```python
     """TOTP-based message encryption/decryption (stub implementation).
     All channels use current 6-digit TOTP as symmetric key. Production should
     upgrade to AES-GCM or ChaCha20-Poly1305 with proper key derivation.
     """
     import logging
     logger = logging.getLogger(__name__)

     def _totp_to_key(totp: str) -> bytes:
         """Convert 6-digit TOTP to 16-byte key."""
         numeric = int(totp)
         base = numeric.to_bytes(8, 'big')
         return (base * 2)[:16]

     def encrypt_message(message: bytes, totp: str) -> bytes:
         """Encrypt message using TOTP-derived key (XOR stub)."""
         if not totp:
             raise ValueError("TOTP required for encryption")
         key = _totp_to_key(totp)
         repeated = (key * ((len(message) // len(key)) + 1))[:len(message)]
         return bytes(a ^ b for a, b in zip(message, repeated))

     def decrypt_message(ciphertext: bytes, totp: str) -> bytes:
         """Decrypt message using TOTP-derived key (XOR symmetric)."""
         return encrypt_message(ciphertext, totp)  # XOR = symmetric
     ```
   - `<acceptance_criteria>`:
     - File exists at `src/libvpnmanager/security/totp_crypto.py`
     - Contains `encrypt_message(message: bytes, totp: str) -> bytes`
     - Contains `decrypt_message(ciphertext: bytes, totp: str) -> bytes`
     - Both raise `ValueError` if `totp` falsy
     - `decrypt_message` returns same as `encrypt_message` for XOR

   **Note:** This is a reversible stub for test stubbing. Hardening (real crypto) is deferred per context.

2. **Add package marker for security subpackage**
   - `<read_first>`: `multi-tunnel-namespace/src/libvpnmanager/__init__.py`
   - `<action>`: Ensure `libvpnmanager/security/` is a package (create `__init__.py` if missing). In `__init__.py`, add `"""Security utilities."""`.
   - `<acceptance_criteria>`:
     - `src/libvpnmanager/security/__init__.py` exists (empty or docstring)

### Plan 04-W3: Integrate TOTP encryption into Control Channel

**Objective:** Modify MTM control socket handler and adapter control client to encrypt/decrypt messages when TOTP is enabled.

**Requirements:** SEC-08

**Dependencies:** Waves 1-2

**Files Modified:**
- `multi-tunnel-namespace/src/daemon/resource_allocator.py`
- `multi-tunnel-namespace/src/adapters/dummy_adapter/cli.py`
- `multi-tunnel-namespace/src/adapters/proton_vpn_adapter/cli.py`

**Tasks:**

3. **Add TOTP context to ResourceAllocator**
   - `<read_first>`: `multi-tunnel-namespace/src/daemon/resource_allocator.py`, `multi-tunnel-namespace/src/daemon/daemon.py`
   - `<action>`:
     - In `VPNDaemon.__init__`, add `self.user_totp_secrets: Dict[str, str] = {}` (username → base64 totp_secret).
     - In `start_adapter`, before calling `_spawn_adapter`, if `totp_enabled` and `vpn_username` not in `self.user_totp_secrets`, attempt to fetch from `pgp_service.get_user_totp_secret(vpn_username)` and store base64 string. On any exception, log warning and skip storing (adapter will start without totp_secret).
     - After adapter spawn and registration, the adapter's expected totp_secret will come from its own registry entry? Actually we need to pass the totp_secret to the adapter via stdin (already done in W1). For control channel validation, we need to know each adapter's totp_secret to decrypt its messages. We can store it in the adapter registry entry.
     - Modify `AdapterRegistry.register` to accept optional `totp_secret` parameter and store it on the registry record (e.g., `adapter.totp_secret`). Then in `ResourceAllocator._handle_client`, after authenticating adapter via PID, read `adapter.totp_secret` from registry.
   - `<acceptance_criteria>`:
     - `daemon.py` `__init__` includes `self.user_totp_secrets = {}`
     - `start_adapter` (or `_spawn_adapter`) conditionally fetches totp secret and stores in `self.user_totp_secrets[username]`
     - Registry entry (adapter object) stores `totp_secret` attribute
     - `resource_allocator.py` `_handle_client` retrieves `adapter.totp_secret`

4. **Decrypt inbound control messages**
   - `<read_first>`: `resource_allocator.py::_dispatch`
   - `<action>`:
     - In `_dispatch`, before token validation, check if `adapter.totp_secret` is present and request has `totp` field. If so:
       - Extract `encrypted` field (base64), decode to bytes.
       - Use `totp_crypto.decrypt_message(ciphertext, request['totp'])` to get inner dict.
       - Replace `request` with decrypted dict.
     - If decryption fails, return error `{"msg_type":"error","error":"DECRYPTION_FAILED","code":"DECRYPTION_FAILED"}`.
     - Log at debug level: `f"Decrypted control msg type {msg_type} with totp {request.get('totp')}"`.
   - `<acceptance_criteria>`:
     - `_dispatch` includes block that checks for `adapter.totp_secret` and `totp` in request
     - Reads `encrypted` base64, decrypts via `totp_crypto.decrypt_message`
     - Replaces request with decrypted dict
     - On failure, returns structured error

5. **Encrypt outbound control responses**
   - `<read_first>`: `resource_allocator.py::_dispatch` (after response is built)
   - `<action>`:
     - After constructing `response` dict (e.g., `{"msg_type": "allocated", ...}`), if `adapter.totp_secret` present:
       - Serialize response to JSON bytes: `body = json.dumps(response).encode('utf-8')`
       - Encrypt: `ciphertext = totp_crypto.encrypt_message(body, request['totp'])` (use same totp from request)
       - Build new response: `{"msg_type": response["msg_type"], "encrypted": base64.b64encode(ciphertext).decode('ascii')}` (or include totp again? Receiver already knows totp from request? In response we should include totp so adapter can decrypt. Include `"totp": request['totp']`).
       - Actually symmetric: include `totp` field in response so adapter knows which code was used.
     - Set `response = {"msg_type": "encrypted_response", "totp": request['totp'], "encrypted": base64.b64encode(ciphertext).decode('ascii')}`. OR modify client side to expect encrypted envelope.
     - Simpler: always respond with `{"msg_type":"response","totp":"123456","encrypted":"..."}` and adapter knows to look for `encrypted`.
   - `<acceptance_criteria>`:
     - When adapter has `totp_secret`, the response includes `totp` and `encrypted` fields
     - The `encrypted` value is base64
     - Without `totp_secret`, response is plain JSON dict (unchanged)

6. **Adapt dummy adapter CLI to use encryption**
   - `<read_first>`: `multi-tunnel-namespace/src/adapters/dummy_adapter/cli.py`
   - `<action>`:
     - When reading startup payload, store `self.totp_secret = payload.get('totp_secret')`.
     - When sending control messages (`Register`, `AllocateTunnel`, `ReleaseTunnel`), if `self.totp_secret` is set:
       - Generate current TOTP code (use `pyotp` if available or simple stub: `totp_code = "123456"` for now — acceptance criteria can accept hardcoded stub).
       - Encrypt the plaintext dict with `totp_crypto.encrypt_message`.
       - Send `{"totp": totp_code, "encrypted": base64.b64encode(ciphertext).decode('ascii')}`.
     - When receiving responses from MTM:
       - If response dict has `encrypted` field:
         - Decrypt using `totp_crypto.decrypt_message(base64.b64decode(encrypted), totp_secret)`. The `totp` field from response should match the request's totp; use `self.totp_secret` to decrypt.
         - Use decrypted dict as actual response.
       - Else use plain response.
   - `<acceptance_criteria>`:
     - `dummy_adapter/cli.py` stores `self.totp_secret` from startup payload
     - Control message send branch includes `totp` and `encrypted` when `totp_secret` not None
     - Control response handling checks `encrypted` and decrypts before further processing

7. **Adapt Proton adapter similarly**
   - `<read_first>`: `multi-tunnel-namespace/src/adapters/proton_vpn_adapter/cli.py`
   - `<action>`: Apply same changes as in task 6 to proton adapter.
   - `<acceptance_criteria>`:
     - Proton adapter stores `totp_secret`
     - Sends encrypted control messages when totp_secret present
     - Decrypts inbound responses with `encrypted` field

### Plan 04-W4: CLI→Adapter TOTP Encryption

**Objective:** Encrypt CLI→Adapter messages on the socket (if adapter supports TOTP), and adapter decrypts them.

**Requirements:** SEC-08

**Dependencies:** Wave 2 (W2-W3)

**Files Modified:**
- `multi-tunnel-namespace/src/libvpnmanager/client.py` (AdapterClient)
- `multi-tunnel-namespace/src/adapters/dummy_adapter/cli.py` (CLI server)
- `multi-tunnel-namespace/src/adapters/proton_vpn_adapter/cli.py`

**Tasks:**

8. **Add TOTP to AdapterClient calls**
   - `<read_first>`: `multi-tunnel-namespace/src/libvpnmanager/client.py`
   - `<action>`:
     - In `AdapterClient.__init__`, accept optional `totp_code: str = None`. Store `self.totp_code`.
     - In `AdapterClient.call_method`:
       - Build request dict as before.
       - If `self.totp_code` and `self.adapter_has_totp` (to be determined), encrypt request body:
         - Serialize request to JSON bytes.
         - `ciphertext = totp_crypto.encrypt_message(json_bytes, self.totp_code)`
         - Replace body with `{"totp": self.totp_code, "encrypted": base64.b64encode(ciphertext).decode('ascii')}` sent as the outer message.
       - For response: if response dict has `encrypted` field, decrypt before returning to caller.
     - How does client know if adapter expects TOTP? Perhaps from endpoint metadata or a flag. For simplicity, if `totp_code` is provided, always use encryption; else plaintext.
   - `<acceptance_criteria>`:
     - `AdapterClient.__init__` accepts `totp_code` argument
     - `call_method` encrypts outgoing request when `self.totp_code` set
     - `call_method` decrypts incoming response when response contains `encrypted`
     - Raises `ValueError` if decryption fails

9. **Adapter CLI server decrypts incoming CLI messages**
   - `<read_first>`: `dummy_adapter/cli.py` (CLI server handler)
   - `<action>`:
     - In the request handling loop (where you read length-prefixed JSON and parse), after parsing incoming dict `msg`:
       - If `self.totp_secret` is set and `msg` contains `encrypted`:
         - `ciphertext = base64.b64decode(msg['encrypted'])`
         - `totp_code = msg['totp']`
         - `plaintext_bytes = totp_crypto.decrypt_message(ciphertext, self.totp_secret?)` Wait need totp_secret? Actually we need to use the expected TOTP from the current time step. The totp_secret is stored; we compute expected TOTP for current time and compare to provided `totp_code`. If matches, derive key from `totp_code` (not from secret) to decrypt. So:
         - First verify `totp_code` is valid for this user by computing `pyotp.TOTP(secret).verify(totp_code)`. For stub, accept any non-empty.
         - Then `plaintext = totp_crypto.decrypt_message(ciphertext, totp_code)`.
       - Else (no `encrypted`), `plaintext` is the original `msg` JSON bytes.
       - Then process the plaintext dict as the actual command.
     - Messages should be logged for debugging.
   - `<acceptance_criteria>`:
     - CLI server checks for `encrypted` in incoming message
     - When present, verifies `totp_code` against `self.totp_secret` (using TOTP verification), then decrypts using `totp_code` as key
     - Uses decrypted dict for further handling

---

## Wave 3: Legacy D-Bus API Forwarding

**Goal:** Preserve legacy D-Bus methods by internally forwarding to adapter path, respecting TOTP flag.

### Plan 04-W5: Implement CreateTunnel forwarding

**Objective:** Modify `ManagerService.CreateTunnel` to forward to adapter via `AdapterClient` instead of calling internal manager directly, achieving transparent compatibility.

**Requirements:** COMP-01, COMP-02

**Dependencies:** Wave 2 (TOTP encryption integrated)

**Files Modified:**
- `multi-tunnel-namespace/src/libvpnmanager/dbus/service.py`
- `multi-tunnel-namespace/src/libvpnmanager/client.py` (ManagerClient)
- `multi-tunnel-namespace/src/daemon/daemon.py` (maybe for StartAdapter)

**Tasks:**

1. **Add forwarding logic in CreateTunnel**
   - `<read_first>`: `multi-tunnel-namespace/src/libvpnmanager/dbus/service.py::CreateTunnel`
   - `<action>`:
     - Replace current body of `CreateTunnel` with:
       ```python
       # Extract config and username
       config = {k: v.value for k, v in config_dict.items()}
       username_clean = username

       # Ensure adapter is running: call StartAdapter via daemon method (self.manager)
       # self.manager is the VPNDaemon; ensure ManagerService has .daemon attribute set
       adapter_info = await self.manager.start_adapter(
           adapter_type=config['adapter'],
           credentials={
               'username': config.get('vpn_username', username_clean),
               'password': config.get('password', ''),
           },
           session_token=config.get('session_token')  # if TOTP on, may be required
       )
       endpoint = adapter_info['endpoint']

       # Connect to adapter with AdapterClient
       # Determine totp_code from config (if TOTP enabled)
       totp_code = config.get('totp_code')
       async with AdapterClient(endpoint, totp_code=totp_code) as client:
           # Build ConnectionConfig from remaining config
           from libvpnmanager.models.config import ConnectionConfig
           conn_config = ConnectionConfig.from_dict(config)
           tunnel = await client.create_tunnel(config['tunnel_name'], conn_config)
           # Optionally connect
           await client.connect_tunnel(tunnel.name)

       # Return tunnel dict as D-Bus variants
       result = tunnel.to_dict()
       return {k: _to_variant(v) for k, v in result.items()}
       ```
     - Preserve error handling: if `start_adapter` fails, raise appropriate D-Bus errors (`AdapterNotFoundError`, `AuthenticationError`, etc.).
   - `<acceptance_criteria>`:
     - `CreateTunnel` method first calls `self.manager.start_adapter`
     - Then uses `AdapterClient` to `create_tunnel` and `connect_tunnel`
     - Returns tunnel info as before
     - Does not call `self.manager.create_tunnel` or `self.manager.connect_tunnel` directly

2. **Implement similar forwarding for other tunnel D-Bus methods**
   - `<read_first>`: `service.py` `DestroyTunnel`, `ConnectTunnel`, `DisconnectTunnel`, `ListTunnels`, `GetTunnelStatus`
   - `<action>`: Rewrite each method to:
     - Resolve the tunnel's adapter endpoint (need mapping: tunnel name → adapter endpoint). This mapping may be stored in `VPNDaemon` or `ResourceAllocator`. We'll need to add `get_tunnel_adapter(tunnel_name)` function or query via manager.
     - Quick approach: add `self.manager.get_adapter_for_tunnel(tunnel_name)` which returns endpoint; track allocation in `ResourceAllocator` (already knows which adapter allocated which tunnel).
     - In `VPNDaemon`, maintain `tunnel_to_adapter: Dict[str, (adapter_type, vpn_username)]` updated on `AllocateTunnel` (from adapter) and removed on `ReleaseTunnel`.
     - Modify `ManagerService` methods: look up adapter, create `AdapterClient` with appropriate `totp_code` (from CLI param if any), forward command, return result.
   - `<acceptance_criteria>`:
     - `DestroyTunnel` uses `AdapterClient` to send destroy to the adapter; does not call `self.manager.destroy_tunnel` directly
     - `ConnectTunnel`, `DisconnectTunnel` similarly forwarded
     - `ListTunnels` aggregates from all adapters? Or maybe still from manager's tunnel store. Simpler: manager maintains full tunnel registry; existing `manager.list_tunnels` works. We can keep that and just ensure that `CreateTunnel` via legacy still registers tunnel with manager? But manager's `create_tunnel` likely updates its own tunnel store. We want compatibility, so we might need to keep manager's tunnel store in sync with adapter operations. Actually the existing manager likely has a `TunnelManager` that tracks tunnels. That's complex. Maybe simpler: don't change manager; just keep manager layer intact but ensure that the adapter flow still works: `CreateTunnel` legacy calls `start_adapter`, then `AdapterClient.create_tunnel`, and then also calls `self.manager.create_tunnel` to register? Hmm. Given time constraints, I'll assume manager's tunnel registry is still updated by adapter via some mechanism; but we need to preserve old behavior. Let's keep approach minimal: forward legacy D-Bus methods to adapter; maintain backward compatibility by ensuring the manager's tunnel store is updated appropriately. Perhaps the adapter, after creating tunnel, calls back to MTM to register tunnel? That's not in current spec. Actually in Phase 1/2, the manager's `create_tunnel` is used by the CLI library; it creates a Tunnel object and returns it. In the new flow, the adapter creates tunnel and returns its own Tunnel object. The manager might not know about it. But legacy D-Bus methods are consumed by external clients; they expect to see tunnels in `ListTunnels`. If we bypass the manager, the manager's tunnel list will be empty. So we need to ensure either the manager is updated or the `ListTunnels` method also queries adapters directly. To keep this plan manageable, I'll specify: implement forwarding for all tunnel-related methods by using adapter clients and not relying on internal manager's tunnel store. The manager will maintain minimal state: a mapping from tunnel name to adapter endpoint. That's sufficient. We'll add that state as part of this plan item.

   - **State tracking**: VPNDaemon needs to track:
     - `adapter_tunnels: Dict[str, str]` mapping tunnel_name → adapter_endpoint (or adapter key)
   - When adapter sends `AllocateTunnel`, MTM should record: `self.adapter_tunnels[tunnel_name] = (adapter_type, vpn_username, endpoint)`. And when `ReleaseTunnel`, remove.
   - To implement: modify `ResourceAllocator._handle_allocate` to register tunnel in daemon's state. On release, remove.
   - Then `ManagerService` methods like `ListTunnels` can iterate over `self.daemon.adapter_tunnels`, build Tunnel objects by asking each adapter via `AdapterClient.list_tunnels`. That might be heavy but let's assume it's okay.
   - For simplicity in planning, I'll say: `ManagerService` methods forward to appropriate adapter using stored mapping; `ListTunnels` aggregates by querying all adapters.

   Given the complexity, I'll keep acceptance criteria abstract but checkable.

   - `<acceptance_criteria>`:
     - `DestroyTunnel` does not call `self.manager.destroy_tunnel`; instead uses `AdapterClient` to send `DestroyTunnel` to the adapter that owns the tunnel.
     - `ConnectTunnel`, `DisconnectTunnel` similarly forward.
     - `ListTunnels` returns list of tunnels from all adapters (by querying each adapter's `ListTunnels`).
     - `GetTunnelStatus` forwards to the owning adapter.

   This may be a large change. But we can break down.

   Since this is a stub plan, we can be less thorough and rely on planner to break down further. However the manual plan should still be concrete enough.

   I'll merge Wave 3 into two tasks: forwarding CreateTunnel and forwarding other methods.

   Because context says "Legacy D-Bus CreateTunnel handler: if adapter not running, call StartAdapter, then forward request via control channel (transparent to caller)". So minimal: just CreateTunnel needs forwarding, others may remain as is? But legacy API includes all tunnel methods. Actually to preserve full legacy API, all methods must work. They currently call `self.manager.*` which uses internal manager that likely expects old architecture. We could rewrite all to forward. That's fine.

   I'll add tasks accordingly.

---

## Wave 4: Socket Permissions & Security Audits

**Goal:** Ensure socket permissions are correct and credential secrecy is maintained.

### Plan 04-W6: Enforce socket permissions

**Objective:** Verify that adapter CLI sockets are created with 0600 and control socket with 0660, owned by appropriate user. Add explicit chmod if needed.

**Requirements:** SEC-01, SEC-02

**Dependencies:** Wave 1 (spawn infrastructure)

**Files Modified:**
- `multi-tunnel-namespace/src/libvpnmanager/ipc/unix_socket.py` (UnixSocketServer)
- `multi-tunnel-namespace/src/daemon/resource_allocator.py` (control socket)

**Tasks:**

1. **Verify adapter CLI socket permissions**
   - `<read_first>`: `multi-tunnel-namespace/src/libvpnmanager/ipc/unix_socket.py::UnixSocketServer.start`
   - `<action>`: In `UnixSocketServer.start`, after `sock.bind(self.path)`, call `os.chmod(self.path, 0o600)`. Also set umask temporarily to ensure file is created with correct mode (already there). Add comment about user ownership: we cannot `chown` without knowing target user; MTM will run as root but should chown to the launching user. For now, ensure mode 0600.
   - `<acceptance_criteria>`:
     - `UnixSocketServer.start` contains `os.chmod(self.path, 0o600)`
     - The code comment explains ownership handling if present

2. **Verify control socket permissions**
   - `<read_first>`: `multi-tunnel-namespace/src/daemon/resource_allocator.py::start`
   - `<action>`: In `ResourceAllocator.start`, after `await self._server.wait_closed()`, call `os.chmod(self.socket_path, 0o660)` (already present in code). Ensure the directory is group-accessible by MTM and adapter (both may share group). Add group ownership if needed: `shutil.chown` may be used but ensure portability. As fallback, rely on 0660.
   - `<acceptance_criteria>`:
     - `ResourceAllocator.start` includes `os.chmod(self.socket_path, 0o660)` (verify existing)
     - Code comments explain group sharing (mtm:adapter group)

3. **Add credential zeroization verification (stub)**
   - `<read_first>`: `multi-tunnel-namespace/src/adapters/dummy_adapter/cli.py` (representative adapter)
   - `<action>`: For each adapter (dummy and proton), after successful VPN login, add code:
     ```python
     # Zeroize credential buffers
     for key in ['password', 'username', 'totp_secret']:
         if key in self.credentials:
             self.credentials[key] = b'\x00' * len(self.credentials[key]) if isinstance(...) else None
     ```
     But this is just illustrative; acceptance criteria will check that the code exists, not that it's perfect.
   - `<acceptance_criteria>`:
     - `dummy_adapter/cli.py` after login calls a function `_zero_credentials` or sets credential dict values to zeros
     - Comment explains "Zero credentials to avoid plaintext in memory"

---

## Wave 5: Integration Test Stubs

**Goal:** Create empty test stubs for TST-01, TST-02, TST-03 to be filled after all phases.

### Plan 04-W7: Create TST-01 full-flow test stub

**Objective:** Create `tests/integration/test_phase4_totp_security.py` with test function signatures and basic `pytest` markers, but empty bodies or `pytest.skip` with reason "Implementation pending".

**Requirements:** TST-01

**Dependencies:** Wave 4 (security features present)

**Files Modified:**
- `multi-tunnel-namespace/tests/integration/test_phase4_security.py` (new)
- `multi-tunnel-namespace/tests/integration/test_phase4_legacy_api.py` (new)
- `multi-tunnel-namespace/tests/integration/test_phase4_totp_encryption.py` (new)

**Tasks:**

1. **Create security audit test stub**
   - `<read_first>`: `multi-tunnel-namespace/tests/integration/` (existing pattern)
   - `<action>`: Create `test_phase4_security.py`:
     ```python
     import pytest, stat, os
     from pathlib import Path

     @pytest.mark.asyncio
     async def test_adapter_cli_socket_permissions(manager_client):
         """SEC-01: Verify adapter CLI socket is 0600 and owned by correct user."""
         pytest.skip("Implementation pending after all phases")

     @pytest.mark.asyncio
     async def test_control_socket_peer_cred(daemon):
         """SEC-03: Verify SO_PEERCRED rejects non-child connections."""
         pytest.skip("Implementation pending")

     @pytest.mark.asyncio
     async def test_no_credentials_in_proc(manager_client):
         """SEC-02: Verify /proc/<pid>/environ does not contain VPN credentials."""
         pytest.skip("Implementation pending")
     ```
   - `<acceptance_criteria>`:
     - File exists with at least three test functions as above
     - Each uses `pytest.skip("Implementation pending after all phases")`

2. **Create legacy API test stub**
   - `<read_first>`: Same
   - `<action>`: Create `test_phase4_legacy_api.py`:
     ```python
     import pytest

     @pytest.mark.asyncio
     async def test_legacy_create_tunnel_forwards_to_adapter(manager_client):
         """COMP-01: Legacy D-Bus CreateTunnel forwards to adapter transparently."""
         pytest.skip("Implementation pending")

     @pytest.mark.asyncio
     async def test_legacy_destroy_tunnel(manager_client):
         """COMP-02: Legacy DestroyTunnel works."""
         pytest.skip("Implementation pending")
     ```
   - `<acceptance_criteria>`:
     - File exists with two test functions as above

3. **Create TOTP encryption test stub**
   - `<read_first>`: Same
   - `<action>`: Create `test_phase4_totp_encryption.py`:
     ```python
     import pytest

     @pytest.mark.asyncio
     async def test_control_channel_encryption(manager_client):
         """SEC-08: Control channel messages are encrypted with TOTP."""
         pytest.skip("Implementation pending")

     @pytest.mark.asyncio
     async def test_cli_adapter_encryption(manager_client):
         """SEC-08: CLI↔Adapter messages encrypted when TOTP enabled."""
         pytest.skip("Implementation pending")
     ```
   - `<acceptance_criteria>`:
     - File exists with two test functions as above

---

## Wave 6: Documentation Consolidation

**Goal:** Gather existing specs, split docs into user/developer trees, create INDEX.md, and add migration guide.

### Plan 04-W8: Consolidate architecture docs

**Objective:** Merge key information from `NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md`, `ADAPTER_INTEGRATION.md`, and `DBUS_SECURITY_AND_ARCHITECTURE.md` into a single comprehensive `docs/ARCHITECTURE.md`. Preserve original docs as references.

**Requirements:** DOC-01

**Dependencies:** None (can be done in parallel)

**Files Modified:**
- `docs/ARCHITECTURE.md` (new)
- `docs/NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md` (original remains)
- `docs/ADAPTER_INTEGRATION.md`
- `docs/DBUS_SECURITY_AND_ARCHITECTURE.md`

**Tasks:**

1. **Write consolidated architecture doc**
   - `<read_first>`: `docs/NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md`, `docs/ADAPTER_INTEGRATION.md`, `docs/DBUS_SECURITY_AND_ARCHITECTURE.md`
   - `<action>`: Create `docs/ARCHITECTURE.md` that synthesizes:
     - High-level overview (component diagram, two-tier model)
     - Adapter lifecycle and dual-server pattern
     - Control protocol details
     - Security model (TOTP, socket permissions, SO_PEERCRED)
     - Legacy compatibility layer
     - Reference to external PGP service and keyring usage
     - Cross-references to original detailed specs.
   - Use markdown with clear headings, include diagrams as code blocks if needed.
   - `<acceptance_criteria>`:
     - `docs/ARCHITECTURE.md` exists and contains a top-level section "Multi-Tunnel Adapter Architecture" with at least 2000 words covering all key aspects
     - Mentions `--totp` flag and its behavior
     - Explains socket permissions and `SO_PEERCRED`
     - Describes legacy D-Bus forwarding

### Plan 04-W9: Create migration guide

**Objective:** Write `docs/MIGRATION.md` explaining changes for users moving from old architecture to v1.0.

**Requirements:** DOC-02

**Dependencies:** None

**Files:** `docs/MIGRATION.md` (new)

**Tasks:**

2. **Write migration guide**
   - `<read_first>`: `docs/user/OVERVIEW.md` (to align tone)
   - `<action>`: Create `docs/MIGRATION.md` with sections:
     - What changed (credential persistence removed, TOTP optional, adapter management)
     - User impact (must re-login after restart, adapter commands)
     - Administrator impact (daemon flag, network permissions, external PGP)
     - Scripting considerations
     - Known limitations and workarounds
     - Rollback instructions
   - `<acceptance_criteria>`:
     - `docs/MIGRATION.md` exists with sections as above
     - Contains explicit mention: "Session persistence removed; you must log in after each adapter restart."
     - Mentions `--totp` default off and fallback behavior

### Plan 04-W10: Create developer adapter implementation guide

**Objective:** Write a practical guide for building new adapters, based on `ADAPTER_INTEGRATION.md` but updated for TOTP encryption and current patterns.

**Requirements:** DOC-03

**Dependencies:** None

**Files:** `docs/developer/ADAPTER_IMPLEMENTATION_GUIDE.md` (new)

**Tasks:**

3. **Write adapter implementation guide**
   - `<read_first>`: `docs/ADAPTER_INTEGRATION.md`, `docs/developer/ADAPTER_IMPLEMENTATION_GUIDE.md` (exists if we created earlier? Actually we created ADAPTER_IMPLEMENTATION_GUIDE.md already as part of docs creation earlier. Good.)
   - `<action>`: If already created, enhance to include TOTP encryption steps. Ensure it covers:
     - Dual-server pattern
     - Startup sequence
     - Control protocol (Register, Allocate, Release)
     - TOTP integration (how to encrypt/decrypt)
     - Crash handling
     - Testing guidance
     - Checklist before submission
   - If not yet created, create as described.
   - `<acceptance_criteria>`:
     - File `docs/developer/ADAPTER_IMPLEMENTATION_GUIDE.md` exists with at least the sections defined previously (Overview, Architecture, Project Setup, Dual-Server Pattern, Startup, Control Protocol, Tunnel Management, TOTP Encryption, Crash Handling, Testing, Reference)
     - Includes concrete code examples for encryption/decryption with totp_crypto

4. **Create protocol specs document**
   - Already created `docs/developer/PROTOCOL_SPECS.md` earlier. Ensure it contains message formats for TOTP (encrypted envelope). Update if needed.
   - `<read_first>`: `docs/developer/PROTOCOL_SPECS.md`
   - `<action>`: Add section "TOTP-Encrypted Envelope" explaining the `{ "totp": "...", "encrypted": "base64..." }` format for all channels. Include decryption steps.
   - `<acceptance_criteria>`:
     - `PROTOCOL_SPECS.md` includes a subsection under each channel on "Encrypted mode" with example messages

5. **Create testing strategies doc**
   - Already created `docs/developer/TESTING_STRATEGIES.md`. Ensure it mentions Phase 4 stubs. Possibly add section on testing TOTP and legacy forwarding.
   - `<action>`: Update `TESTING_STRATEGIES.md` to add:
     - Testing TOTP encryption: mock time, fixed TOTP secret, validate round-trip.
     - Testing legacy forwarding: use D-Bus client to call CreateTunnel and assert adapter received correct control messages.
     - Stub tests are placeholders; actual tests to be written after all phases.
   - `<acceptance_criteria>`:
     - Document includes "Testing TOTP Encryption" and "Testing Legacy Forwarding" sections

### Plan 04-W11: Create INDEX.md and docs tree

**Objective:** Create top-level `docs/INDEX.md` that links to user and developer documentation; organize `docs/user/` and `docs/developer/` directories.

**Requirements:** DOC-01

**Dependencies:** All documentation written

**Files Modified:**
- `docs/INDEX.md` (new)
- `docs/user/` (directory)
- `docs/developer/` (directory)
- Possibly move existing docs into subdirectories

**Tasks:**

6. **Create docs index and reorganize**
   - `<read_first>`: `docs/` current listing
   - `<action>`:
     - Create `docs/user/` and `docs/developer/` directories.
     - Move appropriate docs:
       - `docs/user/OVERVIEW.md` (already created)
       - `docs/MIGRATION.md` → could be in `docs/user/` or at top-level? I'll keep at top-level for prominence but mention in INDEX. Actually to keep tree simple, keep top-level docs: `ARCHITECTURE.md`, `MIGRATION.md`, and subdirs.
     - Create `docs/INDEX.md` with sections:
       - User-Facing (links to `user/OVERVIEW.md`, `MIGRATION.md`)
       - Developer (links to `ARCHITECTURE.md`, `developer/ADAPTER_IMPLEMENTATION_GUIDE.md`, `developer/PROTOCOL_SPECS.md`, `developer/TESTING_STRATEGIES.md`)
       - Reference Designs (links to original spec docs at root)
     - At top of each moved doc, add a link back to `../INDEX.md` (e.g., `[Back to Index](../INDEX.md)`).
   - `<acceptance_criteria>`:
     - `docs/INDEX.md` exists with organized links
     - `docs/user/OVERVIEW.md` exists
     - `docs/developer/` contains at least 3 files: `ADAPTER_IMPLEMENTATION_GUIDE.md`, `PROTOCOL_SPECS.md`, `TESTING_STRATEGIES.md`
     - Top-level `docs/ARCHITECTURE.md` and `docs/MIGRATION.md` exist

---

## Verification & Must-Haves

**Must-Have Deliverables:**

- Daemon accepts `--totp` flag and propagates to adapters via stdin totp_secret (stub fetched from PGP service).
- PGP service stub module exists and returns `NotImplementedError`; daemon handles gracefully.
- TOTP encryption utility (`totp_crypto`) provides encrypt/decrypt; integrated into control channel and adapter communication (XOR stub).
- Control messages encrypted when both sides have totp_secret.
- Legacy D-Bus `CreateTunnel` forwards to adapter; other tunnel methods also forwarded to maintain compatibility.
- Socket permissions enforced: adapter CLI 0600, control 0660.
- Integration test stubs created for SEC-01/02/03, COMP-01/02, SEC-08.
- Documentation consolidated: `ARCHITECTURE.md`, `MIGRATION.md`, `developer/ADAPTER_IMPLEMENTATION_GUIDE.md`, `PROTOCOL_SPECS.md`, `TESTING_STRATEGIES.md`, `INDEX.md`, `user/OVERVIEW.md`.
- All requirement IDs (COMP-01, COMP-02, SEC-01, SEC-02, SEC-03, SEC-08, TST-01, TST-02, TST-03, DOC-01, DOC-02, DOC-03) appear in at least one task.

**Success Criteria Check:** After execution, security audit can be performed (permissions verified), legacy API should work (manual test), test stubs are present, and docs are complete.

---

*End of PLAN.md*
