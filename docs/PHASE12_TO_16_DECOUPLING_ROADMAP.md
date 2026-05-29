# Phase 12-16 Decoupling Roadmap

Last updated: 2026-05-29

Status: `implemented`

## Document Role

This document turns the post-Phase-11 direction into implementation-ready
planning for Phase 12 through Phase 16.

The goal is not to add more product behavior first. The goal is to harden
MissionForge as a generic substrate by removing the next likely coupling
points:

```text
metrics dicts -> typed metric ledger
RuntimeEngine body -> small internal runtime helpers
MissionRuntime worker construction -> PiWorker runtime boundary
contract adjustment artifacts -> real mission revision workflow
JSON file details -> store protocols with JSON backends
```

The roadmap follows the adapter cleanup decision in
`docs/PRODUCT_INTEGRATION_BOUNDARY.md`: product-specific task semantics belong
outside the `missionforge` Python package, while reusable task features belong
in MissionIR, profiles, validators, and evidence requirements.

This roadmap is also a complexity-control document. Phase 12 through Phase 16
should prevent applications from modifying MissionForge internals for their
own task semantics. They should not turn MissionForge into a generic workflow
engine, worker marketplace, observability platform, or database framework.

## Current Baseline

MissionForge currently has:

- MissionIR validation, profile expansion, and frozen contract hashing
- evidence ledger and verifier-owned closure
- PI Agent runtime adapter as the production worker path
- PiWorker/PI Agent as the only supported LLM worker direction
- durable MissionRun, RuntimeAttempt, safe-point resume, and artifact hygiene
- controlled steering contracts, run-local steering artifacts, and opt-in
  provider injection
- Phase 11 operator commands and optional JSONL RPC
- external SkillFoundry integration under `integrations/skillfoundry/`

The remaining coupling risks are not primarily missing features. They are
boundary risks:

- `metrics: dict[str, Any]` is used as a shared loose bag across runtime,
  worker adapters, steering, state, and operator diagnosis.
- `RuntimeEngine` composes too many concerns directly.
- `MissionRuntime` still constructs the PI Agent runtime adapter directly.
- controlled steering has contract-adjustment and repair-strategy artifacts,
  but no full mission revision workflow yet.
- JSON files are an effective current backend, but runtime code should not grow
  around backend-specific storage details.

## Global Principles

These principles apply to all five phases.

1. Mission truth remains `MissionIR -> ExpandedMission ->
   FrozenMissionContract -> EvidenceLedger -> VerificationResult`.
2. Task features belong in profiles, validators, and evidence requirements,
   not adapters or runtime branches.
3. Metrics are diagnostics and observability. Metrics do not prove facts,
   expand authority, or close missions.
4. Runtime routing must use structured state, verifier status, failed
   constraint IDs, safe points, and authority gates, not adapter-private metric
   fields.
5. Public APIs should remain stable unless a phase explicitly documents a
   migration path.
6. Default runtime and default tests remain deterministic and offline.
7. JSON remains the default storage backend until a later phase explicitly
   changes the backend.
8. PiWorker/PI Agent is the only LLM worker direction. Architecture boundaries
   protect MissionForge truth from PiWorker internals; they are not invitations
   for public multi-worker support.
9. Python remains the implementation language for these phases. A Rust or
   binary core is a future packaging/protection option after the Python
   contracts stabilize, not a current rewrite target.
10. Product and customer scenarios must extend MissionForge through MissionIR,
    profiles, validators, evidence requirements, and external integrations,
    not by patching runtime or adapter internals.
11. Each phase must leave focused tests, docs-last updates, and a clear resume
    point.

## Complexity Budget

MissionForge should keep a small number of strong primitives. The default
answer to a new abstraction is no unless it removes more complexity than it
adds.

Rules:

- no public worker registry, worker marketplace, or non-PI LLM worker path
- no dashboard platform, tracing DSL, or observability stack in these phases
- no workflow engine; mission revision is a controlled state transition
- no generic database framework; JSON remains the concrete backend
- no abstractions for hypothetical products, workers, stores, or UIs
- prefer one small helper module over a coordinator family unless the existing
  code has become materially harder to test or change
