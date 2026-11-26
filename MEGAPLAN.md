# Plan Auditor Megaplan

Date: 2026-11-26
Branch: `dev`
Status: proposed implementation roadmap
Audience: maintainer, contributors, and AI coding agents implementing the work

This is an offline, self-contained improvement plan for `plan-auditor`. It is intentionally explicit enough that a future coding session can implement a phase without rediscovering the repository architecture.

---

## 1. Executive summary

`plan-auditor` already has the hard parts of a serious verification system:

- deterministic behavioral checks;
- sealed, monotonically strengthened verification contracts;
- host-owned request contracts;
- hash-chained and HMAC-authenticated evidence;
- a fail-closed completion gate;
- multi-plan and multi-agent concepts;
- STRIPS/PDDL-style formal planning support;
- extensive CI, release provenance, mutation testing, documentation tests, and a 100 percent coverage floor.

The highest-value work is no longer generic hardening. The project now needs convergence:

1. **Make every documented success path actually pass in a clean environment.**
2. **Make the first-use experience simple enough that people reach the trusted workflow.**
3. **Turn the documented isolation threat model into an executable deployment.**
4. **Reduce architectural and static-analysis debt without weakening the security invariants.**
5. **Expose evidence and schemas in forms other tools can consume.**

The recommended order is:

- **Milestone M1:** fix trust-critical documentation and Windows output defects.
- **Milestone M2:** build onboarding and host-install automation.
- **Milestone M3:** build portable isolation and a reference trusted deployment.
- **Milestone M4:** stabilize public contracts, schemas, and package architecture.
- **Milestone M5:** burn down static-analysis debt and simplify maintenance.
- **Milestone M6:** build ecosystem integrations and evidence export formats.

Do not start large refactors before M1. The project's central claim is proof; the documented proof path must itself be reproducible first.

---

## 2. Non-negotiable invariants

These rules outrank every roadmap item.

1. **No LLM output can create PASS.** LLM output may only propose additional deterministic checks or withhold completion.
2. **`scripts/audit_check.py` remains the only component that marks a step verified.** A refactor may move code, but not diffuse this authority.
3. **`supervisor/gate.py` remains the only component that emits final PASS/FAIL/UNKNOWN.** A refactor may move code, but not diffuse this authority.
4. **Behavioral evidence is mandatory.** `run`, `exec`, or `pytest` must be present; `file_exists` and `regex` can never verify alone.
5. **Fail closed.** Missing, malformed, unknown, stale, unsigned, or ambiguous critical state never becomes PASS.
6. **Criteria can only strengthen after sealing.** Never permit silent weakening, deletion, or scope expansion.
7. **No runtime dependencies.** Keep `dependencies = []` in `pyproject.toml`. Development-only dependencies are acceptable when they are clearly not runtime requirements.
8. **Evidence remains append-only.** Existing records must not be edited or reordered.
9. **Secrets never enter the repository or evidence.** HMAC keys stay outside the workspace. Traffic evidence must not store raw secrets or raw request bodies.
10. **Documentation claims must be reproducible.** If a command transcript cannot be executed in CI, mark it illustrative and do not present it as proof.

---

## 3. Current defects and findings driving this plan

### 3.1 The quickstart contradicts the authenticated-evidence gate

`docs/quickstart.md` presents this sequence as a passing flow:

```bash
plan-auditor request init . --file request-source.json
plan-auditor plan verify .
plan-auditor run . 1
plan-auditor audit .
```

It omits HMAC key generation and `plan-auditor integrity init .`. In a clean reproduction, the deterministic checks pass but the integrated audit exits `2` with the expected failure:

```text
RESULT: audit FAILED - evidence is not authenticated: 3 active evidence record(s) are unsigned because no PLAN_AUDITOR_HMAC_KEY or PLAN_AUDITOR_HMAC_KEY_FILE is configured
```

The README has the correct HMAC instructions; `docs/quickstart.md` is stale. This is a trust-critical documentation bug because the project exists to eliminate confident but false completion narratives.

### 3.2 Windows output can crash

On Windows with a cp1252 stdout encoding, running:

```powershell
plan-auditor doctor .
```

in this repository can terminate with:

```text
UnicodeEncodeError: 'charmap' codec can't encode character ...
```

The immediate cause is non-ASCII output being printed through a stream whose default encoding cannot represent it. The repository's own self-audit plan contains Turkish text, so this is not hypothetical. The CLI also mixes Turkish strings such as `CONFIG HATASI` and `HATA` with English output.

### 3.3 The traffic subsystem is exposed but undocumented

The CLI exposes:

```text
plan-auditor traffic --start/--stop/--status/--report/--verify/--install-ca/--remove-ca
```

This subsystem runs a loopback HTTPS proxy, manages a local certificate authority, classifies outbound traffic, and feeds the completion gate. No Markdown documentation currently explains it. That is a serious gap because installing and trusting a local CA is security-sensitive operator behavior even when the implementation is careful.

### 3.4 Advertised LLM tiers are not fully wired

The architecture documents tiers for no LLM, small local LLM, strong local LLM, and remote LLM. The configuration supports a tier value. The strict orchestrator, however, calls `run_adversarial_review()` without an LLM client, so only deterministic static adversarial checks run. Either the tiers need implementation or the documentation needs to say they are design directions rather than current capabilities.

