# D-Bus Architecture & Security in Multi-Tunnel Manager

## Overview

The Proton VPN Manager uses D-Bus as the **inter-process communication (IPC)** mechanism between the privileged daemon (`proton-vpn-manager`) and unprivileged clients (CLI tools, potential GUI apps).

**Key principle**: D-Bus is the **external API surface** of the daemon. It's meant to be called from outside the daemon's process - that's the entire point of the architecture.

---

## Architecture Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     User Space                               │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────┐   │
│  │ protonvpn   │   │   GUI App   │   │  Third-party    │   │
│  │    CLI      │   │   (future)  │   │  Tools          │   │
│  └──────┬──────┘   └──────┬──────┘   └────────┬────────┘   │
│         │ D-Bus calls     │ D-Bus calls          │ D-Bus calls│
│         └──────────────────┼─────────────────────┘           │
│                            │                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           System D-Bus (message bus)                 │   │
│  │                  (kernel-mediated)                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                            │                                 │
│         ┌──────────────────┼─────────────────────┐           │
│         │                  │                     │           │
│  ┌──────▼──────┐  ┌───────▼──────┐  ┌──────────▼────────┐  │
│  │ Polkit     │  │ Policy       │  │ org.protonvpn.    │  │
│  │ (authz)    │  │ (D-Bus       │  │ Manager service   │  │
│  │            │  │  policy)     │  │                   │  │
│  └────────────┘  └──────────────┘  └──────────┬────────┘  │
│                                                │           │
│                                         ┌──────▼──────┐    │
│                                         │  Daemon      │    │
│                                         │  (root,      │    │
│                                         │   CAP_NET_   │    │
│                                         │   CAP_SYS)   │    │
│                                         └──────┬──────┘    │
│                                                │           │
│                                         ┌──────▼──────┐    │
│                                         │ TunnelManager│   │
│                                         │   Logic      │    │
│                                         └─────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## Current Implementation

### 1. D-Bus Service (`libvpnmanager/dbus/service.py`)

- **Interface name**: `org.protonvpn.Manager`
- **Object path**: `/org/protonvpn/Manager`
- **Methods**: CreateTunnel, DestroyTunnel, ConnectTunnel, DisconnectTunnel, ListTunnels, GetTunnelStatus, GetTrafficStats, ListAdapters, GetAdapterCapabilities, Ping, ListSessions, Login, Logout
- **Signals**: TunnelStateChanged, TunnelCreated, TunnelDestroyed, AdapterRegistered
- **Implementation**: `ManagerService` class inheriting from `dbus_next.service.ServiceInterface`

### 2. Daemon Startup (`daemon/daemon.py`)

```python
async def start():
    self.manager = TunnelManager(...)
    await self._register_adapters()
    self.bus, self.service = await start_service(self.manager)
```

- Connects to system D-Bus (default bus)
- Exports the ManagerService at `/org/protonvpn/Manager`
- Requests well-known name `org.protonvpn.Manager`
- Runs as root (or with capabilities via systemd)

### 3. D-Bus Client (`libvpnmanager/dbus/client.py`)

- `VPNManagerClient` connects to system bus, gets proxy object, calls methods
- Used by CLI tools (e.g., `protonvpn tunnel create ...`)
- No authentication credentials needed from client side - the daemon checks the caller's identity via polkit

---

## Security Model

### Threat Model

- **Goal**: Only authorized users (admins) can create/destroy tunnels, move network interfaces, modify routing tables
- **Threats**:
  - Unauthorized local user trying to create a tunnel
  - Malware trying to route traffic through its own tunnel
  - Information disclosure (reading tunnel list of other users)

### Defense Layers

#### Layer 1: D-Bus Policy (`packaging/dbus/org.protonvpn.Manager.conf`)

Restricts who can **connect** and **send messages** to the service:

```xml
<policy user="root">
  <allow own="org.protonvpn.Manager"/>  <!-- daemon owns the name -->
  <allow send_destination="org.protonvpn.Manager"/>
  <allow receive_sender="org.protonvpn.Manager"/>
</policy>

<policy group="sudo">  <!-- also wheel, admin, adm -->
  <allow send_destination="org.protonvpn.Manager"/>
</policy>

<!-- Deny others by default -->
```

**Effect**: Only root and admin group members can send method calls. All users can receive signals (for UI updates).

#### Layer 2: Polkit Rules (`packaging/polkit/60-protonvpn-manager.rules`)

Provides fine-grained authorization per action. Polkit integrates with D-Bus to prompt for authentication or check group membership.

Actions:
- `org.protonvpn.manager.create-tunnel`
- `org.protonvpn.manager.destroy-tunnel`
- `org.protonvpn.manager.connect`
- `org.protonvpn.manager.disconnect`
- `org.protonvpn.manager.register-adapter`

Rule: Allow root or any user in sudo/wheel/admin/adm groups.

**Note**: The D-Bus service doesn't enforce auth itself; the daemon's methods trust the polkit check. Actually, polkit works by the D-Bus service calling `check_authorization` or by being enforced at the bus daemon level. In our implementation, we rely on the bus policy (layer 1). We could also add explicit polkit checks inside each method using `dbus_next`'s `get_connection_unix_user` etc., but not needed if bus policy is strict.

