# Controlled Steering Implementation Plan

Last updated: 2026-05-28

Status: `completed_verified`

## Document Role

This document turns MissionForge's controlled steering constitution into an
implementation plan.

It is based on:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/MISSION_IR.md`
- `docs/DEVELOPMENT_GOAL_PROTOCOL.md`
- `docs/COMPONENT_ACCEPTANCE_MATRIX.md`
- `docs/modules/controlled_steering.md`
- SkillFoundry's previous
  `docs/CONTROLLED_LLM_STEERING_UPGRADE_PLAN.md`

The SkillFoundry plan proved the right product-layer direction:

```text
LLM handles semantic uncertainty.
Code handles authority and truth boundaries.
Verifier handles reality.
Reviewer handles strategy and quality.
```

MissionForge must implement the same control principle as a product-neutral
runtime substrate, not as SkillFoundry product logic.

## Constitutional Laws

Controlled steering may only be implemented if these laws stay true.

1. Mission truth starts in `MissionIR`, is expanded through profiles, and is
   locked in `FrozenMissionContract`.
2. Chat history, raw prompts, raw transcripts, worker messages, and provider
   payloads are not operational task truth.
3. LLM output is proposal, interpretation, or review evidence. It is never
   acceptance by itself.
4. Worker self-report is never acceptance evidence.
5. Runtime state is committed only by MissionForge runtime code after contract,
   scope, ref, evidence, and authority validation.
6. Completion comes from verifier results over locked contracts and evidence
   refs, plus any required authority gate.
7. Reviewer decisions can resolve delegatable quality or manual gates, but they
   cannot override failed executable validators.
8. Frozen contract changes after execution are revisions or redesigns. Repair
   must not silently weaken the contract.
9. Provider metrics are evidence or diagnostics. They are not routing logic.
10. Default tests and default runtime behavior remain deterministic and offline.
11. SkillFoundry, dashboard, host, LangGraph, live LLM, and product registry
    semantics stay outside MissionForge core runtime.
12. Operator, CLI, RPC, and dashboard surfaces observe state or write explicit
    control intent. They do not own verifier, repair, steering, or completion
    semantics.

The short operating rule remains:

```text
LLM proposes.
Harness validates boundaries.
Runtime commits state.
Verifier proves facts.
Reviewer arbitrates quality and authority.
```

## Goal

Implement controlled steering as a generic MissionForge protocol that can
accept deterministic or LLM-backed proposals for route, repair, contract
adjustment, observation interpretation, and review without letting those
providers own durable truth.

The implementation must let future SkillFoundry-like products use MissionForge
for adaptive work while keeping product semantics in MissionIR, profiles,
validators, evidence, and adapters.

## Non-Goals

- Do not make live LLM steering default.
- Do not put SkillFoundry capability-bundle policy into runtime core.
- Do not import live provider code from `missionforge.runtime`,
  `missionforge.harness`, `missionforge.steering`, or package root.
- Do not let an LLM proposal mark a mission complete.
- Do not allow proposals to expand write scope, authority, budget, tools, model
  access, or verification rules without an explicit revision/review gate.
- Do not persist raw prompts, raw model responses, raw transcripts, provider
  payloads, artifact bodies, stdout/stderr bodies, or secrets in default run
  state.
- Do not implement hard mid-tool interruption as part of controlled steering.
  Control remains safe-point based until a separate runtime interruption design
  exists.
- Do not make dashboard, CLI, RPC, host, or reviewer output a second verifier.

## Current Foundation

Implemented today:

- `SteeringProposal`
- `ProposalValidationResult`
- `DecisionLedgerEntry`
- `StateCorrection`
- `ControlRequest`
- `ProposalValidator`
- `WorkUnitCompiler`
- `WorkUnitHarness`
- deterministic proposal creation inside `RuntimeEngine`
- proposal rejection for unsafe refs, missing refs, output-scope expansion,
  authority expansion, and closure attempts
- safe-point halt control
- durable `MissionRun`, `RuntimeAttempt`, `RuntimeSafePoint`, artifact hygiene,
  and operator inspection/diagnosis

Controlled steering is now implemented for the first product-neutral slice.
MissionForge has generic provider context, proposal artifact storage,
deterministic provider injection, runtime proposal mode, observation signal
recording, state-correction refs, contract-adjustment contracts, review packet
handling, optional LLM adapter isolation, benchmark pressure tests, and
operator inspection/diagnosis surface.

Live LLM steering remains opt-in through adapter injection. The default runtime
path remains deterministic/offline.

## SkillFoundry Translation

SkillFoundry's old plan should be translated into MissionForge concepts as
follows.

| SkillFoundry concept | MissionForge target | Core or adapter |
| --- | --- | --- |
| `RoutePlan` | `AdaptiveDecision` plus `MissionRun.next_action` | core |
| `NextStepContract` | `WorkUnitContract` | core |
| `CapabilityStateEstimate` | `SteeringContext` over `MissionRun` and evidence refs | core |
| `SteeringProposal` | product-neutral `SteeringProposal` | core |
| `ObservationReport` | `RuntimeAttempt`, `ExecutionReport`, verifier refs | core |
| `ObservationSignal` | product-neutral observation hypothesis | core |
| `ContractAdjustmentRequest` | product-neutral revision/split/shrink request | core |
| `ProductGradeGate` | verification profiles and verifier results | profile/verifier |
| `RegistryGate` | host/product policy, not MissionForge core | adapter/product |
| Skill bundle policy | MissionIR, profiles, validators, adapter compiler | adapter/profile |
| live LLM steering node | optional provider adapter returning core contracts | adapter |

The important extraction is not any SkillFoundry field name. The important
extraction is the pattern:

```text
semantic uncertainty -> proposal artifact -> boundary validation -> committed
work unit or route -> evidence -> verifier/reviewer decision
```

## Target Architecture

```text
MissionRun + FrozenMissionContract refs + latest attempts + verifier refs
  -> SteeringContext projector
  -> ProposalProvider emits SteeringProposal / ObservationSignal /
     ContractAdjustmentRequest / ReviewPacket refs
  -> schema validation
  -> boundary validation
  -> authority validation
  -> DecisionLedgerEntry
  -> Runtime commits accepted WorkUnitContract or routes review/redesign
  -> Worker executes bounded WorkUnitContract
  -> ExecutionReport / artifact refs / evidence refs
  -> Verifier
  -> StateCorrection
  -> complete | continue | repair | redesign | review | stop | escalate | fail
