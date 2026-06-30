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
- `ContextCheckpoint`: durable refs-only checkpoint created by MissionForge at
  context pressure boundaries.
- `ContextReductionRequest` / `ContextReductionResult`: MissionForge-managed
  reducer boundary records for package-owned context maintenance.
- `ContextCompactionRecord`: durable compaction lifecycle record.
- `ContextManagementPolicy`: mechanical pressure thresholds, reducer
  enablement, retry behavior, and token caps.
- `ContextReadObservation` / `ContextThrashDiagnostics`: repeated-read
  diagnostics without raw query text. Pi agent runtime reports can materialize
  these diagnostics from tool observations, and Kernel flow execution carries
  active diagnostics into the next managed reducer request by policy.
- `ToolOutputProjection`: bounded model-visible projection of full tool output.
  The Pi agent adapter materializes sidecar `projected_observations` into
  refs-only projection records and text stubs under each attempt's
  `context/tool_output_projections/` directory. Kernel flow execution can carry
  those projection record refs into the next step's `ContextCompileRequest`;
  admission still depends on the next step's `ReadGate`.
- `compile_context_request(...)`: product-neutral compile boundary that filters
  sources through `ReadGate`, builds a deterministic `ContextView`, emits cache
  layout and pressure diagnostics, and returns a non-semantic
  `ContextCompileResult`.
- `reconcile_context_epoch(...)`: stable-prefix epoch reconciliation helper.

Core validates refs, hashes, permissions, layout, and lifecycle status. Product
integrations own semantic summaries, source ranking, and domain-specific memory.

Kernel `run_step()` now constructs a `ContextCompileRequest` before PiWorker
invocation and persists the compiled record set beside the existing
`context_projection.json`: compile request, source snapshot, epoch, cache
layout, pressure diagnostics, checkpoint, turn safe point, turn boundary, and
compile result refs. Denied required sources block at this safe boundary before
the PiWorker adapter is called.

At hard pressure, Kernel first writes a checkpoint and invokes a managed
`context_reducer_piworker` when policy allows it. Valid reducer output is
checked against a scoped maintenance permission manifest, recorded as a
refs-only state transition/compaction record, and followed by a fresh context
compile before the original worker call. Invalid or failed reducer output blocks
safely with diagnostic refs and leaves the previous context view/epoch active.
These records are exposed through `StepRecord.metadata`, `inspect_kernel_run()`,
and the read-only adapter CLI.

The Pi agent runtime input now carries a first-class `context_engine` envelope
with the Kernel compile refs. The sidecar reads the compiled `ContextView` and
`ContextCompileResult` before provider invocation and lowers admitted
stable/semi-stable/volatile segment refs into a bounded ephemeral provider-turn
context summary. Admitted working-set and tool-output projection text is
rendered only after sidecar read permission and compiled hash checks. Omitted
and denied refs are not rendered, and durable state
continues to avoid prompt bodies, provider payloads, and raw tool bodies.

Bounded retry attempts reuse the parent call's compiled ContextEngine boundary
only when that reuse is explicit. Kernel attempt calls include
`context_boundary_reuse: "same_preflight_boundary"` plus parent call, compile
result, turn boundary, and epoch refs. The Pi agent adapter rejects retry
attempts that carry parent call metadata and ContextEngine refs without that
same-boundary declaration.

## Kernel API

The compact `missionforge.kernel` package builds on the same primitives with
`Step` and `Flow` descriptors for product integrations that need multi-role
coordination without reimplementing orchestration.
