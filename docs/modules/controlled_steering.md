# Module: Controlled Steering

## Goal

Introduce constrained intelligence into MissionForge without letting LLMs,
workers, reviewers, dashboards, or host adapters own durable truth.

The core rule is:

```text
LLM proposes.
Harness validates boundaries.
Runtime commits state.
Verifier proves facts.
Reviewer arbitrates quality and authority.
```

This module carries the controlled steering lessons from SkillFoundry and the
control-point lessons from MetaLoop into MissionForge as generic protocol
objects.

## Scope

- steering proposal schema
- observation interpretation schema
- contract adjustment request schema
- proposal validation result schema
- state correction schema
- decision ledger entries
- reviewer decision schema
- control request schema
- safe-point protocol
- authority and evidence-reliability rules for proposal-driven steering

## Non-Goals

- no live LLM dependency in the default runtime
- no LLM-owned durable mission state
- no LLM-owned closure or acceptance
- no worker self-review
- no dashboard-owned routing or mutation
- no product-specific steering policy in MissionForge core
- no replacement for verifier, harness, or authority gates

## Current Status

Phase 1 contract primitives exist. Phase 4 added deterministic proposal
boundary validation, decision ledger recording, controlled dispatch safe-point
handling, and a deterministic fake worker harness.

The controlled steering implementation plan is now completed for the first
product-neutral slice. MissionForge has strict refs-only steering context,
proposal, observation-signal, contract-adjustment, repair-strategy, review
packet, state-correction, provider, store, runtime, operator, optional LLM
adapter, and benchmark coverage. The default runtime remains deterministic and
offline unless proposal mode and providers are injected explicitly.

Implemented in Phase 1:

- `SteeringProposal`
- `ProposalValidationResult`
- `StateCorrection`
- `DecisionLedgerEntry`
- `ControlRequest`
- JSON-compatible round-trip helpers for implemented contracts

Implemented in the controlled steering slice:

- `SteeringContext`
- `ObservationSignal`
- `ContractAdjustmentRequest`
- `RepairStrategyProposal`
- `ReviewPacket`
- `ProposalProvider`
- `ObservationInterpreter`
- `ReviewerProvider`
- `SteeringArtifactStore`
- optional `ControlledSteeringLLMAdapter`
- runtime `steering_mode="proposal"` provider injection
- operator inspect/diagnose steering refs
- pressure benchmark for accepted and rejected live-like proposals

Implemented in Phase 15:

- `MissionRevisionRequest`
- `MissionRevisionDecision`
- `MissionRevision`
- `MissionRevisionWorkflow`
- `MissionRevisionStore`
- conservative revision application for shrink/split/reorder/review-required
  routes
- stale contract hash rejection
- reviewer decision freshness checks
- MissionRun revision refs and current contract refs

Implemented Phase 15 repair:

- runtime consumption of the active revised contract
- preservation of `MissionRun.revision_refs` across runtime writes
- operator inspect surface for current contract refs and revision refs
- fail-closed handling for stale or missing active contract refs

The repair plan is tracked in
`docs/PHASE15_REVISION_RUNTIME_REPAIR_PLAN.md`.

MissionForge keeps deterministic behavior by default. Live LLM steering is
still opt-in through adapter injection, and adapter output must pass the same
schema, refs-only, boundary, and authority validation as deterministic fake
providers.

## Public Contracts

- `SteeringProposal`
- `ProposalValidationResult`
- `StateCorrection`
- `SteeringContext`
- `ObservationSignal`
- `ContractAdjustmentRequest`
- `RepairStrategyProposal`
- `ReviewPacket`
- `ProposalProvider`
- `ObservationInterpreter`
- `ReviewerProvider`
- `SteeringArtifactStore`
- `MissionRevisionRequest`
- `MissionRevisionDecision`
- `MissionRevision`
- `MissionRevisionWorkflow`
- `MissionRevisionStore`

To be designed:

- richer `MissionRunView` steering read model beyond the current operator refs

## Permission Model

LLM-backed or deterministic proposal providers may:

- propose a route
- propose a bounded next work unit
- interpret observations as hypotheses
- suggest repair strategy
- request contract shrink, split, reorder, pivot, or revision
- recommend review

They may not:

- commit graph or runtime state
- mutate a frozen mission contract
- expand authority
- write outside a validated scope
- mark a mission complete
- approve registry or product gates
- replace executable verifier evidence
- resolve explicitly user-reserved authority

## Evidence Reliability

Controlled steering depends on explicit trust levels. Candidate levels:

- `untrusted_worker_claim`
- `llm_interpretation`
- `artifact_ref`
- `command_result`
- `test_result`
- `schema_validation`
- `verifier_result`
- `reviewer_decision`
- `human_acceptance`

Rules:

- LLM interpretation is a hypothesis, not a fact.
- Worker claims are advisory observations, not acceptance evidence.
- State correction must cite evidence refs and trust levels.
- High-trust evidence can correct mission state; low-trust evidence can only
  motivate proposals or review.
- Provider-specific telemetry is preserved as evidence or metrics, not control
  logic.

## Proposal Lifecycle

```text
MissionRun state + evidence refs
  -> ProposalProvider emits proposal artifact
  -> schema validation
  -> harness boundary validation
  -> authority validation
  -> accept or reject proposal
  -> write DecisionLedgerEntry
  -> runtime commits accepted WorkUnitContract or routes review/redesign
```

Rejected proposals are still evidence. They should be recorded with rejection
reasons so later diagnosis can distinguish a poor model suggestion from a
failed work attempt.

## Mission Revision Lifecycle

Mission revision is a controlled state transition, not a workflow engine:

```text
ContractAdjustmentRequest
  -> MissionRevisionRequest
  -> authority check
  -> MissionRevisionDecision
  -> conservative MissionIR update
  -> new FrozenMissionContract
  -> MissionRevision record
```

Rules:

- stale base contract hashes are rejected
- harness authority can approve only shrink, split, and reorder
- review-required changes need reviewer approval for the current contract hash
- human-authority changes remain human-authority decisions
- unsupported or expanding changes fail closed unless routed to review, human
  authority, or redesign
- revision metadata changes the frozen contract hash through MissionIR fields
  that are part of the frozen contract
- reviewer prose cannot override failed executable validators

## Candidate Schemas

### SteeringProposal

```json
{
  "schema_version": "missionforge.steering_proposal.v1",
  "proposal_id": "steering-proposal-001",
  "mission_run_id": "run-001",
  "iteration": 3,
  "input_refs": [
    "mission/state_estimate_003.json",
    "evidence/verification_result_002.json"
  ],
  "recommended_route": "repair",
  "proposed_contract": {
    "next_objective": "Repair only the failing validator coverage.",
    "allowed_scope": ["package/tests", "attempts/003"],
    "visible_refs": ["mission/frozen_contract.json", "evidence/failed_constraints.json"],
    "expected_outputs": ["attempts/003/execution_report.json"],
    "exit_criteria": ["Blocking verifier is rerun."],
    "stop_conditions": ["Repair requires changing the frozen mission contract."]
  },
  "rationale": "The latest failure is localized to one validator.",
  "risks": ["The true root cause may be broader than the failed validator."],
  "confidence": 0.72
}
```

### ObservationSignal

```json
{
  "schema_version": "missionforge.observation_signal.v1",
  "signal_id": "observation-signal-001",
  "observation_ref": "attempts/003/execution_report.json",
  "signal_type": "root_cause_hypothesis",
  "safe_summary": "The failure appears to be missing fixture evidence.",
  "source_refs": ["attempts/003/execution_report.json", "verification/result_003.json"],
  "trust_level": "llm_interpretation",
  "recommended_action": "repair",
  "requires_verifier_confirmation": true
}
```

### ContractAdjustmentRequest

