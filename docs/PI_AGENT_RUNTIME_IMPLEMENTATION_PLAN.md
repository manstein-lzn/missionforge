# PI Agent Runtime Implementation Plan

## Objective

Make `pi-agent-runtime` the single production worker for MissionForge.

MissionForge should keep a clean shape:

```text
MissionRuntime -> WorkUnitContract -> pi-agent-runtime -> ExecutionReport -> Verifier
```

There must be one production worker path. Test doubles and faux provider modes
are allowed only for deterministic testing.

Implementation status: completed for the offline production cutover and Phase 6
live provider validation. The default `MissionRuntime` path now uses
`PiAgentRuntimeAdapter`, which invokes `workers/pi-agent-runtime`. The runtime
uses PI Agent packages and a built-in faux provider for deterministic offline
tests. Live provider support is opt-in and has a Codex-current smoke test.

## Single Production Worker

Final product state:

- `pi-agent-runtime` is the only production worker.
- `MissionRuntime` defaults to `pi-agent-runtime`.
- Provider/model/timeout/budget are configuration on that one worker.
- There is no product-level worker registry.
- There is no public runtime selection between fake, faux, command, Codex, or
  PiWorker workers.

Allowed non-production support:

- `FakeWorker` remains a lower-level test fixture and is no longer re-exported
  from the public package root.
- Faux provider mode may exist inside `pi-agent-runtime` for offline tests.
- The old `PiWorkerCommandAdapter` has been removed from production docs and
  default paths after cutover to `pi-agent-runtime`.

## Target File Layout

Add the Node runtime as an internal package:

```text
workers/pi-agent-runtime/
  package.json
  package-lock.json
  tsconfig.json
  NOTICE
  src/
    main.ts
    contract.ts
    provider-config.ts
    runtime.ts
    tools.ts
    evidence-recorder.ts
    filesystem-snapshot.ts
    redaction.ts
    result-writer.ts
  tests/
    contract.test.ts
    faux-runtime.test.ts
    tools.test.ts
    redaction.test.ts
```

Add a Python adapter dedicated to this worker:

```text
src/missionforge/adapters/pi_agent_runtime.py
src/missionforge/adapters/pi_agent_provider_config.py
tests/test_pi_agent_runtime_adapter.py
tests/test_pi_agent_provider_config.py
tests/test_pi_agent_runtime_import_boundaries.py
```

Update runtime integration:

```text
src/missionforge/runtime.py
src/missionforge/runner.py
tests/test_runtime_vertical_slice.py
docs/modules/piworker.md
docs/modules/runtime.md
```

Cleanup after cutover:

```text
src/missionforge/adapters/piworker_command.py
src/missionforge/adapters/piworker_provider_config.py
tests/test_piworker_command_adapter.py
tests/test_piworker_provider_config.py
docs/PIWORKER_LIVE_PROVIDER_INTEGRATION_PLAN.md
```

These cleanup targets should not be deleted until the new runtime has offline
and optional live smoke coverage. They have now been removed from the active
production path.

## Source Strategy From `/home/mansteinl/pi`

Final runtime must not depend on the sibling path `/home/mansteinl/pi`.

Preferred implementation path:

1. Use `/home/mansteinl/pi` as source reference during implementation.
2. Build `workers/pi-agent-runtime` as MissionForge-owned code.
3. Depend on published or vendored PI packages from package metadata, not on a
   local sibling checkout.
4. If PI source is copied into MissionForge, include MIT attribution in
   `workers/pi-agent-runtime/NOTICE`.

Runtime pieces to use:

- `@earendil-works/pi-agent-core`
- `@earendil-works/pi-ai`
- selected tool implementations or exported tool factories from
  `@earendil-works/pi-coding-agent`

Do not import PI's full TUI product shell into MissionForge.

## Contract Names

Use new schema names for the dedicated runtime. Avoid extending the old
`piworker` naming into new architecture.

Input schema:

```text
missionforge.pi_agent_runtime_input.v1
```

Output schema:

```text
missionforge.pi_agent_runtime_output.v1
```

Attempt artifacts:

```text
attempts/<work_unit_id>/pi_agent_input.json
attempts/<work_unit_id>/pi_agent_output.json
attempts/<work_unit_id>/pi_agent_session.jsonl
attempts/<work_unit_id>/pi_agent_events.jsonl
attempts/<work_unit_id>/pi_agent_metrics.json
attempts/<work_unit_id>/pi_agent_execution_report.json
```

Top-level output fields:

- `schema_version`
- `work_unit_id`
- `status`: `completed`, `failed`, `blocked`, `cancelled`
- `produced_artifacts`
- `changed_refs`
- `commands_run`
- `tests_run`
- `failures`
- `worker_claims`
- `verifier_evidence`
- `new_unknowns`
- `recommended_next_steps`
- `verification_status`
- `input_ref`
- `output_ref`
- `session_ref`
- `events_ref`
- `metrics_ref`
- `duration_ms`
- `metrics`

Execution reports remain refs-only. Large tool output belongs in referenced
artifacts, not inline reports.

## Provider Configuration

Use MissionForge-specific environment names:

```text
MISSIONFORGE_PI_AGENT_PROVIDER=faux|live
MISSIONFORGE_PI_AGENT_MODEL=<model>
MISSIONFORGE_PI_AGENT_BASE_URL=<responses base url>
MISSIONFORGE_PI_AGENT_API_KEY=<secret>
MISSIONFORGE_PI_AGENT_REASONING=<off|minimal|low|medium|high|xhigh>
MISSIONFORGE_PI_AGENT_MAX_TURNS=<int>
MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS=<int>
```

Python resolver responsibilities:

- read current Codex config/auth when live mode uses `codex_current`
- require `wire_api=responses`
- pass API key only through child-process environment
- redact diagnostics
- fail before process invocation when required live config is missing

Node runtime responsibilities:

- construct a PI `Model<"openai-responses">`
- use PI's OpenAI Responses streaming implementation
- use `getApiKey` or process env lookup at provider-call time
- never write API keys or authorization headers to disk

## Node Runtime Design

### `main.ts`

Responsibilities:

- parse the single input path argument
- load and validate input JSON
- resolve workspace root and attempt refs
- create `AbortController`
- invoke `runMissionForgePiAgent(input, env)`
- catch failures and always write a normalized output artifact
- exit `0` only when a normalized output artifact was written

CLI contract:

```bash
node workers/pi-agent-runtime/dist/main.js attempts/WU-000001/pi_agent_input.json
```

### `contract.ts`

Define TypeBox schemas and TypeScript types for:

- runtime input
- runtime output
- event jsonl records
- metrics artifact
- session artifact
- tool result summaries

Validation must reject:

- missing refs
- absolute refs in contract fields
- `..` path traversal
- non-object input/output payloads
- unknown schema versions

### `provider-config.ts`

Resolve runtime provider config from environment:

- `faux`: deterministic offline stream function
- `live`: OpenAI Responses through PI AI

The faux provider should live inside `pi-agent-runtime`, not as a separate
MissionForge worker.

### `runtime.ts`

Construct and run PI `Agent`:

- system prompt is derived from `WorkUnitContract`
- tool list is full coding tool set
- model comes from provider config
- `toolExecution` defaults to `parallel`
- `beforeToolCall` enforces hard framework boundaries
- `afterToolCall` records evidence summaries and redacts text
- `prepareNextTurn` writes save-point metrics and checks budgets
- `shouldStopAfterTurn` enforces max turns and stop conditions

Suggested system prompt sections:

- Mission objective
- Expected outputs
- Allowed final output envelope
- Evidence expectations
- Stop conditions
- Reminder that verifier owns final acceptance
- Tool guidance: use full coding tools freely inside the workspace

Do not prompt the model to avoid tools. The worker is expected to act.

### `tools.ts`

Expose full coding tool set:

- `read`
- `bash`
- `edit`
- `write`
- `grep`
- `find`
- `ls`

Wrap operations for:

- workspace-root enforcement
- per-command timeout defaults
- abort propagation
- event capture
- output truncation
- secret redaction

`bash` remains enabled by default.

### `evidence-recorder.ts`

Subscribe to PI Agent events and write jsonl records:

- `agent_start`
- `turn_start`
- `message_start`
- `message_update` summaries
- `message_end`
- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`
- `turn_end`
- `agent_end`

Persist enough data to debug the run without leaking secrets:

- event id
- timestamp
- work unit id
- turn index
- tool call id
- tool name
- redacted args summary
- redacted result summary
- artifact refs
- token usage
- stop reason

Do not store raw full provider payloads by default.

### `filesystem-snapshot.ts`

Record workspace state before and after the run:

- track changed refs under workspace root
- ignore transient output files until final result mapping
- classify expected outputs as produced artifacts
- include scratch files in `changed_refs`

Final `produced_artifacts` should include only files that match
`expected_outputs` or explicitly declared output refs.

### `result-writer.ts`

Always write `pi_agent_output.json`.

Completed status requires:

- agent run ended without runtime failure
- every expected output exists
- produced output refs are inside final output authority
- output JSON and metrics artifacts were written

Otherwise write `failed` with structured failures.

## Python Adapter Design

### `PiAgentRuntimeConfig`

Fields:

- `command: tuple[str, ...]`
- `timeout_seconds: int`
- `provider_mode: "faux" | "live"`
- `provider_config_source: "env" | "codex_current" | "explicit"`
- `model: str | None`
- `runtime_name: str = "missionforge.pi_agent_runtime"`
- `metadata: Mapping[str, JsonValue]`

Validation:

- command is non-empty
- timeout is positive
- provider mode/source are known
- metadata rejects secret-shaped keys

### `PiAgentRuntimeAdapter`

Responsibilities:

- consume committed `WorkUnitContract` only
- write `pi_agent_input.json`
- resolve provider env
- invoke Node runtime command
- load `pi_agent_output.json`
- validate output schema
- enforce work unit id match
- enforce expected outputs exist on disk
- produce refs-only `ExecutionReport`
- append low-trust worker/event evidence into `EvidenceLedger`

This adapter should become MissionRuntime's production worker.

### Runtime Default

Change `RuntimeEngine` from:

```text
worker=self.worker or FakeWorker()
```

to:

```text
worker=self.worker or PiAgentRuntimeAdapter(default_config)
```

Then tighten public API later:

- keep worker injection only for tests, or
- replace it with `pi_agent_config`

The product API should not advertise arbitrary worker replacement.

## Implementation Phases

### Phase 1: Scaffold Internal Runtime Package

Status: completed.

Create:

- `workers/pi-agent-runtime/package.json`
- `workers/pi-agent-runtime/tsconfig.json`
- `workers/pi-agent-runtime/src/main.ts`
- minimal `contract.ts`
- minimal tests

Acceptance Gates:

- `npm test --prefix workers/pi-agent-runtime`
- `npm run build --prefix workers/pi-agent-runtime`
- no Python runtime behavior changed yet

### Phase 2: Implement Runtime Contract And Faux Provider

Status: completed.

Implement:

- input/output schemas
- deterministic faux stream function
- result writer
- event/metrics/session files

Faux run should be able to write a deterministic expected artifact without
network access.

Acceptance Gates:

- Node faux runtime test writes output JSON and expected artifact
- redaction test proves fake API key is absent from artifacts
- Python tests still pass

### Phase 3: Add Python Dedicated Adapter

Status: completed.

Implement:

- `pi_agent_provider_config.py`
- `pi_agent_runtime.py`
- adapter tests with fake command runner
- import-boundary tests

Do not make it default yet.

Acceptance Gates:

- fake runner success maps to `WorkerAdapterResult`
- missing output maps to worker failure
- nonzero command maps to worker failure
- stdout/stderr are redacted
- output outside authority fails
- existing full Python suite passes

### Phase 4: Wire Real Node Faux Runtime Through Python

Status: completed.

Add an optional smoke that invokes the actual Node CLI in faux mode.

Acceptance Gates:

- Python adapter invokes built Node runtime
- output artifact is produced
- `ExecutionReport` is refs-only
- event refs are appended
- no live network required

### Phase 5: Full PI Agent And Tools

Status: completed for the initial full-tool runtime. The runtime uses PI Agent
core, PI AI, and PI coding-agent tools (`read`, `bash`, `edit`, `write`,
`grep`, `find`, `ls`) with MissionForge workspace-root guards and artifact
recording.

Bring in PI runtime pieces:

- PI Agent core
- PI AI stream abstraction
- coding tools
- MissionForge tool wrappers

Acceptance Gates:

- read/write/edit/bash tool events recorded
- bash output is truncated and redacted
- file mutations serialize correctly
- workspace escape is blocked or isolated
- max-turn and timeout failures write normalized output

### Phase 6: Live Provider

Status: completed for the current Codex provider path. Live mode remains
opt-in because it requires external credentials and model availability.

Connect live mode to current Codex config:

- model
- base URL
- responses wire API
- API key from Codex auth/env

Acceptance Gates:

- live config resolver fails closed without required config. Status: completed.
- API key never appears in input/output/session/events/metrics/reports.
  Status: covered by offline redaction tests and live smoke workspace scan.
- optional live smoke creates a small expected artifact. Status: completed
  against the current Codex config.

### Phase 7: Cutover Plan

Status: completed for production default.

Make `pi-agent-runtime` the default and only production worker:

1. Change `RuntimeEngine` default worker to `PiAgentRuntimeAdapter`.
2. Update `MissionRuntime` construction to accept `pi_agent_config`, not
   arbitrary worker selection for product use. Status: completed.
3. Update vertical slice tests to use `pi-agent-runtime` faux mode.
4. Move old `FakeWorker` tests to test fixture coverage or delete them.
   Status: package-root export removed; lower-level fixture tests remain.
5. Remove product docs that describe command PiWorker as a supported live path.
6. Remove `PiWorkerCommandAdapter` after all new tests pass.

Acceptance Gates:

- no product docs describe multiple worker runtime choices
- default runtime path is `pi-agent-runtime`
- all Python tests pass
- all Node tests pass
- optional live smoke passes when enabled

### Phase 8: Cleanup

Status: completed for command PiWorker production-path cleanup.

Remove stale architecture:

- command PiWorker production docs
- live-provider sidecar plan as active guidance
- runtime worker-selection language
- old tests that assert fake/command workers as runtime choices

Keep only:

- `pi-agent-runtime`
- internal faux provider tests
- verifier/evidence/runtime contracts

### Phase 9: Session, Steering, And Repair

Status: completed for the offline session/repair hardening slice.

Detailed plan:

```text
docs/PI_AGENT_RUNTIME_PHASE9_PLAN.md
```

Upgrade the dedicated `pi-agent-runtime` from a one-shot worker into a
session-aware worker:

- save points after each completed assistant turn
- structured verifier repair follow-up
- bounded repair attempts
- safe-point cancellation
- explicit resume boundary
- conservative transcript compaction

Implemented artifacts and contracts:

- `attempts/<work_unit_id>/pi_agent_savepoints.jsonl`
- `savepoints_ref` on input/output/report surfaces
- `repair.mode = none | follow_up`
- `PiAgentRuntimeAdapter.with_repair(...)`
- `RuntimeEngine` one-shot verifier failure repair routing when
  `max_attempts > 1`
- `MISSIONFORGE_PI_AGENT_CANCEL_AFTER_TURNS`
- `MISSIONFORGE_PI_AGENT_COMPACT_AFTER_TURNS`

Keep the same architecture:

```text
MissionRuntime -> WorkUnitContract -> pi-agent-runtime -> ExecutionReport -> Verifier
```

Acceptance Gates:

- savepoint artifacts are refs-only and redacted
- verifier failure can route to one bounded faux repair attempt
- cancellation never maps to verifier success
- resume support is documented only at completed-turn boundaries
- full Python and Node validators pass
- optional live smoke still passes when enabled

### Phase 10: Runtime Hardening

Status: completed for the offline runtime hardening slice.

Detailed plan:

```text
docs/PI_AGENT_RUNTIME_PHASE10_RUNTIME_HARDENING_PLAN.md
```

Harden the single `pi-agent-runtime` path for long-running, failure-prone,
interruptible execution:

- durable `MissionRun` state and attempt ledger
- read-only runtime status/inspection
- safe-point resume command for `after_completed_turn`
- explicit retry, repair, redesign, stop, and escalation policy
- cancellation/control hardening across worker and runtime safe points
- deterministic failure injection suite
- artifact hygiene scanner
- opt-in live provider soak

Keep the same architecture:

```text
MissionRuntime -> WorkUnitContract -> pi-agent-runtime -> ExecutionReport -> Verifier
```

Acceptance Gates:

- every run has inspectable durable state
- every attempt is recorded by ref
- resume rejects unsupported safe-point kinds
- retry/repair/redesign decisions are explicit and bounded
- deterministic failure injection covers critical failure modes
- artifact hygiene scanning is enforced
- optional live soak passes when enabled
- full Python and Node validators pass

## Acceptance Gates

Required before claiming implementation complete:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
npm test --prefix workers/pi-agent-runtime
npm run build --prefix workers/pi-agent-runtime
git diff --check
```

