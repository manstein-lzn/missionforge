# SkillFoundry Bundle Profile Development Guide

Last updated: 2026-05-29

Status: `development guide`; `code_runtime` implemented as the second
SkillFoundry bundle profile.

## Purpose

This guide explains how to add new SkillFoundry bundle profiles on top of the
fixed MissionForge substrate.

Use it when extending SkillFoundry beyond the current `prompt_only` slice, for
example to support `script_tool`, `code_runtime`, `knowledge_runtime`,
`mcp_runtime`, `service_runtime`, or `full_runtime_bundle`.

The key rule is:

```text
SkillFoundry owns bundle product semantics.
MissionForge owns generic mission execution, evidence, verification, freeze,
revision, and runtime mechanics.
```

A bundle profile must compile product-specific rules into MissionForge-readable
contracts. It must not require MissionForge core to understand product names or
bundle profile names.

## Current Baseline

The current implementation has the vocabulary for multiple profiles:

```python
class BundleProfile(StrEnum):
    PROMPT_ONLY = "prompt_only"
    SCRIPT_TOOL = "script_tool"
    CODE_RUNTIME = "code_runtime"
    KNOWLEDGE_RUNTIME = "knowledge_runtime"
    MCP_RUNTIME = "mcp_runtime"
    SERVICE_RUNTIME = "service_runtime"
    FULL_RUNTIME_BUNDLE = "full_runtime_bundle"
```

The current implementation supports these profiles end to end:

```text
prompt_only
code_runtime
```

Other profiles remain vocabulary only until they gain deterministic product
rules, validators, and MissionIR compilation.

## Layering Model

### SkillFoundry Bundle Profile

Owned by `integrations/skillfoundry`.

Defines product shape:

- expected package files;
- runtime assets;
- data assets;
- scripts or service entrypoints;
- allowed write scopes;
- manifest fields;
- risk domains;
- product acceptance checks;
- ProductGradeGate behavior;
- registry status policy.

Examples:

- `prompt_only`
- `script_tool`
- `code_runtime`
- `full_runtime_bundle`

### MissionForge Profile

Owned by MissionForge or external ProfilePacks.

Defines reusable mission behavior:

- capability constraints;
- evidence requirements;
- required artifacts;
- allowed validator language;
- reviewer questions and known gaps.

Examples:

- `user_provided_evidence_only`
- `explicit_output_root`
- `generic_local_verification`
- future `packaged_runtime_assets`
- future `command_health_check_required`

### MissionIR

MissionForge runtime truth.

SkillFoundry compiles the bundle profile into:

- `MissionIR.inputs`;
- `MissionIR.outputs`;
- `MissionIR.constraints`;
- `MissionIR.capability_profiles`;
- `MissionIR.verification`;
- frozen contract refs.

MissionForge executes and verifies only this generic contract.

## Boundary Rules

Do:

- keep all bundle profile code under `integrations/skillfoundry`;
- compile profile semantics into `MissionIR`;
- use MissionForge `ProfilePack` only for reusable generic capability or
  verification semantics;
- add SkillFoundry validators and ProductGradeGate checks in the integration;
- keep outputs, reports, and dogfood summaries refs-only;
- use `MissionRuntime` and `freeze_mission` unchanged.

Do not:

- add `BundleProfile` to `src/missionforge`;
- branch MissionForge runtime on `prompt_only`, `code_runtime`, Codexarium, or
  any product name;
- add a second production worker path;
- let worker self-report decide product grade;
- store raw prompt, transcript, provider payload, package body, secret, or
  credential material in durable reports;
- use MissionForge metrics or adapter internals as hidden product routing.

## Development Shape

Adding another profile should follow this sequence:

```text
BundleProfile enum
  -> product contract defaults
  -> acceptance matrix
  -> manifest contract
  -> MissionIR compiler
  -> bundle validators
  -> ProductGradeGate
  -> runtime facade / dogfood
  -> docs and import-boundary tests
```

Do not start by changing runtime behavior. Start by making the product contract
explicit.

## Files To Touch

Expected files:

- `integrations/skillfoundry/src/missionforge_skillfoundry/product_contract.py`
- `integrations/skillfoundry/src/missionforge_skillfoundry/compiler.py`
- `integrations/skillfoundry/src/missionforge_skillfoundry/validators.py`
- `integrations/skillfoundry/src/missionforge_skillfoundry/product_grade_gate.py`
- `integrations/skillfoundry/src/missionforge_skillfoundry/runtime.py`
- `integrations/skillfoundry/src/missionforge_skillfoundry/__init__.py`
- `integrations/skillfoundry/docs/skillfoundry_integration.md`
- `integrations/skillfoundry/docs/skillfoundry_product_shell_validation_plan.md`

Expected tests:

- `integrations/skillfoundry/tests/test_product_contract.py`
- `integrations/skillfoundry/tests/test_prompt_only_compiler.py` or a new
  profile-specific compiler test file
- `integrations/skillfoundry/tests/test_skill_bundle_validators.py`
- `integrations/skillfoundry/tests/test_product_grade_gate.py`
- `integrations/skillfoundry/tests/test_skillfoundry_runtime_facade.py`
- `integrations/skillfoundry/tests/test_skillfoundry_frontdesk_flow.py`
- `integrations/skillfoundry/tests/test_skillfoundry_import_boundaries.py`

Do not touch `src/missionforge/runtime.py` for a new bundle profile.

## Phase 1: Product Contract Defaults

### Goal

Make the profile accepted by SkillFoundry product contracts without weakening
validation.

### Implementation

In `product_contract.py`, introduce profile-specific default functions instead
of hard-coding prompt-only defaults everywhere.

Recommended helpers:

```python
def target_package_refs_for_profile(profile: BundleProfile) -> list[str]:
    ...

def allowed_write_scopes_for_profile(profile: BundleProfile) -> list[str]:
    ...

def capability_surface_for_profile(profile: BundleProfile) -> dict[str, Any]:
    ...

def acceptance_summary_for_profile(profile: BundleProfile) -> str:
    ...
```

For example, `code_runtime` might require:

```text
package/SKILL.md
package/skillfoundry.bundle.json
package/README.md
package/scripts/<tool>.py
package/bin/<runtime>
package/schemas/<schema>.json
```

Keep refs concrete and workspace-relative.

### Tests

Add tests proving:

- `SkillFoundryRequest` accepts the new `desired_bundle_profile`;
- `SkillProductContract.from_request()` produces profile-specific target refs;
- invalid refs still fail closed;
- non-prompt profiles no longer hit the prompt-only guard;
- product contract hashes remain deterministic.

## Phase 2: Acceptance Matrix

### Goal

Define product-grade checks for the new profile.

### Implementation

Add a profile-specific matrix builder:

```python
ProductAcceptanceMatrix.for_code_runtime(...)
```

or a generic dispatcher:

```python
ProductAcceptanceMatrix.for_profile(bundle_id=..., profile=...)
```

Suggested `code_runtime` checks:

```text
SF-CODE-SKILL-EXISTS
SF-CODE-MANIFEST-EXISTS
SF-CODE-MANIFEST-SCHEMA
SF-CODE-ENTRYPOINT
SF-CODE-README-EXISTS
SF-CODE-RUNTIME-ASSETS-DECLARED
SF-CODE-RUNTIME-ASSETS-EXIST
SF-CODE-SCRIPTS-EXECUTABLE
SF-CODE-SCHEMAS-VALID
SF-CODE-NO-RAW-CONTEXT
SF-CODE-NO-SELF-GRADE
SF-CODE-VERIFICATION
```

For Codexarium specifically, likely checks include:

```text
SF-CODEXARIUM-SKILL-MODES
SF-CODEXARIUM-HELPER-COMMANDS
SF-CODEXARIUM-EVIDENCE-BOUNDARY
SF-CODEXARIUM-WIKI-WRITE-BOUNDARY
SF-CODEXARIUM-SIDECAR-HEALTH-CONTRACT
```

Only add Codexarium-named checks if they stay in SkillFoundry or a Codexarium
integration package, not MissionForge core.

### Tests

Add tests proving:

- the matrix contains all required checks;
- duplicate check ids fail closed;
- profile risk domains add stricter checks where appropriate;
- matrix round-trips through `from_dict()`.

## Phase 3: Manifest Contract

### Goal

Extend `SkillBundleManifest` validation so each profile has a precise package
shape.

### Implementation

The current manifest accepts generic fields but validates prompt-only entrypoint
rules. Add profile-aware validation:

```python
def validate_manifest_for_profile(manifest: SkillBundleManifest) -> None:
    if manifest.bundle_profile == BundleProfile.PROMPT_ONLY:
        ...
    elif manifest.bundle_profile == BundleProfile.CODE_RUNTIME:
        ...
```

For `code_runtime`, require:

- `entrypoint == "SKILL.md"` for Codex skill surface;
- `runtime_assets` contains package-relative refs;
- scripts or binaries stay under package-owned scopes;
- schemas stay under package-owned scopes;
- `permissions` is explicit and refs-only;
- environment requirements are explicit and JSON-compatible;
- no absolute paths or private host paths in manifest refs.

### Tests

Add tests proving:

- valid profile manifest passes;
- missing runtime asset fails;
- unsafe ref fails;
- raw context markers fail;
- prompt-only behavior remains unchanged.

## Phase 4: MissionIR Compilation

### Goal

Compile the new bundle profile into generic MissionForge mission truth.

### Implementation

