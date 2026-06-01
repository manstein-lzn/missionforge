# Agentic Flow

Last updated: 2026-05-31

Status: minimal offline implementation surface for the simplified
TaskContract-based runtime path.

## Purpose

`missionforge.agentic_flow` is the first product-neutral composition layer for
the simplified MissionForge architecture.

It does not understand product meaning, invoke a live PiWorker, perform
semantic acceptance, or repair artifacts. It wires the hard parts together:

```text
TaskContract
  -> WorkerBrief + JudgeRubric
  -> RunWorkspace + PermissionManifest
  -> AgentExecutionPacket
  -> AgentExecutionReport
  -> JudgePacket
  -> JudgeReport
  -> refs-only checkpoint and decision ledger
```

This module exists so later live PiWorker work has a small, tested contract
surface. It also gives tests and benchmarks a clean runtime-only path that is
not contaminated by FrontDesk or product-specific behavior.

## Design Boundaries

- The frozen `TaskContract` is the durable obligation.
- `WorkerBrief` is projected with `project_worker_brief`; fields are not
  hand-copied.
- `JudgeRubric` is projected with `project_judge_rubric`.
- `AgentExecutionPacket`, `AgentExecutionReport`, `JudgePacket`, and
  `JudgeReport` are validated with the existing cross-object validators from
  `agent_packets.py`.
- Execution packets content-bind the worker brief, workspace policy, and
  permission manifest hashes.
- Execution reports and judge reports are stamped with the packet hash they
  answer, and judge packets content-bind the execution packet/report hashes.
- Executor output can never grant final acceptance.
- Judge acceptance requires passed hard checks and completed execution.
- Passed hard checks must cite explicit hard-check refs.
- Repair and revision decisions must point to structured judge-authored
  artifacts that are validated against the judge packet and report before the
  run result is finalized.
- Executor-produced artifacts must be under declared artifact roots and worker
  writable refs.
- Executor evidence, metrics, repair, and revision refs must be worker-writable.
- Judge rationale, repair, and revision refs must be judge-writable.
- Executor and judge nodes receive scoped workspace facades that deny writes to
  runtime-owned contract, packet, report, ledger, and checkpoint refs.
- Hard-check refs are treated as runtime-owned evidence and are denied for
  executor/judge writes after existence is verified.
- Hard-check refs must exist before a `passed` hard-check status can support
  acceptance.
- Accepted runs must cover every required artifact ref, and those artifacts
  must exist in the run workspace.
- Result, checkpoint, and ledger payloads use refs-first shapes and reject raw
  prompts, transcripts, provider payloads, stdout/stderr bodies, artifact
  bodies, and secrets through `assert_refs_only_payload`.

## Non-Goals

- No live PiWorker invocation.
- No provider registry.
- No product-specific fake worker behavior.
- No Python semantic judge.
- No code-based user-need inference.
- No contract weakening or automatic revision approval.
- No replacement of the legacy runtime in this phase.

## Main Types

`AgenticFlowRunner`
: Runs one offline executor-then-judge cycle over a frozen contract and
  workspace policy.

`AgenticFlowRefs`
: Names the emitted workspace refs, including contract, projections, packets,
  reports, ledger, and checkpoint refs.

`AgenticFlowResult`
: Refs-only run result with execution status, judge decision, accepted artifact
  refs, and repair or revision refs when present.

`AgenticFlowStatus`
: Runtime status projected from the independent judge decision.

`AgentExecutorNode`
: Protocol for the executor role. The executor receives an
  `AgentExecutionPacket`, its packet ref, and a `RunWorkspace` constrained by
  the worker `PermissionManifest`.

`AgentJudgeNode`
: Protocol for the judge role. The judge receives a `JudgePacket`, its packet
  ref, and a judge-scoped workspace capability.
`TaskContractFlowPreset`, `create_default_task_contract_flow`
:: Convenience assembly for the TaskContract-native lane. It lives in
  `missionforge.adapters.task_contract_runtime`, packages an `AgenticFlowRunner`
  with PiWorker-backed executor and judge nodes, and keeps node selection
  explicit and testable.

`ScopedAgentWorkspace`
: In-process offline facade that routes node reads and writes through
  `RunWorkspace` while denying writes to runtime-owned refs. This is not a
  substitute for the later PiWorker tool sandbox; it is a product-neutral guard
  for the offline S4 test seam.

`RepairBrief`, `TaskRevisionRequest`, `TaskRevisionDecision`
: Product-neutral repair and revision artifacts used when the judge returns a
  repair or revision-required decision. They preserve the frozen contract hash
  and make the downstream state auditable.

These protocols are test seams and future PiWorker integration seams. They are
not a public multi-worker marketplace.

The live PiWorker-backed judge seam currently lives in
`missionforge.adapters.pi_agent_runtime.PiAgentJudgeNode`; this module remains
the offline composition layer and still accepts any judge-node implementation
through its protocol.

## Workspace Shape

The default refs follow the final-system target layout:

```text
contract/task_contract.json
contract/task_contract.hash
projections/worker_brief.json
packets/execution_packet.json
packets/judge_packet.json
reports/execution_report.json
reports/judge_report.json
ledgers/decision_ledger.jsonl
checkpoints/latest.json
```

`TaskContract.workspace_policy_ref`, `TaskContract.permission_manifest_ref`,
and `TaskContract.judge_rubric_ref` remain contract-owned refs. Product
integrations can choose those refs as data, without adding product branches to
MissionForge core.

## Ledger And Checkpoint

The S4 ledger is deliberately small and append-only from the runner API. It
records product-neutral events such as:

- `execution_packet_issued`
- `execution_report_recorded`
- `judge_packet_issued`
- `judge_report_recorded`

Each entry records event kind, run id, contract id/hash, status when relevant,
and a ref map. It does not embed raw provider output or artifact bodies.

The checkpoint at `checkpoints/latest.json` is overwriteable. It is a compact
recovery pointer to the current result and emitted refs, not a second source of
task truth.

Downstream controllers must not bind durable repair/revision decisions to that
mutable checkpoint. The repair-ticket controller snapshots the
`AgenticFlowResult` into an immutable `results/result-*.json` ref before
writing `repairs/{ticket_id}/repair_ticket.json`.

## Expected Failure Modes

The runner fails closed when:

- the contract hash has drifted;
- source refs are not readable by the worker manifest;
- required artifact refs are outside artifact roots;
- required artifact refs are outside worker writable refs;
- the permission manifest declares unsupported hard policies;
- passed hard-check refs are missing;
- executor reports do not match their packet;
- executor reports cite refs outside worker write authority;
- executor or judge nodes try to write runtime-owned control refs;
- judge packets cite artifacts not produced by execution;
- judge reports do not match their packet;
- judge reports accept failed, missing, or unsupported hard checks;
- judge reports accept an execution that did not complete;
- accepted runs omit required artifact refs or cite artifacts that do not exist;
- ledger/checkpoint/result payloads contain raw prompt, transcript, body,
  payload, stdout/stderr, or secret-like fields.

## Future Work

The next increments should keep this surface small:

- replace offline executor and judge test doubles with PiWorker-backed nodes;
- add a named decision-ledger wrapper if more event kinds or replay APIs are
  needed;
- add explicit hard-check artifact schemas;
- connect repair and revision requests to the existing revision workflow;
- keep Product Integration responsible for domain-specific contracts and judge
  rubric content.
