# Module: Runtime

Status: retired.

The old `MissionIR -> MissionRuntime/RuntimeEngine -> WorkUnitContract` runtime
has been removed from the active codebase. MissionForge no longer provides
`missionforge.runner`, `missionforge.runtime`, `missionforge.work_unit`,
`missionforge.harness`, `missionforge.workers`, or `missionforge.fake_worker`.

The active runtime shape is:

```text
TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> AgenticFlowRunner
  -> PiWorker executor through PiWorkerCall
  -> independent Judge PiWorker through PiWorkerCall
  -> decision ledger + final package refs
```

Use these documents for current runtime behavior:

- `docs/USER_MANUAL.md`
- `docs/API_BOUNDARY.md`
- `docs/modules/agentic_flow.md`
- `docs/modules/piworker.md`

`MissionRun`, `PiWorkerAttempt`, `MetricStore`, and `MissionRunAudit` remain as
refs-only operator/state contracts where they are still used by inspection and
diagnosis surfaces. They are not a semantic runtime fallback and do not execute
missions.
