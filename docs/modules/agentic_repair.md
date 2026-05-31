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
