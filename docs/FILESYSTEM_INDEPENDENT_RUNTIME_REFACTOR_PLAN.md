# Filesystem-Independent Runtime Refactor Plan

Status: active refactor plan, Phase 1 complete, Phases 2-4 substantially
implemented, Phase 6 partially implemented

Last updated: 2026-06-29

## Goal

MissionForge should be a Python package with no implicit filesystem side
effects.

Importing MissionForge must not create files, directories, sockets, caches,
extension installs, progress logs, checkpoints, or temporary workspaces.
Running MissionForge through the default package API should also avoid writing
to the host filesystem unless the caller explicitly provides a filesystem-backed
store, sandbox workspace, extension install root, or materialization target.

The target shape is:

```text
trusted host Python
  -> MissionForge core primitives
  -> explicit RefStore
  -> bounded PiWorker calls and tools
  -> refs, hashes, context views, events, ledgers
  -> optional durable materialization backend
```

This is not a move away from refs. It is a move away from treating refs as file
paths.

```text
refs-first authority model
!=
filesystem-first transport
```

Refs remain the identity, permission, hash, evidence, and replay handles.
Filesystem paths become one optional backend.

## Architectural Position

MissionForge core should remain product-neutral and PiWorker-centered:

```text
ProductIntegration
  -> TaskContract + WorkerBrief + JudgeRubric + PermissionManifest
  -> PiWorkerCall
  -> artifact refs + execution report
  -> independent Judge PiWorker
  -> accepted | repair | revision_required | rejected
  -> refs-first ledger/package
```

This refactor changes the storage and transport layer. It must not change the
semantic authority model.

MissionForge core continues to own:

- frozen task authority;
- explicit contract revision;
- permission manifests;
- refs and hashes;
- read/write gates;
- context compilation and compaction boundaries;
- PiWorker call/result envelopes;
- tool gateway decisions;
- role separation;
- refs-only ledgers, checkpoints, and diagnostics.

MissionForge core must not own:

- product-specific memory semantics;
- hidden skill or tool routing;
- product acceptance decisions;
- filesystem installation policy;
- implicit persistent caches;
- implicit user workspace mutation.

## Current Problem

The active Kernel path is still filesystem-bound.

`src/missionforge/kernel/io.py` resolves every ref under a workspace root and
implements `write_json_ref`, `read_json_ref`, `write_jsonl_ref`, `hash_ref`,
and `ref_exists` by touching the local filesystem. `run_step`, `run_flow`,
`run_steps_batch`, inspection, progress, extension locks, and the Pi runtime
adapter all depend on that shape.

This creates several problems for a Python package:

- `workspace="."` makes the current process directory an implicit runtime
  target.
- Internal runtime records are materialized as files even when the caller only
  wants in-memory package behavior.
- ContextEngine records are durable by default, but durability is achieved by
  writing files rather than by an explicit store contract.
- Test fixtures and product integrations inherit filesystem assumptions.
- Adapter and extension code can silently introduce host side effects through
  temporary directories, install roots, or generated runtime input files.

The architectural issue is not that files exist. The issue is that file-backed
refs are the default and deeply embedded in the call graph.

## Non-Negotiable Laws

1. Raw chat is not operational task truth.
2. A frozen `TaskContract`, or an explicit revision, remains task authority.
3. Refs remain the durable identity and permission unit.
4. Execution workers may not self-accept their own work.
5. Semantic acceptance remains a separate Judge PiWorker or product-owned
   acceptance artifact.
6. Code may reject malformed, unauthorized, unsafe, stale, missing, or
   unreferenced records.
7. Code must not pretend to judge product-level semantic quality.
8. Runtime state should cite refs, hashes, event ids, versions, and store ids by
   default.
9. Raw prompts, provider payloads, tool output bodies, stdout/stderr bodies,
   artifact bodies, and secrets must not appear in operator-facing records by
   default.
10. Product semantics must not move into `src/missionforge`.
11. No default API may write to the filesystem.
12. Any external side effect must require an explicit caller-provided backend,
    mount, install root, or adapter configuration.

## Side Effect Policy

MissionForge must distinguish three categories:

### Import-Time Effects

Allowed:

- class/function definitions;
- local constant construction;
- lazy module imports required by Python.

Forbidden:

- creating files or directories;
- reading user auth/config files;
- opening sockets;
- starting subprocesses;
- installing extensions;
- creating temp directories;
- writing telemetry;
- probing provider credentials.

