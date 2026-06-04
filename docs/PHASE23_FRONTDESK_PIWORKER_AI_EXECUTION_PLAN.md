# Phase 23: FrontDesk PiWorker AI Execution Plan

Last updated: 2026-06-03

Status: partially implemented historical plan. FrontDesk PiWorker authoring
now exists through `FrontDeskPiNodeRunner`, `FrontDesk.with_default_piworker`,
and CLI `--use-default-piworker`. This document remains useful for FrontDesk
authoring provenance and fail-closed requirements, but the current default
runtime target is TaskContract-native PiWorker execution, not MissionIR as the
primary product path.

## Purpose

Phase 22 established the product-context boundary:

```text
FrontDesk + ProductInquiryProfile -> FrontDeskIntentBundle
ProductIntegration + FrontDeskIntentBundle -> TaskContract + product refs
TaskContract-native Runtime -> PiWorker executor + independent Judge PiWorker
ProductGate -> product readiness
```

The current implementation correctly fails closed when FrontDesk needs
semantic authoring but no LLM/PiWorker-authored artifacts exist. It also has an
explicit PiWorker authoring path. The remaining FrontDesk work is to keep that
path aligned with the TaskContract-native kernel: FrontDesk authors intent,
ProductIntegration compiles a TaskContract, and the TaskContract flow invokes
bounded PiWorker executor and judge calls.

## Current State

The codebase already has most of the deterministic shell needed for this
phase:

- `src/missionforge/frontdesk/service.py` records conversations, scouts
  workspace/profile metadata, validates artifact readiness, builds intent
  bundles, and compiles through external product integrations.
- `src/missionforge/frontdesk/pi_node_runner.py` builds bounded
  `WorkUnitContract` objects for FrontDesk PiWorker nodes and validates
  produced refs.
- `src/missionforge/frontdesk/need_griller.py`,
  `src/missionforge/frontdesk/solution_architect.py`, and
  `src/missionforge/frontdesk/spec_grill.py` expose role/output templates but
  intentionally fail closed instead of providing deterministic authoring.
- `src/missionforge/frontdesk/inquiry_profile.py` and
  `src/missionforge/frontdesk/intent_bundle.py` define product inquiry and
  intent-bundle contracts.
- `src/missionforge/product_integration.py` and
  `src/missionforge/product_gate.py` define generic product integration and
  gate envelopes.
- `integrations/skillfoundry/src/missionforge_skillfoundry/` provides a
  reference product integration that owns SkillFoundry-specific inquiry
  slots, compilation, product contracts, MissionIR generation, frozen
  contracts, and gate specs.

Recent dogfood behavior is also correct for the current boundary:

```text
FrontDesk.start/answer/scout: succeeds
FrontDesk.grill/build_intent_bundle/compile_product: fails closed
next_action: configure_frontdesk_llm
reason: explicit LLM/PiWorker node is required
```

This proves the deterministic fallback has been removed. Phase 23 must keep
that property while making the live AI path work.

## Non-Negotiable Constraints

1. PiWorker is the only LLM worker direction.
2. No alternative LLM-worker abstraction should be introduced.
3. No deterministic Python keyword, regex, filename, or artifact-name logic may
   infer user intent, product slots, or product readiness.
4. FrontDesk core must not contain SkillFoundry, Codexarium, finance, trading,
   benchmark, customer, or application-specific branches.
5. Product-specific logic belongs in Product Integration packages.
6. ProductInquiryProfile is data for inquiry; it is not runtime authority.
7. Product Integration owns product-domain MissionIR compilation.
8. MissionForge Runtime must consume only MissionIR/frozen contracts, not raw
   FrontDesk conversation or product-private state.
9. Raw conversation may be visible to FrontDesk AI authoring nodes only as
   authoring provenance. It must not become runtime truth.
10. Runtime-facing artifacts must be sanitized, structured, refs-first, and
    validated.
11. If the configured PiWorker node is missing, invalid, unavailable, writes
    outside scope, omits required refs, or emits invalid schema, FrontDesk must
    fail closed.
12. Tests may use scripted PiWorker adapters or prewritten AI-authored
    fixtures, but those fixtures must be explicit worker outputs with matching
    content-bound execution records, not hidden deterministic understanding.
13. Python may validate, route, persist, hash, compare refs, assemble
    canonical envelopes from already-authored fields, and ask the next stored
    question. Python may not replace the AI node's semantic work.
14. AI-authored artifacts are accepted only when their current bytes are bound
    to a validated node execution record by content hash, input hash, node spec
    hash, session id, node name, and, when applicable, product profile hash.

