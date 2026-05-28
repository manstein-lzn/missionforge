# Phase 11 Operator Productization Plan

## Objective

Turn MissionForge's Phase 10 durable runtime state into a small, reliable
operator surface for running, inspecting, diagnosing, resuming, reviewing, and
validating missions.

Phase 11 is not a new runtime brain. It is the productization layer above the
existing path:

```text
MissionRuntime -> WorkUnitContract -> pi-agent-runtime -> ExecutionReport -> Verifier
```

The runtime already writes `MissionRun`, `RuntimeAttempt`,
`RuntimeSafePoint`, `ArtifactHygieneReport`, PI Agent refs, and verifier-routed
`MissionResult` records. Phase 11 makes those records usable without requiring
operators or host products to manually inspect JSON files.

## Roadmap Position

```text
Phase 6: live provider cutover
  -> Phase 9: session, savepoint, repair, and cancellation hardening
  -> Phase 10: runtime-grade state, resume, failure, hygiene, and status hardening
  -> Phase 11: operator/product UX on top of durable runtime state
```

Phase 10 answered: can MissionForge leave trustworthy refs-only state?

Phase 11 answers: can a host, operator, or SkillFoundry-like product use that
state to make the next operational decision?

## PI Main Reuse Audit

The sibling PI source snapshot at `/home/mansteinl/tmp/pi-main` contains four
major packages:

- `packages/agent`: agent loop, session harness, compaction, and durable
  session concepts
- `packages/ai`: provider/model/streaming abstractions
- `packages/coding-agent`: CLI, RPC mode, session manager, coding tools,
  extensions, and product shell
- `packages/tui`: terminal UI library

MissionForge already reused the right production-worker layer through
`workers/pi-agent-runtime`: PI Agent core, PI AI, and selected coding-agent
tools. Phase 11 should not import PI's whole coding-agent product shell.

### Reuse Matrix

| PI capability | Phase 11 reuse decision | Reason |
| --- | --- | --- |
| PI Agent core loop | Already reused inside `pi-agent-runtime` | Worker autonomy belongs inside the worker boundary |
| PI AI provider layer | Already reused inside `pi-agent-runtime` | Provider parsing and streaming should not be reimplemented |
| Coding tools | Already reused selectively | Tools are wrapped by MissionForge workspace guards |
| CLI flag vocabulary | Reuse as inspiration | `--resume`, `--session`, `--mode json`, and `--offline` are useful UX patterns |
| RPC JSONL protocol | Reuse as a design pattern | Headless commands/responses/events fit future MissionForge embedding |
| Session tree/fork/clone UX | Reuse later for PI session inspection | PI session tree is worker-internal, not MissionForge truth |
| Durable harness recovery doctrine | Reuse directly as policy input | It confirms recovery from durable boundaries, not live streams |
| Full PI TUI | Do not import in Phase 11 | It would add product UI and state semantics MissionForge does not own |
| Full PI coding-agent CLI | Do not import in Phase 11 | It owns agent sessions, model state, extensions, and prompts, not MissionRun truth |

Important version note: the sibling `pi-main` snapshot uses PI package version
`0.75.5`, while MissionForge currently depends on `0.76.0` in
`workers/pi-agent-runtime`. Direct source copying from the sibling tree can
accidentally downgrade or fork the working dependency path.

## Product Boundary

Phase 11 must keep MissionForge's truth sources separate:

```text
MissionRun / RuntimeAttempt / Verifier result = operational truth
PI Agent session / events / messages = worker diagnostic refs
CLI / host / dashboard = observation and explicit control intent
```

The operator surface may summarize, route, and explain existing state. It must
not become a second verifier, a second runtime, or an unvalidated steering
authority.

## Non-Goals

- Do not add another production worker.
- Do not expose a public worker registry.
- Do not import PI's full TUI or full coding-agent CLI.
- Do not make PI session history the MissionForge run ledger.
- Do not expose raw transcripts, provider payloads, or secrets in default
  status output.
- Do not let CLI, dashboard, worker claims, or status summaries prove
  completion.
- Do not implement mid-tool-call resume.
- Do not resume active shell processes.
- Do not replay filesystem mutations that are not represented by durable refs.
- Do not enable live LLM steering by default.
- Do not put SkillFoundry product semantics into MissionForge core.

## Operator Workflows

Phase 11 must support these workflows without requiring users to inspect raw
worker transcripts.

