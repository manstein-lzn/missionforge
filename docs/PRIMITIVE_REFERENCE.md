# Primitive Reference

This is the field-level reference for the main programmer-facing primitives.

## TaskContract

Frozen task authority. It holds:

- `contract_id`
- `contract_hash`
- `objective`
- `required_outputs`
- `hard_constraints`
- `semantic_acceptance`
- `workspace_policy_ref`
- `permission_manifest_ref`
- `judge_rubric_ref`

## WorkspacePolicy

Declares the filesystem layout:

- `workspace_root_ref`
- `input_refs`
- `artifact_root_refs`
- `scratch_root_refs`
- `denied_refs`

## PermissionManifest

Declares read/write authority:

- `readable_refs`
- `writable_refs`
- `denied_refs`
- `allowed_commands`
- `network_policy`
- `env_allowlist`

## PiWorkerCall

The bounded intelligence RPC:

- `call_id`
- `role`
- `contract_id`
- `contract_hash`
- `contract_ref`
- `objective`
- `visible_refs`
- `writable_refs`
- `expected_output_refs`
- `permission_manifest_ref`
- `evidence_refs`

## PiWorkerCallResult

Boundary evidence for one call:

- `result_id`
- `call_id`
- `role`
- `status`
- `execution_report_ref`
- `output_refs`
- `runtime_refs`
- `evidence_refs`
- `metric_refs`

## RepairTicket

Durable same-contract repair authority:

- `ticket_id`
- `ticket_hash`
- `contract_hash`
- `source_result_ref`
- `source_repair_brief_ref`
- `target_artifact_refs`
- `worker_brief_ref`

## RepairExecutionDirective

The next repair execution input:

- `directive_id`
- `directive_hash`
- `repair_ticket_ref`
- `repair_ticket_hash`
- `execution_packet_ref`
- `execution_report_ref`
- `target_artifact_refs`
- `context_refs`

## Repair Rejudge Packet

`build_repair_rejudge_packet(...)` converts a completed repair
`PiWorkerCallResult` into:

- a repair `AgentExecutionReport` at the directive's `execution_report_ref`
- a new `JudgePacket` under `packets/repairs/{ticket_id}/judge_packet.json`
- a new judge report target under `reports/repairs/{ticket_id}/judge_report.json`

It preserves the same `contract_hash` and does not emit acceptance.

## RevisionPendingRecord

Durable record that a judge requested explicit contract revision:

- `pending_id`
- `pending_hash`
- `source_result_ref`
- `source_revision_request_ref`
- `authority_required`
- `contract_hash`

## RevisionAppliedRecord

Durable record that an approved revision changed task authority:

- `applied_id`
- `previous_contract_hash`
- `revised_contract_hash`
- `task_revision_decision_ref`
- `task_contract_revision_ref`
- `revised_contract_ref`

## RevisionExecutionDirective

The first execution entry after explicit revised task authority:

- `directive_id`
- `directive_hash`
- `previous_contract_hash`
- `contract_hash`
- `revision_applied_ref`
- `revision_applied_hash`
- `task_revision_decision_ref`
- `task_contract_revision_ref`
- `revised_contract_ref`
- `worker_brief_ref`
- `execution_packet_ref`
- `execution_report_ref`
- `expected_artifact_refs`
- `context_refs`

`build_revision_execution_directive(...)` writes the revised-contract
`WorkerBrief` and `AgentExecutionPacket` under `revisions/{request_id}/...`. It
does not invoke the executor and does not emit acceptance.

## Revision Rejudge Packet

`build_revision_rejudge_packet(...)` converts a revised-contract executor
`PiWorkerCallResult` into:

- a revised `AgentExecutionReport` at the directive's `execution_report_ref`
- a revised `JudgeRubric` under `revisions/{request_id}/projections/`
- a new `JudgePacket` under `revisions/{request_id}/packets/judge_packet.json`
- a new judge report target under `revisions/{request_id}/reports/judge_report.json`

It binds the packet to the revised contract hash and cites the applied,
decision, contract-revision, and source request refs. It does not emit
acceptance.

## Revision Judge Result

`build_revision_judge_result(...)` records the independent judge result after a
revised-contract execution. It takes:

- `RevisionExecutionDirective`
- revised-contract `JudgePacket`
- independent `JudgeReport`
- `RunWorkspace`
- optional directive, packet, and ledger refs

It validates:

- the directive and judge packet still match the artifacts on disk
- the applied revision hash matches the directive
- the revised execution packet and execution report match the judge packet
- the judge report was authored for that packet
- accepted revised work has completed execution and accepted expected artifacts
- repair decisions include a valid `repair_brief_ref`
- revision-required decisions include a valid `revision_request_ref`

It writes:

- revised `AgenticFlowResult`
- revised checkpoint
- revised judge report
- revised final package when the judge accepts
- refs-only decision ledger entries

It appends `revision_applied` before revised judge/final events when needed.
That event is the only ledger event allowed to change `contract_hash`. The
function does not invoke an executor, invoke a judge, or let the executor
self-accept.

## Revision Draft Contract

`load_revision_draft_contract(...)` validates the output of
`revision_drafter_piworker`:

- the call result role is `revision_drafter_piworker`
- the call result is bound to the `RevisionPendingRecord`
- the expected revised contract ref is present in `output_refs`
- the revised `TaskContract` loads and validates
- the revised contract hash differs from the pending contract hash

It returns a `TaskContract` proposal. It does not produce a
`TaskRevisionDecision` and does not apply the revision.

## AgenticFlowRunner

The default TaskContract-native orchestration path. It runs:

```text
contract -> worker brief -> execution packet -> executor -> judge packet ->
judge report -> refs-only result
```

## SkillFoundry Boundary

SkillFoundry compiles into MissionForge contracts outside core. It should not
be reimplemented by reading MissionForge internals.
