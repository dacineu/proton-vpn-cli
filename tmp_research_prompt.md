# Research Phase 4: Polish, Security & Compatibility

**Status:** Research in progress
**Started:** 2025-03-21

---

## Research Objective

Answer: "What do I need to know to PLAN Phase 4 well?"

**Phase:** Polish, Security & Compatibility
**Requirements to address:** COMP-01, COMP-02, SEC-01, SEC-02, SEC-03, TST-01, TST-02, TST-03, DOC-01, DOC-02, DOC-03

---

## Research Areas

### 1. Unix Socket Security Hardening

**Key questions:**
- How to ensure socket file permissions are set correctly before bind()?
- What are the security guarantees of `SO_PEERCRED`? Can it be spoofed?
- How to prevent credential leakage via `/proc/<pid>/environ` when passing via stdin?
- How to test socket permissions from within Python tests?

**Action:** Investigate Python's `socket` module, `os.fchmod`, `SO_PEERCRED` socket option, and test strategies for verifying permissions.

---

### 2. Backward Compatibility (D-Bus API Forwarding)

**Key questions:**
- How to structure legacy D-Bus methods to internally use the new adapter flow?
- Should legacy methods block until adapter is ready? What timeouts?
- How to map adapter errors to legacy D-Bus error names?
- How to test that legacy API produces identical results to new API?

**Action:** Research D-Bus method forwarding patterns, asyncio-based waiting for adapter spawn, error code mapping strategies.

---

### 3. Integration Testing Strategy

**Key questions:**
- How to write pytest fixtures that spawn MTM daemon and adapter for tests?
- How to simulate adapter crashes? (kill -9, segfault)
- How to test concurrent CLI connections? (pytest-xdist or asyncio tasks)
- Should tests use real Proton credentials or mock the Proton API?
- How to test namespace creation without root privileges? (user namespaces? sudo? mocks?)

**Action:** Investigate pytest-asyncio, fixture patterns for daemon lifecycle, mocking vs integration tradeoffs, Linux namespace testing.

---

### 4. TOTP Encryption on Channels

**Key questions:**
- How to derive a cryptographically strong key from a 6-digit TOTP (30 bits of entropy)?
  - Options: pad to 16 bytes with PBKDF2? Use directly with XOR? Reject due to weak entropy?
- Should encryption be per-message or per-session? How to handle TOTP rotation every 30s?
- What cipher? AES-GCM? ChaCha20-Poly1305? Or simple XOR? (threat model dictates)
- Performance: is per-request encryption/decryption acceptable in asyncio?
- Protocol framing: encrypt entire JSON? field-by-field? prefix-length + ciphertext?

**Action:** Research lightweight encryption patterns for local IPC, key derivation from low-entropy secrets, threat model analysis for local vs remote attackers.

---

### 5. Credential Sanitation in Python

**Key questions:**
- How to reliably zero a `bytes` or `bytearray` in Python? (bytearray is mutable, bytes is not)
- Does `bytearray[:] = b'\x00'` actually overwrite in memory? Or can Python optimize away?
- Should we use `ctypes.memset` or `memoryview` for aggressive clearing?
- Can secrets leak via Python's GC? How to prevent copies?
- How to test that buffer is zeroed? (read memory? not possible from user space)
- Should we use `mlock()` to prevent swap? (requires `CAP_IPC_LOCK` or root)

**Action:** Research Python memory management, `ctypes` memset, `bytearray` guarantees, testing sanitation (heuristic: check source code patterns, not runtime verification).

---

### 6. Legacy D-Bus API Details

**Action:** Review existing dbus/service.py to understand current legacy method signatures and their expected behavior. Plan forwarding implementation that preserves exact behavior (including error codes and side effects).

---

### 7. Documentation Structure

**Action:** Outline structure for:
- `docs/ARCHITECTURE.md` (component diagram, sequence flows, security model)
- `docs/user/MIGRATION.md` (session persistence removal, 2FA mandatory, TOTP encryption, breaking changes)
- `docs/developer/ADAPTER_GUIDE.md` (checklist, protocol specs, testing, debugging)
- `docs/developer/TESTING.md` (test strategy, fixtures, running tests)
- `docs/INDEX.md` (navigation hub linking to all docs)
- `README.md` updates: installation, quickstart, link to full docs

