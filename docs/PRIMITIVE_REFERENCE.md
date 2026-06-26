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

## Context Engine

The ContextEngine primitives are product-neutral lifecycle records for compiling
model working context without turning refs into hidden memory:

- `ContextSource` / `ContextSourceSnapshot`: stable, permission-filtered source
  identity.
- `ContextEpoch`: cache-friendly baseline generation.
- `ContextWorkingSet` / `ContextWorkingSetEntry`: bounded active work memory
  backed by refs, projections, and why-it-matters refs.
- `ContextCacheLayout`: provider-neutral cache strata diagnostics.
- `ContextCompileRequest` / `ContextCompileResult`: host boundary for context
  compilation.
- `ContextTurnBoundary`: safe provider-turn boundary record.
- `ContextCompactionRecord`: durable compaction lifecycle record.
- `ContextReadObservation` / `ContextThrashDiagnostics`: repeated-read
  diagnostics without raw query text.
- `ToolOutputProjection`: bounded model-visible projection of full tool output.

Core validates refs, hashes, permissions, layout, and lifecycle status. Product
integrations own semantic summaries, source ranking, and domain-specific memory.

Kernel `run_step()` currently emits a minimal ContextEngine record set beside
the existing `context_projection.json`: source snapshot, epoch, cache layout,
turn safe point, turn boundary, and compile result refs. These records are
exposed through `StepRecord.metadata`, `inspect_kernel_run()`, and the read-only
adapter CLI. They are diagnostic/control-plane refs and do not change provider
prompt rendering yet.

## Kernel API

The compact `missionforge.kernel` package builds on the same primitives with
`Step` and `Flow` descriptors for product integrations that need multi-role
coordination without reimplementing orchestration.
