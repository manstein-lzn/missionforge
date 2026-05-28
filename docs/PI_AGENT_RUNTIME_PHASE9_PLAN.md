# PI Agent Runtime Phase 9 Plan

## Objective

Upgrade the dedicated `pi-agent-runtime` from a one-shot worker into a
session-aware worker that can save progress, receive verifier-driven repair
follow-ups, stop at safe points, and preserve enough state for later resume
work.

Implementation status: completed for the offline Phase 9 hardening slice on
2026-05-28. The implementation adds savepoints, structured repair envelopes,
bounded verifier repair routing, safe-point cancellation, completed-turn resume
hints, and compaction markers without changing the single-worker architecture.
The optional live smoke remains opt-in and should be rerun only when live
provider spending is intended.

This phase starts after the Phase 6 live provider validation. The production
architecture remains:

```text
MissionRuntime -> WorkUnitContract -> pi-agent-runtime -> ExecutionReport -> Verifier
```

Phase 9 must not introduce a second worker, a worker registry, or a command
PiWorker compatibility path.

## Current Position

Completed before this phase:

- `pi-agent-runtime` is the only production worker.
- `MissionRuntime` defaults to `PiAgentRuntimeAdapter`.
- The worker uses PI Agent core, PI AI, and PI coding-agent tools.
- The full coding tool surface is available by default:
  `read`, `bash`, `edit`, `write`, `grep`, `find`, and `ls`.
- Faux mode is deterministic and offline.
- Live mode uses current Codex provider config as opt-in.
- Live smoke has passed against the current Codex config.

Phase 9 lands the next runtime capability step:

```text
one-shot execution
  -> turn save points
  -> verifier repair follow-up
  -> safe cancellation
  -> resumable attempt boundary
  -> transcript compaction
```

## Goals

- Write a save point after each completed assistant turn.
- Preserve enough structured state to continue or inspect an attempt without
  reading raw transcript bodies from reports.
- Let MissionForge pass verifier failures back to the worker as structured
  repair instructions.
- Support a first repair continuation path using PI Agent follow-up behavior.
- Keep abort and halt behavior at explicit safe points.
- Define the first resume boundary without claiming mid-tool resume support.
- Add conservative transcript compaction for long sessions.
- Keep verifier authority as the only completion authority.

## Non-Goals

- Do not add another production worker.
- Do not restore command PiWorker.
- Do not expose public worker runtime selection.
- Do not import PI's full TUI or product shell.
- Do not remove `bash`.
- Do not constrain the worker's normal tool choices beyond workspace, timeout,
  budget, evidence, and secret boundaries.
- Do not claim support for resuming an in-flight tool call or running shell
  process.
- Do not make live LLM execution default in tests.

## Invariants

- Worker self-report is evidence only.
- MissionForge verifier decides completion.
- Runtime output and `MissionResult` remain refs-only.
- Provider credentials are child-process environment only.
- API keys and authorization headers must not appear in input, output,
  session, events, metrics, reports, stdout/stderr captures, or docs.
- Control requests are consumed only at safe points.
- Repair prompts are derived from structured verifier/runtime state, not
  free-form log scraping.
- Failed constraints must remain addressable by constraint IDs.

## New Attempt Artifacts

Add one new artifact in Phase 9:

```text
attempts/<work_unit_id>/pi_agent_savepoints.jsonl
```

Each line is one completed-turn save point:

```json
{
  "schema_version": "missionforge.pi_agent_runtime_savepoint.v1",
  "work_unit_id": "WU-000001",
  "turn_index": 1,
  "created_at": "2026-05-28T00:00:00Z",
  "message_ref": "attempts/WU-000001/pi_agent_session.jsonl#entry=3",
  "events_ref": "attempts/WU-000001/pi_agent_events.jsonl",
  "changed_refs": ["package/SKILL.md"],
  "tool_call_count": 2,
  "commands_run": ["npm test"],
  "stop_reason": "toolUse",
  "token_count": 1234,
  "resume_hint": {
    "supported": true,
    "boundary": "after_completed_turn"
  }
}
```

Save points must be summaries and refs. They must not embed full transcripts,
large tool output, provider payloads, or secret values.

Implemented behavior:

- Node writes `pi_agent_savepoints.jsonl` from
  `workers/pi-agent-runtime/src/evidence-recorder.ts` after `turn_end`.
- Runtime outputs, adapter results, and execution reports carry the savepoint
  artifact by ref only.
- Savepoints carry `resume_hint.boundary = "after_completed_turn"` and list
  unsupported resume modes explicitly.
- Savepoint payloads are passed through the same redaction path as events and
  session summaries.

## Contract Extension

Extend the runtime input with optional repair state:

```json
{
  "repair": {
    "mode": "none",
    "verifier_failures": [],
    "failed_constraints": [],
    "previous_output_ref": null,
    "repair_prompt": null
  }
}
```

Supported modes for the first implementation:

- `none`: normal first attempt.
- `follow_up`: continue the attempt with a verifier-derived repair instruction.

Do not add a separate repair worker. Repair is behavior on the same
`pi-agent-runtime` worker.