---

### 8. Validation Architecture (Nyquist Dimension 8)

For each requirement, define verifiable test:

| Req | Verification Strategy |
|-----|----------------------|
| COMP-01 | Integration test: after adapter spawn, `os.stat(sock_path).st_mode & 0o777 == 0o600` |
| COMP-02 | Integration test: call legacy `CreateTunnel` with no adapter running; assert adapter auto-starts and tunnel created; compare result to new API call |
| SEC-01 | Same as COMP-01 (socket permissions) |
| SEC-02 | Test: spawn adapter with known secret in stdin; read `/proc/<pid>/environ`; assert secret not present; check that credential buffer overwritten after read |
| SEC-03 | Test: attempt connection to control socket from unauthorized process (different UID); expect `PermissionError` or `ConnectionRefused` |
| SEC-04 | Test: verify TOTP secret stored in keyring is encrypted (libsecret schema), not plaintext; keyring entry label/schema |
| SEC-05 | Unit test: `MTM.verify_2fa(code)` returns True/False; test ±1 time step acceptance |
| SEC-06 | Integration test: CLI→MTM and CLI→Adapter requests with invalid TOTP rejected; valid TOTP accepted |
| SEC-07 | Integration test: adapter receives totp_secret via stdin, verifies on CLI request, test rejection of invalid code |
| SEC-08 | Integration test: adapter→MTM control messages include totp_code, MTM validates before processing |
| SEC-09 | Documentation test: `docs/user/SETUP_2FA.md` exists and explains backup code storage, QR display, recovery |
| SEC-10 | Unit test: TOTP validator with clock skew ±90 seconds; accept codes within window |
| TST-01 | Integration test: full flow end-to-end (CLI → MTM → adapter → namespace → tunnel success) |
| TST-02 | Integration test: `kill -9` adapter during active tunnel; verify MTM detects, cleans namespace within timeout |
| TST-03 | Integration test: multiple concurrent CLI tasks (asyncio.gather) creating tunnels; verify isolation, no cross-talk |
| TST-04 | Verify `tests/integration/dummy_adapter.py` exists and implements minimal adapter |
| DOC-01 | Check `docs/ARCHITECTURE.md` exists and covers adapter lifecycle, communication channels, security model |
| DOC-02 | Check `docs/user/MIGRATION.md` exists and explains session persistence removal, credential flow changes, 2FA requirement |
| DOC-03 | Check `docs/developer/ADAPTER_GUIDE.md` exists with implementation checklist, protocol specs, testing strategy |

**Nyquist Validation Template:** Create `.planning/phases/04-polish-security-compatibility/04-VALIDATION.md` with these test cases, each with:
- Test name
- Verification method (manual/integration/unit)
- Expected outcome
- Commands to run (if manual)

---

## Output Format

Write findings under these headings:

1. **Unix Socket Security** — concrete recommendations, code snippets for socket setup, verification approach
2. **Backward Compatibility** — forwarding pattern code structure, error mapping, test strategy
3. **Integration Testing** — pytest fixture patterns, test layout (tests/integration/), mocking strategy, concurrency approach
4. **TOTP Encryption** — threat model conclusion (is encryption needed? local attacker vs remote), key derivation scheme, protocol changes, fallback behavior
5. **Credential Sanitation** — code patterns for zeroing, memory-safety tips, limitations of Python security
6. **Legacy API Implementation** — pseudocode for forwarding, session token handling, edge cases
7. **Documentation Plan** — file structure, content outline for each doc, cross-references
8. **Validation Architecture** — specific test cases for each requirement, manual verification steps, commands

**Include for each recommendation:**
- Why (rationale)
- How (concrete implementation)
- Risks if not done
- Trade-offs considered

---

## Signal Completion with:

```
## RESEARCH COMPLETE

Summary of findings:
- [Key recommendation 1]
- [Key recommendation 2]
- ...
- Validation Architecture: defined N test criteria for Nyquist

Ready for planning.
```
