# FrontDesk Spec-Grill Implementation Plan

Last updated: 2026-05-29

Status: `implemented first product slice`

## Document Role

This document turns `docs/FRONTDESK_SPEC_GRILL_DESIGN.md` into an executable
development plan.

The design document defines why spec-grill must exist and what authority
boundaries it must respect. This implementation plan defines how to build it in
MissionForge without drifting from those requirements.

Implementation note:

The first offline deterministic product slice has been implemented. It includes
SG0-SG12 contract/test coverage, deterministic scout, NeedGriller, semantic
coverage, solution planning, plan review, MissionIR mapping, audit/freeze
integration, CLI commands, and an opt-in PiWorker node runner that requires an
explicit PiWorker-compatible adapter. Live provider smoke remains separately
gated future hardening; default tests remain offline and deterministic.

Architecture refinement:

The implemented MissionIR mapping path should now be treated as generic
fallback behavior. Product-aware FrontDesk should emit `FrontDeskIntentBundle`
and let Product Integration compile product contracts and final product-domain
MissionIR. See `docs/FRONTDESK_PRODUCT_CONTEXT_AND_INTENT_BUNDLE.md` and
`docs/PHASE22_FRONTDESK_PRODUCT_CONTEXT_PLAN.md`.

Completion of this plan should produce a FrontDesk that:

- actively discovers the user's real need instead of passively collecting form
  fields;
- uses workspace and profile facts before asking the user;
- asks one high-value question at a time by default;
- preserves user intent through semantic coverage;
- proposes a mature solution plan before MissionIR mapping;
- requires explicit plan review before freeze;
- maps every approved requirement into MissionIR with a mapping report;
- lets an independent audit criticize the mapping;
- freezes only through deterministic code;
- remains generic MissionForge core, with product behavior in profiles,
  validators, and integrations.

## Inputs

This plan is based on:

- `docs/FRONTDESK_SPEC_GRILL_DESIGN.md`
- `docs/modules/frontdesk.md`
- `docs/FRONTDESK_IMPLEMENTATION_GUIDE.md`
- `docs/IMPLEMENTATION_STATUS_AND_NEXT_PHASES.md`
- existing `src/missionforge/frontdesk/*` implementation
- SkillFoundry Front Desk prior art
- MetaLoop control discipline
- the public `grill-me` interaction pattern as prior art only

## Non-Negotiable Constraints

These rules apply to every phase.

1. MissionForge core stays task-independent.
2. No SkillFoundry, Codexarium, benchmark, customer, or mission-name branches in
   `src/missionforge`.
3. Product behavior enters through ProfilePacks, validators, integration
   packages, and admitted source refs.
4. PiWorker remains the only live LLM worker direction.
5. Default tests stay deterministic and offline.
6. LLM nodes may draft, infer, recommend, map, and audit only.
7. LLM nodes may not approve, freeze, verify, run, mutate frozen contracts, or
   close missions.
8. Raw prompts, transcripts, provider payloads, messages, secrets, credentials,
   and authorization material must not enter runtime-facing artifacts.
9. Runtime closure remains verifier-owned.
10. Existing FrontDesk compiler/freeze behavior must not be weakened.

## Original Baseline Before This Implementation

MissionForge currently has:

```text
src/missionforge/frontdesk/
  schema.py
  state.py
  workspace.py
  compiler.py
  freeze_gate.py
  elicitor.py
  planner.py
  auditor.py
  runtime_feedback.py
  service.py
  cli.py
```

Original strengths:

- refs-only authoring session state;
- raw conversation stored behind content refs;
- deterministic generic compiler from approved artifacts to MissionIR;
- deterministic freeze through existing profile/freeze path;
- LLM boundary wrappers for elicitor, planner, and auditor;
- CLI surface for start, answer, draft, audit, approve, freeze, run;
- runtime feedback first slice;
- test coverage for existing contracts.

Original gap closed by this implementation:

- `FrontDesk.draft()` used a shallow deterministic draft path;
- there is no workspace/profile scout;
- NeedGriller is not implemented as an active decision-tree node;
- semantic coverage does not check that important user signals survive;
- solution planning is not separated from MissionIR mapping;
- plan review is not a first-class gate;
- MissionIR mapping does not produce a clause-by-clause mapping report;
- FreezeGate does not yet require semantic coverage, plan review, and mapping
  coverage.

The implementation replaced that default path with the deterministic offline
spec-grill convenience flow. The old deterministic helper remains only as a
compatibility fixture for direct tests and legacy code paths.

## Target Architecture

Final authoring flow:

```text
start / answer
  -> scout
  -> grill
  -> semantic_coverage
  -> plan_solution
  -> review_plan
  -> map_mission
  -> audit_mapping
  -> approve
  -> freeze
  -> run
```

Node authority:

| Node | Can Read | Can Write | Cannot Do |
| --- | --- | --- | --- |
| WorkspaceScout | admitted refs, profile registry | workspace facts, profile snapshot, domain language | final requirements, approval, freeze |
| NeedGriller | conversation refs, workspace facts, profile snapshot | decision tree, core need brief, grilling report | plan approval, MissionIR mapping, freeze |
| SemanticCoverage | conversation refs, semantic lock, decision tree | semantic coverage report | weaken or drop requirements silently |
| SolutionArchitect | semantic lock, coverage, facts, profile snapshot | solution plan, profile recommendations, risk register | invent profiles, approve, freeze |
| PlanReview | solution plan, semantic lock | plan review record | runtime handoff |
| MissionIRMapper / GenericProductIntegration | approved plan, semantic lock, profiles | draft generic MissionIR, mapping report, mission plan | freeze, verify, close, product-specific compile |
| ProductIntegrationCompiler | FrontDeskIntentBundle, product inquiry profile, product contract rules | product request, product contract, product-domain MissionIR, compile report | runtime execution, verifier closure, product gate pass |
| MissionIRAuditor | draft MissionIR, mapping report, plan, or product compile report | audit report | freeze |
| FreezeGate | all approved artifacts | freeze result, manifest, mission, frozen contract | best-effort freeze |

## Target Code Layout

Prefer small, generic modules. Do not move existing stable modules unless
necessary.

Add:

```text
src/missionforge/frontdesk/spec_grill_schema.py
src/missionforge/frontdesk/scout.py
src/missionforge/frontdesk/need_griller.py
src/missionforge/frontdesk/semantic_coverage.py
src/missionforge/frontdesk/solution_architect.py
src/missionforge/frontdesk/mission_mapper.py
src/missionforge/frontdesk/spec_grill.py
src/missionforge/frontdesk/pi_node_runner.py
```

Expected responsibilities:

- `spec_grill_schema.py`: new artifact contracts and enums.
- `scout.py`: deterministic workspace/profile fact discovery.
- `need_griller.py`: active grilling node and scripted test client support.
- `semantic_coverage.py`: deterministic coverage checks.
- `solution_architect.py`: solution plan and profile recommendation boundary.
- `mission_mapper.py`: approved solution plan to MissionIR and mapping report.
- `spec_grill.py`: orchestration service used by `FrontDesk`.
- `pi_node_runner.py`: opt-in PiWorker-backed structured LLM node execution.

Update:

```text
src/missionforge/frontdesk/__init__.py
src/missionforge/frontdesk/state.py
src/missionforge/frontdesk/service.py
src/missionforge/frontdesk/cli.py
src/missionforge/frontdesk/compiler.py
src/missionforge/frontdesk/freeze_gate.py
src/missionforge/frontdesk/auditor.py
src/missionforge/frontdesk/elicitor.py
src/missionforge/frontdesk/planner.py
```

Existing `elicitor.py`, `planner.py`, and `auditor.py` should remain as stable
compatibility boundaries. They can delegate to the richer spec-grill nodes over
time.

## Target Artifact Refs

Existing refs remain:

```text
frontdesk/session.json
frontdesk/conversation.jsonl
frontdesk/sanitized_sources.json
frontdesk/semantic_lock.json
frontdesk/mission_brief.json
frontdesk/profile_recommendations.json
frontdesk/mission_plan.json
frontdesk/draft_mission.json
frontdesk/mission_audit.json
frontdesk/authoring_approval.json
frontdesk/freeze_manifest.json
```

Add:

```text
frontdesk/workspace_facts.json
frontdesk/profile_catalog_snapshot.json
frontdesk/domain_language.json
frontdesk/source_admission_report.json
frontdesk/decision_tree.json
frontdesk/core_need_brief.json
frontdesk/need_grilling_report.json
frontdesk/semantic_coverage.json
frontdesk/solution_plan.json
frontdesk/solution_plan.md
frontdesk/plan_risk_register.json
frontdesk/plan_review.json
frontdesk/mission_mapping_report.json
frontdesk/freeze_gate_result.json
```

Only sanitized, structured artifacts may become runtime-facing truth. Raw
conversation remains provenance-only.

## State Strategy

Do not overbuild the state machine.

The public `FrontDeskStatus` enum can remain coarse:

```text
new
eliciting
needs_clarification
draft_ready
audit_required
approval_required
approved
frozen
handed_off
human_review_required
unsupported
failed_closed
```

Fine-grained progress should be represented by:

- `next_action`;
- explicit artifact refs;
- artifact schema status fields;
- `FrontDeskInspectResult`.

Add enum values only if operator behavior becomes ambiguous. If new values are
added, tests must prove old state files still load or fail with a clear
migration error.

Recommended `next_action` values:

```text
scout
grill
answer_question
semantic_coverage
plan_solution
review_plan
map_mission
audit_mapping
approve
freeze
run
human_review
profile_extension
validator_extension
redesign
failed_closed
```

## Approval And Hash Model

The final flow has two distinct approvals.

### Plan Review

`PlanReviewRecord` approves or rejects the proposed solution plan.

It must include:

- `session_id`
- `decision`
- `reviewed_plan_ref`
- `reviewed_plan_hash`
- `reviewed_by`
- `authority`
- `review_notes`
- `requested_changes`
- `created_at`

MissionIR mapping is blocked unless the plan review decision is `approve` and
the reviewed hash matches the current `solution_plan.json`.

### Authoring Approval

`AuthoringApproval` approves the final authoring bundle before freeze.

The approved bundle hash should include:

- semantic lock;
- semantic coverage report;
- solution plan;
- plan review record;
- profile recommendations;
- mission plan;
- draft generic MissionIR or product-compiled MissionIR ref;
- mapping report or product compile report;
- authoring audit;
- sanitized sources.

FreezeGate must reject stale approvals.

## Phase SG0: Lock The Target With Tests First

### Goal

Create failing or pending tests that describe the final behavior before broad
implementation begins.

### Files

Add:

```text
tests/test_frontdesk_spec_grill_acceptance.py
tests/test_frontdesk_spec_grill_boundaries.py
```

### Test Cases

Acceptance tests should encode these product truths:

- vague input produces one targeted question with inference and recommended
  answer;
- user-proposed implementation is treated as a hypothesis;
- workspace facts suppress redundant questions;
- semantic coverage fails when a meaningful user signal is dropped;
- solution plan must be reviewed before MissionIR mapping;
- mapping report must cover every semantic lock clause;
- audit can block unclear or untestable missions;
- freeze fails without semantic coverage, plan review, mapping report, audit,
  and approval;
- raw prompt/transcript/secret fields fail recursively;
- SkillFoundry/Codexarium product names do not appear in core routing logic;
- live PiWorker is opt-in and offline scripted tests are default.

### Acceptance

The tests may start as skipped with explicit reason only for phases not yet
implemented. Each later phase must unskip the relevant tests.

Command:

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_spec_grill_acceptance.py \
  tests/test_frontdesk_spec_grill_boundaries.py
