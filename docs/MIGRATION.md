# Migration Guide: From Old Architecture to v1.0

This guide helps users and operators transition from the previous monolithic Proton VPN CLI to the new Multi-Tunnel Adapter Architecture (v1.0).

---

## What Changed?

| Aspect | Old Architecture | New Architecture (v1.0) |
|--------|------------------|------------------------|
| **Credential storage** | Persistent JSON files in `~/.local/share/protonvpn/sessions/` | Ephemeral, in-process memory only; no disk storage |
| **Adapter model** | In-process adapter calls; single-tunnel only | Persistent adapter processes per user per type; multi-tunnel supported natively |
| **Tunnel command flow** | CLI → D-Bus → daemon → adapter (in-process) | CLI → Unix socket → adapter (direct); daemon only for lifecycle |
| **Session reuse** | Multiple sessions = multiple processes (overhead) | One adapter = one session reused across all tunnels of that type |
| **Crash isolation** | Daemon crash loses all sessions | Adapter crash affects only that user's tunnels; daemon cleans up |
| **2FA handling** | CLI-level token with D-Bus session | Optional TOTP encryption on all channels; per-request codes |

---

## User Impact

### You Must Log In Again

Since session credentials are no longer stored on disk, you will need to provide your Proton VPN credentials when creating the first tunnel after:

- System reboot
- Daemon restart
- Adapter stop/start cycle

**Example:**

```bash
$ protonvpn tunnel create personal --country US --protocol wireguard
Username: user@protonmail.com
Password: ********
# First tunnel: adapter is spawned and login happens inside adapter
Tunnel "personal" created and connected.
```

A second tunnel from the same user will reuse the same adapter and may not prompt for credentials again unless the server forces re-authentication.

### TOTP (2FA) May Be Required

If your organization or security policy requires TOTP, start the daemon with `--totp=on`:

```bash
sudo proton-vpn-manager --totp=on
```

You must then enroll your TOTP secret once:

```bash
protonvpn setup-2fa --scan-qr
```

After that, every command that creates or destroys tunnels will prompt for a 6-digit code:

```bash
$ protonvpn tunnel create work --country DE
TOTP Code: 123456
Tunnel "work" created and connected.
```

**Note:** TOTP secrets are retrieved from an external PGP service at runtime and never stored locally.

### Adapter Management Commands

The old `protonvpn session` commands are replaced by:

```bash
protonvpn adapter list        # List running adapters and their ownership
protonvpn adapter stop proton # Stop the Proton adapter for current user
```

Use these to troubleshoot stuck adapters or force a fresh login.

---

## Administrator Impact

### Service Configuration

If you previously configured a systemd service for `proton-vpn-manager`, update it to include the `--totp` flag if desired:

```ini
# /etc/systemd/system/proton-vpn-manager.service
[Service]
ExecStart=/usr/bin/proton-vpn-manager --totp=off  # default; change to on if required
```

Reload systemd and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart proton-vpn-manager
```

### Network Permissions

The MTM daemon still requires `CAP_NET_ADMIN` to create network namespaces and move devices. This is typically granted by running as root or via systemd `CapabilityBoundingSet=CAP_NET_ADMIN`.

### External PGP Service

If you enable `--totp=on`, the daemon will attempt to fetch TOTP secrets from an external PGP service. Ensure that your deployment can reach this service. If unreachable, the daemon logs a warning and continues operating without TOTP (fallback mode). No blocking failures occur.

Configure the service URL via environment variable or config file (see developer docs).

---

## Scripting and Automation

Existing scripts that called `protonvpn tunnel create` continue to work unchanged **when TOTP is off** (default). However, interactive credential prompts may break non-interactive automation. To automate:

- Pre-create tunnels via configuration (not currently supported; future work)
- Use direct adapter API with proper session management (see developer guide)

When TOTP is enabled, scripts must supply a TOTP code on stdin or via environment; this is not yet standardized. Consider leaving TOTP off for automated deployments.

---

## Known Limitations

- **No session recovery:** After adapter crash or daemon restart, all tunnels are torn down; user must manually recreate.
- **TOTP fallback:** When external PGP service is down, TOTP is effectively disabled; security level drops to legacy token model until service returns.
- **Multi-protocol:** Only the Proton adapter is fully migrated; WireGuard and Psiphon adapters may still use legacy in-process mode unless explicitly updated.

---

## Need Help?

- Check the [User Overview](user/OVERVIEW.md) for conceptual understanding.
- See [Adapter Implementation Guide](developer/ADAPTER_IMPLEMENTATION_GUIDE.md) if you are developing or modifying an adapter.
- Report issues on GitHub: https://github.com/ProtonVPN/proton-vpn-cli/issues

---

*Back to [Index](../INDEX.md)*
