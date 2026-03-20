# 2FA Authentication in Multi-Tunnel System

**Status:** Final design — Phase 1 implementation
**Last updated:** 2025-03-20

---

## Overview

The Multi-Tunnel System uses **TOTP (Time-based One-Time Password)** as mandatory two-factor authentication for every CLI operation. There are **no persistent session tokens**; each request must include a fresh TOTP code from the user's OTP device.

This design ensures:
- **Per-request authentication** — no token theft or replay across commands
- **No secret storage in CLI** — CLI never sees or stores TOTP secret
- **MTM as secret keeper** — TOTP secret stored encrypted, delegated to adapters
- **End-to-end verification** — Both MTM and adapters verify TOTP on relevant messages

---

## Cryptographic Basis

**TOTP = HMAC-SHA1(secret, time-counter)**

- **Secret**: 160-bit random key (base32 encoded, e.g., `JBSWY3DPEHPK3PXP`)
- **Time counter**: `floor(current_unix_time / 30)` (default 30s time step)
- **HMAC-SHA1**: Compute HMAC using secret and counter
- **Digit extraction**: Take 4 bits from HMAC result, modulo 10^6 → 6-digit code

Code changes every 30 seconds.

---

## Setup Phase (One-Time)

User runs:
```bash
protonvpn 2fa setup --scan-qr
```

**MTM actions:**

1. Generate random 160-bit TOTP secret
2. Store encrypted in system keyring (libsecret on Linux) using user's login password or machine-specific key
3. Generate QR code:
   ```
   otpauth://totp/ProtonVPN:user@proton.me?secret=JBSWY3DPEHPK3PXP&issuer=ProtonVPN
   ```
4. Generate **backup codes** (8-digit, single-use, 10 codes)
5. Display to user:
   ```
   ⚠️  IMPORTANT: Save this 2FA key and backup codes securely.
   This is your only backup. Write them down or export them.
   You will not see these secrets again.
   ```
6. Prompt user to enter one current TOTP code to verify setup
7. Store hashed backup codes (like `/etc/shadow` format) for future recovery

**User actions:**
- Scan QR code with TOTP app (Google Authenticator, Authy, YubiKey)
- Write down backup codes and store securely
- Confirm setup by entering current code

**Security:** TOTP secret never displayed again after setup. Cannot be retrieved from MTM; only reset via backup codes or admin intervention.

---

## Normal Operation Flow

### 1. CLI → MTM: Starting an Adapter

User runs:
```bash
protonvpn tunnel create personal --country US --protocol wireguard
```

CLI prompts:
```
TOTP Code: █
```

User enters current 6-digit code (e.g., `123456`).

CLI calls MTM D-Bus:
```json
{
  "method": "StartAdapter",
  "params": {
    "adapter_type": "wireguard",
    "credentials": {
      "username": "user@proton.me",
      "password": "•••••••",
      "twofa": "123456"  // for VPN service if required
    },
    "totp_code": "123456"  // for MTM authentication
  }
}
```

**MTM validates TOTP:**

1. Retrieve stored TOTP secret from keyring (decrypt)
2. Compute expected TOTP for current time (±1 time step window for clock skew)
3. Constant-time compare with provided `totp_code`
4. **If invalid:** Return error `{"error": "INVALID_2FA", "message": "Invalid 2FA code"}`
5. **If valid:** Proceed to spawn adapter

---

### 2. MTM Spawns Adapter with TOTP Secret

MTM:
1. Creates Unix sockets:
   - CLI socket: `/run/mtm/adapters/{os_user}_{adapter_type}.sock`
   - Control socket: `/run/mtm/control/{os_user}_{adapter_type}.sock`
2. Sets permissions `0600`, owned appropriately
3. Prepares stdin payload for adapter:
   ```json
   {
     "session_id": "uuid-v4",
     "totp_secret": "JBSWY3DPEHPK3PXP",
     "vpn_credentials": {
       "username": "user@proton.me",
       "password": "•••••••",
       "twofa": "123456"
     }
   }
   ```
4. Spawns adapter process with environment:
   ```
   ADAPTER_ENDPOINT=/run/mtm/adapters/...
   CONTROL_ENDPOINT=/run/mtm/control/...
   ```
   and pipes stdin JSON
5. Waits for adapter CLI socket to bind (timeout 10s)
6. Returns to CLI: `{"endpoint": "unix:///run/mtm/adapters/..."}` (no session token)

---

### 3. Adapter Startup

Adapter:
1. Reads stdin JSON (blocking until complete)
2. Extracts:
   - `totp_secret` → store in memory for TOTP verification
   - `vpn_credentials` → use to login to VPN service
   - `session_id` → use in control messages
3. **Zero stdin buffer** immediately after reading (overwrite with null bytes)
4. Binds CLI Unix socket (start asyncio server)
5. Connects to MTM control socket
6. Sends `Register` control message:
   ```json
   {
     "action": "Register",
     "session_id": "uuid-v4",
     "adapter_type": "wireguard",
     "username": "user@proton.me"
   }
   ```
   MTM adds to `adapter_pool[(adapter_type, vpn_username)] = AdapterProcess(...)`
7. Performs VPN login using `vpn_credentials`
8. After successful login:
   - Zero credential buffers (password, 2FA for VPN)
   - Keep only VPN session tokens
9. Enters main loop: serve CLI connections, handle control messages

---

### 4. CLI → Adapter: Create Tunnel (with TOTP)

CLI now needs to send request to adapter.

**User must enter TOTP again** (fresh code, possibly different from Step 1):
```
TOTP Code: █
```

User enters new code (e.g., `654321`).

