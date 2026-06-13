# Implementation Status And Next Phases

Last updated: 2026-06-12

Status: current branch audit.

## Executive Position

MissionForge is now a TaskContract-native PiWorker delegation kernel.

The current first-class path is:

```text
ProductIntegration
  -> TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> PiWorker executor
  -> artifact refs + execution report
  -> independent Judge PiWorker
  -> accepted | repair | revision_required | rejected
  -> refs-first DecisionLedger + FinalPackage
```

The old runtime, harness, work-unit, fake-worker, and runner modules have been
removed from the active codebase.

## Current Status

| Area | Status |
| --- | --- |
| TaskContract/PiWorker kernel | Primary path, implemented and validated |
| Pi Agent runtime sidecar | Active PiWorker execution boundary |
| Executor/judge role separation | Implemented |
| Repair controller | Same-contract repair path implemented |
| Revision controller | Explicit TaskContract revision path implemented |
| Decision ledger and replay | Implemented |
| Workspace and permission primitives | Implemented |
| FrontDesk | Authoring surface; fails closed when required PiWorker-authored artifacts are unavailable |
| SkillFoundry | External product integration, TaskContract facade active |
| MissionIR | Compatibility/high-detail data shape only |
| Operator CLI | Inspect/diagnose/control/review/validate/frontdesk shell only |

## Removed Surfaces

These are no longer importable active modules:

- `missionforge.runner`
- `missionforge.runtime`
- `missionforge.work_unit`
- `missionforge.harness`
- `missionforge.workers`
- `missionforge.fake_worker`
- `missionforge.adapters.piworker`
- `missionforge.mission`

These are no longer active product/runtime facades:

- top-level CLI `run`;
- top-level CLI `resume`;
- JSONL RPC `run`;
- JSONL RPC `resume`;
- `run_skillfoundry_bundle_build(...)`.

## What Still Exists

Some older data modules remain because they preserve product-neutral invariants
or support FrontDesk/operator state:

- `missionforge.ir`;
- `missionforge.freeze`;
- `missionforge.state`;
- `missionforge.run_audit`;
- metrics and stores;
- steering proposal data contracts.

They are not the conceptual runtime center and should not be expanded into a
parallel execution path.

## Next Work

1. Keep docs and public examples centered on TaskContract/PiWorkerCall.
2. Keep product semantics in integrations and rubrics.
3. Strengthen live PiWorker validation without adding provider registries.
4. Add narrow tests for permission rejection, refs-only state, role separation,
   repair, and revision.
5. Remove or rewrite stale historical plans when they obscure the active system.
