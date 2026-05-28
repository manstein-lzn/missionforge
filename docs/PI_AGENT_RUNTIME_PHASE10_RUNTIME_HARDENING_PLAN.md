# PI Agent Runtime Phase 10 Runtime Hardening Plan

## Objective

Harden MissionForge's single production worker path so long-running,
failure-prone, interruptible execution can be inspected, resumed, diagnosed,
and verified without loosening the worker's autonomy.

The production architecture stays intentionally small:

```text
MissionRuntime -> WorkUnitContract -> pi-agent-runtime -> ExecutionReport -> Verifier
```

Phase 10 does not introduce another worker, a public worker registry, or a
host-owned agent brain. It hardens the dedicated `pi-agent-runtime` path that
Phase 6 and Phase 9 established.

Implementation status: completed for the offline runtime hardening slice on
2026-05-28. Final closeout requires the validation gates in this document to
pass after any code or documentation changes.

## Roadmap Position

MissionForge is currently at the runtime hardening stage of the PI Agent
Runtime roadmap:

```text
Phase 6: live provider cutover
  -> Phase 9: session, savepoint, repair, and cancellation hardening
  -> Phase 10: runtime-grade state, resume, failure, hygiene, and status hardening
  -> Phase 11: productization loop, CLI/UX polish, operator workflows
```

Phase 9 made the worker session-aware. Phase 10 makes the runtime
operationally reliable enough for productization to sit on top of it.

## Success Criteria

Phase 10 is complete when MissionForge can prove all of the following through
durable artifacts and tests:

- every run writes an inspectable `MissionRun` ledger,
- every worker dispatch, repair follow-up, retry, cancellation, or resume is
  represented as a refs-only runtime attempt record,
- status inspection is read-only and does not expose transcripts or secrets,
- resume is accepted only from the `after_completed_turn` safe point,
- retry, repair, redesign, review, escalation, stop, and completion are
  distinguishable runtime decisions,
- cancellation never maps to verifier success,
- deterministic failure injection covers critical provider, tool, contract,
  artifact, verifier, timeout, and secret-leak paths,
- artifact hygiene scanning proves reports are refs-only and secret-safe,
- live provider soak exists but remains skipped unless explicitly enabled,
- the verifier remains the only completion authority.

## Non-Goals

- Do not add another production worker.
- Do not restore command PiWorker.
- Do not expose worker selection as a product API.
- Do not import PI's full TUI or product shell.
- Do not constrain the worker's normal tool freedom beyond workspace,
  timeout, budget, evidence, and secret boundaries.
- Do not implement mid-tool-call resume.
- Do not resume active shell processes.
- Do not recover partial provider streams.
- Do not replay uncommitted filesystem mutations automatically.
- Do not make live LLM tests mandatory in default CI.
- Do not treat worker claims, UI summaries, or status output as completion
  authority.

## Runtime Invariants

- `pi-agent-runtime` is the only production worker.
- Worker output is evidence, not acceptance.
- The verifier is the sole completion authority.
- Runtime reports and `MissionResult` stay refs-only.
- Provider credentials are passed only through the child-process environment.
- Secrets must not appear in inputs, outputs, events, metrics, savepoints,
  ledgers, status summaries, execution reports, stdout/stderr captures, docs,
  or test artifacts.
- Resume is allowed only from durable completed-turn safe points.
- Retry is only for structured transient failures where the runtime can prove
  retry is safe.
- Repair is for verifier-detected artifact or constraint failures.
- Redesign is for contract, authority, unsupported validator, or impossible
  scope failures.
- Control requests are consumed only at safe points and preserved as evidence.

## Durable Runtime Artifacts

Phase 10 adds durable run-level artifacts under:

```text
runs/<mission_run_id>/
  mission_run.json
  attempts.jsonl
  artifact_hygiene.json
```

### Mission Run Ledger

`mission_run.json` is the latest refs-only runtime state:

