# Mission IR

Mission IR is the canonical mission contract for MissionForge. It is not a
task template, a prompt, a product-specific schema, or a worker input format.
It is a domain-neutral control contract for goal-seeking work.

The core abstraction is:

```text
Mission = goal-directed change under constraints, observed through evidence,
verified by locked predicates, and adapted through explicit control decisions.
```

MissionForge should be able to execute a software task, documentation task,
benchmark task, research task, data task, or operational task without adding
task-name branches to the runtime. Domain specificity enters through profiles,
evidence, validators, and artifacts, not through core control flow.

## Theory Base

Mission IR is grounded in a small set of reusable systems ideas:

- control theory: execution is a closed loop, not one-shot generation
- systems engineering: goals, non-goals, assumptions, constraints, risks, and
  acceptance must be traceable
- contract-based design: assumptions, guarantees, invariants, and obligations
  must be explicit
- planning theory: work proceeds through state, action, observation, and
  replanning
- formal verification discipline: completion requires evidence and validators,
  not worker self-report
- provenance and audit: every operational fact should be backed by refs
- capability security: actions, tools, writes, resources, and authority must be
  bounded before execution
- controlled steering: LLMs and workers may propose or interpret, but only
  validated runtime code commits state and only verifier evidence proves facts

These theories constrain the shape of Mission IR, but the wire format remains
pragmatic JSON-compatible data.

## Semantic Layers

MissionForge uses multiple mission objects rather than one overloaded schema.

```text
MissionIR
  The authoring-level structured intent supplied by a host, FrontDesk-like
  compiler, CLI, service, or another orchestrator.

CapabilityProfile
  A reusable capability declaration. It expands generic or domain capabilities
  into constraints, artifacts, evidence requirements, risk checks, repair hints,
  and worker guidance.

VerificationProfile
  A reusable verification-language declaration. It declares validator types,
  validator modes and severities, manual or unsupported checks, review
  questions, risk checks, and known gaps.

ExpandedMission
  MissionIR after all profile references are resolved and normalized. This is
  still a design product and may be inspected before lock.

FrozenMissionContract
  The locked, hashed, executable mission constitution. Runtime execution,
  repair, review, and completion are judged against this object.

MissionRun
  Durable execution state: attempts, work units, observations, execution
  reports, evidence ledger refs, verification results, adaptive decisions,
  metrics, controls, and final result.

SteeringProposal
  A proposed route, work unit, repair strategy, observation interpretation, or
  contract adjustment. It is evidence until validated and committed. It is not
  durable truth by itself.
```

The worker should not consume free-form chat or an unfrozen MissionIR. PiWorker
receives a bounded WorkUnitContract compiled from the FrozenMissionContract.

## Lifecycle

```text
draft MissionIR
  -> validate authoring shape
  -> resolve CapabilityProfile and VerificationProfile references
  -> expand to ExpandedMission
  -> review assumptions, risks, and unverifiable gates
  -> freeze to FrozenMissionContract
  -> estimate mission state
  -> propose or deterministically select WorkUnitContract
  -> validate proposal, authority, refs, and scope
  -> commit WorkUnitContract
  -> execute PiWorker attempt
  -> collect Observation and ExecutionReport
  -> verify EvidenceLedger through VerificationSpec
  -> record StateCorrection and DecisionLedgerEntry
  -> decide complete | continue | repair | redesign | pivot | review | stop | escalate
  -> emit MissionResult
```

Changing a locked contract is a revision. Repair does not weaken the contract.
If execution reveals that the mission contract is wrong or underspecified, the
adaptive decision is redesign and a new frozen revision is created.

## Core Vocabulary

### Objective

The desired state and value of the mission.

Required concepts:

- summary: human-readable intent
- desired_state: the target condition, not an implementation plan
- success_predicates: observable conditions that imply enough success
- preferences: soft tradeoffs such as speed, simplicity, quality, or cost
- non_goals: outcomes explicitly outside the mission