### Default Runtime Effects

Allowed:

- mutations inside caller-provided in-memory stores;
- provider calls only when the caller explicitly invokes a runtime function and
  supplies adapter/provider configuration;
- deterministic validation of Python objects.

Forbidden:

- writing to `.` by default;
- writing to `/tmp` by default;
- creating `.missionforge` by default;
- installing packages by default;
- materializing sandbox workspaces by default;
- reading host files by ref unless the caller provided a filesystem-backed
  store or explicit mount.

### Explicit Runtime Effects

Allowed only with explicit caller configuration:

- `FileRefStore(root=...)`;
- `SqliteRefStore(path=...)`;
- `ObjectRefStore(...)`;
- sandbox workspace mounts;
- extension install roots;
- provider config file discovery;
- local coding-agent filesystem tools.

These effects are user-selected storage or execution backends, not hidden core
behavior.

## Core Abstraction

Introduce a product-neutral runtime storage boundary:

```python
class RefStore(Protocol):
    store_id: str

    def exists(self, ref: str) -> bool: ...
    def read_bytes(self, ref: str) -> bytes: ...
    def write_bytes(
        self,
        ref: str,
        body: bytes,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord: ...
    def append_jsonl(self, ref: str, item: Mapping[str, Any]) -> RefRecord: ...
    def hash_ref(self, ref: str) -> str: ...
    def list_refs(self, prefix: str = "") -> list[str]: ...
```

`RefStore` is the runtime record plane. It should support JSON records,
JSONL events, context views, ledgers, permission manifests, and small
artifacts.

`ArtifactStore` remains useful for immutable versioned artifact bodies. The
refactor should avoid forcing every runtime record through the versioned
artifact path, because event logs and snapshots have different mutation
semantics.

Recommended store family:

```text
RefStore
  MemoryRefStore       default package runtime, volatile, no filesystem effects
  FileRefStore         explicit filesystem materialization backend
  SqliteRefStore       optional durable single-file backend
  ObjectRefStore       optional external object store / database backend
```

The first implementation should add `MemoryRefStore` and `FileRefStore`.
`SqliteRefStore` and external stores are deferred until the interface is stable.

## Runtime Shape

New package entry points should prefer explicit runtime objects:

```python
from missionforge import MemoryRefStore, MissionForgeRuntime

store = MemoryRefStore()
runtime = MissionForgeRuntime(store=store, adapter=adapter)
result = runtime.run_step(step)
```

The old shape:

```python
run_step(step, workspace=".")
```

should become a compatibility path, not the recommended API.

The compatibility path may remain temporarily, but it must be implemented as:

```text
workspace path -> explicit FileRefStore(root=workspace)
```

It must not be the default.

## Data Plane Design

### RefRecord

Add a small record for store writes:

```text
RefRecord
  ref
  content_hash
  size_bytes
  media_type
  materialization_state
  store_id
  created_at
  metadata
```

This is not product semantics. It is evidence metadata for runtime storage.

### MemoryRefStore

Requirements:

- no filesystem writes;
- canonical JSON hashing for structured records;
- immutable bytes per write unless an explicit append API is used;
- JSONL append support for run events and ledgers;
- deterministic `hash_ref` for missing refs;
- refs-only metadata validation;
- no raw prompt/provider/tool bodies in metadata.

Memory-only state is volatile. It can be the default package behavior, but it
cannot claim crash recovery.

### FileRefStore

Requirements:

- explicit root;
- no default root;
- no path traversal;
- atomic writes where practical;
- body hash verification on read;
- JSONL append support;
- compatible with existing workspace refs for migration;
- no package import side effects.

### Durable Store Tradeoff

MissionForge cannot provide both of these at the same time without an explicit
external backend:

```text
no external side effects
crash recovery after process death
```

The default `MemoryRefStore` gives no filesystem side effects and no crash
recovery.

Long-running unattended systems must provide an explicit durable store. That
store can be filesystem-backed, SQLite-backed, database-backed, or object-store
backed. The key is that the side effect belongs to the host application by
configuration, not to MissionForge by default.

## ContextEngine Changes

ContextEngine should compile context into store records, not files.

Current durable records remain conceptually valid:

- context policy;
- compile request;
- context projection;
- stable baseline;
- source snapshot;
- epoch;
- cache layout;
- pressure;
- turn safe point;
- turn boundary;
- checkpoint;
- compile result;
- reduction request/result;
- compaction record;
- thrash diagnostics.

The change is:

```text
write_json_ref(workspace, ref, payload)
```

becomes:

```text
store.write_json(ref, payload)
```

Provider-facing prompt rendering remains ephemeral. `ContextView` remains a
refs-only durable layout and diagnostics record. Raw provider messages and raw
tool bodies must still not be stored in ContextView.

Context compilation must still run permission filtering before source
selection:

```text
ContextSource refs
  -> ReadGate
  -> source admission / denial metadata
  -> ContextView
```

## Kernel API Changes

### Step Execution

Target signature:

```python
def run_step(
    step: Step,
    *,
    context: StepCompileContext,
    store: RefStore | None = None,
    runtime: MissionForgeRuntime | None = None,
    adapter: PiWorkerCallAdapter | None = None,
    ...
) -> StepRunResult:
```

Default behavior:

- if no store is supplied, create an internal `MemoryRefStore`;
- return the store or expose it through the result/runtime object;
- do not write to `.` or `/tmp`;
- do not install extensions;
- do not materialize a sandbox workspace.

Compatibility behavior:

```python
run_step(..., workspace="/path")
```

may remain as a deprecated alias for:

```python
run_step(..., store=FileRefStore("/path"))
```

### Flow Execution

`run_flow` should use one shared `RefStore` for all step records, route
artifacts, ledgers, context records, and final result records.

Flow-level concurrency must use store-level conflict checks:

- duplicate output refs are rejected before execution;
- concurrent writes to the same ref fail closed;
- batch execution never relies on shared filesystem directories for isolation.

### Inspection

Inspection should read from a `RefStore`:

```python
inspect_kernel_run(store, flow_result_ref)
```

The CLI can still accept `--workspace`, but that should construct a
`FileRefStore` explicitly inside the adapter layer.

## PiWorker Runtime Adapter Changes

The Pi sidecar currently expects filesystem paths and writes runtime input,
output, savepoints, diagnostics, and projection files.

This must become an adapter-specific materialization boundary, not a core
runtime assumption.

Target modes:

### Pure Package Mode

No filesystem tools. No sidecar workspace materialization.

Useful for:

- provider-only PiWorker calls;
- tests;
- products whose tools are logical APIs rather than host filesystem tools;
- context compilation and judgment over in-memory artifacts.

### Explicit Sandbox Mode

The caller provides a sandbox backend:

```python
SandboxWorkspace(
    root=Path(...),
    materialize_refs=[...],
    capture_refs=[...],
)
```

Only this mode may write to the host filesystem.

The adapter may materialize selected refs into the sandbox workspace, execute
Pi, then capture declared output refs back into `RefStore`.

Rules:

- no implicit temp directory;
- no implicit `.missionforge`;
- no implicit cwd;
- no implicit extension install;
- all materialized refs must pass ReadGate;
- all captured refs must pass WriteGate;
- tool observations and stdout/stderr bodies remain bounded projections or refs,
  not operator-facing raw state.

## Tool And Extension Changes

Core tools should be capability names, not filesystem operations by default.

Recommended split:

```text
logical tools
  read_ref
  write_ref
  edit_ref
  emit_progress
  append_event

filesystem-backed tools
  read_file
  write_file
  edit_file
  bash
```

`read_ref` and `write_ref` operate through `RefStore`.

`read_file`, `write_file`, `edit_file`, and `bash` require explicit sandbox
workspace configuration.

Extension installation must also be explicit:

- `verify-installed` requires a caller-supplied install root or package index;
- `install` requires explicit installer approval/configuration;
- no extension compile path may default to `.missionforge/extensions`.

## Progress, Observation, And Ledger Changes

The following modules should move from path-based helpers to store-backed
helpers:

- `progress_stream.py`;
- `observation.py`;
- `decision_ledger.py`;
- `piworker_progress.py`;
- `piworker_batch.py`;
- `kernel/inspect.py`.

Design rule:

```text
core modules accept RefStore
CLI adapters may construct FileRefStore
product integrations may choose durable stores
```

Operator output remains refs-only.

## API Boundary Changes

Package root may export product-neutral store primitives once stable:

```text
RefRecord
RefStore
MemoryRefStore
FileRefStore
MissionForgeRuntime
```

