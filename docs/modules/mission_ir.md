# Module: Mission IR

Status: compatibility data module.

`missionforge.ir` keeps the older high-detail MissionIR dataclasses available
for migration and generic mapping code. It is not the active execution API.

## Active Replacement

New code should prefer:

- `TaskContract`;
- `WorkspacePolicy`;
- `PermissionManifest`;
- `WorkerBrief`;
- `JudgeRubric`;
- `PiWorkerCall`;
- `AgenticFlowRunner`.

## Invariants Preserved

- Raw chat is not task truth.
- Structured contracts carry authority.
- Stable refs and hashes matter.
- Repair does not change task authority.
- Revision is explicit when task authority changes.

## Non-Goals

- no MissionIR runtime facade;
- no deterministic runtime orchestration around MissionIR;
- no work-unit projection path;
- no product-specific behavior in `src/missionforge`.