## Design Thesis

```text
AI drafts meaning. Deterministic code proves boundaries.
```

FrontDesk is a high-AI authoring surface. The complex part is not storing a
chat transcript or filling a form. The complex part is extracting the user's
real pain when the user does not know what they do not know, asking only the
few questions that change the downstream solution, and turning that result
into a product-aware but product-neutral intent bundle.

That intelligence must live in PiWorker-authored nodes. MissionForge core
should provide:

- durable session state;
- role and output contracts;
- visible input refs;
- allowed write scopes;
- schema validators;
- source-admission gates;
- product profile injection as data;
- execution records proving which node authored which artifact;
- fail-closed service transitions.

It should not provide a hand-coded intent extractor.

## Target Architecture

```text
User
  -> FrontDesk.start / FrontDesk.answer
  -> FrontDesk.scout
       writes workspace facts, profile catalog snapshot,
       domain language, source admission report
  -> NeedGriller PiWorker node
       asks restrained clarification questions and writes core need artifacts
  -> SemanticCoverageChecker
       deterministic validation over AI-authored artifacts
  -> additional FrontDesk.answer + NeedGriller loop when needed
  -> SolutionArchitect PiWorker node
       writes product-neutral solution plan and risk register
  -> IntentBundleAuthor PiWorker node
       consumes ProductInquiryProfile and AI-authored FrontDesk artifacts
       writes product slot candidate values and intent-bundle candidate
  -> FrontDesk deterministic intent finalizer
       validates candidate, profile hash, refs, missing slots, source policy
       writes canonical frontdesk/intent_bundle.json
  -> ProductIntegration.compile_intent()
       owns product request, TaskContract, workspace policy, permission
       manifest, judge rubric, product refs, and product clarification requests
  -> TaskContract-native MissionForge runtime
       executes only frozen TaskContract state through PiWorkerCall
  -> independent Judge PiWorker + ProductGate refs
       close semantic acceptance and product readiness separately
```

The product-specific path for SkillFoundry should become:

```text
SkillFoundryInquiryProfile
  -> FrontDesk AI grilling with SkillFoundry inquiry context
  -> FrontDeskIntentBundle
  -> SkillFoundryFrontDeskIntegration.compile_intent()
  -> SkillFoundryRequest
  -> SkillFoundryProductContract
  -> TaskContract + WorkspacePolicy + PermissionManifest + JudgeRubric
  -> SkillFoundry ProductGradeGate refs

MissionIR output is compatibility-only for generic fallback or migration. It is
not the desired default runtime authority for product-aware flows.
```

## Node Model

### Node 1: NeedGriller

Purpose:

- behave like a restrained requirements interviewer;
- infer the user's real pain from messy natural-language statements;
- identify contradictions, hidden assumptions, and high-impact unknowns;
- ask at most one or a small bounded number of high-value questions per turn;
- produce core need artifacts once enough semantic coverage exists.

Visible refs:

```text
frontdesk/conversation.jsonl
frontdesk/workspace_facts.json
frontdesk/source_admission_report.json
frontdesk/profile_catalog_snapshot.json
frontdesk/product_inquiry_profile.json   # optional, data only
```

Expected outputs:

NeedGriller has two output modes. A clarification turn may produce only the
per-turn report and question. A completion turn must also produce the durable
semantic artifacts needed downstream.

Per-turn required outputs:

```text
frontdesk/decision_tree.json
frontdesk/need_grilling_report.json
```

Completion outputs:

```text
frontdesk/core_need_brief.json
frontdesk/sanitized_sources.json
frontdesk/semantic_lock.json
frontdesk/mission_brief.json
```

Quality obligations:

- ask questions that reveal constraints, desired outcomes, non-goals, users,
  risks, acceptance signals, and product-relevant missing information;
- distinguish what the user explicitly said, what the node inferred, and what
  remains unknown;
- avoid asking implementation trivia before the need is understood;
- avoid exposing raw conversation in runtime-facing artifacts;
- never approve, compile, freeze, verify, or run the mission.

Deterministic validation:

- required refs exist;
- schemas validate;
- output refs stay under `frontdesk/`;
- raw prompt/transcript/provider/secret fields are rejected recursively;
- `source_refs` point to admitted refs;
- next question is present when coverage is incomplete;
- downstream authoring is blocked until the completion outputs exist and are
  hash-bound to the current NeedGriller execution;
- `core_need_brief` cannot be treated as complete unless required fields are
  non-empty and source-backed.

