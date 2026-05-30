# Phase 22: FrontDesk Product Context And Intent Bundle Plan

Last updated: 2026-05-30

Status: `implemented`

Implementation note:

Phase 22 is implemented in the current codebase. The core contracts live in
`src/missionforge/frontdesk/inquiry_profile.py`,
`src/missionforge/frontdesk/intent_bundle.py`,
`src/missionforge/product_integration.py`, and
`src/missionforge/product_gate.py`. FrontDesk now writes
`frontdesk/intent_bundle.json`, keeps `draft()` compatibility through
`GenericProductIntegration`, exposes `build_intent_bundle()` and
`compile_product()`, and adds CLI `intent` / `compile-product` commands. The
SkillFoundry reference bridge lives under
`integrations/skillfoundry/src/missionforge_skillfoundry/` and compiles
FrontDesk intent bundles into SkillFoundry requests, product contracts,
MissionIR, frozen contracts, and product gate spec refs without core imports.

## Purpose

This phase implements the architecture in
`docs/FRONTDESK_PRODUCT_CONTEXT_AND_INTENT_BUNDLE.md`.

The goal is to make FrontDesk product-aware without making MissionForge core
product-specific.

After this phase, a product integration such as SkillFoundry should be able to:

1. provide a `ProductInquiryProfile`;
2. let the generic FrontDesk engine ask product-scoped questions;
3. receive a `FrontDeskIntentBundle`;
4. compile that bundle into a product request, product contract, MissionIR, and
   product gate spec;
5. request further clarification when blocking product slots are missing;
6. run through normal MissionForge runtime and verifier;
7. evaluate product readiness through a product-specific gate under a generic
   ProductGate result protocol.

## Non-Negotiable Constraints

1. No product branches in `src/missionforge/frontdesk`.
2. No product branches in `src/missionforge/runtime`.
3. No product-specific adapters under `src/missionforge/adapters`.
4. MissionForge core must not import `missionforge_skillfoundry` or any future
   product integration.
5. Product integrations may import MissionForge.
6. ProductInquiryProfile affects questioning only; it does not grant runtime
   authority.
7. FrontDesk outputs refs-first authoring artifacts and intent bundles, not raw
   prompt or transcript truth.
8. Product Integration owns final product-domain MissionIR compilation.
9. Verifier owns MissionIR closure.
10. ProductGate owns product readiness, not generic verifier completion.
11. PiWorker remains the only LLM worker direction.
12. Default tests stay deterministic and offline by using scripted clients or
    prewritten LLM artifact fixtures, not deterministic authoring fallback.
13. No LLM means no authoring: FrontDesk must fail closed before need
    grilling, solution architecture, MissionIR mapping, or intent bundle
    authoring if the LLM/PiWorker-authored artifacts are absent.

## Target End State

```text
ProductIntegration.inquiry_profile()
  -> FrontDesk(product_context=profile)
  -> frontdesk/intent_bundle.json
  -> ProductIntegration.compile_intent(bundle)
  -> product request / product contract / MissionIR / product gate spec
  -> freeze_mission
  -> MissionRuntime
  -> Verifier
  -> ProductIntegration.product_gate()
```

The current FrontDesk `draft()` path remains compatible only after LLM-authored
FrontDesk artifacts exist. It must not fabricate those artifacts through
deterministic fallback.

## New Public Concepts

### ProductInquiryProfile

Authoring-time product identity and question plan.

### InquirySlot

One product-specific information slot FrontDesk should fill or explicitly mark
missing.

### FrontDeskIntentBundle

Formal FrontDesk output consumed by product integrations.

### ProductIntegration

Protocol implemented by product packages.

### ProductCompileResult

Compiled product artifacts or a clarification request.

### ProductGateResult

Generic result envelope for product-specific gates.

## Files To Add

Core:

```text
src/missionforge/frontdesk/inquiry_profile.py
src/missionforge/frontdesk/intent_bundle.py
src/missionforge/product_integration.py
src/missionforge/product_gate.py
```