Do not export:

- product-specific stores;
- adapter-private sidecar materializers;
- provider credential readers;
- extension installer helpers as default root API;
- filesystem CLI convenience wrappers.

The root API should make the no-side-effect path obvious.

## Migration Plan

### Current Implementation Snapshot

Status as of 2026-06-29:

- `RefRecord`, `RefStore`, `MemoryRefStore`, and `FileRefStore` exist.
- `kernel/io.py` is now a compatibility layer that accepts either a `RefStore`
  or a filesystem workspace path.
- `run_step(..., store=MemoryRefStore(), adapter=store_aware_adapter)` can run
  one complete fixture step without creating files.
- `run_flow(..., store=MemoryRefStore(), adapter=store_aware_adapter)` can run a
  small routed executor -> judge fixture flow without creating files.
- `run_steps_batch(..., store=MemoryRefStore(), adapter_factory=...)` can run
  independent fixture steps without creating files.
- `run_piworker_call_batch(..., store=MemoryRefStore(), adapter_factory=...)`
  can run independent already-compiled PiWorker calls without creating files.
- `run_flow_step_once(...)` now defaults to a memory-backed debug run unless a
  filesystem workspace is explicitly supplied.
- Public observation helpers can append/read run events and snapshots through
  `RefStore` or an explicit filesystem path.
- Progress streams can append/read/render events through `RefStore` or an
  explicit filesystem path.
- Interaction ports can project and acknowledge user events through `RefStore`
  or an explicit filesystem path.
- `inspect_kernel_run(store, flow_result_ref)` can inspect memory-backed flow
  records, run events, snapshots, ledgers, step records, metrics, context
  records, and tool observation JSONL refs without materializing files.
- The PiWorker progress bridge can tail runtime events and expected artifact
  refs from `RefStore` or an explicit filesystem path.
- If `run_step` receives neither `store` nor `workspace`, it creates an internal
  `MemoryRefStore` and exposes it through `StepRunResult.store`.
- `workspace=...` remains supported and maps to an explicit `FileRefStore`.
- `run_piworker_call(..., store=...)` passes the store only to adapters that
  declare a `store` parameter or accept `**kwargs`; legacy adapters remain
  compatible.
- RefStore-only `run_step` can verify an existing extension lock record from
  the selected store, but fails closed if it would need to compile, install, or
  otherwise materialize extension packages without an explicit filesystem
  workspace.
- `FileRefStore` construction and read-style helpers no longer create missing
  workspace directories; directories are created only by explicit writes.
- `MemoryRefStore` and `FileRefStore` use method-level locks so parallel step
  batches can share one store without unsynchronized dictionary or JSONL
  mutations.
- Default `run_piworker_call(call)` now fails closed without an explicit
  filesystem workspace instead of using cwd.
- The default Pi sidecar adapter requires an explicit filesystem workspace and
  no longer records raw stdout/stderr bodies in evidence events.

Still incomplete:

- extension installation and sidecar materialization remain filesystem-oriented
  and must not yet be advertised as no-side-effect default package runtime
  surfaces.
- The default Pi sidecar adapter is still a filesystem materialization adapter.
  Pure package mode requires a store-aware adapter.
- Store-level write conflict checks are not yet implemented.
- Static side-effect boundary tests are not yet implemented.
- `MissionForgeRuntime` has not been introduced.

### Phase 0: Side Effect Audit

Status: partially complete.

Deliverables:

1. Add tests that importing `missionforge` creates no files under cwd or `/tmp`.
2. Add tests that default `run_step` with a fixture adapter does not create
   filesystem entries.
3. Add a static boundary test that core modules do not call `Path(".")`,
   `TemporaryDirectory`, `tempfile`, or workspace write helpers except through
   approved backend modules.
4. Document every remaining explicit filesystem entry point.

Exit criteria:

- all implicit filesystem side effects are named;
- the migration has a measurable baseline.

### Phase 1: Introduce RefStore

Status: complete.

Deliverables:

1. Add `RefRecord`, `RefStore`, `MemoryRefStore`, and `FileRefStore`.
2. Move JSON, JSONL, hash, and existence operations behind the store boundary.
3. Keep `kernel/io.py` as compatibility wrappers over `FileRefStore`.
4. Add tests for memory store hashing, append, missing refs, refs-only metadata,
   and no filesystem writes.
