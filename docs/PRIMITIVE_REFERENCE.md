# Primitive Reference

## Task Authority

- `TaskContract`: frozen task truth.
- `TaskContractRevision`: explicit task truth change.
- `WorkspacePolicy`: workspace boundary.
- `PermissionManifest`: readable refs, writable refs, denied refs, commands,
  network policy, and extension grants.

## Projections

- `WorkerBrief`: role-specific worker brief projected from the contract.
- `JudgeRubric`: role-specific judge rubric projected from the contract.

## PiWorker Boundary

- `PiWorkerCall`: one bounded intelligence RPC.
- `PiWorkerCallRole`: frontdesk author, executor, judge, repair, or revision
  drafter role.
- `PiWorkerCallResult`: refs-first runtime result.
- `run_piworker_call(...)`: default execution helper.

`PiWorkerCallResult` records boundary status and refs. It does not grant
semantic acceptance.

## Runtime Adapter

`missionforge.adapters.pi_agent_runtime` contains the Pi sidecar adapter and
configuration:

- `PiAgentRuntimeAdapter`
- `PiAgentRuntimeConfig`
- `PiAgentCallSpec`

These are explicit adapter internals, not package-root exports.

## Evidence And Progress

- `EvidenceLedger`, `EvidenceRecord`, `ArtifactRef`, `EvidenceRef`
- `ProgressEvent`, `ProgressStreamWriter`, `stream_progress`
- `ContextSummaryArtifact`

Durable records should cite refs and hashes. They should not embed raw prompts,
provider payloads, stdout/stderr bodies, artifact bodies, or secrets.

## Kernel API

The compact `missionforge.kernel` package builds on the same primitives with
`Step` and `Flow` descriptors for product integrations that need multi-role
coordination without reimplementing orchestration.