- extension pressure from user applications should be absorbed by profiles,
  validators, evidence contracts, and integration packages

## Stable Primitive Set

The long-term system should remain explainable through these primitives:

- `MissionIR`: task-independent declaration of intent, constraints, and
  acceptance structure
- `Profile`: reusable task feature expansion, not product policy
- `FrozenMissionContract`: immutable runtime contract and hash boundary
- `WorkUnitContract`: bounded unit handed to PiWorker
- `PiWorker`: the only LLM worker execution direction
- `Evidence`: refs-first facts and artifacts
- `Verifier`: completion authority
- `MissionRun`: durable run state and safe-point history
- `Revision`: explicit contract transition under authority gates
- `MetricEvent`: diagnostic measurement, never acceptance evidence

## Order

Recommended order:

```text
Phase 12: Measurement Decoupling / Metric Ledger
Phase 13: Runtime Decomposition
Phase 14: PiWorker Runtime Boundary
Phase 15: Mission Revision / Contract Adjustment Workflow
Phase 16: Store Interface
```

Why this order:

- Phase 12 removes the loose metrics bag before runtime internals are split.
- Phase 13 makes the runtime easier to change before PiWorker construction is
  isolated.
- Phase 14 removes the remaining direct PiWorker construction exception without
  adding generic worker selection.
- Phase 15 adds real adaptive revision after runtime responsibilities are
  clearer.
- Phase 16 abstracts storage after the data shapes are stable enough to avoid
  over-designing the store too early.

## Phase 12: Measurement Decoupling / Metric Ledger

Status: `implemented`

### Intent

Replace unstructured cross-module `metrics` usage with a typed metric event
ledger and deterministic metric projections.

This phase should make module measurement independently inspectable without
letting metrics become runtime truth.

### Minimal First Slice

The first implementation should be intentionally small:

- `MetricEvent`: typed, refs-first diagnostic event
- `MetricProjection`: deterministic operator-facing summary rebuilt from
  events
- `MetricStore`: JSONL-backed run-local event store
- compatibility projection into `MissionResult.metrics`
- operator `inspect` and `diagnose` reading projection refs instead of loose
  runtime dict keys

Do not build a general observability layer. This phase exists to make metrics
less coupled and less authoritative, not to add a monitoring product.

### Problem

Current metrics are spread through several contract surfaces:

- `MissionResult.metrics`
- `MissionRun.metrics`
- `RuntimeAttempt.metrics`
- `ExecutionReport.metrics`
- `AdapterResult.metrics`
- PI Agent runtime metrics
- controlled steering counters
- operator diagnosis logic

This works for the current vertical slice, but it has weak boundaries:

- no stable metric namespace
- no typed metric schema
- no clear source refs for every metric
- no metric trust or diagnostic class
- possible key collisions across modules
- operator diagnosis reads runtime metric keys directly
- adapter-private metrics can become tempting routing inputs

### Primary Files

Implemented primary files:

- `src/missionforge/metrics.py`
- `src/missionforge/metric_store.py`
- `docs/modules/metrics.md`
- `tests/test_metrics_contracts.py`
- `tests/test_metric_store.py`
- `tests/test_runtime_metric_boundaries.py`
- `tests/test_operator_metric_projection.py`

Touched/supporting files:

- `src/missionforge/runtime.py`
- `src/missionforge/runner.py`
- `src/missionforge/state.py`
- `src/missionforge/adapters/cli.py`
- `src/missionforge/adapters/pi_agent_runtime.py`
- `src/missionforge/steering_store.py`
- `docs/modules/runtime.md`
- `docs/modules/host_adapters.md`
- `docs/modules/controlled_steering.md`

### Core Contracts

#### MetricNamespace

Namespaces should make metric ownership explicit:

```text
missionforge.runtime
missionforge.verifier
missionforge.harness
missionforge.worker.pi_agent
missionforge.steering
missionforge.operator.cli
missionforge.operator.rpc
missionforge.store.json
integration.<product>
```

Rules:

- namespaces are lower-case dotted names
- `missionforge.*` is reserved for MissionForge package modules
- `integration.*` is reserved for external product integrations
- product names must not appear under `missionforge.*`

#### MetricTrustLevel

Metric trust should describe diagnostic reliability, not fact authority.

Candidate values:

```text
runtime_diagnostic
adapter_diagnostic
worker_reported
provider_reported
operator_diagnostic
store_diagnostic
integration_diagnostic
```

Rules:

- metric trust is not evidence trust
- metric trust cannot satisfy verification requirements
- worker/provider-reported metrics are operational diagnostics only

#### MetricEvent

Example:

```json
{
  "schema_version": "missionforge.metric_event.v1",
  "metric_id": "ME-000001",
  "mission_run_id": "run-sample",
  "namespace": "missionforge.worker.pi_agent",
  "source_ref": "attempts/WU-000001/pi_agent_metrics.json",
  "run_ref": "runs/run-sample/mission_run.json",
  "metric_kind": "counter",
  "values": {
    "tool_call_count": 3,
    "token_count": 1200,
    "duration_ms": 7400
  },
  "trust_level": "adapter_diagnostic",
  "tags": ["worker", "pi_agent"]
}
```

Required rules:

- refs are workspace-relative safe refs
- values are JSON-compatible scalar or shallow numeric/string/boolean values
- raw prompts, raw transcripts, provider payloads, stdout/stderr bodies,
  artifact bodies, and secrets are rejected
- every metric cites a source ref or run ref
- metric IDs are stable enough for deterministic tests

#### MetricProjection

The projection is the operator-friendly view:

```json
{
  "schema_version": "missionforge.metric_projection.v1",
  "mission_run_id": "run-sample",
  "metric_event_refs": ["runs/run-sample/metrics/events.jsonl"],
  "namespaces": {
    "missionforge.worker.pi_agent": {
      "tool_call_count": 3,
      "token_count": 1200
    },
    "missionforge.steering": {
      "proposal_count": 1,
      "rejected_proposal_count": 1
    }
  },
  "diagnostic_flags": [
    "unsafe_steering_proposal_rejected"
  ]
}
```

Rules:

- operator diagnosis reads projection fields, not arbitrary runtime dict keys
- projections are derived from events and can be rebuilt
- projections do not decide runtime status

### Runtime Integration

Phase 12 should be low-risk and mostly additive.

Required behavior:

- Runtime writes metric events for attempt count, repair state, resume count,
  verifier status, validator result count, and steering counters.
- PI Agent adapter writes worker/provider metric events or returns metric refs
  that runtime records.
- Controlled steering writes metric events for proposal count, accepted/rejected
  proposals, provider failures, reviewer packets, and observation signals.
- Operator inspect includes metric refs and a metric projection ref.
- Operator diagnose reads deterministic diagnostic flags from the projection.
- `MissionResult.metrics` remains as a backward-compatible summary, but should
  cite `metric_projection_ref`.

Forbidden behavior:

- runtime routing based on `MetricEvent.values`
- verifier success based on metrics
- reviewer authority inferred from metrics
- adapter-private metric keys consumed directly by runtime or CLI diagnosis

### Acceptance

Must pass:

- metric contracts round-trip through JSON-compatible dicts
- unsafe refs are rejected
- raw prompt/transcript/body/payload/secret-shaped fields are rejected
- namespaces are validated
- product namespaces are rejected under `missionforge.*`
- MetricStore writes events under `runs/{mission_run_id}/metrics/`
- projections are deterministic and rebuildable
- default runtime emits metric refs without changing mission result status
- operator inspect surfaces metric refs without embedding raw metric source
  bodies
- operator diagnose reads metric projection, not arbitrary runtime metric dicts
- existing default validation passes