### Environment

The known world before execution.

Required concepts:

- source_refs: allowed task inputs and evidence sources
- assumptions: facts accepted for the current contract
- uncertainties: facts that may affect execution or verification
- forbidden_sources: inputs that must not influence worker execution
- workspace: root, allowed read scopes, allowed write scopes, and protected
  paths

Raw conversation may be stored for provenance, but it is not operational task
truth unless an explicit sanitized derivative is admitted as a source ref.

### Contract

The mission constitution.

Required concepts:

- constraints: hard and soft obligations
- invariants: properties that must remain true across attempts
- guarantees: what a completed mission promises
- forbidden_actions: actions the runtime or worker must not take
- required_artifacts: artifacts that must exist before closure
- risk_policy: known risk checks and escalation boundaries
- revision_policy: which contract changes require redesign, reviewer approval,
  or user authority

Every constraint should be stable, identifiable, and traceable to source refs,
profiles, or explicit host policy.

### Capabilities

The allowed operational surface.

Required concepts:

- capability_profile_refs: reusable capability declarations to expand
- verification_profile_refs: reusable verification-language declarations to
  expand
- tool_policy: allowed, forbidden, and approval-required tool classes
- action_policy: permitted action families and preconditions
- resource_policy: cost, time, model, network, credential, and external system
  boundaries
- authority_policy: which decisions are delegated to MissionForge, reviewer,
  host, or user

Capabilities authorize possible work; they do not prove completion.

### Evidence

The observable proof surface.

Required concepts:

- evidence_requirements: artifacts, logs, metrics, snapshots, command outputs,
  hashes, or review notes required by the contract
- provenance_policy: source refs, hashes, timestamps, and derived artifact
  lineage
- evidence_ledger: append-only refs written during MissionRun
- forbidden_evidence: material that must not be ingested or emitted
- reliability_policy: trust levels for worker claims, LLM interpretations,
  artifacts, command results, verifier results, reviewer decisions, and human
  acceptance

Evidence refs should be durable and inspectable. Long free-form logs may be
referenced, but worker self-report is not acceptance evidence by itself.

Candidate evidence trust levels:

- `untrusted_worker_claim`
- `llm_interpretation`
- `artifact_ref`
- `command_result`
- `test_result`
- `schema_validation`
- `verifier_result`
- `reviewer_decision`
- `human_acceptance`

Low-trust evidence may motivate a proposal, diagnosis, or review. It does not
prove completion.

### Verification

The locked completion logic.

Validator shape:

```json
{
  "validator_id": "V-001",
  "constraint_refs": ["C-001"],
  "type": "command",
  "mode": "executable",
  "severity": "blocking",
  "description": "Run the mission test command.",
  "inputs": {"command": "python3 -m unittest discover -s tests -v"}
}
```

Validator modes:

- `executable`: MissionForge can run or compute the check
- `manual`: reviewer or user judgment is required
- `unsupported`: the check is important but no current executor exists

Validator severities:

- `blocking`: unresolved or failed means not complete
- `advisory`: reported as warning, never hard proof

VerificationProfile should declare which validator types are valid for the
mission. Unknown validators fail closed unless they are declared by a locked
profile and classified as manual or unsupported.

Candidate verification statuses:

- `completed_verified`
- `failed`
- `review_required`
- `human_acceptance_required`
- `unsupported_verification_spec`
- `missing_verification_plan`
- `execution_incomplete`
- `invalid_contract`

`review_required` is recoverable when a delegatable manual gate can be decided
by an independent reviewer. `human_acceptance_required` appears only when the
frozen mission contract explicitly reserves authority for the user.

### Controlled Steering

The proposal and authority vocabulary for intelligence inside the loop.

Required concepts:

- steering_proposals: proposed route or work-unit contracts
- observation_signals: safe summaries and hypotheses derived from observations
- contract_adjustment_requests: requests to shrink, expand, split, pivot, or
  revise a contract