Implemented behavior:

- Node contract validation defaults missing `repair` to `mode = "none"`.
- `follow_up` requires verifier failures or failed constraints,
  `previous_output_ref`, and `repair_prompt`.
- Python adapter config exposes the same repair envelope and `with_repair()`
  clones the same adapter into follow-up mode.
- Runtime repair routing calls `with_repair()` on the current worker when the
  verifier fails and `max_attempts` still allows one bounded retry.

## Phase 9 Workstreams

### 9.1 Baseline Closure

Status: completed.

Before coding, keep the Phase 6 baseline green:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
npm test --prefix workers/pi-agent-runtime
npm run build --prefix workers/pi-agent-runtime
git diff --check
```

If the MetaLoop capsule still has a delegable review gate, close it through an
independent reviewer when authorized. Do not block implementation on that gate
when hard validators are already green, but do not claim independent review
has happened until it has.

### 9.2 Save Points

Status: completed.

Implement turn save points in the Node runtime.

Primary files:

- `workers/pi-agent-runtime/src/contract.ts`
- `workers/pi-agent-runtime/src/evidence-recorder.ts`
- `workers/pi-agent-runtime/src/runtime.ts`
- `workers/pi-agent-runtime/src/result-writer.ts`
- `src/missionforge/adapters/pi_agent_runtime.py`

Acceptance:

- Faux mode writes `pi_agent_savepoints.jsonl`.
- One save point exists after each completed assistant turn.
- Save points contain refs and summaries, not raw artifact bodies.
- Save points are redacted.
- Execution reports include the savepoint artifact by ref only.

### 9.3 Repair Input Contract

Status: completed.

Add Python and Node validation for the optional repair envelope.

Primary files:

- `workers/pi-agent-runtime/src/contract.ts`
- `src/missionforge/adapters/pi_agent_runtime.py`
- `tests/test_pi_agent_runtime_adapter.py`
- `workers/pi-agent-runtime/tests/contract.test.mjs`

Acceptance:

- Missing `repair` defaults to `mode = "none"`.
- Unknown repair modes fail validation.
- `follow_up` requires structured verifier failure data.
- Repair fields reject absolute refs and path traversal.
- Repair metadata cannot contain sensitive keys.

### 9.4 Faux Repair Loop

Status: completed as a deterministic runtime repair route.

Implement deterministic repair behavior before touching live repair.

The faux provider should simulate:

1. first attempt writes an incomplete or invalid artifact,
2. verifier reports failure,
3. MissionForge sends a repair follow-up,
4. worker writes the corrected artifact,
5. verifier owns final acceptance.

Primary files:

- `workers/pi-agent-runtime/src/runtime.ts`
- `workers/pi-agent-runtime/tests/faux-runtime.test.mjs`
- `src/missionforge/runtime.py`
- `tests/test_runtime_vertical_slice.py`

Acceptance:

- A worker `completed` claim does not bypass verifier failure.
- A verifier failure can route to a single repair attempt.
- The repair attempt references previous output and verifier evidence.
- Max repair attempts prevent infinite loops.

### 9.5 Runtime Repair Routing

Status: completed for one bounded follow-up attempt.

Connect verifier failure records to repair work-unit execution.

MissionForge should derive repair instructions from structured verifier
records:

- failed constraint IDs,
- missing expected outputs,
- invalid refs,
- local validator failures,
- reviewer/verifier decisions when present.

Acceptance:

- Runtime can distinguish repair from redesign.
- Failed constraints stay structured.
- Repair prompt is stored by ref or compact field, not as a raw report body.
- Verifier still decides final `MissionResult`.

### 9.6 Abort And Cancellation

Status: completed for worker safe-point cancellation.

Add safe-point cancellation semantics.

Safe points:

- before worker invocation,
- after each assistant turn,
- before repair follow-up,
- after verifier result,
- before committing final runtime state.

Output behavior:

```json
{
  "status": "cancelled",
  "verification_status": "failed",
  "recommended_next_steps": ["Run was cancelled at a MissionForge safe point."]
}
```

Acceptance:

- Halt before invocation does not start the worker.
- Halt after a turn produces normalized output artifacts.
- Cancelled output is never mapped to verifier success.
- Events and metrics are still written when cancellation is graceful.

### 9.7 Resume Boundary

Status: completed as an explicit artifact and documentation boundary.

Define the first resume boundary and artifact contract.

Supported first:

- resume after a completed assistant turn,
- reconstruct continuation context from session summaries and save points,
- continue with a verifier or user follow-up prompt.

Explicitly unsupported first:

- mid-tool-call resume,
- resuming an active shell process,
- recovering partial provider streams,
- automatically replaying uncommitted filesystem mutations.

Acceptance:

- Docs state the resume boundary.
- Savepoint schema carries enough information for future resume work.
- Runtime does not claim resume support where it cannot provide it.

### 9.8 Transcript Compaction

Status: completed as conservative marker-based compaction support.

Add conservative compaction after save points and repair are stable.

Compaction policy:

- keep recent turn detail,
- summarize older turns,
- keep artifact refs and changed refs,
- keep failed constraint IDs,
- drop raw large tool output from provider-visible context,
- never compact away verifier authority or stop conditions.

Acceptance:

- Long faux sessions can trigger compaction.
- Compaction creates an event and savepoint marker.
- Reports remain refs-only.
- Secrets remain redacted after compaction.

### 9.9 Final Hardening

Status: completed for required offline validators.

Complete failure coverage:

- max turns,
- tool timeout,
- provider error,
- invalid repair contract,
- missing savepoint artifact,
- cancelled run,
- verifier failure after repair,
- repair max-attempt exhaustion,
- output contract rewrite after repair failure.

Acceptance:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
npm test --prefix workers/pi-agent-runtime
npm run build --prefix workers/pi-agent-runtime
git diff --check
```

