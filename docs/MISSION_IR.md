# Mission IR

Status: compatibility data shape.

`MissionIR` is a high-detail, domain-neutral mission description retained for
older mapping paths, profile/freeze tests, and migration tooling. It is not the
first-class execution contract for new MissionForge work.

New product work should compile to:

```text
TaskContract
  + WorkspacePolicy
  + PermissionManifest
  + JudgeRubric
```

and then execute through:

```text
PiWorkerCall -> PiWorkerCallResult -> independent Judge PiWorker
```

## What Remains Useful

The old MissionIR family still captures several durable principles:

- raw chat is not operational task truth;
- task authority must be structured and reviewable;
- constraints, assumptions, non-goals, risks, and evidence requirements should be
  explicit;
- repair must not silently weaken acceptance;
- task truth changes require explicit revision.

Those principles now live on the active path through `TaskContract`,
`WorkerBrief`, `JudgeRubric`, repair records, revision records, and the decision
ledger.

## Boundary

Use `missionforge.ir` only when maintaining older MissionIR-compatible data or
tests. Do not introduce new execution paths that route product work through a
MissionIR runtime facade.

MissionIR may be translated into a TaskContract by an external integration or
migration tool, but that translation is compatibility work, not the normal
programmer-facing API.
