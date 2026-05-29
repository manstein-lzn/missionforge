# SkillFoundry On MissionForge Plan

Last updated: 2026-05-29

Status: implemented through SF8 `code_runtime` as the second bundle profile

## Purpose

This document defines how to rebuild SkillFoundry as a thin product shell on top
of MissionForge.

The architectural test is simple:

```text
SkillFoundry product semantics + glue code should be enough to build a complete
Capability Bundle factory on the fixed MissionForge substrate.
```

If this effort requires new worker runtimes, product branches inside
`src/missionforge`, a new evidence ledger, a new repair loop, or a new
steering substrate, then either the integration is repeating MissionForge or the
MissionForge substrate still has a missing abstraction.

## Product Goal

SkillFoundry turns vague user needs into verified AI-native Capability Bundles.

It does not merely generate `SKILL.md`. A minimal bundle may only contain a
skill entry and references, but the product target includes richer bundles with
scripts, tests, data, services, MCP servers, examples, verification artifacts,
and distribution metadata.

The product promise is:

```text
User intent -> frozen product contract -> bounded agent build -> independent
verification -> product-grade gate -> registry.
```

## Fixed Substrate

MissionForge is the fixed base:

- `MissionIR` carries task facts.
- `ProfilePack` and profile refs carry reusable capability semantics.
- `FrozenMissionContract` locks mission truth.
- `WorkUnitContract` bounds a worker attempt.
- `pi-agent-runtime` is the only production worker.
- Evidence and metrics are recorded as refs.
- Verifier owns completion.
- Controlled steering proposes next steps without owning durable truth.
- Mission revisions change frozen contracts only through authority gates.
- Operator and audit surfaces observe state or write explicit control intent.

SkillFoundry must depend on MissionForge. MissionForge must not import
SkillFoundry.

## Integration Location

The work belongs under:

```text
integrations/skillfoundry/
```

Current bridge:

```text
FrontDesk-style refs
  -> SkillFoundrySourceBundle
  -> MissionIR
  -> freeze_mission
  -> MissionRuntime / CLI smoke
```

This should be extended into a product shell, not moved into core.

## Decisions

These decisions are locked for the first implementation pass so the work can
move without recurring architecture debates.

1. Keep SkillFoundry under `integrations/skillfoundry/`.
2. Treat MissionForge core as fixed unless dogfood proves a generic substrate
   gap.
3. Build the first slice around `prompt_only`, because it is the smallest real
   Capability Bundle profile that still tests product contracts, validators,
   product-grade status, and registry promotion.
4. Keep registry, product-grade semantics, and bundle manifest semantics inside
   the integration.
5. Use MissionForge public APIs first. Lower-level MissionForge imports are
   allowed only for existing integration compiler contracts and focused tests.
6. Keep default tests deterministic/offline. Live PI Agent runs are dogfood
   gates, not default validation.
7. Prefer product validators over MissionForge runtime changes.
8. Record every product-facing result as refs-only reports. The integration may
   inspect package files for validation, but public state should reference
   artifacts instead of embedding bodies.

## Non-Goals

- Do not add SkillFoundry branches to `src/missionforge`.
- Do not add a public worker registry.
- Do not revive command PiWorker as a product worker.
- Do not import old SkillFoundry runtime packages into MissionForge core.
- Do not introduce LangGraph, ForgeUnit, or ContextForge as required runtime
  dependencies for the new integration.
- Do not make live LLM execution the default.
- Do not let worker self-report, reviewer prose, dashboard state, or registry
  state close a mission.
- Do not store raw conversation, raw prompt, raw transcript, raw provider
  payloads, package bodies, or command bodies in refs-only run state.

## Current Starting Point

The repository already contains an integration bridge:

- `compiler.py` defines refs-only FrontDesk-style source bundle contracts.
- `SkillFoundryMissionCompiler` compiles accepted source refs into `MissionIR`.
- The compiler rejects raw transcript, prompt, payload, and body fields.
- Generated missions freeze deterministically through MissionForge.
- Integration tests prove MissionForge core does not import SkillFoundry.
- Operator smoke proves compiled SkillFoundry MissionIR can run and inspect
  through MissionForge without runtime branches.

This plan should build forward from that bridge. It should not replace it with
old SkillFoundry infrastructure.

## Current Implementation Status

Implemented in this slice:

- SF1 product contracts, bundle profiles, risk domains, product acceptance
  matrix, and prompt-only bundle manifest.