### Run A Mission

```bash
missionforge run --workspace . --mission-ref missions/input.mission.json
```

Expected behavior:

- validates the MissionIR ref,
- runs the default `MissionRuntime`,
- writes a refs-only `MissionResult`,
- prints a refs-only command result,
- returns a nonzero exit code for invalid input, failed runtime execution, or
  failed blocking verification.

### Inspect A Run

```bash
missionforge inspect --workspace . --run run-sample-mission
```

Expected output fields:

- `mission_run_id`
- `mission_id`
- `status`
- `current_attempt`
- `latest_work_unit_id`
- `latest_decision`
- `next_action`
- `latest_safe_point`
- `attempt_count`
- latest attempt refs
- failed constraint IDs
- artifact refs
- evidence refs
- artifact hygiene status

### Diagnose A Failed Run

```bash
missionforge diagnose --workspace . --run run-sample-mission
```

Diagnosis is a deterministic view over existing state. It maps runtime status,
attempt failure category, verifier status, hygiene status, and safe-point
availability into a recommended operator action:

| Condition | Diagnosis | Operator action |
| --- | --- | --- |
| verifier completed | `complete` | no action |
| no latest safe point | `no_resume_safe_point` | inspect or redesign |
| worker failed before output | `worker_failure` | inspect latest output/report refs |
| verifier failed and repair budget remains | `repairable_verifier_failure` | resume repair |
| verifier failed after repair budget | `repair_exhausted` | stop or redesign |
| unsupported validator | `redesign_required` | revise contract/profile |
| review gate pending | `review_required` | create or record review decision |
| human-only gate pending | `human_acceptance_required` | wait for explicit human authority |
| artifact hygiene failed | `artifact_hygiene_failed` | inspect hygiene report before retry |

The diagnosis command must cite refs. It must not embed artifact bodies or raw
session messages.

### Resume From A Safe Point

```bash
missionforge resume \
  --workspace . \
  --run run-sample-mission \
  --mission-ref missions/input.mission.json \
  --prompt "Continue from the latest completed turn."
```

Expected behavior:

- reads `MissionRun.latest_safe_point`,
- rejects missing or non-`after_completed_turn` boundaries,
- appends a new runtime attempt,
- preserves prior attempt records,
- reruns verifier after the resumed attempt,
- returns the new refs-only `MissionResult`.

### Write Explicit Control Intent

```bash
missionforge control halt \
  --workspace . \
  --run run-sample-mission \
  --reason "Operator requested pause before the next attempt."
```

Expected behavior:

- writes an explicit `ControlRequest` ref,
- does not mutate `MissionRun`,
- lets runtime consume the control only at safe points.

### Record A Review Decision

```bash
missionforge review record \
  --workspace . \
  --run run-sample-mission \
  --decision approved \
  --review-ref reviews/reviewer-decision.json
```

Expected behavior:

- validates reviewer decision freshness against the current contract hash,
  capsule/run identity, and verification spec where available,
- records only refs and decision metadata,
- does not replace failed executable validators.

### Validate The Environment

```bash
missionforge validate
```

At first this can delegate to `scripts/validate.sh`. Later it may become a
native CLI command that checks:

- Node version from `.nvmrc`
- `workers/pi-agent-runtime` dependency/build health
- Python test suite
- whitespace checks
- optional live-provider readiness without consuming live budget by default

## Optional Headless Protocol

Phase 11 can add a MissionForge-owned JSONL protocol inspired by PI RPC. It
should be refs-only and MissionRun-centered.

Input examples:

```json
{"id":"1","type":"inspect","run":"run-sample-mission"}
{"id":"2","type":"diagnose","run":"run-sample-mission"}
{"id":"3","type":"resume","run":"run-sample-mission","mission_ref":"missions/input.mission.json"}
{"id":"4","type":"write_control","control_type":"halt","reason":"Pause before next attempt."}
```

Output examples:

```json
{"id":"1","type":"response","command":"inspect","success":true,"data":{"mission_run_id":"run-sample-mission","next_action":"complete"}}
{"id":"2","type":"response","command":"diagnose","success":true,"data":{"diagnosis":"complete","refs":[]}}
```

Forbidden defaults:

- no raw transcript bodies,
- no raw provider messages,
- no embedded artifact contents,
- no secret values,
- no CLI-side completion authority.

## SkillFoundry Product Path

