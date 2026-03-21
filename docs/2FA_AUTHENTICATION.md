# 2FA Authentication in Multi-Tunnel System

**Status:** Final design — Phase 1 implementation, with Phase 4 external service integration
**Last updated:** 2025-03-21

---

## Important: Two Distinct 2FA Layers

⚠️ **Do not confuse these:**

| Layer | Purpose | Is it mandatory? | Who authenticates? | Where secret stored? |
|-------|---------|------------------|-------------------|---------------------|
| **MTM 2FA** | Authorize user to control the local Multi-Tunnel Manager | Yes (unless `--totp=off`) | User → MTM daemon | Encrypted in system keyring (libsecret) |
| **VPN Adapter 2FA** | Authenticate adapter to the VPN backend (e.g., Proton VPN) | **No** — only if the VPN service requires it | Adapter → VPN backend API | Never stored; used ephemerally in adapter memory |

**Key differences:**
- **MTM 2FA** is a **local security boundary** — it protects your system from unauthorized control.
- **VPN Adapter 2FA** is a **remote service requirement** — the VPN backend (like Proton's servers) may require 2FA based on the user's account settings. This is independent of the local MTM 2FA.
- Both layers use the **same TOTP secret**, but they are **separate, independent authentications** to different entities (local daemon vs remote VPN service).

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

### Option A: Generate New TOTP Secret (Current)

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

### Option B: Import TOTP Secret from External Service (Planned for Phase 4)

For users migrating from other systems or enterprise environments where TOTP secrets are centrally managed, the CLI supports importing pre-existing TOTP keys from Proton's external authentication service.

User runs:
```bash
protonvpn 2fa setup --download-key
```

**Flow:**

1. CLI prompts for Proton account credentials (username/password)
2. CLI authenticates with Proton's authentication API over secure TLS
3. Proton API returns the user's existing TOTP secret (if 2FA is already enabled on the account)
   - The secret is delivered via an encrypted channel using the user's session token
   - The API response includes metadata: `{"secret": "JBSWY3DPEHPK3PXP", "method": "totp", "backup_codes": [...]}`
4. CLI **never stores** the secret; it streams directly to MTM via D-Bus:
   ```json
   {
     "method": "Import2FASecret",
     "params": {
       "totp_secret": "JBSWY3DPEHPK3PXP",
       "source": "proton_api"
     }
   }
   ```
5. MTM:
   - Validates the secret by computing a test TOTP and verifying with Proton's API (optional challenge-response)
   - Stores encrypted in system keyring (same as Option A)
   - Generates new backup codes (since old ones may be compromised in transit)
   - Prompts user to verify by entering a current TOTP code from their existing device
6. After verification, MTM confirms setup to CLI

**Security considerations:**
- **Transport security:** All communication with Proton API uses TLS 1.3+ with certificate pinning
- **Secret exposure:** TOTP secret lives in CLI memory only transiently during import; zeroed immediately after streaming to MTM
- **Verification required:** Even imported secrets must be verified with a live TOTP code to confirm the user possesses the OTP device
- **Backup code rotation:** New backup codes are generated to prevent reuse of potentially exposed codes
- **Audit trail:** Import operation is logged in MTM audit log with source identification

**Implementation notes:**
- The Proton API endpoint: `POST /v2/2fa/secret` (authenticated session required)
- Rate limiting: 3 import attempts per hour to prevent abuse
- Fallback: If import fails (e.g., user doesn't have 2FA on Proton account), MTM returns `2FA_IMPORT_FAILED` with guidance

---

**Security:** Regardless of method, the TOTP secret is:
- Never stored in plaintext on disk (always encrypted in keyring)
- Never displayed to the user after initial setup/import
- Never transmitted after initial provisioning
- Zeroed from memory when possible
- Only accessible to MTM and adapter processes with appropriate Unix socket permissions

---

## Authentication Flow Summary

```
┌─────────┐
│   CLI   │ prompts user for TOTP code
└────┬────┘      │
     │ enters "123456"
     ▼             │ (same 6-digit code)
┌─────────────────────────────────────────────┐
│                                            │
│  ┌─────────────────────────────────────┐  │
│  │  MTM AUTHENTICATION (Local)         │  │
│  │  • CLI → MTM D-Bus with totp_code  │  │
│  │  • MTM verifies against stored TOTP│  │
│  │    secret in keyring                │  │
│  │  • Grants: permission to control    │  │
│  │    adapters, allocate namespaces    │  │
│  └─────────────────────────────────────┘  │
│                                            │
│  ┌─────────────────────────────────────┐  │
│  │  VPN ADAPTER AUTHENTICATION (Backend)│  │
│  │  • Adapter → Proton VPN API with    │  │
│  │    vpn_credentials.twofa = "123456"│  │
│  │  • Proton verifies TOTP             │  │
│  │  • Grants: VPN session, server      │  │
│  │    access, traffic routing          │  │
│  └─────────────────────────────────────┘  │
│                                            │
└────────────────────────────────────────────┘
```

**Key insight:** One TOTP code provides **two independent authentications**:

| Authentication | When is it required? | What happens if it fails? |
|----------------|---------------------|---------------------------|
| **MTM (local)** | Always (unless `--totp=off`) | Operation rejected — user not authorized to control the system |
| **VPN adapter (backend)** | Only if the VPN service requires 2FA for this account | VPN login fails — adapter cannot establish tunnel |

If either verification fails, the operation is rejected. They are **independent security layers**: local system protection and remote service authentication.

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

**Note:** This single TOTP code serves **two independent authentications**:
- **MTM authentication** (local control — **always required** unless `--totp=off`)
- **VPN adapter authentication** (remote VPN backend — **only if the VPN service requires 2FA** for this account)

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
      "twofa": "123456"  // optional: for VPN adapter authentication if the VPN backend requires it
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
   - `vpn_credentials` → use to authenticate to the VPN backend
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
   - The `vpn_credentials.twofa` field contains the same TOTP code from the CLI request
   - This authenticates the user to Proton's VPN backend (VPN adapter authentication)
   - If the VPN backend doesn't require 2FA for this account, the field may be empty or omitted
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

This same TOTP code will be used for:
- **Adapter → MTM control verification** (MTM 2FA) — always required
- **VPN adapter authentication** (VPN backend 2FA) — only if the VPN service (e.g., Proton VPN) requires 2FA for this account; otherwise the field may be ignored

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

**2FA Import failures:**
- `2FA_IMPORT_FAILED` — API call to Proton failed (network error, auth failure, or user not enrolled)
- `2FA_IMPORT_VERIFICATION_FAILED` — User failed to provide valid TOTP after import (3 attempts max)
- `2FA_IMPORT_RATE_LIMITED` — Too many import attempts; user must wait or use manual method
- CLI displays actionable guidance: check credentials, verify 2FA is enabled on account, retry after cooldown

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
