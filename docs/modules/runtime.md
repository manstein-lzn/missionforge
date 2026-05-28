# Module: Runtime Engine

## Goal

Execute Mission IR through a fixed evidence-first adaptive loop.

## Scope

- mission validation
- profile resolution and mission expansion
- frozen contract creation
- work-unit compilation from FrozenMissionContract
- controlled steering proposal selection and validation
- PI Agent runtime worker execution
- observation collection
- verification
- state correction
- adaptive routing
- control request safe-point handling
- mission result emission

## Non-Goals

- no LangGraph dependency in core
- no CodexWorker support
- no public multi-worker runtime selection
- no task-name-specific control flow
- no live LLM proposal mode by default
- no dashboard or host-owned runtime mutation

## Current Status

Phase 5 implemented the first deterministic runtime vertical slice behind the
existing `MissionRuntime.run()` facade. The runtime now defaults to the
dedicated `PiAgentRuntimeAdapter`, which invokes
`workers/pi-agent-runtime` in faux mode for deterministic offline execution.
Phase 6 completed the opt-in live provider path against the current Codex
configuration while keeping default tests offline.
Phase 9 completed the offline session/repair hardening slice: PI Agent runtime
attempts now produce completed-turn savepoints, accept structured verifier
repair follow-ups, can route one bounded repair attempt through the same worker,
write normalized safe-point cancellation output, expose an honest completed-turn
resume boundary, and emit compaction markers for long sessions.

The deterministic kernel pieces now composed by the runtime are:

- Phase 2: `ExpandedMission`, `FrozenMissionContract`, and `ContractManifest`
- Phase 3: evidence ledger, local validators, verifier routing, and reviewer
  decision validation
- Phase 4: proposal boundary validation, work-unit compilation, worker
  dispatch, decision ledger entries, and halt safe-point checks
- Phase 5: deterministic `RuntimeEngine`, `MissionRunState`, verifier-routed
  `MissionResult`, and refs-only runtime output
- PI Agent runtime: Node/TypeScript PI Agent worker with faux provider tests,
  event/session/metrics artifacts, and Python adapter normalization
- Phase 6 live provider: Codex-current model/base URL/API key resolution,
  fail-closed config validation, max-turn/tool-timeout runtime boundaries, and
  an opt-in live smoke test
- Phase 9 session hardening: savepoint artifacts, structured repair envelopes,
  verifier-driven bounded repair routing, safe-point cancellation, completed
  turn resume hints, and transcript compaction markers. The detailed record is
  `docs/PI_AGENT_RUNTIME_PHASE9_PLAN.md`.
- Phase 10 runtime hardening is planned in
  `docs/PI_AGENT_RUNTIME_PHASE10_RUNTIME_HARDENING_PLAN.md` and completed for
  the offline hardening slice: durable run ledgers, refs-only attempt ledgers
  that preserve resume history, read-only status, completed-turn resume,
  explicit retry/repair/redesign metrics, failure injection, artifact hygiene,
  and opt-in live soak.

The runtime remains deliberately small. It does not expose a product-level
worker registry or competing worker choices.

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
- PI Agent runtime receives WorkUnitContract, not raw MissionIR or chat
  history.
- Runtime commits state only after proposal, scope, authority, and evidence
  validation.
- Runtime completion comes from verifier status, not worker output or
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
- `workers/pi-agent-runtime`

## Verification Strategy

- standalone runtime call without LangGraph
- deterministic fixture mission
- repair loop tests once verifier records exist
- MissionIR -> ExpandedMission -> FrozenMissionContract transition tests
- proposal acceptance and rejection tests
- control request safe-point tests
- repair versus redesign routing tests
- PI Agent savepoint, cancellation, compaction, and repair envelope tests
- runtime hardening tests for run ledgers, status, resume, failure injection,
  artifact hygiene, and live soak

## Verification Evidence

Phase 5:

```bash
PYTHONPATH=src python3 -m unittest tests/test_ir.py tests/test_runtime_vertical_slice.py tests/test_runtime_routes.py tests/test_runtime_refs_only.py
# Ran 9 tests: OK
```

Phase 9:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 157 tests: OK (skipped=1)

npm test --prefix workers/pi-agent-runtime
# 15 tests passed
```

Phase 10:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 168 tests: OK (skipped=2)

npm test --prefix workers/pi-agent-runtime
# 17 tests passed
```

## Open Questions

- Phase 11 should decide CLI/product UX on top of the Phase 10 durable state.
- Broader process resume remains unsupported beyond completed-turn resume.
- A future implementation may add real bounded retry execution for transient
  provider/tool failures; Phase 10 records retry metrics and separates routes.
- JSON artifacts are sufficient for the current runtime hardening slice; SQLite
  or a pluggable store remains a future scaling decision.