```json
{
  "schema_version": "missionforge.mission_run.v1",
  "mission_run_id": "run-mission-001",
  "mission_id": "mission-001",
  "status": "failed",
  "current_attempt": "attempt-000002",
  "latest_work_unit_id": "WU-000002",
  "latest_safe_point": {
    "kind": "after_completed_turn",
    "savepoint_ref": "attempts/WU-000001/pi_agent_savepoints.jsonl#turn=2",
    "session_ref": "attempts/WU-000001/pi_agent_session.jsonl",
    "events_ref": "attempts/WU-000001/pi_agent_events.jsonl"
  },
  "latest_decision": "repair",
  "next_action": "resume_repair",
  "artifact_refs": ["package/SKILL.md"],
  "evidence_refs": ["E-000001"],
  "failed_constraint_ids": ["C-001"],
  "attempts_ref": "runs/run-mission-001/attempts.jsonl",
  "artifact_hygiene_ref": "runs/run-mission-001/artifact_hygiene.json",
  "metrics": {
    "attempt_count": 2,
    "repair_attempted": true,
    "retry_attempted": false,
    "redesign_required": false,
    "resume_count": 0,
    "artifact_hygiene_passed": true
  },
  "updated_at": "2026-05-28T00:00:00Z"
}
```

The ledger must summarize state only. It must not embed raw transcripts,
artifact bodies, provider payloads, stdout/stderr bodies, or secrets.

### Runtime Attempt Ledger

`attempts.jsonl` stores one `missionforge.runtime_attempt.v1` record per
dispatch-like runtime action. Resume preserves previous records and appends a
new `attempt_kind = "resume"` record.

```json
{
  "schema_version": "missionforge.runtime_attempt.v1",
  "attempt_id": "attempt-000002",
  "work_unit_id": "WU-000002",
  "attempt_kind": "resume",
  "worker": "missionforge.pi_agent_runtime",
  "input_ref": "attempts/WU-000002/pi_agent_input.json",
  "output_ref": "attempts/WU-000002/pi_agent_output.json",
  "report_ref": "attempts/WU-000002/pi_agent_execution_report.json",
  "savepoints_ref": "attempts/WU-000002/pi_agent_savepoints.jsonl",
  "status": "completed",
  "verification_status": "completed_verified",
  "decision": "resume",
  "evidence_refs": [],
  "artifact_refs": ["package/SKILL.md"],
  "failure_category": "",
  "metrics": {
    "input_ref": "attempts/WU-000002/pi_agent_input.json",
    "output_ref": "attempts/WU-000002/pi_agent_output.json",
    "savepoints_ref": "attempts/WU-000002/pi_agent_savepoints.jsonl"
  },
  "created_at": "2026-05-28T00:00:00Z"
}
```

Attempt records may cite refs and small metrics. They must not carry raw tool
output, transcript bodies, provider messages, or secret values.

### Artifact Hygiene Report

`artifact_hygiene.json` records deterministic hygiene checks:

- every recorded ref is workspace-relative,
- required refs exist when the run status depends on them,
- report bodies do not embed expected output contents,
- secret values and secret-shaped patterns are absent,
- path traversal and absolute refs are rejected,
- large captured streams are truncated before they can enter reports.

The hygiene report is evidence for runtime safety. A passing worker run with a
failing hygiene report is not product-ready.

## Resume Contract

Supported in Phase 10:

- resume from the latest `after_completed_turn` savepoint,
- pass savepoint, session, and events refs to `pi-agent-runtime`,
- provide a follow-up prompt,
- record the resumed invocation as a new runtime attempt,
- let the verifier decide the final result after the resume.

Unsupported in Phase 10:

- mid-tool-call resume,
- active shell process recovery,
- partial provider stream recovery,
- automatic replay of filesystem mutations not represented by durable refs,
- resume from unknown or manually edited safe-point kinds.

The Python runtime and Node contract both reject unsupported resume boundaries.

## Runtime Decision Model

