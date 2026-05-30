# Module: FrontDesk

## Goal

FrontDesk is MissionForge's formal requirements-discovery and intent-authoring
surface.

It turns natural-language intent, user answers, host-provided facts, optional
product-scoped inquiry metadata, and governed artifact refs into a reviewable
`FrontDeskIntentBundle`. Product integrations or the generic fallback compiler
then turn that bundle into MissionIR. This keeps users from hand-writing
MissionIR while preventing MissionForge core from learning product-specific
backend rules.

FrontDesk authoring intelligence is mandatory. The service layer may collect
conversation turns, inspect refs, and scout workspace/profile metadata without
a live authoring worker. It must fail closed before need grilling, solution
architecture, MissionIR mapping, or intent bundle authoring when no LLM/PiWorker
node has produced the required FrontDesk artifacts. Deterministic code may
preserve explicit evidence and validate schemas; it must not pretend to
understand user needs.

FrontDesk is a product-grade authoring surface, not a runtime shortcut and not
an MVP shell.

The active requirements-discovery behavior is specified in
`docs/FRONTDESK_SPEC_GRILL_DESIGN.md`. The refined product-context boundary is
specified in `docs/FRONTDESK_PRODUCT_CONTEXT_AND_INTENT_BUNDLE.md`, with the
development plan in `docs/PHASE22_FRONTDESK_PRODUCT_CONTEXT_PLAN.md`. The
planned live PiWorker authoring path is specified in
`docs/PHASE23_FRONTDESK_PIWORKER_AI_EXECUTION_PLAN.md`.

```text
user intent + source refs
  -> FrontDesk authoring session
  -> semantic lock and mission brief
  -> product inquiry slot filling when context is present
  -> FrontDeskIntentBundle
  -> ProductIntegration or GenericProductIntegration
  -> ProductContract and MissionIR
  -> user, policy, or product compiler approval
  -> freeze_mission
  -> MissionRuntime
```

## Scope

FrontDesk owns the pre-runtime authoring workflow:

- requirements elicitation;
- user-facing clarification;
- sanitized source and conversation provenance;
- semantic locking of task facts;
- product inquiry slot filling through injected ProductInquiryProfile metadata;
- product hypotheses and missing blocking-slot reporting;
- profile recommendation and profile requirement drafting for generic fallback
  and product compiler inputs;
- FrontDeskIntentBundle generation;
- generic MissionIR draft generation only as fallback compatibility;
- intent and mapping audit before product compile or generic freeze;
- user or policy approval records;
- freeze manifest and handoff refs;
- optional operator commands for authoring, inspection, freezing, and running.

`start`, `answer`, `inspect`, and metadata `scout` are not intelligence nodes
and can run offline. `grill`, `draft`, `plan`, `map`, and intent bundle
authoring require LLM-authored artifacts and fail closed with
`configure_frontdesk_llm` when those artifacts are absent.

FrontDesk is generic. It helps discover intent for software work,
documentation work, data work, research work, operational tasks, and external
products such as SkillFoundry. Product-specific meaning enters through
ProductInquiryProfile data, ProductIntegration packages, MissionIR fields,
ProfilePacks, validators, product gates, and evidence refs, not through
FrontDesk or runtime branches.

## Non-Goals

- no replacement for MissionRuntime;
- no PiWorker inner-loop control;
- no worker-owned acceptance;
- no product-specific SkillFoundry, Codexarium, benchmark, or customer branches
  in MissionForge core;
- no UI requirement for the first product implementation;
- no treating raw chat as runtime truth;
- no hidden profile grants from LLM output;
- no treating ProductInquiryProfile as runtime authority;
- no pretending generic fallback MissionIR satisfies product-specific gates;
- no contract mutation after freeze except through explicit mission revision.

## Position In MissionForge

FrontDesk sits before the frozen runtime contract.

```text
FrontDeskAuthoringSession
  -> FrontDeskIntentBundle
  -> ProductIntegration or GenericProductIntegration
  -> DraftMissionIR
  -> AuthoringApproval / ProductCompileResult
  -> FrozenMissionContract
  -> MissionRun
```

