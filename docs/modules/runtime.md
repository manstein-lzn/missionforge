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
- Controlled steering implementation: runtime now supports explicit
  `steering_mode="proposal"` with injected proposal providers, run-local
  steering artifacts, accepted/rejected decision ledger refs, optional
  observation interpreter state-correction refs, and optional reviewer provider
  resolution for delegatable manual gates. Deterministic runtime behavior
  remains the default.

The runtime remains deliberately small. It does not expose a product-level
worker registry or competing worker choices.

Phase 12-14 added the next decoupling layer:

- metrics are written as `MetricEvent` JSONL and `MetricProjection` refs under
  `runs/{mission_run_id}/metrics/`
- operator diagnosis reads metric projection flags instead of runtime-private
  metric dict keys
- attempt record assembly moved to `RuntimeAttemptRunner`
- durable state/attempt/hygiene/metric writes moved to `RuntimeStateWriter`
- `MissionRuntime` delegates default PI Agent construction to
  `PiWorkerRuntimeFactory`, so `runner.py` no longer imports the PI Agent
  adapter directly

The runtime loop still remains in `RuntimeEngine`; the extraction is limited
to attempt assembly and durable writes.

Phase 15 revision contracts are implemented, and runtime consumption of a
recorded revised contract is completed for the conservative repair slice. The
repair is documented in `docs/PHASE15_REVISION_RUNTIME_REPAIR_PLAN.md`: once a
revision is recorded, `MissionRun.current_contract_ref`,
`MissionRun.current_contract_hash`, and `MissionRun.revision_refs` remain
authoritative for later runtime work.

Phase 17-21 hardening is documented in
`docs/PHASE17_TO_21_IMPLEMENTATION_GUIDE.md`. The runtime-facing effects are:

- main durable writes route through `JsonWorkspaceStore`;
- revision activation fails closed if required refs are not present;
- operator diagnosis reads metric projections instead of loose metric dict
  route keys;
- `MissionRunAudit` provides refs-only stale/missing ref diagnostics for
  long-running missions.

## Public Contracts

- `MissionRuntime`
- `MissionResult`
- `RuntimeEngine`
- `MissionRunState`
- `RuntimeAttemptRunner`
- `RuntimeStateWriter`
- `PiWorkerRuntimeFactory`

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
- Proposal mode is opt-in. Provider output must pass the same schema, refs,
  scope, authority, and verifier-boundary checks as deterministic proposals.
- Runtime completion comes from verifier status, not worker output or
  proposal confidence.
- `MissionResult` is refs-only and must not include raw prompts, transcripts,
  worker claims, or artifact bodies.
- Control requests are consumed only at safe points.
- Metrics are diagnostics only. Runtime routing must not depend on
  `MetricEvent.values`.
- PI Agent remains the only LLM worker direction; the PiWorker boundary is not
  a public worker registry.

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
- controlled steering tests for proposal mode, observation signals, reviewer
  provider gates, optional LLM adapter isolation, and operator steering refs
- metric ledger tests for typed events, projections, runtime metric refs, and
  operator diagnosis boundaries
- run audit tests for refs-only long-run diagnostics and stale ref handling
- PiWorker runtime boundary import tests

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

Controlled steering slice:

```bash
PYTHONPATH=src python3 -m unittest tests/test_controlled_steering_runtime.py tests/test_controlled_steering_benchmark.py
# passed

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 222 tests: OK (skipped=2)
```

Phase 12-14 decoupling focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_metrics_contracts.py tests/test_metric_store.py tests/test_runtime_metric_boundaries.py tests/test_operator_metric_projection.py
# passed

PYTHONPATH=src python3 -m unittest tests/test_piworker_runtime_boundary.py tests/test_pi_agent_runtime_import_boundaries.py tests/test_adapter_import_boundaries.py
# passed
```

Phase 15 revision runtime repair:

```bash
PYTHONPATH=src python3 -m unittest tests/test_runtime_revision_preservation.py tests/test_operator_revision_surface.py tests/test_runtime_revision_consumption.py
# passed
```

## Open Questions

- Phase 11 operator/product UX is now scoped in
  `docs/PHASE11_OPERATOR_PRODUCTIZATION_PLAN.md`, with executable `/goal`
  slices in `docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md`; those slices are
  completed for the refs-only operator surface.
- Broader process resume remains unsupported beyond completed-turn resume.
- A future implementation may add real bounded retry execution for transient
  provider/tool failures; Phase 10 records retry metrics and separates routes.
- JSON artifacts are sufficient for the current runtime hardening slice; SQLite
  or a pluggable store remains a future scaling decision.