### 3.5 Static-analysis debt is explicitly baselined

The ratchet baselines currently record:

- 861 Ruff findings;
- 434 mypy findings.

The ratchet correctly prevents new debt, but the existing debt remains large. Much of the Ruff debt appears mechanical (`UP006`, `UP045`, `UP031`). The mypy debt includes many `no-untyped-call` and `no-untyped-def` findings.

### 3.6 Packaging uses a collision-prone top-level module name

The wheel ships `supervisor` and `scripts` as top-level Python packages. `scripts` is especially collision-prone in shared Python environments. The project already namespaces skill assets as `plan_auditor_skill`, but the implementation packages themselves remain generic.

### 3.7 The deterministic core is becoming a monolith

`scripts/audit_check.py` is approximately 2,269 lines with about 85 top-level functions. It contains schema validation, execution, evidence handling, snapshot/rollback, output bounding, workspace fingerprinting, and CLI behavior. The conceptual architecture is layered, but the core implementation is concentrated in one file.

### 3.8 Regression-test organization is hard to navigate

The suite is extensive, but many files are date-suffixed incident or hardening matrices. Out of 142 top-level test files, 86 have date suffixes. The coverage is valuable; the organization makes ownership and refactoring harder.

### 3.9 Manual onboarding is too difficult

The current operator must understand and manually coordinate:

- plan JSON;
- request JSON;
- behavioral checks;
- HMAC key generation and placement;
- environment variables;
- skill installation paths;
- host-specific hooks;
- activation, sealing, execution, integrity initialization, and audit ordering.

This is correct for a trust-sensitive system but too much for first use. The setup should be automated without hiding security decisions.

### 3.10 Isolation is documented but not turnkey

The deployment-isolation documentation is honest and technically sound. It explains distinct supervisor, agent, and check-execution identities. But the strong deployment is mostly an operator-assembled Linux configuration. Windows/macOS have no equivalent implementation, and containerized reference deployment is not provided.

---

## 4. Target end state

A successful implementation of this megaplan produces the following experience.

### 4.1 New user experience

```bash
pipx install plan-auditor
cd my-project
plan-auditor init . --host auto
plan-auditor doctor .
```

`init` should:

1. detect the project and supported agent hosts;
2. create a safe template plan/request pair or explain what the operator must write;
3. generate or configure an external HMAC key with correct permissions;
4. install host hooks only after explicit consent;
5. print a short next-command sequence;
6. never write key material into the workspace;
7. support `--dry-run` and `--json`.

The operator still owns requirements. Automation may scaffold them, but must not silently invent acceptance criteria.

### 4.2 Verification experience

```bash
plan-auditor request init . --file request-source.json
plan-auditor plan verify .
plan-auditor run .
plan-auditor integrity init .
plan-auditor audit .
```

Every documented quickstart variant runs this order or explains a deliberate deviation. The same flow works on Linux, macOS, and Windows with no encoding crash.

### 4.3 Trusted deployment experience

A reference deployment can be started with one documented command, for example:

```bash
plan-auditor isolate up .
plan-auditor isolate audit .
plan-auditor isolate down .
```

or with a checked-in container compose file when a CLI abstraction is not appropriate.

It establishes separate identities for:

- trusted supervisor;
- untrusted implementing agent;
- untrusted check execution.

The HMAC key is visible only to the supervisor identity. Behavioral checks execute without key access. Evidence is written or authenticated by the supervisor after checks complete.

### 4.4 Integration experience

Downstream tools can consume stable machine contracts:

- versioned JSON Schemas for plans, requests, evidence records, gate results, and traffic reports;
- signed/exported evidence bundles;
- optional SARIF/JUnit/HTML output for CI and code-review systems;
- stable command behavior documented in a hosted documentation site.

---

## 5. Milestone roadmap

| Milestone | Goal | Main outcome | Suggested size |
|---|---|---|---|
| M1 | Trust-critical correctness | Docs match reality; Windows output does not crash; traffic is documented | Small |
| M2 | Adoption | `init`, key bootstrap, host installer, hosted docs | Medium |
| M3 | Isolation | Container/reference trusted deployment with integration tests | Large |
| M4 | Contracts and architecture | Versioned schemas, safer package namespace, split core | Large |
| M5 | Maintainability | Ruff/mypy burn-down, test organization, benchmark harness | Medium/continuous |
| M6 | Ecosystem | Export formats, host-specific plugins, optional LLM-tier implementation | Medium/large |

M1 is prerequisite for everything. M2 and M3 can overlap if different contributors exist. M4 should not begin until the public behavior fixed in M1 and M2 is stable.

---

## 6. Milestone M1 - trust-critical correctness

### Task M1.1: Make one canonical quickstart

**Problem:** README and `docs/quickstart.md` disagree about whether HMAC initialization is required.

**Implementation:**

1. Decide that the README quickstart and `docs/quickstart.md` use the exact same command sequence.
2. Include these steps in order:
   - activate request;
   - seal plan;
   - run step(s);
   - generate an external HMAC key;
   - configure `PLAN_AUDITOR_HMAC_KEY_FILE`;
   - run `plan-auditor integrity init .`;
   - run `plan-auditor audit .`.