5. Add tests proving `FileRefStore` preserves current workspace behavior.

Exit criteria:

- new store-backed helpers can replace `write_json_ref`, `read_json_ref`,
  `write_jsonl_ref`, `hash_ref`, and `ref_exists`;
- old filesystem tests still pass through compatibility wrappers.

### Phase 2: Store-Backed Kernel Step

Status: partially complete.

Deliverables:

1. Add `store=` to `run_step`.
2. Route step spec, permission manifest, context records, PiWorker call/result,
   step records, and validation reports through `RefStore`.
3. Make no supplied store mean `MemoryRefStore`, not `workspace="."`.
4. Keep `workspace=` as deprecated compatibility sugar for `FileRefStore`.
5. Update tests to assert memory-backed `run_step` creates no files.

Exit criteria:

- a complete step can run with fixture adapter and memory store only;
- step result refs are readable from the returned/runtime store;
- filesystem behavior is opt-in.

Completed in the first implementation slice:

- `store=` was added to `run_step`.
- step spec, permission manifest, ContextEngine records, PiWorker call/result,
  step records, validation reports, hashes, token estimates, and resume reuse
  records are routed through the selected `RefStore`.
- no supplied `store` or `workspace` now means an internal `MemoryRefStore`.
- `StepRunResult.store` exposes the selected store for package callers.
- `workspace=` remains compatibility sugar for `FileRefStore`.
- store-aware adapters can receive the selected store through
  `run_piworker_call(..., store=...)`.
- memory-backed fixture tests prove a complete step can run without filesystem
  writes.

Remaining Phase 2 work:

- add a deprecation warning or migration note for `workspace=`.
- decide whether `StepRunResult.store` is the final public surface or whether a
  `MissionForgeRuntime` wrapper should own store access.
- broaden memory-backed tests for blocked preflight, retry exhaustion, invalid
  output, and resume skip behavior.

### Phase 3: Store-Backed ContextEngine

Status: partially complete for `run_step`, not complete as an independent
ContextEngine boundary.

Deliverables:

1. Route ContextEngine compile records through `RefStore`.
2. Route working-set reads and context-feed reads through `RefStore`.
3. Preserve ReadGate filtering before source admission.
4. Preserve refs-only ContextView records.
5. Add memory-backed tests for pressure, checkpoint, compaction failure, and
   reducer result validation.

Exit criteria:

- ContextEngine no longer requires a workspace path;
- all context records remain replayable from the selected store;
- no raw prompts, provider payloads, or raw tool bodies appear in store metadata
  or operator views.

Completed in the first implementation slice:

- Context compile records emitted by `run_step` are written to `RefStore`.
- working-set reads, context-feed reads, context source hashes, and token
  estimates in `run_step` use store helpers.
- ReadGate filtering remains before source admission.

Remaining Phase 3 work:

- add standalone ContextEngine memory-store tests for pressure, checkpoint,
  reducer success, reducer failure, and thrash diagnostics.
- make any public ContextEngine compile helper accept `RefStore` directly if it
  gains persistence responsibility outside `run_step`.

### Phase 4: Store-Backed Flow And Batch

Status: partially complete for `run_flow`, `run_steps_batch`, and
`run_piworker_call_batch`.

Deliverables:

1. Add `store=` to `run_flow` and `run_steps_batch`.
2. Use store-level conflict checks for output refs and write roots.
3. Route flow ledgers, route decisions, flow results, batch specs, batch
   results, and per-step context refs through `RefStore`.
4. Preserve independent step namespaces without relying on directories.
5. Add memory-backed batch tests proving parallel fan-out/fan-in has no
   filesystem side effects.

Exit criteria:

- Flow and batch APIs can run entirely in memory with fixture adapters;
- opt-in FileRefStore behavior remains compatible.

Completed in the second implementation slice:

- `store=` was added to `run_flow`.
- no supplied `store` or `workspace` now means one shared internal
  `MemoryRefStore` for the whole flow.
- flow execution ids, run events, snapshots, ledgers, route decisions, context
  feed refs, context thrash diagnostics refs, flow results, and step calls use
  the selected store.
- `FlowRunResult.store` exposes the selected store.
- memory-backed flow tests prove a small routed executor -> judge flow can run
  without filesystem writes.
- `store=` was added to `run_steps_batch`.
- no supplied `store` or `workspace` now means one shared internal
  `MemoryRefStore` for the whole step batch.