### Node 2: SemanticCoverageChecker

Purpose:

- deterministic gate over AI-authored artifacts;
- decide whether enough structured semantic coverage exists to plan a
  solution;
- produce blocking gaps when coverage is insufficient.

This node should remain deterministic because it is not discovering meaning.
It checks that AI-produced structured fields cover the contract.

It must not infer missing user intent from raw text. If the AI artifacts do not
contain the required information, the result is `needs_clarification`.

Expected output:

```text
frontdesk/semantic_coverage.json
```

### Node 3: SolutionArchitect

Purpose:

- act as a mature product architect and technical planner;
- turn the confirmed need into a bounded solution plan;
- produce non-goals, tradeoffs, risks, verification strategy, profile
  recommendations, and implementation boundaries;
- remain product-aware only through injected metadata and structured FrontDesk
  artifacts.

Visible refs:

```text
frontdesk/core_need_brief.json
frontdesk/semantic_lock.json
frontdesk/mission_brief.json
frontdesk/semantic_coverage.json
frontdesk/profile_catalog_snapshot.json
frontdesk/product_inquiry_profile.json   # optional, data only
```

Expected outputs:

```text
frontdesk/solution_plan.json
frontdesk/solution_plan.md
frontdesk/plan_risk_register.json
frontdesk/profile_recommendations.json
frontdesk/mission_plan.json
```

Quality obligations:

- design the solution that would actually solve the underlying pain, not only
  mirror the user's surface words;
- keep the first implementation bounded;
- surface risks and verification requirements early;
- recommend only known profiles from the registry snapshot;
- leave product compilation to Product Integration.

Deterministic validation:

- schemas validate;
- selected profile refs exist in the registry snapshot;
- risk register uses structured refs;
- plan does not grant runtime permissions;
- plan does not claim ProductGate approval;
- no raw conversation or provider payload appears in runtime-facing fields.

### Node 4: IntentBundleAuthor

Purpose:

- consume the ProductInquiryProfile and AI-authored FrontDesk artifacts;
- resolve product inquiry slots through reasoning over structured
  AI-authored artifacts. The node may read admitted conversation refs as
  authoring context, but product slot `source_refs` for compile must cite
  structured AI-authored artifacts or explicitly admitted sanitized refs;
- produce explicit slot values, missing slot explanations, product hypotheses,
  risk flags, and compiler notes;
- write an intent-bundle candidate that deterministic code can validate and
  canonicalize.

This node is the key Phase 23 addition. The current service can assemble an
intent bundle from defaults and missing slots, but it must not fill product
slots by Python inference. Product slots require PiWorker-authored reasoning.

Visible refs:

```text
frontdesk/product_inquiry_profile.json
frontdesk/core_need_brief.json
frontdesk/semantic_lock.json
frontdesk/mission_brief.json
frontdesk/semantic_coverage.json
frontdesk/solution_plan.json
frontdesk/mission_plan.json
frontdesk/source_admission_report.json
frontdesk/sanitized_sources.json
```

Expected candidate output:

```text
frontdesk/intent_bundle_candidate.json
```

Canonical output after deterministic validation:

```text
frontdesk/intent_bundle.json
```

Candidate requirements:

- include `profile_hash` matching the active ProductInquiryProfile;
- include one slot candidate for each profile slot;
- mark each slot as `confirmed`, `inferred`, `assumed`, `missing`,
  `rejected`, or `not_applicable`;
- cite `source_refs` for resolved values unless the value is an explicit
  profile default. Runtime-facing slot refs must cite structured AI-authored
  artifacts or sanitized admitted source refs, not raw conversation refs;
- include clarification questions for missing blocking slots;
- include product hypotheses as hypotheses, not product contracts;
- include risk flags with rationale and refs;
- avoid any product-specific compilation result.

Deterministic finalization:

- validate candidate schema;
- validate profile id and hash;
- validate slot ids are known in the profile;
- validate enum choices and ref-like values;
- validate candidate `source_refs`, slot refs, hypothesis refs, risk refs, and
  Product Integration inputs against
  `ProductInquiryProfile.source_policy.allowed_source_refs` and
  `excluded_source_refs`;
- recompute missing blocking slots from candidate statuses and profile
  readiness rules;
- set readiness to `needs_clarification` or `ready_for_product_compile`;
- write the canonical `frontdesk/intent_bundle.json`;
- fail closed on any mismatch.

### Node 5: MissionIR Mapper

Purpose:

- support PiWorker-authored generic fallback MissionIR drafting when no Product
  Integration is active;
