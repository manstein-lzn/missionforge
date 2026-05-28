# Component Development Plan

This is the implementation plan for MissionForge's first deterministic runtime
kernel. It turns the architecture documents into a sequenced component backlog.

Development proceeds in phases. Each phase must leave tests, docs, and a clear
resume point before the next phase starts.

## Phase Overview

```text
Phase 1: Contract Kernel
Phase 2: Profile and Freeze Kernel
Phase 3: Evidence Ledger and Verification Kernel
Phase 4: Work-Unit Harness and Controlled Steering Validation
Phase 5: Runtime Vertical Slice
Phase 6: PiWorker and SkillFoundry Adapter Preparation
```

Do not start Phase 6 until the deterministic runtime vertical slice is passing.

## Phase 1: Contract Kernel

Status: `completed_verified`

Goal:

Define shared data contracts and validation helpers used by every other module.

Primary modules:

- `src/missionforge/contracts.py`
- `src/missionforge/mission.py`
- `src/missionforge/evidence.py`
- `src/missionforge/verification.py`
- `src/missionforge/work_unit.py`
- `src/missionforge/steering.py`

Existing `src/missionforge/ir.py` may remain as a compatibility import surface
until the new modules are stable.

Public contracts:

- `MissionForgeError`
- `ContractValidationError`
- `MissionValidationError`
- `EvidenceTrustLevel`
- `ValidatorMode`
- `ValidatorSeverity`
- `VerificationStatus`
- `AdaptiveDecision`
- `ProposalValidationStatus`
- `Ref`
- `ArtifactRef`
- `EvidenceRef`
- `ValidatorSpec`
- `VerificationSpec`
- `WorkUnitContract`
- `ExecutionReport`
- `SteeringProposal`
- `ProposalValidationResult`
- `StateCorrection`
- `MissionResult`

Implementation tasks:

- create shared enum and validation helpers
- implement safe ref validation
- implement stable JSON hashing
- implement contract round-trip helpers
- keep existing `MissionIR` tests passing
- add tests for unsafe refs, duplicate IDs, enum validation, and hash stability

Non-goals:

- no profile registry
- no evidence store
- no worker execution
- no runtime loop
- no live LLM or PiWorker code

Acceptance:

- invalid schemas fail closed
- unsafe refs are rejected
- stable hashes do not depend on dict key order
- proposal confidence does not grant authority
- worker claim trust level cannot satisfy verifier trust requirements
- default test command passes

Suggested tests:

- `tests/test_contracts.py`
- `tests/test_evidence_contracts.py`
- `tests/test_verification_contracts.py`
- `tests/test_work_unit_contracts.py`
- `tests/test_steering_contracts.py`

Docs-last updates:

- `docs/modules/mission_ir.md`
- `docs/modules/context_evidence.md`
- `docs/modules/controlled_steering.md`

Implemented behavior:

- added shared contract errors, enums, validation helpers, safe refs, and stable
  JSON hashing in `src/missionforge/contracts.py`
- added evidence ref and artifact ref contracts with explicit trust levels in
  `src/missionforge/evidence.py`
- added validator, verification spec, validator result, and verification result
  contracts in `src/missionforge/verification.py`
- added work-unit, attempt manifest, execution report, and worker result
  contracts in `src/missionforge/work_unit.py`
- added steering proposal, proposal validation result, and state correction
  contracts in `src/missionforge/steering.py`
- kept the existing `MissionIR` import surface passing and added
  `src/missionforge/mission.py` as a compatibility mission contract surface
- repaired independent reviewer findings by adding missing `from_dict()` helpers
  for public Phase 1 contracts and exporting `Ref` from the package root

Verification evidence:

```bash
PYTHONPATH=src python3 -m unittest tests/test_contracts.py tests/test_evidence_contracts.py tests/test_verification_contracts.py tests/test_work_unit_contracts.py tests/test_steering_contracts.py
# Ran 26 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 29 tests: OK

git diff --check
# passed
```

Known gaps:

- profile expansion and frozen contract generation remain Phase 2 work
- evidence storage and verifier execution remain Phase 3 work
- proposal boundary validation and harness execution remain Phase 4 work
- runtime orchestration remains Phase 5 work

Review gate:

- Initial MetaLoop verification reached `review_required` because Phase 1
  acceptance includes delegatable reviewer gates.
- Independent reviewer `Confucius` approved the Phase 1 evidence after the
  missing round-trip helpers and `Ref` package-root export were repaired.
- MetaLoop verification then reached `completed_verified`.

## Phase 2: Profile And Freeze Kernel

Status: `completed_verified`

Goal:

Implement `MissionIR -> ExpandedMission -> FrozenMissionContract` with
deterministic profile expansion and provenance.

Primary modules:

- `src/missionforge/profiles.py`
- `src/missionforge/freeze.py`
- `src/missionforge/mission.py`

Public contracts:

- `CapabilityProfile`
- `VerificationProfile`
- `ProfileRegistry`
- `ProfileExpansion`
- `ExpandedMission`
- `FrozenMissionContract`
- `ContractManifest`

Initial profiles:

- `user_provided_evidence_only`
- `explicit_output_root`
- `generic_local_verification`

Implementation tasks:

- split capability and verification profile concepts
- implement deterministic profile expansion
- generate stable IDs for expanded fragments
- preserve source profile provenance
- freeze contract with stable hash
- reject unknown profile refs
- reject unknown validator types unless declared by a verification profile

Non-goals:

- no large profile library
- no product-specific profile branching
- no runtime execution

Acceptance:

- profile expansion is deterministic
- expanded constraints and validators cite provenance
- frozen contract hash is stable
- contract-relevant changes alter the hash
- dict key order does not alter the hash
- unknown validators fail closed

Suggested tests:

- `tests/test_profiles.py`
- `tests/test_freeze.py`
- `tests/test_contract_manifest.py`

Docs-last updates:

- `docs/modules/profiles.md`
- `docs/modules/mission_ir.md`
- `docs/MISSION_IR.md`

Implemented behavior:

- added `CapabilityProfile`, `VerificationProfile`, `ProfileExpansion`, and
  deterministic `ProfileRegistry` in `src/missionforge/profiles.py`
- added built-in initial profiles: `user_provided_evidence_only`,
  `explicit_output_root`, and `generic_local_verification`
- added `ExpandedMission`, `FrozenMissionContract`, `ContractManifest`,
  `expand_mission()`, and `freeze_mission()` in `src/missionforge/freeze.py`
- added package exports for Phase 2 contracts and helpers
- implemented validator-language checks so unknown validator types fail unless
  declared by an active verification profile
- implemented stable frozen contract hash and manifest generation
- locked `CapabilityProfileRef.requirements` into profile expansions and frozen
  contract hashes so requirement changes are contract-relevant

Verification evidence:

```bash
PYTHONPATH=src python3 -m unittest tests/test_profiles.py tests/test_freeze.py tests/test_contract_manifest.py
# Ran 12 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 41 tests: OK

git diff --check
# passed
```

Known gaps:

- evidence storage and verifier execution remain Phase 3 work
- proposal boundary validation and harness execution remain Phase 4 work
- runtime orchestration remains Phase 5 work

Review gate:

- Phase 2 acceptance includes deterministic profile expansion, provenance,
  stable freezing, and validator-language checks. Independent reviewer approval
  was required before marking this phase `completed_verified`.
- Independent reviewer `Helmholtz` initially returned `needs_changes` because
  `CapabilityProfileRef.requirements` did not affect the frozen contract hash.
  The repair locked profile ref requirements and hashes into the expanded
  contract payload, added regression tests, and passed focused re-review.
- MetaLoop verification then reached `completed_verified`.

## Phase 3: Evidence Ledger And Verification Kernel

Status: `completed_verified`

Goal:

Make evidence and verification real before runtime orchestration grows.

Primary modules:

- `src/missionforge/evidence_store.py`
- `src/missionforge/validators.py`
- `src/missionforge/verifier.py`
- `src/missionforge/review.py`

Public contracts:

- `EvidenceLedger`
- `EvidenceRecord`
- `EvidenceSnapshot`
- `InMemoryEvidenceStore`
- `FileEvidenceStore`
- `ValidatorResult`
- `VerificationResult`
- `FailedConstraint`
- `MissingEvidence`
- `ReviewerDecision`

Initial validators:

- `file_exists`
- `file_contains`
- `forbidden_path`
- `json_field_exists`
- `artifact_hash`
- `command`

Implementation tasks:

- implement append-only evidence records
- implement evidence trust levels
- implement validator dispatch
- implement verifier status routing
- implement reviewer decision validation
- ensure verifier cites evidence refs
- store command stdout/stderr as evidence refs or summaries, not acceptance
  truth

Non-goals:

- no SQLite
- no distributed ledger
- no live reviewer agent
- no runtime adaptive loop

Acceptance:

- blocking executable validator failure returns `failed`
- delegatable manual blocking gate returns `review_required`
- explicit user-authority gate returns `human_acceptance_required`
- unsupported blocking validator returns `unsupported_verification_spec`
- advisory failures become warnings
- stale reviewer decision is rejected
- worker-authored reviewer decision is rejected
- worker claim evidence cannot complete a validator

Suggested tests:

- `tests/test_evidence_ledger.py`
- `tests/test_validators.py`
- `tests/test_verifier.py`
- `tests/test_reviewer_decision.py`

Docs-last updates:

- `docs/modules/context_evidence.md`
- `docs/modules/verifier_repair.md`

Implemented behavior:

- added append-only `EvidenceRecord`, `EvidenceSnapshot`,
  `InMemoryEvidenceStore`, and `FileEvidenceStore` in
  `src/missionforge/evidence_store.py`
- added deterministic local validators in `src/missionforge/validators.py` for
  `file_exists`, `file_contains`, `forbidden_path`, `json_field_exists`,
  `artifact_hash`, and `command`
- added `Verifier` and `verify_spec()` routing in `src/missionforge/verifier.py`
  for executable, manual, unsupported, advisory, reviewer, and human-authority
  outcomes
- added `ReviewerDecision` validation in `src/missionforge/review.py` with
  current-contract checks and worker-authored approval rejection
- extended verification result contracts with `FailedConstraint` and
  `MissingEvidence`
- exported Phase 3 public contracts from the package root

Verification evidence:

```bash
PYTHONPATH=src python3 -m unittest tests/test_evidence_ledger.py tests/test_validators.py tests/test_verifier.py tests/test_reviewer_decision.py
# Ran 21 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 62 tests: OK

git diff --check
# passed
```

Known gaps:

- work-unit harness execution and controlled steering validation remain Phase 4
  work
- runtime orchestration remains Phase 5 work
- live LLM, PiWorker, LangGraph, HTTP, and SkillFoundry adapters remain out of
  scope

Review gate:

- Phase 3 affects verifier routing, evidence authority, and reviewer decision
  semantics. Independent reviewer approval was required before marking this
  phase `completed_verified`.
- Independent reviewer `Confucius` approved the Phase 3 evidence and manual
  gates: append-only ledger semantics, verifier routing statuses, advisory
  warning behavior, reviewer decision freshness/independence checks, and trust
  rejection for worker-claim evidence.
- MetaLoop verification then reached `completed_verified`.

## Phase 4: Work-Unit Harness And Controlled Steering Validation

Status: `completed_verified`

Goal:

Implement the proposal-to-work-unit boundary and a deterministic fake worker.

Primary modules:

- `src/missionforge/harness.py`
- `src/missionforge/steering.py`
- `src/missionforge/fake_worker.py`
- `src/missionforge/control.py`

Public contracts:

- `ProposalProvider`
- `DeterministicProposalProvider`
- `ProposalValidator`
- `WorkUnitCompiler`
- `AttemptInputManifest`
- `WorkerInvocation`
- `WorkerResult`
- `ExecutionReport`
- `DecisionLedgerEntry`
- `ControlRequest`

Implementation tasks:

- emit deterministic steering proposals
- validate proposal schema, refs, scope, expected outputs, and authority
- commit accepted proposals as `WorkUnitContract`
- reject closure proposals without verifier evidence
- reject frozen contract mutation
- record rejected proposals in the decision ledger
- implement fake worker that writes one artifact and one execution report
- implement safe-point control checks for `halt`

Non-goals:

- no live LLM proposal provider
- no PiWorker
- no host adapter
- no verifier acceptance inside harness

Acceptance:

- valid proposal is accepted
- unsafe path is rejected
- missing visible ref is rejected
- expected output outside allowed scope is rejected
- proposal cannot close a mission
- proposal cannot expand frozen contract authority
- rejected proposal is recorded
- fake worker output is evidence, not acceptance
- halt control blocks worker dispatch at a safe point

Suggested tests:

- `tests/test_proposal_validation.py`
- `tests/test_harness.py`
- `tests/test_fake_worker.py`
- `tests/test_control_requests.py`

Docs-last updates:

- `docs/modules/controlled_steering.md`
- `docs/modules/harness.md`
- `docs/modules/runtime.md`

Implemented behavior:

- added `ControlRequest`, `ControlPoint`, and `ControlHalt` in
  `src/missionforge/control.py`
- added `DecisionLedgerEntry` to controlled steering contracts
- added `WorkerInvocation` to work-unit contracts
- added deterministic `ProposalProvider`, `DeterministicProposalProvider`,
  `ProposalValidator`, `WorkUnitCompiler`, and `WorkUnitHarness` in
  `src/missionforge/harness.py`
- added deterministic `FakeWorker` in `src/missionforge/fake_worker.py`
- validated proposal refs, visible refs, allowed output scopes, closure
  authority, and frozen-contract authority expansion before worker dispatch
- required explicit proposal validation boundary context so missing refs and
  output authority fail closed by default
- recorded rejected proposals in the decision ledger
- checked halt controls at the safe point before worker dispatch

Verification evidence:

```bash
PYTHONPATH=src python3 -m unittest tests/test_proposal_validation.py tests/test_harness.py tests/test_fake_worker.py tests/test_control_requests.py
# Ran 16 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 78 tests: OK

git diff --check
# passed
```

Known gaps:

- runtime orchestration remains Phase 5 work
- verifier acceptance remains outside the harness
- live LLM proposal provider, PiWorker, LangGraph, HTTP, and SkillFoundry
  adapters remain out of scope

Review gate:

- Phase 4 affects controlled steering authority and worker dispatch boundaries.
  Independent reviewer approval was required before marking this phase
  `completed_verified`.
- Independent reviewer `Helmholtz` initially returned `needs_changes` because
  default `ProposalValidator` construction skipped visible-ref and output-root
  authority checks. The repair made boundary context explicit and fail-closed,
  added regression tests, and passed focused re-review.
- MetaLoop verification then reached `completed_verified`.

## Phase 5: Runtime Vertical Slice

Status: `completed_verified`

Goal:

Run the first deterministic MissionRuntime loop end to end.

Primary modules:

- `src/missionforge/runtime.py`
- `src/missionforge/runner.py`
- `src/missionforge/state.py`

Runtime loop:

```text
validate mission
resolve profiles
freeze contract
create initial state estimate
select deterministic proposal
validate and commit work unit
run fake worker
record execution report
verify evidence
record state correction
route complete | repair | review | fail
emit MissionResult
```

Implementation tasks:

- replace the current `accepted` facade with a deterministic loop
- keep the public `MissionRuntime.run()` boundary stable
- produce refs-only `MissionResult`
- route `completed_verified`, `failed`, `review_required`, and
  `unsupported_verification_spec`
- stop repeated failures with a bounded attempt limit
- ensure runtime has no LangGraph, SkillFoundry, PiWorker, or live LLM
  dependency

