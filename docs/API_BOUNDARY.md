# API Boundary

Last updated: 2026-06-13

Status: `reference`

## Goal

MissionForge is a Python package for composing code and model calls. The root
package must feel like a small set of primitives, not a catalog of runtime
internals.

The package root is the stable programmer kernel:

```python
from missionforge import TaskContract, WorkspacePolicy, PermissionManifest
from missionforge import PiWorkerCall, run_piworker_call
```

Everything more specialized is still available, but from an explicit module:

- `missionforge.agentic_flow` for the bundled executor -> judge flow;
- `missionforge.agent_packets` for flow packets and reports;
- `missionforge.agentic_repair*` for repair and revision governance;
- `missionforge.frontdesk` for requirements discovery;
- `missionforge.adapters.*` for runtime adapters;
- `missionforge.profiles`, `missionforge.verifier`, and stores for supporting
  infrastructure.

## Root Programmer Kernel

The package root exports only these categories.

Task authority:

- `TaskContract`
- `TaskContractRevision`
- `ContractClause`

Workspace and permission authority:

- `WorkspacePolicy`
- `PermissionManifest`
- `NetworkPolicy`

Role projections:

- `WorkerBrief`
- `JudgeRubric`
- `build_worker_brief`
- `build_judge_rubric`
- `project_worker_brief`
- `project_judge_rubric`

One bounded intelligence RPC:

- `PiWorkerCall`
- `PiWorkerCallRole`
- `PiWorkerCallResult`
- `PiWorkerCallResultStatus`
- `PiWorkerCallAdapter`
- `create_default_piworker_adapter`
- `run_piworker_call`

Convenience assembly:

- `TaskContractFlowPreset`
- `create_default_task_contract_flow`

Refs and evidence:

- `Ref`
- `ArtifactRef`
- `EvidenceRef`
- `ContextSummaryArtifact`
- `ContextSummaryKind`
- `ContextSummarySource`
- `EvidenceLedger`
- `EvidenceRecord`
- `FileEvidenceStore`
- `InMemoryEvidenceStore`
- `FinalPackage`
- `replay_decision_ledger`

Product integration protocols:

- `ProductIntegration`
- `TaskContractProductIntegration`
- `ProductTaskContractCompileResult`
- `ProductCompileStatus`

Shared validation helpers:

- `ContractValidationError`
- `MissionForgeError`
- `stable_json_hash`
- `validate_ref`
- `assert_refs_only_payload`

## Why The Root Is Small

The root API should let a programmer treat a model as a bounded Python package
call:

```text
code creates TaskContract + permissions
code creates PiWorkerCall
code runs the call
code inspects refs-first result
code decides what to do next
```

MissionForge does not force a product methodology. A programmer may build a
single call, a judge loop, a repair loop, a product shell, or a larger
distributed system from the same primitives.

## Explicit Advanced Modules

Use module imports when you want a higher-level composition.

`missionforge.agentic_flow`
: Bundled TaskContract executor -> judge lane. Exposes `AgenticFlowRunner`,
  `AgenticFlowStatus`, `AgentWorkspace`, and flow refs.

`missionforge.agent_packets`
: Role-separated execution and judge packet/report contracts.

`missionforge.agentic_repair` and controller modules
: Same-contract repair and explicit TaskContract revision governance.

`missionforge.frontdesk`
: High-intelligence requirement discovery and intent authoring. FrontDesk
  output is not task truth; executable authority still comes from
  `TaskContract`.

`missionforge.adapters.pi_agent_runtime`
: The Pi Agent sidecar adapter, runtime config, executor node, and judge node.
  Adapter internals are intentionally not exported from root.

`missionforge.context_summary`
: Explicit PiWorker/Judge-authored semantic context summary artifact schemas.
  These are exported from the root because they are product-neutral evidence
  contracts, not runtime internals.

`missionforge.profiles`, `missionforge.verification`, `missionforge.verifier`
: Compatibility and supporting validation infrastructure. These are useful, but
  not part of the minimal model-call kernel.

## Forbidden Root Exports

The root must not export product-specific names, adapter internals, old runtime
surfaces, FrontDesk objects, packet internals, repair/revision controller
records, profile registries, verifiers, stores, or metric projections by
default.

Tests enforce this boundary in `tests/test_public_api_boundary.py`.

## Product Integration Rule

Product integrations should depend on MissionForge in this order:

1. Use product code, UI, config, FrontDesk, source refs, or external systems to
   gather product facts.
2. Compile those facts into `TaskContract`, `WorkspacePolicy`, and
   `PermissionManifest`.
3. Use `PiWorkerCall` and `run_piworker_call(...)` directly, or assemble a
   higher-level flow from `missionforge.agentic_flow`.
4. Keep product hard checks and product gates outside `src/missionforge`.
5. Record refs-only evidence, results, packages, repair records, and revision
   records.

If a product needs a branch in `src/missionforge`, the product boundary has
failed.