The runtime still consumes only `MissionIR` or frozen contract state. PiWorker
still consumes bounded `WorkUnitContract` objects. Product-aware FrontDesk
output is useful only after Product Integration compiles it, deterministic
validation passes, and freeze succeeds.

## Core Principle

```text
LLM drafts; deterministic code validates.
```

LLM-backed components may:

- summarize intent;
- ask high-value clarification questions;
- propose a mission shape;
- recommend profile refs;
- fill ProductInquiryProfile slots;
- propose product hypotheses and missing-slot questions;
- draft generic constraints, outputs, validators, and risk notes;
- audit whether an intent bundle or generic draft is coherent, feasible, and
  testable.

Deterministic MissionForge code must own:

- schema validation;
- source-ref admission;
- raw transcript exclusion;
- profile existence checks;
- profile requirement validation;
- validator language checks;
- ProductInquiryProfile schema validation;
- product compile readiness checks;
- user or policy approval;
- freeze and contract hashing;
- MissionIR validation;
- runtime handoff;
- revision authority after freeze.

LLM output is never accepted as task truth by itself.

The inverse is also required: deterministic code is never accepted as
user-need understanding by itself. If the LLM-backed authoring node is
unavailable, the workflow stops instead of fabricating a low-confidence draft.

## Relationship To Profiles

Profiles are the reusable capability and verification extension mechanism.
FrontDesk should use them as its primary abstraction for turning user intent
into executable MissionForge contracts when compiling generic fallback missions
or preparing product compiler inputs.

FrontDesk is responsible for selecting and explaining profile refs:

```text
user intent
  -> profile candidates
  -> profile recommendation rationale
  -> MissionIR.capability_profiles
  -> MissionIR.verification.verification_profiles
```

Profiles are responsible for deterministic expansion:

```text
CapabilityProfileRef / VerificationProfileRef
  -> expand_mission
  -> constraints
  -> evidence requirements
  -> required artifacts
  -> validator language
  -> review questions and known gaps
```

FrontDesk may recommend a profile only if the active registry knows it. It may
not invent profile behavior. Unknown profile ids, invalid requirements, unknown
validator types, or missing verifier implementations fail closed before freeze.

External products may provide ProfilePacks. FrontDesk can present those
profiles as authoring choices without adding product branches to MissionForge
runtime code.

## Relationship To Product Inquiry Profiles

ProductInquiryProfile is the authoring-time product identity and question plan.
It is provided by a Product Integration and consumed by the generic FrontDesk
engine.

```text
ProductIntegration.inquiry_profile()
  -> ProductInquiryProfile
  -> FrontDesk slot filling
  -> FrontDeskIntentBundle
  -> ProductIntegration.compile_intent()
```

ProductInquiryProfile may describe:

- product identity and activation terms;
- blocking, recommended, optional, and conditional inquiry slots;
- targeted questions and recommended answers;
- risk dimensions and acceptance prerequisites;
- downstream mapping targets such as product request fields, MissionIR paths, or
  product gate check ids.

It may not:

- grant runtime permissions;
- approve a product contract;
- verify completion;
- close a mission;
- require MissionForge core to import the product integration.

## Authoring Artifacts

FrontDesk should write durable, refs-first artifacts. Raw conversation may be
kept for provenance when allowed, but runtime-facing truth must be sanitized and
structured.

Recommended artifact set:

- `frontdesk/session.json`: refs-only authoring session state.
- `frontdesk/conversation.jsonl`: optional raw or redacted provenance log.
- `frontdesk/sanitized_sources.json`: admitted source refs and redaction notes.
- `frontdesk/semantic_lock.json`: stable task facts extracted from conversation
  and source refs.
- `frontdesk/mission_brief.json`: goal, users, desired outcome, non-goals,
  assumptions, risks, and open questions.
- `frontdesk/profile_recommendations.json`: candidate profiles, chosen profiles,
  requirements, rationale, and rejected alternatives.
- `frontdesk/mission_plan.json`: proposed outputs, constraints, evidence, and
  verification approach.
- `frontdesk/intent_bundle.json`: formal FrontDesk output for product-aware
  authoring, including generic refs, product context snapshot, slot values,
  missing blocking slots, risk flags, and readiness.