SkillFoundry reference integration:

```text
integrations/skillfoundry/src/missionforge_skillfoundry/frontdesk_context.py
integrations/skillfoundry/src/missionforge_skillfoundry/frontdesk_bridge.py
```

Tests:

```text
tests/test_frontdesk_inquiry_profile.py
tests/test_frontdesk_intent_bundle.py
tests/test_product_integration_contracts.py
tests/test_product_gate_contracts.py
tests/test_frontdesk_product_context_service.py
tests/test_frontdesk_product_boundary.py
integrations/skillfoundry/tests/test_frontdesk_context.py
integrations/skillfoundry/tests/test_frontdesk_bridge.py
integrations/skillfoundry/tests/test_skillfoundry_product_context_flow.py
```

Docs:

```text
docs/FRONTDESK_PRODUCT_CONTEXT_AND_INTENT_BUNDLE.md
docs/PHASE22_FRONTDESK_PRODUCT_CONTEXT_PLAN.md
docs/modules/frontdesk.md
docs/PRODUCT_INTEGRATION_BOUNDARY.md
docs/ARCHITECTURE.md
```

## Files To Update

```text
src/missionforge/frontdesk/service.py
src/missionforge/frontdesk/state.py
src/missionforge/frontdesk/spec_grill.py
src/missionforge/frontdesk/__init__.py
src/missionforge/frontdesk/cli.py
src/missionforge/__init__.py
integrations/skillfoundry/src/missionforge_skillfoundry/__init__.py
integrations/skillfoundry/src/missionforge_skillfoundry/compiler.py
```

Keep package-root exports conservative. Only export product-context contracts
that are intended as stable extension APIs.

## Phase 22.1: ProductInquiryProfile Contracts

### Goal

Add typed, refs-safe schema objects for product inquiry metadata.

### Implementation

Add `src/missionforge/frontdesk/inquiry_profile.py`.

Define:

```text
ProductInquiryProfile
ProductActivation
InquirySlot
SlotRequirement
SlotValueType
SlotTargetMapping
RiskDimension
ArtifactArchetype
AcceptancePrerequisite
CompilerReadiness
SourcePolicy
```

Recommended enums:

```text
SlotRequirement:
  blocking | recommended | optional | conditional

SlotValueType:
  free_text | enum | boolean | number | ref | ref_list |
  string_list | artifact_path | artifact_path_list

InquiryConfidence:
  observed | inferred | assumed

AuthorityRequirement:
  harness | reviewer | human
```

Validation rules:

- `product_id`, `version`, and `display_name` are non-empty strings.
- `slot_id` values are unique.
- blocking readiness slot ids exist in `slots`.
- `choices` are required for `enum` slots.
- ref-like defaults or choices validate as workspace refs only when the slot
  type is ref-like.
- `maps_to[].target` is a non-empty dotted path string; do not interpret it in
  core.
- raw fields such as `raw_prompt`, `transcript`, `api_key`, `secret`, and
  provider payload keys are rejected recursively.
- no product-specific code branch is allowed in core tests.

### Tests

```bash
PYTHONPATH=src python3 -m unittest tests/test_frontdesk_inquiry_profile.py
```

Test cases:

- round-trip full profile;
- rejects duplicate slot ids;
- rejects enum slots without choices;
- rejects unknown blocking readiness slot ids;
- rejects raw prompt/transcript/secret fields;
- allows product-specific ids as data, not imports.

## Phase 22.2: FrontDeskIntentBundle Contracts

### Goal

Make FrontDesk's formal output an intent bundle that product integrations can
consume.

### Implementation

Add `src/missionforge/frontdesk/intent_bundle.py`.

Define:

```text
FrontDeskIntentBundle
ProductContextSnapshot
IntentGenericRefs
SlotValue
SlotValueStatus
ProductHypothesis
RiskFlag
IntentBundleReadiness
```

