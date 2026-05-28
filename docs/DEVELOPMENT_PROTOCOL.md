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

Before starting an implementation phase, read:

- `docs/DEVELOPMENT_GOAL_PROTOCOL.md`
- `docs/COMPONENT_DEVELOPMENT_PLAN.md`
- `docs/COMPONENT_ACCEPTANCE_MATRIX.md`

The phase objective, public contracts, focused tests, and docs-last targets
must be clear before code changes begin.

## Docs-Last

Before work on a module is considered complete, its module document must be
updated with:

- implemented behavior
- changed contracts
- known gaps
- verification evidence
- next design questions

The relevant phase checklist in `docs/COMPONENT_DEVELOPMENT_PLAN.md` and
acceptance checks in `docs/COMPONENT_ACCEPTANCE_MATRIX.md` should still match
the implemented behavior. If implementation reveals that a phase plan is wrong,
update the plan as an explicit redesign rather than silently drifting.

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

## Controlled Steering Scope

MissionForge should design controlled steering before enabling live LLM
proposal nodes.

Default runtime behavior must remain deterministic/offline. LLM-backed nodes,
when added, may propose, interpret, or review, but they must not:

- commit durable runtime state
- mutate a frozen mission contract
- expand authority
- verify truth
- close a mission

Proposal validation, evidence reliability, reviewer independence, and safe-point
control handling must be tested with deterministic fixtures before any live LLM
provider is used.

The first runtime slice is deterministic by construction: it may use a
deterministic proposal provider and fake worker, but verifier status remains the
only completion authority. Fake worker output and proposal confidence are
execution evidence, not acceptance.

## Completion Standard

A change is not complete unless:

- module docs match behavior
- tests or verification notes exist
- task-specific names do not enter core code
- runtime behavior is driven by Mission IR, profiles, validators, controlled
  steering records, and evidence records
- LLM or worker claims are not treated as acceptance evidence