In `compiler.py`, dispatch by `product_contract.bundle_profile`:

```python
def _compile_product_mission(request, product_contract):
    if product_contract.bundle_profile == BundleProfile.PROMPT_ONLY:
        return _compile_prompt_only_mission(request, product_contract)
    if product_contract.bundle_profile == BundleProfile.CODE_RUNTIME:
        return _compile_code_runtime_mission(request, product_contract)
    ...
```

The profile-specific compiler must fill:

```text
MissionIR.outputs.required_artifacts
MissionIR.outputs.allowed_write_scopes
MissionIR.outputs.bundle_profile
MissionIR.outputs.bundle_manifest_ref
MissionIR.outputs.artifact_contracts
MissionIR.constraints
MissionIR.capability_profiles
MissionIR.verification.required_evidence
MissionIR.verification.verification_profiles
MissionIR.verification.validators
```

Suggested `code_runtime` validators:

```json
{
  "validator_id": "V-code-runtime-skill-exists",
  "type": "file_exists",
  "inputs": {"path": "package/SKILL.md"}
}
```

```json
{
  "validator_id": "V-code-runtime-helper-executable",
  "type": "command",
  "inputs": {"cmd": "python3 package/scripts/codexarium.py --help"}
}
```

```json
{
  "validator_id": "V-code-runtime-manifest-schema",
  "type": "json_field_exists",
  "inputs": {"path": "package/skillfoundry.bundle.json", "field": "runtime_assets"}
}
```

Validator types must be declared by active verification profiles. If the
built-in `generic_local_verification` is not enough, provide a SkillFoundry
`ProfilePack` with a reusable verification profile.

### Tests

Add tests proving:

- generated MissionIR validates;
- generated MissionIR freezes deterministically;
- validators are declared by the active verification profile;
- unknown validator types fail closed;
- MissionForge core imports no SkillFoundry package.

## Phase 5: Bundle Validators

### Goal

Make deterministic package inspection enforce the product profile.

### Implementation

In `validators.py`, avoid one monolithic prompt-only validator. Dispatch by
matrix or manifest profile:

```python
def validate_skill_bundle(...):
    matrix = ProductAcceptanceMatrix.from_dict(...)
    if matrix.bundle_profile == BundleProfile.PROMPT_ONLY:
        return _validate_prompt_only_bundle(...)
    if matrix.bundle_profile == BundleProfile.CODE_RUNTIME:
        return _validate_code_runtime_bundle(...)
```

For `code_runtime`, inspect:

- required files exist;
- manifest schema and profile match;
- runtime assets listed in manifest exist;
- helper scripts are executable or runnable;
- schema files parse as JSON;
- package text contains no raw context markers;
- package text does not self-claim product-grade approval;
- package refs stay inside allowed scopes.

Keep reports refs-only. Do not embed package bodies.

### Tests

Add tests proving:

- valid package passes;
- missing runtime asset fails;
- bad manifest fails;
- raw context marker fails;
- self-grade claim fails;
- report is refs-only.

## Phase 6: ProductGradeGate And Registry

### Goal

Preserve ProductGradeGate authority for the new profile.

### Implementation

`evaluate_product_grade()` should remain profile-aware but not worker-trusting:

- verifier status must be `completed_verified`;
- bundle validation report must pass;
- package refs must match product contract targets;
- registry records candidate vs product-grade accurately;
- failed product-grade emits a repair packet.

Do not let a generated package claim product-grade status inside its own files.

### Tests

Add tests proving:

- valid profile package becomes `product_grade_registered`;
- failing profile package becomes candidate and emits repair packet;
- worker self-report does not override validators;
- registry entry remains refs-only.

## Phase 7: Runtime Facade And Dogfood

### Goal

Run the new profile through the same SkillFoundry product lifecycle.

### Implementation

`run_skillfoundry_bundle_build()` should not branch into a new runtime. It
should still:

```text
compile SkillFoundryRequest
  -> load MissionIR
  -> MissionRuntime.run()
  -> validate_skill_bundle()
  -> evaluate_product_grade()
  -> register_skill_bundle()
  -> write product report
```

The only profile-specific behavior should be in product contracts, compiler,
validators, and ProductGradeGate policy.

Live dogfood remains opt-in through the existing harness.

### Tests

Add tests proving:

- fixture runtime can produce a valid new-profile package;
- default runtime failure registers candidate, not product-grade;
- live dogfood can classify product-contract, worker, verifier, product-grade,
  registry, and completed outcomes.

## Phase 8: FrontDesk Integration

### Goal

Allow users to request the new profile naturally.

### Implementation

FrontDesk should not learn product internals. The SkillFoundry integration
should map FrontDesk authoring refs into a `SkillFoundryRequest` with the right
`desired_bundle_profile`.

For example:

```text
natural language:
  "Build Codexarium as a Codex skill with helper scripts and Rust sidecar"

SkillFoundry mapping:
  desired_bundle_profile = "code_runtime"
  source_refs = [
    "frontdesk/semantic_lock.json",
    "frontdesk/mission_brief.json",
    "frontdesk/mission_plan.json",
    ...
  ]
```

If the request needs runtime assets but the selected profile is `prompt_only`,
the integration should reject or route to clarification. Do not silently
downgrade product scope in production.

### Tests

Add tests proving:

- FrontDesk-generated refs can compile to the new profile;
- prompt-only downgrade is rejected when runtime assets are required;
- raw conversation stays provenance-only;
- SkillFoundry mapping lives under `integrations/skillfoundry`.

## Codexarium As Product Slice 2

Codexarium is the primary validation candidate for the implemented
`code_runtime` profile because it exposed the original prompt-only limit.

Recommended profile:

```text
BundleProfile.CODE_RUNTIME
```

Required product capabilities:

- Codex skill entrypoint;
- helper script package;
- Rust sidecar or runtime asset ref;
- JSON schemas;
- source/evidence boundary;
- Obsidian wiki write-scope contract;
- local health check contract;
- no raw Codex JSONL mirroring;
- no auth, SQLite, sandbox, shell snapshot, provider payload, API key, or
  secret leakage.

Expected package shape:

```text
package/SKILL.md
package/skillfoundry.bundle.json
package/README.md
package/scripts/codexarium.py
package/bin/codexarium-core-linux-x64
package/schemas/normalized_batch.schema.json
package/schemas/codex_output.schema.json
package/schemas/review_item.schema.json
package/schemas/source_registry.schema.json
```

Initial ProductGradeGate should validate:

- required refs exist;
- helper script has a `--help` or `doctor` path;
- sidecar has a documented health command or packaged binary ref;
- schemas parse as JSON;
- `SKILL.md` contains curator and secretary modes;
- `SKILL.md` states raw fallback policy;
- manifest declares runtime assets and schemas;
- package text has no raw context markers or self-grade claims;
- MissionForge verifier status is `completed_verified`.

This now compiles to MissionForge as generic MissionIR with package artifacts,
file validators, command validators, and source-boundary constraints. Product
specific Codexarium semantics should still be expressed through SkillFoundry
requests, package refs, validators, and ProductGradeGate policy, not through
MissionForge core branches.

## ProfilePack Use

Use a MissionForge `ProfilePack` only when a rule is reusable outside
SkillFoundry.

Good reusable profiles:

```text
packaged_runtime_assets
source_manifest_required
no_raw_context_material
command_health_check_required
schema_artifacts_required
```

Bad reusable profiles:

```text
codexarium_skill
customer_x_bundle
skillfoundry_code_runtime
```

Product-specific names can exist in SkillFoundry tests and product contracts,
but MissionForge ProfilePack names should stay capability-oriented.

## Acceptance Commands

Run profile-specific tests first:

```bash
PYTHONPATH=src:integrations/skillfoundry/src python3 -m unittest \
  integrations/skillfoundry/tests/test_product_contract.py \
  integrations/skillfoundry/tests/test_skill_bundle_validators.py \
  integrations/skillfoundry/tests/test_product_grade_gate.py \
  integrations/skillfoundry/tests/test_skillfoundry_runtime_facade.py
```

Run integration boundary gates:

```bash
./scripts/validate_integrations.sh skillfoundry
PYTHONPATH=src python3 -m unittest tests/test_adapter_import_boundaries.py
```

Run MissionForge regression gates:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

If live dogfood is touched, keep it opt-in and run deterministic tests by
default.

## Completion Definition

A new bundle profile is complete when:

- `SkillFoundryRequest` accepts it;
- `SkillProductContract` freezes deterministic product defaults for it;
- acceptance matrix lists all blocking product-grade checks;
- manifest validation is profile-aware;
- compiler emits valid MissionIR and frozen contract refs;
- bundle validators enforce the profile;
- ProductGradeGate distinguishes product-grade from candidate;
- runtime facade works without a new worker path;
- FrontDesk mapping can select the profile from natural language;
- integration validation passes;
- MissionForge core remains free of SkillFoundry product branches.

## Common Failure Modes

```text
New profile requires MissionForge runtime branch:
  Move behavior into MissionIR constraints, validators, ProfilePack data, or
  SkillFoundry ProductGradeGate.

Validator type is unknown:
  Add a reusable verification profile through ProfilePack or use an existing
  supported validator type.

ProductGradeGate trusts package text or worker report:
  Replace with deterministic validator evidence.

Generated manifest uses host absolute paths:
  Convert to package-relative refs or explicit external evidence refs.

FrontDesk silently chooses prompt_only for runtime bundle:
  Reject or clarify. Do not downgrade product scope in production.
```
