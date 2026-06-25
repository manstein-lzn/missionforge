# Interaction Port

MissionForge's interaction plane lets hosts and user interfaces communicate
with running flows without weakening the frozen contract model.

It is deliberately small:

```text
UserEvent  -> user intervention submitted to a running flow
AgentEvent -> user-visible event emitted by runtime/product code
FileInteractionPort -> append-only workspace-backed implementation
```

## Invariants

- User events are interventions, not task authority.
- Frozen contracts and explicit revisions remain the durable task authority.
- Pause, cancel, and contract revision requests are handled at kernel safe
  points unless a future runtime explicitly supports stronger semantics.
- Flow ledgers cite interaction refs and counts; they do not embed raw user
  message text.
- Worker-visible user events enter through explicit input refs so resume and
  input hashes see the intervention.
- Workers may read interaction snapshots, but they should not write the
  interaction ledger unless explicitly granted by a product integration.
- Product integrations own semantics. Core does not know FrontDesk,
  DeepResearch, code generation, or other product meanings.

## Files

The default file-backed port writes under the run workspace:

```text
interaction/user_events.jsonl
interaction/agent_events.jsonl
interaction/user_event_acks.jsonl
kernel/{flow}/runs/{run}/executions/{execution}/interaction/safe_points/{step}-user_events.json
```

The execution-scoped `interaction/safe_points/*.json` files are mechanical
projections of currently pending user events. Kernel steps receive only the
current projection as a readable input ref when an interaction port is provided;
workers do not receive the raw `interaction/user_events.jsonl` log by default.

`interaction/user_event_acks.jsonl` records delivery to a completed safe-point
step. It is not semantic proof that the worker agreed with the user request or
changed the frozen task. If the step fails or blocks, the event remains pending
for later resume or revision handling.

## Safe-Point Semantics

The first implementation is intentionally safe-point based and now routes all
host-side control requests through `ControlPort`:

```text
TUI/Web submits ControlPort request
  -> FileControlPort appends the corresponding UserEvent
  -> kernel checks before the next step
  -> kernel writes execution-scoped safe-point projection
  -> next PiWorker sees the projection as an input ref
```

This is not mid-tool interruption. It does not cancel an in-flight provider call
or mutate a running tool invocation.

Pause and cancel requests currently stop the flow with:

```text
status: blocked
stop_reason: user_pause_requested | user_cancel_requested
```

This keeps the terminal status model conservative and prevents user
interventions from looking like successful completion.

## Product Use

DeepResearch uses the interaction plane to let users type while a research run
is active. Natural-language messages are queued as `message` events. `/revise`
creates a `contract_revision_request`. `/pause` and `/cancel` become control
events handled at the next safe point.

Researchers, reviewers, and judges are instructed to treat user events as
guidance or interruption signals. If an event conflicts with the frozen
contract, they must ask for revision or block rather than silently changing the
task.
