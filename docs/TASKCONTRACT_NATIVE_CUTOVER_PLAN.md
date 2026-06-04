# TaskContract-Native Runtime Cutover Plan

Last updated: 2026-06-03

Status: historical cutover plan, now subordinate to
`docs/PI_BASED_MINIMAL_KERNEL_DEVELOPMENT_PLAN.md`. Phases C1 and C2 are
implemented in the current tree through `PiAgentJudgeNode`,
`PiAgentExecutorNode`, `PiWorkerCall`, and the default TaskContract flow
preset. The remaining work is product default-path closure, repair/revision
runtime closure, DecisionLedger/FinalPackage replay, and legacy MissionIR/API
demotion.

## Goal

Make this path the default product runtime for new MissionForge work:

```text
FrontDeskIntentBundle
  -> ProductIntegration.compile_task_contract()
  -> frozen TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> Executor PiWorker
  -> hard checks
  -> independent Judge PiWorker
  -> accepted | repair | revision_required | rejected
  -> DecisionLedger
  -> FinalPackage | RepairBrief | RevisionRequest
```

## Non-Goals

- Do not delete legacy MissionIR runtime code until equivalent TaskContract path
  evidence exists.
- Do not add product-specific branches to `src/missionforge`.
- Do not make deterministic code infer user needs or semantic acceptance.
- Do not allow executor self-acceptance.
- Do not weaken a frozen contract through repair.
- Do not create a public multi-worker registry; PiWorker remains the single
  production worker direction.

## Current Baseline

Implemented and validated in the current tree:

- TaskContract, WorkspacePolicy, PermissionManifest, WorkerBrief, JudgeRubric.
- AgentExecutionPacket, AgentExecutionReport, JudgePacket, JudgeReport.
- PiWorkerCall as the shared refs-first invocation boundary before existing
  WorkUnitContract runtime projection.
- Content-hash binding between packets, projections, execution reports, and
  judge reports.
- `AgenticFlowRunner` offline executor/judge path with refs-only checkpoint and
  decision ledger.
- Pi Agent runtime with Node 22, permission-aware file tools, exact-command bash
  policy, environment filtering, secret redaction, symlink escape rejection, and
  live provider support.
- FrontDesk live PiWorker authoring opt-in through
  `FrontDesk.with_default_piworker(...)` and CLI `--use-default-piworker`.
- Live FrontDesk grill smoke through `codex_current` provider.
- SkillFoundry external TaskContract compiler and tests.
- Repair/revision artifact and controller records for TaskContract-native flow.

Remaining gaps are runtime closure, not architecture discovery.

## Cutover Principles

1. One lane at a time. Each phase must leave a validated, usable invariant.
2. Runtime code validates schemas, refs, hashes, permissions, and hard-check
   preconditions; PiWorker owns semantic execution or semantic judgment.
3. ProductIntegration owns product-specific rubric and final package content.
4. Every durable state record cites refs rather than embedding raw prompt,
   transcript, provider payload, stdout/stderr body, artifact body, or secrets.
5. Legacy MissionIR stays compatibility-only until new-path benchmarks and
   product flows prove equivalent or better guarantees.

## Phase C1: Live Judge PiWorker Lane

Status: implemented. Retained as the acceptance record for the judge lane.

Purpose: close independent semantic acceptance without changing the product
entrypoint or repair loop.

Deliverables:

- `PiAgentJudgeNode` or equivalent PiWorker-backed implementation of the
  existing `AgentJudgeNode` protocol.
- Bounded Judge work unit compiled from `JudgePacket`.
- Judge-visible refs limited to contract, rubric, execution packet/report,
  artifact refs, hard-check refs, and evidence refs.
- Judge writable refs limited to `JudgePacket.report_ref` and declared
  judge-authored repair/revision refs.
- Gated live smoke: `MISSIONFORGE_JUDGE_LIVE_SMOKE=1`.

Acceptance:

- Judge cannot accept failed/missing hard checks.
- Judge cannot accept incomplete execution.
- JudgeReport must match JudgePacket ref/hash/contract hash.
- Judge cannot mutate executor artifacts or runtime-owned refs.
- Secret and raw-provider payload leak checks pass.
- Full repository validation passes.

Exit criterion:

```text
AgenticFlowRunner(..., judge_node=PiWorker-backed judge)
```

can produce an independently judged accepted/rejected/repair/revision decision
for a small product-neutral TaskContract.

## Phase C2: PiWorker Executor + Judge AgenticFlow Preset

Status: implemented. The narrow public entrypoint is
`create_default_task_contract_flow`; adapter internals remain outside the
package-root API.

Purpose: provide a boring default TaskContract-native runtime assembly without
turning it into a worker marketplace.

Deliverables:

- Executor and Judge nodes project role packets through `PiWorkerCall` before
  converting to the current `WorkUnitContract` runtime shape.
- A small factory/helper that assembles:
  - `PiAgentExecutorNode`
  - `PiAgentJudgeNode`
  - `AgenticFlowRunner`
- Explicit opt-in from CLI/programmatic API for the TaskContract-native lane.
- No package-root re-export of adapter internals.

Acceptance:

- Offline tests cover faux executor + faux judge and mixed executor/judge
  failure paths.
- Live smoke covers executor and judge together on a tiny TaskContract.
- Import-boundary tests still prove MissionForge core does not expose a provider
  zoo.