3. Show Bash and PowerShell forms for environment-variable setup.
4. Avoid opaque shell magic where possible. Prefer a documented Python one-liner only until `plan-auditor init` exists.
5. Make clear whether `run` must happen before `integrity init`, or whether `integrity init` re-authenticates existing records. The test must prove the documented order.
6. Remove the statement that the quickstart is verified only "in pieces" or replace it with an exact statement of what CI executes.

**Tests:**

- Extract commands from the quickstart and execute them in a clean temporary workspace.
- Scrub `PLAN_AUDITOR_HMAC_KEY` and `PLAN_AUDITOR_HMAC_KEY_FILE` initially.
- Assert the pre-integrity audit fails nonzero.
- Assert the post-integrity audit exits `0`.
- Run the same test on Linux and Windows CI.

**Acceptance criteria:**

- A user can copy the quickstart into a clean shell and reach exit `0`.
- The docs never show keyless evidence as a passing completion proof.
- The quickstart contains Windows-compatible instructions.

**Primary files:**

- `README.md`
- `docs/quickstart.md`
- `tests/test_readme_quickstart.py`
- `tests/test_doc_transcripts.py`
- `tests/test_docs_metadata.py`

---

### Task M1.2: Fix Unicode-safe output

**Problem:** JSON/prose output can crash on cp1252 Windows consoles.

**Implementation options, in preferred order:**

1. **ASCII-safe machine JSON:** use `ensure_ascii=True` for JSON printed to stdout. JSON Unicode escapes are semantically equivalent and remain machine-parseable.
2. **Safe stdout/stderr wrapper:** at CLI entrypoint, reconfigure stdout and stderr with `errors="backslashreplace"` when the stream supports `reconfigure`.
3. **Central output helper:** route all CLI output through a helper that never raises `UnicodeEncodeError`.

Recommended implementation:

- use ASCII-safe JSON for machine output;
- use `backslashreplace` for human prose and subprocess output tails;
- do not mutate global stdout deep inside library functions; configure it once at entrypoints.

**Tests:**

- Add a test invoking `plan-auditor doctor` in a workspace whose plan/request contains Turkish or other non-ASCII text while stdout uses cp1252.
- If direct encoding control is difficult cross-platform, test the output helper with a cp1252 `TextIOWrapper`.
- Assert exit behavior is determined by the audit result, not by an encoding exception.

**Acceptance criteria:**

- `plan-auditor doctor .` never crashes solely because stdout cannot encode a character.
- JSON output remains valid JSON.
- No `\ufffd` replacement corruption appears in stored evidence because of terminal encoding.

**Primary files:**

- `supervisor/cli.py`
- `scripts/audit_check.py`
- `tests/test_cli*.py`
- new focused encoding regression test

---

### Task M1.3: Standardize human-facing CLI language

**Problem:** the CLI mixes Turkish and English in output.

**Implementation:**

1. Inventory user-facing strings in `scripts/audit_check.py` and `supervisor/cli.py`.
2. Convert unexpected Turkish strings to English.
3. Keep machine output unchanged except where the current text is documented.
4. Update transcripts that intentionally capture output.
5. If localization is desired later, design it explicitly rather than mixing languages incidentally.

**Acceptance criteria:**

- English documentation matches English CLI output.
- Tests do not depend on accidental language fragments.
- A future localization design has a single string table or explicit boundary.

**Primary files:**

- `scripts/audit_check.py`
- `tests/test_doc_transcripts.py`
- tests that assert exact human output

---

### Task M1.4: Document the traffic subsystem before expanding it

**Problem:** security-sensitive traffic capture is exposed but undocumented.

**Documentation content required:**

1. What the subsystem does and does not prove.
2. How the loopback HTTPS proxy works at a high level.
3. Exactly when a local CA is generated.
4. What `--install-ca` changes on Linux, macOS, and Windows.
5. What `--remove-ca` removes and what it cannot remove.
6. Where CA material lives and what permissions are required.
7. What data enters evidence:
   - host, method, path, payload hash, byte count, classification;
   - no raw body;
   - sensitive headers are not stored raw;
   - secret hits are masked and fingerprinted.
8. What a `SILENT` outcome means and why silence is not proof.
9. How to declare a traffic contract in a plan.
10. How to interpret `OK`, `INCOMPLETE`, `VIOLATION`, `TAMPERED`, `UNVERIFIED`, and `NOT_CONFIGURED`.
11. Operator consent warnings for CA installation.
12. Failure modes and troubleshooting.

**Implementation:**

- create `docs/traffic.md`;
- add it under Security or Concepts in `mkdocs.yml`;
- add a CLI reference section;
- extend docs metadata tests to enforce bidirectional coverage: every public CLI command must appear in CLI docs;
- mark the feature experimental if it is not yet considered stable.

**Acceptance criteria:**

- `traffic` appears in user-facing docs with security warnings.
- Every `--install-ca` and `--remove-ca` behavior has a documented platform matrix.
- No user discovers CA installation only through `--help`.

**Primary files:**