Recommended readiness values:

```text
needs_clarification
ready_for_product_compile
generic_compile_only
unsupported_product
human_review_required
failed_closed
```

Recommended slot status values:

```text
confirmed | inferred | assumed | missing | rejected | not_applicable
```

Validation rules:

- `generic_refs` must point to existing FrontDesk artifact refs when checked by
  service-level code.
- `slot_values[].slot_id` are unique.
- `missing_blocking_slots` must not contain a slot that has a confirmed value.
- `ready_for_product_compile` requires no missing blocking slots.
- `profile_hash` must be `sha256:*` when present.
- all refs are workspace-relative.
- raw prompt/transcript/provider/secret fields are rejected recursively.

### Service Integration

Add a method:

```python
FrontDesk.build_intent_bundle(session_ref, *, product_context=None)
```

It should:

- load existing spec-grill artifacts;
- include generic refs;
- include product context id/profile ref/hash when present;
- fill slot values from LLM-authored FrontDesk artifacts and explicit
  product-context defaults;
- mark unknown blocking slots as missing;
- write `frontdesk/intent_bundle.json`.

Deterministic code may preserve explicit refs and validate shape, but it must
not perform product meaning extraction from raw conversation, artifact names, or
generic FrontDesk summaries. If LLM/PiWorker-authored slot values or explicit
profile defaults are absent, blocking product slots remain missing.

### Tests

```bash
PYTHONPATH=src python3 -m unittest tests/test_frontdesk_intent_bundle.py tests/test_frontdesk_product_context_service.py
```

Test cases:

- generic session produces an intent bundle;
- product context populates context snapshot;
- missing blocking slots route to `needs_clarification`;
- ready bundle requires no blocking missing slots;
- raw text is provenance only and not embedded as runtime truth.

## Phase 22.3: ProductIntegration Protocol

### Goal

Define how product packages plug into FrontDesk without core imports.

### Implementation

Add `src/missionforge/product_integration.py`.

Define:

```text
ProductIntegration
ProductCompileStatus
ProductCompileResult
ProductClarificationRequest
ProductClarificationQuestion
ProductArtifactRefs
```

Recommended compile statuses:

```text
compiled
needs_clarification
unsupported
human_review_required
failed_closed
```

`ProductCompileResult` should include:

```text
product_id
status
intent_bundle_ref
product_request_ref
product_contract_ref
mission_ir_ref
frozen_contract_ref
product_gate_spec_ref
missing_slot_ids
clarification_questions
evidence_refs
reason
```

Validation rules:

- compiled result requires `mission_ir_ref`;
- clarification result requires at least one missing slot or question;
- all refs validate;
- raw payload fields are rejected;
- product id is data only.

### Tests

```bash
PYTHONPATH=src python3 -m unittest tests/test_product_integration_contracts.py
```

Test cases:

- compile result round trip;
- compiled status requires mission ref;
- clarification status requires missing slots/questions;
- rejects unsafe refs and raw fields.

## Phase 22.4: ProductGate Protocol

### Goal

Create a generic gate result envelope while keeping product criteria outside
core.

### Implementation

Add `src/missionforge/product_gate.py`.

Define:

```text
ProductGateStatus
ProductGateSeverity
ProductGateSpec
ProductGateCheck
ProductGateFinding
ProductGateResult
```

Recommended statuses:

```text
passed
failed
needs_review
unsupported
candidate
product_grade
quarantined
```

Validation rules:

- product check ids are opaque strings;
- core does not interpret product check ids;
- blocking findings prevent `passed` and `product_grade`;
- evidence refs validate;
- raw fields are rejected recursively.

### Tests

```bash
PYTHONPATH=src python3 -m unittest tests/test_product_gate_contracts.py
```

Test cases:

- round trip spec/result/finding;
- blocking finding prevents pass;
- rejects raw provider payload fields;
- product-specific check ids remain opaque.

## Phase 22.5: FrontDesk Service And CLI

### Goal

