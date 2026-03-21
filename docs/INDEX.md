# Documentation Index

Welcome! This index organizes the documentation for the Multi-Tunnel Adapter Architecture project.

---

## User-Facing Documentation

These documents explain the system from an end-user perspective.

- **[Architecture Overview](user/OVERVIEW.md)** — High-level explanation of how the system works, key concepts (adapters, MTM daemon, tunnels), and what changed in v1.0.
- **[Migration Guide](MIGRATION.md)** — Transitioning from the old architecture to the new: session persistence removal, TOTP security layer, and compatibility notes.

## Developer Documentation

These documents provide implementation details, protocol specifications, and testing guidance.

- **[Adapter Implementation Guide](developer/ADAPTER_IMPLEMENTATION_GUIDE.md)** — Step-by-step guide for building a new VPN adapter: dual-server pattern, control protocol, namespace allocation, crash handling, and TOTP integration.
- **[Protocol Specifications](developer/PROTOCOL_SPECS.md)** — Detailed wire formats, message structures, and state machines for CLI↔Adapter, Adapter↔MTM, and CLI↔MTM channels.
- **[Testing Strategies](developer/TESTING_STRATEGIES.md)** — How to write unit tests, integration tests, and system tests; test fixtures; mocking strategies.

## Reference Designs

Original design documents (for historical context and detailed rationale).

- [NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md](../NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md) — Complete specification with component diagram, communication channels, and flow examples.
- [ADAPTER_INTEGRATION.md](../ADAPTER_INTEGRATION.md) — Proton adapter integration details and daemon changes for multi-tunnel support.
- [DBUS_SECURITY_AND_ARCHITECTURE.md](../DBUS_SECURITY_AND_ARCHITECTURE.md) — D-Bus security model and legacy API design.
- [MULTIUSER_MULTIADAPTER_DESIGN.md](../MULTIUSER_MULTIADAPTER_DESIGN.md) — Multi-user and multi-adapter considerations.

---

*Last updated: 2025-03-21*