Phase 11 should prove MissionForge can support a SkillFoundry-like product
without putting SkillFoundry semantics in core:

```text
SkillFoundry source refs
  -> SkillFoundryMissionCompiler
  -> MissionIR
  -> MissionRuntime
  -> pi-agent-runtime
  -> Verifier
  -> MissionResult refs
  -> operator inspect/diagnose/resume
```

The SkillFoundry adapter remains an adapter. The operator surface should expose
MissionForge refs and state, not SkillFoundry-specific runtime branches.

## Workstreams

### 11.1 CLI Entrypoint

Add a small MissionForge CLI entrypoint that routes subcommands to existing
Python APIs.

Primary commands:

- `run`
- `inspect`
- `diagnose`
- `resume`
- `control halt`
- `review record`
- `validate`

Acceptance:

- commands return deterministic JSON by default or through `--json`,
- exit codes distinguish success, verification failure, invalid input, missing
  state, and unsupported operation,
- no command prints raw transcript or secret material.

### 11.2 Inspect And Diagnose

Build read-only summaries over `MissionRun`, `RuntimeAttempt`, and hygiene
reports.

Acceptance:

- inspection does not mutate files,
- diagnosis cites refs and deterministic reason codes,
- missing run state returns a structured error,
- latest attempt and safe-point data are visible without opening raw PI session
  messages.

### 11.3 Resume Command

Expose completed-turn resume through CLI while preserving Phase 10 boundaries.

Acceptance:

- missing safe point fails closed,
- unsupported safe-point kind fails closed,
- resume appends attempt history,
- verifier remains completion authority.

### 11.4 Control And Review Commands

Expose explicit control intent and review recording without letting hosts own
runtime mutation.

Acceptance:

- halt writes a `ControlRequest` ref only,
- review decisions are checked for freshness,
- stale or worker-authored decisions fail closed,
- executable verifier failures cannot be overridden by review approval.

### 11.5 Validation Entrypoint

Promote `scripts/validate.sh` into the operator workflow and keep it as the
canonical repo health check.

Acceptance:

- default validation runs Node runtime tests, Python tests, and whitespace
  checks,
- local fast mode can skip `npm ci` explicitly,
- live provider tests remain opt-in.

### 11.6 Optional MissionForge JSONL RPC

Add only after the CLI semantics are stable.

Acceptance:

- protocol is refs-only,
- each command has request/response correlation,
- commands map to the same implementations as CLI,
- event output is observation only and cannot mutate runtime truth.

## Implementation Order

1. Add Phase 11 design document and align module docs.
2. Add CLI parser and command dispatch tests.
3. Implement `inspect`.
4. Implement `diagnose`.
5. Implement `run` using the existing `MissionCLI` result contract or its
   successor.
6. Implement `resume`.
7. Implement `control halt`.
8. Implement `review record`.
9. Wire `validate` to `scripts/validate.sh`.
10. Add SkillFoundry compiled-mission operator smoke.
11. Decide whether JSONL RPC is needed immediately or can remain Phase 12.

## Validation Gates

Targeted tests:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_host_cli_adapter \
  tests.test_host_observation_adapter \
  tests.test_runtime_state_ledger \
  tests.test_runtime_resume
```

Full validation:

```bash
./scripts/validate.sh
```

Future Phase 11-specific tests should cover:

- CLI inspect read-only behavior,
- CLI diagnosis reason codes,
- CLI resume safe-point rejection and success,
- CLI control halt writes intent only,
- CLI review freshness rejection,
- CLI output redaction and refs-only policy,
- SkillFoundry compiled MissionIR operator smoke.

## Completion Criteria

Phase 11 is complete when an operator can:

1. run a mission from a MissionIR ref,
2. inspect the resulting MissionRun without reading raw JSON manually,
3. diagnose why a non-success run stopped,
4. resume only from a completed-turn safe point,
5. write explicit halt control intent,
6. record or reject review decisions correctly,
7. run the canonical validation command,
8. verify that MissionForge, not PI session UI or worker self-report, remains
   the source of operational truth.

## Handoff After Phase 11

After Phase 11, MissionForge can consider:

- richer controlled LLM proposal providers,
- PI session tree inspection under attempt refs,
- a JSONL RPC or dashboard on top of the CLI command semantics,
- live provider soak as a scheduled but opt-in gate,
- persistent state backends beyond JSON files if operational scale requires it.