- batch runtime exception records are written through the selected store.
- `StepBatchResult.store` exposes the selected store.
- memory-backed batch tests prove independent steps can run without filesystem
  writes.
- `store=` was added to `run_piworker_call_batch`.
- no supplied `store` or `workspace` now means one shared internal
  `MemoryRefStore` for the whole PiWorker call batch.
- batch spec, call result refs, runtime error refs, execution reports, and batch
  result records are written through the selected store.
- default file evidence/progress records are only materialized when a filesystem
  workspace/FileRefStore is selected.
- `PiWorkerCallBatchResult.store` exposes the selected store.
- memory-backed PiWorker batch tests prove independent calls can run without
  filesystem writes.

Remaining Phase 4 work:

- add store-level conflict checks for parallel writes.
- clarify projector behavior for pure in-memory projections versus explicit
  filesystem materialization.

### Phase 5: Adapter Materialization Boundary

Status: not started.

Deliverables:

1. Split pure package PiWorker calls from filesystem-backed sidecar calls.
2. Add explicit sandbox materialization configuration.
3. Make sidecar workspace creation impossible without explicit sandbox config.
4. Capture sidecar outputs back into `RefStore` through WriteGate.
5. Keep raw stdout/stderr/tool bodies behind refs or bounded projections.

Exit criteria:

- package default runtime does not create adapter files;
- filesystem sidecar execution is explicit and audited;
- missing sandbox config fails closed when filesystem tools are requested.

### Phase 6: Progress, Observation, Inspection, Extensions

Status: partially complete.

Deliverables:

1. Move progress streams to `RefStore`.
2. Move run events and snapshots to `RefStore`.
3. Move inspection to `RefStore`.
4. Move extension locks to `RefStore` records while keeping installation
   explicit.
5. Keep CLI workspace flags as adapter-level `FileRefStore` construction.

Exit criteria:

- core observation surfaces no longer require paths;
- CLI remains useful as a filesystem-backed adapter;
- package root remains side-effect free.

Completed in the third and fourth implementation slices:

- `append_run_event`, `read_run_events`, `write_run_snapshot`,
  `read_run_snapshot`, and `latest_run_snapshot` accept `RefStore | str | Path`.
- `ProgressStreamWriter`, `append_progress_event`, `read_progress_events`, and
  `stream_progress` accept `RefStore | str | Path`.
- `kernel/io.py` exposes `read_jsonl_ref` through the store boundary.
- `inspect_kernel_run` accepts `RefStore | str | Path` and reads flow ledgers
  and tool-observation JSONL refs through the selected store instead of direct
  path reads.
- `StoreInteractionPort` provides a store-backed interaction plane while
  `FileInteractionPort` remains explicit filesystem compatibility.
- `run_flow` accepts the generic interaction port, so store-backed safe-point
  projections and acknowledgements work in memory-backed flow runs.
- `PiWorkerProgressBridge` can tail runtime event JSONL and expected artifact
  refs from a `RefStore` or an explicit filesystem path.
- Memory-backed observation, progress, and inspection tests prove these public
  surfaces can operate without filesystem writes.
- Memory-backed interaction and PiWorker progress tests prove these surfaces can
  operate without filesystem writes.
- A static side-effect boundary test now guards core modules against new
  implicit `Path('.')` / `TemporaryDirectory` patterns outside explicit
  backend modules.
- Extension lock records can now be read and written through `RefStore` while
  compile/install materialization stays explicitly file-backed.

Remaining Phase 6 work:

- keep CLI workspace flags as adapter-level `FileRefStore` construction.

### Phase 7: Deprecation And API Cleanup

Status: not started.

Deliverables:

1. Mark `workspace="."` defaults as deprecated.
2. Update README, Getting Started, User Manual, and Cookbook to show
   `MemoryRefStore` first.
3. Keep filesystem examples under an explicit "durable file backend" section.
4. Add public API boundary tests for store exports.
5. Add import-side-effect and default-runtime-side-effect tests to CI.

Exit criteria:

- new users see a no-side-effect Python package API first;
- filesystem behavior is visibly opt-in;
- compatibility paths are documented and tested.

## Testing Strategy

Add tests in this order:

1. `tests/test_import_side_effects.py`
   - import package in a clean cwd;
   - assert no new files or directories are created.

