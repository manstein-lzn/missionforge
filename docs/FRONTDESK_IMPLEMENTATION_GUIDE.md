# FrontDesk Implementation Guide

Last updated: 2026-05-30

Status: `implemented`

## Purpose

This guide is the executable development plan for MissionForge FrontDesk.

The authoritative architecture reference is `docs/modules/frontdesk.md`. This
document converts that design into phases, files, tests, and acceptance gates a
developer can follow directly.

For the current product-context architecture, use
`docs/FRONTDESK_PRODUCT_CONTEXT_AND_INTENT_BUNDLE.md` and
`docs/PHASE22_FRONTDESK_PRODUCT_CONTEXT_PLAN.md`. For a current-state,
start-coding-now runbook, use `docs/FRONTDESK_DEVELOPMENT_RUNBOOK.md`.

FrontDesk must be implemented as a formal MissionForge product capability:

```text
natural language + governed source refs
  -> FrontDesk authoring artifacts
  -> FrontDeskIntentBundle
  -> ProductIntegration or GenericProductIntegration
  -> approved MissionIR
  -> freeze_mission
  -> MissionRuntime
```

It is not an MVP, not a SkillFoundry adapter, and not a runtime inner loop.

## Non-Negotiable Rules

1. FrontDesk is generic requirements discovery and intent bundling. Direct
   MissionIR authoring is generic fallback behavior.
2. Product-specific behavior stays outside `src/missionforge`.
3. Runtime code must not branch on FrontDesk, SkillFoundry, Codexarium, product
   names, mission names, or benchmark names.
4. LLM output may draft, recommend, and audit. It may not approve, freeze,
   verify, or mutate a frozen contract.
5. Profiles and ProfilePacks are the extension mechanism for reusable
   capability semantics.
6. Raw chat, prompts, provider payloads, transcripts, secrets, and credentials
   must not enter runtime-facing MissionIR or frozen contracts.
7. Default tests must stay deterministic and offline.
8. PiWorker remains the only LLM worker direction. Do not add a second
   production worker abstraction for FrontDesk.

## Target Package Layout

Add a new package under `src/missionforge/frontdesk/`:

```text
src/missionforge/frontdesk/
  __init__.py
  schema.py
  state.py
  workspace.py
  compiler.py
  freeze_gate.py
  elicitor.py
  planner.py
  auditor.py
  service.py
  cli.py
```

Expected responsibilities:

- `schema.py`: dataclasses and validation for authoring artifacts.
- `state.py`: `FrontDeskAuthoringSession` and state transitions.
- `workspace.py`: safe ref read/write helpers backed by `JsonWorkspaceStore`.
- `compiler.py`: approved FrontDesk artifacts to generic fallback `MissionIR`.
- `freeze_gate.py`: deterministic approval, validation, and freeze manifest.
- `elicitor.py`: LLM-assisted clarification boundary with scripted test client.
- `planner.py`: LLM-assisted MissionIR/profile draft boundary.
- `auditor.py`: LLM-assisted spec/profile/verification audit boundary.
- `service.py`: high-level `FrontDesk` facade.
- `cli.py`: operator commands once core contracts are stable.

Do not add FrontDesk code under `src/missionforge/adapters/`.

## Public API Target

After the first stable implementation, export only generic symbols from the
package root:

```python
from missionforge import (
    FrontDesk,
    FrontDeskAuthoringSession,
    FrontDeskState,
    MissionSemanticLock,
    MissionBrief,
    ProfileRecommendationSet,
    MissionPlan,
    MissionAuthoringAudit,
    AuthoringApproval,
    FrontDeskFreezeManifest,
)
```

Do not export product-specific SkillFoundry or Codexarium contracts from
`missionforge`.

## Artifact Refs