Phase 10 makes runtime routing explicit. The runtime must not mechanically
retry every failure.

| Condition | Decision | Required behavior |
| --- | --- | --- |
| Verifier passes | `complete` | Emit success only through verifier status. |
| Expected artifact missing | `repair` | Preserve failed constraint IDs and route bounded follow-up when available. |
| Verifier fails after repair budget | `stop` | Record repair exhaustion and keep non-success status. |
| Unsupported validator/spec | `redesign` | Do not retry; contract or authority must change. |
| Proposal rejected by contract validation | `redesign` | Do not dispatch worker. |
| Provider/tool transient failure before mutation | `retry` | Retry only when structured evidence proves it is safe and bounded. |
| Worker output schema invalid | `fail` or `redesign` | Do not trust worker claims. |
| Output outside allowed scope | `fail` or `redesign` | Preserve authority-boundary evidence. |
| Halt before invocation | `cancelled` | Write state without worker dispatch. |
| Halt after completed turn | `cancelled` | Preserve latest safe point; never mark verifier success. |
| Review gate | `review` | Await independent reviewer decision. |
| Human-only gate | `escalate` | Await explicit human acceptance. |

Metrics must expose at least:

- `attempt_count`,
- `repair_attempted`,
- `repair_exhausted`,
- `retry_attempted`,
- `retry_exhausted`,
- `redesign_required`,
- `resume_count`,
- `latest_decision`,
- `next_action`,
- `verification_status`,
- `artifact_hygiene_passed`.

## Workstreams

### 10.1 Runtime State Ledger

Status: implemented.

Primary files:

- `src/missionforge/state.py`
- `src/missionforge/runtime.py`
- `src/missionforge/runner.py`
- `tests/test_runtime_state_ledger.py`

Acceptance:

- `mission_run.json` is written for every completed runtime path.
- `attempts.jsonl` records every dispatch-like attempt by ref.
- Resume preserves existing attempt records and adds a resume record.
- `MissionResult` stays refs-only.
- Ledger reads do not require raw transcript bodies.

### 10.2 Read-Only Runtime Status

Status: implemented through Python API.

API:

```python
MissionRuntime.inspect(mission_run_id=None)
```

Acceptance:

- Inspection returns latest run status, latest safe point, latest attempt,
  failed constraints, next action, and key refs.
- Inspection does not mutate files.
- Inspection does not expose provider secrets or raw transcripts.
- Missing run state returns a structured validation error.

CLI status is intentionally deferred to Phase 11 productization.

### 10.3 Safe-Point Resume

Status: implemented for `after_completed_turn`.

Primary files:

- `src/missionforge/runtime.py`
- `src/missionforge/runner.py`
- `src/missionforge/adapters/pi_agent_runtime.py`
- `workers/pi-agent-runtime/src/contract.ts`
- `workers/pi-agent-runtime/src/runtime.ts`
- `tests/test_runtime_resume.py`
- `workers/pi-agent-runtime/tests/contract.test.mjs`

Acceptance:

- Resume rejects non-`after_completed_turn` boundaries.
- Resume input references previous savepoint/session/events by ref.
- Resume records `attempt_kind = "resume"`.
- Resume does not rewrite previous attempt artifacts.
- The verifier still decides completion.

### 10.4 Retry, Repair, And Redesign Policy

Status: implemented for explicit decisions, metrics, failure categories, and
bounded verifier repair.

Acceptance:

- Verifier failures route to repair, not blind retry.
- Repair attempts are bounded.
- Unsupported verifier specs set `redesign_required`.
- Contract/schema/authority failures do not silently retry.
- Retry fields exist and remain false unless a safe retry path is actually
  taken.
- Exhaustion reasons are visible in metrics.

### 10.5 Cancellation And Control Hardening

Status: implemented for current safe points.

Acceptance:

- Halt before invocation prevents worker dispatch.
- Halt before repair follow-up prevents repair dispatch.
- Halt after verifier result preserves verifier evidence.
- Cancelled output is never mapped to verifier success.
- Control evidence remains linked from runtime state.