- remain optional for product-aware flows;
- never compile SkillFoundry or any other product-specific MissionIR in
  FrontDesk core.

For SkillFoundry and future product integrations, the final MissionIR mapping
belongs to `ProductIntegration.compile_intent()`.

Generic fallback must fail closed when an active product context, product slot
state, or product hypothesis indicates a product-domain compile is required.
It must not become a silent escape hatch merely because the caller forgot to
load a Product Integration.

## PiWorker Execution Contract

`FrontDeskPiNodeRunner` should become the only way service code invokes
FrontDesk AI authoring.

Required upgrades:

1. Add explicit support for `intent_bundle_author`.
2. Add a node-spec artifact for each run, for example:

   ```text
   frontdesk/pi_nodes/<session>/<node>/node_spec.json
   ```

   This artifact should contain the role, rules, visible refs, expected
   outputs, schema pointers, and output checklist. The `WorkUnitContract`
   should point PiWorker at that node spec through `visible_refs`.

3. Add content-bound execution-record checks:

   ```text
   frontdesk/pi_nodes/<session>/<node>/execution.json
   ```

   The service should treat a FrontDesk artifact as AI-authored only when
   `require_ai_authored(ref, node_name, session_id)` verifies all of the
   following:

   - execution record exists and validates;
   - node name and session id match exactly;
   - produced ref is listed in the execution record;
   - current artifact bytes hash to the recorded output `sha256`;
   - the execution record is bound to the current `WorkUnitContract` or
     `node_spec` hash;
   - visible input refs used by the node are bound by hash or explicit
     freshness policy;
   - the active ProductInquiryProfile hash matches for intent-bundle
     authoring;
   - the worker result status is acceptable for the node output mode.

   A ref-only execution record is not enough. Post-run edits, stale artifacts,
   copied fixtures, or deterministic writes to an expected ref must fail
   closed.

4. Keep `WorkerAdapter` as the harness protocol, but configure only a
   PiWorker-compatible adapter in product use. A production adapter is
   PiWorker-compatible only when it is constructed through the MissionForge
   PiWorker factory or exposes an explicit `adapter_family="piworker"` marker
   validated by FrontDesk configuration. Do not introduce `OpenAIWorker`,
   `AnthropicWorker`, or other provider-specific workers under FrontDesk.
   Scripted adapters are allowed only in tests and must still emit the same
   content-bound execution records.

5. Make worker configuration explicit:

   ```text
   FrontDesk(..., worker=piworker_adapter)
   missionforge frontdesk grill --worker piworker
   missionforge frontdesk plan --worker piworker
   missionforge frontdesk intent --worker piworker
   ```

   Exact CLI flags can evolve, but silent fallback is forbidden.

6. Worker results must remain refs-only. Metrics can be emitted later through
   the Phase 12 metric ledger, but routing decisions must not depend on
   adapter-private metrics.

## Service API Shape

Recommended programmatic shape:

```python
frontdesk = FrontDesk(workspace=workspace, registry=registry, worker=piworker)

session = frontdesk.start(user_text, session_id="sf-dogfood")
frontdesk.scout(session.session_ref)
frontdesk.grill(session.session_ref)

while frontdesk.inspect(session.session_ref).next_action == "answer_question":
    frontdesk.answer(session.session_ref, user_answer)
    frontdesk.grill(session.session_ref)

frontdesk.cover_semantics(session.session_ref)
frontdesk.plan_solution(session.session_ref)
frontdesk.build_intent_bundle(
    session.session_ref,
    product_context=skillfoundry.inquiry_profile(),
)
frontdesk.compile_product(
    session.session_ref,
    SkillFoundryFrontDeskIntegration(bundle_id="example"),
)
```

The same high-level shape should be available from CLI commands, but the
initial implementation may keep the dogfood harness programmatic until the
node contracts stabilize.

## State Transitions

Phase 23 should preserve and tighten the current state model:

```text
new
  -> eliciting
  -> needs_clarification
  -> eliciting
  -> draft_ready
  -> approval_required
  -> approved
  -> frozen
  -> handed_off
```

Recommended authoring transitions:

| Operation | Success State | Failure State | Next Action |
| --- | --- | --- | --- |
| `start` | `eliciting` | n/a | `scout` |
| `scout` | `eliciting` | `failed_closed` | `grill` |
| `grill` with question | `needs_clarification` | `failed_closed` | `answer_question` |
| `grill` with core need | `eliciting` | `failed_closed` | `cover_semantics` |
| `cover_semantics` passed | `eliciting` | n/a | `plan_solution` |
| `cover_semantics` blocked | `needs_clarification` | n/a | `answer_question` |
| `plan_solution` | `draft_ready` or `approval_required` | `failed_closed` | `build_intent_bundle` |
| `build_intent_bundle` ready | existing state | `failed_closed` | `compile_product` |
| `build_intent_bundle` missing slots | `needs_clarification` | `failed_closed` | `answer_question` |
| `compile_product` compiled | existing state | `failed_closed` | product handoff |
| `compile_product` needs clarification | `needs_clarification` | n/a | `answer_question` |

No state transition should imply mission execution or product readiness.

## Product Inquiry Profile Boundary

FrontDesk should let a product profile steer the questions without letting the
profile become executable authority.

Allowed uses:

- show product identity to PiWorker as authoring context;
- ask product-specific slot questions;
- require certain slots before product compile;
- expose risks and acceptance prerequisites early;
- compile with a Product Integration explicitly supplied by the caller, CLI, or
  product-specific entrypoint after the intent bundle is ready.

Forbidden uses:

- runtime permission grants;
- verifier closure;
- product readiness approval;
- core imports of product packages;
- hard-coded slot interpretation in `src/missionforge/frontdesk`;
- using activation terms as deterministic product detection in core.

For product selection, a caller may explicitly pass a Product Integration or
ProductInquiryProfile. Automatic product routing can be added later, but it
must be implemented as an AI-authored product hypothesis plus deterministic
validation and explicit integration loading. Core must not auto-import or
choose products by activation terms.

## Raw Conversation And Source Policy

FrontDesk AI nodes need access to the user's words to ask intelligent
questions. That does not make raw conversation task truth.

The boundary is:

```text
conversation/content refs:
  authoring provenance only

semantic_lock/core_need/mission_brief/solution_plan/intent_bundle:
  structured authoring truth after validation

MissionIR/frozen contract/runtime:
  no raw conversation dependency
```

Implementation rules:

- raw or redacted conversation may be stored under `frontdesk/` for
  provenance;
- AI nodes may read conversation refs when their node contract allows it;
- explicit user clarification artifacts must be either typed slot answers
  captured through a declared slot-id/value API or PiWorker-authored
  interpretation artifacts. They must not mean Python parsing free-form
  `answer()` text;
- product integrations should consume `FrontDeskIntentBundle` and structured
  refs, not `frontdesk/conversation.jsonl`;
- source policy should exclude conversation refs from product compiler
  runtime-facing truth by default;
- validators should reject forbidden fields such as `raw_prompt`,
  `transcript`, `provider_payload`, `api_key`, `credential`, and `secret`.

## Implementation Slices

### Phase 23.1: Node Execution Provenance

Goal:

- make service entrypoints distinguish AI-authored artifacts from arbitrary
  files on disk.

Work:

- extend `FRONTDESK_NODE_NAMES` with `intent_bundle_author`;
- add node-spec refs and execution-record refs to state constants;
- write node spec before each PiWorker run;
- record output content hashes, node spec hash, work-unit hash, visible input
  hashes, active profile hash, session id, and node name in the execution
  record;
- require execution records for artifacts consumed by `grill`,
  `plan_solution`, `map_mission`, and `build_intent_bundle`;
- add helper:

  ```python
  FrontDeskWorkspace.require_ai_authored(ref, node_name, session_id)
  ```

  or an equivalent service-level validator that checks the current artifact
  bytes against the recorded output hash and rejects stale input/profile
  bindings.
- revalidate or invalidate existing `frontdesk/intent_bundle.json` before
  reuse by checking candidate execution record, session id, profile hash,
  bundle hash, and current input hashes.

Tests:

- artifact exists but no execution record -> fail closed;
- execution record exists but does not list artifact -> fail closed;
- execution record lists output outside allowed scope -> fail closed;
- execution record exists but artifact bytes changed -> fail closed;
- execution record exists for the same ref but wrong node or session -> fail
  closed;
- execution record exists but current ProductInquiryProfile hash changed ->
  fail closed;
- execution record exists but visible input artifact changed after the run ->
  fail closed unless the node declares an explicit freshness policy;
- scripted PiWorker output with matching record -> accepted.

### Phase 23.2: NeedGriller PiWorker Path

Goal:

- make `FrontDesk.grill()` execute the NeedGriller PiWorker node when a worker
  is explicitly configured.

Work:

- inject `WorkerAdapter | None` into `FrontDesk`;
- preserve current fail-closed behavior when no worker exists;
- run `FrontDeskPiNodeRunner.run_node(node_name="need_griller", ...)` with an
  output mode that distinguishes question-only turns from completion turns;