```

## Phase SG1: Spec-Grill Schemas

### Goal

Add generic, refs-first contracts for all new artifacts.

### Files

Add:

```text
src/missionforge/frontdesk/spec_grill_schema.py
tests/test_frontdesk_spec_grill_schema.py
```

Update:

```text
src/missionforge/frontdesk/__init__.py
src/missionforge/frontdesk/state.py
tests/test_frontdesk_state.py
tests/test_public_api_boundary.py
```

### Contracts

Implement:

- `WorkspaceFact`
- `WorkspaceFacts`
- `ProfileCatalogSnapshot`
- `DomainLanguage`
- `SourceAdmissionReport`
- `DecisionOption`
- `DecisionNode`
- `DecisionTree`
- `CoreNeedBrief`
- `GrillingQuestion`
- `NeedGrillingReport`
- `SemanticCoverageItem`
- `MissionSemanticCoverageReport`
- `MissionSolutionPlan`
- `PlanRiskRegister`
- `PlanReviewRecord`
- `RequirementMapping`
- `MissionIRMappingReport`
- `FrontDeskFreezeGateResult`

Required methods:

- `from_dict()`
- `to_dict()`
- `validate()`

Validation requirements:

- unknown fields fail unless under explicit `metadata`;
- all refs pass `validate_ref`;
- repeated ids fail closed;
- status enums are strict;
- empty required strings fail;
- raw fields fail recursively:
  - `conversation`
  - `messages`
  - `prompt`
  - `prompts`
  - `raw_prompt`
  - `model_output`
  - `raw_model_output`
  - `transcript`
  - `raw_transcript`
  - `secret`
  - `credential`
  - `credentials`
  - `api_key`
  - `authorization`
  - `password`

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_spec_grill_schema.py \
  tests/test_frontdesk_state.py \
  tests/test_public_api_boundary.py
```

## Phase SG2: Workspace And Profile Scout

### Goal

Let FrontDesk inspect admitted workspace and profile facts before asking the
user questions.

### Files

Add:

```text
src/missionforge/frontdesk/scout.py
tests/test_frontdesk_scout.py
```

Update:

```text
src/missionforge/frontdesk/workspace.py
src/missionforge/frontdesk/service.py
src/missionforge/frontdesk/cli.py
```

### Behavior

`WorkspaceScout.scout()` should:

- read only admitted refs and safe project metadata;
- snapshot capability and verification profile ids;
- record profile requirement schemas when available;
- record facts with `fact_id`, summary, confidence, and source refs;
- record which likely questions are already answered by workspace facts;
- write `workspace_facts.json`, `profile_catalog_snapshot.json`,
  `domain_language.json`, and `source_admission_report.json`;
- fail closed on unsafe refs.

It should not:

- infer final requirements;
- select final profiles;
- read arbitrary private files;
- copy raw file contents into runtime-facing truth.

### CLI

Add:

```bash
missionforge frontdesk scout --session frontdesk/session.json
```

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_scout.py \
  tests/test_frontdesk_workspace.py \
  tests/test_frontdesk_cli.py
```

## Phase SG3: NeedGriller

### Goal

Replace passive elicitation with active, restrained need discovery.

### Files

Add:

```text
src/missionforge/frontdesk/need_griller.py
tests/test_frontdesk_need_griller.py
```

Update:

```text
src/missionforge/frontdesk/elicitor.py
src/missionforge/frontdesk/service.py
src/missionforge/frontdesk/cli.py
tests/test_frontdesk_elicitor.py
tests/test_frontdesk_llm_boundaries.py
```

### Behavior

`NeedGriller.grill()` should:

- consume conversation refs, workspace facts, profile snapshot, and prior
  decision tree;
- produce or update decision tree;
- produce core need brief when enough information exists;
- produce one `GrillingQuestion` by default when clarity is insufficient;
- include inference, recommended answer, question, why it matters, blocking
  decision ids, and answer type;
- refuse vague catch-all questions;
- avoid asking facts already answered by workspace facts;
- route max-round exhaustion to review or fail-closed;
- use scripted deterministic client in tests.

### LLM Boundary

Live mode must use a structured client contract:

```text
input: refs and structured facts
output: NeedGrillingReport JSON only
authority: draft/propose
allowed write scope: frontdesk/need_grilling_report.json, frontdesk/decision_tree.json, frontdesk/core_need_brief.json
```

### CLI

Add:

```bash
missionforge frontdesk grill --session frontdesk/session.json
```

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_need_griller.py \
  tests/test_frontdesk_elicitor.py \
  tests/test_frontdesk_llm_boundaries.py \
  tests/test_frontdesk_cli.py
```

