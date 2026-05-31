# Phase 24 TaskContract Repair / Revision Controller Plan

Last updated: 2026-05-31

Status: implemented S6 repair/revision thin control surface.

## Goal

Turn already-validated repair and revision artifacts into small, explicit,
idempotent control records that decide the next durable step without mutating
the frozen contract implicitly.

The controller should sit between the judge decision and the next run action:

```text
AgenticFlowResult(status=repair)
  -> validated RepairBrief
  -> RepairTicket
  -> RepairExecutionDirective

AgenticFlowResult(status=revision_required)
  -> validated TaskRevisionRequest
  -> RevisionPendingRecord
  -> authority-matching approved TaskRevisionDecision + revised TaskContract
  -> RevisionAppliedRecord + TaskContractRevision
```

This is intentionally not a new workflow engine. It is a compact state
transition surface for repair and revision authority. Repair and revision are
implemented as separate controller modules so the repair path cannot silently
apply or weaken a contract.

## Why This Exists

The current runtime already does the hard part correctly:

- `AgenticFlowRunner` only finalizes `repair` / `revision_required` after it
  validates the structured artifact.
- `RepairBrief` and `TaskRevisionRequest` are refs-first and bound to the
  active run, contract hash, judge packet, and judge report.
- `TaskRevisionDecision` is type-strict and hash-sensitive.

The dedicated control step turns those artifacts into the next durable action
without collapsing into ad hoc glue.

## Non-Goals

- No live PiWorker invocation.
- No deterministic semantic repair inference in code.
- No product-specific branches in `src/missionforge`.
- No general workflow engine.
- No automatic contract weakening.
- No implicit approval of revision.
- No replacement for `AgenticFlowRunner`.

## Proposed Controller Shape

Use a small product-neutral controller module, likely under
`src/missionforge/`.

The controller should accept:

- the active `TaskContract`;
- the validated `AgenticFlowResult` with `status=repair`;
- the validated `RepairBrief`;
- the matching `JudgePacket` and `JudgeReport` that produced the repair brief;
- the matching `AgentExecutionPacket` and active `WorkerBrief`, when the
  caller wants the controller to bind the next repair execution input
  explicitly;
- the run workspace or run-state refs needed to write durable records.

It should emit one durable control outcome at a time:

1. `RepairTicket`
2. `RepairExecutionDirective`
3. `RevisionPendingRecord`
4. `RevisionAppliedRecord`

`accepted` remains a terminal path handled by the flow, not the controller.
`revision_required` is handled by the separate revision controller, not by the
repair-ticket builder.

## Invariants

### Repair

- Repair keeps the current `TaskContract.contract_hash`.
- Repair does not change `required_outputs`, `semantic_acceptance`, or
  `hard_constraints`.
- Repair artifacts must stay bound to the current run, current judge packet,
  current judge report, and the judged artifact/evidence surface.
- The controller must not invoke another executor pass directly. It writes a
  durable ticket and, when asked, a repair execution directive plus packet ref
  for the outer runtime to consume.

### Revision

- Revision keeps the original `TaskContract.contract_hash` authoritative until
  an approved decision and revised contract are content-bound.
- Revision pending records must cite the immutable result, judge report,
  revision request, execution packet/report, and current contract.
- The revision decision authority must match the pending record's
  `authority_required`.
- Applying a revision must write an explicit `TaskContractRevision`.
- Rejected or redesign-required decisions cannot include revised contract refs
  and cannot apply a contract.

### General

- Controller records stay refs-first.
- No raw prompt, transcript, provider payload, stdout/stderr body, or secret
  may be written into controller records.
- The controller must stay product-neutral.

## Durable State Shape

Suggested run layout:

```text
runs/{run_id}/
  results/{result_id}.json
  repairs/{ticket_id}/
    repair_ticket.json
    repair_execution_directive.json
  packets/repairs/{ticket_id}/
    execution_packet.json
  revisions/{request_id}/
    revision_pending.json
    task_revision_decision.json
    task_contract_revision.json
    revision_applied.json
```

Notes:

- `repair_ticket.json` is a durable repair control record, not a semantic
  judgment;
- `repair_execution_directive.json` prepares the next repair execution packet
  but does not invoke a worker;
- the layout uses the existing run workspace as the physical root; refs stay
  workspace-relative inside the controller/runtime boundary;
- `result_id` is an immutable result artifact id derived from the validated
  `AgenticFlowResult` content; `checkpoints/latest.json` is an overwriteable
  convenience pointer and must never be used as `source_result_ref`;
- if the current `AgenticFlowRunner` has not yet written immutable result
  artifacts, the controller must snapshot the result payload to
  `results/{result_id}.json` before ticket creation and then bind the ticket to
  that immutable ref;