Latest local evidence:

```bash
npm test --prefix workers/pi-agent-runtime
# 9 tests passed

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 152 tests: OK (skipped=1)

MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 MISSIONFORGE_PI_AGENT_MAX_TURNS=4 \
MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS=30 \
PYTHONPATH=src python3 -m unittest tests.test_pi_agent_runtime_live_smoke
# Ran 1 test: OK

git diff --check
# passed
```

Required artifact checks:

- `pi_agent_input.json` exists and contains no secrets
- `pi_agent_output.json` exists on success and failure
- `pi_agent_events.jsonl` exists
- `pi_agent_session.jsonl` exists
- `pi_agent_metrics.json` exists
- `pi_agent_execution_report.json` is refs-only
- expected outputs exist on completed runs

Required negative checks:

- no API key appears in any workspace artifact
- no absolute path escape is accepted as a ref
- no worker self-claim grants verifier success
- no missing expected output returns completed
- no product runtime-selection matrix remains

Optional live check:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 MISSIONFORGE_PI_AGENT_MAX_TURNS=4 \
MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS=30 \
PYTHONPATH=src python3 -m unittest tests.test_pi_agent_runtime_live_smoke
```

## Engineering Order

Recommended commit order:

1. Node package scaffold and contract schemas.
2. Node faux runtime.
3. Python adapter and provider config.
4. Python-to-Node faux smoke.
5. PI Agent core integration.
6. Full tool wrappers.
7. Live provider.
8. Default runtime cutover.
9. Cleanup old worker paths and docs.

This order keeps every step verifiable and avoids carrying two production
worker paths longer than necessary.

## Design Decisions

- The runtime is Node/TypeScript because PI's agent and provider layers are
  TypeScript.
- Python remains the MissionForge orchestrator and verifier owner.
- The process boundary remains explicit: it is a worker isolation boundary, not
  a second product architecture.
- `allowed_scope` is final output authority, not per-step worker handcuffs.
- The worker gets full coding tools by default.
- `bash` remains available.
- Verifier remains the only completion authority.

## Open Questions Before Coding

These should be answered during Phase 1 or Phase 2, not left until cutover:

- Should PI packages be consumed from npm or vendored from the sibling repo?
- What exact Node version should MissionForge declare for this worker?
- Should default local development use faux mode unless live is explicitly
  requested?
- Should `MissionRuntime(worker=...)` become private/test-only immediately, or
  after cutover? Resolved: removed from the public facade; tests that need
  injection use lower-level harness/runtime objects.

None of these questions changes the core architecture: one production worker,
`pi-agent-runtime`.