Use these refs unless an implementation reason forces a documented change:

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
missions/<session_id>.mission.json
missions/<session_id>.frozen_contract.json
```

Runtime-facing artifacts are:

- `frontdesk/semantic_lock.json`
- `frontdesk/mission_brief.json`
- `frontdesk/profile_recommendations.json`
- `frontdesk/mission_plan.json`
- `frontdesk/draft_mission.json`
- `frontdesk/authoring_approval.json`
- `frontdesk/freeze_manifest.json`
- `missions/<session_id>.mission.json`
- `missions/<session_id>.frozen_contract.json`

`frontdesk/conversation.jsonl` is provenance only. It must not be referenced as
runtime task truth unless a sanitized derivative explicitly admits selected
facts.

## Phase 1: Schema And State

### Goal

Create the deterministic FrontDesk contract layer and state machine.

### Files

Add:

- `src/missionforge/frontdesk/__init__.py`
- `src/missionforge/frontdesk/schema.py`
- `src/missionforge/frontdesk/state.py`
- `src/missionforge/frontdesk/workspace.py`
- `tests/test_frontdesk_schema.py`
- `tests/test_frontdesk_state.py`
- `tests/test_frontdesk_workspace.py`

Update:

- `src/missionforge/__init__.py`
- `docs/API_BOUNDARY.md` if exported symbols differ from the target.

### Contracts To Implement

Use frozen dataclasses where practical. Every contract needs `from_dict()`,
`to_dict()`, and `validate()`.

Required contracts:

- `FrontDeskState`
- `FrontDeskAuthoringSession`
- `ConversationTurn`
- `SanitizedSourceSet`
- `MissionSemanticLock`
- `MissionBrief`
- `ProfileRecommendation`
- `ProfileRecommendationSet`
- `MissionPlan`
- `MissionAuthoringAudit`
- `AuthoringApproval`
- `FrontDeskFreezeManifest`

Suggested state values:

```text
new
eliciting
draft_ready
audit_required
needs_clarification
approval_required
approved
frozen
handed_off
human_review_required
unsupported
failed_closed
```

### Validation Requirements

- reject unknown fields unless the contract explicitly has `metadata`;
- reject unsafe refs using existing `validate_ref`;
- reject empty ids and empty summary fields;
- reject duplicate profile ids in selected recommendations;
- reject approval records without authority, approved ref, and approved hash;
- reject freeze manifests whose MissionIR or frozen contract refs are missing;
- reject forbidden raw fields recursively:
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
  - `api_key`
  - `authorization`
  - `password`

### Tests

Add tests proving:

- each schema round-trips through dict;
- unknown fields fail closed;
- unsafe refs fail closed;
- raw transcript/prompt/secret fields fail closed;
- session state transitions reject invalid jumps;
- approved and frozen states require the expected refs;
- state payload remains refs-first and does not embed raw conversation text.

### Acceptance Command

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_schema.py \
  tests/test_frontdesk_state.py \
  tests/test_frontdesk_workspace.py
```

## Phase 2: Deterministic Compiler

### Goal

Compile approved FrontDesk artifacts into valid MissionIR and freeze it through
the existing MissionForge profile/freeze pipeline.

### Files

Add:

- `src/missionforge/frontdesk/compiler.py`
- `src/missionforge/frontdesk/freeze_gate.py`
- `tests/test_frontdesk_compiler.py`
- `tests/test_frontdesk_freeze_gate.py`
- `tests/test_frontdesk_profile_integration.py`

Update:

- `src/missionforge/frontdesk/__init__.py`
- `src/missionforge/__init__.py`

### Compiler Input

The compiler consumes only structured artifacts:

- `MissionSemanticLock`
- `MissionBrief`
- `ProfileRecommendationSet`
- `MissionPlan`
- `AuthoringApproval`

It must not consume raw conversation text or raw LLM provider output.

### Compiler Output

The compiler writes:

- `frontdesk/draft_mission.json`
- `missions/<session_id>.mission.json`
- `missions/<session_id>.frozen_contract.json`
- `frontdesk/freeze_manifest.json`

The compiler returns a refs-only result containing:

- session id;
- MissionIR ref;
- frozen contract ref;
- contract hash;
- profile ids;
- approval ref;
- freeze manifest ref;
- warnings;
- next action.

### MissionIR Mapping

Map FrontDesk artifacts as follows:

- `MissionBrief.goal` -> `MissionObjective.summary`
- `MissionBrief.deliverable_type` -> `MissionObjective.deliverable_type`
- `MissionBrief.success_signals` -> `MissionObjective.success_signals`
- semantic lock source refs -> `MissionIR.inputs["admitted_source_refs"]`
- excluded refs -> `MissionIR.inputs["excluded_source_refs"]`
- planned artifacts -> `MissionIR.outputs["required_artifacts"]`
- selected capability profiles -> `MissionIR.capability_profiles`
- selected verification profiles -> `MissionIR.verification["verification_profiles"]`
- planned validators -> `MissionIR.verification["validators"]`
- manual gates -> `MissionIR.verification["manual_gates"]`
- risk notes -> constraints or observability, depending on whether blocking
- approval metadata -> `MissionIR.observability["frontdesk_approval_ref"]`

### Profile Validation

Use `ProfileRegistry.builtins()` by default, with optional caller-provided
registry.

Before freeze:

- every selected capability profile must exist;
- every selected verification profile must exist;
- profile requirements must be JSON-compatible;
- validator types must be declared by active verification profiles;
- `expand_mission()` must succeed;
- `freeze_mission()` must succeed.

### Tests

Add tests proving:

- approved artifacts compile to valid `MissionIR`;
- generated MissionIR freezes deterministically;
- unknown capability profile fails closed;
- unknown verification profile fails closed;
- validator type not declared by verification profile fails closed;
- no approval means no freeze;
- freeze manifest hash matches frozen contract hash;
- raw conversation ref is excluded from runtime truth;
- external `ProfilePack` can be supplied and used without runtime branches.

### Acceptance Command

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_compiler.py \
  tests/test_frontdesk_freeze_gate.py \
  tests/test_frontdesk_profile_integration.py \
  tests/test_profiles.py \
  tests/test_freeze.py
```

## Phase 3: Deterministic Service Facade

### Goal

Provide a usable programmatic FrontDesk facade before adding live LLM behavior.

### Files

Add:

- `src/missionforge/frontdesk/service.py`
- `tests/test_frontdesk_service.py`

Update:

- `src/missionforge/frontdesk/__init__.py`
- `src/missionforge/__init__.py`

### API Shape

Implement a synchronous facade:

```python
frontdesk = FrontDesk(workspace=".")
session = frontdesk.start("Build a documentation updater.")
session = frontdesk.answer(session.session_ref, "It should update README.")
draft = frontdesk.draft(session.session_ref)
audit = frontdesk.audit(session.session_ref)
approval = frontdesk.approve(session.session_ref, approved_by="user")
frozen = frontdesk.freeze(session.session_ref)
```

In this phase, `draft()` may use deterministic heuristics or scripted inputs,
but it must still produce the real schema artifacts and run the real compiler.

### Tests

Add tests proving:

- start writes session state;
- answer appends provenance without making raw text runtime truth;
- draft produces structured artifacts;
- inspect returns refs-only status;
- approve records authority;
- freeze returns valid MissionIR and frozen contract refs;
- frozen mission can be loaded with `MissionIR.from_dict`.

### Acceptance Command

```bash
PYTHONPATH=src python3 -m unittest tests/test_frontdesk_service.py
```

## Phase 4: LLM-Assisted Authoring Nodes

### Goal

Add intelligent authoring while keeping deterministic tests and authority
boundaries.

### Files

Add:

- `src/missionforge/frontdesk/elicitor.py`
- `src/missionforge/frontdesk/planner.py`
- `src/missionforge/frontdesk/auditor.py`
- `tests/test_frontdesk_elicitor.py`
- `tests/test_frontdesk_planner.py`
- `tests/test_frontdesk_auditor.py`
- `tests/test_frontdesk_llm_boundaries.py`

### Node Contracts

Each LLM node must:

- accept structured input artifacts and allowed source refs;
- return exactly one JSON-compatible payload;
- validate output with FrontDesk schemas;
- write failure artifacts on invalid output;
- never approve or freeze;
- never write raw provider payloads into runtime-facing artifacts;
- support deterministic scripted clients in tests.

### Elicitor Responsibilities

- identify missing fields;
- ask one or a few high-value questions;
- update `MissionBrief` and `MissionSemanticLock` drafts;
- route to `needs_clarification` when required facts are missing.

### Planner Responsibilities

- propose MissionIR shape;
- recommend profiles from the active registry;
- draft constraints, expected outputs, and validators;
- explain rejected profile alternatives.

### Auditor Responsibilities

- check clarity, feasibility, safety, profile validity, and testability;
- identify unsupported validator or authority issues;
- route to approve, clarify, human review, unsupported, or failed closed.

### PiWorker Strategy

Do not add a second production worker.

Use one of these two paths:

- a narrow structured-output adapter backed by current PiWorker/live provider
  config;
- a bounded MissionRuntime work unit that asks PiWorker to produce FrontDesk
  authoring artifacts.

Keep the first implementation behind an explicit provider config. Default tests
must use scripted clients.

### Tests

Add tests proving:

- vague input produces a clarification question;
- clear input produces a draft plan;
- planner only selects known profile ids;
- auditor blocks unknown validator language;
- invalid JSON output fails closed with a failure artifact;
- model output cannot approve, freeze, or bypass the compiler;
- provider secrets do not appear in artifacts.

### Acceptance Command

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_frontdesk_elicitor.py \
  tests/test_frontdesk_planner.py \
  tests/test_frontdesk_auditor.py \
  tests/test_frontdesk_llm_boundaries.py
```