Exit criterion:

A caller with a frozen TaskContract can run the new lane without manually wiring
all nodes.

## Phase C3: ProductIntegration Default Runtime Path

Purpose: make external product integrations use TaskContract-native runtime by
default for new work.

Deliverables:

- FrontDesk/ProductIntegration path returns or persists TaskContract as the
  primary execution contract.
- SkillFoundry full-flow fixture runs through TaskContract-native executor and
  judge lane.
- MissionIR compiler remains compatibility/migration code.

Acceptance:

- SkillFoundry tests prove product-specific semantics remain outside
  `src/missionforge`.
- FrontDesk compile + SkillFoundry TaskContract + AgenticFlow run produces
  accepted/repair/revision decision.
- No new product strings or branches appear in MissionForge core.

Exit criterion:

New product work can use:

```text
FrontDeskIntentBundle -> ProductIntegration -> TaskContract -> AgenticFlow
```

without converting through MissionIR.

## Phase C4: Repair Loop Runtime Closure

Purpose: turn durable repair records into an executable same-contract retry
without weakening acceptance.

Deliverables:

- Repair ticket/directive consumed by the executor lane.
- Repair execution packet generated from the same TaskContract hash.
- Rejudge after repair.
- Ledger events for repair requested, repair execution started/completed, and
  repair judged.

Acceptance:

- Repair cannot change contract hash or acceptance criteria.
- Stale or drifted repair inputs fail closed.
- Repaired artifact is judged independently.
- Failed repair remains visible as repair/rejected, not accepted by executor
  claim.

Exit criterion:

A judge repair decision can automatically produce the next bounded executor
attempt and return to judge.

## Phase C5: Revision Runtime Closure

Purpose: make contract changes explicit, auditable, and active only after proper
authority.

Deliverables:

- Revision-required JudgeReport creates RevisionPendingRecord.
- Approved TaskRevisionDecision plus revised TaskContract writes
  TaskContractRevision.
- Active runtime authority switches only to the frozen revised contract.
- Rejected revision routes back to repair/rejected/operator state.

Acceptance:

- Wrong authority fails closed.
- Revised contract hash differs and old hash remains ledgered.
- No repair path can silently apply a revision.
- Resume/retry uses active contract authority, not stale checkpoint state.

Exit criterion:

Revision-required work can safely continue under a new frozen TaskContract.

## Phase C6: DecisionLedger And FinalPackage

Purpose: create one replayable product-neutral audit spine and final handoff
surface.

Deliverables:

- Named DecisionLedger wrapper for TaskContract-native flow.
- Required event kinds:
  - contract_frozen
  - worker_packet_issued
  - execution_report_recorded
  - hard_checks_recorded
  - judge_packet_issued
  - judge_report_recorded
  - repair_requested
  - revision_requested
  - revision_applied
  - final_package_emitted
- FinalPackage shell with product-owned payload refs.

Acceptance:

- Ledger entries are append-only refs-first JSON objects.
- Replay from ledger refs can locate contract, packets, reports, artifacts,
  repair/revision records, metrics, and final package.
- FinalPackage does not embed product artifact bodies unless the product
  integration explicitly owns that packaging artifact.

Exit criterion:

Operator can inspect one ledger/package surface for the whole TaskContract run.

## Phase C7: Legacy Runtime Demotion

Purpose: reduce confusion after new-path equivalence evidence exists.

Deliverables:

- Documentation marks MissionIR runtime as legacy/high-detail compatibility for
  new product work.
- CLI/API defaults prefer TaskContract-native product flow where available.
- Legacy tests remain only where they preserve invariants not yet covered by the
  new path.

Acceptance:

- Validation passes.
- Benchmarks still run.
- External integrations do not break.
- No useful evidence, metric, permission, or revision invariant is lost.

Exit criterion:

New maintainers see one default product path and one documented compatibility
path.

## Phase C8: Optional Value Comparison

Purpose: prove what the added structure buys after the kernel is stable,
without over-claiming speed or cost wins. This is not a request to restore the
removed value_benchmark lane into core.

Deliverables:

- Direct PiWorker baseline.
- WorkerBrief-only TaskContract runtime lane.
- Full FrontDesk + ProductIntegration + Executor + Judge lane.
- Repair-required and revision-required cases.
- Readiness reports for hidden checks, pricing, provider config, and fixture
  availability.

Acceptance:

- Report separates provider-reported cost from pricing projection.
- Report distinguishes deterministic hard checks from semantic Judge results.
- Claims are suppressed when readiness is unavailable or review is waived.
- Product boundary contamination check remains clean.

Exit criterion:

MissionForge can state, with evidence, which reliability/audit/repair benefits
it buys relative to direct PiWorker chat.

## Immediate Next Task

Implement the remaining convergence work from
`docs/PI_BASED_MINIMAL_KERNEL_DEVELOPMENT_PLAN.md`, starting with the default
TaskContract product path, repair/revision runtime closure, and
DecisionLedger/FinalPackage replay.

## Completion Definition For Cutover

The cutover is complete when a new product task can run end to end through:

```text
FrontDesk live authoring
  -> ProductIntegration TaskContract compilation
  -> TaskContract-native Executor PiWorker
  -> independent Judge PiWorker
  -> repair/revision/final package as required
  -> DecisionLedger replay
```

with validation evidence and without using MissionIR as the default execution
authority.