- load and validate NeedGriller outputs into `NeedGrillResult`;
- set `next_action` based on whether the node produced a question or complete
  core-need artifacts;
- avoid any Python fallback that tries to infer the question.

Tests:

- no worker -> current fail-closed error;
- scripted worker writes valid question-only report -> `needs_clarification`;
- scripted worker writes valid core need -> `cover_semantics`;
- question-only output is accepted without completion artifacts, but downstream
  authoring remains blocked until completion artifacts exist and pass
  provenance checks;
- invalid schema -> fail closed;
- raw field leakage -> fail closed.

### Phase 23.3: Clarification Loop And Semantic Coverage

Goal:

- support controlled multi-turn need grilling without turning FrontDesk into
  an endless chatbot.

Work:

- keep `answer()` as a pure conversation append;
- re-run NeedGriller after each answer when the previous report asked a
  question;
- enforce `max_questions` or policy budget at orchestration level;
- run `SemanticCoverageChecker` only over AI-authored structured artifacts;
- route uncovered semantic gaps back to NeedGriller as visible refs.

Tests:

- one question then answer then passed coverage;
- repeated missing coverage stops with bounded clarification state;
- coverage checker does not read raw conversation to fill missing fields.

### Phase 23.4: SolutionArchitect PiWorker Path

Goal:

- make `FrontDesk.plan_solution()` execute the SolutionArchitect node.

Work:

- run PiWorker with core need, semantic lock, mission brief, semantic coverage,
  registry snapshot, and optional product profile;
- validate `solution_plan`, `solution_plan.md`, `plan_risk_register`,
  `profile_recommendations`, and `mission_plan`;
- ensure selected profiles exist in the registry snapshot;
- set state to `draft_ready` or `approval_required` according to existing plan
  review policy.

Tests:

- valid scripted worker plan -> accepted;
- unknown profile -> fail closed;
- plan claims product approval -> fail closed;
- missing expected artifact -> fail closed.

### Phase 23.5: IntentBundleAuthor PiWorker Path

Goal:

- replace default/missing-only product slot assembly with explicit AI-authored
  slot reasoning, while keeping canonical bundle finalization deterministic.

Work:

- add `frontdesk/intent_bundle_candidate.json`;
- add an `IntentBundleCandidate` schema if the canonical
  `FrontDeskIntentBundle` is too strict for pre-finalization output;
- run PiWorker with `ProductInquiryProfile` and structured FrontDesk artifacts;
- validate the candidate against profile slots, profile hash, source policy,
  enum choices, ref-like values, and forbidden raw fields;
- validate that existing canonical bundles are not reused after profile,
  candidate, core need, semantic lock, solution plan, or mission plan inputs
  change;
- canonicalize into `frontdesk/intent_bundle.json`;
- keep profile defaults allowed only when the candidate explicitly marks the
  slot as default-backed or the deterministic finalizer applies a declared
  profile default without semantic inference;
- route missing blocking slots to clarification.

Tests:

- no worker/candidate -> fail closed;
- candidate fills SkillFoundry slots from cited AI artifacts -> ready for
  product compile;
- candidate missing blocking slots -> clarification questions;
- candidate uses unknown slot id -> fail closed;
- candidate invents enum value -> fail closed;
- candidate cites raw conversation as product-compile or runtime-facing source
  -> fail closed;
- core need, filenames, artifact refs, or conversation text mention
  SkillFoundry slot content, but the candidate does not: Python must not fill
  the slot;
- current bundle exists but its candidate execution record is stale -> fail
  closed.

### Phase 23.6: Product Compile And SkillFoundry Dogfood Harness

Goal:

- prove the product-aware path works end to end for SkillFoundry without
  putting SkillFoundry logic into FrontDesk core.

Work:

- keep `SkillFoundryInquiryProfile` in the integration package;
- keep `SkillFoundryFrontDeskIntegration.compile_intent()` as the product
  compiler;
- filter Product Integration source refs through the active product
  `SourcePolicy` instead of bulk-forwarding every generic FrontDesk ref;
- add a dogfood harness that feeds a source-free, colloquial user transcript
  into FrontDesk, uses scripted PiWorker outputs for deterministic tests, and
  verifies the resulting SkillFoundry MissionIR/product artifacts;
- do not expose Codexarium source paths, code, or private project details in
  fixtures.

Tests:

- source-free colloquial transcript produces a good `CoreNeedBrief`;
- SkillFoundry slot values are authored by the scripted PiWorker fixture, not
  inferred by Python;