Non-goals:

- no full route vocabulary on day one
- no PiWorker
- no live LLM
- no external service adapter

Acceptance:

- valid deterministic mission reaches `completed_verified`
- missing artifact routes to repair or fail with failed constraint IDs
- manual gate routes to `review_required`
- unsupported validator routes to `unsupported_verification_spec`
- MissionResult is refs-only
- no raw prompt, transcript, or worker artifact body enters result
- runtime stays host-independent

Suggested tests:

- `tests/test_runtime_vertical_slice.py`
- `tests/test_runtime_routes.py`
- `tests/test_runtime_refs_only.py`

Docs-last updates:

- `docs/modules/runtime.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_PROTOCOL.md`

Implemented behavior:

- added `MissionRunState` in `src/missionforge/state.py`
- added `RuntimeEngine` in `src/missionforge/runtime.py`
- updated `MissionRuntime.run()` to execute the deterministic vertical slice
  behind the existing public boundary
- runtime now validates Mission IR, freezes the contract, writes a frozen
  contract ref, emits a deterministic proposal, validates/compiles a work unit,
  runs the fake worker, verifies evidence, and emits a refs-only
  `MissionResult`
- routed `completed_verified`, `failed`, `review_required`, and
  `unsupported_verification_spec`
- kept fake worker output as artifact/evidence only; completion comes from the
  verifier status

Verification evidence:

```bash
PYTHONPATH=src python3 -m unittest tests/test_ir.py tests/test_runtime_vertical_slice.py tests/test_runtime_routes.py tests/test_runtime_refs_only.py
# Ran 9 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 83 tests: OK

git diff --check
# passed
```

Known gaps:

- no full multi-attempt repair planner yet
- no PiWorker, live LLM, LangGraph, HTTP, host adapter, or SkillFoundry adapter
- Phase 6 adapter preparation should be split into separate follow-on goals if
  the deterministic runtime vertical slice is accepted

Review gate:

- Phase 5 composes all prior kernels and changes the public runtime behavior
  from `accepted` facade to verifier-routed status. Independent reviewer
  approval was required before marking this phase `completed_verified`.
- Independent reviewer `Confucius` approved the Phase 5 vertical slice:
  deterministic freeze/proposal/harness/fake-worker/verifier composition,
  refs-only `MissionResult`, verifier-owned completion, failure/review/
  unsupported routing, and host independence.
- MetaLoop verification then reached `completed_verified`.

## Phase 6: PiWorker And SkillFoundry Adapter Preparation

Status: `completed_verified`

Goal:

Prepare the first real adapter boundaries after the deterministic runtime is
verified.

Phase 6 must be split into separate follow-on goals now that Phase 5 is
complete. Use `docs/FOLLOW_ON_GOALS.md` as the launch contract for those goals.

Recommended order:

```text
Goal 6.0: Adapter Boundary Preflight
Goal 6A: Faux PiWorker Adapter
Goal 6B: SkillFoundry MissionIR Compiler
Goal 6C: Optional Host Adapter Shell
```

Do not combine 6A and 6B in one implementation goal. PiWorker adapter work
changes worker trust boundaries; SkillFoundry adapter work changes product and
source-compilation boundaries. Keeping them separate prevents product-specific
semantics from leaking into the worker/runtime kernel.

Phase 6 is complete when Goal 6.0, Goal 6A, Goal 6B, and Goal 6C are all
`completed_verified`. That condition is now satisfied.

### Phase 6.0: Adapter Boundary Preflight

Status: `completed_verified`

Primary documentation:

- `docs/FOLLOW_ON_GOALS.md`
- `docs/modules/adapter_contracts.md`
- `docs/modules/piworker.md`
- `docs/modules/skillfoundry_adapter.md`
- `docs/modules/host_adapters.md`

Potential modules:

- `src/missionforge/adapters/__init__.py`
- `src/missionforge/adapters/contracts.py`

Acceptance:

- adapter package boundaries are documented before implementation
- core runtime modules do not import adapter modules
- shared adapter contracts are refs-only
- focused import-boundary tests are defined or implemented
- no real PiWorker, SkillFoundry, LangGraph, HTTP, or live LLM integration is
  added

Implemented behavior:

- added `src/missionforge/adapters/__init__.py`
- added `src/missionforge/adapters/contracts.py`
- added shared refs-only adapter contracts:
  - `AdapterBoundary`
  - `AdapterInvocation`
  - `AdapterDiagnostic`
  - `AdapterResult`
- added import-boundary tests proving core modules do not import
  `missionforge.adapters`
- kept the package root from importing or re-exporting adapter contracts
- added tests rejecting raw payload/body/transcript-like fields in adapter
  contracts
- added recursive rejection for provider-secret-shaped fields such as
  `api_key`, `access_token`, `password`, `secret_key`, and prompt-like fields

Verification evidence:

```bash
PYTHONPATH=src python3 -m unittest tests/test_adapter_contracts.py tests/test_adapter_import_boundaries.py
# Ran 10 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 93 tests: OK

git diff --check
# passed
```

Known gaps:

- faux PiWorker remains Goal 6A
- SkillFoundry compiler remains Goal 6B
- optional host shells remain Goal 6C
- no real PiWorker, live LLM, LangGraph, HTTP, or SkillFoundry behavior exists
  in Goal 6.0

Review gate:

- Goal 6.0 defines adapter import and trust boundaries. Independent reviewer
  approval was required before marking this subphase `completed_verified`.
- Independent reviewer `Confucius` initially returned `needs_changes` because
  adapter result metrics accepted provider-secret-shaped keys such as
  `api_key`, `access_token`, `password`, and `secret_key`. The repair added
  recursive raw/prompt/transcript/provider-secret-shaped key rejection and
  focused regression tests.
- MetaLoop verification then reached `completed_verified`.

### Phase 6A: PiWorker Adapter

Status: `completed_verified`

Primary modules:

- `src/missionforge/adapters/piworker.py`
- `src/missionforge/workers.py`

Public contracts:

- `WorkerAdapter`
- `WorkerAdapterResult`
- `PiWorkerInput`
- `PiWorkerEvent`
- `PiWorkerOutput`
- `PiWorkerMetrics`
- `ContractAdjustmentEvidence`

Acceptance:

- PiWorker consumes committed `WorkUnitContract`, not raw MissionIR or
  SteeringProposal
- PiWorker event stream maps to evidence refs and execution reports
- metrics are evidence/metrics, not control logic
- worker-requested contract adjustment becomes evidence, not mutation
- faux PiWorker tests pass before live smoke exists
- MissionForge core has no PiWorker imports

Non-goals:

- no live PiWorker process in the first adapter goal
- no provider credentials
- no multi-worker abstraction
- no adapter-owned acceptance or verifier replacement

Implemented behavior:

- added `src/missionforge/workers.py` with the generic `WorkerAdapter`
  protocol and `WorkerAdapterResult`
- added `src/missionforge/adapters/piworker.py` with deterministic faux
  PiWorker contracts:
  - `PiWorkerInput`
  - `PiWorkerEvent`
  - `PiWorkerOutput`
  - `PiWorkerMetrics`
  - `ContractAdjustmentEvidence`
  - `FauxPiWorkerAdapter`
- `FauxPiWorkerAdapter` consumes committed `WorkUnitContract` objects only and
  rejects raw `MissionIR`, `SteeringProposal`, dict-like input, and expected
  outputs outside `allowed_scope`
- deterministic artifact writes are constrained to workspace-relative refs
  under the work-unit allowed scope
- PiWorker-like invocation, artifact, metrics, adjustment, and completion
  events are appended to `EvidenceLedger` as `artifact_ref` evidence
- worker-requested contract adjustment is recorded as
  `contract_adjustment_request` evidence and included in
  `ExecutionReport.evidence_refs`; it does not mutate `WorkUnitContract` or any
  frozen mission contract