## Phase SG4: Semantic Lock And Coverage

### Goal

Ensure that important user signals are preserved or explicitly rejected before
solution planning.

### Files

Add:

```text
src/missionforge/frontdesk/semantic_coverage.py
tests/test_frontdesk_semantic_coverage.py
```

Update:

```text
src/missionforge/frontdesk/service.py
src/missionforge/frontdesk/cli.py
tests/test_frontdesk_schema.py
```

### Behavior

`SemanticCoverageChecker.check()` should:

- compare conversation/source signals to semantic lock and decision tree;
- verify that meaningful terms and requirement clauses are covered;
- require explicit rejection rationale for dropped signals;
- track coverage status per signal;
- fail when privacy, authority, verification, or implementation preferences are
  lost without explanation;
- write `semantic_coverage.json`.

Signals to test explicitly:

- `Rust`
- `schema`
- `health`
- `privacy`
- `long-running`
- `performance`
- `local`
- `do not expose internals`

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_semantic_coverage.py \
  tests/test_frontdesk_schema.py \
  tests/test_frontdesk_cli.py
```

## Phase SG5: SolutionArchitect And Profile Planning

### Goal

Produce a mature solution plan before MissionIR mapping.

### Files

Add:

```text
src/missionforge/frontdesk/solution_architect.py
tests/test_frontdesk_solution_architect.py
```

Update:

```text
src/missionforge/frontdesk/planner.py
src/missionforge/frontdesk/service.py
src/missionforge/frontdesk/cli.py
tests/test_frontdesk_planner.py
tests/test_frontdesk_profile_integration.py
```

### Behavior

`SolutionArchitect.plan()` should:

- consume semantic lock, coverage, core need brief, workspace facts, decision
  tree, and profile snapshot;
- produce `solution_plan.json` and optionally `solution_plan.md`;
- separate MVP, future scope, rejected directions, risks, authority needs, and
  verification strategy;
- produce `profile_recommendations.json`;
- select only known profiles;
- route missing capabilities to profile extension or validator extension;
- refuse to invent profile behavior.

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_solution_architect.py \
  tests/test_frontdesk_planner.py \
  tests/test_frontdesk_profile_integration.py
```

## Phase SG6: Plan Review Gate

### Goal

Make solution plan review a first-class gate before MissionIR mapping.

### Files

Add:

```text
tests/test_frontdesk_plan_review.py
```

Update:

```text
src/missionforge/frontdesk/service.py
src/missionforge/frontdesk/cli.py
src/missionforge/frontdesk/spec_grill_schema.py
tests/test_frontdesk_service.py
tests/test_frontdesk_cli.py
```

### Behavior

Add service method:

```python
FrontDesk.review_plan(session_ref, *, reviewed_by, decision, authority, notes=None)
```

The method should:

- load `solution_plan.json`;
- compute stable plan hash;
- write `plan_review.json`;
- transition to next action `map_mission` only when decision is `approve`;
- route `request_revision`, `reject`, and `human_review_required` explicitly.

MissionIR mapping must reject:

- missing plan review;
- non-approved plan review;
- stale plan hash.

### CLI

Add:

```bash
missionforge frontdesk review-plan --session frontdesk/session.json --approved-by <id>
```

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_plan_review.py \
  tests/test_frontdesk_service.py \
  tests/test_frontdesk_cli.py