### 10.6 Failure Injection Suite

Status: implemented for deterministic offline coverage.

Failure modes to cover:

- provider startup failure,
- provider timeout or stream failure,
- malformed or invalid runtime output,
- missing expected output artifact,
- missing savepoint/session/events/metrics artifact,
- output outside allowed scope,
- absolute or path-traversal refs,
- secret-shaped stdout/stderr or metadata,
- unsupported verification spec,
- verifier failure after repair,
- repair exhaustion,
- retry exhaustion metrics.

Acceptance:

- Each failure path writes normalized state where possible.
- No failure path produces verifier success unless the verifier passes.
- Required tests run offline without live provider access.
- Secret scanning catches injected secret values.

### 10.7 Artifact Hygiene Scanner

Status: implemented.

Primary files:

- `src/missionforge/state.py`
- `tests/test_runtime_artifact_hygiene.py`

Acceptance:

- Scanner writes `artifact_hygiene.json`.
- Scanner validates workspace-relative refs.
- Scanner validates required attempt artifacts.
- Scanner rejects embedded expected-output bodies in reports.
- Scanner detects explicit secrets and secret-shaped patterns.
- Scanner runs in both default offline tests and opt-in live checks.

### 10.8 Metrics And Budgets

Status: implemented for runtime summaries.

Acceptance:

- Run ledger and result metrics expose attempt, repair, retry, resume,
  redesign, decision, and verification summaries.
- Metrics are small JSON values only.
- Metrics do not contain raw transcript text or secret values.
- Budget exhaustion is distinguishable from verifier failure when the worker
  reports enough structured data.

### 10.9 Live Provider Soak

Status: implemented as skipped-by-default test.

Command:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SOAK=1 \
MISSIONFORGE_PI_AGENT_MAX_TURNS=8 \
MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS=45 \
PYTHONPATH=src python3 -m unittest tests.test_pi_agent_runtime_live_soak
```

Acceptance:

- The test is skipped unless explicitly enabled.
- It uses current Codex live provider config.
- It exercises multi-turn tool use.
- It writes savepoints and run ledgers.
- It scans generated artifacts for live API key and authorization leaks.
- It verifies expected output through MissionForge verifier.

### 10.10 Documentation And Operator Runbook

Status: implemented in this document and `docs/modules/runtime.md`.

Acceptance:

- Docs state supported and unsupported resume modes.
- Docs explain retry versus repair versus redesign.
- Docs list validation commands.
- Docs include diagnosis and handoff guidance for Phase 11.

## Operator Runbook

### Inspect A Run

Use the Python API until Phase 11 adds CLI UX:

```python
from missionforge import MissionRuntime

summary = MissionRuntime(workspace="...").inspect("run-sample-mission")
```

Read these fields first:

- `mission_run.status`,
- `mission_run.latest_decision`,
- `mission_run.next_action`,
- `mission_run.latest_safe_point`,
- `latest_attempt`,
- `attempt_count`.

### Resume A Run

Resume only when `mission_run.latest_safe_point.kind` is
`after_completed_turn`:

```python
runtime.resume(mission, follow_up_prompt="Continue from the latest completed turn.")
```

Expected evidence after resume:

- `attempts.jsonl` includes the previous attempt records,
- the latest record has `attempt_kind = "resume"`,
- the input envelope references savepoint/session/events refs,
- verification runs again after the resumed attempt.

### Diagnose A Failed Run

Use `latest_decision` and `next_action`:

- `resume_repair`: verifier failure is repairable within policy.
- `redesign`: contract, authority, or validator scope must change.
- `await_review`: independent reviewer gate is pending.
- `await_human_acceptance`: user-only authority is required.
- `inspect_failure`: no automatic route remains; inspect latest attempt refs.

Then inspect:

- `runs/<run>/attempts.jsonl`,
- latest attempt `report_ref`,
- latest attempt `output_ref`,
- `runs/<run>/artifact_hygiene.json`,
- verifier evidence refs.

Do not inspect raw session or event transcripts as acceptance evidence. They
are diagnostic material only.

## Implementation Order

1. Define `MissionRun`, `RuntimeAttempt`, `RuntimeSafePoint`, and
   `ArtifactHygieneReport` schemas.
2. Write run and attempt ledgers for normal deterministic runs.
3. Add read-only runtime inspection.
4. Add artifact hygiene scanning.
5. Add deterministic failure injection tests.
6. Add explicit retry, repair, redesign, and exhaustion metrics.
7. Implement completed-turn resume.
8. Preserve prior attempt records across resume.
9. Harden cancellation/control around repair and resume safe points.
10. Add skipped-by-default live provider soak.
11. Update documentation and run the full validation gates.

## Validation Gates

Required targeted tests:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_runtime_state_ledger \
  tests.test_runtime_resume \
  tests.test_runtime_failure_injection \
  tests.test_runtime_artifact_hygiene
```