Expose product-context-aware FrontDesk while preserving product-neutral service
entrypoints. Generic usage must still respect the LLM authoring boundary.

### API

Add:

```python
FrontDesk.build_intent_bundle(session_ref, *, product_context=None)
FrontDesk.compile_product(session_ref, integration)
```

Compatibility:

```python
FrontDesk.draft(session_ref)
```

should continue to work only when the required LLM-authored FrontDesk artifacts
already exist:

```text
LLM-authored FrontDesk artifacts
  -> FrontDesk.draft()
  -> build_intent_bundle()
  -> GenericProductIntegration
  -> draft_mission.json
```

### CLI

Add commands:

```bash
missionforge frontdesk intent --session frontdesk/session.json
missionforge frontdesk compile-product --session frontdesk/session.json --integration-ref ...
```

Do not make core CLI import product packages by name. Product integrations may
provide their own CLI entrypoints, such as:

```bash
missionforge-skillfoundry frontdesk
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest tests/test_frontdesk_product_context_service.py tests/test_frontdesk_cli.py
```

Test cases:

- current `draft/audit/approve/freeze` remains compatible;
- `intent` writes `frontdesk/intent_bundle.json`;
- missing blocking product slots appear in `inspect`;
- core CLI does not import SkillFoundry integration.

## Phase 22.6: SkillFoundry Reference Bridge

### Goal

Turn the current SkillFoundry FrontDesk dogfood helper into a formal product
bridge.

### Implementation

Add:

```text
integrations/skillfoundry/src/missionforge_skillfoundry/frontdesk_context.py
integrations/skillfoundry/src/missionforge_skillfoundry/frontdesk_bridge.py
```

`frontdesk_context.py` should provide:

```text
SkillFoundryInquiryProfile
```

Required slots:

```text
capability_goal
target_user
trigger_scenarios
non_trigger_scenarios
bundle_profile
required_package_outputs
runtime_assets_required
data_assets_required
privacy_boundary
distribution_boundary
```

Risk dimensions:

```text
raw_context_leakage
self_grade_claim
runtime_execution
filesystem_write
external_document_ingestion
```

`frontdesk_bridge.py` should provide:

```python
build_skillfoundry_request(bundle, *, bundle_id, default_profile)
compile_frontdesk_intent(bundle, *, workspace, bundle_id)
```

It should:

- consume `FrontDeskIntentBundle`;
- produce `SkillFoundryRequest`;
- return `ProductClarificationRequest` when blocking slots are missing;
- call `SkillFoundryMissionCompiler` only after readiness checks pass;
- preserve refs to the FrontDesk intent bundle and source artifacts;
- never read raw conversation as product truth.

### Tests

```bash
PYTHONPATH=src python3 -m unittest \
  integrations/skillfoundry/tests/test_frontdesk_context.py \
  integrations/skillfoundry/tests/test_frontdesk_bridge.py \
  integrations/skillfoundry/tests/test_skillfoundry_product_context_flow.py
```

Test cases:

- SkillFoundry inquiry profile validates;
- prompt-only FrontDesk bundle compiles to `SkillFoundryRequest`;
- code-runtime slots compile to `BundleProfile.CODE_RUNTIME`;
- missing bundle profile or privacy boundary returns clarification;
- compiled SkillFoundry MissionIR contains `inputs.frontdesk_intent_bundle_ref`;
- product-specific logic remains outside `src/missionforge`.

## Phase 22.7: Generic Fallback Integration

### Goal

Keep simple generic tasks working without requiring a product package.

### Implementation

Add a small internal generic integration, either in FrontDesk or a core-neutral
module:

```text
src/missionforge/frontdesk/generic_integration.py
```

It should:

- consume a `FrontDeskIntentBundle`;
- use current `MissionIRMapper` behavior;
- compile simple file/document/artifact missions;
- fail closed when product-specific slots are present but no integration is
  selected;
- mark output as `generic_compile_only`.

