# Integration: SkillFoundry

## Goal

Compile SkillFoundry-facing source artifacts into MissionForge `MissionIR`
without making the `missionforge` Python package depend on SkillFoundry product
semantics.

SkillFoundry should become an application shell on top of MissionForge, not a
set of runtime branches inside MissionForge.

## Scope

- FrontDesk-style source bundle refs
- sanitized user/task source refs
- capability-bundle MissionIR compilation
- profile ref selection
- Skill package output target declaration
- product integration import-boundary checks
- refs-only compile result
- prompt-only and code-runtime product shell contracts, validators,
  ProductGradeGate, registry, product report, and opt-in live dogfood

## Non-Goals

- no SkillFoundry dependency in the `missionforge` Python package
- no external registry publishing
- no product-specific runtime branch
- no live LLM in default validation
- no live PI Agent execution unless explicitly opted in for dogfood
- no raw transcript ingestion unless represented as an explicitly allowed
  sanitized source ref

## Current Status

The migration bridge is now an external product integration under
`integrations/skillfoundry/`. It compiles FrontDesk-style refs into
MissionForge `MissionIR`, writes refs-only compiler outputs, and keeps
SkillFoundry product semantics outside the `missionforge` Python package.

The deterministic bridge still does not import SkillFoundry runtime packages,
call live LLMs by default, use LangGraph, or expose HTTP. The product-shell
slice adds integration-owned registry/ProductGradeGate behavior and an explicit
opt-in live PI Agent dogfood harness that runs through MissionForge
`MissionRuntime`, not through a SkillFoundry-specific runtime branch.

Phase 11 operator productization adds a smoke path proving compiled
SkillFoundry MissionIR can pass through `MissionCLI.run_command(["run", ...])`
and `inspect` without adding SkillFoundry runtime branches.

The product-shell roadmap is tracked separately in
`docs/skillfoundry_on_missionforge_plan.md`. This document remains the current
integration contract; the roadmap defines how to extend the bridge into a
complete SkillFoundry shell on the MissionForge substrate.

## Public Contracts

Implemented in Goal 6B:

- `SkillFoundrySourceBundle`
- `SkillFoundryCompileResult`
- `FrontDeskArtifactRef`
- `SkillPackageTarget`
- `SkillFoundryMissionCompiler`

Implemented in the product-shell slices:

- `SkillFoundryRequest`
- `SkillProductContract`
- `ProductAcceptanceMatrix`
- `SkillBundleManifest`
- `validate_skill_bundle`
- `evaluate_product_grade`
- `register_skill_bundle`
- `run_skillfoundry_bundle_build`
- `run_skillfoundry_live_dogfood`

Implemented bundle profiles:

- `prompt_only`
- `code_runtime`

## Contract Sketch

`SkillFoundrySourceBundle` should describe input refs only:

```json
{
  "bundle_id": "sf-source-001",
  "frontdesk_contract_ref": "frontdesk/task_contract.json",
  "source_manifest_ref": "frontdesk/source_manifest.json",
  "target_package_ref": "package/SKILL.md",
  "allowed_write_scopes": ["package", "attempts"],
  "capability_profile_refs": [
    {
      "profile_id": "user_provided_evidence_only",
      "requirements": {}
    },
    {
      "profile_id": "explicit_output_root",
      "requirements": {
        "output_root": "package"
      }
    }
  ]
}
```

`SkillFoundryCompileResult` should return a MissionIR ref and diagnostics:

```json
{
  "bundle_id": "sf-source-001",
  "mission_ir_ref": "missions/sf-source-001.mission.json",
  "diagnostic_refs": ["evidence/skillfoundry_compile_diagnostics.json"],
  "warnings": []
}
```

## Invariants

- SkillFoundry names may appear in this external integration, not in
  MissionForge runtime branches or core adapters.
- The integration compiles product facts into MissionIR and profile refs.
- Capability bundle behavior is expressed through profiles and validators.
- Raw chat or transcript material is not task truth.
- Compile results are refs-only.
- Free-form SkillFoundry worker or LLM claims are evidence only, never
  acceptance.
- `missionforge` must not import `missionforge_skillfoundry`.
- `src/missionforge/adapters/skillfoundry.py` must not exist.

## Implemented Integration Behavior

- `SkillFoundrySourceBundle` describes FrontDesk contract refs, source manifest
  refs, target package refs, allowed write scopes, capability profile refs, and
  verification profile refs.
- `FrontDeskArtifactRef` admits sanitized refs such as `sanitized_source` and
  `sanitized_transcript`; raw transcript/chat/conversation refs are rejected.
- `SkillFoundryMissionCompiler` reads the referenced FrontDesk contract and
  source manifest, rejects raw transcript/prompt/payload/body fields, and
  compiles a valid `MissionIR`.