- SF2 prompt-only request compiler into product contract, acceptance matrix,
  MissionIR, frozen contract, and compiler diagnostics.
- SF3 prompt-only bundle validators for package files, manifest schema,
  safe refs, raw-context markers, and self-grade claims.
- SF4 ProductGradeGate with refs-only product-grade report and repair packet.
- SF5 local registry with candidate vs product-grade registration.
- SF6 thin runtime facade that composes compile, `MissionRuntime`, bundle
  validation, ProductGradeGate, registry, and refs-only product report.
- SF7 opt-in live PI Agent dogfood harness, refs-only dogfood report, and
  failure classification tests. The live run itself remains explicit and is
  skipped by default.
- SF8 `code_runtime` bundle profile with product contract defaults,
  acceptance matrix, manifest validation, MissionIR compilation, bundle
  validators, ProductGradeGate package-ref consistency checks, runtime facade
  tests, and FrontDesk mapping coverage.
- PI Agent faux runtime now writes all expected outputs, which is product
  neutral and lets multi-artifact MissionForge contracts execute offline.
- PI Agent live runtime now reached prompt-only product-grade registration in
  `.metaloop/skillfoundry_live_dogfood_sf7_repair3/` after two dogfood repairs:
  OpenAI Responses replay strips unreplayable thinking blocks, default live turn
  budget is 12, MissionForge work units name all expected outputs and generic
  artifact contracts, and the SkillFoundry compiler emits prompt-only manifest
  artifact contracts.

Not implemented yet:

- UI/API beyond the integration-level Python facade.
- Additional profiles after `code_runtime`, such as `knowledge_runtime`, MCP,
  service bundles, or full runtime bundles.

## Target Shape

```text
integrations/skillfoundry/
  src/missionforge_skillfoundry/
    compiler.py              # existing FrontDesk refs -> MissionIR bridge
    product_contract.py      # SkillFoundry product contracts
    profile_pack.py          # bundle profiles and risk domains
    validators.py            # package and bundle validators
    product_grade_gate.py    # candidate vs product-grade gate
    registry.py              # local product registry
    runtime.py               # thin facade over MissionRuntime
    reports.py               # refs-only product read model
  tests/
  docs/
```

The package should expose a small application API:

```python
compile_skillfoundry_bundle(...)
run_skillfoundry_bundle_build(...)
validate_skill_bundle(...)
evaluate_product_grade(...)
register_skill_bundle(...)
```

Each function is integration-level glue over MissionForge contracts and
SkillFoundry-specific validators.

## Domain Objects

### SkillFoundryRequest

The user-facing request or FrontDesk output. It should describe user intent in
product language:

- desired capability
- target user
- trigger and non-trigger cases
- expected outputs
- must / must_not constraints
- privacy and distribution boundaries
- optional source refs
- desired bundle profile, if known

It must not require the user to specify implementation-grade checks.

### SkillProductContract

The frozen product contract compiled from user-facing inputs:

- user intent contract
- selected bundle profile
- risk domains
- capability surface
- target package refs
- allowed write scopes
- acceptance summary
- verification principles

This is SkillFoundry product truth. It compiles into `MissionIR`, profile refs,
and validators.

### BundleProfile

Initial profiles:

- `prompt_only`
- `script_tool`
- `code_runtime`
- `knowledge_runtime`
- `mcp_runtime`
- `service_runtime`
- `full_runtime_bundle`

The first implementation should support only `prompt_only`. Other profiles are
planned once the shell proves the MissionForge integration path.

### RiskDomain

Initial risk domains:

- `privacy_sensitive_input`
- `filesystem_write`
- `structured_data_validation`
- `external_document_ingestion`
- `domain_knowledge_reliability`
- `network_boundary`
- `runtime_execution`
- `long_running_service`
- `distribution_package`

Risk domains drive product-grade defaults. They are SkillFoundry policy, not
MissionForge core policy.

### ProductAcceptanceMatrix

The matrix translates user intent and inferred risks into product-grade checks.

Examples:

```text
User says: "do not overwrite my files"
System injects:
  - existing target conflict check
  - same-plan duplicate target check
  - path traversal rejection
  - absolute path rejection
  - validation-only no-write check
```

The user should not have to name these implementation details.

Initial prompt-only matrix:

| Check id | Purpose | Blocking |
| --- | --- | --- |
| `SF-PROMPT-SKILL-EXISTS` | `package/SKILL.md` exists | yes |
| `SF-PROMPT-MANIFEST-EXISTS` | `package/skillfoundry.bundle.json` exists | yes |
| `SF-PROMPT-MANIFEST-SCHEMA` | manifest has required fields | yes |
| `SF-PROMPT-ENTRYPOINT` | manifest entrypoint is `SKILL.md` inside package | yes |
| `SF-PROMPT-README-EXISTS` | `package/README.md` exists | yes |
| `SF-PROMPT-REFS-SAFE` | manifest refs are workspace-relative package refs | yes |
| `SF-PROMPT-NO-RAW-CONTEXT` | package does not expose raw prompt/transcript markers | yes |
| `SF-PROMPT-NO-SELF-GRADE` | package does not claim its own product-grade approval | yes |
| `SF-PROMPT-VERIFICATION` | verifier and product gate refs are recorded externally | yes |

### SkillBundleManifest

Machine-readable bundle contract:

```text
package/skillfoundry.bundle.json
```

Minimum fields:

- schema version
- bundle id
- bundle profile
- entrypoint
- capability surface
- runtime assets
- data assets
- references
- environment
- permissions
- verification
- distribution

For `prompt_only`, the manifest may be small, but it must still define the
bundle identity, entrypoint, references, and verification contract.

### ProductGradeReport

The product-grade gate output:

- candidate package ref
- verifier refs
- product acceptance matrix ref
- checks run
- blocking findings
- major findings
- product grade boolean
- recommended registry status
- repair packet ref, if needed

Product-grade status is not the same as generic verification status.

### RegistryEntry

Registry status should distinguish at least:

- `generated`
- `verified`
- `candidate_registered`
- `product_grade_registered`
- `published`
- `deprecated`
- `quarantined`

The MVP may implement only `candidate_registered` and
`product_grade_registered`, with other statuses reserved.

### ProductReport

Refs-only product read model for CLI/API/UI:

- request ref
- product contract ref
- mission ref
- mission run id
- verifier refs
- product-grade report ref
- registry decision ref
- package refs
- final status
- trust boundary flags

It must not inline package bodies, raw worker outputs, raw prompts, or raw
transcripts.

## MissionForge Mapping

| SkillFoundry concept | MissionForge representation |
| --- | --- |
| SkillFoundryRequest | input artifact refs and integration payload |
| SkillProductContract | `MissionIR` inputs/outputs plus product refs |
| BundleProfile | profile refs / integration profile pack |
| RiskDomain | product validators and acceptance matrix |
| Capability surface | `MissionIR.outputs` and bundle manifest |
| Next build step | `WorkUnitContract` |
| Builder | `pi-agent-runtime` |
| Work evidence | evidence refs / artifact refs |
| ProductGradeGate | integration-level verifier gate |
| Registry | integration-level asset registry |
| Adaptive steering | MissionForge controlled steering contracts |
| Spec revision | MissionForge mission revision plus product authority |

## Minimal Product Slice

The first product slice should prove the shell with the smallest credible
Capability Bundle:

```text
Profile: prompt_only
Expected package:
  package/SKILL.md
  package/skillfoundry.bundle.json
  package/README.md
```

Required checks:

- `SKILL.md` exists.
- `skillfoundry.bundle.json` exists.
- manifest schema is valid.
- manifest entrypoint points to `SKILL.md`.
- `README.md` exists.
- package refs stay inside allowed package scope.
- package does not include raw prompt/transcript/conversation markers.
- bundle does not claim product-grade status in its own content.
- MissionForge verifier passes before registry.
- ProductGradeGate passes before product-grade registration.

Default execution should remain deterministic/offline. Live
`pi-agent-runtime` can be used only through explicit opt-in configuration.

## MVP File Artifacts

The first slice should produce and consume these integration-owned artifacts:

```text
product_contract/skill_product_contract.json
product_contract/product_acceptance_matrix.json
product_contract/compiler_report.json
package/SKILL.md
package/skillfoundry.bundle.json
package/README.md
qa/skill_bundle_validation_report.json
qa/product_grade_report.json
qa/product_repair_packet.json        # only on blocking findings
registry/skillfoundry_registry.json
reports/skillfoundry_product_report.json
```

MissionForge-owned artifacts remain under existing MissionForge refs such as
`missions/`, `runs/`, `attempts/`, `evidence/`, and steering refs.

## Product Flow

MVP flow:

```text
SkillFoundryRequest / FrontDesk refs
  -> SkillProductContract
  -> ProductAcceptanceMatrix
  -> MissionIR + profile refs + validators
  -> MissionRuntime
  -> pi-agent-runtime
  -> MissionResult + evidence refs
  -> Skill bundle validators
  -> ProductGradeGate
  -> LocalRegistry
  -> refs-only ProductReport
```

Repair flow:

```text
ProductGradeGate failure
  -> ProductRepairPacket
  -> MissionForge repair follow-up or controlled steering proposal
  -> next WorkUnitContract
  -> verifier and ProductGradeGate rerun
```

The repair packet is product guidance. Runtime authority still belongs to
MissionForge.

## Controlled Steering Role

SkillFoundry should use MissionForge controlled steering for adaptive product
work, but only after the deterministic MVP proves the thin shell.

The steering estimator should read:

- mission run refs
- attempt refs
- verifier refs
- product-grade report refs
- repair packet refs
- registry decision refs

It may emit:

- observation signals
- repair strategy proposals
- contract adjustment requests
- review packets

It may not:

- close a mission
- register a package
- weaken the frozen product contract
- expand write scope without revision authority
- override failed executable validators

## Phase Plan

### Phase SF0: Planning And Boundary Lock

Status: implemented.

Deliverables:

- this plan
- updated integration README pointer
- no code changes in `src/missionforge`

Acceptance:

- clear location under `integrations/skillfoundry`
- no new core imports
- implementation phases can be tested independently

### Phase SF1: Product Contracts

Status: implemented for the prompt-only MVP.

Add:

- `SkillFoundryRequest`
- `SkillProductContract`
- `BundleProfile`
- `RiskDomain`
- `ProductAcceptanceMatrix`
- `SkillBundleManifest`

Acceptance:

- schema round-trip tests
- refs-only checks
- raw prompt/transcript fields rejected
- deterministic hash for product contract

Recommended tests:

- `test_product_contract.py`
- `test_product_acceptance_matrix.py`

### Phase SF2: Prompt-Only Compiler

Status: implemented.

Extend the existing compiler path:

```text
SkillFoundryRequest / FrontDesk refs
  -> SkillProductContract
  -> MissionIR
```

Acceptance:

- `prompt_only` request compiles to valid MissionIR
- required outputs include `package/SKILL.md`,
  `package/skillfoundry.bundle.json`, and `package/README.md`
- generated mission freezes deterministically
- profile refs are used, not runtime branches

Recommended tests:

- extend `test_skillfoundry_compiler.py`
- add `test_prompt_only_compiler.py`

### Phase SF3: Bundle Validators

Status: implemented for prompt-only package checks.

Add deterministic validators for the prompt-only package.

Acceptance:

- valid package passes
- missing `SKILL.md` fails
- missing or malformed manifest fails
- manifest entrypoint outside package fails
- raw prompt/transcript markers fail
- self-claimed product-grade content fails

Recommended tests:

- `test_skill_bundle_validators.py`

### Phase SF4: ProductGradeGate

Status: implemented.

Add a SkillFoundry product-grade gate that consumes MissionForge verifier output
and bundle validator reports.

Acceptance:

- verifier pass plus product checks pass -> product grade true
- verifier pass but product checks fail -> product grade false
- worker self-report never counts as acceptance
- report is refs-only and hashable
- repair packet is generated for blocking findings

Recommended tests:

- `test_product_grade_gate.py`

### Phase SF5: Local Registry

Status: implemented.

Add local registry as an integration-level product asset store.

Acceptance:

- failed ProductGradeGate cannot create `product_grade_registered`
- passing ProductGradeGate can create `product_grade_registered`
- candidate registration remains distinguishable from product-grade
- registry entry includes package hash and ProductGradeGate refs

Recommended tests:

- `test_registry.py`

### Phase SF6: Thin Runtime Facade

Status: implemented.

Add a product convenience API over MissionForge:

```text
run_skillfoundry_bundle_build(...)
```

It should compose:

```text
compile -> runtime.run -> validate -> grade -> register -> report
```

Acceptance:

- offline smoke completes with deterministic/faux worker path
- operator inspect still works through MissionForge
- product report is refs-only
- no MissionForge core changes are needed

Recommended tests:

- `test_skillfoundry_runtime_facade.py`
- keep `test_operator_skillfoundry_smoke.py` passing