## Phase 5: CLI Surface

### Goal

Expose FrontDesk as a practical operator tool.

### Files

Add:

- `src/missionforge/frontdesk/cli.py`
- `tests/test_frontdesk_cli.py`

Update:

- `src/missionforge/adapters/cli.py` only if the existing CLI shell should
  dispatch `frontdesk` subcommands.
- docs under `docs/modules/host_adapters.md` if CLI behavior becomes part of
  the operator surface.

### Commands

Implement:

```bash
missionforge frontdesk start --workspace . --text "..."
missionforge frontdesk answer --workspace . --session frontdesk/session.json --text "..."
missionforge frontdesk inspect --workspace . --session frontdesk/session.json --json
missionforge frontdesk draft --workspace . --session frontdesk/session.json
missionforge frontdesk audit --workspace . --session frontdesk/session.json
missionforge frontdesk approve --workspace . --session frontdesk/session.json --approved-by user
missionforge frontdesk freeze --workspace . --session frontdesk/session.json
missionforge frontdesk run --workspace . --session frontdesk/session.json
```

The CLI must:

- emit JSON when `--json` is provided;
- keep inspection refs-only;
- not print raw provider payloads or secrets;
- fail closed on invalid state;
- require approval before freeze;
- use existing `MissionRuntime` for `run`.

### Tests

Add tests proving:

- each command works on a happy path;
- `freeze` fails before approval;
- `inspect --json` is refs-only;
- invalid session ref fails closed;
- `run` uses the generated MissionIR ref and normal runtime path.

### Acceptance Command

```bash
PYTHONPATH=src python3 -m unittest tests/test_frontdesk_cli.py
```

## Phase 6: Revision And Runtime Feedback

### Goal

Let FrontDesk help users interpret failed runs without bypassing runtime
authority.

### Files

Add:

- `src/missionforge/frontdesk/runtime_feedback.py` if this does not fit cleanly
  in `service.py`.
- `tests/test_frontdesk_runtime_feedback.py`

### Behavior

Given a `MissionRunAudit`, `MissionResult`, verifier failure, or revision
diagnosis, FrontDesk may recommend:

- repair;
- resume;
- mission revision;
- redesign;
- profile extension;
- validator extension;
- human review;
- stop.

It may draft a `MissionRevisionRequest`, but existing revision authority gates
must decide whether the revision is accepted.

### Tests

Add tests proving:

- verifier failure routes to repair guidance;
- contract mismatch routes to revision guidance;
- unsupported validator routes to profile/validator extension guidance;
- FrontDesk cannot auto-approve a revision;
- user-reserved authority remains user-reserved.

### Acceptance Command

```bash
PYTHONPATH=src python3 -m unittest tests/test_frontdesk_runtime_feedback.py
```

## Phase 7: Product Dogfood

### Goal

Prove FrontDesk can author real missions for downstream products without core
runtime branches.

