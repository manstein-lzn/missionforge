# Development Protocol

MissionForge is a formal architecture project. Implementation follows the
documentation, not the other way around.

## Docs-First

Before a module is implemented, it must have a module document under
`docs/modules/`.

Each module document must include:

- goal
- scope
- non-goals
- current status
- public contracts
- invariants
- dependencies
- verification strategy
- open questions

## Docs-Last

Before work on a module is considered complete, its module document must be
updated with:

- implemented behavior
- changed contracts
- known gaps
- verification evidence
- next design questions

## Worker Scope

MissionForge is PiWorker-only for the first formal design cycle.

The PiWorker direction is inspired by the PI GitHub project and by the current
SkillFoundry PiWorker adapter. PI is MIT-licensed; any future copied or adapted
PI source must retain required attribution.

Out of scope for now:

- CodexWorker as a first-class worker
- multi-worker abstraction
- provider-specific control logic in core runtime
- LangGraph as a required internal runtime

## Completion Standard

A change is not complete unless:

- module docs match behavior
- tests or verification notes exist
- task-specific names do not enter core code
- runtime behavior is driven by Mission IR, profiles, validators, and evidence
  records