Do not let generic fallback pretend to satisfy product-specific gates.

### Tests

```bash
PYTHONPATH=src python3 -m unittest tests/test_frontdesk_spec_grill_e2e.py tests/test_frontdesk_spec_grill_acceptance.py
```

Existing acceptance tests should still pass.

## Phase 22.8: Boundary And Import Tests

### Goal

Make the new extension model hard to accidentally violate.

### Tests

Add or update:

```text
tests/test_frontdesk_product_boundary.py
integrations/skillfoundry/tests/test_skillfoundry_import_boundaries.py
```

Assertions:

- `src/missionforge` does not import `missionforge_skillfoundry`;
- `src/missionforge/frontdesk` has no product-name behavior branches;
- `src/missionforge/adapters` has no product-specific adapter modules;
- ProductInquiryProfile data may contain `skillfoundry` as data only;
- product check ids are opaque to core.

## Phase 22.9: Documentation Updates

Update:

```text
docs/modules/frontdesk.md
docs/ARCHITECTURE.md
docs/PRODUCT_INTEGRATION_BOUNDARY.md
docs/IMPLEMENTATION_STATUS_AND_NEXT_PHASES.md
docs/FRONTDESK_SPEC_GRILL_DESIGN.md
docs/FRONTDESK_SPEC_GRILL_IMPLEMENTATION_PLAN.md
```

Required wording:

- FrontDesk's formal product-aware output is `FrontDeskIntentBundle`.
- Final product-domain MissionIR is compiled by Product Integration.
- Existing direct MissionIR mapping is generic fallback behavior.
- ProductGate is generic protocol plus product-specific criteria.
- ProductInquiryProfile is authoring-time metadata, not MissionIR and not a
  runtime authority grant.

## Acceptance Matrix

| Requirement | Evidence |
| --- | --- |
| Product inquiry metadata is typed and safe | `tests/test_frontdesk_inquiry_profile.py` |
| FrontDesk emits intent bundle | `tests/test_frontdesk_intent_bundle.py` |
| Product integration can compile or request clarification | `tests/test_product_integration_contracts.py` |
| Product gate protocol is generic | `tests/test_product_gate_contracts.py` |
| Generic FrontDesk fails closed without LLM artifacts | FrontDesk service/CLI tests |
| SkillFoundry bridge is formal | SkillFoundry frontdesk context/bridge tests |
| Core remains product-neutral | product boundary/import tests |
| Full project validates | `./scripts/validate.sh` and integration validation |

## Full Validation

```bash
PYTHONPATH=src python3 -m unittest discover -s tests

MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh

./scripts/validate_integrations.sh skillfoundry

git diff --check
```

## Migration Notes

Current behavior:

```text
FrontDesk.draft()
  -> fail closed unless LLM-authored FrontDesk artifacts already exist
```

Target behavior:

```text
LLM-authored FrontDesk artifacts
  -> FrontDesk.draft()
  -> build_intent_bundle()
  -> GenericProductIntegration
  -> draft_mission.json
```

Product-aware behavior:

```text
FrontDesk.build_intent_bundle(product_context=...)
  -> ProductIntegration.compile_intent()
  -> product MissionIR
```

Do not remove current CLI commands in this phase. Add product-context-aware
commands, but keep old commands behind the same LLM-authored artifact boundary
instead of deterministic authoring fallback.

## Done Definition

This phase is done when:

- `ProductInquiryProfile`, `FrontDeskIntentBundle`, `ProductIntegration`, and
  `ProductGate` contracts exist and are tested;
- FrontDesk can emit `frontdesk/intent_bundle.json`;
- generic `draft()` and CLI authoring fail closed without LLM-authored
  FrontDesk artifacts;
- SkillFoundry has a formal FrontDesk context and bridge outside core;
- missing product slots route to clarification rather than shallow MissionIR;
- product-gate criteria remain outside MissionForge core;
- full Python, Node, integration, and whitespace validation pass.