- proposal_validation_results: accepted or rejected proposal decisions with
  reasons
- state_corrections: updates to mission state backed by evidence refs and trust
  levels
- decision_ledger: append-only decisions, routes, proposal refs, and rejection
  reasons
- reviewer_decisions: independent review artifacts bound to contract revision
  and verification spec hash
- control_requests: explicit halt, resource approval, injected fact, or contract
  revision intent consumed at safe points

LLM-backed components may propose, interpret, or review. They may not commit
state, mutate a frozen mission contract, expand mission authority, verify
truth, or close a mission.

### Adaptation

The closed-loop control vocabulary after each attempt.

Decision vocabulary:

- `complete`: locked verification is satisfied
- `continue`: mission remains valid; more attempts or evidence are needed
- `repair`: implementation or artifact is defective, but contract remains valid
- `redesign`: mission contract, assumptions, acceptance, or profiles are wrong
  or incomplete
- `pivot`: the mission remains valid, but the current strategy direction should
  change
- `review`: independent judgment is required
- `stop`: continuing is not justified under current constraints
- `escalate`: blocked by authority, resource, safety, or external dependency

Each failed or partial attempt should record:

- plan
- observation
- evaluation
- diagnosis
- decision
- next_plan
- evidence_refs
- proposal_refs
- state_corrections

State correction follows the MetaLoop-style learning discipline:

```text
Observe -> Evaluate -> Diagnose -> Decide -> Next Plan
```

Verification proves whether the locked contract is satisfied. Diagnosis records
what was learned and why the next step is justified. The two must not collapse
into each other.

## Authoring Shape

The exact schema will evolve, but the stable top-level shape should remain close
to this:

```json
{
  "schema_version": "missionforge.mission_ir.v1",
  "mission_id": "example",
  "objective": {
    "summary": "Produce a verified local deliverable.",
    "desired_state": "The required deliverable exists and passes locked validation.",
    "success_predicates": ["verification.completed_verified"],
    "preferences": [{"kind": "quality", "priority": "should", "statement": "Keep the design simple."}],
    "non_goals": ["Do not add product-specific runtime branches."]
  },
  "environment": {
    "source_refs": ["frontdesk/task_contract.json"],
    "forbidden_sources": ["raw_conversation"],
    "assumptions": [],
    "uncertainties": [],
    "workspace": {
      "root": ".",
      "allowed_write_scopes": ["package", "attempts"],
      "protected_paths": [".git", ".env"]
    }
  },
  "contract": {
    "constraints": [
      {
        "constraint_id": "C-001",
        "kind": "data_boundary",
        "priority": "must",
        "statement": "Use only admitted source refs for task facts.",
        "source_refs": ["frontdesk/task_contract.json"],
        "evidence_obligations": ["evidence/source_manifest.json"]
      }
    ],
    "invariants": [],
    "required_artifacts": ["outputs/deliverable.md"],
    "forbidden_actions": [],
    "risk_policy": [],
    "revision_policy": {
      "contract_changes_after_freeze": "explicit_revision"
    }
  },
  "capabilities": {
    "capability_profile_refs": [
      {
        "profile_id": "user_provided_evidence_only",
        "version": "1.0",
        "requirements": {}
      }
    ],
    "verification_profile_refs": [
      {
        "profile_id": "generic_local_verification",
        "version": "1.0",
        "requirements": {}
      }
    ],
    "tool_policy": {},
    "resource_policy": {},
    "authority_policy": {
      "delegated_review": true,
      "user_reserved_authority": []
    }
  },
  "evidence": {
    "requirements": ["verifier/verification_result.json"],
    "provenance_policy": {"raw_conversation": "provenance_only"},
    "forbidden_evidence": ["secrets", "raw_logs"],
    "reliability_policy": {
      "worker_claim": "untrusted_worker_claim",
      "llm_output": "llm_interpretation",
      "verifier_output": "verifier_result"
    }
  },
  "verification": {
    "validators": [],
    "manual_gates": [],
    "known_gaps": [],
    "review_questions": []
  },
  "steering": {
    "proposal_mode": "deterministic",
    "allowed_proposal_sources": ["runtime_policy"],
    "proposal_rules": {
      "proposal_cannot_close": true,
      "proposal_cannot_expand_contract": true,
      "proposal_confidence_grants_no_authority": true
    },
    "control_request_types": [
      "halt",
      "resource_approval",
      "inject_fact",
      "revise_contract_request"
    ]
  },
  "adaptation": {
    "allowed_decisions": ["complete", "continue", "repair", "redesign", "pivot", "review", "stop", "escalate"],
    "repair_policy": {},
    "redesign_policy": {}
  },
  "observability": {
    "required_events": ["attempt_started", "verification_completed"],
    "summary_fields": ["goal", "status", "latest_decision", "verification_status"]
  },
  "budget": {}
}
```

