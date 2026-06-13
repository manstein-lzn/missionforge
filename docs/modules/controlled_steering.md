# Module: Controlled Steering

Status: supporting compatibility/data surface.

Controlled steering records model or reviewer suggestions as structured
artifacts. Suggestions are evidence and diagnosis input. They are not durable
task truth and they do not execute work.

The active runtime path is TaskContract/PiWorkerCall. Controlled steering must
not reintroduce a parallel runtime, work-unit compiler, or deterministic semantic
planner.

## Scope

- proposal-shaped artifacts;
- observation hypotheses;
- contract adjustment requests;
- review packets and reviewer decisions;
- explicit control requests;
- decision-ledger evidence around accepted or rejected suggestions.

## Rules

- LLM output may propose, interpret, or request review.
- Code may validate schemas, refs, authority, freshness, and permissions.
- A proposal cannot mutate a frozen `TaskContract`.
- A proposal cannot broaden authority.
- A proposal cannot mark work accepted.
- Contract truth changes require explicit TaskContract revision records on the
  active path.

## Relationship To Current Runtime

Current product execution should flow through:

```text
TaskContract
  -> PiWorkerCall(role=executor_piworker)
  -> PiWorkerCallResult
  -> PiWorkerCall(role=judge_piworker)
  -> JudgeReport
  -> DecisionLedger
```

Controlled steering artifacts may be cited as context or diagnosis refs, but
they do not replace the executor, judge, hard checks, repair controller, revision
controller, or ledger.

## Invariants

- Raw prompts and transcripts stay out of durable state by default.
- Suggestions are refs-first artifacts.
- Proposal confidence grants no authority.
- Metrics are diagnostics, not semantic route or acceptance authority.
- Review decisions must be independent from the worker being reviewed.
