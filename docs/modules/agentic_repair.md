# Agentic Repair

Last updated: 2026-05-31

Status: TaskContract-native repair and revision artifact surface for the
simplified agentic runtime.

## Purpose

`missionforge.agentic_repair` holds the small product-neutral artifacts that
turn judge repair and revision decisions into structured, auditable state.

It does not decide whether the artifact is good. It only makes the judge's
decision durable and verifiable:

```text
JudgeReport(decision=repair)
  -> RepairBrief
  -> repair loop or operator follow-up

JudgeReport(decision=revision_required)
  -> TaskRevisionRequest
  -> TaskRevisionDecision
  -> optional TaskContractRevision
```

## Design Boundaries

- `RepairBrief` preserves the frozen contract hash.
- `RepairBrief` cites the judge packet, judge report, execution report, and
  target artifact refs.
- `RepairBrief.run_id` and `TaskRevisionRequest.run_id` must match the active
  run before the flow finalizes the decision.
- `RepairBrief.target_artifact_refs` and both artifacts' evidence refs must be
  bound to the judged packet/evidence surface, not arbitrary refs.
- `TaskRevisionRequest` proposes a contract change, but does not mutate the
  active contract.
- `TaskRevisionDecision` is explicit and hash-sensitive.
- Approved revision must produce a different contract hash from the current
  one.
- All artifacts are refs-first and validate their own bindings; they do not
  embed raw prompts, transcripts, provider payloads, stdout/stderr bodies, or
  secrets.

## Non-Goals

- No live PiWorker orchestration.
- No semantic repair strategy selection in code.
- No automatic contract weakening.
- No product-specific logic in MissionForge core.

## Runtime Role

`missionforge.agentic_flow` can require these artifacts when a judge returns
repair or revision-required. The flow then validates that the structured
artifact actually matches the judge packet and report before the run result is
finalized.

This keeps repair and revision in the contract/governance layer instead of
making them ad hoc prompt text.

## Repair Ticket Controller

`missionforge.agentic_repair_controller` is the next thin control layer after a
validated repair result. It turns:

```text
AgenticFlowResult(status=repair)
  + RepairBrief
  + JudgePacket/JudgeReport
  + projected WorkerBrief/ExecutionPacket refs
  -> RepairTicket
```

`RepairTicket` is not a workflow engine and not a semantic repair plan. It is a
refs-only durable directive for the next repair execution pass. It records the
frozen contract id/hash, immutable source result ref, repair brief ref, judge
packet/report refs, execution packet/report refs, worker brief ref, target
artifact refs, and evidence refs.

The controller enforces these boundaries:

- it only accepts `AgenticFlowResult.status=repair` and
  `JudgeReportDecision.REPAIR`;
- it re-runs `validate_repair_brief_for_judge(...)` instead of trusting caller
  convention;
- it snapshots the result to an immutable `results/result-*.json` ref when no
  immutable result ref is supplied;
- it rejects checkpoint refs as `source_result_ref`;
- it loads and content-binds the result, contract, judge packet, judge report,
  repair brief, worker brief, and execution packet refs before writing a
  ticket;
- it writes `repairs/{ticket_id}/repair_ticket.json` idempotently, returning
  the existing ticket on exact replay and failing closed on hash conflict;
- it does not copy judge-authored `reason` or `repair_steps` into the ticket;
- it does not apply revisions, schedule a new executor pass, mutate the frozen
  contract, or write a controller ledger in the first slice.