2. `tests/test_ref_store.py`
   - memory write/read/hash;
   - JSON canonical hash;
   - JSONL append;
   - missing ref hash;
   - refs-only metadata rejection;
   - no filesystem writes.

3. `tests/test_kernel_memory_store.py`
   - run one step with fixture adapter and `MemoryRefStore`;
   - assert step records and context records live in the store;
   - assert cwd remains unchanged.

4. `tests/test_context_engine_memory_store.py`
   - compile context through memory store;
   - deny unreadable refs;
   - handle pressure/checkpoint;
   - validate reducer success and failure boundaries.

5. `tests/test_flow_memory_store.py`
   - run a small executor -> judge flow entirely in memory;
   - assert no worker self-acceptance;
   - assert route artifacts and ledgers are store records.

6. Compatibility tests
   - existing workspace behavior through `FileRefStore`;
   - CLI inspection through explicit file backend;
   - extension lock verify/install with explicit install root.

## Compatibility Rules

Existing filesystem users should not be broken abruptly.

Temporary compatibility layer:

```text
workspace=path
  -> FileRefStore(root=path)
```

But:

- `workspace="."` must stop being the default;
- docs should stop teaching workspace-first usage;
- deprecation warnings should point to `store=MemoryRefStore()` or
  `store=FileRefStore(root=...)`;
- hidden fallback to cwd is forbidden.

## Risk Register

### Risk: Store Abstraction Becomes A Database Framework

Mitigation:

- keep `RefStore` minimal;
- do not add query language;
- do not add vector retrieval;
- do not add product memory semantics;
- add only operations required by current refs, hashes, JSON records, and event
  logs.

### Risk: Memory Store Weakens Auditability

Mitigation:

- mark memory records as volatile;
- never claim crash recovery with memory-only store;
- require explicit durable backend for unattended long-running production runs;
- preserve hashes and refs in all stores.

### Risk: Adapter Materialization Reintroduces Hidden Files

Mitigation:

- make sandbox materialization explicit;
- fail closed when filesystem tools are requested without sandbox config;
- test cwd and `/tmp` remain unchanged by default runtime calls.

### Risk: Product Semantics Sneak Into Core Store Logic

Mitigation:

- store only bytes, JSON records, refs, hashes, metadata, and event records;
- keep skill, research, report, benchmark, finance, and customer semantics in
  product integrations.

### Risk: Long-Running Stability Is Oversold

Mitigation:

- document that memory-only mode is no-side-effect but not crash-recoverable;
- define "unattended stable" as requiring explicit durable store,
  checkpoint/replay tests, and adapter recovery tests.

## Definition Of Done

This refactor is complete when:

1. Importing MissionForge has no filesystem, network, subprocess, install, or
   temp-directory side effects.
2. Default package runtime uses `MemoryRefStore` and does not write to cwd or
   `/tmp`.
3. `run_step`, `run_flow`, and `run_steps_batch` can execute fixture PiWorker
   flows entirely in memory.
4. ContextEngine records are store-backed, refs-only, and permission-filtered.
5. Filesystem materialization is available only through explicit `FileRefStore`
   or explicit sandbox configuration.
6. Pi sidecar filesystem tools fail closed without explicit sandbox
   materialization.
7. Existing filesystem-backed workflows still work through explicit file
   backend configuration.
8. Operator views remain refs-only and do not expose raw prompts, provider
   payloads, raw tool bodies, stdout/stderr bodies, artifact bodies, or secrets.
9. Tests prove import-time no-side-effect, default-runtime no-side-effect,
   store-backed Kernel execution, store-backed ContextEngine execution, and
   explicit filesystem compatibility.
10. Documentation teaches the package-first, no-side-effect path before the
    filesystem-backed path.

## Recommended First Slice

Start small:

```text
RefRecord
RefStore
MemoryRefStore
FileRefStore
store-backed JSON/hash helpers
one memory-backed run_step fixture test
```

Do not start with Pi sidecar materialization or extension installation. Those
are adapter-level side effects and should be migrated only after Kernel and
ContextEngine no longer require filesystem refs.

The first slice succeeds if a product author can do this without creating any
files:

```python
from missionforge import MemoryRefStore
from missionforge.kernel import run_step

store = MemoryRefStore()
result = run_step(step, context=context, store=store, adapter=fixture_adapter)
```

and then inspect the refs from `store` rather than from a directory.