- Generated MissionIR carries admitted source refs in `inputs`, target package
  refs and allowed write scopes in `outputs`, integration constraints, and the
  selected capability/verification profile refs.
- Source bundles must declare capability profile refs; the compiler rejects
  capability-bundle input that would otherwise bypass profile expansion.
- Generated MissionIR is frozen through `freeze_mission`, so capability and
  verification profile behavior uses the same deterministic expansion path as
  core MissionForge.
- `SkillFoundryCompileResult` returns only refs, profile ids, target package
  ref, contract hash, diagnostics refs, and warnings. It does not embed
  FrontDesk artifact bodies.
- The integration operator smoke compiles a FrontDesk fixture, runs the generated
  MissionIR through the operator `run` command, and inspects the resulting
  `MissionRun` state through the operator `inspect` command.
- `SkillFoundryRequest` compiles to product contract refs,
  MissionIR, bundle validators, ProductGradeGate, local registry, product
  report, and opt-in live dogfood report.
- Prompt-only MissionIR includes generic artifact contracts for required
  package files so MissionForge can pass product-shell artifact requirements to
  workers without knowing SkillFoundry semantics.
- Code-runtime MissionIR includes generic package artifact contracts for
  `SKILL.md`, the SkillFoundry manifest, README, runtime assets, helper
  scripts, and schema refs. The compiler emits generic `file_exists`,
  `json_field_exists`, and `command` validators under
  `generic_local_verification`.
- Code-runtime package validation checks manifest profile, runtime asset
  declaration/existence, helper script health entrypoints, JSON schema parsing,
  raw-context markers, and package self-grade claims.
- Live dogfood remains explicit opt-in and uses `pi-agent-runtime` with
  `provider_mode=live` and `provider_config_source=codex_current`.

## Dependencies

- Mission IR
- profiles
- freeze kernel
- context/evidence
- adapter contracts

## Verification Strategy

- valid FrontDesk fixture compiles to valid MissionIR
- generated MissionIR freezes deterministically
- raw transcript input is rejected unless declared as sanitized evidence
- capability bundle behavior uses profiles, not runtime branches
- import-boundary test proves MissionForge does not import the SkillFoundry
  integration and does not contain a SkillFoundry adapter module
- compile result is refs-only

## Verification Evidence

Goal 6B focused tests:

```bash
PYTHONPATH=src:integrations/skillfoundry/src python3 -m unittest discover -s integrations/skillfoundry/tests
# Ran 24 tests: OK

./scripts/validate_integrations.sh skillfoundry
# passed
```

Independent reviewer `Helmholtz` approved Goal 6B after one repair to require
capability profile refs for capability-bundle compilation. MetaLoop
verification reached `completed_verified`.

Prompt-only product-shell verification:

```bash
PYTHONPATH=src:integrations/skillfoundry/src python3 -m unittest discover -s integrations/skillfoundry/tests
# Ran 45 tests: OK (skipped=1)

./scripts/validate_integrations.sh skillfoundry
# passed

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 248 tests: OK (skipped=2)

npm test --prefix workers/pi-agent-runtime
# 19 tests: pass
```

Code-runtime profile verification:

```bash
PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
  python3 -m unittest \
  integrations/skillfoundry/tests/test_product_contract.py \
  integrations/skillfoundry/tests/test_prompt_only_compiler.py \
  integrations/skillfoundry/tests/test_skill_bundle_validators.py \
  integrations/skillfoundry/tests/test_product_grade_gate.py \
  integrations/skillfoundry/tests/test_skillfoundry_runtime_facade.py \
  integrations/skillfoundry/tests/test_skillfoundry_frontdesk_flow.py \
  integrations/skillfoundry/tests/test_skillfoundry_import_boundaries.py
# Ran 43 tests: OK

./scripts/validate_integrations.sh skillfoundry
# Ran 65 tests: OK (skipped=1)

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 292 tests: OK (skipped=2)
```

Opt-in live dogfood evidence:

```text
Workspace: .metaloop/skillfoundry_live_dogfood_sf7_repair3/
Outcome category: completed
Run status: completed
Registry status: product_grade_registered
```

## Review Gates

Independent review is required if:

- integration behavior appears to require a MissionForge runtime branch
- source bundle shape exposes raw conversation or private material
- profile requirements are too product-specific for reusable profile data
- registry publishing or packaging side effects enter the compile step
- live dogfood requires a SkillFoundry-specific MissionForge runtime branch

## Open Questions

- Which exact FrontDesk artifacts should become the first stable
  SkillFoundry-facing product fixture?
- Should the integration write MissionIR files itself or return an in-memory object
  plus refs?
- Should SkillFoundry package validation eventually become a reusable
  MissionForge verification profile after more product evidence?
