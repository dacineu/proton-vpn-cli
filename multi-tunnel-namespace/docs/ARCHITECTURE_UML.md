# Architecture UML Diagrams

## Table of Contents
1. [Package Diagram](#package-diagram)
2. [Class Diagram](#class-diagram)
3. [Sequence Diagrams](#sequence-diagrams)
4. [Component Diagram](#component-diagram)
5. [Deployment Diagram](#deployment-diagram)

---

## Package Diagram

Shows high-level package structure and dependencies.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          multi-tunnel-namespace/                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐         depends on         ┌──────────────────┐  │
│  │  core/           │◄──────────────────────────│  python-stdlib   │  │
│  │  libvpnmanager   │                            └──────────────────┘  │
│  │  (pure Python)   │                                 ▲               │
│  └──────────────────┘                                 │               │
│         │                                             │               │
│         │ defines ABCs                               │               │
│         ▼                                             │               │
│  ┌──────────────────┐         depends on         ┌──────────────────┐  │
│  │ adapters/        │◄──────────────────────────│  libvpnmanager   │  │
│  │ • proton-vpn-    │                            └──────────────────┘  │
│  │   adapter/       │                                 ▲               │
│  │ • psiphon-       │                                 │               │
│  │   adapter/       │                            ┌────┴──────┐       │
│  │ • wireguard-     │                            │ external  │       │
│  │   adapter/       │                            │ services  │       │
│  └──────────────────┘                            │ (proton,  │       │
│         │                                         │ psiphon,  │       │
│         │ provides adapter impls                  │ wireguard)│       │
│         ▼                                         └───────────┘       │
│  ┌──────────────────┐                                                  │
│  │ clis/            │                                                  │
│  │ • protonvpn/     │◄──────────────────user interaction─────────────┘  │
│  │ • psiphon-cli/   │
│  │ • wireguard-cli/ │
│  └──────────────────┘
│         │
│         │ uses
│         ▼
│  ┌──────────────────┐
│  │ daemon/          │
│  │ daemon.py        │
│  └──────────────────┘
│         │
│         │ provides
│         ▼
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                System (Linux)                              │   │
│  │  ┌────────────┐  ┌─────────────┐  ┌─────────────────────┐  │   │
│  │  │ D-Bus      │  │ systemd     │  │ network namespaces  │  │   │
│  │  │ daemon     │  │ service     │  │ / TUN devices       │  │   │
│  │  └────────────┘  └─────────────┘  └─────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Class Diagram

Key classes and their relationships.

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                          libvpnmanager (core)                            ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  ┌─────────────────────────────────────────────────────────────────┐    ║
║  │                          TunnelManager                          │    ║
║  ├─────────────────────────────────────────────────────────────────┤    ║
║  │ - routing: RoutingStrategy                                      │    ║
║  │ - session_manager: SessionManager                               │    ║
║  │ - _adapters: Dict[Tuple[str, str], VPNAdapter]                  │    ║
║  │ - tunnels: Dict[str, Tunnel]                                    │    ║
║  │ - _lock: asyncio.Lock                                           │    ║
║  ├─────────────────────────────────────────────────────────────────┤    ║
║  │ + create_tunnel(config, username) → Tunnel                      │    ║
║  │ + connect_tunnel(name, username) → Tunnel                       │    ║
║  │ + disconnect_tunnel(name, username) → None                      │    ║
║  │ + destroy_tunnel(name, username) → None                         │    ║
║  │ + list_tunnels(username, all_users) → List[Tunnel]              │    ║
║  │ + get_adapter_capabilities(adapter) → AdapterCapabilities       │    ║
║  │ + shutdown() → None                                             │    ║
║  │                                                                 │    ║
║  │ # _get_adapter_for_tunnel(type, session, user) → VPNAdapter    │    ║
║  └─────────────────────────────────────────────────────────────────┘    ║
║                              △ aggregates                                ║
║                              │                                           ║
║  ┌───────────────────────────┴────────────────────────────────────────┐ ║
║  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐│ ║
║  │  │ NetworkName-    │  │   Session-      │  │   D-Bus Service     ││ ║
║  │  │   spaceRouting  │  │   Manager       │  │                     ││ ║
║  │  ├─────────────────┤  ├─────────────────┤  ├─────────────────────┤│ ║
║  │  │ + create_ctx()  │  │ + load_session()│  │ + start_service()   ││ ║
║  │  │ + destroy_ctx() │  │ + save_session()│  │                     ││ ║
║  │  │                 │  │ + list_sessions()│  │ [exposes Tunnel-    ││ ║
║  │  │ [creates netns, │  │                 │  │  Manager interface] ││ ║
║  │  │  moves devices] │  │                 │  │                     ││ ║
║  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘│ ║
║  │         △                      △                                    ║
║  │         │ uses                 │ uses                               ║
║  │         ▼                      ▼                                    ║
║  └────────┼──────────────────────┼────────────────────────────────────┘ ║
║           │                      │                                     ║
║  ┌────────▼──────────────────────▼────────────────────────────────────┐ ║
║  │                        VPNAdapter (ABC)                            ║
║  ├────────────────────────────────────────────────────────────────────┤ ║
║  │ + connect(config, progress_cb) → Tunnel                           ║
║  │ + disconnect(tunnel) → None                                        ║
║  │ + get_status(tunnel) → TunnelStatus                                ║
║  │ + get_traffic_stats(tunnel) → Tuple[int, int]                      ║
║  │ + cleanup() → None                                                 ║
║  │ + capabilities → AdapterCapabilities                               ║
║  └────────────────────────────────────────────────────────────────────┘ ║
║                              △                                           ║
║                              │ implements                               ║
║  ┌───────────────────────────┴────────────────────────────────────────┐ ║
║  │                     Adapter Implementations                        ║
║  │  (in separate packages: proton-vpn-adapter, etc.)                ║
║  └────────────────────────────────────────────────────────────────────┘ ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────┐
│                     Session (ABC) - in libvpnmanager                   │
├─────────────────────────────────────────────────────────────────────────┤
│ + adapter_type: str                                                   │
│ + session_name: str                                                   │
│ + username: str                                                       │
│ + created_at: datetime                                                │
│ + expires_at: Optional[datetime]                                      │
├─────────────────────────────────────────────────────────────────────────┤
│ # _save_credentials() → Dict[str, Any]  (abstract)                   │
│ # _load_credentials(data) → None       (abstract)                    │
├─────────────────────────────────────────────────────────────────────────┤
│ + to_dict() → Dict[str, Any]                                          │
│ + is_expired() → bool                                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                △
                                │ extends
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼────────┐  ┌───────────▼─────────┐  ┌────────▼──────────┐
│ ProtonSession  │  │  PsiphonSession     │  │ WireGuardSession  │
├─────────────────┤  ├─────────────────────┤  ├───────────────────┤
│ + access_token  │  │ + credentials       │  │ + private_key     │
│ + refresh_token │  │ + obfuscation_opt  │  │ + psk             │
│ + server_id     │  │ + ...               │  │ + ...             │
├─────────────────┤  ├─────────────────────┤  ├───────────────────┤
│ # _save_creds() │  │ # _save_creds()     │  │ # _save_creds()   │
│ # _load_creds() │  │ # _load_creds()     │  │ # _load_creds()   │
└─────────────────┘  └─────────────────────┘  └───────────────────┘
```

---

## Sequence Diagrams

### 1. Tunnel Creation Flow

```
User                          CLI (protonvpn)              D-Bus                    Daemon (TunnelManager)              Adapter (ProtonVPNAdapter)
 ── protonvpn tunnel create ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────>
                              │                            │                         │                                   │
                              │ parse args → ProtonConnConfig │                    │                                   │
                              │─────────────────────────────►│                         │                                   │
                              │                            │ Manager.CreateTunnel(config)│                                   │
                              │                            ├─────────────────────────►│                                   │
                              │                            │                         │ create_tunnel(config, user)        │
                              │                            │                         ├──────────────────────────────────►│
                              │                            │                         │                                   │ get_or_create_adapter("proton", session)
                              │                            │                         │                                   ├──────────────────►
                              │                            │                         │                                   │
                              │                            │                         │◄──────────────────────────────────┤ return adapter
                              │                            │                         │                                   │
                              │                            │                         │ adapter.validate_config()         │
                              │                            │                         ├──────────────────────────────────►│
                              │                            │                         │                                   │
                              │                            │                         │◄──────────────────────────────────┤ validated
                              │                            │                         │                                   │
                              │                            │                         │ store tunnel in registry          │
                              │                            │                         ├──────────────────────────────────►│
                              │                            │                         │                                   │
                              │                            │                         │◄──────────────────────────────────┤
                              │                            │                         │                                   │
                              │                            │                         │ return Tunnel(name=..., status=DISCONNECTED)
                              │                            │                         ├──────────────────────────────────►│
                              │                            │                         │                                   │
                              │                            │◄─────────────────────────┤                                   │
                              │                            │  returns tunnel_name      │                                   │
                              │◄───────────────────────────┤                           │                                   │
                              │  "Tunnel 'myvpn' created"  │                           │                                   │
                              │                            │                           │                                   │
 ── protonvpn tunnel connect myvpn ────────────────────────────────────────────────────────────────────────────────────────────────────────────>
                              │                            │                         │                                   │
                              │                            │ Manager.ConnectTunnel(name)│                                   │
                              │                            ├─────────────────────────►│                                   │
                              │                            │                         │ connect_tunnel(name, user)        │
                              │                            │                         ├──────────────────────────────────►│
                              │                            │                         │                                   │ get_adapter for (proton, session)
                              │                            │                         │                                   ├──────────────────►
                              │                            │                         │                                   │
                              │                            │                         │◄──────────────────────────────────┤ return adapter
                              │                            │                         │                                   │
                              │                            │                         │ connected_tunnel = await         │
                              │                            │                         │   adapter.connect(config)         │
                              │                            │                         ├──────────────────────────────────►│                   │
                              │                            │                         │                                   │
                              │                            │                         │      ┌────────────────────────┐   │                   │
                              │                            │                         │      │ Proton VPN API Call   │   │                   │
                              │                            │                         │      │ (establish TUN dev)   │   │                   │
                              │                            │                         │      └────────────────────────┘   │                   │
                              │                            │                         │                                   │
                              │                            │                         │◄──────────────────────────────────┤ return Tunnel(device="tun0")
                              │                            │                         │                                   │
                              │                            │                         │ routing.create_tunnel_context()  │
                              │                            │                         ├──────────────────────────────────►│
                              │                            │                         │                                   │ create namespace, move device
                              │                            │                         │                                   │
                              │                            │                         │◄──────────────────────────────────┤ namespace created
                              │                            │                         │                                   │
                              │                            │                         │ return connected tunnel          │
                              │                            │                         ├──────────────────────────────────►│
                              │                            │                         │                                   │
                              │                            │◄─────────────────────────┤                                   │
                              │◄───────────────────────────┤  success                 │                                   │
                              │  "Connected to @fastest"   │                           │                                   │
                              │                            │                           │                                   │
```

### 2. Traffic Stats Query

```
User                CLI               D-Bus                 Daemon                      Adapter
 ── protonvpn tunnel stats myvpn ────────────────────────────────────────────────────────────────────────>
                      │                 │                     │                           │
                      │                 │ Manager.GetStats(name)│                           │
                      │                 ├─────────────────────►│                           │
                      │                 │                     │ get_traffic_stats(name)    │
                      │                 │                     ├──────────────────────────►│
                      │                 │                     │                           │ adapter.get_traffic_stats(tunnel)
                      │                 │                     │                           ├──────────────────►
                      │                 │                     │                           │
                      │                 │                     │◄──────────────────────────┤ return (bytes_in, bytes_out)
                      │                 │                     │                           │
                      │                 │◄─────────────────────┤                           │
                      │◄────────────────┤ stats: 1.2GB/3.4GB  │                           │
                      │  "1.2 GB in, 3.4 GB out"│                     │                           │
```

---

## Class Diagram (Detailed)

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                              libvpnmanager (Core)                             ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐  ║
║  │  Tunnel                                                               │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ + name: str                                                           │  ║
║  │ + adapter: str                                                        │  ║
║  │ + session_name: str                                                   │  ║
║  │ + username: str                                                       │  ║
║  │ + device: str                                                         │  ║
║  │ + namespace: Optional[str]                                            │  ║
║  │ + endpoint: Optional[str]                                             │  ║
║  │ + connected_at: Optional[datetime]                                    │  ║
║  │ + bytes_in: int                                                       │  ║
║  │ + bytes_out: int                                                      │  ║
║  │ + metadata: Dict[str, Any]                                            │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐  ║
║  │  ConnectionConfig (ABC)                                               │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ + tunnel_name: str                                                    │  ║
║  │ + adapter: str                                                        │  ║
║  │ + session_name: str                                                   │  ║
║  │ + username: str                                                       │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ # to_dict() → Dict[str, Any]     (abstract)                          │  ║
║  │ @classmethod                                                   │  ║
║  │   from_dict(data) → Config         (abstract)                        │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                              △                                               ║
║                              │ implements                                   ║
║        ┌─────────────────────┼─────────────────────┐                         ║
║        │                     │                     │                         ║
║  ┌─────▼──────────┐  ┌───────▼─────────┐  ┌───────▼──────────┐              ║
║  │ ProtonConn-    │  │ PsiphonConn-    │  │ WireGuardConn-   │              ║
║  │   figuration   │  │   figuration    │  │   figuration     │              ║
║  ├─────────────────┤  ├─────────────────┤  ├──────────────────┤              ║
║  │ + server: str   │  │ + host: str     │  │ + interface: str │              ║
║  │ + protocol: str │  │ + port: int     │  │ + peers: List    │              ║
║  │ + ...           │  │ + ...           │  │ + ...            │              ║
║  └─────────────────┘  └─────────────────┘  └──────────────────┘              ║
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐  ║
║  │  TunnelStatus (Enum)                                                  │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ DISCONNECTED, CONNECTING, CONNECTED, DISCONNECTING, ERROR             │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐  ║
║  │  AdapterCapabilities (dataclass)                                      │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ + multi_tunnel: bool                                                  │  ║
║  │ + supports_protocols: List[str]                                       │  ║
║  │ + max_tunnels: Optional[int]                                          │  ║
║  │ + supports_per_app_routing: bool                                      │  ║
║  │ + supports_kill_switch: bool                                          │  ║
║  │ + supports_dns_isolation: bool                                        │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐  ║
║  │  VPNAdapter (ABC)                                                     │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ + connect(config, progress_cb) → Tunnel                   (abstract)   ║
║  │ + disconnect(tunnel) → None                               (abstract)   ║
║  │ + get_status(tunnel) → TunnelStatus                      (abstract)   ║
║  │ + get_traffic_stats(tunnel) → Tuple[int, int]            (abstract)   ║
║  │ + cleanup() → None                                        (abstract)   ║
║  │ + capabilities → AdapterCapabilities                     (property)   ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                              △                                               ║
║                              │ implements                                   ║
║        ┌─────────────────────┼─────────────────────┐                         ║
║        │                     │                     │                         ║
║  ┌─────▼──────────┐  ┌───────▼─────────┐  ┌───────▼──────────┐              ║
║  │ ProtonVPN-     │  │ PsiphonAdapter  │  │ WireGuardAdapter │              ║
║  │   Adapter      │  │                 │  │                  │              ║
║  ├─────────────────┤  ├─────────────────┤  ├──────────────────┤              ║
║  │ + api: ProtonAPI│  │ + client: ...   │  │ + wg: WireGuard  │              ║
║  │                │  │                 │  │                  │              ║
║  │ async connect()│  │ async connect() │  │ async connect()  │              ║
║  │ async disconn()│  │ async disconn() │  │ async disconn()  │              ║
║  │ async status() │  │ async status()  │  │ async status()   │              ║
║  └─────────────────┘  └─────────────────┘  └──────────────────┘              ║
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐  ║
║  │  Session (ABC)                                                        │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ + adapter_type: str                                                   │  ║
║  │ + session_name: str                                                   │  ║
║  │ + username: str                                                       │  ║
║  │ + created_at: datetime                                                │  ║
║  │ + expires_at: Optional[datetime]                                      │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ # _save_credentials() → Dict[str, Any]       (abstract)              │  ║
║  │ # _load_credentials(data) → None             (abstract)               │  ║
║  │ + to_dict() → Dict[str, Any]                                         │  ║
║  │ + is_expired() → bool                                                 │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                              △                                               ║
║                              │ extends                                     ║
║        ┌─────────────────────┼─────────────────────┐                         ║
║        │                     │                     │                         ║
║  ┌─────▼──────────┐  ┌───────▼─────────┐  ┌───────▼──────────┐              ║
║  │ ProtonSession  │  │ PsiphonSession  │  │ WireGuardSession │              ║
║  ├─────────────────┤  ├─────────────────┤  ├──────────────────┤              ║
║  │ + access_token  │  │ + credentials   │  │ + private_key    │              ║
║  │ + refresh_token │  │ + obfuscation_opt│ │ + psk            │              ║
║  │ + server_id     │  │ + ...           │  │ + ...            │              ║
║  └─────────────────┘  └─────────────────┘  └──────────────────┘              ║
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐  ║
║  │  SessionManager                                                       │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ - _sessions: Dict[str, Session]                                        │  ║
║  │ - _lock: asyncio.Lock                                                 │  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │ + load_session(adapter, name, username) → Session                     │  ║
║  │ + save_session(session) → None                                        │  ║
║  │ + delete_session(adapter, name, username) → None                      │  ║
║  │ + list_sessions(username) → List[SessionInfo]                         │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

┌───────────────────────────────────────────────────────────────────────────────┐
│                          proton-vpn-adapter Package                          │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐      │
│  │  ProtonVPNAdapter(VPNAdapter)                                      │      │
│  ├─────────────────────────────────────────────────────────────────────┤      │
│  │  Depends: libvpnmanager, proton-vpn-api-core                       │      │
│  │                                                                     │      │
│  │  async connect(config, progress_cb) → Tunnel                       │      │
│  │    - Load ProtonSession from session_manager                       │      │
│  │    - Initialize ProtonVPNAPI()                                      │      │
│  │    - api.login(session.credentials)                                │      │
│  │    - connection = api.connect(server, protocol, tunnel_name)       │      │
│  │    - Monitor connection, call progress_cb                          │      │
│  │    - return Tunnel(device=connection.tun)                          │      │
│  │                                                                     │      │
│  │  async disconnect(tunnel) → None                                   │      │
│  │    - api.disconnect_tunnel(tunnel.name)                            │      │
│  │                                                                     │      │
│  │  async get_status(tunnel) → TunnelStatus                           │      │
│  │    - connection = api.get_connection(tunnel.name)                  │      │
│  │    - return connection.status                                      │      │      │
│  │                                                                     │      │
│  │  async get_traffic_stats(tunnel) → (in, out)                       │      │
│  │    - connection = api.get_connection(tunnel.name)                  │      │
│  │    - return (connection.bytes_in, connection.bytes_out)            │      │
│  │                                                                     │      │
│  │  async cleanup() → None                                            │      │
│  │    - if api: api.logout()                                          │      │
│  └─────────────────────────────────────────────────────────────────────┘      │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐      │
│  │  ProtonSession(Session)                                            │      │
│  ├─────────────────────────────────────────────────────────────────────┤      │
│  │  + access_token: str                                               │      │
│  │  + refresh_token: str                                              │      │
│  │  + server_id: Optional[str]                                        │      │
│  │  + client_id: str                                                  │      │
│  │                                                                     │      │
│  │  # _save_credentials() → Dict[str, Any]                            │      │
│  │    - Return {'access_token': ..., 'refresh_token': ...}            │      │
│  │                                                                     │      │
│  │  # _load_credentials(data) → None                                  │      │
│  │    - self.access_token = data['access_token']                      │      │
│  │    - self.refresh_token = data['refresh_token']                    │      │
│  │                                                                     │      │
│  │  + is_expired() → bool                                             │      │
│  │    - Check if access_token is expired (via API or timestamp)       │      │
│  └─────────────────────────────────────────────────────────────────────┘      │
│                                                                               │
│  [pyproject.toml]                                                             │
│  name = "proton-vpn-adapter"                                                 │
│  dependencies = ["libvpnmanager", "proton-vpn-api-core"]                     │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Diagram

Runtime view of the system.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Linux System                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                          System Daemons                             │    │
│  │  ┌─────────────────┐                ┌────────────────────────┐     │    │
│  │  │   dbus-daemon    │◄──────────────►│  systemd-journald      │     │    │
│  │  │   (Session Bus) │                │                        │     │    │
│  │  └─────────────────┘                └────────────────────────┘     │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │ D-Bus                                  │
│                                   │                                        │
│  ┌────────────────────────────────▼────────────────────────────────────┐   │
│  │                    proton-vpn-manager Service                      │   │
│  │  [Systemd Service Type=dbus, BusName=org.protonvpn.Manager]       │   │
│  │                                                                    │   │
│  │  ┌────────────────────────────────────────────────────────────┐   │   │
│  │  │                   Daemon Process                          │   │   │
│  │  │  ┌──────────────────────────────────────────────────────┐  │   │   │
│  │  │  │              TunnelManager (singleton)              │  │   │   │
│  │  │  │  • Manages all tunnels (dict: name → Tunnel)       │  │   │   │
│  │  │  │  • Adapter registry (dict: (type,session) → Adapter)│  │   │   │
│  │  │  │  • Auth/perm checking                               │  │   │   │
│  │  │  └─────────────────────────┬──────────────────────────┘  │   │   │
│  │  │                            │ delegates                   │   │   │
│  │  │  ┌─────────────────────────▼──────────────────────────┐  │   │   │
│  │  │  │         Adapter Manager (in TunnelManager)         │  │   │   │
│  │  │  │  • Loads adapters from config                      │  │   │   │
│  │  │  │  • Caches adapter instances                        │  │   │   │
│  │  │  │  • Routes tunnel requests to correct adapter       │  │   │   │
│  │  │  └──────────────┬──────────────┬───────────────┬──────┘  │   │   │
│  │  │                 │              │               │          │   │   │
│  │  │          ┌──────▼─────┐ ┌────▼─────┐ ┌──────▼─────┐    │   │   │
│  │  │          │ ProtonVPN   │ │ Psiphon  │ │ WireGuard   │    │   │   │
│  │  │          │ Adapter     │ │ Adapter  │ │ Adapter     │    │   │   │
│  │  │          │ (from       │ │ (from    │ │ (from       │    │   │   │
│  │  │          │  proton-vpn-│ │  psiphon-│ │  wireguard- │    │   │   │
│  │  │          │  adapter    │ │  adapter │ │  adapter    │    │   │   │
│  │  │          │  package)   │ │  package)│ │  package)   │    │   │   │
│  │  │          └──────┬─────┘ └────┬─────┘ └──────┬─────┘    │   │   │
│  │  │                 │              │               │          │   │   │
│  │  │          ┌──────▼──────────────▼──────────────▼─────┐    │   │   │
│  │  │          │        External VPN Service APIs         │    │   │   │
│  │  │          │  • proton-vpn-api-core (Proton)          │    │   │   │
│  │  │          │  • psiphon Python wrapper                │    │   │   │
│  │  │          │  • wireguard-tools / pyroute2            │    │   │   │
│  │  │          └──────────────────────────────────────────┘    │   │   │
│  │  │                                                          │   │   │
│  │  │  ┌─────────────────────────────────────────────────────┐ │   │   │
│  │  │  │           Network Namespace Manager                │ │   │   │
│  │  │  │  (NetworkNamespaceRouting)                        │ │   │   │
│  │  │  │  • ip netns add/delete/move                       │ │   │   │
│  │  │  │  • TUN device setup                               │ │   │   │
│  │  │  │  • Routing/DNS configuration                     │ │   │   │
│  │  │  └─────────────────────────────────────────────────────┘ │   │   │
│  │  │                                                          │   │   │
│  │  │  ┌─────────────────────────────────────────────────────┐ │   │   │
│  │  │  │           SessionManager                            │ │   │   │
│  │  │  │  • Load/save sessions from /var/lib/protonvpn     │ │   │   │
│  │  │  │  • Session credential storage per user            │ │   │   │
│  │  │  └─────────────────────────────────────────────────────┘ │   │   │
│  │  │                                                          │   │   │
│  │  │  ┌─────────────────────────────────────────────────────┐ │   │   │
│  │  │  │           D-Bus Service Exporter                   │ │   │   │
│  │  │  │  • org.protonvpn.Manager interface                 │ │   │   │
│  │  │  │  • Methods: CreateTunnel, Connect, Disconnect      │ │   │   │
│  │  │  │  • Signals: TunnelAdded, TunnelRemoved, Status     │ │   │   │
│  │  │  └─────────────────────────────────────────────────────┘ │   │   │
│  │  └──────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      CLI Processes                               │   │
│  │  ┌─────────────┐              ┌─────────────┐                   │   │
│  │  │ protonvpn   │              │ psiphon-cli │                   │   │
│  │  │ (user space)│              │ (user space)│                   │   │
│  │  ├─────────────┤              ├─────────────┤                   │   │
│  │  │ • D-Bus     │              │ • D-Bus     │                   │   │
│  │  │   client    │              │   client    │                   │   │
│  │  │ • Uses      │              │ • Uses      │                   │   │
│  │  │   proton-   │              │   psiphon-  │                   │   │
│  │  │   vpn-      │              │   adapter   │                   │   │
│  │  │   adapter   │              │   types     │                   │   │
│  │  └─────────────┘              └─────────────┘                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Kernel/System Level                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │   │
│  │  │ Network      │  │ TUN/TAP      │  │ iptables/nftables    │ │   │
│  │  │ Namespaces   │  │ devices      │  │                      │ │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Deployment Diagram

How components are deployed across systems.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                User's Laptop                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  User Shell ($)                                                    │    │
│  │  ┌───────────────────────────────────────────────────────────────┐ │    │
│  │  │ $ protonvpn tunnel create --server @fastest                 │ │    │
│  │  └───────────────────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                   │                                        │
│                                   ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  protonvpn CLI (standalone binary or pip package)                │    │
│  │  ┌───────────────────────────────────────────────────────────────┐ │    │
│  │  │ 1. Parse arguments                                            │ │    │
│  │  │ 2. Import: from proton_vpn_adapter import ProtonConnConfig    │ │    │
│  │  │ 3. Import: from libvpnmanager.dbus.client import get_client   │ │    │
│  │  │ 4. Connect to D-Bus: bus = await get_client()                │ │    │
│  │  │ 5. Call: bus.create_tunnel(config, username)                 │ │    │
│  │  └───────────────────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                   │                                        │
│                                   │ D-Bus (session or system)            │
│                                   │                                        │
│  ┌────────────────────────────────▼─────────────────────────────────────┐│ │
│  │  System daemon: proton-vpn-manager (running as root)               ││ │
│  │  ┌───────────────────────────────────────────────────────────────┐││ │
│  │  │ from libvpnmanager import TunnelManager                       │││ │
│  │  │ from proton_vpn_adapter import ProtonVPNAdapter              │││ │
│  │  │ from wireguard_adapter import WireGuardAdapter               │││ │
│  │  │                                                                │││ │
│  │  │ manager = TunnelManager(NetworkNamespaceRouting())           │││ │
│  │  │ manager.register_adapter(ProtonVPNAdapter())                │││ │
│  │  │ manager.register_adapter(WireGuardAdapter())                │││ │
│  │  │                                                                │││ │
│  │  │ # Start D-Bus service on org.protonvpn.Manager               │││ │
│  │  │ await start_service(manager)                                 │││ │
│  │  └───────────────────────────────────────────────────────────────┘││ │
│  └─────────────────────────────────────────────────────────────────────┘│ │
│                                   │                                        │
│                                   │ calls                                 │
│                                   ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐│ │
│  │  External Service: Proton VPN API                                 ││ │
│  │  ┌───────────────────────────────────────────────────────────────┐││ │
│  │  │ e.g., api.protonvpn.com/vpn/v1/...                         │││ │
│  │  └───────────────────────────────────────────────────────────────┘││ │
│  └─────────────────────────────────────────────────────────────────────┘│ │
│                                                                         │ │
│  ┌─────────────────────────────────────────────────────────────────────┐│ │
│  │  External Service: WireGuard (local config files)                ││ │
│  │  └───────────────────────────────────────────────────────────────┘││ │
│  └─────────────────────────────────────────────────────────────────────┘│ │
│                                                                         │ │
│  ┌─────────────────────────────────────────────────────────────────────┐│ │
│  │  Linux Kernel (network namespace, TUN, routing)                 ││ │
│  │  ┌─────────────┐         ┌─────────────┐                        ││ │
│  │  │ ns1 (proton) │         │ ns2 (wireguard)│                       ││ │
│  │  │ - tun0       │         │ - wg0        │                        ││ │
│  │  │ - routes     │         │ - routes     │                        ││ │
│  │  │ - resolv.conf │         │ - resolv.conf│                        ││ │
│  │  └─────────────┘         └─────────────┘                        ││ │
│  └─────────────────────────────────────────────────────────────────────┘│ │
│                                                                         │ │
└─────────────────────────────────────────────────────────────────────────┘ │
                                                                             │
┌─────────────────────────────────────────────────────────────────────────────┘
```

---

## Adapter Class Hierarchy

```
libvpnmanager.adapters.base
│
├── VPNAdapter (ABC)
│   ├── async connect(config, progress_cb) → Tunnel
│   ├── async disconnect(tunnel) → None
│   ├── async get_status(tunnel) → TunnelStatus
│   ├── async get_traffic_stats(tunnel) → (int, int)
│   ├── async cleanup() → None
│   └── capabilities (property) → AdapterCapabilities
│
└── AdapterCapabilities (dataclass)
    ├── multi_tunnel: bool
    ├── supports_protocols: List[str]
    ├── max_tunnels: Optional[int]
    ├── supports_per_app_routing: bool
    ├── supports_kill_switch: bool
    └── supports_dns_isolation: bool

────────────────────────────────────────────────────────────────────────────

proton-vpn-adapter.adapter
│
├── ProtonVPNAdapter(VPNAdapter)
│   ├── __init__(session_manager)
│   ├── async connect(config, progress_cb) → Tunnel
│   │   └─> Uses ProtonVPNAPI from proton-vpn-api-core
│   ├── async disconnect(tunnel) → None
│   ├── async get_status(tunnel) → TunnelStatus
│   ├── async get_traffic_stats(tunnel) → (int, int)
│   ├── async cleanup() → None
│   └── capabilities → AdapterCapabilities(
│        multi_tunnel=True,
│        supports_protocols=["wireguard", "openvpn-udp", "openvpn-tcp"],
│        supports_kill_switch=True,
│        supports_dns_isolation=True
│   )
│
└── ProtonSession(Session)  [from sessions.proton]
    ├── adapter_type = "proton"
    ├── access_token: str
    ├── refresh_token: str
    ├── server_id: Optional[str]
    ├── client_id: str
    ├── # _save_credentials() → Dict
    ├── # _load_credentials(data) → None
    ├── is_expired() → bool
    └── to_dict() / from_dict()

────────────────────────────────────────────────────────────────────────────

wireguard-adapter.adapter
│
├── WireGuardAdapter(VPNAdapter)
│   ├── __init__(session_manager)
│   ├── async connect(config, progress_cb) → Tunnel
│   │   └─> wg-quick up /wg set ... (via subprocess or pyroute2)
│   ├── async disconnect(tunnel) → None
│   ├── async get_status(tunnel) → TunnelStatus
│   ├── async get_traffic_stats(tunnel) → (int, int)
│   ├── async cleanup() → None
│   └── capabilities → AdapterCapabilities(
│        multi_tunnel=True,
│        supports_protocols=["wireguard"],
│        supports_kill_switch=False,
│        supports_dns_isolation=False
│   )
│
└── WireGuardSession(Session)
    ├── adapter_type = "wireguard"
    ├── private_key: str
    ├── psk: Optional[str]
    ├── endpoint: str
    ├── allowed_ips: List[str]
    ├── # _save_credentials() → Dict
    └── # _load_credentials(data) → None
```

---

## Package Dependencies Graph

```
                    ┌─────────────────────┐
                    │   python-stdlib     │
                    └──────────┬──────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
           ┌────▼────┐  ┌────▼─────┐  ┌────▼─────┐
           │  Pydantic│  │ Async-   │  │ pyroute2 │
           │          │  │ stdlib   │  │          │
           └────┬────┘  └────┬─────┘  └────┬─────┘
                │              │              │
                └──────────────┼──────────────┘
                               ▼
                    ┌─────────────────────┐
                    │  libvpnmanager      │
                    │  (core)              │
                    │  No service-specific│
                    │  deps!               │
                    └──────────┬──────────┘
                               │ depends on
                ┌──────────────┼──────────────┐
                │              │              │
           ┌────▼──────────┐  │  ┌──────────▼──────────┐
           │ proton-vpn-   │  │  │ psiphon-adapter     │
           │ adapter       │  │  │ (or others)         │
           ├───────────────┤  │  ├─────────────────────┤
           │ depends on:   │  │  │ depends on:         │
           │ - libvpnmgr   │  │  │ - libvpnmgr         │
           │ - proton-vpn- │  │  │ - psiphon lib       │
           │   api-core    │  │  └─────────────────────┘
           └───────────────┘  │
                              │
                       ┌──────▼──────────┐
                       │ protonvpn CLI   │
                       ├─────────────────┤
                       │ depends on:     │
                       │ - libvpnmgr     │
                       │ - proton-vpn-   │
                       │   adapter       │
                       │ - click, etc.   │
                       └─────────────────┘
```

---

## Key Design Principles

1. **Dependency Inversion**: High-level `TunnelManager` depends on `VPNAdapter` abstraction, not concrete adapters
2. **Single Responsibility**:
   - Core: Tunnel lifecycle + routing
   - Adapter: Service-specific connection logic
   - CLI: User interface
   - Daemon: System integration
3. **Open/Closed**: New adapters can be added without modifying core
4. **Liskov Substitution**: Any `VPNAdapter` can be used by `TunnelManager`
5. **Interface Segregation**: Clean ABCs with minimal required methods
6. **Composition over Inheritance**: TunnelManager composes with adapters, doesn't subclass

---

## Glossary

- **Adapter**: Bridge between core manager and a specific VPN service (Proton, Psiphon, etc.)
- **Session**: Persisted credentials/tokens for a VPN service, per user
- **Routing Strategy**: Pluggable network isolation (currently only NetworkNamespace)
- **D-Bus**: Inter-process communication mechanism, daemon exposes service here
- **Tunnel**: VPN connection instance with name, device, namespace, etc.