Suggested focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_metrics_contracts.py tests/test_metric_store.py
PYTHONPATH=src python3 -m unittest tests/test_runtime_metric_boundaries.py tests/test_operator_metric_projection.py
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

### Non-Goals

- no dashboard
- no metrics database
- no Prometheus/OpenTelemetry integration
- no tracing DSL
- no generic event bus
- no cross-run analytics engine
- no live provider requirement
- no runtime behavior changes
- no removal of all `MissionResult.metrics` fields in the first slice

### Suggested Goal Prompt

```text
/goal 使用 $metaloop 按 docs/PHASE12_TO_16_DECOUPLING_ROADMAP.md 的
Phase 12 实现 Measurement Decoupling / Metric Ledger。新增 typed
MetricEvent、MetricProjection、MetricStore 和 focused tests；保持 runtime
默认行为不变，MissionResult.metrics 只做兼容 summary，operator diagnose
通过 projection 读取诊断信息。不要引入 dashboard、数据库、Prometheus、
OpenTelemetry、live provider 或 runtime routing 新语义。
```

## Phase 13: Runtime Decomposition

Status: `implemented`

### Intent

Split the largest `RuntimeEngine` responsibilities into a few internal helpers
without changing the public runtime API or default behavior.

### Problem

`RuntimeEngine` currently composes many concerns directly:

- mission validation
- profile freeze
- initial proposal creation
- steering provider context
- harness dispatch
- worker execution
- verifier routing
- reviewer packet handling
- bounded repair
- observation interpretation
- runtime state writing
- steering artifact writing
- metric summary assembly
- next-action computation

This concentration makes later controlled steering, mission revision, and store
work harder to reason about.

### Primary Files

Implemented primary files:

- `src/missionforge/runtime_attempts.py`
- `src/missionforge/runtime_state_writer.py`

Touched/supporting files:

- `src/missionforge/runtime.py`
- `tests/test_runtime_vertical_slice.py`
- `tests/test_runtime_routes.py`
- `tests/test_runtime_resume.py`
- `tests/test_runtime_failure_injection.py`
- `tests/test_controlled_steering_runtime.py`
- `docs/modules/runtime.md`

### Minimal Decomposition

Do not split the runtime into a large coordinator family in the first slice.
The useful boundary is the one that removes repeated mutation and attempt
assembly from the main loop.

#### RuntimeAttemptRunner

Owns:

- harness construction
- proposal dispatch
- PiWorker-compatible adapter execution
- `RuntimeAttempt` record input assembly

Must not:

- decide mission completion
- mutate frozen contracts
- inspect product integration details
- read metric projections as routing truth

#### RuntimeStateWriter

Owns:

- `MissionRun` writes
- `RuntimeAttempt` ledger writes
- artifact hygiene refs
- `MissionResult` refs
- safe-point state persistence

Must not:

- execute PiWorker
- validate proposals
- infer product semantics

#### Keep In `RuntimeEngine` Until Proven Otherwise

These responsibilities should remain in `RuntimeEngine` unless they become
hard to test after Phase 12:

- verifier routing
- bounded repair routing
- controlled steering authority checks
- reviewer packet routing
- next-action computation

This keeps the mental model simple: one runtime loop, with extracted attempt
execution and durable writes.

### Acceptance

Must pass:

- public `MissionRuntime.run()` and `MissionRuntime.resume()` behavior is
  unchanged
- deterministic successful mission output is unchanged except intentional
  metric refs from Phase 12
- failure, review, unsupported, repair, and resume routes still pass
- controlled steering proposal-mode tests still pass
- import-boundary tests still pass
- `RuntimeEngine` is smaller and easier to review, but still visibly owns the
  runtime loop
- no new optional dependency
- no product-specific branch

Suggested focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_runtime_vertical_slice.py tests/test_runtime_routes.py tests/test_runtime_resume.py
PYTHONPATH=src python3 -m unittest tests/test_runtime_failure_injection.py tests/test_controlled_steering_runtime.py
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

### Non-Goals

