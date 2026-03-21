# Adapter Implementation Guide

**Target:** Developers building a new VPN adapter for the Multi-Tunnel Manager (MTM).

This guide covers the complete process: from project setup to a fully functional adapter that integrates with MTM's dual-channel architecture and supports optional TOTP security.

---

## Table of Contents

1. [Overview](#overview)
2. [Adapter Architecture](#adapter-architecture)
3. [Project Setup](#project-setup)
4. [Dual-Server Pattern](#dual-server-pattern)
5. [Startup Sequence](#startup-sequence)
6. [Control Protocol](#control-protocol)
7. [Tunnel Management](#tunnel-management)
8. [TOTP Encryption](#totp-encryption)
9. [Crash Handling and Cleanup](#crash-handling-and-cleanup)
10. [Testing Your Adapter](#testing-your-adapter)
11. [Reference Implementation](#reference-implementation)

---

## Overview

An **adapter** is a standalone process that encapsulates a specific VPN protocol (Proton, WireGuard, etc.). It handles:

- **VPN protocol logic**: Authentication, connection establishment, key exchange.
- **Tunnel lifecycle**: Creating and destroying virtual network interfaces (TUN/TAP).
- **Multi-tunnel support**: Multiple concurrent tunnels in the same process, sharing the VPN session.

The MTM daemon is responsible for:

- Spawning adapter processes on demand.
- Allocating network namespaces and moving devices into them.
- Monitoring adapter health and cleaning up resources if an adapter crashes.

Communication channels:

```
CLI ──Unix socket──▶ Adapter   (tunnel operations)
Adapter ──Unix socket──▶ MTM   (resource allocation control)
```

---

## Adapter Architecture

Each adapter must provide:

1. **CLI Server** — Listens on Unix socket (path provided by MTM via env `MTM_ADAPTER_SOCKET`). Accepts JSON-RPC-like commands: `CreateTunnel`, `DestroyTunnel`, `ListTunnels`, `GetStatus`.
2. **Control Client** — Connects to MTM's internal control socket (path via env `MTM_CONTROL_SOCKET`). Sends control messages: `Register`, `AllocateTunnel`, `ReleaseTunnel`.
3. **Startup Payload** — On stdin, receives a JSON object with `session_id`, `vpn_credentials`, `session_token`, and optionally `totp_secret` (if TOTP enabled).

Adapters run as the **user who invoked the CLI**; MTM runs as root. The adapter must **never** drop privileges or perform privileged operations; all privileged actions go through MTM via the control channel.

---

## Project Setup

We recommend a dedicated Python package per adapter:

```
adapters/
  proton_vpn_adapter/
    pyproject.toml
    cli.py           # entry point
    vpn_adapter.py   # core logic
    tunnel.py        # tunnel state
```

**Dependencies** (minimal):

```toml
[project]
name = "mtm-adapter-proton"
version = "1.0.0"
dependencies = [
    "libvpnmanager @ file://../../../multi-tunnel-namespace/src",  # local package
]
```

The `libvpnmanager` package provides shared models and client libraries. Import it as:

```python
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.config import ConnectionConfig
```

---

## Dual-Server Pattern

Your adapter's `main()` should:

1. Parse environment variables:
   - `MTM_ADAPTER_SOCKET` — path to bind for CLI server
   - `MTM_CONTROL_SOCKET` — path to connect to MTM control
   - `MTM_SESSION_NAME` — unique session identifier (UUID)
   - `MTM_ADAPTER_TYPE` — adapter type string (e.g., "proton")
2. Read startup payload from stdin (single JSON line).
3. Start the **CLI server** (asyncio Unix socket server) bound to `MTM_ADAPTER_SOCKET`.
4. Connect to **MTM control socket** and send `Register` message.
5. Perform VPN login using credentials (if needed).
6. Await CLI commands.

**Skeleton:**

```python
import asyncio, json, os, logging
from libvpnmanager.ipc.unix_socket import UnixSocketServer, UnixSocketClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AdapterCLIServer(UnixSocketServer):
    def __init__(self, adapter):
        super().__init__(adapter)
        self.adapter = adapter

    async def handle_request(self, msg):
        # Dispatch based on msg.method
        ...

class AdapterControlClient(UnixSocketClient):
    async def send_allocate(self, tunnel_name, device, gateway, dns, vpn_ip):
        ...

class ProtonAdapter:
    def __init__(self, startup_payload):
        self.session_id = startup_payload["session_id"]
        self.credentials = startup_payload["vpn_credentials"]
        self.session_token = startup_payload["session_token"]
        self.totp_secret = startup_payload.get("totp_secret")  # may be None
        self.tunnels = {}  # tunnel_name -> Tunnel object

    async def run(self):
        # 1. Start CLI server
        socket_path = os.environ["MTM_ADAPTER_SOCKET"]
        self.cli_server = AdapterCLIServer(self)
        await self.cli_server.start(socket_path)

        # 2. Connect to control and register
        control_path = os.environ["MTM_CONTROL_SOCKET"]
        self.control = AdapterControlClient(control_path)
        await self.control.connect()
        await self.control.send_register(...)

        # 3. VPN login if needed
        await self._login()

        # Keep running
        await self._wait_for_shutdown()

async def main():
    # Read stdin payload
    startup = json.loads(sys.stdin.readline())
    adapter = ProtonAdapter(startup)
    await adapter.run()

if __name__ == '__main__':
    asyncio.run(main())
```

---

## Startup Sequence

1. **MTM** spawns adapter process with env vars and pipes for stdin/stdout.
2. **Adapter** reads startup payload from stdin (newline-terminated JSON).
3. **Adapter** binds CLI socket; MTM waits for socket file to appear (timeout 10s).
4. **Adapter** connects to MTM control socket and sends `Register`:
   ```json
   {
     "msg_type": "register",
     "session_id": "...",
     "adapter_type": "proton",
     "username": "user@example.com"
   }
   ```
5. MTM responds with `registered` and includes control socket path in response.
6. **Adapter** performs VPN login (using `vpn_credentials`). After successful login, overwrite credential buffers with zeros (security).
7. **Adapter** is now ready to accept CLI connections.

---

## Control Protocol

All control messages between Adapter and MTM are length-prefixed JSON (4-byte big-endian length). The message format:

```json
{
  "msg_type": "allocate|release|register",
  ... other fields per type ...
}
```

### Register

Sent by adapter after control connection. MTM stores adapter instance by PID for `SO_PEERCRED` authentication.

### AllocateTunnel

Sent by adapter when a CLI requests a new tunnel. Includes:

- `tunnel_name`
- `username` (of the user, same as in register)
- `device` (TUN device name chosen by adapter)
- `gateway` (VPN gateway IP)
- `dns` (list of DNS servers)
- `vpn_ip` (assigned VPN IP for this tunnel)

MTM responds with `allocated` containing `namespace` and echo of fields, or `error`.

### ReleaseTunnel

Sent when tunnel is destroyed. MTM releases namespace and cleans up.

**Note:** When TOTP is enabled, each control message must include a `totp_code` field (current 6-digit code). MTM validates against stored TOTP secret for the user.

---

## Tunnel Management

Your adapter must:

- Create a new TUN device (name like `proton0`, `proton1`, ...). Use `os.open('/dev/net/tun', ...)` with `IFF_TUN` and `IFF_NO_PI`.
- Bring device up, assign IP address, configure routes inside the network namespace later (MTM does that after `AllocateTunnel`).
- Track tunnels in a dictionary: `self.tunnels[tunnel_name] = Tunnel(...)`.
- Handle concurrent CLI requests: protect `self.tunnels` with an `asyncio.Lock`.
- On `DestroyTunnel`, close TUN device, delete namespace via MTM `ReleaseTunnel`, and remove from `self.tunnels`.

The `CreateTunnel` CLI request should:

1. Create TUN device.
2. Determine gateway and DNS (from VPN server info or configuration).
3. Send `AllocateTunnel` to MTM with device info.
4. If allocation succeeds, store tunnel and respond to CLI with tunnel object.
5. If allocation fails, close TUN device and return error.

---

## TOTP Encryption

When daemon is started with `--totp=on`, all three channels encrypt their payloads using the current TOTP code as a symmetric key.

### Key Material

- The TOTP secret for a user is retrieved from an external PGP service by MTM at adapter spawn time.
- MTM includes `totp_secret` (base64) in the startup payload.
- Adapter stores it in memory, uses it to derive the same TOTP codes as MTM.

### Encryption Model

**Simple XOR-based stub** is acceptable for Phase 4, but real deployment should use AES-GCM or ChaCha20-Poly1305. The encryption flow:

- Sender includes a `totp` field (current 6-digit code) and an `encrypted` field (base64 ciphertext) in the JSON message.
- Receiver uses `totp` + stored `totp_secret` to derive the key, then decrypts `encrypted` to obtain the actual message dict.

Example control message (encrypted mode):

```json
{
  "totp": "123456",
  "encrypted": "base64-ciphertext"
}
```

The decrypted plaintext is the original `{ "msg_type": "allocate", ... }` structure.

### Implementation Hints

Use the shared `libvpnmanager.security.totp_crypto` module (to be created):

```python
from libvpnmanager.security.totp_crypto import encrypt_message, decrypt_message, generate_current_totp

# To encrypt:
ciphertext = encrypt_message(plaintext_bytes, totp_code)
# To decrypt:
plaintext = decrypt_message(ciphertext_bytes, totp_secret, totp_code)
```

Your adapter and MTM must:
- Generate current TOTP from secret (using `time.time()` and time step 30s)
- Include the code in every outbound message
- Decrypt inbound messages using the shared secret and provided code

**Fallback:** If `totp_secret` is `None` (daemon TOTP disabled), pass messages unencrypted.

---

## Crash Handling and Cleanup

MTM monitors adapter processes via `asyncio.wait` on the subprocess. If an adapter exits unexpectedly:

1. MTM receives notification.
2. MTM calls `release_adapter_tunnels` on the `ResourceAllocator`, which sends `ReleaseTunnel` for every tunnel in `adapter.tunnels`.
3. Namespaces and devices are cleaned up.
4. Adapter removed from `adapter_pool`.

Your adapter does not need special crash handling; just ensure `tunnels` dictionary is accurate. When your adapter receives a `SIGTERM` or `SIGINT`, it should:

- Close CLI server socket.
- Send `Shutdown` or simply exit; control socket will close.
- OS will evacuate memory; MTM will clean up tunnels.

**Graceful shutdown:** If you send `Shutdown` on control socket before exiting, MTM can call `ReleaseTunnel` while your adapter is still alive (cleaner). This is optional but recommended.

---

## Testing Your Adapter

Create unit tests under `tests/unit/` and integration tests under `tests/integration/`.

**Unit tests** should mock the control socket and focus on tunnel creation logic, device handling, and encryption/decryption.

**Integration tests** spin up a real MTM daemon (as root or with mock root) and verify end-to-end flow:

1. Start daemon with temporary sockets.
2. Use `ManagerClient` to start your adapter.
3. Use `AdapterClient` to create/destroy tunnels.
4. Verify namespace appears and is cleaned.
5. Simulate adapter crash (send `SIGKILL`) and assert MTM cleans up.

See existing integration tests in `multi-tunnel-namespace/tests/integration/` for patterns.

---

## Reference Implementation

The `dummy_adapter` in `src/adapters/dummy_adapter/cli.py` demonstrates the complete pattern:

- Dual-server startup
- Registration with MTM
- Tunnel simulation with 500ms delay
- Multi-tunnel dictionary
- No real VPN, just placeholder

The `proton_vpn_adapter/cli.py` shows a real implementation with `proton.vpn.core.api` integration.

Study these to understand the expected message flows and error handling.

---

## Checklist Before Submitting

- [ ] Adapter reads stdin payload with `session_id`, `totp_secret`, `vpn_credentials`, `session_token`.
- [ ] CLI server binds to `MTM_ADAPTER_SOCKET` (0600 permissions).
- [ ] Control client connects to `MTM_CONTROL_SOCKET` and sends `Register`.
- [ ] `Register` includes `session_id`, `adapter_type`, `username`.
- [ ] `AllocateTunnel` sends device, gateway, dns, vpn_ip.
- [ ] `CreateTunnel` command handled concurrently with lock.
- [ ] Credentials zeroized after login.
- [ ] TOTP encryption used on all channels if `totp_secret` provided.
- [ ] Adapter shuts down cleanly on SIGTERM.
- [ ] Unit tests cover core logic.
- [ ] Integration test passes with full flow.
- [ ] Documentation updated (protocol specifics, config options).

---

*Back to [INDEX.md](../INDEX.md)*