### Phase SF7: Live PI Agent Dogfood

Status: implemented with opt-in live dogfood reaching product-grade
registration. This must remain opt-in and should not run in default tests.

Run opt-in live dogfood using current Codex provider configuration.

Acceptance:

- live execution requires explicit opt-in;
- API keys and provider payloads are absent from product-facing artifacts;
- the dogfood harness uses `pi-agent-runtime` through `MissionRuntime` with
  `provider_mode=live` and `provider_config_source=codex_current`;
- at least one prompt-only bundle attempt is compiled, run, validated, graded,
  and registered when the opt-in live command is executed;
- failures are classified as product contract, worker execution, verifier,
  product-grade, or registry failures.

Implemented artifacts:

- `dogfood.py` defines the refs-only dogfood report and live harness.
- `test_skillfoundry_live_dogfood.py` verifies explicit opt-in, live provider
  configuration, product-grade failure classification, and early product
  contract failure classification.
- The opt-in live test is skipped unless
  `MISSIONFORGE_SKILLFOUNDRY_LIVE_DOGFOOD=1` is set.

Live dogfood evidence:

```text
Workspace: .metaloop/skillfoundry_live_dogfood_sf7/
Report: reports/skillfoundry_live_dogfood_report.json
Outcome category: worker_execution
Run status: classified_failure
Issue codes:
  - missing_expected_package_refs
  - verifier_status:failed
Report hash:
  sha256:ff5cfd7113ea105b21b2c9ae6e9d2b9c405ac7e83d36077b11b2471954be0059
```

Initial evidence showed the shell compiled and ran, but the live worker did not
create the required package artifacts. This was treated as a worker execution /
work-unit shaping finding, not as a reason to add another worker.

```text
Workspace: .metaloop/skillfoundry_live_dogfood_sf7_repair2/
Report: reports/skillfoundry_live_dogfood_report.json
Outcome category: product_grade
Run status: classified_failure
Issue codes:
  - bundle_validator:SF-PROMPT-MANIFEST-SCHEMA
  - bundle_validator:SF-PROMPT-ENTRYPOINT
  - bundle_validator:SF-PROMPT-REFS-SAFE
Report hash:
  sha256:e32fbd1be21a6a04a37d46266bdc0a79244733b0f29a0f3ec8d0343cf1cb65be
```

Repair2 evidence showed MissionForge and the live PI Agent could produce all
three required package refs and pass MissionForge verification. The remaining
gap was SkillFoundry product-grade manifest quality, so the repair belonged in
product contract / artifact-contract guidance.

```text
Workspace: .metaloop/skillfoundry_live_dogfood_sf7_repair3/
Report: reports/skillfoundry_live_dogfood_report.json
Outcome category: completed
Run status: completed
Issue codes:
  - product_grade_registered
Package refs:
  - package/SKILL.md
  - package/skillfoundry.bundle.json
  - package/README.md
Report hash:
  sha256:97b2fb38d3b86af0484ec9a048bed53ffb3f208edbe23968604751be0790fd25
```

Repair3 evidence proves the prompt-only live product slice can compile, run
through `pi-agent-runtime`, pass MissionForge verification, pass the
SkillFoundry bundle validators and ProductGradeGate, and register as
`product_grade_registered`.

Common leak-marker scan over the repair3 workspace found no matches for API key
names, provider payload markers, raw prompt/transcript markers, or `sk-*`
token-shaped strings.

Recommended evidence:

- opt-in live run transcript refs are redacted
- product report captures failure category or registry status
- live artifacts are not committed by default

### Phase SF8: Next Bundle Profile

Status: implemented for `code_runtime`.

The selected second profile is:

```text
code_runtime
```

This choice matches the Codexarium validation target, where executable helper
logic, schema artifacts, and local runtime assets dominate the real acceptance
criteria.

Acceptance:

- new profile adds product validators, not MissionForge runtime branches
- ProductAcceptanceMatrix injects risk-driven checks
- at least one realistic package fails before hardening and passes after repair

Current decision:

SF8 is implemented as an integration-owned profile. It adds code-runtime
product contracts, package refs, manifest rules, MissionIR compilation,
validators, and ProductGradeGate checks while preserving the fixed MissionForge
substrate. MissionForge core still does not know about `BundleProfile`,
`code_runtime`, SkillFoundry, or Codexarium product semantics.

## Implementation Order

The original SF0-SF8 order was intentionally narrow:

1. Implement schemas and hashable refs-only artifacts.
2. Compile prompt-only product contract into the existing MissionIR bridge.
3. Validate a hand-authored prompt-only package before invoking runtime.
4. Add ProductGradeGate over validator reports.
5. Add local registry.
6. Add runtime facade that composes the already-tested pieces.
7. Run deterministic/faux smoke.
8. Run live dogfood only after offline closure is stable.
9. Add `code_runtime` as the first non-prompt bundle profile using
   SkillFoundry-owned contracts and validators.

This sequence prevents the product shell from hiding weak contracts behind a
successful worker run.

## Validation Commands

Integration tests:

```bash
PYTHONPATH=src:integrations/skillfoundry/src \
  python3 -m unittest discover -s integrations/skillfoundry/tests
```

Integration boundary script:

```bash
./scripts/validate_integrations.sh skillfoundry
```

Core regression should still pass without depending on the integration:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Node worker regression:

```bash
npm test --prefix workers/pi-agent-runtime
```

Latest verification evidence:

```bash
PYTHONPATH=src:integrations/skillfoundry/src python3 -m unittest discover -s integrations/skillfoundry/tests
# Ran 40 tests: OK

./scripts/validate_integrations.sh skillfoundry
# passed

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 246 tests: OK (skipped=2)

npm test --prefix workers/pi-agent-runtime
# 17 tests: pass

git diff --check
# passed

PYTHONPATH=src:integrations/skillfoundry/src python3 -m unittest discover -s integrations/skillfoundry/tests
# Ran 45 tests: OK (skipped=1)

MISSIONFORGE_SKILLFOUNDRY_LIVE_DOGFOOD=1 MISSIONFORGE_SKILLFOUNDRY_LIVE_TIMEOUT_SECONDS=300 \
PYTHONPATH=src:integrations/skillfoundry/src \
  python3 -m unittest discover -s integrations/skillfoundry/tests -p "test_skillfoundry_live_dogfood.py"
# Ran 5 tests: OK

MISSIONFORGE_SKILLFOUNDRY_LIVE_DOGFOOD=1 MISSIONFORGE_SKILLFOUNDRY_LIVE_TIMEOUT_SECONDS=300 \
PYTHONPATH=src:integrations/skillfoundry/src \
  python3 - <<'PY'
# Produced .metaloop/skillfoundry_live_dogfood_sf7/reports/skillfoundry_live_dogfood_report.json
# outcome_category=worker_execution, run_status=classified_failure
PY

PYTHONPATH=src:integrations/skillfoundry/src python3 -m unittest discover -s integrations/skillfoundry/tests
# Ran 45 tests: OK (skipped=1)

./scripts/validate_integrations.sh skillfoundry
# passed; Ran 45 tests: OK (skipped=1)

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 248 tests: OK (skipped=2)

npm test --prefix workers/pi-agent-runtime
# 19 tests: pass

git diff --check
# passed

MISSIONFORGE_SKILLFOUNDRY_LIVE_DOGFOOD=1 MISSIONFORGE_SKILLFOUNDRY_LIVE_TIMEOUT_SECONDS=300 \
PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
  python3 - <<'PY'
# Produced .metaloop/skillfoundry_live_dogfood_sf7_repair3/reports/skillfoundry_live_dogfood_report.json
# outcome_category=completed, run_status=completed
# registry status=product_grade_registered
PY
```

## Architecture Review Gates

Stop and redesign if any phase requires:

- importing `missionforge_skillfoundry` from `src/missionforge`
- adding SkillFoundry-specific switches to runtime
- bypassing `MissionRuntime`
- bypassing verifier closure
- treating PI Agent claims as acceptance
- storing raw prompt/transcript/provider payloads in state
- adding a second production worker path
- moving registry or product-grade semantics into MissionForge core

Escalate to MissionForge core only when the integration proves a generic
substrate gap that would also affect non-SkillFoundry products.

## Success Criteria

The architecture validation succeeds when:

- the MVP SkillFoundry product shell builds and registers a prompt-only
  Capability Bundle;
- all product semantics live under `integrations/skillfoundry`;
- MissionForge core remains product-neutral;
- the implementation mostly composes existing MissionForge public APIs;
- failure handling uses MissionForge verifier, repair, steering, revision, and
  audit paths rather than custom product runtime logic;
- live dogfood produces a product-grade registered prompt-only bundle and
  concrete evidence for selecting the next bundle profile.
