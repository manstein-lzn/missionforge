# FrontDesk Product Context And Intent Bundle

Last updated: 2026-05-30

Status: `architecture reference`

## Purpose

This document refines the FrontDesk boundary after the spec-grill first slice.
The earlier design treated FrontDesk as MissionForge's formal MissionIR
authoring tool. That is still useful for generic fallback tasks, but it is not
the right final boundary for product-specific domains.

MissionIR is structurally generic, but its content is always domain-shaped.
A SkillFoundry mission, a finance research mission, and an operational task can
share the same MissionIR schema while requiring very different questions,
artifacts, risks, validators, and product gates.

Therefore:

```text
FrontDesk core should not own final product-domain MissionIR compilation.
FrontDesk core should own disciplined requirement discovery.
Product integrations should own domain contracts and final MissionIR
compilation.
```

## Core Thesis

FrontDesk should be a generic spec-grill engine driven by optional product
context metadata.

```text
FrontDesk Engine
  + ProductInquiryProfile
  -> FrontDeskIntentBundle

Product Integration
  + FrontDeskIntentBundle
  -> ProductContract
  -> MissionIR
  -> ProductGateSpec
```

The FrontDesk engine remains product-neutral. Product identity enters through
data or integration-provided contracts, not through product branches in
`src/missionforge/frontdesk`.

The engine is not allowed to replace LLM reasoning with deterministic
heuristics. Conversation recording, source admission, workspace scouting, and
schema validation may run offline. Need grilling, solution architecture,
product slot filling, and MissionIR/intent mapping require LLM-authored
FrontDesk artifacts. If those artifacts are absent, service entrypoints fail
closed instead of producing a low-confidence deterministic draft.

## Refined Architecture

```text
User expression
  -> FrontDesk Engine
  -> optional ProductInquiryProfile
  -> active grilling and semantic coverage
  -> FrontDeskIntentBundle
  -> ProductIntegration.compile_intent()
  -> ProductContract
  -> MissionIR
  -> freeze_mission
  -> MissionRuntime
  -> Verifier
  -> ProductGate
```

### Responsibilities

| Component | Owns | Must Not Own |
| --- | --- | --- |
| FrontDesk Engine | conversation, need grilling, source admission, semantic lock, slot filling, unknowns, intent bundle | product-specific compiler logic, product-grade decision, runtime closure |
| ProductInquiryProfile | product identity, slots, questions, risk dimensions, acceptance prerequisites, readiness rules | runtime authority, verifier closure |
| Product Integration | domain request schema, product contract, MissionIR compiler, product validators, product gate criteria | MissionForge runtime internals, PiWorker internals, FrontDesk core branches |
| MissionIR | final executable mission contract shape | elicitation strategy, product conversation protocol |
| MissionRuntime | work-unit execution and adaptive runtime state | product names, user-intent interpretation |
| Verifier | proof that MissionIR constraints are satisfied | product-grade registration |
| ProductGate | product readiness decision using verifier/artifact evidence | generic verifier replacement, worker self-report acceptance |

## ProductInquiryProfile

`ProductInquiryProfile` is the metadata contract that lets FrontDesk ask with a
product identity without hard-coding that product in core.

It should be small, typed, and refs-first. It is not a prompt template and not
a MissionIR fragment. It describes what FrontDesk must discover before a
product integration can safely compile.

Recommended schema:

```json
{
  "schema_version": "missionforge.frontdesk.product_inquiry_profile.v1",
  "product_id": "skillfoundry",
  "version": "1.0",
  "display_name": "SkillFoundry",
  "purpose": "Build product-grade Codex skill packages.",
  "activation": {
    "positive_terms": ["skill", "SKILL.md", "skill package"],
    "negative_terms": ["live trading"],
    "default_confidence": "hypothesis"
  },
  "inquiry_principles": [
    "Ask one high-value question at a time.",
    "Do not ask for secrets or raw provider payloads.",
    "Prefer product-readiness questions over implementation trivia."
  ],
  "slots": [],
  "risk_dimensions": [],
  "artifact_archetypes": [],
  "acceptance_prerequisites": [],
  "compiler_readiness": {
    "blocking_slot_ids": [],
    "allow_assumptions": false
  },
  "source_policy": {
    "raw_conversation_runtime_truth": false,
    "requires_sanitized_refs": true
  }
}
```

### InquirySlot

Slots are the main abstraction. A slot is not a passive form field. It carries
why the answer matters, how to ask for it, what shape the answer has, whether
it blocks compilation, and where it maps downstream.

Recommended schema:

```json
{
  "slot_id": "bundle_profile",
  "label": "Bundle profile",
  "description": "Whether the skill is prompt-only or needs runtime assets.",
  "required": "blocking",
  "value_type": "enum",
  "choices": ["prompt_only", "code_runtime"],
  "question": "这个 skill 是纯 prompt 能力，还是需要脚本、schema 或其他 runtime assets？",
  "why_this_matters": "SkillFoundry needs this to choose package artifacts and product-grade checks.",
  "recommended_answer": "If no scripts or schemas are required, choose prompt_only.",
  "default_value": "prompt_only",
  "depends_on": [],
  "conflicts_with": [],
  "maps_to": [
    {"target": "product_request.desired_bundle_profile"},
    {"target": "product_contract.bundle_profile"},
    {"target": "mission_ir.outputs.bundle_profile"},
    {"target": "product_gate.acceptance_matrix"}
  ],
  "risk_links": ["runtime_execution"],
  "source_refs_required": false,
  "authority_required": "harness"
}
```

