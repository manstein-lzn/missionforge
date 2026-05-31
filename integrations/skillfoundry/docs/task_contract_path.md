# SkillFoundry TaskContract Path

Last updated: 2026-05-31

Status: S5 external integration path for MissionForge's simplified agentic
runtime.

## Purpose

SkillFoundry now has a product-side compiler for the new MissionForge runtime
shape:

```text
FrontDeskIntentBundle
  -> SkillFoundryRequest
  -> SkillProductContract + ProductAcceptanceMatrix
  -> TaskContract + WorkspacePolicy + PermissionManifest
  -> AgenticFlowRunner
```

This path is additive. The existing MissionIR compiler remains available for
legacy tests and migration comparison, but new simplified-runtime work should
prefer the TaskContract path.

## Product Boundary

All SkillFoundry-specific meaning remains under `integrations/skillfoundry`.
MissionForge core receives only product-neutral data:

- `TaskContract`
- `WorkspacePolicy`
- `PermissionManifest`
- package artifact refs
- hard-check refs
- judge rubric content derived through generic projection

Core must not import `missionforge_skillfoundry`, and SkillFoundry package
requirements must not be added to `src/missionforge`.

## Compiler Surface

The main API is:

```python
compile_skillfoundry_task_contract(request, workspace=...)
load_skillfoundry_task_contract(workspace, result)
```

`compile_skillfoundry_task_contract` writes refs under:

```text
runs/{bundle_id}/
  contract/task_contract.json
  policy/workspace_policy.json
  policy/permission_manifest.json
  product_contract/skillfoundry_request.json
  product_contract/skill_product_contract.json
  product_contract/product_acceptance_matrix.json
  product_contract/task_contract_compile_report.json
```

The result is refs-only and does not require or emit `mission_ir_ref`.
All compile-result runtime artifact refs must be rooted under the declared
`run_workspace_ref`. `hard_check_refs` intentionally remain run-workspace
relative because `AgenticFlowRunner` consumes them inside the active
`RunWorkspace`.

Source refs from FrontDesk are treated as provenance first and worker-readable
inputs only when the referenced sanitized artifact already exists in the
product workspace. The compiler mirrors available source files into
`runs/{bundle_id}/...` and advertises only those materialized refs through
`TaskContract.source_refs`, `WorkspacePolicy.input_refs`, and
`PermissionManifest.readable_refs`. Missing source refs are recorded in
`product_contract/task_contract_compile_report.json` as
`unavailable_source_refs`; the sanitized SkillFoundry request remains the
authoritative product input.

## Agentic Flow Fixture

The integration tests run the compiled contract through `AgenticFlowRunner`
with offline executor and judge fakes:

- executor writes required `package/...` artifacts;
- hard-check evidence is written by the test fixture;
- judge accepts only from `JudgePacket` refs and passed hard checks;
- result, checkpoint, and ledger remain refs-first.

This proves the product can use the new path without changing MissionForge
core. It does not replace the future live PiWorker executor/judge integration.

## Remaining Work

- connect real SkillFoundry hard-check/product-grade reports as hard-check refs;
- add repair and revision handling on top of `JudgeReport.repair` and
  `JudgeReport.revision_required`;
- migrate the product runtime facade away from `MissionIR` after the new path
  has equivalent product-grade coverage;
- rerun value benchmarks with direct chat, runtime-only TaskContract flow, and
  full product flow.
