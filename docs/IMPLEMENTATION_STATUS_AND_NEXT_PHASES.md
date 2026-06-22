# Implementation Status And Next Phases

Last updated: 2026-06-12

Status: current branch audit after core slimming.

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
| FrontDesk | Frozen outside active core under `frozen/frontdesk/`; pending TaskContract-native rewrite |
| DeepResearch | External product integration, TaskContract facade active |
| MissionIR/Profile/Verifier | Removed from active core |
| Operator CLI/RPC/TUI | Removed from active core |

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
- `missionforge.ir`
- `missionforge.freeze`
- `missionforge.profiles`
- `missionforge.verification`
- `missionforge.verifier`
- `missionforge.validators`
- `missionforge.state`
- `missionforge.json_store`
- `missionforge.stores`
- `missionforge.metrics`
- `missionforge.metric_store`
- `missionforge.run_audit`
- `missionforge.tui`
- `missionforge.adapters.cli`
- `missionforge.adapters.rpc`
- `missionforge.adapters.observation`

These are no longer active product/runtime facades:

- top-level CLI `run`;
- top-level CLI `resume`;
- JSONL RPC `run`;
- JSONL RPC `resume`;
- deleted product-specific bundle-build facades.

## What Still Exists

The active package now keeps only product-neutral kernel primitives, PiWorker
boundaries, runtime adapter code, extension grants, permission/sandbox
contracts, progress streaming, evidence refs, product integration contracts,
and the compact kernel flow API.

Historical FrontDesk source and tests remain in `frozen/frontdesk/` as a
non-active tool snapshot. They are not imported by `src/missionforge` and are
not part of the active validation suite.

## Next Work

1. Keep docs and public examples centered on TaskContract/PiWorkerCall.
2. Keep product semantics in integrations and rubrics.
3. Strengthen live PiWorker validation without adding provider registries.
4. Add narrow tests for permission rejection, refs-only state, role separation,
   repair, and revision.
5. Remove or rewrite stale historical plans when they obscure the active system.
