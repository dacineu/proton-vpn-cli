<planning_context>
**Phase:** 1
**Mode:** standard

<files_to_read>
- .planning/STATE.md (Project State)
- .planning/ROADMAP.md (Roadmap)
- .planning/REQUIREMENTS.md (Requirements)
- .planning/phases/01-foundation/1-CONTEXT.md (USER DECISIONS from /gsd:discuss-phase)
- .planning/phases/01-foundation/1-RESEARCH.md (Technical Research)
</files_to_read>

**Phase requirement IDs (every ID MUST appear in a plan's `requirements` field):** DAEM-01, DAEM-02, ADPT-01, ADPT-02, ADPT-03, ADPT-06, CLI-01, CLI-02, TST-04, SEC-04, SEC-05, SEC-06, SEC-07

**Project instructions:** Read ./CLAUDE.md if exists — follow project-specific guidelines
**Project skills:** Check .claude/skills/ or .agents/skills/ directory (if either exists) — read SKILL.md files, plans should account for project skill rules
</planning_context>

<downstream_consumer>
Output consumed by /gsd:execute-phase. Plans need:
- Frontmatter (wave, depends_on, files_modified, autonomous)
- Tasks in XML format with read_first and acceptance_criteria fields (MANDATORY on every task)
- Verification criteria
- must_haves for goal-backward verification
</downstream_consumer>

<deep_work_rules>
## Anti-Shallow Execution Rules (MANDATORY)

Every task MUST include these fields — they are NOT optional:

1. **`<read_first>`** — Files the executor MUST read before touching anything. Always include:
   - The file being modified (so executor sees current state, not assumptions)
   - Any "source of truth" file referenced in CONTEXT.md (reference implementations, existing patterns, config files, schemas)
   - Any file whose patterns, signatures, types, or conventions must be replicated or respected

2. **`<acceptance_criteria>`** — Verifiable conditions that prove the task was done correctly. Rules:
   - Every criterion must be checkable with grep, file read, test command, or CLI output
   - NEVER use subjective language ("looks correct", "properly configured", "consistent with")
   - ALWAYS include exact strings, patterns, values, or command outputs that must be present
   - Examples:
     - Code: `auth.py contains def verify_token(` / `test_auth.py exits 0`
     - Config: `.env.example contains DATABASE_URL=` / `Dockerfile contains HEALTHCHECK`
     - Docs: `README.md contains '## Installation'` / `API.md lists all endpoints`
     - Infra: `deploy.yml has rollback step` / `docker-compose.yml has healthcheck for db`

3. **`<action>`** — Must include CONCRETE values, not references. Rules:
   - NEVER say "align X with Y", "match X to Y", "update to be consistent" without specifying the exact target state
   - ALWAYS include the actual values: config keys, function signatures, SQL statements, class names, import paths, env vars, etc.
   - If CONTEXT.md has a comparison table or expected values, copy them into the action verbatim
   - The executor should be able to complete the task from the action text alone, without needing to read CONTEXT.md or reference files (read_first is for verification, not discovery)

**Why this matters:** Executor agents work from the plan text. Vague instructions like "update the config to match production" produce shallow one-line changes. Concrete instructions like "add DATABASE_URL=postgresql://... , set POOL_SIZE=20, add REDIS_URL=redis://..." produce complete work. The cost of verbose plans is far less than the cost of re-doing shallow execution.
</deep_work_rules>

<quality_gate>
- [ ] PLAN.md files created in phase directory
- [ ] Each plan has valid frontmatter
- [ ] Tasks are specific and actionable
- [ ] Every task has `<read_first>` with at least the file being modified
- [ ] Every task has `<acceptance_criteria>` with grep-verifiable conditions
- [ ] Every `<action>` contains concrete values (no "align X with Y" without specifying what)
- [ ] Dependencies correctly identified
- [ ] Waves assigned for parallel execution
- [ ] must_haves derived from phase goal
</quality_gate>

<objective>
Create detailed implementation plans for Phase 1 that cover all 19 requirements (DAEM-01, DAEM-02, ADPT-01, ADPT-02, ADPT-03, ADPT-06, CLI-01, CLI-02, TST-04, SEC-04, SEC-05, SEC-06, SEC-07). The phase goal: "Establish the fundamental adapter process pattern with dual Unix sockets and control protocol; deliver a working Dummy adapter that demonstrates the basic flow without real VPN operations." Success criteria: 1) Adapter startup works, 2) Dummy tunnel creation, 3) Concurrent connections, 4) Token authentication works (with dummy tokens).

Use the research in 1-RESEARCH.md to inform concrete implementation steps. Break work into 4-8 plans with 3-10 tasks each. Tasks must be executable with clear actions and verifiable acceptance criteria.

Key deliverables from ROADMAP:
- `daemon/daemon.py`: `AdapterProcess` class, `StartAdapter()` D-Bus method, `ListAdapters()`, basic adapter_pool tracking, session token handling
- `adapters/dummy/cli.py` (new): dual-server pattern, stdin credential reading, Register to MTM, dummy CreateTunnel handler, session token validation
- `libvpnmanager/client.py`: `start_adapter()`, `AdapterClient` with JSON-RPC, session token propagation
- Integration smoke test using Dummy adapter with token validation

Plans should be organized by functional area or component, with clear dependencies. Wave 1: Core infrastructure (registry extensions, token store). Wave 2: Adapter standalone executable. Wave 3: Client extensions. Wave 4: Integration tests and legacy compatibility.
</objective>

<output>
Write multiple PLAN.md files to: .planning/phases/01-foundation/

Use naming: `01-<topic>-PLAN.md` (e.g., `01-daemon-extensions-PLAN.md`, `02-dummy-adapter-PLAN.md`, `03-client-extensions-PLAN.md`, `04-integration-testing-PLAN.md`)

Each PLAN.md must include:
- Frontmatter with: `wave`, `depends_on` (list of plan numbers or empty), `files_modified` (list of file paths), `autonomous` (bool, typically false for Phase 1)
- Objective/summary
- Tasks in XML format: `<task id="N"><description>...</description><read_first>...</read_first><action>...</action><acceptance_criteria>...</acceptance_criteria></task>`
- Verification section: how to verify plan completion (commands to run, grep checks)
- must_haves: list of must-have items for phase success derived from phase goal

Do NOT create SUMMARY.md files — those are created after execution.
</output>
