# API Boundary

Status: `reference`

MissionForge root is the programmer kernel. It should expose primitives, not
old product flows or adapter internals.

MissionForge is distributed as the AI-in-Code infrastructure package, not as a
core-only SDK. The default Python package carries the product-neutral control
plane and the packaged PiAgent runtime assets. Platform-specific OS isolation
backends remain explicit capabilities: Linux `bubblewrap`/`seccomp` sandboxing
may be required by a task, but its absence must not make `import missionforge`
fail or create implicit filesystem side effects.

## Root Exports

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

PiWorker invocation:

- `PiWorkerCall`
- `PiWorkerCallBatch`
- `PiWorkerCallBatchResult`
- `PiWorkerCallRole`
- `PiWorkerCallResult`
- `PiWorkerCallResultStatus`
- `PiWorkerCallAdapter`
- `create_default_piworker_adapter`
- `run_piworker_call`
- `run_piworker_call_batch`

Packaged PiAgent runtime preflight:

- `PiAgentRuntimeCapability`
- `PiAgentRuntimeCapabilityStatus`
- `PiAgentRuntimePreflightReport`
- `default_pi_agent_runtime_command`
- `find_pi_agent_runtime_dir`
- `preflight_pi_agent_runtime`

Evidence, extensions, sandbox, and progress primitives may be exported when
they are product-neutral and refs-first.

## Explicit Modules

- `missionforge.adapters.pi_agent_runtime`: Pi sidecar adapter internals.
- `missionforge.pi_agent_runtime_bundle`: packaged runtime discovery,
  materialization, and host capability preflight.
- `missionforge.kernel`: compact flow-building API for product integrations.
- `missionforge.decision_ledger`: refs-first ledger/package primitives retained
  as product-neutral evidence contracts.

## Frozen Legacy Tools

FrontDesk has been moved out of the active `missionforge` package and frozen
under `frozen/frontdesk/`. It is retained as source material for a later
TaskContract-native rewrite, but it no longer constrains core imports or public
API shape.

## Forbidden Root Exports

The root must not export product-specific names, adapter internals, legacy
flow factories, old packet layers, repair/revision controller records, profile
registries, verifiers, stores, or metric projections by default.

Tests enforce this in `tests/test_public_api_boundary.py`.

## Product Integration Rule

Product integrations should:

1. Gather product facts outside core.
2. Compile facts into `TaskContract`, `WorkspacePolicy`, and
   `PermissionManifest`.
3. Invoke PiWorker through `PiWorkerCall` / `run_piworker_call(...)` or the
   compact `missionforge.kernel` API.
4. Keep product hard checks, rubrics, and semantic judgment outside
   `src/missionforge`.
5. Record refs-only evidence and final product packages.

If a product needs a branch in `src/missionforge`, the product boundary has
failed.
