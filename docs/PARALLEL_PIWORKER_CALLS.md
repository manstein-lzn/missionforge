# MissionForge Parallel PiWorker Calls Development Plan

Status: first slice implemented

Last updated: 2026-06-28

## Implementation Status

Implemented in this slice:

- low-level `PiWorkerCallBatch` / `PiWorkerCallBatchResult` contracts;
- `run_piworker_call_batch(...)` for isolated concurrent `PiWorkerCall`
  execution;
- preflight rejection for duplicate call ids, duplicate outputs, and overlapping
  writable refs;
- per-call batch namespaces for result, evidence, progress, and structured
  runtime error records;
- Kernel `StepBatchResult` and `run_steps_batch(...)` wrapper over existing
  `run_step(...)`;
- root and `missionforge.kernel` exports;
- focused unit tests for conflict rejection, namespace isolation, partial
  failure collection, and Kernel context boundary isolation.

Still intentionally out of scope:

- shared mutable state;
- reducers or automatic merge;
- parallel `run_flow(...)` routing;
- product-specific synthesis;
- simultaneous writes to the same project tree.

## Background

MissionForge is a Python-first Agent-in-Code harness infrastructure. It is not a
DeerFlow clone, a LangGraph replacement, or an application-level agent product.

Developers should be able to use ordinary Python code plus MissionForge
primitives to build concrete systems such as DeepResearch, DeerFlow-like agents,
code review agents, multi-agent analysis tools, and product-specific agent
workflows.

MissionForge core should provide small, orthogonal runtime primitives:

- `PiWorkerCall`;
- `ContextEngine`;
- `PermissionManifest`;
- `ToolGateway`;
- artifact refs and workspace boundaries;
- runtime control;
- parallel fan-out / fan-in.

The current major infrastructure gap is the lack of a controlled multi-agent
parallel execution primitive.

## Core Position

This phase must not attempt to solve shared-state race cases.

The first parallel primitive is not intended to support:

```text
multiple agents editing the same project tree at the same time
multiple agents sharing mutable state
MissionForge automatically resolving merge, race, or semantic conflicts
```

The first parallel primitive should support:

```text
isolated parallel calls with no shared writes
fail-closed conflict detection before execution
per-call context / permission / runtime namespaces
structured fan-in results
semantic synthesis in a later Python workflow / PiWorker / Judge step
```

This matches the MissionForge boundary:

```text
Python owns orchestration.
MissionForge owns execution boundaries.
```

## Target Capability

Add a low-level parallel call primitive:

```python
result = run_piworker_call_batch(
    PiWorkerCallBatch(
        batch_id="analysis-batch",
        calls=[call_a, call_b, call_c],
        concurrency=3,
    ),
    workspace="./runs",
)
```

Add a Kernel Step wrapper:

```python
result = run_steps_batch(
    [step_a, step_b, step_c],
    context=context,
    workspace="./runs",
    concurrency=3,
)
```

After this phase, developers should be able to use MissionForge public
primitives for:

- parallel analysis;
- parallel research;
- parallel review;
- parallel candidate generation;
- parallel module inspection;
- parallel subagent exploration.

Shared writes, automatic merge, and complex graph execution are out of scope.

The two APIs have different guarantees:

- `run_piworker_call_batch(...)` is a low-level batch wrapper around
  `run_piworker_call(...)`. It runs already-compiled `PiWorkerCall` objects in
  isolated namespaces. It does not by itself compile a ContextEngine provider
  turn.
- `run_steps_batch(...)` is the ContextEngine-managed Kernel entry point. It
  should reuse existing `run_step(...)` behavior so each Step still receives the
  normal PermissionManifest, ContextEngine, extension, resume, and StepRecord
  handling.

## Existing Code Base

Relevant existing foundations:

- `src/missionforge/piworker_call.py`
  - `PiWorkerCall` already has `call_id`, `visible_refs`, `writable_refs`,
    `expected_output_refs`, `permission_manifest_ref`, and `runtime_budget`.
- `src/missionforge/piworker_runtime.py`
  - `run_piworker_call(...)` is the single-call PiWorker execution primitive.
- `src/missionforge/kernel/runner.py`
  - `run_step(...)` already implements the full Step path:
    `Step -> PermissionManifest -> ContextEngine -> PiWorkerCall -> StepRecord`.
  - `run_flow(...)` is currently sequential routing and does not support
    parallel step groups.
- `src/missionforge/runtime_control.py`
  - `ToolGateway`, `CapabilityGrant`, sandbox profile, and permission
    boundaries already exist.

Known parallelization risks:

- `src/missionforge/kernel/io.py`
  - `write_json_ref(...)` writes directly with `Path.write_text(...)`.
  - It is not an atomic concurrent write primitive.
- `src/missionforge/evidence_store.py`
  - `FileEvidenceStore` uses in-memory sequence allocation and should not be
    shared across concurrent calls.
- `src/missionforge/progress_stream.py`
  - `ProgressStreamWriter` locks only one writer instance.
  - Multiple writer instances writing the same stream are not safe.