```

## Phase SG7: MissionIRMapper And Mapping Report

### Goal

Map the approved solution plan into DraftMissionIR with full requirement
coverage.

### Files

Add:

```text
src/missionforge/frontdesk/mission_mapper.py
tests/test_frontdesk_mission_mapper.py
```

Update:

```text
src/missionforge/frontdesk/compiler.py
src/missionforge/frontdesk/service.py
src/missionforge/frontdesk/cli.py
tests/test_frontdesk_compiler.py
```

### Behavior

`MissionIRMapper.map()` should:

- require approved plan review;
- generate `frontdesk/mission_plan.json`;
- generate `frontdesk/draft_mission.json`;
- generate `frontdesk/mission_mapping_report.json`;
- map every semantic lock requirement clause;
- map every expected artifact;
- map every success signal to validator or manual gate;
- map every selected profile;
- record dropped or transformed clauses with rationale;
- fail closed on unknown profiles or validator types.

The existing `build_mission_ir()` may remain the deterministic compiler core,
but it must consume mapping artifacts rather than bypass them.

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_mission_mapper.py \
  tests/test_frontdesk_compiler.py \
  tests/test_frontdesk_profile_integration.py
```

## Phase SG8: MissionIRAuditor And FreezeGate Upgrade

### Goal

Require audit, coverage, mapping, and approval before deterministic freeze.

### Files

Update:

```text
src/missionforge/frontdesk/auditor.py
src/missionforge/frontdesk/freeze_gate.py
src/missionforge/frontdesk/compiler.py
src/missionforge/frontdesk/service.py
tests/test_frontdesk_auditor.py
tests/test_frontdesk_freeze_gate.py
```

Add:

```text
tests/test_frontdesk_mapping_auditor.py
tests/test_frontdesk_spec_grill_freeze_gate.py
```

### Behavior

Auditor must check:

- mapping report covers every requirement;
- outputs are testable;
- raw fields are absent;
- unsupported validators are routed;
- profile requirements are valid;
- authority needs are explicit.

FreezeGate must require:

- `semantic_coverage.json` status passed;
- approved `plan_review.json` with matching plan hash;
- `mission_mapping_report.json` with no unmapped blocking requirements;
- `mission_audit.json` decision approve;
- `authoring_approval.json` with current approved bundle hash;
- valid `sanitized_sources.json`;
- valid profile expansion;
- valid MissionIR freeze.

Write:

```text
frontdesk/freeze_gate_result.json
```

The result must explain every failed gate with structured reasons.

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_mapping_auditor.py \
  tests/test_frontdesk_spec_grill_freeze_gate.py \
  tests/test_frontdesk_auditor.py \
  tests/test_frontdesk_freeze_gate.py
```

## Phase SG9: Service Orchestration

### Goal

Expose the full spec-grill flow through `FrontDesk` while preserving explicit
operator control.

### Files

Add:

```text
src/missionforge/frontdesk/spec_grill.py
tests/test_frontdesk_spec_grill_service.py
```

Update:

```text
src/missionforge/frontdesk/service.py
tests/test_frontdesk_service.py
```

### Behavior

Add high-level methods:

```python
FrontDesk.scout(session_ref)
FrontDesk.grill(session_ref)
FrontDesk.cover_semantics(session_ref)
FrontDesk.plan_solution(session_ref)
FrontDesk.review_plan(session_ref, ...)
FrontDesk.map_mission(session_ref)
FrontDesk.audit(session_ref)
FrontDesk.approve(session_ref, ...)
FrontDesk.freeze(session_ref)
```

Migration rule for `FrontDesk.draft()`:

- final default behavior must not call the shallow deterministic draft;
- it should either run the full spec-grill path when all prerequisites and
  clients are configured, or return a clear next action;
- shallow draft should move behind an explicit fixture method or test-only
  deterministic helper.

Suggested final behavior:

```text
FrontDesk.draft()
  if no core need -> route to grill
  if no semantic coverage -> route to semantic_coverage
  if no approved plan -> route to review_plan
  if approved plan exists -> map_mission