- `docs/traffic.md`
- `docs/cli.md`
- `docs/threat-model.md`
- `mkdocs.yml`
- `tests/test_docs_metadata.py`

---

## 7. Milestone M2 - adoption and onboarding

### Task M2.1: Add `plan-auditor init`

**Goal:** replace a multi-page manual setup with one safe bootstrap command.

**Proposed interface:**

```bash
plan-auditor init . \
  --host auto \
  --profile standard \
  --mode serial \
  --create-key \
  --install-hooks
```

Useful variants:

```bash
plan-auditor init . --dry-run
plan-auditor init . --json
plan-auditor init . --no-install-hooks
plan-auditor init . --template python-pytest
```

**Behavior:**

1. Verify Python version and platform support.
2. Inspect the workspace without modifying it.
3. Detect existing `.plan-auditor` state and refuse destructive overwrite.
4. Create a template `.plan-auditor/plan.json` only when requested or when no plan exists.
5. Create `request-source.json` only as a template; the operator must edit and activate it.
6. Generate a strong random key outside the workspace when `--create-key` is passed.
7. Set restrictive permissions:
   - POSIX: `0600` key file and secure parent directories;
   - Windows: ACL the file to the current trusted user where practical.
8. Print export instructions or write no environment state silently.
9. Detect host skill directories but do not install hooks unless explicitly requested.
10. Emit machine-readable output with `json` when requested.

**Important trust rule:** `init` may scaffold requirements, but must not silently treat generated requirements as user-approved. Activation remains an explicit operator action.

**Acceptance criteria:**

- A clean Python project can be scaffolded in under five minutes.
- No key material appears inside the workspace.
- Re-running `init` is idempotent and non-destructive.
- `--dry-run` writes nothing.
- `--json` output is stable enough for host automation.

**Primary files:**

- `supervisor/cli.py`
- new `supervisor/bootstrap.py`
- tests under `tests/test_bootstrap*.py`
- `docs/quickstart.md`
- `docs/cli.md`

---

### Task M2.2: Add host installation automation

**Goal:** remove manual copying of skill files and hooks.

**Proposed command:**

```bash
plan-auditor install-skill --host claude --scope user
plan-auditor install-skill --host codex --scope project --dir .
plan-auditor install-skill --host opencode --dry-run
```

**Behavior:**

1. Locate skill assets inside the installed wheel under `plan_auditor_skill`.
2. Detect host-specific installation directories.
3. Copy or symlink files according to platform and user preference.
4. Install hook configuration only when the host format is known.
5. Back up existing files before replacement.
6. Print exact paths changed.
7. Support `--uninstall` later, but do not implement uninstall before install is correct.

**Security rules:**

- Never overwrite a user hook silently.
- Never modify host settings outside the requested scope without explicit consent.
- Show hook command before installing it.

**Acceptance criteria:**

- Claude Code, Codex CLI, OpenCode, and Command Code have documented supported paths.
- Unsupported host produces a clear nonzero result.
- Existing custom hooks are preserved or refused, not overwritten silently.

---

### Task M2.3: Improve key management

**Goal:** make correct key placement the easy path.

**Near-term implementation:**

1. `plan-auditor integrity keygen --out ~/.plan-auditor/plan-auditor-hmac.key`.
2. Refuse output inside the workspace.
3. Refuse insecure existing permissions when strict mode is requested.
4. Print shell-specific environment setup instructions.
5. Never print key bytes.

**Later implementation:**

- OS keychain integration through optional development/install extras or a plugin boundary;
- hardware-backed or cloud KMS integration only after the local threat model is stable.

**Acceptance criteria:**

- README and quickstart no longer require users to write Python key-generation one-liners.
- Wrong key location and weak permissions fail with actionable messages.
- Tests prove key material is not logged.

---

### Task M2.4: Publish the documentation site and clarify canonical repository ownership

**Implementation:**

1. Deploy MkDocs to GitHub Pages or another versioned docs host.
2. Add docs deployment to release workflow, not every PR unless previewing is cheap.
3. Decide whether the canonical repository is `Furox-Art/plan-auditor`, `theCosmicCrafter/plan-auditor`, or a mirror relationship.
4. Update `mkdocs.yml`, package metadata, badges, issue links, and docs links consistently.
5. If both repositories remain, document which one receives issues and which one publishes releases.

**Acceptance criteria:**

- The docs site URL appears in package metadata.
- Users do not need to read raw Markdown on GitHub for normal documentation.
- Repository ownership is unambiguous.

---

## 8. Milestone M3 - executable isolation

### Task M3.1: Design the trusted deployment architecture

**Required roles:**

1. **Supervisor identity**
   - owns HMAC key;
   - owns final audit;
   - writes/authenticates evidence;
   - runs trusted Plan Auditor installation.
2. **Agent identity**
   - writes only the intended product workspace;
   - cannot read key material;
   - cannot modify supervisor executable or control-plane policy.
3. **Check identity**
   - executes behavioral checks;
   - has no HMAC key;
   - ideally has restricted network and resource limits;
   - reports result artifacts back to the supervisor.

**Core design decision:** decide whether checks communicate results through:

- exit code plus bounded stdout/stderr captured by supervisor;
- a checked result artifact in a shared scratch area;
- a local supervisor service API.

Start with exit code plus bounded output because it matches the existing deterministic core.

**Acceptance criteria:**

- A diagram and exact trust-boundary table exist in `docs/deployment-isolation.md`.
- Every writable mount is labeled owner, reader, writer, and trust level.
- The design states what a hostile agent can and cannot do.

---

### Task M3.2: Provide a containerized reference implementation

**Goal:** convert the manual Linux deployment into a reproducible reference.

**Implementation:**

1. Add `deploy/isolated/` with a compose or equivalent container definition.
2. Build separate images or one image launched with separate users/configuration.
3. Mount the product workspace with least privilege.
4. Mount HMAC key only into the supervisor container.
5. Run check execution without key access.
6. Optionally disable network access for the check container by default.
7. Add a smoke test that:
   - starts the reference deployment;
   - runs a known passing plan;
   - verifies audit PASS;
   - confirms the check container cannot read the key;
   - attempts workspace evidence tampering and verifies detection.

**Important limitation:** containers are not automatically a complete security boundary. Document kernel/shared-host limitations honestly.

**Acceptance criteria:**

- A maintainer can run the reference deployment with one or two commands.
- CI runs at least a smoke test where the container runtime is available.
- Failure to establish isolation fails closed.

---

### Task M3.3: Add a portable isolation command layer only if it simplifies the reference deployment

Possible interface:

```bash
plan-auditor isolate up .
plan-auditor isolate audit .
plan-auditor isolate down .
```

Do not build this abstraction merely to hide compose. Build it only if it adds real validation, lifecycle management, or cross-platform behavior.

**Acceptance criteria:**

- The command never silently falls back to same-user execution when isolation was requested.
- Unsupported platform returns nonzero with a clear explanation.
- The compose/reference path remains visible and debuggable.

---

### Task M3.4: Harden traffic capture as part of the isolation story

**Implementation:**

1. Document whether the traffic proxy runs in the supervisor identity, agent identity, or a fourth observer identity.
2. Threat-model CA private-key access.
3. Add lifecycle tests proving CA removal is best-effort and verified.
4. Document network policy interaction: traffic observation is not network enforcement.
5. Consider integrating allowed-host egress policy with container network controls rather than only observational traffic evidence.

**Acceptance criteria:**

- Traffic observation has an explicit trust boundary.
- CA install/remove behavior is tested or clearly marked manual.
- Users understand observation is not enforcement.

---

## 9. Milestone M4 - public contracts and architecture

### Task M4.1: Publish versioned machine-readable schemas

**Goal:** make plans, requests, evidence, and gate output consumable by other tools without importing Python implementation internals.

**Schemas to add:**

```text
schemas/plan-v4.schema.json
schemas/request-v1.schema.json
schemas/evidence-record-v1.schema.json
schemas/gate-result-v1.schema.json
schemas/traffic-contract-v1.schema.json
schemas/traffic-report-v1.schema.json
```

**Implementation:**

1. Generate initial schemas from current behavior.
2. Add examples that validate against schemas.
3. Add conformance tests using development-only JSON Schema validation.
4. Keep runtime dependency-free; schema validation need not be runtime-required.
5. Document which fields are stable public contract and which are implementation details.
6. Add schema version fields where absent or document why canonical existing fields are sufficient.

**Acceptance criteria:**

- External contributors can validate a plan without reading all of `audit_check.py`.
- Schema changes are versioned and changelogged.
- CI rejects examples that drift from schemas.

---

### Task M4.2: Move implementation out of generic top-level `scripts`

**Goal:** eliminate the collision-prone top-level `scripts` package.

**Target shape:**

```text
plan_auditor/
  core/
  supervisor/
  formal/
  traffic/
  evidence/
```

**Migration strategy:**

1. Create the new package without deleting old entrypoints.
2. Move code in small slices:
   - evidence/integrity primitives;
   - path/workspace confinement;
   - plan schema validation;
   - command execution;
   - snapshot/rollback;
   - audit orchestration.
3. Keep compatibility modules at `scripts` and `supervisor` for one or two minor releases if necessary.
4. Emit deprecation warnings only where they will not break machine output.
5. Update tests to import the new package primarily.
6. Keep the copied Agent Skill workflow working; if hosts expect a literal `scripts/` directory, generate it as a thin compatibility bundle rather than making it the implementation.

**Acceptance criteria:**

- The wheel no longer owns generic top-level implementation modules, or a documented compatibility exception remains with an expiration plan.
- `pip install plan-auditor` cannot collide with unrelated `scripts` packages.
- Existing CLI behavior and exit codes remain unchanged.

---

### Task M4.3: Split the deterministic core by responsibility

**Proposed module boundaries:**

```text
core/schema.py         - plan validation and check-type rules
core/execution.py      - subprocess execution, argv handling, output bounds
core/evidence.py       - append, rotate, verify, authenticate chain
core/workspace.py      - fingerprinting, path confinement, file state
core/snapshot.py       - snapshot and rollback
core/audit.py          - audit orchestration and step state transitions
core/cli.py            - deterministic-core command-line adapter
```

**Rules for the refactor:**

