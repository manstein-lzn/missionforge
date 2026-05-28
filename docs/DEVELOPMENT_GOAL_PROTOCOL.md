# Development Goal Protocol

This document is the operating contract for driving MissionForge implementation
through a long-running `/goal` session.

It is inspired by MetaLoop's lightweight protocol, but it is MissionForge
documentation, not a dependency on MetaLoop runtime state. The purpose is to
make implementation resumable, evidence-driven, and resistant to scope drift.

## Goal Contract

Goal:

```text
Build MissionForge from design documents into a deterministic, evidence-first
mission runtime kernel before adding live LLM steering, PiWorker integration,
host adapters, or SkillFoundry product adapters.
```

Success:

- the six development phases in `docs/COMPONENT_DEVELOPMENT_PLAN.md` are
  completed in order or explicitly revised
- each phase has passing focused tests
- every implemented module has docs-last updates
- runtime behavior remains product-neutral
- completion and repair decisions are based on structured contracts, evidence,
  validators, and proposal validation records

Non-goals for the initial development goal:

- no live LLM provider integration
- no real PiWorker execution
- no LangGraph adapter
- no HTTP service
- no SkillFoundry adapter
- no SQLite ledger unless a phase explicitly revises the plan
- no product-specific mission branches

Constraints:

- default tests must stay deterministic and offline
- worker and LLM self-report are never acceptance evidence
- frozen contracts cannot be silently weakened after execution
- host adapters must not enter core runtime
- provider-specific telemetry is evidence or metrics, not control logic
- every phase must leave a clear resume point

## Protocol Shape

Use `single_node` for the first implementation goal.

Rationale:

- all work is in one repository
- no separate workspaces are required
- module boundaries are contract boundaries, not separate agents yet
- a single `/goal` can drive the sequence as long as phase checkpoints are
  explicit

Do not introduce routable work units until a real need appears, such as parallel
workspace isolation, independent reviewer implementation, or separate PiWorker
adapter development.

## Six Control Gates

### 1. Design Gate

Before implementing a phase, the agent must state:

- phase objective
- files expected to change
- public contracts introduced or changed
- tests to add or update
- docs to update after behavior changes
- risks that would force repair or redesign

Design is not considered complete if it only names a module. It must name the
contracts and verification evidence for the phase.

### 2. State Checkpoint

At the end of every phase, update the relevant module docs with:

- implemented behavior
- changed contracts
- known gaps
- verification command and result
- next design questions

If a phase is interrupted, the next agent should be able to resume from:

- `git status --short`
- the latest test output
- the phase checklist in `docs/COMPONENT_DEVELOPMENT_PLAN.md`
- module docs under `docs/modules/`

### 3. Verification Gate

Every phase must run:

```bash
git diff --check
PYTHONPATH=src python3 -m unittest discover -s tests
```

Additional focused tests should be added per phase. A phase cannot be marked
complete because files were created; it is complete only when its locked
acceptance checks pass or a documented review gate remains.

### 4. Adaptive Loop

After any failed or partial attempt, record the next decision in the final
response or phase notes using this vocabulary:

- `complete`: phase acceptance is satisfied
- `continue`: same phase remains valid and another attempt is justified
- `repair`: implementation is defective but phase contract remains valid
- `redesign`: the phase contract, schema, or acceptance is wrong
- `pivot`: the goal remains valid but the implementation route should change
- `review`: independent judgment is needed before continuing
- `stop`: continuing is not justified under current constraints
- `escalate`: blocked by permission, resource, or external dependency

Mechanical retry is not acceptable. The next attempt must be grounded in the
failed evidence.

### 5. Control Point

If the user changes direction, treat it as an explicit control request:

- `halt`: stop the current phase and summarize status
- `inject_fact`: incorporate a new fact into phase design
- `revise_contract_request`: revise the phase acceptance or order
- `resource_approval`: allow a previously out-of-scope resource

Do not silently change phase acceptance after seeing test results.

### 6. Observation Surface

Every final response for a phase should include:

- what changed
- which phase checklist items are complete
- verification commands and results
- known gaps
- next recommended phase

Keep this concise. The durable truth belongs in repository docs and tests.

## Phase Status Vocabulary

Use these statuses in docs or handoff notes:

- `not_started`
- `in_design`
- `in_progress`
- `repair_required`
- `redesign_required`
- `review_required`
- `completed_verified`
- `blocked`

`completed_verified` requires passing tests and docs-last updates.

## Review Policy

Use `review_required` when:

- a validator or schema choice affects multiple future phases
- a manual quality judgment is needed
- a live LLM or PiWorker boundary is being considered
- a contract change would weaken previous acceptance
- a product-specific branch is tempting

Reviewer approval cannot replace failed executable tests. It can only resolve a
manual or strategic gate.

## Completion Standard

The development goal is complete when:

- all phases in `docs/COMPONENT_DEVELOPMENT_PLAN.md` through the runtime
  vertical slice are `completed_verified`
- all default tests pass
- module docs match implementation
- the runtime remains deterministic/offline by default
- no MissionForge core module imports host, SkillFoundry, LangGraph, or live LLM
  provider code

PiWorker and SkillFoundry adapters may be a follow-on goal if the deterministic
runtime kernel is complete.

Follow-on adapter work should use `docs/FOLLOW_ON_GOALS.md` and should be split
by trust boundary. Do not combine PiWorker, SkillFoundry, host adapters, live
LLM steering, LangGraph, or HTTP service work in a single goal unless a later
design revision explicitly justifies that merge.