Recommended slot enums:

```text
required:
  blocking | recommended | optional | conditional

value_type:
  free_text | enum | boolean | number | ref | ref_list |
  string_list | artifact_path | artifact_path_list

authority_required:
  harness | reviewer | human
```

Avoid an expression language in the first implementation. Use simple
`depends_on`, `conflicts_with`, and `maps_to` references. More expressive
validation can live in product integration code.

### RiskDimension

Risk dimensions tell FrontDesk what domain risks to surface early.

```json
{
  "risk_id": "raw_context_leakage",
  "label": "Raw context leakage",
  "trigger_terms": ["raw prompt", "transcript", "provider payload", "secret"],
  "blocking": true,
  "required_slot_ids": ["privacy_boundary"],
  "default_constraints": [
    "Do not write raw conversation, raw prompt, transcript, provider payload, credentials, or secrets into runtime-facing artifacts."
  ],
  "gate_links": ["SF-PROMPT-NO-RAW-CONTEXT"]
}
```

### AcceptancePrerequisite

Acceptance prerequisites are the part of ProductGate that should influence
FrontDesk questioning before compile time. They do not run product gates early;
they identify information ProductGate will need later.

```json
{
  "prerequisite_id": "skillfoundry-package-outputs-known",
  "summary": "Required package output refs are known.",
  "blocking_slot_ids": ["required_package_outputs"],
  "gate_check_ids": ["SF-PROMPT-SKILL-EXISTS", "SF-PROMPT-MANIFEST-EXISTS"],
  "failure_route": "needs_clarification"
}
```

## FrontDeskIntentBundle

`FrontDeskIntentBundle` is the formal FrontDesk output for product-aware
authoring. It aggregates current FrontDesk artifacts and product slot state
without becoming a product contract or MissionIR.

Building an intent bundle is an assembly step over LLM-authored FrontDesk
artifacts. It may preserve explicit refs and validate slot readiness
deterministically, but it must not auto-infer product meaning from raw
conversation or generic artifact names. Product slot values must come from
explicit LLM/PiWorker-authored artifacts, explicit profile defaults, or later
clarification answers.

Recommended artifact:

```text
frontdesk/intent_bundle.json
```

Recommended schema:

```json
{
  "schema_version": "missionforge.frontdesk_intent_bundle.v1",
  "session_id": "sf-frontdesk",
  "product_context": {
    "product_id": "skillfoundry",
    "profile_ref": "product_context/skillfoundry_inquiry_profile.json",
    "profile_hash": "sha256:..."
  },
  "generic_refs": {
    "semantic_lock_ref": "frontdesk/semantic_lock.json",
    "core_need_brief_ref": "frontdesk/core_need_brief.json",
    "source_admission_report_ref": "frontdesk/source_admission_report.json",
    "domain_language_ref": "frontdesk/domain_language.json"
  },
  "slot_values": [],
  "missing_blocking_slots": [],
  "risk_flags": [],
  "product_hypotheses": [],
  "readiness": "ready_for_product_compile",
  "compiler_notes": [],
  "source_refs": []
}
```

### SlotValue

```json
{
  "slot_id": "bundle_profile",
  "value": "prompt_only",
  "status": "confirmed",
  "confidence": "observed",
  "source_refs": ["frontdesk/turns/turn-002.txt"],
  "assumption": false
}
```

Recommended status values:

```text
confirmed | inferred | assumed | missing | rejected | not_applicable
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

## ProductIntegration Protocol

MissionForge core should expose the protocol shape. Product packages implement
the behavior.

```python
class ProductIntegration(Protocol):
    product_id: str

    def inquiry_profile(self) -> ProductInquiryProfile:
        ...

    def compile_intent(
        self,
        bundle: FrontDeskIntentBundle,
        *,
        workspace: str | Path,
    ) -> ProductCompileResult:
        ...

    def product_gate(
        self,
        *,
        workspace: str | Path,
    ) -> ProductGateResult:
        ...
```

`compile_intent()` may return:

```text
compiled:
  product_request_ref
  product_contract_ref
  mission_ir_ref
  frozen_contract_ref

needs_clarification:
  missing_slot_ids
  product_clarification_questions
```

This lets Product Integration participate in the clarification loop without
moving product branches into FrontDesk core.

## ProductGate Boundary

ProductGate should be split:

```text
MissionForge core:
  ProductGate protocol, result schema, finding schema, status vocabulary,
  refs-only validation.

Product Integration:
  product-specific acceptance matrix, checks, reports, registry/promotion
  semantics.