- product compiler emits SkillFoundry request, product contract, MissionIR,
  frozen contract, and product gate spec;
- product compile asks clarification when a blocking slot remains missing;
- SkillFoundry bridge excludes refs forbidden by its `SourcePolicy`, including
  raw conversation refs;
- activation terms in the product profile are never consumed by core product
  routing.

### Phase 23.7: CLI And Operator Experience

Goal:

- make the AI path usable from CLI without hiding the worker requirement.

Work:

- add explicit worker-required CLI paths for:

  ```text
  missionforge frontdesk grill
  missionforge frontdesk plan
  missionforge frontdesk intent
  missionforge frontdesk compile-product
  ```

- ensure CLI prints `configure_frontdesk_llm` or equivalent when no PiWorker is
  configured;
- expose `inspect` fields for AI execution refs, latest question, missing
  product slots, product context, and next action;
- keep product integration loading explicit.

Tests:

- CLI no-worker fail-closed;
- CLI scripted worker success;
- CLI compile-product SkillFoundry clarification;
- CLI inspect shows no raw conversation content.

### Phase 23.8: Metrics And Diagnostics

Goal:

- record useful operator evidence without coupling runtime routing to
  adapter-private metrics.

Work:

- emit metric events through the Phase 12 metric ledger once available;
- record node execution duration, output refs, validation failures, and
  clarification counts;
- avoid routing based on private PiWorker scores;
- keep diagnostics refs-only.

Tests:

- metrics contain refs and node names but no raw prompt/transcript/secret;
- invalid node output records a fail-closed diagnostic.

## Expected File Changes

Likely core files:

```text
src/missionforge/frontdesk/pi_node_runner.py
src/missionforge/frontdesk/service.py
src/missionforge/frontdesk/need_griller.py
src/missionforge/frontdesk/solution_architect.py
src/missionforge/frontdesk/spec_grill.py
src/missionforge/frontdesk/state.py
src/missionforge/frontdesk/intent_bundle.py
src/missionforge/frontdesk/cli.py
src/missionforge/workers.py                     # only if protocol metadata is needed
```

Possible new core files:

```text
src/missionforge/frontdesk/ai_orchestrator.py
src/missionforge/frontdesk/ai_artifacts.py
src/missionforge/frontdesk/intent_bundle_author.py
```

Likely SkillFoundry files:

```text
integrations/skillfoundry/src/missionforge_skillfoundry/frontdesk_context.py
integrations/skillfoundry/src/missionforge_skillfoundry/frontdesk_bridge.py
integrations/skillfoundry/tests/test_skillfoundry_frontdesk_flow.py
```

Likely tests:

```text
tests/test_frontdesk_pi_node_runner.py
tests/test_frontdesk_ai_artifact_provenance.py
tests/test_frontdesk_ai_artifact_staleness.py
tests/test_frontdesk_need_griller.py
tests/test_frontdesk_solution_architect.py
tests/test_frontdesk_intent_bundle_author.py
tests/test_frontdesk_product_context_service.py
tests/test_frontdesk_spec_grill_boundaries.py
integrations/skillfoundry/tests/test_skillfoundry_product_context_flow.py
```

## Regression Tests That Must Stay In Place

These tests guard the architectural boundary:

- no worker means fail closed;
- no AI-authored artifacts means fail closed;
- AI-authored artifact acceptance checks current content hashes, input hashes,
  node spec hash, node/session identity, and product profile hash when
  applicable;
- stale execution records, stale input artifacts, changed profile hashes, and
  post-run artifact edits fail closed;
- deterministic code cannot fill product slots from raw conversation;
- deterministic code cannot infer Rust/privacy/performance/customer-specific
  requirements from keywords;
- FrontDesk core does not import product integrations;
- runtime does not import product integrations;
- adapters do not contain concrete task logic;
- Product Integration may import MissionForge, but MissionForge must not
  import the product package;
- SkillFoundry product compile uses `FrontDeskIntentBundle`, not raw
  conversation;
- Product Integration source refs are filtered through product source policy;
- activation terms are profile data for AI inquiry, not deterministic core
  routing rules;
- raw prompt/transcript/provider/secret keys are rejected recursively;
- output refs cannot escape allowed scopes.

## Acceptance Criteria

Phase 23 is complete when all of the following are true:

1. A FrontDesk session with no configured PiWorker still fails closed before
   need grilling, solution planning, mission mapping, or intent-bundle
   authoring.