CLI connects to adapter socket and sends:
```json
{
  "action": "CreateTunnel",
  "totp_code": "654321",
  "tunnel_name": "personal",
  "config": {
    "country": "US",
    "protocol": "wireguard"
  }
}
```

---

### 5. Adapter Validates TOTP on CLI Request

Adapter:
1. Compute expected TOTP from stored `totp_secret` (current ±1 time step)
2. Constant-time compare with `totp_code`
3. **If invalid:**
   - Log WARNING: `Invalid TOTP from CLI`
   - Close connection (or return `{"error": "INVALID_2FA"}`)
4. **If valid:** Process request:
   - Use VPN session to create WireGuard connection
   - Extract `device`, `gateway`, `dns`
   - Send `AllocateTunnel` to MTM (see next step)
   - Wait for MTM response
   - Return tunnel info to CLI

---

### 6. Adapter → MTM: AllocateTunnel (with TOTP)

Adapter sends on control socket:
```json
{
  "action": "AllocateTunnel",
  "totp_code": "654321",  // same TOTP from CLI request
  "session_id": "uuid-v4",
  "tunnel_name": "personal",
  "device": "wg0-personal",
  "gateway": "10.9.0.1",
  "dns": ["1.1.1.1"]
}
```

---

### 7. MTM Validates TOTP on Control Message

MTM:
1. Look up adapter by `session_id` → get associated `vpn_username`
2. Retrieve stored TOTP secret for that user from keyring (decrypt)
3. Compute expected TOTP (current ±1 window)
4. Compare with `totp_code`
5. **If invalid:**
   - Log WARNING: `Invalid TOTP on control channel from adapter session_id=...`
   - Return error: `{"status": "error", "code": "INVALID_2FA"}`
   - Potentially consider adapter compromised? (maybe flag for review)
6. **If valid:**
   - Proceed with namespace allocation:
     - `ip netns add vpn_personal`
     - `ip link set wg0-personal netns vpn_personal`
     - Configure address, routes, DNS inside namespace
   - Return success:
     ```json
     {
       "status": "allocated",
       "namespace": "vpn_personal",
       "device": "wg0-personal"
     }
     ```

---

### 8. Adapter Returns Success to CLI

Adapter receives MTM response, then replies to CLI:
```json
{
  "status": "connected",
  "tunnel": {
    "name": "personal",
    "device": "wg0-personal",
    "namespace": "vpn_personal",
    "endpoint": "se1-01.proton.me:51820"
  }
}
```

CLI prints to user:
```
✓ Tunnel 'personal' connected
  Device: wg0-personal
  Namespace: vpn_personal
```

---

## Security Properties

| Threat | Mitigation |
|--------|------------|
| **Unauthorized CLI usage** | Every command requires fresh TOTP from OTP device |
| **Rogue process as same user** | TOTP secret not stored in CLI; attacker cannot generate valid codes without physical OTP device |
| **Adapter impersonation** | Adapter receives TOTP secret only from MTM during spawn; rogue process cannot get secret without compromising MTM |
| **Control message forgery** | MTM validates TOTP on every `AllocateTunnel`, `ReleaseTunnel` |
| **Replay attack** | TOTP codes expire in 30s windows; old codes rejected |
| **Memory scraping** | TOTP secret kept in memory only; MTM stores encrypted on disk; adapter zeroes on shutdown |
| **Man-in-the-middle** | Unix sockets local only; no network exposure |
| **Privilege separation** | MTM holds persistent encrypted secret; adapter holds ephemeral in-memory copy; CLI never sees secret |

---

## Error Handling

**Invalid TOTP:**
- MTM returns `INVALID_2FA` to CLI (StartAdapter)
- Adapter returns `INVALID_2FA` to CLI (tunnel operations)
- MTM logs WARNING on invalid control messages (potential attack indicator)

**Clock skew:**
- Accept current time step ±1 (allows for slight clock drift between user's OTP device and system)
- If consistently failing, suggest user check time sync

**Backup codes:**
- 8-digit single-use backup codes stored hashed in MTM keyring
- Used when OTP device lost
- CLI calls `protonvpn 2fa backup --use CODE12345` to authenticate instead of TOTP
- MTM marks backup code as used after successful auth

---

## Memory Sanitation

**Adapter:**
- Read stdin into `bytearray`, zero after parsing
- Keep `totp_secret` as `bytearray` (mutable) to allow overwriting
- On graceful shutdown: overwrite `totp_secret` with null bytes
- Note: Python may keep copies in GC; use `ctypes` or `memoryview` for aggressive clearing if needed

**MTM:**
- Decrypt TOTP secret from keyring into memory buffer
- Keep in memory for duration of daemon (performance vs security tradeoff)
- Could decrypt on-demand for each verification (slower but more secure)
- On shutdown: overwrite buffer

---

## Future Improvements

- **CLI session caching**: After first TOTP, issue short-lived (15min) session token to reduce user prompts (currently burdensome)
- **Hardware security**: Store TOTP secret in TPM or YubiKey; MTM uses HSM for cryptographic operations without exposing secret to memory
- **Audit logging**: Log TOTP failures with rate limiting to detect brute-force attacks
- **Device binding**: Bind TOTP secret to specific OTP device public key (if using YubiKey)

---

**Related documents:**
- `SOCKET_ARCHITECTURE.md` — Socket paths, permissions, dual-socket design
- `COMMUNICATION_PROTOCOL.md` — Message formats, error codes, framing
- `SECURITY_MODEL.md` — Full threat model and security properties
- `PROCESS_FLOW.md` — End-to-end sequence diagrams

---

*This document captures the final agreed design for Phase 1 implementation. Do not modify without team discussion.*