- `frontdesk/draft_mission.json`: validated draft MissionIR payload.
- `frontdesk/mission_audit.json`: coherence, feasibility, safety, profile, and
  verification audit.
- `frontdesk/authoring_approval.json`: user, reviewer, or policy approval
  record.
- `frontdesk/freeze_manifest.json`: final authoring refs, MissionIR ref,
  frozen contract ref, hashes, and authority record.

The exact filenames can evolve, but the separation must remain: conversation is
provenance, semantic lock is task truth, intent bundle is FrontDesk output,
Product Integration owns product contracts, and MissionIR is the runtime
contract.

## State Model

FrontDesk should expose a durable `FrontDeskAuthoringSession` with explicit
states:

```text
new
  -> eliciting
  -> draft_ready
  -> audit_required
  -> needs_clarification
  -> approval_required
  -> approved
  -> frozen
  -> handed_off
  -> human_review_required
  -> unsupported
  -> failed_closed
```

Draft artifacts can be revised freely. Approved artifacts may change only by
recording a new approval. Frozen artifacts may change only through MissionForge
revision or redesign.

## Authority Gates

FrontDesk must make authority explicit before runtime handoff.

Authority records should answer:

- Who approved the mission objective?
- Which output refs are expected?
- Which constraints are blocking?
- Which profiles and profile requirements are locked?
- Which validators are executable, manual, or unsupported?
- Which risks require reviewer or human authority?
- Which sources are admitted?
- Which sources are excluded?
- Which ProductInquiryProfile, if any, drove questioning?
- Which blocking product slots are missing or assumed?
- Which Product Integration compiled the final MissionIR?

No approved plan review means no freeze. No valid freeze means no runtime
handoff.

## Failure Modes

FrontDesk should fail closed or route to review when:

- user intent is too vague to produce testable success signals;
- the draft requires an unknown profile;
- a profile requirement is invalid;
- the mission requires a validator type not declared by verification profiles;
- a blocking validator is unsupported;
- the requested output cannot be verified;
- raw transcripts, prompts, secrets, or credentials would enter runtime truth;
- user goals conflict with constraints or safety boundaries;
- a selected ProductInquiryProfile has missing blocking slots;
- Product Integration refuses to compile the intent bundle;
- generic fallback is asked to satisfy product-specific gates;
- required authority exceeds the configured policy;
- the generated MissionIR does not validate;
- freeze hash or manifest validation fails.

These are product states, not prompt failures. The user should receive a clear
next action: clarify, approve, revise, add a ProfilePack, add a validator,
request reviewer authority, redesign, or stop.

## CLI And Programmatic Surface

The first product implementation should prioritize a stable CLI/API before a
visual UI.

Candidate command shape:

```bash
missionforge frontdesk start --workspace . --session frontdesk/session.json
missionforge frontdesk answer --session frontdesk/session.json --text "..."
missionforge frontdesk inspect --session frontdesk/session.json
missionforge frontdesk intent --session frontdesk/session.json
missionforge frontdesk draft --session frontdesk/session.json
missionforge frontdesk audit --session frontdesk/session.json
missionforge frontdesk approve --session frontdesk/session.json
missionforge frontdesk freeze --session frontdesk/session.json
missionforge frontdesk run --session frontdesk/session.json
```

Candidate Python surface:

```python
from missionforge.frontdesk import FrontDesk

session = FrontDesk(workspace=".").start("Build a local documentation task.")
session = session.answer("It should update package docs and verify links.")
intent = session.build_intent_bundle()
draft = session.draft_mission()
audit = session.audit()
frozen = session.approve().freeze()
result = frozen.run()
```

The API should expose refs and structured state, not raw provider payloads.

## LLM Provider Strategy

FrontDesk requires LLM intelligence for authoring. It should use
MissionForge's existing PiWorker-first direction without creating a second
production worker.

Acceptable implementation paths:

- use PiWorker as an internal authoring assistant through a bounded FrontDesk
  work unit;
- use a PiWorker-compatible adapter-family marker for production
  configuration, not a second provider abstraction;
