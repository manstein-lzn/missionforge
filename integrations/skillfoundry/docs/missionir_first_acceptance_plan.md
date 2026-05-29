# SkillFoundry MissionIR-First Acceptance Plan

Last updated: 2026-05-29

Status: development standard for the next SkillFoundry hardening phase.

## Purpose

This document defines how SkillFoundry must close the gap exposed by the
Codexarium live dogfood:

```text
MissionForge verifier passed, but SkillFoundry ProductGradeGate rejected the
bundle because a blocking product check was not inside the MissionIR verifier
loop.
```

The goal is not to add another verifier beside MissionForge. The goal is to
make SkillFoundry a better MissionIR compiler so that product-grade acceptance
is enforced by the MissionForge verify / repair / revision / continue loop.

## Product Principle

Users and product shells should not build isolated verification loops.

They should express the full acceptance contract as MissionIR, then let
MissionForge execute, verify, repair, revise, and close the mission.

SkillFoundry may own product semantics, but it must compile those semantics
into MissionForge-readable contracts.

## Hard Constraints

- Do not modify `src/missionforge/**`.
- Do not modify `workers/pi-agent-runtime/**`.
- Do not add Codexarium-specific branches.
- Do not weaken existing SkillFoundry product standards.
- Do not treat worker self-report as acceptance.
- Do not let a blocking SkillFoundry product check remain outside MissionIR
  unless it is explicitly represented as a MissionIR manual or reviewer gate.
- Do not keep two conflicting truths where MissionForge says complete while a
  later blocking SkillFoundry validator says product failure.

## Layering Decision

MissionForge remains the fixed substrate:

- MissionIR;
- frozen mission contracts;
- work-unit dispatch;
- PiWorker runtime;
- verifier closure;
- repair and revision primitives;
- refs-only evidence and runtime state.

SkillFoundry remains a product integration:

- bundle profiles;
- product contracts;
- acceptance matrix;
- manifest semantics;
- package artifact contracts;
- product registry policy;
- product reports;
- mapping from product acceptance rules into MissionIR validators.

MissionForge core must not learn about `prompt_only`, `code_runtime`,
Codexarium, bundle manifests, or package hygiene markers.

## Root Cause From Codexarium Dogfood

The Codexarium run produced a structurally complete `code_runtime` bundle.
MissionForge runtime verification passed because the MissionIR validators
checked required artifacts, manifest fields, and health commands.

SkillFoundry then ran `validate_skill_bundle()` and ProductGradeGate after
MissionForge runtime completion. That later product-level check failed on:

```text
SF-CODE-NO-RAW-CONTEXT
package exposes raw context marker: raw transcript
```

The rule was valid, but it was outside the MissionIR verifier loop. Therefore
MissionForge had no chance to repair the package before SkillFoundry registered
it as only `candidate_registered`.

## Target Architecture

The target flow is:

```text
SkillFoundryRequest
  -> SkillProductContract
  -> ProductAcceptanceMatrix
  -> AcceptanceCoverageReport
  -> MissionIR with product-grade validators
  -> MissionForge runtime
  -> MissionForge verifier / repair loop
  -> SkillFoundry ProductGradeGate audit
  -> product_grade_registered or candidate_registered
```

ProductGradeGate should not normally discover new blocking failures after
MissionForge verifier success. If it does, that is a coverage miss in the
SkillFoundry compiler.

## Phase 1: Acceptance Coverage

### Goal

Every blocking `ProductAcceptanceMatrix` item must have a declared MissionIR
coverage route.

### Required Coverage Routes

Each blocking check maps to exactly one of:

- `mission_ir_validator`: executable validator inside `MissionIR.verification`;
- `mission_ir_manual_gate`: manual or reviewer gate inside MissionIR;
- `mission_ir_profile`: reusable MissionForge profile expansion that creates
  validators or gates;
- `audit_only`: allowed only for non-blocking checks.

Blocking checks must not use `audit_only`.

### New Artifact

Generate:

```text
product_contract/acceptance_coverage_report.json
```

Recommended fields:

```json
{
  "schema_version": "missionforge_skillfoundry.acceptance_coverage_report.v1",
  "bundle_id": "codexarium",
  "bundle_profile": "code_runtime",
  "matrix_ref": "product_contract/product_acceptance_matrix.json",
  "mission_ref": "missions/codexarium.mission.json",
  "items": [
    {
      "check_id": "SF-CODE-NO-RAW-CONTEXT",
      "blocking": true,
      "coverage_route": "mission_ir_validator",
      "validator_ids": ["V-code-runtime-no-raw-context-001"],
      "covered": true
    }
  ],
  "blocking_coverage_passed": true
}
```

### Compile-Time Rule

`compile_skillfoundry_bundle()` must fail if any blocking acceptance item is
uncovered.

This fail-fast behavior belongs in `integrations/skillfoundry`, not in
MissionForge core.

## Phase 2: MissionIR Validator Expansion

### Goal

Move blocking bundle checks from post-runtime-only validation into MissionIR
validators whenever they can be evaluated by MissionForge's generic validator
language.

### Required Mappings

For both `prompt_only` and `code_runtime` profiles:

- artifact exists -> `file_exists`;
- manifest exists -> `file_exists`;
- manifest field exists -> `json_field_exists`;
- no raw context markers -> `file_contains` with `not_contains`;
- no self-grade claims -> `file_contains` with `not_contains`;
- external verification refs exist -> `json_field_exists` or `file_exists`.

For `code_runtime`:

- runtime assets exist -> `file_exists`;
- helper script health -> `command`;
- declared schemas parse -> `command` using `python3 -m json.tool` or another
  package-local JSON parse command;
