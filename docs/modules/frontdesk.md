# Module: FrontDesk

## Goal

FrontDesk is MissionForge's formal MissionIR authoring tool.

It turns natural-language intent, user answers, host-provided facts, and
governed artifact refs into a reviewable MissionIR authoring contract. It
exists to make MissionForge usable without requiring users to hand-write
MissionIR while preserving the same contract, evidence, profile, freeze, and
verification discipline as the runtime.

FrontDesk is a product-grade authoring surface, not a runtime shortcut and not
an MVP shell.

```text
user intent + source refs
  -> FrontDesk authoring session
  -> semantic lock and mission brief
  -> profile recommendations
  -> draft MissionIR
  -> user or policy approval
  -> freeze_mission
  -> MissionRuntime
```

## Scope

FrontDesk owns the pre-runtime authoring workflow:

- requirements elicitation;
- user-facing clarification;
- sanitized source and conversation provenance;
- semantic locking of task facts;
- profile recommendation and profile requirement drafting;
- MissionIR draft generation;
- MissionIR audit and repair before freeze;
- user or policy approval records;
- freeze manifest and handoff refs;
- optional operator commands for authoring, inspection, freezing, and running.

FrontDesk is generic. It helps author MissionForge missions for software work,
documentation work, data work, research work, operational tasks, and external
products such as SkillFoundry. Product-specific meaning enters through
MissionIR fields, ProfilePacks, validators, and evidence refs, not through
runtime branches.

## Non-Goals

- no replacement for MissionRuntime;
- no PiWorker inner-loop control;
- no worker-owned acceptance;
- no product-specific SkillFoundry, Codexarium, benchmark, or customer branches
  in MissionForge core;
- no UI requirement for the first product implementation;
- no treating raw chat as runtime truth;
- no hidden profile grants from LLM output;
- no contract mutation after freeze except through explicit mission revision.

## Position In MissionForge

FrontDesk sits before the frozen runtime contract.

```text
FrontDeskAuthoringSession
  -> DraftMissionIR
  -> AuthoringApproval
  -> FrozenMissionContract
  -> MissionRun
```

The runtime still consumes only `MissionIR` or frozen contract state. PiWorker
still consumes bounded `WorkUnitContract` objects. FrontDesk output is useful
only after deterministic validation and freeze.

## Core Principle

```text
LLM drafts; deterministic code validates.
```

LLM-backed components may:

- summarize intent;
- ask high-value clarification questions;
- propose a mission shape;
- recommend profile refs;
- draft constraints, outputs, validators, and risk notes;
- audit whether a draft is coherent, feasible, and testable.

Deterministic MissionForge code must own:

- schema validation;
- source-ref admission;
- raw transcript exclusion;
- profile existence checks;
- profile requirement validation;
- validator language checks;
- user or policy approval;
- freeze and contract hashing;
- MissionIR validation;
- runtime handoff;
- revision authority after freeze.

LLM output is never accepted as task truth by itself.

## Relationship To Profiles

Profiles are the reusable capability and verification extension mechanism.
FrontDesk should use them as its primary abstraction for turning user intent
into executable MissionForge contracts.

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
- `frontdesk/draft_mission.json`: validated draft MissionIR payload.
- `frontdesk/mission_audit.json`: coherence, feasibility, safety, profile, and
  verification audit.
- `frontdesk/authoring_approval.json`: user, reviewer, or policy approval
  record.
- `frontdesk/freeze_manifest.json`: final authoring refs, MissionIR ref,
  frozen contract ref, hashes, and authority record.

The exact filenames can evolve, but the separation must remain: conversation is
provenance, semantic lock is task truth, MissionIR is the runtime contract.

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
draft = session.draft_mission()
audit = session.audit()
frozen = session.approve().freeze()
result = frozen.run()
```

The API should expose refs and structured state, not raw provider payloads.

## LLM Provider Strategy

FrontDesk requires LLM intelligence for high-quality authoring. It should use
MissionForge's existing PiWorker-first direction without creating a second
production worker.

Acceptable implementation paths:

- use PiWorker as an internal authoring assistant through a bounded FrontDesk
  work unit;
- use a narrow LLM adapter that returns structured FrontDesk draft artifacts;
- use deterministic scripted clients in default tests.

The default test suite must remain offline and deterministic. Live FrontDesk
dogfood should be explicit opt-in.

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

### Phase 2: Deterministic Compiler

- compile approved FrontDesk artifacts into valid MissionIR;
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

## Verification Strategy

FrontDesk implementation should include tests for:

- vague user request routes to clarification;
- clear request produces a valid draft MissionIR;
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

Status: implemented product module.

The current implementation includes:

- strict FrontDesk schemas and authoring session state;
- refs-first workspace artifacts and provenance separation;
- deterministic MissionIR compiler and freeze gate;
- deterministic service facade;
- LLM-assisted elicitor, planner, and auditor boundaries with scripted tests;
- CLI commands for start, answer, inspect, draft, audit, approve, freeze, and
  run;
- runtime feedback recommendations for repair, resume, revision, redesign,
  profile or validator extension, human review, and stop;
- SkillFoundry dogfood that consumes FrontDesk-generated refs from
  `integrations/skillfoundry` without adding core runtime branches.

Verified on 2026-05-29 with:

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

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 292 tests: OK (skipped=2)

./scripts/validate_integrations.sh skillfoundry
# Ran 48 tests: OK (skipped=1)

git diff --check
# passed
```

## Remaining Product Questions

- How should FrontDesk present external ProfilePack descriptions to users?
- Which approval modes are acceptable for non-interactive host integrations?
- Should live PiWorker-backed authoring use a normal MissionRuntime work unit or
  a narrower structured-output assistant boundary?
- Which additional product dogfood scenarios should become non-optional gates
  after SkillFoundry?