- use deterministic scripted clients or prewritten LLM artifact fixtures in
  tests only when they include the same content-bound execution provenance as
  a PiWorker run.

The default test suite must remain offline and deterministic, but service-level
tests must not exercise a product path that silently falls back to
deterministic understanding. Live FrontDesk dogfood should be explicit opt-in.

## Runtime And Revision Interaction

FrontDesk is not only a start screen. It may also help interpret runtime
outcomes, but it must respect runtime authority.

After a run:

- verifier failure can route to repair if the frozen contract remains correct;
- contract mismatch can route to mission revision;
- missing product intent can route to FrontDesk redesign;
- unsupported verification can route to profile or validator extension;
- human authority remains human authority.

FrontDesk may draft a revision proposal. It may not silently weaken a frozen
contract or approve its own revision.

## Implementation Roadmap

### Phase 1: Contracts And State

- define `FrontDeskAuthoringSession`;
- define semantic lock, mission brief, profile recommendation, mission plan,
  audit, approval, and freeze manifest schemas;
- enforce refs-only state where required;
- add raw transcript and secret exclusion checks;
- document root/API surface.

### Phase 2: Deterministic Generic Compiler

- compile approved FrontDesk artifacts into valid generic fallback MissionIR;
- validate selected profile refs against a ProfileRegistry;
- validate verification profile refs and validator language;
- freeze through existing `freeze_mission`;
- emit mission ref, frozen contract ref, and freeze manifest.

### Phase 3: LLM-Assisted Authoring Nodes

- implement requirements elicitor;
- implement mission planner;
- implement spec/profile auditor;
- require JSON schema output;
- write failure artifacts on invalid model output;
- keep deterministic scripted clients for tests.

### Phase 4: Operator Surface

- add CLI commands for start, answer, inspect, draft, audit, approve, freeze,
  and run;
- add refs-only inspect output;
- add diagnosis for clarification, unsupported profiles, invalid validators,
  and authority gates.

### Phase 5: ProfilePack-Aware Product Use

- load external ProfilePacks for authoring;
- expose profile descriptions and requirements to FrontDesk;
- prove SkillFoundry and Codexarium can be expressed as profile-backed
  authoring flows without runtime branches.

### Phase 6: Product Dogfood

- run real authoring sessions through PiWorker-backed FrontDesk;
- freeze and run generated missions;
- compare generated MissionIR quality against hand-authored MissionIR;
- record failure categories and profile gaps;
- promote only after verifier/product-grade evidence, not worker self-report.

### Phase 7: Product Context And Intent Bundle

- define `ProductInquiryProfile` and `FrontDeskIntentBundle`;
- let Product Integration provide authoring-time inquiry metadata;
- make FrontDesk emit intent bundles before product compilation;
- define `ProductIntegration` and `ProductCompileResult` contracts;
- define generic ProductGate result contracts with product-owned criteria;
- treat existing MissionIRMapper as generic fallback behavior;
- formalize SkillFoundry's FrontDesk bridge outside core.

## Verification Strategy

FrontDesk implementation should include tests for:

- vague user request routes to clarification;
- clear request produces a valid draft MissionIR;
- product context produces a valid FrontDeskIntentBundle;
- missing blocking product slots route to clarification;
- Product Integration can compile an intent bundle or request clarification;
- generic fallback does not claim product-specific gate readiness;
- profile recommendation cites known profile ids only;
- unknown profile id fails closed;
- invalid profile requirements fail closed;
- validator type not declared by verification profiles fails closed;
- no raw transcript, prompt, model payload, or secret enters runtime-facing
  MissionIR;
- approval is required before freeze;
- frozen contract hash is stable;
- frozen MissionIR can run through `MissionRuntime`;
- external ProfilePack composition works without core runtime branches;
- SkillFoundry uses FrontDesk output as an integration, not as core runtime
  behavior.

## Current Status

Status: implemented product module with product context and intent-bundle first
slice.

Product context and intent-bundle boundaries are now implemented. The current
implementation still maps FrontDesk artifacts directly to MissionIR for generic
compatibility, but that path is explicitly represented as
`GenericProductIntegration`, not as the permanent FrontDesk responsibility.

The current implementation includes:

- strict FrontDesk schemas and authoring session state;
- refs-first workspace artifacts and provenance separation;
- spec-grill schemas for workspace facts, profile snapshots, decision trees,
  core need briefs, grilling reports, semantic coverage reports, solution
  plans, plan reviews, mapping reports, and freeze gate results;
- deterministic workspace/profile scouting before user questioning;
- LLM node templates for NeedGriller and SolutionArchitect that fail closed
  unless PiWorker-authored artifacts exist;
- semantic coverage checks over explicit AI-authored domain language and
  semantic-lock clauses, not raw conversation guessing;
- solution planning with known profile recommendations and explicit plan
  review;
- generic fallback MissionIR mapping with requirement coverage reports;
- `ProductInquiryProfile` contracts for authoring-time product metadata;
- `FrontDeskIntentBundle` contracts and `frontdesk/intent_bundle.json` output;
- `ProductIntegration`, `ProductCompileResult`, and generic `ProductGate`
  result contracts;
- `FrontDesk.build_intent_bundle()` and `FrontDesk.compile_product()` service
  APIs;
- CLI commands for `frontdesk intent` and `frontdesk compile-product`;
- deterministic generic MissionIR compiler and freeze gate;
- fail-closed service facade for authoring operations when no LLM/PiWorker
  authoring node has produced the required artifacts;
- spec-grill `draft()` command that now stops at the LLM boundary instead of
  using deterministic authoring fallback;
- LLM-assisted elicitor, planner, and auditor boundaries with scripted tests;
- CLI commands for start, answer, inspect, scout, grill, cover-semantics, plan,
  review-plan, map, draft, intent, compile-product, audit, approve, freeze,
  and run;
- opt-in PiWorker node runner that builds bounded contracts, requires explicit
  adapter injection, validates exact expected refs, and records execution
  provenance without adding another worker abstraction;
- runtime feedback recommendations for repair, resume, revision, redesign,
  profile or validator extension, human review, and stop;
- SkillFoundry dogfood and formal SkillFoundry FrontDesk bridge that consume
  FrontDesk-generated refs from `integrations/skillfoundry` without adding core
  runtime branches.

Verified on 2026-05-30 with:

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_schema.py \
  tests/test_frontdesk_state.py \
  tests/test_frontdesk_workspace.py \
  tests/test_frontdesk_compiler.py \
  tests/test_frontdesk_freeze_gate.py \
  tests/test_frontdesk_profile_integration.py \
  tests/test_frontdesk_service.py \
  tests/test_frontdesk_elicitor.py \
  tests/test_frontdesk_planner.py \
  tests/test_frontdesk_auditor.py \
  tests/test_frontdesk_llm_boundaries.py \
  tests/test_frontdesk_cli.py \
  tests/test_frontdesk_runtime_feedback.py \
  tests/test_frontdesk_spec_grill_schema.py \
  tests/test_frontdesk_scout.py \
  tests/test_frontdesk_need_griller.py \
  tests/test_frontdesk_semantic_coverage.py \
  tests/test_frontdesk_solution_architect.py \
  tests/test_frontdesk_plan_review.py \
  tests/test_frontdesk_mission_mapper.py \
  tests/test_frontdesk_mapping_auditor.py \
  tests/test_frontdesk_spec_grill_freeze_gate.py \
  tests/test_frontdesk_spec_grill_service.py \
  tests/test_frontdesk_spec_grill_e2e.py \
  tests/test_frontdesk_spec_grill_acceptance.py \
  tests/test_frontdesk_spec_grill_boundaries.py \
tests/test_frontdesk_pi_node_runner.py
# Ran 81 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 359 tests: OK (skipped=2)

MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
# MissionForge validation passed

./scripts/validate_integrations.sh skillfoundry
# Ran 84 tests: OK (skipped=1)

git diff --check
# passed
```

## Remaining Product Questions

- How should FrontDesk present external ProfilePack descriptions to users?
- Which approval modes are acceptable for non-interactive host integrations?
- How much live PiWorker-backed authoring should be enabled by default after
  the current bounded node contract helper is hardened?
- Which additional product dogfood scenarios should become non-optional gates
  after SkillFoundry?