```json
{
  "schema_version": "missionforge.contract_adjustment_request.v1",
  "request_id": "contract-adjustment-001",
  "mission_run_id": "run-001",
  "iteration": 3,
  "contract_ref": "work_units/work_unit_003.json",
  "requested_change": "split",
  "reason": "The current work unit mixes implementation and verifier repair.",
  "evidence_refs": ["attempts/003/execution_report.json"],
  "authority_required": "reviewer",
  "risk_if_rejected": "The next failure may remain ambiguous."
}
```

Allowed requested changes:

- `shrink`
- `expand`
- `split`
- `reorder`
- `pivot`
- `spec_revision`
- `review_required`

## Review Semantics

`review_required` is a recoverable protocol state, not a terminal shrug.

```text
review_required
  -> write review packet
  -> independent ReviewerDecision
  -> resume | repair | redesign | stop | escalate
```

Rules:

- The reviewer must be independent from the worker being reviewed.
- Reviewer approval can resolve delegatable manual gates.
- Reviewer approval cannot replace failed executable validators.
- Stale reviewer decisions are rejected.
- Human-only authority remains human-only when explicitly reserved by the
  frozen mission contract.
- Proposal validation fails closed on unsafe refs, output scope expansion,
  closure attempts, and authority expansion.
- Proposal validation requires explicit visible-ref and output-root context; an
  unconfigured validator does not imply broad authority.
- Rejected proposals are recorded in a decision ledger.
- Halt controls block worker dispatch at a safe point.

## Control Requests

MissionForge should expose explicit control intent at safe points. Candidate
control types:

- `halt`
- `resource_approval`
- `inject_fact`
- `revise_contract_request`
- `budget_override_request`
- `worker_interrupt_request`

Control requests express intent. They do not mutate a frozen mission contract,
approve resources, kill workers, or route work by themselves.

## Safe Points

Runtime and worker adapters should check controls and commit evidence at
predictable safe points:

- before freezing a mission contract
- before proposing a work unit
- before expensive execution
- before dispatching a worker
- after an execution report is written
- before verification
- before closure
- before resume or handoff

## Invariants

- No proposal is durable truth until accepted by runtime code.
- No accepted proposal may broaden the frozen mission contract.
- Any contract change after freeze is a revision or redesign.
- Proposal confidence never grants authority.
- Closure requires verifier evidence and any required authority gate.
- Graph, host, and summary state store proposal refs, not raw prompts or raw
  transcripts.
- Observation surfaces are read-only.
- Control surfaces write explicit intent, not hidden mutations.

## Dependencies

- Mission IR
- context/evidence module
- work-unit harness
- verification and repair module
- runtime engine

## Verification Strategy

- valid deterministic proposal is accepted and committed as a work unit
- malformed proposal fails closed
- unsafe scope is rejected
- closure proposal without verifier evidence is rejected
- frozen contract mutation is rejected
- rejected proposal writes a ledger entry
- observation signal cannot turn failed verification into closure
- stale reviewer decision is rejected
- worker-authored reviewer decision is rejected
- control request is observed only at safe points
- runtime state stores refs, not raw prompt or transcript material

## Verification Evidence

Phase 1:

```bash
PYTHONPATH=src python3 -m unittest tests/test_steering_contracts.py
# Ran 6 tests: OK
```

Phase 4:

```bash
PYTHONPATH=src python3 -m unittest tests/test_proposal_validation.py tests/test_harness.py tests/test_fake_worker.py tests/test_control_requests.py
# Ran 16 tests: OK
```

Controlled steering implementation slice:

```bash
PYTHONPATH=src python3 -m unittest tests/test_controlled_steering_contracts.py tests/test_controlled_steering_store.py tests/test_controlled_steering_runtime.py tests/test_controlled_steering_llm_adapter.py tests/test_controlled_steering_import_boundaries.py tests/test_controlled_steering_benchmark.py tests/test_operator_controlled_steering_surface.py
# Ran 20 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 222 tests: OK (skipped=2)
```

## Open Questions

- Should the next state backend expose a first-class indexed steering read
  model instead of run-local JSON discovery?
- Should `MissionRevisionRequest` become a separate contract before adding
  broader redesign workflows?
- Which live LLM provider should be the first scheduled opt-in soak target?
