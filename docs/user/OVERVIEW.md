# Multi-Tunnel Architecture: User Overview

**Version:** v1.0 (Python implementation)
**Date:** 2025-03-20

---

## What Is This?

The Multi-Tunnel Adapter Architecture reimagines the Proton VPN CLI's tunnel manager (MTM) as a **process supervisor** that manages isolated, credential-holding adapter processes. This delivers secure multi-tunnel VPN management without storing credentials on disk.

### Before (Monolithic)

The old daemon directly managed VPN connections in-process, storing credentials in `$XDG_DATA_HOME/protonvpn/sessions/` as JSON files. Multiple tunnels required complex session juggling and a special multi-tunnel connector.

### After (Two-Tier)

- **MTM daemon** runs as root (or with NET_ADMIN) and handles only privileged operations: spawning adapter processes, allocating network namespaces, and cleaning up on crashes.
- **Adapters** run as unprivileged user processes, each holding a single user's VPN credentials in memory. One adapter per user per VPN type (e.g., one Proton adapter). Multiple tunnels reuse the same adapter and session.
- **CLI** talks directly to adapters for tunnel operations (create, destroy, connect, disconnect), bypassing the daemon for normal flow.

---

## Key User-Visible Changes

### 1. No Session Persistence

- **Before:** You logged in once; sessions saved to disk and reused across restarts.
- **After:** Adapter processes hold credentials only in memory. If the adapter stops (crash, reboot, manual stop), you must log in again when creating a new tunnel.
- **Impact:** Slightly more frequent credential prompts; significantly better security (no plaintext tokens on disk).

### 2. Optional TOTP Security Layer

The daemon supports an optional `--totp=on|off` flag (default **off**) that requires a TOTP code for every CLI command. When enabled:

- All communications (CLI↔MTM, MTM↔Adapter, CLI↔Adapter) are encrypted using the current TOTP code as a symmetric key.
- TOTP secrets are fetched from an external PGP service at runtime; they are never stored on disk.
- If the external PGP service is unreachable, the system falls back to operating without TOTP (no blocking error).

**Note:** Most users will keep TOTP disabled unless required by organizational security policies.

### 3. Legacy API Compatibility

The classic `protonvpn tunnel create ...` command still works exactly as before. Internally, the legacy D-Bus API forwards to the new adapter architecture transparently. Existing scripts and tools continue to function unchanged.

---

## Advisor: Command Changes

### New Commands

- `protonvpn adapter list` — Show running adapter processes.
- `protonvpn adapter stop <type>` — Stop a specific adapter (e.g., `protonvpn adapter stop proton`).

These replace the old `protonvpn session` commands, which are now removed.

### Modified Commands

- `protonvpn tunnel create ...` — May prompt for credentials on first tunnel of a session (adapter startup). Subsequent tunnels reuse the same adapter and only ask for VPN credentials if the server requires it.
- Interactive prompts: If TOTP is enabled, you'll be asked for a TOTP code on each command that triggers network operations.

---

## Architecture in a Nutshell

```
CLI (user) ──Unix socket──▶ Adapter (user process, holds VPN credentials)
                               │
                               │ control (AllocateTunnel, ReleaseTunnel)
                               ▼
                        MTM Daemon (root, NET_ADMIN)
                               │
                               ▼
                        Linux network namespaces
```

- **Adapter processes** are persistent: one per user per adapter type. The second tunnel you create uses the same adapter; no second login needed.
- **MTM** spawns adapters on demand and tracks them in a registry. If an adapter crashes, MTM detects it and cleanly releases all associated tunnel resources (namespaces, devices).
- **Idle timeout:** Adapters with no active tunnels for a configurable period (default 5 minutes) are automatically shut down to reclaim resources.

---

## Troubleshooting

### Adapter not running?

If you get "Adapter not found" errors, start the MTM daemon:

```bash
sudo proton-vpn-manager  # or systemctl start proton-vpn-manager
```

Then create a tunnel; the daemon will spawn the adapter automatically.

### Stale adapter after crash?

Check running adapters:

```bash
protonvpn adapter list
```

Stop a problematic adapter:

```bash
protonvpn adapter stop proton
```

### No TOTP device configured?

TOTP is optional. If your administrator requires it, use `protonvpn setup-2fa` once to enroll your TOTP secret (stored in system keyring and distributed via external PGP service). After that, you'll be prompted for a 6-digit code on each tunnel operation.

---

## For Developers

See the [Developer Documentation Index](INDEX.md#developer-documentation) for implementation guides, protocol specs, and testing strategies.

---

*Back to [Index](../INDEX.md)*
