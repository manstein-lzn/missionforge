# Module: PiWorker

## Goal

Historical PiWorker adapter notes for the earlier compatibility path.

The current production direction is `pi-agent-runtime`, not PiWorker. The
dedicated PI Agent runtime is documented in
`docs/PI_AGENT_RUNTIME_IMPLEMENTATION_PLAN.md`.

## Scope

- PiWorker work-unit input
- PiWorker event stream
- tool-mediated workspace reads/writes
- provider usage metrics
- cache metrics
- refs-only output evidence
- optional contract adjustment request evidence

## Non-Goals

- no CodexWorker support
- no multi-worker abstraction
- no provider-specific policy in core runtime
- no PiWorker-owned acceptance, closure, or contract revision

## Current Status

Goal 6A implemented a deterministic faux PiWorker adapter. The adapter proves
MissionForge's PiWorker-facing contract boundary without starting a live
PiWorker process, loading provider credentials, calling a live LLM, depending
on LangGraph or HTTP, or importing SkillFoundry adapter behavior.

The live-provider integration slice now adds an opt-in command-boundary
adapter. The deterministic faux adapter remains available and default tests
remain offline. The command adapter writes a bounded PiWorker input artifact,
invokes an injected runner or subprocess sidecar, reads normalized output,
records refs-only evidence, and returns `WorkerAdapterResult`.

Current live provider support reads the current Codex config/auth at runtime
when `provider_config_source="codex_current"`. It maps model/base URL/API key
into child-process environment variables and never serializes the API key into
MissionForge input artifacts, evidence, execution reports, metrics, docs, or
logs.

This module is now legacy reference material. MissionForge's default runtime
uses `PiAgentRuntimeAdapter`, which invokes `workers/pi-agent-runtime`.

## Attribution

The PI GitHub project is MIT-licensed. MissionForge is inspired by PI. The
initial MissionForge skeleton does not copy PI source code. Any future copied or
adapted PI source must retain required attribution.

## Public Contracts

Implemented in Goal 6A:

- `WorkerAdapter`
- `WorkerAdapterResult`
- `PiWorkerInput`
- `PiWorkerOutput`
- `PiWorkerEvent`
- `PiWorkerMetrics`
- `ContractAdjustmentEvidence`
- `PiWorkerRunResult`
- `PiWorkerProviderEnvironment`

## Contract Sketch

`PiWorkerInput` should be derived from a committed `WorkUnitContract` and an
attempt manifest:

```json
{
  "input_id": "piworker-input-001",
  "work_unit_ref": "work_units/WU-000001.json",
  "attempt_manifest_ref": "attempts/WU-000001/input_manifest.json",
  "allowed_scope": ["attempts/WU-000001"],
  "visible_refs": ["mission/frozen_contract.json"],
  "expected_outputs": ["attempts/WU-000001/artifact.txt"]
}
```

`PiWorkerEvent` should be refs-first and evidence-safe:

```json
{
  "event_id": "piworker-event-001",
  "work_unit_id": "WU-000001",
  "event_type": "artifact_written",
  "artifact_refs": ["attempts/WU-000001/artifact.txt"],
  "evidence_refs": ["evidence/E-000001.json"],
  "metrics": {
    "tool_call_count": 1
  }
}
```

Provider, cache, token, and tool metrics are metrics/evidence. They are not
runtime route logic.

## Implemented Adapter Behavior

- `FauxPiWorkerAdapter` accepts committed `WorkUnitContract` objects only.
- Raw `MissionIR`, raw `SteeringProposal`, dict-like input, and output refs
  outside `WorkUnitContract.allowed_scope` are rejected.
- Expected outputs are written deterministically under the workspace using
  safe relative refs.
- Invocation, artifact, metrics, optional contract-adjustment, and completion
  events are appended to the evidence ledger.
- `ExecutionReport` contains refs, evidence refs, empty worker claims, and
  metrics only. It does not embed artifact bodies, raw prompts, transcripts,
  provider credentials, or worker claim bodies.
- Worker-requested contract adjustment is stored as evidence and linked from
  the execution report. It does not revise the work unit or frozen mission
  contract.
- Adapter status and metrics are not completion authority. Completion remains
  owned by verifier output.

## Command Adapter Behavior

The command PiWorker behavior was superseded by `pi-agent-runtime`. Historical
command adapter code and tests were removed after the dedicated PI Agent
runtime reached offline parity.

## Legacy Invariants

- PiWorker receives a bounded work-unit contract.
- PiWorker writes only through allowed tools or write scopes.
- PiWorker output is evidence, not acceptance.
- Metrics are preserved in MissionResult evidence.
- PiWorker consumes committed WorkUnitContract objects, not raw steering
  proposals.
- PiWorker command execution is optional and is not the default runtime path.
- Live provider credentials are child-process environment only.
- Any worker-requested contract adjustment is evidence for controlled steering,
  not a mutation of the frozen mission contract.
- MissionForge core must not import the PiWorker adapter.
- Faux PiWorker tests must pass before any live PiWorker smoke.

## Dependencies

- Mission IR
- work-unit harness
- context/evidence
- controlled steering for contract adjustment requests
- adapter contracts

## Verification Strategy

- faux PiWorker fixture
- import-boundary tests proving core does not import the adapter
- event stream completeness checks
- token/cache metrics checks
- worker contract adjustment request is recorded but not auto-committed
- verifier authority test proving adapter `completed` status does not grant
  completion
- live PiWorker smoke after deterministic path is stable

## Verification Evidence

Goal 6A focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_piworker_adapter_contracts.py tests/test_faux_piworker_adapter.py tests/test_piworker_import_boundaries.py tests/test_adapter_import_boundaries.py
# Ran 16 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 106 tests: OK

git diff --check
# passed
```

Independent reviewer `Confucius` approved Goal 6A, and MetaLoop verification
reached `completed_verified`.

PI Agent runtime cutover evidence is tracked in
`docs/PI_AGENT_RUNTIME_IMPLEMENTATION_PLAN.md`.

## Superseded Follow-On Goal

This old launch prompt is retained only as historical context:

```text
/goal 使用 $metaloop 按 docs/FOLLOW_ON_GOALS.md 的 Goal 6A 实现
MissionForge Faux PiWorker Adapter。实现 deterministic faux adapter、
event-to-evidence mapping、refs-only ExecutionReport、import-boundary tests。
不要接 live PiWorker、provider credentials、live LLM、LangGraph、HTTP 或
SkillFoundry adapter。
```

## Open Questions

- How should user steering interrupt a live PiWorker session?
- Which PI runtime concepts should remain internal to the adapter?
- How should provider profiles be declared without leaking credentials?
- Which PiWorker event types should map to evidence reliability levels?