- `PiWorkerCallAdapter`
  - There is no thread-safety contract.
  - A shared adapter instance must not be assumed safe for concurrent use.

## New Modules

Add:

```text
src/missionforge/piworker_batch.py
src/missionforge/kernel/batch.py
```

Export the public API from:

```text
src/missionforge/__init__.py
src/missionforge/kernel/__init__.py
```

## Data Contracts

### `PiWorkerCallBatch`

```python
@dataclass(frozen=True)
class PiWorkerCallBatch:
    batch_id: str
    calls: list[PiWorkerCall]
    concurrency: int = 3
    conflict_policy: str = "reject"
    failure_policy: str = "collect"
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

Validation rules:

- `batch_id` must be a safe id.
- `calls` must not be empty.
- each `call_id` must be unique within the batch.
- `concurrency` must be at least `1`.
- `conflict_policy` initially supports only `"reject"`.
- `failure_policy` initially supports only `"collect"`.
- every call must pass `PiWorkerCall.validate()`.

### `PiWorkerCallBatchResult`

```python
@dataclass(frozen=True)
class PiWorkerCallBatchResult:
    batch_id: str
    status: str
    call_result_refs: list[str]
    completed_call_ids: list[str]
    failed_call_ids: list[str]
    blocked_call_ids: list[str]
    invalid_call_ids: list[str]
    output_refs: list[str]
    runtime_refs: list[str]
    batch_result_ref: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

Initial statuses:

```text
completed
partial
failed
cancelled
```

Status calculation:

- `completed`: all calls completed successfully.
- `partial`: at least one call completed and at least one call did not complete.
- `failed`: no call completed successfully and at least one call failed,
  blocked, or produced invalid output.
- `cancelled`: reserved for future cancellation propagation or explicit batch
  cancellation support.

Runtime exceptions raised while executing one call must be represented as a
call-level failed result, not as an unstructured batch crash. The batch runtime
should write:

```text
piworker_batches/{batch_id}/calls/{call_segment}/error.json
piworker_batches/{batch_id}/calls/{call_segment}/execution_report.json
piworker_batches/{batch_id}/calls/{call_segment}/piworker_call_result.json
```

The synthetic `PiWorkerCallResult` should use `RUNTIME_ERROR` when the adapter
or runtime raised before a valid worker result existed. The minimal execution
report should cite the error ref and preserve the original `call_id`,
`contract_id`, `contract_hash`, and role.

## Execution API

Add:

```python
def run_piworker_call_batch(
    batch: PiWorkerCallBatch,
    *,
    workspace: str | Path = ".",
    piworker_config: Any | None = None,
    adapter_factory: Callable[[PiWorkerCall], PiWorkerCallAdapter] | None = None,
    evidence_store_factory: Callable[[PiWorkerCall], EvidenceLedger] | None = None,
    runtime_progress_sink_factory: Callable[[PiWorkerCall], PiWorkerProgressSink] | None = None,
) -> PiWorkerCallBatchResult:
    ...
```

Default behavior:

- create a separate adapter per call;
- do not reuse a shared adapter instance;
- create a separate evidence namespace per call;
- create a separate progress namespace per call;
- write batch spec/result from the parent runtime path, serially;
- execute calls concurrently only after batch-level preflight succeeds;
- collect failed call exceptions into structured result records.

Because this low-level API receives already-compiled calls, it must not claim to
provide ContextEngine-managed turns. Callers that need package-managed context
compilation should use `run_steps_batch(...)` or compile calls through the
Kernel path before batching.

## Namespace Rules

Batch-level records:

```text
piworker_batches/{batch_id}/batch_spec.json
piworker_batches/{batch_id}/batch_result.json
```

Call-level records:

```text
piworker_batches/{batch_id}/calls/{call_id}/piworker_call_result.json
piworker_batches/{batch_id}/calls/{call_id}/evidence/
piworker_batches/{batch_id}/calls/{call_id}/progress.jsonl
```

Kernel Step batch records:

```text
kernel/{flow_id}/batches/{batch_id}/steps/{index}-{step_id}/
```

Call IDs must be safe enough for use as ref path segments. If the existing
`call_id` validation is looser than path-segment safety, the batch layer should
derive a safe path segment while preserving the original `call_id` in records.

## Conflict Validation

Batch execution must perform preflight validation before starting any call.

Reject:

```text
duplicate call_id
duplicate expected_output_refs
same writable_ref across calls
writable_refs with parent/child overlap across calls
expected_output_ref not under that call's writable_refs
```

Overlap examples:

```text
artifacts/a.json and artifacts/a.json -> conflict
artifacts and artifacts/a.json -> conflict
outputs/module-a and outputs/module-b -> allowed
```

The first phase must not implement reducers.

If multiple outputs need to be merged, a later explicit synthesis, writer, or
merge step must consume the batch result refs.

For Kernel Step batches, the same conflict rules apply to each Step's declared
`outputs` and `write` refs before any Step is executed. If two Steps would write
the same ref or overlapping writable roots, the batch must fail closed.