- no new runtime behavior
- no PiWorker runtime boundary refactor yet
- no mission revision workflow yet
- no store backend changes
- no broad coordinator family unless the first extraction proves insufficient

### Suggested Goal Prompt

```text
/goal 使用 $metaloop 按 docs/PHASE12_TO_16_DECOUPLING_ROADMAP.md 的
Phase 13 实现 Runtime Decomposition。先抽出最小的 attempt runner 和 state
writer，让 RuntimeEngine 继续清晰拥有主循环；保持 public API、默认行为、
验证结果和 operator surface 不变。不要引入新 runtime 语义、PiWorker
boundary refactor、mission revision、store backend 变化，或大规模 coordinator
家族。
```

## Phase 14: PiWorker Runtime Boundary

Status: `implemented`

### Intent

Remove the remaining direct PiWorker construction coupling from `MissionRuntime`
while keeping PI Agent as the only supported LLM worker path.

### Problem

The product-specific adapter cleanup removed product integrations from
`missionforge.adapters`, but `MissionRuntime` still constructs
`PiAgentRuntimeAdapter` directly. Import-boundary tests currently allow this as
a deliberate exception.

This is acceptable as a transitional default, but the cleaner boundary is:

```text
MissionRuntime delegates default PiWorker construction to a narrow factory.
The factory is PiWorker-specific, not a public worker registry.
RuntimeEngine only sees the committed worker adapter behavior.
```

This phase is about protecting runtime truth from PiWorker construction details.
It is not about supporting multiple workers.

### Primary Files

Implemented primary files:

- `src/missionforge/piworker_runtime.py`

Touched/supporting files:

- `src/missionforge/runner.py`
- `src/missionforge/runtime.py`
- `src/missionforge/workers.py`
- `src/missionforge/adapters/pi_agent_runtime.py`
- `tests/test_pi_agent_runtime_import_boundaries.py`
- `tests/test_adapter_import_boundaries.py`
- `tests/test_host_cli_adapter.py`
- `docs/modules/runtime.md`
- `docs/modules/piworker.md`

### Core Contracts

Candidate narrow factory:

```python
class PiWorkerRuntimeFactory:
    def create_default_worker(self) -> WorkerAdapter:
        ...
```

Or a function-level boundary if that fits the current code better:

```python
def create_default_piworker_adapter(config: PiWorkerRuntimeConfig | None = None) -> WorkerAdapter:
    ...
```

Rules:

- names should say `piworker` or `pi_agent`, not generic `worker_provider`, if
  there is only one supported LLM worker
- the public `MissionRuntime` API may keep a simple default constructor
- explicit injection remains useful for tests, but it is not a product-facing
  worker selection surface
- `RuntimeEngine` receives a worker-compatible object and does not construct
  PI Agent internals

### Required Behavior

- `RuntimeEngine` continues to accept an already-created worker object.
- `MissionRuntime` can be constructed with an injected worker for tests or
  controlled internal use.
- The current public PI Agent default path remains available and remains the
  only LLM worker direction.
- The direct allowed import from `runner.py` to
  `missionforge.adapters.pi_agent_runtime` is removed or isolated behind the
  documented PiWorker runtime boundary.
- Resume and repair still clone workers through adapter-supported methods.
- Default validation remains offline.

### Acceptance

Must pass:

- existing host CLI and runtime tests pass
- PI Agent runtime adapter tests pass
- import-boundary tests no longer need the current direct runner exception, or
  the exception is reduced to a documented PiWorker factory boundary
- runtime core does not import product integrations
- no public multi-worker selection UI is introduced
- no public generic worker registry is introduced
- verifier remains completion authority

Suggested focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_pi_agent_runtime_import_boundaries.py tests/test_adapter_import_boundaries.py
PYTHONPATH=src python3 -m unittest tests/test_host_cli_adapter.py tests/test_runtime_vertical_slice.py tests/test_runtime_resume.py
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

### Non-Goals