Required full validation:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
npm test --prefix workers/pi-agent-runtime
npm run build --prefix workers/pi-agent-runtime
git diff --check
```

MetaLoop closeout:

```bash
python3 /home/mansteinl/.codex/skills/metaloop/scripts/metaloop_kernel.py --workspace . status
python3 /home/mansteinl/.codex/skills/metaloop/scripts/metaloop_kernel.py --workspace . verify --json
```

Optional live soak:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SOAK=1 \
MISSIONFORGE_PI_AGENT_MAX_TURNS=8 \
MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS=45 \
PYTHONPATH=src python3 -m unittest tests.test_pi_agent_runtime_live_soak
```

The live soak is not part of default validation because it consumes live model
resources and depends on external provider availability.

## Completion Audit

| Requirement | Evidence |
| --- | --- |
| MissionRun ledger written | `tests/test_runtime_state_ledger.py` |
| Attempts ledger refs-only | `tests/test_runtime_state_ledger.py` |
| Resume appends attempt history | `tests/test_runtime_resume.py` |
| Inspect/status read-only | `tests/test_runtime_state_ledger.py` |
| Completed-turn resume only | `tests/test_runtime_resume.py`; `workers/pi-agent-runtime/tests/contract.test.mjs` |
| Unsupported resume rejected | `tests/test_runtime_resume.py`; `workers/pi-agent-runtime/tests/contract.test.mjs` |
| Retry/repair/redesign separated | `tests/test_runtime_failure_injection.py` |
| Cancellation safe-point consistency | `tests/test_control_requests.py`; `workers/pi-agent-runtime/tests/faux-runtime.test.mjs` |
| Artifact hygiene enforced | `tests/test_runtime_artifact_hygiene.py` |
| Live soak opt-in | `tests/test_pi_agent_runtime_live_soak.py` |

## Known Limits After Phase 10

- CLI status/resume UX is deferred to Phase 11.
- Resume is completed-turn only.
- Active shell process recovery is unsupported.
- Partial provider stream recovery is unsupported.
- Automatic retry execution should remain conservative and evidence-gated.
- JSON files are sufficient for this hardening slice; SQLite or another store
  can be considered later if operational scale requires it.

## Handoff To Phase 11

Phase 11 productization should build on the Phase 10 durable state instead of
inventing a second runtime surface. Product UX should answer these questions
from the existing ledgers:

- What is the latest run status?
- Which attempt produced the latest evidence?
- What safe point can be resumed?
- Why did the run stop?
- Should the next action be retry, repair, redesign, review, stop, or resume?
- Which refs should a user inspect?
- Did the verifier, not the worker, prove completion?

Only after these answers are clear should Phase 11 add CLI commands, operator
views, packaged workflows, or higher-level product affordances.

The Phase 11 scope is tracked in
`docs/PHASE11_OPERATOR_PRODUCTIZATION_PLAN.md`.