### Required Scenarios

1. Generic file/documentation mission.
2. SkillFoundry capability bundle mission using external integration/profile
   data.
3. Codexarium-style non-prompt-only skill mission, if the required profile and
   validator pack exists.

### Files

Add or update:

- `integrations/skillfoundry/tests/test_skillfoundry_frontdesk_flow.py`
- optional `integrations/codexarium/...` only if codexarium integration exists
  outside MissionForge core.
- `docs/modules/frontdesk.md` with verification evidence.

### Tests

Add tests proving:

- FrontDesk-generated MissionIR runs through `MissionRuntime`;
- product-specific code stays under `integrations/*`;
- MissionForge core imports no SkillFoundry/Codexarium modules;
- product-grade checks remain outside worker self-report.

### Acceptance Command

```bash
./scripts/validate_integrations.sh skillfoundry
PYTHONPATH=src python3 -m unittest tests/test_adapter_import_boundaries.py
```

## Final Integration Gate

Before marking FrontDesk implementation complete, run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
./scripts/validate_integrations.sh skillfoundry
git diff --check
```

If Node runtime behavior changes as part of PiWorker-backed authoring, also run:

```bash
cd workers/pi-agent-runtime && npm test
```

Live FrontDesk/PiWorker dogfood must be opt-in and skipped by default.

## Implementation Evidence

Implemented on 2026-05-29.

Phase coverage:

- Phase 1 schema, state, and workspace contracts are implemented.
- Phase 2 deterministic compiler and freeze gate are implemented.
- Phase 3 deterministic service facade is implemented.
- Phase 4 LLM-assisted authoring node boundaries are implemented with scripted
  tests.
- Phase 5 CLI surface is implemented and operator-envelope safe.
- Phase 6 runtime feedback recommendations are implemented and cannot
  auto-approve revisions.
- Phase 7 SkillFoundry dogfood is implemented under `integrations/skillfoundry`
  without core product branches.

Verification:

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
  tests/test_frontdesk_runtime_feedback.py
# Ran 44 tests: OK

PYTHONPATH=src python3 -m unittest \
  tests/test_adapter_import_boundaries.py \
  tests/test_profiles.py \
  tests/test_freeze.py \
  tests/test_public_api_boundary.py
# Ran 18 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 292 tests: OK (skipped=2)

./scripts/validate_integrations.sh skillfoundry
# Ran 48 tests: OK (skipped=1)

git diff --check
# passed
```

## Implementation Order

Do not skip directly to LLM-backed authoring.

The order is:

1. contracts;
2. deterministic compiler;
3. deterministic service facade;
4. LLM nodes with scripted tests;
5. CLI;
6. runtime feedback;
7. product dogfood.

This order protects the core product guarantee: the intelligent part can be
improved without weakening MissionForge's deterministic contract boundary.

## Development Checklist

Use this checklist for every implementation PR or agent run:

- [ ] No product-specific branch was added under `src/missionforge`.
- [ ] No runtime branch was added for FrontDesk output.
- [ ] LLM output is validated before use.
- [ ] Approval is required before freeze.
- [ ] Frozen changes go through revision, not silent FrontDesk mutation.
- [ ] Runtime-facing artifacts are refs-first.
- [ ] Raw transcripts and provider payloads are excluded from MissionIR.
- [ ] Profile ids are resolved through `ProfileRegistry`.
- [ ] Validator types are declared by verification profiles.
- [ ] Default tests are offline and deterministic.
- [ ] Docs are updated with status and verification evidence.

## First Work Unit Prompt

Use this as the first implementation prompt:

```text
Implement Phase 1 of docs/FRONTDESK_IMPLEMENTATION_GUIDE.md.

Add src/missionforge/frontdesk/{__init__.py,schema.py,state.py,workspace.py}
and tests/test_frontdesk_{schema,state,workspace}.py.

Do not implement LLM calls, CLI, MissionIR compilation, SkillFoundry behavior,
or runtime changes. Keep the package generic. Ensure forbidden raw transcript,
prompt, provider payload, and secret fields are rejected. Run the Phase 1
acceptance command and git diff --check.
```