```

Generic status vocabulary:

```text
passed
failed
needs_review
unsupported
candidate
product_grade
quarantined
```

SkillFoundry may define checks such as:

```text
SF-PROMPT-SKILL-EXISTS
SF-PROMPT-MANIFEST-SCHEMA
SF-PROMPT-NO-RAW-CONTEXT
SF-PROMPT-NO-SELF-GRADE
```

Finance research may define different checks:

```text
FIN-NO-LIVE-TRADING
FIN-DATA-PROVENANCE
FIN-BACKTEST-REPRODUCIBLE
FIN-COST-SLIPPAGE-MODELED
FIN-NO-FINANCIAL-ADVICE
```

Core must not interpret product check ids.

## Relationship To MissionIR

MissionIR remains the runtime contract. Product context metadata should project
into MissionIR through Product Integration, not by overloading MissionIR with
elicitation protocol data.

Recommended MissionIR conventions for product-compiled missions:

```text
inputs.frontdesk_intent_bundle_ref
inputs.product_request_ref
inputs.product_contract_ref
inputs.acceptance_matrix_ref
outputs.required_artifacts
outputs.allowed_write_scopes
outputs.<product metadata>
constraints[].source_refs
verification.validators
verification.verification_profiles
observability.product_id
observability.product_compiler
```

MissionIR should not contain raw conversation, raw prompt text, provider
payloads, credentials, secrets, or ProductInquiryProfile internals beyond refs.

## Relationship To Profiles

Do not merge ProductInquiryProfile and ProfilePack.

```text
ProductInquiryProfile:
  FrontDesk questioning and slot filling.

ProfilePack:
  MissionIR expansion, capability constraints, validator language, evidence
  requirements.

ProductContract:
  Product-specific frozen intent after FrontDesk, before MissionIR.

ProductGateSpec:
  Product readiness criteria after runtime/verifier evidence exists.
```

Profiles remain the deterministic runtime/verifier extension mechanism.
ProductInquiryProfile remains the authoring-time questioning mechanism.

## SkillFoundry Reference Flow

The current SkillFoundry integration already has:

```text
SkillFoundryRequest
SkillProductContract
ProductAcceptanceMatrix
SkillFoundryMissionCompiler
ProductGradeGate
```

The missing formal bridge is:

```text
SkillFoundryInquiryProfile
FrontDeskIntentBundle -> SkillFoundryRequest
ProductClarificationRequest when required slots are missing
```

Target flow:

```text
missionforge-skillfoundry frontdesk
  -> FrontDesk(product_context=SkillFoundryInquiryProfile)
  -> frontdesk/intent_bundle.json
  -> SkillFoundryFrontDeskBridge
  -> product_contract/skillfoundry_request.json
  -> product_contract/skill_product_contract.json
  -> mission/skillfoundry_mission.json
  -> freeze
  -> runtime
  -> SkillFoundry ProductGradeGate
```

## Finance Research Example

A finance research integration should not add runtime branches. It should
provide its own inquiry profile, product contract, compiler, validators, and
product gate.

Possible required slots:

```text
research_question
asset_universe
timeframe
data_sources
backtest_window
execution_assumptions
cost_and_slippage_assumptions
risk_metrics
no_live_trading_boundary
output_reports
compliance_boundary
```

Possible product gate checks:

```text
FIN-NO-LIVE-TRADING
FIN-DATA-PROVENANCE
FIN-BACKTEST-REPRODUCIBLE
FIN-COST-SLIPPAGE-MODELED
FIN-OUT-OF-SAMPLE-REPORTED
FIN-NO-FINANCIAL-ADVICE
```

MissionForge core should see only refs, MissionIR, validators, evidence, and
product gate reports.

## Migration Rule

The existing FrontDesk `MissionIRMapper` should be treated as a generic fallback
compiler, not as the permanent FrontDesk responsibility.

Short-term compatibility after the LLM boundary:

```text
LLM-authored FrontDesk artifacts
  -> FrontDesk.draft()
  -> build generic FrontDeskIntentBundle internally
  -> GenericProductIntegration
  -> draft_mission.json
```

Long-term product-aware path:

```text
FrontDesk.elicit()
FrontDesk.build_intent_bundle()
ProductIntegration.compile_intent()
```

## Non-Goals

- no product branches in `src/missionforge/frontdesk`;
- no product branches in `src/missionforge/runtime`;
- no product-specific adapters under `src/missionforge/adapters`;
- no expression language in the first ProductInquiryProfile implementation;
- no deterministic authoring fallback when the LLM/PiWorker authoring node is
  unavailable;
- no live LLM requirement for default tests; use scripted clients or prewritten
  LLM artifact fixtures instead;
- no ProductGate result before runtime/verifier evidence exists;
- no MissionIR mutation by FrontDesk after freeze.

## Invariants

1. FrontDesk core may execute product inquiry metadata, but it must not import
   product integration modules.
2. Product Integration may depend on MissionForge. MissionForge must not depend
   on product integrations.
3. ProductInquiryProfile affects questioning only. It does not grant runtime
   authority.
4. Product Integration decides whether an intent bundle is sufficient for
   product compilation.
5. MissionIR remains the only runtime contract.
6. Verifier owns MissionIR closure.
7. ProductGate owns product readiness or registration, not generic verifier
   completion.
8. PiWorker remains the only LLM worker direction.
