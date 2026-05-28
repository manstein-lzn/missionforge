# Design Program

MissionForge is a formal architecture effort, not an MVP extraction. The goal
is to define a durable mission execution substrate before implementation grows.

The project should proceed by design gates. Each gate must tighten the contract
between Mission IR, context evidence, controlled steering, work-unit execution,
verification, repair, and host integration.

## Gate 0: Prior-Art Contract Audit

Normalize the proven control vocabulary from SkillFoundry, MetaLoop, and the
controlled LLM steering plan before implementation grows.

Outputs:

- MissionForge vocabulary map
- imported-primitives decision record
- rejected-primitives decision record
- product-boundary notes for SkillFoundry and MetaLoop concepts

Design questions:

- Which SkillFoundry adaptive primitives are generic enough for MissionForge?
- Which MetaLoop control objects should influence MissionForge contracts?
- Which concepts remain product-layer or host-layer concerns?
- How are LLM proposal rights separated from runtime commit rights?

Acceptance:

- MissionForge absorbs stable primitives without copying product shape
- core terminology does not depend on SkillFoundry or MetaLoop names
- LLM, worker, verifier, reviewer, runtime, and host authorities are distinct

## Gate 1: Mission Contract Kernel

Define the canonical Mission IR and runtime state model.

Outputs:

- Mission IR schema
- ExpandedMission schema
- FrozenMissionContract schema
- Mission state schema
- Mission result schema
- authority policy schema
- revision policy schema
- stable ID rules
- source/provenance rules
- versioning policy

Design questions:

- What belongs in Mission IR versus profile data?
- What is the minimal mission truth required by every runtime?
- How are raw user inputs excluded from worker context while preserving
  provenance?
- How are reviewer, runtime, host, user, and worker authorities represented?
- What contract changes require redesign or revision?

Acceptance:

- mission semantics are expressible without product-name branches
- a mission can be frozen and hashed
- invalid mission contracts fail closed
- contract changes after freeze are explicit revisions
- user-only authority appears only when explicitly reserved

## Gate 2: Verification Language Kernel

Define reusable verification-language profiles inspired by MetaLoop
ExtensionSpec and SkillFoundry verifier profiles.

Outputs:

- VerificationProfile schema
- validator type registry model
- validator mode and severity model
- manual, unsupported, review, and human-authority gate semantics
- known gap and review question model

Design questions:

- Which generic validators ship first?
- How does a profile declare validators without hardcoding product logic?
- How are delegatable reviewer gates distinguished from user-only gates?
- How are unsupported blocking validators routed?

Acceptance:

- unknown validator types fail closed unless declared by a locked profile
- executable/manual/unsupported validators route to distinct statuses
- advisory failures are warnings, not completion proof
- review-required gates are recoverable through independent reviewer evidence

## Gate 3: Context and Evidence Kernel

Define the context plane inspired by ContextForge.

Outputs:

- evidence ref model
- evidence reliability model
- contract manifest model
- ledger event model
- checkpoint model
- verification gate model
- raw input boundary model

Design questions:

- Which records are immutable?
- Which refs are worker-visible?
- Which artifacts are provenance-only?
- How is evidence freshness verified?
- How are worker claims and LLM interpretations recorded without becoming
  acceptance evidence?

Acceptance:

- every worker-visible input has a frozen ref
- every verifier decision cites evidence refs
- raw conversation or raw private material is never operational context
- every state correction cites evidence refs and trust levels

## Gate 4: Work-Unit Harness

Define the execution plane inspired by ForgeUnit.

Outputs:

- work-unit contract schema
- attempt input manifest
- worker invocation record
- execution report
- artifact write scope model
- metrics model

Design questions:

- What is the minimum contract every worker consumes?
- How are tool calls, command calls, and model calls recorded?
- How does cancellation or steering appear in evidence?
- How does harness validation accept or reject proposed work-unit contracts?

Acceptance:

- worker self-report is not acceptance
- every attempt has independent execution evidence
- worker adapters can be swapped without changing Mission IR
- proposed work units fail closed when scope, refs, or authority are invalid

## Gate 5: Controlled Steering Protocol

Define how deterministic or LLM-backed intelligence enters the loop as
proposal, hypothesis, or review evidence without taking authority from the
runtime, harness, or verifier.

Outputs:

- SteeringProposal schema
- ObservationSignal schema
- ContractAdjustmentRequest schema
- ProposalValidationResult schema
- StateCorrection schema
- DecisionLedgerEntry schema
- ReviewerDecision schema
- ControlRequest schema
- ProposalProvider interface

Design questions:

- Which proposal fields are generic enough to freeze?
- Where do proposal artifacts live in the evidence ledger?
- What proposal changes require reviewer or user authority?
- How are stale, unsafe, malformed, or overbroad proposals rejected?
- What safe points must check pending controls?

Acceptance:

- no live LLM is required for default runtime behavior
- valid deterministic proposals can be accepted and committed
- rejected proposals are recorded with structured reasons
- LLM interpretation cannot turn failed verification into closure
- proposal confidence never grants authority
- graph, host, and summary state store refs instead of raw prompts or
  transcripts

## Gate 6: Verification and Repair Protocol

Define how MissionForge reaches closure.

Outputs:

- validator result schema
- failed constraint schema
- repair contract schema
- redesign request schema
- repair routing policy
- review and authority gates

Design questions:

- How do validators map failures back to Mission IR constraints?
- What repair hints are declarative data versus runtime logic?
- How are generated tests treated as evidence?
- How are review-required states resumed after an independent reviewer decision?
- Which failures require redesign instead of repair?

Acceptance:

- repair does not depend on string-matching logs
- failure records include constraint IDs and missing evidence
- adaptive routing is mission-generic
- reviewer approval does not replace failed executable validators
- repair does not weaken the frozen contract

## Gate 7: Profile System

Define reusable capability and verification profiles.

Initial candidate profiles:

- `capability_bundle`
- `explicit_output_root`
- `user_provided_evidence_only`
- `no_raw_log_or_secret_ingestion`
- `local_file_path_safety`
- `no_overwrite_conflict_policy`
- `rust_helper_runtime`
- `synthetic_fixture_pack`
- `reference_documentation_pack`
- `markdown_output_contract`
- `generic_local_verification`
- `manual_review_gate`

Design questions:

- Are profiles data-only, code-backed, or both?
- How are profiles versioned?
- How does FrontDesk select profiles without task-name detection?
- What is the split between CapabilityProfile and VerificationProfile?

Acceptance:

- profile composition can represent a concrete product mission without a
  product-specific branch
- another unrelated mission can reuse at least half of the same profiles
- runtime decisions use expanded profile fragments, not profile names

## Gate 8: Runtime Engine

Define and implement the fixed runtime loop.

Loop:

```text
validate mission
resolve profiles
freeze contract and context
estimate mission state
propose or select work unit
validate proposal and authority
commit work unit
execute worker
collect observation
verify evidence
record state correction
route repair/review/redesign/closure
emit result
```

Design questions:

- Which state is durable?
- Which state is derived?
- How is resume represented without depending on a specific host framework?
- How are control requests consumed at safe points?

Acceptance:

- the core runtime has no LangGraph dependency
- the same runtime can be called from CLI, tests, services, or host adapters
- live LLM proposal mode is opt-in only
- runtime commits state only through validated contracts and evidence

## Gate 9: Worker Adapters

Define the PiWorker adapter contract. Other workers are explicitly out of scope
for this design cycle.

MissionForge is informed by the PI GitHub project and the current SkillFoundry
PiWorker integration. The design should initially mirror the proven PiWorker
shape: bounded work-unit input, observable event stream, tool-mediated
workspace writes, provider metrics, and refs-only output evidence.

Acceptance:

- PiWorker consumes the canonical work-unit contract
- PiWorker metrics normalize provider usage, cache reads, tool calls, and model
  calls
- provider-specific telemetry is preserved as evidence, not control logic
- PI attribution requirements are recorded before any PI-derived source is
  copied or adapted

## Gate 10: Host, Observation, and Control Adapters

Define optional adapters after the core runtime is stable.

Candidate adapters:

- LangGraph node
- CLI command
- Python API
- HTTP service
- read-only observer/dashboard
- explicit control request writer

Acceptance:

- host adapters do not own mission semantics
- host state can consume MissionResult without inspecting runtime internals
- observation adapters are read-only
- control adapters write intent, not hidden runtime mutations

## Gate 11: SkillFoundry Adapter

Rebuild SkillFoundry as an application shell on top of MissionForge.

Acceptance:

- FrontDesk compiles user needs into Mission IR
- Skill package generation uses MissionRuntime
- SkillFoundry code contains no mission-name verifier branches

## Implementation Execution

The design gates describe architecture order. Day-to-day component development
is governed by:

- `docs/DEVELOPMENT_GOAL_PROTOCOL.md`
- `docs/COMPONENT_DEVELOPMENT_PLAN.md`
- `docs/COMPONENT_ACCEPTANCE_MATRIX.md`

These documents translate the design gates into a six-phase implementation
sequence with MetaLoop-style design, checkpoint, verification, adaptive,
control, and observation rules.