```

Core modules own protocol and validation. Optional adapters own live provider
I/O.

```text
missionforge.steering
  contract dataclasses, enums, provider protocols, trust/authority vocabulary

missionforge.harness
  boundary validation, work-unit compilation, decision ledger entries

missionforge.runtime
  safe-point integration, provider injection, route commit

missionforge.state
  durable refs-only run and steering artifact refs

missionforge.review
  reviewer freshness, independence, review packet semantics

missionforge.adapters.steering_llm
  optional live/fake LLM provider adapter; never imported by core
```

## Provider Placement Decision

`ProposalProvider` should be a core protocol, but live implementations must be
adapters.

Reasoning:

- Runtime needs a stable type boundary for provider injection.
- Tests need deterministic fake providers without adapter dependencies.
- Live provider code must not enter core imports.
- Host products may supply their own providers as long as they emit core
  contracts.

The split should be:

```text
src/missionforge/steering.py
  ProposalProvider protocol
  ObservationInterpreter protocol
  ReviewerProvider protocol
  deterministic contract objects

src/missionforge/testing or tests fixtures
  deterministic fake providers

src/missionforge/adapters/steering_llm.py
  optional live LLM provider adapter
```

If a testing helper module is introduced, it must not be imported by package
root as a production API unless explicitly documented.

## New Core Contracts

### SteeringContext

`SteeringContext` is the only default input shape for proposal providers.

It should contain refs and safe summaries, not raw bodies.

Required fields:

- `schema_version`
- `mission_run_id`
- `mission_id`
- `iteration`
- `contract_ref`
- `contract_hash`
- `mission_run_ref`
- `attempt_refs`
- `latest_attempt_ref`
- `verification_refs`
- `artifact_hygiene_ref`
- `failed_constraint_ids`
- `allowed_output_roots`
- `visible_refs`
- `forbidden_actions`
- `authority_policy_ref`
- `safe_summary`

Rules:

- All refs are workspace-relative safe refs.
- `safe_summary` must be bounded text generated by MissionForge code.
- `safe_summary` cannot include raw prompts, transcripts, artifact bodies,
  stdout/stderr bodies, secrets, or provider payloads.
- A provider may request more context only through explicit visible refs and
  host policy; default core behavior does not grant raw workspace access.

### SteeringProposal V2

Current `SteeringProposal` should evolve to include:

- `schema_version`
- `proposal_kind`
- `source`
- `source_refs`
- `authority_required`
- `trust_level`
- `alternatives`
- `provider_diagnostic_refs`

Allowed `proposal_kind` values:

- `next_work_unit`
- `repair`
- `redesign`
- `review`
- `stop`
- `escalate`

Rules:

- `recommended_route = complete` remains forbidden.
- `confidence` is telemetry. It grants no authority.
- `source_refs` must cite the context, verifier, attempt, or review packet refs
  that motivated the proposal.
- Provider diagnostics must be refs-only and redacted.

### ObservationSignal

`ObservationSignal` records an interpretation, not a fact.

Required fields:

- `schema_version`
- `signal_id`
- `mission_run_id`
- `iteration`
- `observation_ref`
- `source_refs`
- `signal_type`
- `safe_summary`
- `trust_level`
- `recommended_action`
- `affected_contract_fields`
- `confidence`
- `requires_verifier_confirmation`

Allowed `signal_type` values:

- `root_cause_hypothesis`
- `risk_hypothesis`
- `scope_mismatch`
- `missing_evidence`
- `repair_hint`
- `review_hint`

Rules:

- `trust_level` for LLM output is `llm_interpretation`.
- Signals can influence proposal generation and state correction.
- Signals cannot turn failed verification into closure.
- Signals must cite source refs.

### ContractAdjustmentRequest

`ContractAdjustmentRequest` records a request to change work shape or mission
contract authority.

Required fields:

- `schema_version`
- `request_id`
- `mission_run_id`
- `iteration`
- `contract_ref`
- `requested_change`
- `reason`
- `evidence_refs`
- `proposed_contract_refs`
- `authority_required`
- `risk_if_rejected`

Allowed `requested_change` values:

- `shrink`
- `split`
- `reorder`
- `pivot`
- `expand`
- `spec_revision`
- `review_required`

Rules:

- `shrink`, `split`, and `reorder` may be harness-authorized if they stay
  inside the frozen contract authority.
- `expand`, `pivot`, and `spec_revision` require review or redesign.
- Any request touching frozen contract constraints, guarantees, validator
  rules, resource policy, authority policy, tool policy, or protected paths is
  not a repair. It is a revision/redesign candidate.

### RepairStrategyProposal

`RepairStrategyProposal` is optional but useful when failures are many or
ambiguous.

Required fields:

- `schema_version`
- `strategy_id`
- `mission_run_id`
- `iteration`
- `failure_refs`
- `failed_constraint_ids`
- `repair_order`
- `work_unit_splits`
- `risk_notes`
- `stop_conditions`
- `confidence`

Rules:

- It cannot execute work.
- It cannot alter the frozen contract.
- It can only be compiled into one or more validated `SteeringProposal` records.

### ReviewPacket

`ReviewPacket` is the bridge from runtime to reviewer.

Required fields:

- `schema_version`
- `review_packet_id`
- `mission_run_id`
- `iteration`
- `reason`
- `contract_ref`
- `mission_run_ref`
- `attempt_refs`
- `verification_refs`
- `proposal_refs`
- `failed_constraint_ids`
- `questions`
- `forbidden_decisions`

Rules:

- A review packet must be refs-only.
- It must state whether the reviewer may resolve a delegatable manual gate or
  may only recommend redesign/repair/stop.
- It must explicitly forbid replacing failed executable validators.

`ReviewerDecision` should remain freshness-checked and independence-checked by
`missionforge.review`.

## Steering Artifact Layout

Use run-local refs so operator inspection and cleanup remain simple.

```text
runs/{mission_run_id}/steering/context_{iteration}.json
runs/{mission_run_id}/steering/proposals/{iteration}/steering_proposal.json
runs/{mission_run_id}/steering/proposals/{iteration}/observation_signal.json
runs/{mission_run_id}/steering/proposals/{iteration}/contract_adjustment_request.json
runs/{mission_run_id}/steering/proposals/{iteration}/repair_strategy.json
runs/{mission_run_id}/steering/proposals/{iteration}/state_correction.json
runs/{mission_run_id}/steering/reviews/{iteration}/review_packet.json
runs/{mission_run_id}/steering/reviews/{iteration}/reviewer_decision.json
runs/{mission_run_id}/steering/decision_ledger.jsonl
```

`MissionRun` should eventually expose:

- `steering_context_ref`
- `latest_steering_proposal_ref`
- `latest_observation_signal_ref`
- `latest_contract_adjustment_request_ref`
- `latest_state_correction_ref`
- `latest_review_packet_ref`
- `decision_ledger_ref`

To avoid an unsafe schema break, the first implementation may keep these refs
discoverable by run-local convention and expose them through `inspect` before
bumping `MissionRun` schema version.

## Runtime Integration

The runtime should keep current deterministic behavior by default.

Proposed constructor shape:

```python
RuntimeEngine(
    workspace=".",
    max_attempts=1,
    worker=worker,
    steering_provider=None,
    observation_interpreter=None,
    reviewer_provider=None,
    steering_mode="deterministic",
)
```

Rules:

- `steering_mode="deterministic"` preserves current behavior.
- `steering_mode="proposal"` requires a provider or deterministic fake.
- If provider output is malformed, unsafe, stale, missing refs, or over
  authority, runtime rejects it and records the rejection.
- Provider failure does not silently fall through to unsafe work. Runtime either
  uses documented deterministic fallback or routes `review`/`redesign`,
  depending on locked policy.
- Runtime never imports optional live provider adapters.
- Runtime checks explicit controls before expensive provider calls and before
  worker dispatch.

## Validation Policy

Proposal validation must fail closed on:

- invalid schema version
- unknown fields if the contract type is strict
- missing `mission_run_id`
- mismatched `mission_run_id`
- stale iteration
- unsafe refs
- missing visible refs
- proposed output outside allowed scope
- allowed scope outside frozen authority
- forbidden paths
- raw prompt/transcript/provider/payload/body/stdout/stderr/secret-shaped keys
- missing source refs
- authority expansion
- frozen contract mutation
- closure proposal
- verifier override
- review approval over failed executable validators
- live provider use without explicit opt-in

The existing `assert_refs_only_command_payload()` logic in the CLI adapter is
useful but should not remain CLI-owned if core steering needs the same safety
check. Move or duplicate the generic part into a core helper such as
`assert_refs_only_payload()` in `contracts.py`, then let CLI import the core
helper.

## Evidence Reliability

Keep discrete trust levels. Do not introduce fuzzy weighting yet.

Existing candidate levels are sufficient for the first implementation:

- `untrusted_worker_claim`
- `llm_interpretation`
- `artifact_ref`
- `command_result`
- `test_result`
- `schema_validation`
- `verifier_result`
- `reviewer_decision`
- `human_acceptance`

Routing rules:

- `llm_interpretation` may motivate repair, review, or redesign.
- `untrusted_worker_claim` may motivate observation or review only.
- `schema_validation`, `command_result`, `test_result`, and
  `verifier_result` can support state correction.
- `reviewer_decision` can resolve delegatable manual gates but cannot replace
  failed executable validators.
- `human_acceptance` is used only when frozen authority explicitly reserves the
  gate for the user.

## Metrics

Controlled steering must expose decoupled metrics without becoming control
logic.

Recommended metrics:

- `steering_context_count`
- `proposal_count`
- `accepted_proposal_count`
- `rejected_proposal_count`
- `proposal_rejection_reasons`
- `observation_signal_count`
- `contract_adjustment_request_count`
- `review_packet_count`
- `reviewer_decision_count`
- `provider_failure_count`
- `unsafe_proposal_rejection_count`
- `authority_gate_count`
- `repair_strategy_count`
- `repair_loop_count`
- `redesign_required_count`
- `raw_leakage_violation_count`
- `verifier_override_attempt_count`
- `live_provider_call_count`
- `provider_token_usage`
- `provider_latency_ms`

Provider token usage and latency are recorded as diagnostics, not as route
truth.

## Implementation Phases

### Goal CS0: Constitution Lock

Status: `completed_verified`

Objective:

```text
Lock the controlled steering implementation contract before changing runtime
behavior.
```

Primary files:

- `docs/CONTROLLED_STEERING_IMPLEMENTATION_PLAN.md`
- `docs/modules/controlled_steering.md`
- `docs/COMPONENT_ACCEPTANCE_MATRIX.md`

Acceptance:

- document states core laws, non-goals, provider placement, artifact layout,
  and phase gates
- no code behavior changes
- `git diff --check` passes

### Goal CS1: Core Schema Upgrade

Status: `completed_verified`

Objective:

```text
Add product-neutral controlled steering contract objects and strict validation.
```

Primary files:

- `src/missionforge/steering.py`
- `src/missionforge/contracts.py`
- `tests/test_steering_contracts.py`

Implementation:

- add schema versions where missing
- add `SteeringContext`
- add `ObservationSignal`
- add `ContractAdjustmentRequest`
- add `RepairStrategyProposal`
- add review packet contract if it does not belong in `review.py`
- add authority/request enums
- add generic refs-only payload helper in core contracts

Acceptance:

- all objects round trip through dicts
- unsafe refs fail
- unknown enum values fail
- confidence must be finite in `[0, 1]`
- forbidden raw keys fail
- LLM trust level cannot prove completion
- default test suite passes

### Goal CS2: Steering Artifact Store

Status: `completed_verified`

Objective:

```text
Persist proposal, signal, adjustment, strategy, review, and decision artifacts
as run-local refs without embedding raw bodies in MissionRun.
```

Primary files:

- `src/missionforge/state.py`
- optional `src/missionforge/steering_store.py`
- `tests/test_controlled_steering_store.py`
- `tests/test_runtime_artifact_hygiene.py`

Implementation:

- write run-local steering refs under `runs/{mission_run_id}/steering/`
- write `decision_ledger.jsonl`
- add read helpers for operator inspection
- keep state refs-only
- scan steering artifacts in artifact hygiene

Acceptance:

- artifact refs are stable and workspace-relative
- raw prompt/transcript/payload/body/stdout/stderr/secret-shaped fields are
  rejected or flagged
- accepted and rejected proposals are both durable
- inspect can surface steering refs without embedding artifact bodies

### Goal CS3: Provider Protocol And Deterministic Fakes

Status: `completed_verified`

Objective:

```text
Introduce provider protocols and deterministic fake providers before live LLMs.
```

Primary files:

- `src/missionforge/steering.py`
- `src/missionforge/harness.py`
- `tests/test_controlled_steering_providers.py`

Implementation:

- define `ProposalProvider`
- define `ObservationInterpreter`
- define `ReviewerProvider`
- add deterministic fake providers for valid, unsafe, stale, closure, and
  authority-expanding outputs
- keep provider output as contract objects, not direct state mutation

Acceptance:

- valid fake proposal can be accepted
- unsafe fake proposal is rejected
- closure fake proposal is rejected
- stale fake proposal is rejected
- authority-expanding fake proposal is rejected
- provider failure produces structured failure evidence

### Goal CS4: Runtime Proposal Mode

Status: `completed_verified`

Objective:

```text
Let RuntimeEngine consume an injected provider under an explicit proposal mode
while preserving deterministic default behavior.
```

Primary files:

- `src/missionforge/runtime.py`
- `src/missionforge/runner.py`
- `tests/test_controlled_steering_runtime.py`
- `tests/test_runtime_vertical_slice.py`
- `tests/test_runtime_routes.py`

Implementation:

- add optional provider injection
- add `steering_mode`
- build `SteeringContext` from run refs
- ask provider only at safe points
- validate provider proposal through harness
- record accept/reject decisions
- compile accepted proposal into `WorkUnitContract`
- fallback or route according to explicit policy

Acceptance:

- current deterministic runtime tests pass unchanged
- proposal mode is opt-in
- malformed provider output does not dispatch worker
- rejected proposal writes decision ledger
- accepted proposal executes only within allowed scope
- verifier remains completion authority

### Goal CS5: Observation Interpretation And State Correction

Status: `completed_verified`

Objective:

```text
Allow optional observation interpretation while keeping state correction
evidence-backed and verifier-bound.
```

Primary files:

- `src/missionforge/steering.py`
- `src/missionforge/runtime.py`
- `src/missionforge/verifier.py`
- `tests/test_controlled_steering_observation.py`

Implementation:

- create `ObservationSignal` after attempt/verifier output
- write signal refs
- let `StateCorrection` cite trust levels and source refs
- ensure failed verifier cannot be converted to closure by signal

Acceptance:

- signal is stored as refs-only artifact
- state correction cites source refs and trust level
- LLM signal can recommend repair/review/redesign
- LLM signal cannot close mission
- failed executable verifier remains failed

### Goal CS6: Contract Adjustment And Review Gate

Status: `completed_verified`

Objective:

```text
Support shrink, split, reorder, pivot, expansion, spec revision, and review
requests without allowing silent frozen-contract mutation.
```

Primary files:

- `src/missionforge/steering.py`
- `src/missionforge/review.py`
- `src/missionforge/runtime.py`
- `tests/test_controlled_steering_adjustment.py`
- `tests/test_reviewer_decision.py`

Implementation:

- validate `ContractAdjustmentRequest`
- classify changes as harness-authorized, review-required, redesign-required,
  or human-authority-required
- emit `ReviewPacket` for review routes
- reuse reviewer freshness and independence checks
- reject worker-authored self-review

Acceptance:

- shrink/split/reorder inside frozen authority can route repair/continue
- expand/pivot/spec revision routes review or redesign
- stale reviewer decision is rejected
- reviewer approval cannot override failed executable validator
- human-only gate remains human-only

### Goal CS7: Optional LLM Provider Adapter

Status: `completed_verified`

Objective:

```text
Add a live-provider adapter that emits core controlled steering contracts
without entering runtime core or default tests.
```

Primary files:

- `src/missionforge/adapters/steering_llm.py`
- `src/missionforge/adapters/pi_agent_provider_config.py` if shared provider
  config is reused
- `tests/test_controlled_steering_import_boundaries.py`
- `tests/test_controlled_steering_llm_adapter.py`
- optional skipped live smoke test

Implementation:

- live provider accepts `SteeringContext`
- provider returns strict JSON contract objects
- raw prompt and raw response are not written into default run state
- provider diagnostics are refs-only and redacted
- adapter is opt-in through host/runtime construction, not auto-loaded

Acceptance:

- core modules do not import `missionforge.adapters.steering_llm`
- no live provider is used by default validation
- missing live config fails closed before provider call
- adapter output passes the same schema and boundary validators
- live smoke is skipped unless explicitly enabled

### Goal CS8: Pressure Benchmark

Status: `completed_verified`

Objective:

```text
Prove controlled steering improves complex adaptive behavior without weakening
safety invariants.
```

Primary files:

- `tests/test_controlled_steering_benchmark.py`
- fixtures under `tests/fixtures/` if needed

Scenarios:

1. contract too broad -> provider proposes split
2. contract too narrow -> provider proposes review-required expansion
3. verifier failure ambiguous -> observation interpreter identifies likely root
   cause as hypothesis
4. repeated repair failure -> review packet
5. unsafe scope proposal -> rejected
6. closure without verifier -> rejected
7. stale reviewer decision -> rejected
8. live-like fake proposer reduces repair loops versus deterministic baseline

Metrics:

- final verification status
- iteration count
- repair loop count
- accepted proposal count
- rejected proposal count
- unsafe rejection count
- review boundary count
- raw leakage violation count
- verifier false-success resistance

Acceptance:

- deterministic default baseline remains passing
- fake LLM proposal mode improves at least one complex fixture without
  violating invariants
- unsafe proposals are rejected and recorded
- no raw leakage appears in run state

### Goal CS9: Operator Surface

Status: `completed_verified`

Objective:

```text
Expose controlled steering refs and decisions through existing operator
inspect/diagnose without creating host-owned steering authority.
```

Primary files:

- `src/missionforge/adapters/cli.py`
- `src/missionforge/adapters/rpc.py`
- `docs/modules/host_adapters.md`
- `tests/test_operator_cli_inspect.py`
- `tests/test_operator_cli_diagnose.py`
- `tests/test_operator_jsonl_rpc.py`

Implementation:

- add steering refs to inspect data
- add diagnosis reason codes for proposal rejection, review gate,
  adjustment-required, provider failure, and unsafe proposal rejection
- keep command output refs-only
- do not add CLI commands that approve proposals or mutate runtime state
  implicitly

Acceptance:

- inspect is read-only
- diagnose cites steering refs
- command output remains refs-only
- CLI/RPC cannot turn proposal into completion

## Default Validation

Every goal must pass:

```bash
git diff --check
PYTHONPATH=src python3 -m unittest discover -s tests
```

When TypeScript worker behavior is touched, also run:

```bash
npm test --prefix workers/pi-agent-runtime
```

When the repository health check is required:

```bash
./scripts/validate.sh
```

Live LLM checks must remain skipped unless an explicit environment flag is set.

Verification evidence for the completed implementation:

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_controlled_steering_contracts.py \
  tests/test_controlled_steering_store.py \
  tests/test_controlled_steering_runtime.py \
  tests/test_controlled_steering_llm_adapter.py \
  tests/test_controlled_steering_import_boundaries.py \
  tests/test_controlled_steering_benchmark.py \
  tests/test_operator_controlled_steering_surface.py
# Ran 20 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 222 tests: OK (skipped=2)
```

## Recommended First Goal Prompt

```text
/goal 使用 $metaloop 按 docs/CONTROLLED_STEERING_IMPLEMENTATION_PLAN.md 的
Goal CS1 推进 MissionForge controlled steering core schema upgrade。只实现
product-neutral schema contracts、strict validation、refs-only payload helper
和 focused tests；不要接 live LLM、不要改 runtime 默认行为、不要引入
SkillFoundry product semantics、不要让 proposal 拥有 completion authority。
```

## Completion Standard

Controlled steering is implementation-complete when:

- deterministic default runtime remains unchanged unless proposal mode is
  explicitly selected
- controlled steering contracts are strict and JSON-compatible
- provider outputs are stored as proposal/evidence refs
- accepted and rejected proposals are both ledgered
- unsafe proposal, stale proposal, authority expansion, frozen contract
  mutation, and closure attempts fail closed
- runtime commits only validated work units or route changes
- verifier remains the only executable completion authority
- reviewer protocol is recoverable but cannot override failed executable
  validators
- live provider adapter is optional and import-isolated
- operator surfaces expose refs and decisions without owning steering
- SkillFoundry-like products can use the protocol through MissionIR, profiles,
  validators, and adapters, not runtime branches
