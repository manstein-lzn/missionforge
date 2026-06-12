# Migration Guide

This guide helps move older MissionIR / legacy-runtime code to the
TaskContract-native PiWorker path.

## Old Shape

```text
MissionIR -> MissionRuntime -> MissionResult
```

## New Default Shape

```text
TaskContract -> WorkspacePolicy -> PermissionManifest
  -> AgenticFlowRunner
  -> PiWorker executor
  -> independent judge
  -> refs-first result
```

## Migration Steps

1. Move product-specific meaning into an integration package.
2. Compile that meaning into `TaskContract`, `WorkspacePolicy`, and
   `PermissionManifest`.
3. Use `create_default_task_contract_flow(...)` for the normal execution path.
4. Keep MissionIR only where compatibility still matters.
5. Move acceptance decisions to the judge path.

## What Not To Do

- do not branch on product names in `src/missionforge`
- do not let worker output accept itself
- do not treat runtime evidence as the same thing as acceptance
- do not use raw chat as durable task truth

## SkillFoundry Example

SkillFoundry is the external product integration example. It compiles a
product request into TaskContract-native artifacts before running the default
PiWorker lane.