- generated `ExecutionReport` is refs-only: produced artifacts, changed refs,
  evidence refs, empty `worker_claims`, and metrics, with no artifact body,
  prompt, transcript, or provider credential body
- adapter status and metrics remain worker evidence only; verifier completion
  still requires `VerificationResult.status`
- MissionForge core and package root do not import or re-export the PiWorker
  adapter

Focused tests:

- `tests/test_piworker_adapter_contracts.py`
- `tests/test_faux_piworker_adapter.py`
- `tests/test_piworker_import_boundaries.py`

Verification evidence:

```bash
PYTHONPATH=src python3 -m unittest tests/test_piworker_adapter_contracts.py tests/test_faux_piworker_adapter.py tests/test_piworker_import_boundaries.py tests/test_adapter_import_boundaries.py
# Ran 16 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 106 tests: OK

git diff --check
# passed
```

Known gaps:

- no live PiWorker process
- no provider credentials or live LLM
- no LangGraph, HTTP, or SkillFoundry adapter behavior
- no multi-worker abstraction
- no copied PI source

Review gate:

- Goal 6A changes the worker trust boundary. Independent reviewer approval is
  required before this phase can be marked `completed_verified`.
- Independent reviewer `Confucius` approved the locked Goal 6A revision after
  inspecting the adapter behavior, import boundaries, refs-only execution
  report, verifier authority regression, docs, full test output, and focused
  test output.
- MetaLoop verification then reached `completed_verified`.

### Phase 6B: SkillFoundry Adapter

Status: `completed_verified`

Primary modules:

- `src/missionforge/adapters/skillfoundry.py`

Public contracts:

- `SkillFoundrySourceBundle`
- `SkillFoundryCompileResult`
- `FrontDeskArtifactRef`
- `SkillPackageTarget`

Acceptance:

- SkillFoundry FrontDesk artifacts compile into MissionIR
- capability-bundle behavior is expressed through profiles
- MissionForge core does not import SkillFoundry
- registry/product packaging remains outside MissionForge core
- compile output is refs-only
- raw transcript input is rejected unless represented as an explicitly allowed
  sanitized source ref

Non-goals:

- no SkillFoundry runtime dependency in core
- no registry publishing
- no product-specific runtime branch
- no live LLM or PiWorker execution

Implemented behavior:

- added `src/missionforge/adapters/skillfoundry.py`
- added deterministic refs-only adapter contracts:
  - `FrontDeskArtifactRef`
  - `SkillPackageTarget`
  - `SkillFoundrySourceBundle`
  - `SkillFoundryCompileResult`
  - `SkillFoundryMissionCompiler`
- `SkillFoundryMissionCompiler` reads FrontDesk-style contract and source
  manifest refs from a workspace and compiles them into valid `MissionIR`
- generated MissionIR is written to `missions/{bundle_id}.mission.json`
- generated frozen contract is written to
  `missions/{bundle_id}.frozen_contract.json`
- compile diagnostics are written as refs-only diagnostics under `evidence/`
- compile result contains refs, profile ids, target package ref, warnings, and
  contract hash only; it does not embed source artifact bodies
- raw transcript, raw prompt, raw payload, private text/body fields, and
  transcript-shaped inputs are rejected unless represented as sanitized source
  refs
- capability-bundle behavior is expressed through `CapabilityProfileRef` and
  verification profile ids, then frozen through the existing profile expansion
  path
- SkillFoundry source bundles fail closed when capability profile refs are
  omitted, so capability-bundle behavior cannot bypass profile expansion
- MissionForge core and package root do not import or re-export the
  SkillFoundry adapter

Focused tests:

- `tests/test_skillfoundry_adapter_contracts.py`
- `tests/test_skillfoundry_compiler.py`
- `tests/test_skillfoundry_import_boundaries.py`

Verification evidence:

```bash
PYTHONPATH=src python3 -m unittest tests/test_skillfoundry_adapter_contracts.py tests/test_skillfoundry_compiler.py tests/test_skillfoundry_import_boundaries.py tests/test_adapter_import_boundaries.py tests/test_piworker_import_boundaries.py
# Ran 24 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 124 tests: OK

git diff --check
# passed
```

Known gaps:

- no SkillFoundry runtime dependency in MissionForge core
- no registry publishing or packaging side effects
- no product-specific runtime branch
- no live LLM, PiWorker execution, LangGraph, or HTTP

Review gate:

- Goal 6B changes the product/source compilation boundary. Independent
  reviewer approval is required before this phase can be marked
  `completed_verified`.
- Independent reviewer `Helmholtz` initially returned `needs_changes` because
  the compiler allowed capability-bundle compilation without capability profile
  refs. The repair made `SkillFoundrySourceBundle` fail closed when
  `capability_profile_refs` are omitted and added regression tests.
- `Helmholtz` approved the repair, and MetaLoop verification then reached
  `completed_verified`.

### Phase 6C: Optional Host Adapter Shell

Status: `completed_verified`

Primary modules:

- `src/missionforge/adapters/cli.py`
- `src/missionforge/adapters/observation.py`
- optional later `src/missionforge/adapters/langgraph.py`

Acceptance:

- host adapters pass MissionIR in and receive MissionResult out
- observation surfaces are read-only
- control surfaces write explicit `ControlRequest` intent
- optional host dependencies do not enter MissionForge core imports

Non-goals:

- no required LangGraph dependency
- no HTTP service unless split into its own follow-on goal
- no host-owned verifier, repair, or steering semantics

Implemented behavior:

- added `src/missionforge/adapters/cli.py`
- added `src/missionforge/adapters/observation.py`
- `MissionCLI` reads a workspace-relative MissionIR ref, calls the primary
  `MissionRuntime` Python API, writes a workspace-relative `MissionResult` ref,
  and returns a refs-only `MissionCLIResult`
- `MissionRunView` creates a read-only host-facing summary from
  `MissionResult` and an optional evidence snapshot
- `ControlRequestWriter` writes explicit `ControlRequest` halt intent JSON
  under `control/` and does not mutate runtime state or dispatch directly
- package root and core runtime modules do not import or re-export host adapter
  modules
- no `langgraph.py`, `http.py`, HTTP framework, network client, or required
  host dependency was added

Focused tests:

- `tests/test_host_cli_adapter.py`
- `tests/test_host_observation_adapter.py`
- `tests/test_host_import_boundaries.py`

Verification evidence:

```bash
PYTHONPATH=src python3 -m unittest tests/test_host_cli_adapter.py tests/test_host_observation_adapter.py tests/test_host_import_boundaries.py tests/test_adapter_import_boundaries.py tests/test_piworker_import_boundaries.py tests/test_skillfoundry_import_boundaries.py
# Ran 17 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 131 tests: OK

git diff --check
# passed
```

Known gaps:

- no LangGraph adapter
- no HTTP service or dashboard
- no streaming observation
- no live LLM, PiWorker execution, registry publishing, or host-owned verifier

Review gate:

- Goal 6C changes the host integration boundary. Independent reviewer approval
  is required before this phase can be marked `completed_verified`.
- Independent reviewer `Confucius` approved the locked Goal 6C revision after
  inspecting CLI/Python shell behavior, read-only observation, control intent
  writes, import boundaries, docs, full test output, and focused test output.
- MetaLoop verification then reached `completed_verified`.

Non-goals for Phase 6:

- no live LLM steering by default
- no product-specific branches in runtime
- no multi-worker abstraction until PiWorker path is stable
- no adapter code imported by core runtime modules

## Global Done Definition

A phase is `completed_verified` only when:

- focused tests pass
- default test command passes
- `git diff --check` passes
- module docs are updated
- implementation remains deterministic/offline by default
- no worker or LLM claim is used as acceptance evidence

Default verification:

```bash
git diff --check
PYTHONPATH=src python3 -m unittest discover -s tests
```