- one behavioral slice per commit;
- no simultaneous feature changes;
- preserve exact exit codes;
- use transcript and hardening tests as regression evidence;
- do not let convenience imports bypass the single authority rules.

**Acceptance criteria:**

- No file exceeds a maintainer-agreed size threshold unless there is a documented reason.
- Core authority remains obvious: one execution path marks steps verified.
- Import graph tests prevent accidental cycles.

---

### Task M4.4: Normalize CLI structure and help output

**Implementation:**

1. Write a CLI style guide:
   - noun-first command groups;
   - consistent `dir` positional behavior;
   - JSON output flags;
   - stable error wording;
   - documented exit codes.
2. Improve `--help` examples for major commands.
3. Avoid overlapping aliases unless intentionally supported.
4. Add tests that every public command is documented and every documented command exists.

**Acceptance criteria:**

- A user can predict command syntax after learning one group.
- Help output includes at least one real example for complex commands.
- Bidirectional docs/CLI coverage is enforced in CI.

---

## 10. Milestone M5 - maintainability and measured quality

### Task M5.1: Burn down Ruff debt

**Current baseline:** 861 findings.

**Order:**

1. `UP006` - modernize type annotations.
2. `UP045` - modernize optional annotations.
3. `UP035` - update deprecated imports.
4. `UP031` - replace printf-style formatting where safe.
5. `I001` - import ordering.
6. `F401`/`F841`/`E741` - small correctness/readability issues.

**Method:**

- one rule or one small group per PR;
- use Ruff autofix only after inspecting unsafe fixes;
- update `.github/baselines/ruff.json` downward;
- never raise the baseline.

**Acceptance criteria:**

- The Ruff baseline trends to zero or to a tiny explicitly justified remainder.
- The quality ratchet still blocks regressions.

---

### Task M5.2: Burn down mypy debt in core-first order

**Current baseline:** 434 findings.

**Order:**

1. `scripts/audit_check.py` and future core modules.
2. `supervisor/gate.py`, `plans.py`, `control_plane.py`, `evidence.py`, `integrity.py`.
3. CLI and daemon boundaries.
4. Traffic and formal-planning modules.
5. Tests last, unless tests hide implementation type errors.

**Method:**

- replace bare `Dict`/`List` with precise generic types;
- introduce typed dictionaries or dataclasses for public JSON contracts;
- avoid scattering casts; centralize parsing/validation so types narrow naturally.

**Acceptance criteria:**

- Core verification modules reach strict or near-strict typing.
- The mypy baseline trends downward every maintenance iteration.
- Public schema boundaries have precise types.

---

### Task M5.3: Reorganize regression tests without losing coverage

**Goal:** keep hardening coverage while making the suite navigable.

**Implementation:**

1. Group tests by subsystem:
   - `tests/core/`
   - `tests/supervisor/`
   - `tests/traffic/`
   - `tests/formal/`
   - `tests/integration/`
   - `tests/regression/`
2. Rename date-suffixed files by behavior where possible.
3. Keep incident dates in comments or test docstrings, not as the primary organization.
4. Deduplicate shared fixtures into `tests/conftest.py` or focused fixture modules.
5. Do not delete regression coverage merely to reduce file count.

**Acceptance criteria:**

- A contributor can find tests by subsystem.
- Coverage remains at the enforced floor.
- Mutation-test signal does not regress in target modules.

---

### Task M5.4: Build a real comparison and performance harness

The documentation correctly says there is no defensible cross-tool comparison table. Build one rather than publishing anecdotes.

**Harness dimensions:**

- false completion detection;
- tamper detection;
- setup time;
- audit runtime overhead;
- false blockage rate;
- operator steps required;
- platform support;
- isolation strength.

**Implementation:**

1. Define 10-20 small tasks with known outcomes.
2. Include tasks with skipped tests, edited tests, fake file existence, evidence tampering, dependency omission, and secret leakage attempts.
3. Run Plan Auditor and selected comparison tools under identical conditions.
4. Publish methodology, limitations, and raw results.

**Acceptance criteria:**

- Every number on the benchmark page is generated by a committed harness.
- No comparative claim exists without methodology and reproducible artifacts.

---

## 11. Milestone M6 - ecosystem and advanced capabilities

### Task M6.1: Evidence export formats

**Goal:** make audit evidence reviewable outside the terminal.

**Candidate formats:**

- self-contained HTML report;
- SARIF for code scanning integrations;
- JUnit XML for CI test reporting;
- JSON bundle conforming to the public schema.

**Implementation notes:**

- include command outputs or tails according to bounded-size rules;
- include chain head, plan hash, seal hash, request hash, workspace fingerprint, and verdict;
- do not include secrets or raw traffic bodies;
- expose exactly how a reviewer verifies the bundle.

**Acceptance criteria:**

- CI can upload a concise audit artifact.
- Reviewers can distinguish deterministic failure from gate/policy failure quickly.
- Export cannot convert FAIL or UNKNOWN into a visually misleading success.

---

### Task M6.2: Decide and implement the LLM-tier boundary

**Decision point:** either implement tiers 2-4 or explicitly document them as future design.

If implementing:

1. Define a provider-neutral client interface.
2. Keep LLM access out of the deterministic verification path.
3. LLM findings can only propose deterministic checks or add withholding findings.
4. Log prompts/responses only with explicit redaction and consent.
5. Support a local backend first; remote APIs later.
6. Do not add runtime dependencies; call external binaries or use stdlib HTTP behind explicit opt-in configuration.

**Acceptance criteria:**

- Tier configuration changes observable behavior or is rejected as unsupported.
- An LLM cannot weaken or bypass deterministic results.
- Documentation exactly matches implementation.

---

### Task M6.3: Improve formal-planning usability

**Implementation:**

1. Add a small end-to-end formal-planning example beyond the fib example.
2. Document when formalization adds value and when it is unnecessary.
3. Surface planner failures with actionable messages.
4. Provide clearer Fast Downward installation/use instructions where supported.
5. Add schema documentation for manual formal contracts.

**Acceptance criteria:**

- A user can compile and verify a multi-step dependency example without reading implementation code.
- Unsupported Fast Downward environments fail with clear instructions.

---

### Task M6.4: Consider an MCP/server integration carefully

A MCP integration could let agent hosts invoke the auditor directly. This is attractive but risky if it creates a second control plane.

**Rules:**

- MCP is an adapter, not a second verifier.
- It must call the same deterministic core and completion gate.
- It must not expose HMAC keys or privileged operations to untrusted clients.
- Tool definitions should expose narrow operations: status, doctor, run-step, audit, verify-evidence.
- Mutating operations such as request activation and hook installation require explicit host/user mediation.

**Acceptance criteria:**

- No behavior is unique to the MCP path.
- Security documentation explains exactly what an untrusted MCP client can do.

---

## 12. Recommended implementation sequence

### Sprint 1 - correctness quick wins

1. M1.2 Unicode-safe output.
2. M1.3 CLI language consistency.
3. M1.1 canonical quickstart.
4. M1.4 traffic documentation skeleton.

Deliverable: users can trust the documented walkthrough and run `doctor` on Windows.

### Sprint 2 - onboarding

1. M2.3 key-generation command.
2. M2.1 `plan-auditor init`.
3. M2.2 host installer.
4. M2.4 docs publishing/canonical links.

Deliverable: first-use setup drops from manual multi-page instructions to a guided bootstrap.

### Sprint 3 - isolation foundation

1. M3.1 trust architecture.
2. M3.2 reference container deployment.
3. M3.4 traffic trust-boundary integration.
4. Optional M3.3 command abstraction.

Deliverable: the hostile-agent deployment is reproducible, not merely described.

### Sprint 4 - public contracts

1. M4.1 schemas.
2. M4.4 CLI normalization.
3. M4.3 core split, first slices only.
4. M4.2 package namespace migration plan and initial compatibility layer.

Deliverable: external tools have stable contracts, and architecture work can proceed safely.

### Ongoing maintenance lane

1. M5.1 Ruff burn-down.
2. M5.2 mypy burn-down.
3. M5.3 test reorganization.
4. M5.4 benchmark harness.

This lane should proceed in small PRs alongside feature milestones.

---

## 13. Dependency and risk map

| Dependency | Risk | Mitigation |
|---|---|---|
| M1 before adoption work | Users follow broken docs while onboarding improves | Fix docs first; do not market until M1 lands |
| Bootstrap before isolation | Easier onboarding increases same-user usage | Make same-user limitation explicit in `init` output |
| Container runtime availability | Not all users/CI have Docker/Podman | Keep manual Linux deployment and document graceful unsupported states |
| Namespace migration | Breaks skill copies and imports | Compatibility layer, staged deprecation, strong import tests |
| Core split | Accidental authority diffusion | Import-graph tests and architecture invariant tests |
| Schema publication | Users depend on unstable internals | Mark implementation-only fields explicitly internal |
| Evidence export | Reports may overstate proof | Export exact gate outcome and machine-verifiable hashes; never imply semantic correctness |
| Traffic docs | Documentation may legitimize risky CA installation | Require explicit consent and document removal/platform limitations |
| LLM tiers | LLM integration weakens trust story | Keep LLM outside verification path; implement only after core boundaries are stable |

---

## 14. Validation matrix

Run the relevant subset for each PR.

### Fast local validation

```bash
python -m pytest tests/ -q
python -m pytest examples/fib/test_fib.py -q
npm test
npm run test:contract
```

### Distribution validation

```bash
python -m pip install .
python -m pytest tests/ -q --cov --cov-report=term-missing
python -m build
python .github/scripts/check_dist_assets.py
```

### Documentation validation

```bash
python -m mkdocs build --strict
python -m pytest tests/test_docs_metadata.py tests/test_readme_quickstart.py tests/test_doc_transcripts.py -q
```

### Self-audit validation

```bash
plan-auditor request init . --file .plan-auditor/request-source.json
python scripts/audit_check.py validate .
plan-auditor plan verify .
plan-auditor audit .
```

### Platform validation

- Linux: primary CI matrix.
- Windows: cp1252/default-console behavior, path behavior, service/ACL documentation.
- macOS: wheel smoke and hook paths.

### Isolation validation

When M3 exists:

```bash
# Exact commands depend on the final implementation.
plan-auditor isolate up .
plan-auditor isolate audit .
plan-auditor isolate down .
```

Required negative tests:

- check identity cannot read HMAC key;
- tampered evidence is detected;
- missing isolation variables fail closed;
- unsupported platform does not silently fall back.

---

## 15. Pull-request slicing guidance

Keep PRs small enough that a failure is diagnosable.

### Good PR sizes

- one documentation correction plus its regression test;
- one encoding fix plus focused tests;
- one Ruff rule burn-down;
- one schema family plus examples;
- one core module extraction;
- one host installer backend;
- one isolation reference deployment layer.

### Bad PR sizes

- "modernize typing and refactor core";
- "add init, install hooks, keygen, docs rewrite";
- "container isolation plus traffic redesign";
- "namespace migration plus behavior changes."

### Required PR evidence

Every PR should state:

1. user-visible behavior before/after;
2. exact validation commands run;
3. whether public contracts changed;
4. whether the threat model changed;
5. whether documentation was regenerated or manually edited;
6. whether the self-audit plan/seal needed host-approved strengthening.

---

## 16. Documentation updates required as work lands

Keep these documents synchronized:

- `README.md` - concise entrypoint, verified quickstart, honest limits.
- `docs/quickstart.md` - same canonical quickstart, more troubleshooting.
- `docs/cli.md` - every public command and exit code.
- `docs/threat-model.md` - every security-sensitive capability and boundary.
- `docs/deployment-isolation.md` - executable reference deployment once available.
- `docs/integrations.md` - generated installer behavior rather than manual copying.
- `docs/traffic.md` - new required page.
- `CONTRIBUTING.md` - development workflow and validation matrix.
- `CHANGELOG.md` - user-visible behavior changes and migration notes.
- `SECURITY.md` - reporting and supported-version policy.

Rule: if docs and implementation disagree, treat it as a bug in whichever one is wrong; do not explain away the mismatch.

---

## 17. Open decisions for the maintainer

These should be answered before large implementation slices.

1. **Canonical repository:** Is `Furox-Art/plan-auditor` the canonical public repo, is `theCosmicCrafter/plan-auditor` canonical, or is one a mirror?
2. **Traffic stability:** Is traffic capture a stable feature, beta feature, or experimental subsystem?
3. **Host priority:** Which agent host matters most first: Claude Code, Codex CLI, OpenCode, Command Code, or another host?
4. **Key storage:** Should the near-term recommended path remain key files, or should OS keychain support be prioritized?
5. **Isolation runtime:** Docker, Podman, or both? Should Windows service isolation be automated before containers?
6. **LLM tiers:** Implement, defer, or remove from current-capability documentation?
7. **Package migration compatibility:** How many minor releases should retain `scripts`/`supervisor` compatibility imports?
8. **Evidence export priority:** HTML first for humans, SARIF first for GitHub/code scanning, or JSON schema bundle first for downstream tooling?
9. **Public API policy:** Are Python imports considered public API, or is the CLI the only stable interface?
10. **Localization:** Should CLI output be English-only, or is a deliberate localization framework desired?

---

## 18. Definition of done for the whole megaplan

The megaplan is complete when all of the following are true:

1. The README and docs quickstart execute end-to-end in clean CI environments on supported platforms.
2. `plan-auditor doctor` and all primary commands never fail because of terminal encoding.
3. Every public CLI command is documented, and every documented command exists.
4. Traffic capture is either documented end-to-end with security warnings or hidden behind an explicit experimental interface.
5. A new user can bootstrap a project and host integration through a guided command without manually copying skill assets.
6. HMAC key generation and permission validation are built-in.
7. A reproducible isolated reference deployment exists and passes negative security tests.
8. Public schemas exist for plans, requests, evidence, gate results, and traffic contracts/reports.
9. The implementation no longer depends on a generic top-level `scripts` package, or a documented compatibility sunset exists.
10. The deterministic core is split into cohesive modules while preserving exact behavior.
11. Ruff and mypy baselines have materially decreased, with core modules approaching strict typing.
12. Tests are organized by subsystem and remain at the required coverage floor.
13. Benchmarks are generated by a committed harness rather than prose.
14. Evidence can be exported in at least one review-friendly format without weakening the verdict semantics.
15. Documentation, package metadata, repository links, and the hosted docs site all agree on the canonical project home.

---

## 19. Immediate next implementation task

The safest first code change is **M1.2 Unicode-safe output** because it is small, independently testable, and fixes a reproduced defect.

Recommended first PR:

1. Change machine JSON output to ASCII-safe JSON or implement a central safe-output helper.
2. Add a cp1252 regression test using non-ASCII plan text.
3. Convert the accidental Turkish CLI strings to English.
4. Update exact-output transcript tests.
5. Do not touch quickstart, traffic, architecture, or packaging in the same PR.

Recommended second PR:

1. Correct `docs/quickstart.md` to the authenticated flow.
2. Extend quickstart tests to execute the full documented sequence in a clean environment.
3. Add Bash and PowerShell key setup instructions.

These two PRs establish the project's most important property: the documentation does not merely claim proof; it demonstrates a proof path that actually runs.