## Profile Expansion

Profiles are not task names and not prompt templates. Capability profiles are
reusable capability compilers:

```text
CapabilityProfile + requirements -> mission fragments
```

Profile expansion may contribute:

- constraints
- required artifacts
- allowed or forbidden scopes
- evidence requirements
- validator declarations
- manual gates
- risk checks
- repair hints
- worker guidance
- generated fixture or reference artifact declarations

The expanded fragments must preserve provenance:

```text
constraint C-012 came from profile rust_helper_runtime@1.0
validator V-003 came from profile markdown_output_contract@1.0
artifact A-002 came from host MissionIR
```

The profile reference itself is also part of the locked contract. In the Phase 2
kernel, capability profile ref requirements are preserved as
`source_ref_requirements` with a stable `source_ref_hash`; changing those
requirements changes the frozen contract hash even before later phases add
requirement-specific fragment generation.

Runtime routing must use expanded constraints and validators, not profile names.

Verification profiles are reusable verification-language compilers:

```text
VerificationProfile + requirements -> validator language and review fragments
```

Verification profile expansion may contribute:

- validator type declarations
- validator executability metadata
- mode and severity defaults
- manual gates
- unsupported checks
- review questions
- known gaps
- authority rules

Unknown validator types cannot be smuggled into a generic mission. They must be
declared by a locked verification profile and then classified as executable,
manual, or unsupported.

## Anti-Specialization Rules

MissionForge core must never branch on a task name, product name, benchmark
name, or demo name.

Forbidden core patterns:

```text
if mission_id == "specific_demo": ...
if profile_id == "bad_runtime_patch": ...
if "expected phrase" in logs: mark complete
```

Allowed patterns:

```text
if failed_constraint.kind == "missing_required_artifact": repair
if verification.status == "review_required": route to reviewer gate
if validator.mode == "unsupported" and severity == "blocking": redesign
if proposal_validation.status == "rejected": record decision and continue
```

The goal is not to avoid domain complexity. The goal is to locate domain
complexity in profile data, evidence data, validator data, and generated
artifacts instead of hidden runtime branches.

## Implementation Status

The current Python dataclasses are intentionally behind this document. They
validate the initial MissionIR skeleton plus the first contract/profile/freeze
kernels. Remaining runtime objects should still be introduced in order:

Completed:

1. `CapabilityProfile` and `VerificationProfile`
2. `ExpandedMission`
3. `FrozenMissionContract`
4. `VerificationSpec` and validator result records
5. `EvidenceRef` and `EvidenceReliability`
6. `SteeringProposal` and `StateCorrection`

Remaining:

1. `EvidenceLedger`
2. verifier execution and repair records
3. proposal boundary validation
4. harness execution reports from real attempts
5. `MissionRun` and adaptive decision records

Code should not be expanded until the corresponding module documents are
updated.
