# Module: Runtime Engine

## Goal

Execute Mission IR through a fixed evidence-first adaptive loop.

## Scope

- mission validation
- profile resolution and mission expansion
- frozen contract creation
- work-unit compilation from FrozenMissionContract
- controlled steering proposal selection and validation
- PiWorker execution
- observation collection
- verification
- state correction
- adaptive routing
- control request safe-point handling
- mission result emission

## Non-Goals

- no LangGraph dependency in core
- no CodexWorker support in the first design cycle
- no task-name-specific control flow
- no live LLM proposal mode by default
- no dashboard or host-owned runtime mutation

## Current Status

Phase 5 implemented the first deterministic runtime vertical slice behind the
existing `MissionRuntime.run()` facade.

The deterministic kernel pieces now composed by the runtime are:

- Phase 2: `ExpandedMission`, `FrozenMissionContract`, and `ContractManifest`
- Phase 3: evidence ledger, local validators, verifier routing, and reviewer
  decision validation
- Phase 4: proposal boundary validation, work-unit compilation, fake worker
  dispatch, decision ledger entries, and halt safe-point checks
- Phase 5: deterministic `RuntimeEngine`, `MissionRunState`, verifier-routed
  `MissionResult`, and refs-only runtime output

The runtime remains deliberately small. It does not implement a full repair
planner or any live worker/provider integration.

## Public Contracts

- `MissionRuntime`
- `MissionResult`
- `RuntimeEngine`
- `MissionRunState`

## Invariants

- Runtime decisions must be based on structured mission state and verifier
  records.
- Worker self-report is never acceptance.
- LLM proposal output is never acceptance.
- Failed constraints must route repair through constraint IDs, not log strings.
- Repair, redesign, review, stop, and escalation are separate runtime
  decisions.
- PiWorker receives WorkUnitContract, not raw MissionIR or chat history.
- Runtime commits state only after proposal, scope, authority, and evidence
  validation.
- Runtime completion comes from verifier status, not fake worker output or
  proposal confidence.
- `MissionResult` is refs-only and must not include raw prompts, transcripts,
  worker claims, or artifact bodies.
- Control requests are consumed only at safe points.

## Dependencies

- Mission IR
- context/evidence module
- harness module
- controlled steering module
- verifier module
- future PiWorker module

## Verification Strategy

- standalone runtime call without LangGraph
- deterministic fixture mission
- repair loop tests once verifier records exist
- MissionIR -> ExpandedMission -> FrozenMissionContract transition tests
- proposal acceptance and rejection tests
- control request safe-point tests
- repair versus redesign routing tests

## Verification Evidence

Phase 5:

```bash
PYTHONPATH=src python3 -m unittest tests/test_ir.py tests/test_runtime_vertical_slice.py tests/test_runtime_routes.py tests/test_runtime_refs_only.py
# Ran 9 tests: OK
```

## Open Questions

- What state is durable versus derived?
- What is the exact resume boundary?
- How should user steering interrupt a running PiWorker attempt?
- Where should MissionRun live: JSONL ledger, SQLite, or pluggable store?
- How much of the Phase 5 deterministic route should become reusable repair
  planner machinery?
