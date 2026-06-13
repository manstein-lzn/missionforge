# MissionForge Next Development Plan

Last updated: 2026-06-12

Status: active post-legacy-cleanup plan.

## Goal

Make the TaskContract/PiWorker kernel usable by programmers without requiring
source archaeology.

MissionForge should expose a small set of orthogonal primitives:

```text
ProductIntegration
  -> TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> PiWorkerCall executor
  -> PiWorkerCall judge
  -> DecisionLedger + FinalPackage
```

## Phase 1: Stabilize The Clean Cut

- Keep old runtime, harness, work-unit, runner, fake-worker, and old PiWorker
  adapter modules deleted.
- Keep top-level CLI/RPC `run` and `resume` deleted.
- Keep SkillFoundry on `run_skillfoundry_task_contract_bundle_build(...)`.
- Keep README, manual, primitive reference, architecture, and API boundary aligned
  with TaskContract/PiWorker.

Exit condition: scans show no active imports or public examples for the retired
runtime path.

## Phase 2: Documentation As Product Surface

- Treat `docs/USER_MANUAL.md` as the complete programmer manual.
- Keep `docs/PRIMITIVE_REFERENCE.md` precise enough to implement against.
- Keep `docs/COOKBOOK.md` focused on composition patterns, not product
  methodology.
- Keep examples runnable from public imports.
- Add focused tests for examples that the manual promises.

Exit condition: a programmer can build a standalone product integration from
docs and public primitives without copying SkillFoundry internals.

## Phase 3: FrontDesk To TaskContract

- Keep FrontDesk as requirements discovery, not execution.
- Fail closed when required PiWorker-authored authoring artifacts are missing.
- Prefer ProductIntegration compilation to TaskContract.
- Keep MissionIR mapping only as compatibility data, not the normal handoff.

Exit condition: the default FrontDesk handoff is TaskContract-native.

## Phase 4: Live PiWorker Confidence

- Keep faux provider as the default CI lane.
- Run live smoke tests only when explicitly opted in.
- Validate refs, permissions, role separation, and secret exclusion around live
  calls.
- Convert repeated live failures into deterministic boundary tests.

Exit condition: live validation increases confidence without adding provider
registry complexity.

## Phase 5: Product Integration Pressure

- Keep SkillFoundry as an external product proof.
- Preserve product-grade checks under `integrations/skillfoundry`.
- Add a second small example integration only if it exposes missing primitives,
  not to create product methodology in core.

Exit condition: integrations exercise the primitives without changing the core
architecture.

## Required Checks

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src:integrations/skillfoundry/src python3 -m unittest discover -s integrations/skillfoundry/tests
npm test --prefix workers/pi-agent-runtime
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
./scripts/validate_integrations.sh skillfoundry
git diff --check
```