- `ticket_id` and `repair_id` are the same deterministic value in the first
  slice;
- frozen contract remains untouched by repair;
- revision application writes a new `TaskContractRevision`; runtime activation
  of that revised contract remains a separate runtime-state concern;
- the original `RepairBrief` remains at its source ref; the controller does not
  duplicate it into the ticket directory.

## RepairTicket Schema

The first implementation slice should introduce a strongly typed
`RepairTicket`.

Required fields:

```text
RepairTicket
  schema_version
  ticket_id
  ticket_hash
  run_id
  contract_id
  contract_hash
  contract_ref
  source_result_ref
  source_judge_report_ref
  source_repair_brief_ref
  execution_packet_ref
  execution_report_ref
  judge_packet_ref
  judge_report_ref
  target_artifact_refs
  evidence_refs
  worker_brief_ref
  status
```

Rules:

- `schema_version` starts as `repair_ticket.v1`.
- `status` is a typed enum. The S6 value is `ready`.
- `source_result_ref` is the immutable result artifact ref that stores the
  validated `AgenticFlowResult`; it is not under `checkpoints/`.
- If the controller receives `source_result_ref`, it must load the JSON at that
  ref and parse it as `AgenticFlowResult`; the loaded result must equal the
  supplied result's canonical `to_dict()` payload.
- If the controller receives `source_judge_report_ref`, it must load the JSON
  at that ref and parse it as `JudgeReport`; the loaded report must equal the
  supplied report's canonical `to_dict()` payload.
- If the controller receives `source_repair_brief_ref`, it must load the JSON
  at that ref and parse it as `RepairBrief`; the loaded brief must equal the
  supplied brief's canonical `to_dict()` payload.
- `ticket_id` is deterministic from the canonical JSON hash of:
  `schema_version`, `run_id`, `contract_hash`, `source_result_ref`, and
  `source_repair_brief_ref`. This gives the ticket one identifier system;
  `repair_id`, if ever exposed later, must equal `ticket_id`.
- `ticket_hash` is `stable_json_hash(ticket_payload_without_ticket_hash)`.
  `ticket_payload_without_ticket_hash` means the complete ticket payload with
  every persisted field except `ticket_hash`, serialized through the existing
  `stable_json_hash(...)` function in `src/missionforge/contracts.py`.
- Replay-safe writing compares the canonical `ticket_hash` stored in the
  existing `repair_ticket.json`. Re-running the same build returns the same
  ticket when the hash matches. Re-running with the same deterministic
  `ticket_id` but a different canonical hash fails closed as a conflict.
- `contract_hash` must equal the active `TaskContract.contract_hash`.
- `source_result_ref` must equal the terminal immutable result artifact ref
  used by the flow or the immutable snapshot ref created by the controller.
- `source_repair_brief_ref` must equal `AgenticFlowResult.repair_brief_ref`.
- `source_judge_report_ref` must equal `AgenticFlowResult.refs.judge_report_ref`.
- `JudgeReport.repair_brief_ref` must equal
  `AgenticFlowResult.repair_brief_ref`.
- `JudgePacket.execution_packet_ref` must equal
  `AgenticFlowResult.refs.execution_packet_ref`; the controller should also
  validate the loaded execution packet/report against the judge packet.
- `judge_packet_ref` must equal `RepairBrief.judge_packet_ref`.
- `judge_report_ref` must equal `RepairBrief.judge_report_ref` and must equal
  `source_judge_report_ref`.
- `execution_report_ref` must equal `RepairBrief.execution_report_ref`.
- `worker_brief_ref` must equal `result.refs.worker_brief_ref` and, if the
  controller receives the execution packet, `execution_packet.worker_brief_ref`.
- The loaded `WorkerBrief` at `worker_brief_ref`, when supplied, must match the
  active `contract_id`, `contract_hash`, and `contract_ref`.
- `target_artifact_refs` must be copied from the validated repair brief, not
  inferred by the controller.
- `evidence_refs` must be copied from the validated repair brief and stay
  within the judged evidence surface.
- No judge-authored `reason` or `repair_steps` text should be copied into the
  ticket; the ticket cites the repair brief by ref.
- `build_repair_ticket(...)` must call
  `validate_repair_brief_for_judge(brief, packet, report, run_id=result.run_id)`
  itself. It must not rely on caller convention that the brief was already
  validated.

Later slices may add consumed/closed states, but S6 does not implement a retry
loop.

## Controller APIs

The code prefers explicit helpers over a controller class:

```text
build_repair_ticket(
  *,
  contract,
  result,
  repair_brief,
  judge_packet,
  judge_report,
  workspace,
  source_result_ref=None,
  worker_brief=None,
  execution_packet=None,
) -> RepairTicket

build_repair_execution_directive(
  *,
  ticket,
  workspace,
  repair_ticket_ref=None,
  worker_brief=None,
) -> RepairExecutionDirective

build_revision_pending_record(
  *,
  contract,
  result,
  revision_request,
  judge_packet,
  judge_report,
  workspace,
  source_result_ref=None,
) -> RevisionPendingRecord

apply_task_contract_revision(
  *,
  pending,
  decision,
  revised_contract,
  workspace,
  pending_ref=None,
  decision_ref=None,
) -> RevisionAppliedRecord
```

`build_repair_ticket(...)` and `build_revision_pending_record(...)` are allowed
to snapshot `result` to an immutable `results/{id}.json` ref if
`source_result_ref` is not supplied. The repair ticket helper writes only:

```text
results/{result_id}.json
repairs/{ticket_id}/repair_ticket.json
```

`build_repair_execution_directive(...)` additionally writes:

```text
packets/repairs/{ticket_id}/execution_packet.json
repairs/{ticket_id}/repair_execution_directive.json
```

The revision helpers write under `revisions/{request_id}/`. No controller
ledger is part of S6. A ledger can be added later only after its event schema
is designed.

## Revision Control Slice

Revision application is implemented in `missionforge.agentic_revision_controller`.
It defines:

- a `RevisionPendingRecord` that binds `TaskRevisionRequest` to
  `AgenticFlowResult`;
- a stricter `TaskRevisionDecision` binding helper that includes run id,
  contract id, authority route, request ref, and current contract hash;
- `RevisionAppliedRecord` that loads the revised `TaskContract`, recomputes
  its hash, compares it to `revised_contract_hash`, and writes a
  `TaskContractRevision`;
- idempotency and conflict rules equivalent to `RepairTicket`.

The revision controller remains separate from the repair controller. The repair
ticket builder cannot approve or apply a revision.

## Acceptance Conditions

The repair controller design is good enough when:

- a foreign `run_id` fails closed;
- `AgenticFlowResult.status`, `AgenticFlowResult.judge_decision`, and the
  repair artifact type all agree that this is a repair flow;
- accepted, rejected, and `revision_required` results bypass the repair
  controller and fail closed if passed to `build_repair_ticket(...)`;
- `ticket.run_id == result.run_id == RepairBrief.run_id`;
- `ticket.contract_id`, `ticket.contract_ref`, and `ticket.contract_hash`
  match the active `TaskContract`, `AgenticFlowResult`, and `RepairBrief`;
- `build_repair_ticket(...)` re-validates `RepairBrief` against `JudgePacket`
  and `JudgeReport` using the active `run_id`;
- a repair brief cannot target artifacts outside the judged artifact surface;
- a repair brief cannot cite evidence outside the judged evidence surface;
- `ticket.execution_packet_ref == result.refs.execution_packet_ref`;
- `ticket.source_result_ref` is an immutable result ref, never under
  `checkpoints/`;
- `ticket.source_result_ref`, `ticket.source_judge_report_ref`, and
  `ticket.source_repair_brief_ref` are loaded and canonical-content-bound to
  the supplied result, judge report, and repair brief;
- `ticket.worker_brief_ref == result.refs.worker_brief_ref`, and the loaded
  worker brief matches the active contract when supplied;
- a repair run does not alter the frozen contract hash;
- all controller records remain refs-first and product-neutral;
- the controller surface can be tested with offline fake executor and judge
  fixtures only;
- revision application is implemented only through
  `apply_task_contract_revision(...)`, after an approved
  authority-matching `TaskRevisionDecision` and a content-bound revised
  `TaskContract`;
- no controller decision ledger is implemented in this slice.

## Review Questions

The reviewer should specifically check:

- whether the controller is too eager to become a workflow engine;
- whether repair and revision are still cleanly separated;
- whether any product-specific semantics leaked into `src/missionforge`;
- whether the durable layout remains stable enough for later PiWorker runtime
  hardening.

## Implemented Slice

The S6 code slice is intentionally small:

1. add `RepairTicket`, `RepairExecutionDirective`, and repair builders;
2. add `RevisionPendingRecord`, `RevisionAppliedRecord`, and revision builders;
3. add deterministic idempotency keys and replay-safe record writing using
   `stable_json_hash(...)`;
4. add tests for accepted / repair / revision / foreign-run / unreviewed-target
   / replay / content-drift paths;
5. keep live PiWorker integration out of scope for this slice.
