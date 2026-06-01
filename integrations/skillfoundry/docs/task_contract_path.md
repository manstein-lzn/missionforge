# SkillFoundry TaskContract Path

Last updated: 2026-05-31

Status: default external integration path for MissionForge's simplified agentic
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

This is the default path for new SkillFoundry-on-MissionForge work. The existing
MissionIR compiler remains available only as a compatibility and migration
comparison surface.

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

The main request-level API is:

```python
compile_skillfoundry_task_contract(request, workspace=...)
load_skillfoundry_task_contract(workspace, result)
```

The FrontDesk-level default API is:

```python
FrontDesk.compile_product_task_contract(session_ref, SkillFoundryFrontDeskIntegration(...))
```

`FrontDesk.compile_product(...)` and `compile_frontdesk_intent(...)` remain
legacy MissionIR compatibility APIs.

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

The integration tests run the compiled contract through `AgenticFlowRunner` in
two modes:

- an offline executor/judge fixture that proves the product-neutral contract
  shape;
- a faux Pi runtime executor boundary backed by `PiAgentRuntimeAdapter`, followed
  by an independent judge fixture.

Both paths keep artifacts under the declared workspace refs, require hard-check
evidence, and leave final acceptance to the judge packet/report path.

## Remaining Work

- connect real SkillFoundry hard-check/product-grade reports as hard-check refs;
- replace the in-process judge fixture with a PiWorker judge adapter when live
  judge credentials are available;
- add repair and revision handling on top of `JudgeReport.repair` and
  `JudgeReport.revision_required`;
- rerun value benchmarks with direct chat, runtime-only TaskContract flow, and
  full product flow.