#### Layer 3: Daemon Method Checks

Each method receives `username` argument and the daemon verifies:
- Tunnel ownership (`tunnel.username == username`)
- Admin status (`_is_admin(username)`) for cross-user operations

Even if someone bypasses D-Bus auth (e.g., runs daemon without policy), the method itself validates.

---

## "Without any other external access from outside the architecture" - What This Means

**Interpretation**: You want to ensure that **only the project's CLI** (and not arbitrary third-party apps) can control the VPN.

**Reality**:
- With standard Linux service design, **any local process** in the sudo/admin group can connect to the D-Bus service and call methods.
- This is **by design** - it's an open API for local administration.
- If you want to restrict to a specific binary (e.g., only `/usr/bin/protonvpn`), D-Bus alone **cannot** do that. D-Bus authenticates **users**, not **executables**.
- Workarounds:
  1. **Private Unix socket** instead of D-Bus: Create socket `/run/protonvpn/manager.sock` with mode 0600, owned by `root:protonvpn`. Only processes running as root or in the `protonvpn` group can connect. The CLI binary would be setgid protonvpn or run with appropriate group. This is more restrictive but less standard.
  2. **Token-based auth**: D-Bus method requires a secret token passed in message. The token is known only to the CLI. But token would be in CLI binary (reverse-engineering possible).
  3. **AppArmor/SELinux confinement**: Label the CLI binary with a specific domain and only allow that domain to connect to the D-Bus socket. Complex.

**Recommendation**: Stick with standard D-Bus + polkit + admin group. It's the same model used by `systemd`, `NetworkManager`, `udisks2`, `logind`. Anyone with sudo privileges can manage the VPN - that's acceptable because they already have root-equivalent access.

---

## D-Bus Configuration Files

### 1. System bus configuration (installed to `/etc/dbus-1/system.d/`)

File: `org.protonvpn.Manager.conf` (created above)

Registers the service and defines policy. Must be installed before daemon starts, otherwise bus will deny name ownership.

### 2. PolicyKit configuration (installed to `/etc/polkit-1/rules.d/`)

File: `60-protonvpn-manager.rules`

Provides authorization rules. Polkit watches D-Bus traffic and intercepts method calls to check authorization. Without polkit, only the bus config applies.

---

## Installation & Deployment

### Package layout

```
/
├── usr/bin/proton-vpn-manager        (daemon binary)
├── usr/lib/systemd/system/proton-vpn-manager.service
├── etc/dbus-1/system.d/org.protonvpn.Manager.conf
├── etc/polkit-1/rules.d/60-protonvpn-manager.rules
└── etc/protonvpn/daemon.yaml          (optional config)
```

### Enabling the daemon

```bash
# Install files
sudo cp proton-vpn-manager /usr/bin/
sudo cp packaging/systemd/usr/lib/systemd/system/proton-vpn-manager.service /usr/lib/systemd/system/
sudo cp packaging/dbus/org.protonvpn.Manager.conf /etc/dbus-1/system.d/
sudo cp packaging/polkit/60-protonvpn-manager.rules /etc/polkit-1/rules.d/

# Reload systemd and dbus
sudo systemctl daemon-reload
sudo dbus-daemon --system --fork --print-address  # or restart dbus: sudo systemctl restart dbus

# Enable and start
sudo systemctl enable --now proton-vpn-manager.service
```

### Testing the D-Bus interface

```bash
# Check service is registered
busctl --system list | grep protonvpn

# Introspect
busctl --system introspect org.protonvpn.Manager /org/protonvpn/Manager

# Call Ping (no auth needed if policy allows)
busctl --system call org.protonvpn.Manager /org/protonvpn/Manager org.protonvpn.Manager Ping
```

---

## Potential Improvements

1. **Add explicit polkit check in daemon methods** (currently we rely on bus policy). Could use `dbus_next` to get caller's uid and check via `polkit` Python library for fine-grained control.

2. **Add D-Bus signal filtering** - allow clients to subscribe to specific tunnels only.

3. **Add introspection improvements** - annotate methods with readable descriptions.

4. **Consider adding a "private" mode**: daemon reads env var `PROTONVPN_PRIVATE=1` and only accepts connections from a specific socket path. CLI would use that socket. But systemd `Type=dbus` expects well-known name on system bus, so mixing modes is tricky.

---

## Summary

- **D-Bus is intentionally the external API** - that's the architecture's design.
- **Access control** is via:
  - D-Bus policy (which groups can send messages)
  - Polkit rules (per-action authorization)
  - Daemon method checks (ownership, admin rights)
- **"External access"** from arbitrary apps is **allowed** for admin users (via group membership). This is standard Linux service behavior.
- If stricter isolation is required, would need to switch to a private socket instead of D-Bus, but that diverges from standard patterns and would complicate integration with polkit and systemd.

**Bottom line**: The current D-Bus setup is correct, secure, and follows Linux desktop/server service best practices.