- no public multi-worker registry
- no non-PI worker implementation
- no worker marketplace
- no product-specific worker selection
- no live provider default requirement
- no claim that MissionForge implementation supports arbitrary LLM workers
- no new abstraction whose only purpose is hypothetical future workers

### Suggested Goal Prompt

```text
/goal 使用 $metaloop 按 docs/PHASE12_TO_16_DECOUPLING_ROADMAP.md 的
Phase 14 实现 PiWorker Runtime Boundary。去掉 MissionRuntime 对
PiAgentRuntimeAdapter 的直接硬编码，保留 PI Agent/PiWorker 作为唯一 LLM
worker 默认路径，并让 RuntimeEngine 只接收已创建的 worker-compatible
对象。不要做 public multi-worker registry、非 PI worker、产品 worker 选择、
通用 worker 平台或 live-provider 默认行为。
```

## Phase 15: Mission Revision / Contract Adjustment Workflow

Status: `implemented`; runtime consumption repair is completed in
`docs/PHASE15_REVISION_RUNTIME_REPAIR_PLAN.md`.

### Intent

Turn existing controlled steering contract-adjustment artifacts into a real,
auditable mission revision workflow.

This must stay a small state transition protocol, not a workflow engine.

### Problem

MissionForge already has:

- `ContractAdjustmentRequest`
- `RepairStrategyProposal`
- `ReviewPacket`
- `ReviewerDecision`
- `StateCorrection`

These contracts let providers and reviewers express controlled changes, but the
runtime does not yet have a full workflow for:

```text
adjustment request -> authority check -> revision decision ->
new FrozenMissionContract -> resumed/restarted work under the new contract
```

Without this workflow, complex adaptive work can only be represented as repair
or redesign hints rather than a durable revision path.

### Minimal First Slice

The first slice should implement one controlled transition:

```text
ContractAdjustmentRequest
  -> authority check
  -> MissionRevisionDecision
  -> MissionRevision
  -> new FrozenMissionContract when allowed
```

The runtime should only consume the new contract after the revision record is
written and the contract hash is explicit.

The first implementation added the contracts, conservative workflow, and
revision store. The repair in
`docs/PHASE15_REVISION_RUNTIME_REPAIR_PLAN.md` makes recorded revisions become
the active contract state for subsequent runtime work.

### Primary Files

Implemented primary files:

- `src/missionforge/revision.py`
- `src/missionforge/revision_store.py`
- `tests/test_mission_revision_contracts.py`
- `tests/test_mission_revision_workflow.py`
- `tests/test_revision_authority_boundaries.py`

Touched/supporting files:

- `src/missionforge/steering.py`
- `src/missionforge/review.py`
- `src/missionforge/runtime.py`
- `src/missionforge/freeze.py`
- `src/missionforge/state.py`
- `src/missionforge/steering_store.py`
- `docs/modules/controlled_steering.md`
- `docs/modules/runtime.md`

### Core Contracts

#### MissionRevisionRequest

Represents a request to create a new mission contract version.

Fields should likely include:

- `schema_version`
- `revision_id`
- `mission_run_id`
- `base_contract_ref`
- `base_contract_hash`
- `request_ref`
- `requested_change`
- `authority_required`
- `evidence_refs`
- `proposal_refs`
- `reason`
- `risk_if_rejected`

#### MissionRevisionDecision

Records the authority outcome:

- approved
- rejected
- needs_review
- human_authority_required
- redesign_required

#### MissionRevision

Records the durable revision:

- old contract ref/hash
- new contract ref/hash
- revision decision ref
- changed fields summary
- carried evidence refs
- invalidated refs, if any
- next runtime route

### Workflow

Nominal route:

```text
ContractAdjustmentRequest
  -> schema/ref/authority validation
  -> reviewer or human gate if required
  -> MissionRevisionDecision
  -> apply allowed change to MissionIR/profile input or expanded contract source
  -> freeze new contract
  -> write MissionRevision
  -> route next work unit under new contract hash
```

Allowed first-slice changes should be conservative:

- shrink work scope
- split work unit
- reorder repair strategy
- require review

High-risk changes should not auto-apply in the first slice:

- expand write scope
- expand authority
- weaken blocking validators
- replace executable validators with reviewer approval
- silently change user-reserved authority

### Acceptance

Must pass:

- revision contracts round-trip
- stale base contract hashes are rejected
- unsupported changes fail closed
- harness-authorized shrink/split/reorder can be recorded safely
- authority-required changes route to review or human gate
- reviewer approval cannot override failed executable validators
- user-reserved human authority remains human-only
- new frozen contract hash changes when revision content changes
- old contract refs remain inspectable
- MissionRun records revision refs and current contract hash
- operator inspect surfaces revision refs without embedding raw bodies

Suggested focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_mission_revision_contracts.py tests/test_revision_authority_boundaries.py
PYTHONPATH=src python3 -m unittest tests/test_mission_revision_workflow.py tests/test_controlled_steering_runtime.py
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

### Non-Goals

- no arbitrary free-form contract mutation
- no workflow engine
- no multi-step orchestration DSL
- no weakening frozen contracts without explicit revision
- no automatic expansion of authority
- no replacement of failed executable validators by review prose
- no dashboard-owned revision
- no live LLM default

### Suggested Goal Prompt

```text
/goal 使用 $metaloop 按 docs/PHASE12_TO_16_DECOUPLING_ROADMAP.md 的
Phase 15 实现 Mission Revision / Contract Adjustment Workflow。把
ContractAdjustmentRequest、RepairStrategyProposal、ReviewPacket 等现有协议
接成可审计 revision workflow，支持保守的 shrink/split/reorder/review 路线，
保持 frozen contract 不被静默弱化。不要允许自动扩权、用 reviewer 覆盖失败的
executable validator、dashboard-owned revision 或 live LLM 默认路径。
```

## Phase 16: Store Interface

Status: `implemented`

### Intent

Introduce store protocols for MissionForge durable state while keeping JSON
files as the default backend.

### Problem

Current JSON files are useful and should remain the default, but storage
concerns are gradually spreading through runtime, steering, evidence, operator,
and adapter code.

Before adding SQLite or remote stores, MissionForge should define store
interfaces and make the JSON backend explicit.

### Primary Files

Implemented primary files:

- `src/missionforge/stores.py`
- `src/missionforge/json_store.py`
- `tests/test_store_contracts.py`
- `tests/test_json_store_backend.py`
- `tests/test_runtime_store_integration.py`

Touched/supporting files:

- `src/missionforge/state.py`
- `src/missionforge/evidence_store.py`
- `src/missionforge/steering_store.py`
- `src/missionforge/metric_store.py`
- `src/missionforge/runtime.py`
- `src/missionforge/adapters/cli.py`
- `docs/modules/context_evidence.md`
- `docs/modules/runtime.md`
- `docs/modules/controlled_steering.md`

### Store Protocols

Start with a small boundary and expand only when tests prove the split is
needed:

```text
RunStore
ArtifactStore
EventLogStore
```

Initial ownership:

- `RunStore`: `MissionRun`, current contract refs, attempts, result refs, and
  safe-point state
- `ArtifactStore`: evidence, steering, review, metric, and product-independent
  artifact refs
- `EventLogStore`: append-only JSONL ledgers such as attempts, controls,
  metrics, and revision events

Do not create one protocol per JSON file in the first implementation. If a
sub-store becomes independently useful, split it after the shared boundary is
working.

### JSON Backend

The default backend remains workspace-relative JSON/JSONL files:

```text
runs/{mission_run_id}/mission_run.json
runs/{mission_run_id}/attempts.jsonl
runs/{mission_run_id}/steering/...
runs/{mission_run_id}/metrics/...
evidence/...
control/...
reviews/...
host_results/...
```

Rules:

- paths remain workspace-relative safe refs
- store APIs reject path escapes
- JSON output stays deterministic where contractually required
- JSONL append behavior is explicit
- stores return refs and contract objects, not raw bodies unless the caller is
  explicitly a store backend test