## Concurrency Strategy

Use `ThreadPoolExecutor` for the first implementation.

Sketch:

```python
validate_batch(batch)
write_batch_spec(...)

with ThreadPoolExecutor(max_workers=batch.concurrency) as pool:
    futures = {
        pool.submit(run_one_call, call): call
        for call in batch.calls
    }

    for future in as_completed(futures):
        collect_result_or_failure(future)

write_batch_result(...)
return batch_result
```

`run_one_call` should:

```python
adapter = adapter_factory(call) if adapter_factory else create_default_piworker_adapter(...)
evidence_store = evidence_store_factory(call) or FileEvidenceStore(call_namespace)
progress_sink = runtime_progress_sink_factory(call) or None

result = run_piworker_call(
    call,
    workspace=workspace,
    adapter=adapter,
    evidence_store=evidence_store,
    runtime_progress_sink=progress_sink,
)
```

Implementation notes:

- exceptions must become structured failed results;
- the parent batch should not leave a half-written batch result;
- batch spec can be written before execution;
- batch result must be written after collecting all finished call outcomes;
- the first implementation should only support `failure_policy="collect"`.

`fail_fast` is intentionally deferred. With `ThreadPoolExecutor`, submitting all
futures up front makes "do not start pending calls after first failure" hard to
guarantee without a more complex scheduler. The first version should prefer
simple, deterministic collection over partially reliable cancellation semantics.

## Kernel Step Batch

Add:

```python
def run_steps_batch(
    steps: list[Step],
    *,
    context: StepCompileContext,
    workspace: str | Path = ".",
    concurrency: int = 3,
    ...
) -> StepBatchResult:
    ...
```

Principles:

- do not reimplement `run_step(...)`;
- derive a unique `StepCompileContext.ref_prefix` for each step;
- derive a unique `call_id` for each step;
- reuse the existing ContextEngine, PermissionManifest, extension, resume, and
  StepRecord path;
- the batch layer only validates conflicts, schedules execution, and collects
  results.

Step batch isolation requirements:

- every Step must execute with a unique derived `ref_prefix`;
- every Step must execute with a unique derived `call_id`;
- Step `outputs` and `write` refs must be conflict-checked before execution;
- callers must not share a mutable `EvidenceLedger` across concurrent Steps;
- progress streams must be per-Step or explicitly sink-isolated;
- ContextEngine records must remain under each Step's derived prefix;
- batch execution must not mutate the caller's original `StepCompileContext`.

The first implementation can keep `run_flow(...)` sequential. Do not add
parallel route semantics to `Flow` in this phase.

## Atomic IO Guidance

This phase can avoid broad IO rewrites by strict namespace isolation and serial
batch writes.

Do not introduce shared concurrent writes to:

- one evidence store;
- one progress stream;
- one JSONL ledger;
- one runtime record ref.

If a helper is needed for batch result durability, add a local atomic write
helper for the new batch module:

```text
write temp file in same directory
replace target with os.replace
```

Avoid broad replacement of existing IO helpers unless required by tests.

## Non-Goals

Do not implement in this phase:

- LangGraph-style graph engine;
- BSP / superstep runtime;
- reducers, CRDTs, or shared mutable state;
- multi-agent simultaneous edits to the same project tree;
- automatic dependency analysis;
- DeerFlow-style lead agent preset;
- DeepResearch-specific logic;
- product-specific routing;
- parallel `run_flow(...)` route semantics.

## Tests

Add tests for the low-level batch module:

- duplicate `call_id` is rejected;
- duplicate `expected_output_refs` is rejected;
- same writable ref is rejected;
- parent/child writable ref overlap is rejected;
- three fake adapter calls can complete through the batch API;
- one failed call and two completed calls with `failure_policy="collect"`
  returns `partial`;
- `adapter_factory` is called once per call;
- call result refs are written in distinct per-call namespaces;
- evidence/progress namespaces do not conflict.

Add tests for Kernel Step batch:

- each step gets a distinct `step_record_ref`;
- each step gets a distinct `context_projection_ref`;
- ContextEngine metadata remains per-step;
- executor self-acceptance remains impossible;
- Judge acceptance rules remain unchanged.

## Acceptance Criteria

After implementation, this should work:

```python
results = run_piworker_call_batch(
    PiWorkerCallBatch(
        batch_id="module-analysis",
        calls=[call_a, call_b, call_c],
        concurrency=3,
    ),
    workspace="./runs",
)
```

And this should work through the Kernel layer:

```python
step_results = run_steps_batch(
    [analyze_auth, analyze_billing, analyze_search],
    context=context,
    workspace="./runs",
    concurrency=3,
)
```

MissionForge must guarantee:

```text
output conflicts are rejected before execution
runtime namespaces are isolated
context, evidence, and progress records are isolated
partial failures are returned structurally
semantic synthesis remains a later explicit workflow step
```

This is the smallest useful parallel Agent primitive for MissionForge as an
Agent-in-Code harness.