```

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_spec_grill_service.py \
  tests/test_frontdesk_service.py \
  tests/test_frontdesk_spec_grill_acceptance.py
```

## Phase SG10: CLI And Operator Surface

### Goal

Make the spec-grill workflow usable and inspectable from the operator CLI.

### Files

Update:

```text
src/missionforge/frontdesk/cli.py
tests/test_frontdesk_cli.py
tests/test_operator_cli_contracts.py
```

### Commands

Add or revise:

```bash
missionforge frontdesk scout
missionforge frontdesk grill
missionforge frontdesk cover-semantics
missionforge frontdesk plan
missionforge frontdesk review-plan
missionforge frontdesk map
missionforge frontdesk audit
missionforge frontdesk approve
missionforge frontdesk freeze
missionforge frontdesk inspect
```

`inspect` should show:

- status;
- next action;
- artifact refs;
- missing required artifacts;
- failed gates;
- latest question;
- review status;
- freeze readiness.

Command results must remain refs-only and operator-safe.

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_cli.py \
  tests/test_operator_cli_contracts.py \
  tests/test_operator_cli_inspect.py
```

## Phase SG11: PiWorker Node Runner

### Goal

Support live LLM-backed spec-grill nodes through PiWorker without adding a
second worker abstraction.

### Files

Add:

```text
src/missionforge/frontdesk/pi_node_runner.py
tests/test_frontdesk_pi_node_runner.py
```

Update:

```text
src/missionforge/frontdesk/need_griller.py
src/missionforge/frontdesk/solution_architect.py
src/missionforge/frontdesk/mission_mapper.py
src/missionforge/frontdesk/auditor.py
tests/test_frontdesk_llm_boundaries.py
```

Do not update `src/missionforge/piworker_runtime.py` unless live provider
configuration needs new generic PiWorker factory behavior. FrontDesk should use
the existing PiWorker adapter protocol by explicit injection.

### Behavior

`FrontDeskPiNodeRunner` should:

- build bounded `WorkUnitContract` objects;
- expose only declared `visible_refs`;
- allow writes only under node-owned `frontdesk/*` refs;
- require exact expected output refs;
- reject raw prompt/transcript/provider payload leakage;
- record node execution refs as evidence/provenance;
- fail closed on malformed output.

Live provider execution must be opt-in. Default tests use scripted/faux clients.

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_pi_node_runner.py \
  tests/test_pi_agent_runtime_import_boundaries.py \
  tests/test_piworker_import_boundaries.py
```

Live smoke stays separately gated:

```bash
MISSIONFORGE_PIWORKER_LIVE=1 PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_pi_node_runner_live_smoke.py
```

Only add the live smoke test when provider configuration is stable enough. It
must be skipped by default.

## Phase SG12: End-To-End Dogfood And Regression Hardening

### Goal

Prove the completed FrontDesk meets the design requirements without polluting
MissionForge core.

### Files

Add:

```text
tests/test_frontdesk_spec_grill_e2e.py
```

Update as needed:

```text
integrations/skillfoundry/tests/*
scripts/validate_integrations.sh
docs/FRONTDESK_IMPLEMENTATION_GUIDE.md
docs/FRONTDESK_DEVELOPMENT_RUNBOOK.md
docs/IMPLEMENTATION_STATUS_AND_NEXT_PHASES.md
```

### E2E Scenarios

1. Vague user asks for a local high-performance implementation.
   - NeedGriller asks whether the real concern is performance, packaging,
     protection from core edits, or task-specific pollution.
   - Rust is preserved as an implementation preference, not blindly made a
     mandatory profile.

2. Workspace facts answer a profile question.
   - FrontDesk does not ask the user which built-in verification profiles
     exist.

3. User mentions privacy and raw logs.
   - Semantic coverage proves the privacy constraint survives into solution
     plan and MissionIR.

4. Planner needs an unknown capability.
   - The route is profile extension, not a core branch.

5. Mapper drops a requirement.
   - Mapping report fails and FreezeGate refuses freeze.

6. Auditor approves but FreezeGate detects stale plan hash.
   - Freeze fails deterministically.

7. SkillFoundry dogfood mission uses integration profiles.
   - MissionForge core stays free of SkillFoundry-specific imports or route
     branches.

### Acceptance

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_spec_grill_e2e.py \
  tests/test_frontdesk_spec_grill_acceptance.py \
  tests/test_frontdesk_spec_grill_boundaries.py
```

Then run focused FrontDesk suite:

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_schema.py \
  tests/test_frontdesk_state.py \
  tests/test_frontdesk_workspace.py \
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
  tests/test_frontdesk_cli.py \
  tests/test_frontdesk_runtime_feedback.py
```

Then full validation:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
./scripts/validate_integrations.sh skillfoundry
git diff --check
```

## Completion Definition

Spec-grill FrontDesk is complete only when all of the following are true.

### Product Behavior

- A vague request no longer turns directly into a shallow MissionIR.
- FrontDesk asks one high-value question with inference and recommended answer
  when the core need is unclear.
- FrontDesk uses workspace/profile facts before asking the user.
- FrontDesk can produce a core need brief, decision tree, semantic lock,
  semantic coverage report, solution plan, plan review, mapping report, audit,
  approval, freeze manifest, MissionIR, and frozen contract.
- The user or policy can review the solution plan before MissionIR mapping.
- MissionIR mapping is explainable requirement by requirement.
- Freeze refuses incomplete, stale, unmapped, unsupported, or unaudited
  authoring bundles.

### Architecture

- MissionForge core remains task-independent.
- SkillFoundry-specific behavior remains under `integrations/skillfoundry`.
- Adapters contain no product-specific task logic.
- Profiles and validators express reusable task semantics.
- PiWorker is the only live LLM path.
- Default tests are deterministic and offline.

### Safety And Governance

- Raw conversation is provenance only.
- Runtime-facing artifacts are sanitized and refs-first.
- LLM output is never approval, freeze, verification, or closure.
- Verifier-owned runtime closure remains unchanged.
- Stale approval hashes fail closed.
- Unsupported validator/profile needs route to extension or review.

### Verification

- Focused FrontDesk suite passes.
- Full MissionForge validation passes.
- SkillFoundry integration validation passes.
- Import-boundary tests prove no product contamination.
- `git diff --check` passes.

## Development Order

Recommended order:

1. SG0 acceptance tests.
2. SG1 schemas.
3. SG2 scout.
4. SG3 NeedGriller.
5. SG4 semantic coverage.
6. SG5 solution architect.
7. SG6 plan review.
8. SG7 mapper.
9. SG8 auditor/freeze upgrade.
10. SG9 service orchestration.
11. SG10 CLI.
12. SG11 PiWorker node runner.
13. SG12 dogfood and regression hardening.

Do not start live PiWorker work before the offline scripted pipeline is fully
passing. Live intelligence should improve answer quality, not supply missing
authority.

## Review Checklist

Before merging any spec-grill phase, check:

- Does the change preserve deterministic/offline tests?
- Does it keep raw conversation out of runtime truth?
- Does it avoid product-specific branches?
- Does every new artifact have schema validation?
- Does every LLM output have a deterministic validator?
- Does every failure produce a structured route?
- Does FreezeGate still own freeze?
- Does MissionRuntime remain unaware of FrontDesk internals?
- Does the operator surface show refs and next actions clearly?
- Does this reduce user burden instead of adding a checklist?

## Final Guardrail

The implementation should always satisfy this control sentence:

```text
FrontDesk actively discovers and structures intent.
Profiles express reusable semantics.
LLM nodes propose and audit.
Deterministic gates approve, map, and freeze.
Verifier-owned runtime proves completion.
```

If a future patch violates that sentence, it is not implementing spec-grill.