- manifest runtime/data asset declarations -> `json_field_exists`;
- health command declaration -> `json_field_exists`.

### Forbidden Marker Policy

Forbidden-marker validators must be generated from generic marker lists, not
from bundle names or product-specific branches.

Current marker families include:

- raw prompt markers;
- raw transcript markers;
- provider payload markers;
- conversation log markers;
- self-grade / product-grade claim markers.

If a marker is too broad and blocks legitimate prohibition language, improve
the marker policy generically. Do not add a Codexarium exception.

## Phase 3: ProductGradeGate Role Change

### Goal

ProductGradeGate becomes a final audit and registry decision surface, not a
second independent blocking verifier.

### Required Behavior

After MissionForge verifier success:

- if ProductGradeGate passes, register `product_grade_registered`;
- if ProductGradeGate finds only non-blocking audit notes, still allow
  product-grade according to policy;
- if ProductGradeGate finds a blocking failure that should have been covered
  by MissionIR, classify it as `coverage_miss`;
- `coverage_miss` means SkillFoundry compiler/runtime integration is defective,
  not that the worker simply produced a normal candidate.

### Report Semantics

Product reports should distinguish:

- `mission_verifier_failed`;
- `product_grade_failed_after_covered_verification`;
- `coverage_miss`;
- `product_grade_registered`;
- `candidate_registered`.

This improves diagnosis without changing MissionForge.

## Phase 4: Repair Through MissionForge

### Goal

Product-grade repair must use MissionForge's existing repair loop.

### Desired Failure Location

If a generated bundle contains a forbidden raw-context marker, the failure
should happen during MissionForge verifier execution, not after the mission has
already closed.

Expected loop:

```text
PiWorker writes package
  -> MissionForge verifier detects forbidden marker
  -> MissionForge calls worker.with_repair(...)
  -> PiWorker edits package
  -> MissionForge verifier reruns
  -> mission closes only when validators pass
```

### SkillFoundry Runtime Rule

`run_skillfoundry_bundle_build()` should not invent a separate product repair
worker.

It should instead ensure that ProductAcceptanceMatrix blocking checks are in
MissionIR before `MissionRuntime.run()` starts.

## Phase 5: Tests

### Unit Tests

Add or update tests under `integrations/skillfoundry/tests/`:

- acceptance coverage report round trip;
- prompt-only matrix has complete MissionIR coverage;
- code-runtime matrix has complete MissionIR coverage;
- uncovered blocking item fails compile;
- non-blocking audit-only item is allowed;
- raw-context markers compile into MissionIR validators;
- self-grade markers compile into MissionIR validators;
- schema parse checks compile into MissionIR validators;
- ProductGradeGate classifies post-verifier blocking failures as
  `coverage_miss`.

### Regression Tests

The existing tests must continue to pass:

```bash
PYTHONPATH=src:integrations/skillfoundry/src:integrations/skillfoundry/tests \
python3 -m unittest \
  integrations.skillfoundry.tests.test_product_contract \
  integrations.skillfoundry.tests.test_prompt_only_compiler \
  integrations.skillfoundry.tests.test_skill_bundle_validators \
  integrations.skillfoundry.tests.test_product_grade_gate \
  integrations.skillfoundry.tests.test_skillfoundry_runtime_facade \
  integrations.skillfoundry.tests.test_skillfoundry_frontdesk_flow \
  integrations.skillfoundry.tests.test_skillfoundry_live_dogfood
```

### Import Boundary Test

Keep or extend the import boundary test:

- `src/missionforge/**` must not import `missionforge_skillfoundry`;
- `src/missionforge/**` must not contain product branches for SkillFoundry,
  Codexarium, or bundle profiles.

## Phase 6: Live Dogfood Re-Run

After implementation, rerun the same Codexarium FrontDesk dogfood without
manual artifact edits.

Acceptance:

- FrontDesk input remains non-technical pain text.
- SkillFoundry request remains generic `code_runtime`.
- no Codexarium-specific compiler branch exists.
- MissionIR contains validators for raw-context and self-grade forbidden
  markers.
- MissionForge verifier catches forbidden markers before ProductGradeGate.
- repair is attempted by MissionForge when `max_attempts > 1`.
- final registry status is `product_grade_registered`, or failure is clearly
  inside MissionForge verifier/repair with no post-runtime blocking surprise.

## Definition Of Done

This hardening phase is complete when:

- every blocking ProductAcceptanceMatrix check has coverage;
- uncovered blocking checks fail compile;
- ProductGradeGate no longer discovers normal blocking checks outside
  MissionIR;
- product-grade repair uses MissionForge's existing loop;
- SkillFoundry stays inside `integrations/skillfoundry`;
- MissionForge source remains unchanged;
- Codexarium dogfood either passes product-grade or fails inside the
  MissionForge verifier loop with actionable repair evidence.

## Non-Goals

- Do not make MissionForge understand SkillFoundry products.
- Do not add a new worker.
- Do not add Codexarium-specific shortcuts.
- Do not weaken raw-context or self-grade safety checks.
- Do not replace ProductGradeGate with worker claims.
- Do not claim product-grade if any blocking product check remains outside
  MissionIR coverage.

## Engineering Interpretation

The correct fix is not:

```text
MissionForge should magically know all downstream product standards.
```

The correct fix is:

```text
Downstream product standards must be compiled into MissionIR or rejected as
uncovered before runtime.
```

MissionForge remains the generic execution and verification substrate.
SkillFoundry becomes responsible for producing complete MissionIR contracts.
