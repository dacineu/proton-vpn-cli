# Protocol Specifications

This document defines the wire protocols used between components:

- [CLI ↔ Adapter](#cli--adapter)
- [Adapter ↔ MTM](#adapter--mtm)
- [CLI ↔ MTM (D-Bus)](#cli--mtm-d-bus)

All protocols assume UTF-8 encoding for strings and JSON for structured data. Binary blobs use base64 encoding when carried in JSON.

---

## CLI ↔ Adapter

**Transport:** Unix domain socket (stream).
**Framing:** 4-byte big-endian length prefix followed by JSON payload.

### Message Types

| msg_type | Direction | Description |
|----------|-----------|-------------|
| `CreateTunnel` | CLI → Adapter | Create a new tunnel |
| `DestroyTunnel` | CLI → Adapter | Destroy a tunnel |
| `ListTunnels` | CLI → Adapter | List all tunnels |
| `GetStatus` | CLI → Adapter | Get status for a tunnel |
| `tunnel_created` | Adapter → CLI | Event: tunnel created |
| `tunnel_destroyed` | Adapter → CLI | Event: tunnel destroyed |

#### CreateTunnel

**Request fields:**

```json
{
  "msg_type": "CreateTunnel",
  "request_id": 123,
  "totp": "123456",               // optional if TOTP disabled
  "encrypted": "base64...",       // optional: encrypted full payload
  "session_token": "abc...",      // session token from MTM
  "tunnel_name": "personal",
  "config": { ... }               // ConnectionConfig fields (adapter-specific)
}
```

If `encrypted` is present, decrypt it using TOTP to obtain the true payload (which includes the above fields without `totp`/`encrypted`). The decrypted payload is a JSON object with at least `tunnel_name` and `config`.

**Response:**

```json
{
  "msg_type": "response",
  "request_id": 123,
  "result": { "tunnel": { ... } }   // Tunnel object
}
```

or

```json
{
  "msg_type": "error",
  "request_id": 123,
  "error": "Error message",
  "code": "ERROR_CODE"
}
```

#### DestroyTunnel

**Request:**

```json
{
  "msg_type": "DestroyTunnel",
  "request_id": 124,
  "totp": "654321",
  "session_token": "abc...",
  "tunnel_name": "personal"
}
```

**Response:** Success `{}` or error.

---

## Adapter ↔ MTM

**Transport:** Unix domain socket (stream).
**Framing:** Same 4-byte length prefix + JSON.

### Control Messages

| msg_type | Direction | Description |
|----------|-----------|-------------|
| `register` | Adapter → MTM | Register adapter instance |
| `allocate` | Adapter → MTM | Request namespace allocation |
| `release` | Adapter → MTM | Release tunnel resources |
| `shutdown` | Either → Either | Graceful shutdown notice |

#### Register

**Request (from adapter):**

```json
{
  "msg_type": "register",
  "session_id": "uuid",
  "adapter_type": "proton",
  "username": "user@example.com"
}
```

MTM responds:

```json
{
  "msg_type": "registered",
  "control_socket": "/run/mtm/internal.sock"
}
```

#### AllocateTunnel

**Request (from adapter):**

```json
{
  "msg_type": "allocate",
  "totp": "123456",            // if TOTP enabled
  "encrypted": "base64...",    // if TOTP enabled, contains the rest
  "session_token": "...",      // session token for validation
  "tunnel_name": "t1",
  "username": "user@example.com",
  "device": "tun0",
  "gateway": "10.8.0.1",
  "dns": ["1.1.1.1", "1.0.0.1"],
  "vpn_ip": "10.8.0.2"
}
```

**Response:**

```json
{
  "msg_type": "allocated",
  "tunnel_name": "t1",
  "namespace": "vpn_t1",
  "device": "tun0",
  "gateway": "10.8.0.1",
  "dns": ["1.1.1.1"],
  "vpn_ip": "10.8.0.2"
}
```

#### ReleaseTunnel

**Request:**

```json
{
  "msg_type": "release",
  "totp": "654321",
  "encrypted": "base64...",
  "session_token": "...",
  "tunnel_name": "t1"
}
```

**Response:**

```json
{
  "msg_type": "released",
  "tunnel_name": "t1"
}
```

---

## CLI ↔ MTM (D-Bus)

**Interface:** `org.protonvpn.Manager` on `/org/protonvpn/Manager`.
**Wire format:** D-Bus native (binary). The methods and signals are defined in the service.

### Methods

- `CreateTunnel(config_dict: a{sv}, username: s) -> a{sv}`
- `DestroyTunnel(name: s, username: s) -> b`
- `ConnectTunnel(name: s, username: s) -> b`
- `DisconnectTunnel(name: s, username: s) -> b`
- `ListTunnels(username: s, all_users: b) -> aa{sv}`
- `GetTunnelStatus(name: s, username: s) -> a{sv}`
- `StartAdapter(adapter_type: s, credentials: a{sv}) -> a{sv}` (internal use, but part of client library)

When TOTP is enabled, the `config_dict` may contain an `encrypted` blob and the caller must supply a `totp_code` field. The D-Bus method signatures remain unchanged; encryption is at the application level.

---

## Error Codes

String error codes (uppercase with underscores) are used in error responses:

- `INVALID_SESSION` — session token missing or invalid
- `INVALID_2FA` — TOTP code incorrect
- `DEVICE_NOT_FOUND` — TUN device missing
- `NAMESPACE_EXISTS` — namespace already exists (stale)
- `DEVICE_BUSY` — device already in another namespace
- `UNSUPPORTED` — operation not supported by this adapter type
- `MISSING_FIELD` — required parameter missing
- `INTERNAL_ERROR` — unexpected failure

---

*Back to [INDEX.md](../INDEX.md)*