### Acceptance

Must pass:

- store protocols are documented
- JSON backend preserves current file layout
- runtime output refs remain compatible
- operator inspect and diagnose still work
- evidence ledger hash remains stable
- steering artifact collection still works
- metric store from Phase 12 uses the same storage boundary
- no SQLite dependency is introduced in this phase unless explicitly split
- default validation passes

Suggested focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_store_contracts.py tests/test_json_store_backend.py
PYTHONPATH=src python3 -m unittest tests/test_runtime_store_integration.py tests/test_runtime_state_ledger.py
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

### Non-Goals

- no SQLite implementation in the first store-interface phase
- no remote store
- no HTTP service
- no dashboard
- no general database abstraction layer
- no protocol per file unless implementation pressure proves it necessary
- no change to workspace-relative ref semantics
- no migration tool for old runs unless a focused test requires it

### Suggested Goal Prompt

```text
/goal 使用 $metaloop 按 docs/PHASE12_TO_16_DECOUPLING_ROADMAP.md 的
Phase 16 实现 Store Interface。先定义小而稳定的 RunStore、ArtifactStore、
EventLogStore，并保留 JSON 文件作为默认 backend；保持现有 refs 和 operator
inspect/diagnose 兼容。不要引入 SQLite、remote store、HTTP service、
dashboard、通用数据库抽象层或 workspace ref 语义变化。
```

## Future: Rust Core Kernel / Binary Distribution

Rust or another compiled core can be considered after Phase 12 through Phase 16
stabilize the Python contracts. It should not be used to compensate for unclear
boundaries.

Motivation:

- protect MissionForge core assets from casual invasive modification
- improve performance for validation, hashing, projection, replay, and storage
- make multi-platform distribution more predictable
- keep product integrations outside the core package boundary

Candidate Rust/core-kernel areas, in likely order:

- safe-ref validation and canonical hashing
- frozen contract validation
- metric event validation and projection
- append-only event log and replay
- mission revision state transition validation
- JSON backend acceleration, then optional SQLite or embedded store support

Non-goals for the Rust direction:

- no immediate Python rewrite
- no task-specific compiled rules
- no worker marketplace
- no hidden route where customer scenarios patch the core binary
- no performance work before the Python contract surface is stable enough to
  preserve

## Cross-Phase Acceptance Matrix

| Phase | Must Change | Must Not Change |
| --- | --- | --- |
| 12 Metrics | module metrics become typed events and projections | verifier-owned completion, default runtime behavior |
| 13 Runtime | internal runtime responsibilities are split | public `MissionRuntime` behavior |
| 14 PiWorker Boundary | PI Agent construction is isolated behind a narrow factory/boundary | PI Agent remains the only supported LLM worker path |
| 15 Revision | contract adjustment becomes auditable revision workflow | frozen contracts cannot be silently weakened |
| 16 Store | store protocols make JSON backend explicit | JSON remains default backend and refs stay compatible |

## Global Verification Commands

Every phase should end with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
git diff --check
```

If a phase touches product integrations, run explicit integration validation:

```bash
./scripts/validate_integrations.sh skillfoundry
```

## Open Questions

- Should `MetricTrustLevel` reuse `EvidenceTrustLevel`, or remain separate to
  make it impossible to confuse metric diagnostics with verification evidence?
- Should Phase 12 keep all existing `MissionResult.metrics` keys for one
  compatibility cycle, or reduce them immediately to refs and minimal summary?
- Should the PiWorker runtime factory live in core or under an adapter-facing
  namespace?
- Should mission revisions create a new MissionRun id or remain under the same
  MissionRun with revision refs?
- Is the first store boundary best expressed as exactly `RunStore`,
  `ArtifactStore`, and `EventLogStore`, or should `MetricStore` remain separate
  because Phase 12 already introduces it?
- When should SQLite be introduced: only after store protocols are stable, or
  as a separate Phase 17?