2. A FrontDesk session with a scripted PiWorker adapter can:
   - ask a useful clarification question;
   - accept a user answer;
   - produce `core_need_brief`, `semantic_lock`, and `mission_brief`;
   - pass semantic coverage;
   - produce a solution plan and risk register;
   - produce an AI-authored intent-bundle candidate;
   - finalize `frontdesk/intent_bundle.json`.
3. The same scripted path can compile through
   `SkillFoundryFrontDeskIntegration` into SkillFoundry product artifacts.
4. The SkillFoundry dogfood fixture uses colloquial, source-free user language
   and does not leak Codexarium source code, paths, or private internals.
5. No FrontDesk core test depends on hard-coded SkillFoundry slot semantics
   outside the ProductInquiryProfile data contract.
6. No product-specific branch is added to `src/missionforge/frontdesk`,
   `src/missionforge/runtime`, or `src/missionforge/adapters`.
7. Invalid, missing, out-of-scope, or non-schema PiWorker outputs fail closed.
8. Post-run edits, stale execution records, stale input refs, wrong
   node/session records, and changed product profile hashes fail closed.
9. Product Integration receives a validated `FrontDeskIntentBundle`, not raw
   conversation.
10. MissionForge Runtime receives only MissionIR/frozen contract state.
11. The full validation suite passes:

    ```bash
    PYTHONPATH=src python3 -m unittest discover -s tests
    ./scripts/validate_integrations.sh skillfoundry
    MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
    git diff --check
    ```

## Dogfood Scenario

The dogfood scenario should intentionally sound like a real user:

```text
I keep trying to turn messy project instincts into reusable Codex skills, but
the current process depends too much on me knowing how to describe the skill.
I want something that can grill me a bit, figure out the real capability, and
then produce a clean package. I care a lot about not leaking my private project
context, and I want the reusable core to stay separate from the specific thing
I am building.
```

This transcript is only an example of tone. It should not contain private
source, internal repository paths, or exact Codexarium implementation details.

Expected AI-authored interpretation:

- the user wants a reusable skill/capability package;
- the user does not want to hand-author all requirements;
- the system must actively elicit hidden constraints;
- privacy and source-boundary control are first-class;
- product-specific compilation belongs to SkillFoundry integration;
- the generic FrontDesk must remain reusable for future products.

The expected output is not a generic MissionIR directly from FrontDesk. It is:

```text
FrontDeskIntentBundle
  -> SkillFoundryFrontDeskIntegration
  -> SkillFoundry product request/contract/MissionIR/gate spec
```

## What Must Not Be Built

Do not build:

- a Python intent classifier for this transcript;
- keyword rules for Rust, privacy, performance, SkillFoundry, or any product
  slot;
- a product auto-router based on activation terms;
- a second LLM provider abstraction;
- product-specific code in MissionForge adapters;
- runtime behavior that reads FrontDesk raw conversation;
- a generic fallback that silently claims product readiness;
- tests that pass because Python knows the dogfood answer in advance.
- test fixtures that write final FrontDesk artifacts without scripted
  PiWorker-style execution records and content hashes.

## Open Decisions

These should be settled during implementation, but they do not change the
architecture:

1. Whether `FrontDesk` receives `worker` at construction time, per method call,
   or both.
2. Whether canonical intent-bundle finalization reuses
   `FrontDeskIntentBundle` directly or introduces an explicit
   `IntentBundleCandidate`.
3. Whether `plan_solution()` should require a manual `review_plan()` before
   intent-bundle authoring in the first AI-enabled slice.
4. How much of `frontdesk/conversation.jsonl` should be raw versus redacted by
   default.
5. Whether the first CLI product integration loading path is static
   SkillFoundry registration or an explicit import string.

The answer to each decision should preserve the same rule: PiWorker owns
meaning; Python owns contracts.

## Review Checklist

Use this checklist for implementation reviews:

- Does this change add any semantic inference in Python?
- Does this change add product-specific code to MissionForge core?
- Does every AI-authored artifact have a content-hash-bound execution record
  tied to the current node spec, session, inputs, and product profile?
- Does every product slot value come from an AI-authored candidate, profile
  default, typed slot answer, or PiWorker-authored interpretation of a user
  clarification?
- Does the product integration compile from an intent bundle rather than raw
  conversation?
- Does runtime remain unaware of product integration internals?
- Does invalid worker output fail closed?
- Are tests proving the boundary rather than replaying hidden heuristics?
- Is the dogfood scenario source-free and privacy-safe?
- Are docs and CLI messages honest that the live AI path requires PiWorker?
