<objective>
Research how to implement Phase 1: Foundation — Adapter Lifecycle & Core Protocol. Answer: "What do I need to know to PLAN this phase well?"
</objective>

<files_to_read>
- .planning/phases/01-foundation/1-CONTEXT.md (USER DECISIONS from /gsd:discuss-phase)
- .planning/REQUIREMENTS.md (Project requirements)
- .planning/STATE.md (Project decisions and history)
</files_to_read>

<additional_context>
**Phase description:** Establish the fundamental adapter process pattern with dual Unix sockets and control protocol; deliver a working Dummy adapter that demonstrates the basic flow without real VPN operations.

**Phase requirement IDs (MUST address):** DAEM-01, DAEM-02, ADPT-01, ADPT-02, ADPT-03, ADPT-06, CLI-01, CLI-02, TST-04, SEC-04, SEC-05, SEC-06, SEC-07

**Project instructions:** Read ./CLAUDE.md if exists — follow project-specific guidelines
**Project skills:** Check .claude/skills/ or .agents/skills/ directory (if either exists) — read SKILL.md files, research should account for project skill patterns

**Key decisions from CONTEXT.md:**
- Socket paths: /run/mtm/adapters/{username}_{adapter_type}.sock and /run/mtm/control/{username}_{adapter_type}.sock
- NDJSON control protocol with SO_PEERCRED verification
- Dummy adapter behavior: realistic simulation, varying devices, AllocateTunnel flow even if mocked
- Adapter lifecycle: StartAdapter, adapter_pool keyed by (adapter_type, vpn_username), spawn flow
- Token model: session token (not per-request TOTP in Phase 1), MTM validates TOTP before spawn
- Credential handling: stdin transport, zeroization after VPN login

**Existing codebase (to be read by agent):**
- multi-tunnel-namespace/src/daemon/daemon.py — existing D-Bus daemon
- multi-tunnel-namespace/src/libvpnmanager/adapters/base.py — adapter base class
- multi-tunnel-namespace/src/daemon/adapter_registry.py — adapter discovery
- multi-tunnel-namespace/src/daemon/resource_allocator.py — namespace allocation
- multi-tunnel-namespace/src/libvpnmanager/client.py — client library
- multi-tunnel-namespace/src/adapters/dummy/ — existing dummy adapter
</additional_context>

<output>
Write to: .planning/phases/01-foundation/1-RESEARCH.md
</output>