Optional live check:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 MISSIONFORGE_PI_AGENT_MAX_TURNS=4 \
MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS=30 \
PYTHONPATH=src python3 -m unittest tests.test_pi_agent_runtime_live_smoke
```

## Implementation Order Landed

1. Add savepoint schema and writer.
2. Add Python adapter refs for savepoints.
3. Add repair input contract validation.
4. Add deterministic faux repair loop.
5. Connect RuntimeEngine verifier failure routing to repair.
6. Add safe-point cancellation output.
7. Define resume boundary in docs and artifacts.
8. Add transcript compaction.
9. Harden all failure modes and rerun full validation.

This order keeps every step offline-testable and avoids weakening the current
live provider path.

## Completion Audit

Phase 9 acceptance is mapped to implementation and tests as follows:

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Savepoints after completed turns | `EvidenceRecorder.record()` writes savepoints on `turn_end`; output/report refs include `savepoints_ref`. | `workers/pi-agent-runtime/tests/faux-runtime.test.mjs`; `tests/test_pi_agent_runtime_adapter.py` |
| Savepoints are refs-only and redacted | Savepoints store summaries, refs, token/tool counts, commands, and resume hints; payloads use `redactJson()`. | `faux runtime does not serialize api keys` Node test |
| Repair input contract | Node `RepairInput` and Python `PiAgentRuntimeConfig` validate modes, refs, and required fields. | `workers/pi-agent-runtime/tests/contract.test.mjs`; `tests/test_pi_agent_runtime_adapter.py` |
| Verifier-driven bounded repair | `RuntimeEngine` derives repair prompts from structured verifier failures and calls `worker.with_repair()` once when `max_attempts > 1`. | `tests/test_runtime_routes.py::test_verifier_failure_routes_to_bounded_repair_attempt` |
| Same worker, no registry | Repair is adapter behavior on `PiAgentRuntimeAdapter`; no command PiWorker or worker registry is added. | `src/missionforge/runtime.py`; `src/missionforge/adapters/pi_agent_runtime.py` |
| Cancellation is non-success | Node cancellation writes `status = "cancelled"` and `verification_status = "failed"`. | `workers/pi-agent-runtime/tests/faux-runtime.test.mjs` |
| Resume boundary is honest | Savepoint `resume_hint` supports only `after_completed_turn` and lists unsupported mid-tool/shell/provider-stream modes. | Savepoint schema and Node faux savepoint test |
| Compaction marker | Long sessions can write a `compaction` event and savepoint marker after a completed turn. | `faux runtime compaction writes a savepoint marker` Node test |
| Contract rewrite/failure hardening | Python adapter rewrites invalid or out-of-scope output as failed normalized output with savepoint refs. | `tests/test_pi_agent_runtime_adapter.py` |
| Full offline validation | Python tests, Node tests, TypeScript build, and diff whitespace checks pass. | Verification commands below |

## Verification Evidence

Required validators run after implementation:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 157 tests in 4.410s: OK (skipped=1)

npm test --prefix workers/pi-agent-runtime
# 15 tests passed

npm run build --prefix workers/pi-agent-runtime
# OK
```

`git diff --check` also passed after this documentation update.

The optional live smoke was not rerun for this documentation update. It remains
available:

```bash
MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 MISSIONFORGE_PI_AGENT_MAX_TURNS=4 \
MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS=30 \
PYTHONPATH=src python3 -m unittest tests.test_pi_agent_runtime_live_smoke
```

## Deferred Work

Phase 9 deliberately does not claim full process resume. The durable boundary is
`after_completed_turn`; mid-tool-call resume, active shell recovery, partial
provider stream recovery, and automatic replay of uncommitted filesystem
mutations remain unsupported.

Future work can build a resume command on top of the savepoint/session artifacts
and can expand repair planning beyond one bounded follow-up attempt, but that
should remain verifier-governed and keep the single `pi-agent-runtime` worker
path.

## Completion Criteria

Phase 9 is complete when:

- savepoints are written on every completed turn,
- structured repair follow-up works in faux mode,
- runtime verifier failure can route to one bounded repair attempt,
- cancellation produces normalized non-success output,
- resume boundaries are documented and represented in artifacts,
- compaction is available for long sessions,
- all required Python and Node validators pass,
- optional live smoke still passes when enabled.
