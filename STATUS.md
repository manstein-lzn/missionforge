# MissionForge Status

Last updated: 2026-06-28

Active branch: `feature/ref-addressed-agent-toolkit`

Base commit: `9ad0b5c`

## Current Objective

Refactor MissionForge into a small, product-neutral, refs-first agent toolkit:

```text
trusted host Python owns orchestration
MissionForge owns contracts, permissions, sandbox, refs, context, tools, audit, and judge boundaries
PiWorker owns semantic work
```

The immediate focus is to preserve MissionForge's white-box safety model while
removing the disk-first assumption from data and context movement.

## Current Position

| Area | Status |
| --- | --- |
| Git hygiene | `main` pushed; old local and remote branches removed; new working branch created |
| Core direction | Product-neutral PiWorker-centered toolkit, not a workflow framework |
| Kernel API | Kept as a thin developer-friendly facade over core primitives |
| DeepResearch | Product integration; now consumes Kernel status view as pressure test, not core architecture |
| Data model | Minimal `ArtifactRecord` / versioned ref slice implemented with durable filesystem and volatile memory stores |
| Context management | Package-managed ContextEngine preflight, checkpointing, managed reducer invocation, refs-only compaction records, fresh recompile, first provider-turn lowering, and runtime repeated-read thrash routing are implemented; soak/restart hardening remains |
| Observation/control | Phase 4 slices implemented: refs-only `RunEvent`, `RunSnapshot`, safe-point `ControlPort`, Kernel run inspection, fixture debug stepping, replay planning, and a richer read-only status observer exist; DeepResearch TUI now routes runtime controls through the shared control port |
| Host cookbook | Minimal product-neutral Kernel host example added under `examples/` |
| Permission gates | Phase 1 hard `ReadGate` / `WriteGate` / `allowed_tools` boundaries implemented |
| Parallel PiWorker calls | First isolated fan-out/fan-in primitive implemented: low-level call batches plus Kernel step batches; shared writes, reducers, merge, and parallel flow routing remain out of scope |

## Completed Recently

- Cleaned branch topology so only `main` and the active feature branch remain.
- Committed and pushed the latest DeepResearch flow and architecture documents.
- Added the architecture proposal describing refs-first vs disk-first separation.
- Clarified that MissionForge should be a toolkit embedded in host systems, not
  a LangGraph-style containing framework.
- Clarified that Kernel API is a facade/compiler for developer ergonomics, not
  the core authority model.
- Implemented Phase 1 Gates Before Storage:
  - `PermissionManifest` and `SandboxProfile` carry `allowed_tools`;
  - Python `ReadGate` and `WriteGate` enforce ref boundaries before storage changes;
  - PiWorker writes to runtime-owned roots are rejected through `WriteGate`;
  - Kernel `Step.tools` compile to concrete allowed tool names;
  - the Pi agent sidecar mounts only allowed tools and checks the gateway before
    tool effects, including direct bash command/cwd/env authorization paths;
  - extension tools are gateway-wrapped and cannot shadow core tool names.
- Implemented Phase 3 Context View Diagnostics first slice:
  - added refs-only `ContextSegment`, `ContextView`, `ToolObservation`, and
    context pressure diagnostics;
  - Kernel `run_step` writes `context_projection.json` beside the step record;
  - step records include `context_projection_ref` and `context_hash`;
  - diagnostics remain advisory and do not change PiWorker runtime behavior.
- Implemented Phase 4 Observation/Control first slice:
  - added `RunEvent`, `RunSnapshot`, `ControlPort`, and `FileControlPort`;
  - Kernel `run_flow` writes execution-scoped `observation/run_events.jsonl`
    and `observation/run_snapshot.json`;
  - pause/cancel/revision requests stop at safe points; `stop_after_current_turn`
    lets the current step finish before blocking route progression;
  - observation state remains refs-only and does not embed user text, prompts,
    tool bodies, provider payloads, or stdout/stderr.
- Added minimal Kernel/DeepResearch alignment:
  - Kernel flow results expose `run_events_ref` and `run_snapshot_ref` through
    metadata;
  - DeepResearch result packages surface those refs for product UIs and debug
    tools without moving research semantics into core.
- Added a product-neutral Kernel run inspection helper:
  - `missionforge.kernel.inspect_kernel_run()` reads `FlowResult`,
    `RunSnapshot`, `RunEvent`, `FlowLedgerEvent`, and `StepRecord` refs;
  - inspection output stays refs-only and does not expand artifact bodies,
    PiWorker prompts, execution reports, provider payloads, tool bodies, or
    safe-point user text;
  - mixed `ledger_refs` are handled conservatively so projection records remain
    refs and are not parsed as flow JSONL ledgers.
- Added first fixture-flow debug stepping primitives:
  - `preview_flow_step()` returns refs/hash/tool/permission/context boundary
    summaries without writing files;
  - `run_flow_step_once()` runs one explicit step under a caller-chosen debug
    ref prefix and does not create flow result, ledger, or snapshot records;
  - `read_flow_route()` resolves structured decision artifacts into safe
    `step`, `stop`, `unrouted`, or `invalid` route decisions without exposing
    decision prose or malformed raw values.
- Added a minimal refs-only replay planning helper:
  - `ContextReplayPlan` and `build_context_replay_plan()` capture checkpoint,
    source refs, summary refs, and denied/allowed replay refs without turning
    replay into a second runtime;
  - the helper stays explicit about refs and permissions instead of hydrating
    hidden memory.
- Added a minimal host cookbook example that demonstrates ordinary Python code
  using `StepCompileContext`, `Flow`, `preview_flow_step()`,
  `run_flow_step_once()`, `run_flow()`, `read_flow_route()`, and
  `inspect_kernel_run()` without pulling in DeepResearch semantics.
- Added a minimal read-only host adapter CLI:
  - `python -m missionforge.adapters.cli tui` / `status` renders a refs-only
    `MissionRunView` from `inspect_kernel_run()`;
  - JSON and plain text output include statuses, counts, refs, token usage,
    context pressure, tool observation refs, latest event age, and safe-point
    details without expanding artifact bodies, prompts, provider payloads, or
    tool output.
- Wired DeepResearch TUI to the product-neutral Kernel status view:
  - `state/run_status.json` carries Kernel flow/event/snapshot refs;
  - `/status` and final result views render a `Kernel 状态` panel from
    `MissionRunView` while keeping DeepResearch semantics in the integration.
  - The panel now shows optional Kernel observer rows for usage totals, context
    pressure, latest event age, tool activity refs, and safe-point details when
    those refs/metrics exist.
  - Runtime user commands now go through `FileControlPort` (`/pause`,
    `/cancel`, `/resume`, `/checkpoint`, `/stop`, `/revise`) rather than
    appending interaction files directly in the TUI layer.
- Implemented the first minimal ContextEngine contract slice:
  - added `docs/MISSIONFORGE_CONTEXT_ENGINE_ARCHITECTURE.md` to define the
    refs-only context architecture, prompt-cache layout principles, working-set
    lifecycle, tool-output projection, turn boundary, and compaction model;
  - added product-neutral `ContextSource`, `ContextSourceSnapshot`,
    `ContextEpoch`, `ContextWorkingSet`, `ContextCacheLayout`,
    `ContextCompileRequest`, `ContextCompileResult`, `ContextTurnBoundary`,
    `ContextCompactionRecord`, `ContextReadObservation`, and
    `ContextThrashDiagnostics` contracts;
  - added `filter_context_sources()`, `build_context_epoch()`,
    `build_context_cache_layout()`, and `build_thrash_diagnostics()` helpers;
  - added `ToolOutputProjection` and `bound_tool_output()` so full tool outputs
    can be kept as raw refs while model-visible projections remain bounded;
  - exported the new primitives from the package root and documented them in
    `docs/PRIMITIVE_REFERENCE.md`.
- Wired the first ContextEngine runtime adoption slice into Kernel:
  - `run_step()` now writes source snapshot, context epoch, cache layout, turn
    safe point, turn boundary, and context compile result refs beside the
    existing `context_projection.json`;
  - normal and resume/skip step records preserve those refs in metadata;
  - `inspect_kernel_run()` and `python -m missionforge.adapters.cli status`
    surface the ContextEngine refs without expanding artifact bodies, prompts,
    provider payloads, or tool outputs.
- Added the first active Kernel compile/preflight boundary:
  - `compile_context_request()` compiles `ContextCompileRequest` through
    `ReadGate` into a deterministic `ContextView`, cache layout, pressure
    diagnostics, and `ContextCompileResult`;
  - `reconcile_context_epoch()` preserves compatible stable-prefix epochs and
    emits a new epoch when role, contract hash, permission manifest, or stable
    baseline changes;
  - Kernel `run_step()` now constructs a real context compile request before
    PiWorker invocation and writes `context/compile_request.json`,
    `context/pressure.json`, and the resulting compile refs;
  - input hashes and token estimates are derived only after `ReadGate`
    admission, so denied inputs can block without being content-read first;
  - denied required inputs and real hard checkpoint-before-next-turn pressure
    now block at the context safe boundary before any PiWorker adapter call.
- Connected the compiled ContextEngine boundary to provider-turn lowering:
  - Kernel context refs are passed to the Pi agent sidecar as a first-class
    `context_engine` envelope on runtime input;
  - the sidecar reads the compiled `ContextView` and `ContextCompileResult`
    before provider invocation and renders a bounded refs-only provider-turn
    context summary from admitted stable/semi-stable/volatile segments;
  - omitted and denied refs are not rendered, and the ephemeral provider text is
    not persisted as prompt/provider state.
- Made bounded retry reuse of ContextEngine boundaries explicit:
  - multi-attempt Kernel calls now mark inherited ContextEngine refs with
    `context_boundary_reuse: "same_preflight_boundary"` plus parent call,
    compile result, turn boundary, and epoch refs;
  - the Pi agent adapter rejects retry attempts that carry parent call metadata
    and ContextEngine refs without that same-boundary declaration.
- Connected runtime tool-output projection diagnostics to MissionForge records:
  - the Pi agent runtime already projects stale large tool results into provider
    stubs; the Python adapter now materializes those sidecar
    `projected_observations` as `ToolOutputProjection` records and bounded
    projection refs under `attempts/<call_id>/context/tool_output_projections/`;
  - execution reports expose `tool_output_projection_index_ref` and
    `tool_output_projection_count`, and changed refs include the index, record,
    and projection refs;
  - read/source refs can be represented as `ref_stub` projections without
    pretending they are raw output refs.
- Fed materialized tool-output projections into the next ContextEngine boundary:
  - Kernel flow execution carries bounded `ToolOutputProjection` record refs
    from one completed step to the next step's `ContextCompileRequest`;
  - the next step's `ReadGate` decides whether those projection records and
    projection text refs are admitted, so the feed does not grant raw-output or
    attempts-directory access by itself;
  - the Pi agent sidecar renders admitted tool-output projection text only after
    sidecar read permission and compiled hash checks pass.
- Implemented the package-managed ContextEngine reducer/compaction slice:
  - added `ContextCheckpoint`, `ContextReductionRequest`,
    `ContextReductionResult`, `ContextManagementPolicy`, and the
    `context_reducer_piworker` boundary;
  - Kernel now writes checkpoint refs at context pressure boundaries without
    host code;
  - hard pressure invokes a MissionForge-managed reducer call with a scoped
    maintenance permission manifest;
  - valid reducer output is boundary-validated, recorded as a refs-only state
    transition and `ContextCompactionRecord`, then followed by a fresh
    ContextEngine compile before the original worker call;
  - invalid or failed reducer output blocks safely with diagnostic refs and
    leaves the previous context view/epoch active.
- Implemented the first parallel PiWorker call primitive:
  - added `PiWorkerCallBatch`, `PiWorkerCallBatchResult`, and
    `run_piworker_call_batch(...)` for already-compiled independent calls;
  - added preflight conflict rejection for duplicate call ids, duplicate
    outputs, overlapping writable refs, and outputs outside writable roots;
  - isolated per-call result, evidence, progress, and structured runtime-error
    records under `piworker_batches/{batch_id}/calls/{call_id}/`;
  - added Kernel `StepBatchResult` and `run_steps_batch(...)`, reusing the
    existing `run_step(...)` path so ContextEngine, permission manifests,
    extension locks, resume checks, and step records remain per-step;
  - kept shared writes, reducers, automatic merge, product synthesis, and
    parallel `run_flow(...)` routing explicitly out of scope.

## In Progress

- Extend the ref-addressed information kernel beyond the first data-plane slice:
  - broader storage integration after hard gates
  - add checkpoint/compaction records after the new preflight boundary
  - runtime adoption without changing product integration semantics
- Harden context and observation adoption:
  - express more existing refs as `ArtifactRecord`;
  - extend debug stepping and replay planning for fixture flows;
  - keep the host cookbook example small and product-neutral.
- Harden ContextEngine beyond the first automatic compaction loops:
  - broaden repeated-read diagnostics across more tool/query observation forms;
  - soak-test hard-pressure and thrash-triggered reducer loops across many steps;
  - keep richer working-set semantics in product integrations while preserving
    core refs/hash/permission validation.

## Next Milestones

1. Keep `ReadGate`, `WriteGate`, and `ToolGateway` in front of all new storage
   behavior.
2. Adopt `ArtifactRecord` in more existing step/output refs without weakening
   filesystem compatibility.
3. Extend fixture-flow debug stepping and replay planning; the host
   cookbook slice is now present.
4. Use DeepResearch only as an integration pressure test while keeping prompts,
   rubrics, source tools, and report contracts in the integration package.

## Guardrails

- Do not add product semantics to `src/missionforge`.
- Do not build a workflow framework or graph DSL in core.
- Do not make Python judge domain quality in core.
- Do not replace file-backed refs with memory-only authority until gates,
  durability, and audit semantics are explicit.
- Do not expose a broad public API before one product integration and one small
  example prove the primitive shape.

## Verification Baseline

Latest known passing checks on 2026-06-26:

```bash
PYTHONPATH=src python3 -m unittest tests.test_context_engine tests.test_tool_projection tests.test_public_api_boundary -q
python3 -m py_compile src/missionforge/context_engine.py src/missionforge/tool_projection.py src/missionforge/__init__.py tests/test_context_engine.py tests/test_tool_projection.py tests/test_public_api_boundary.py
python3 -m py_compile src/missionforge/artifacts.py src/missionforge/__init__.py tests/test_artifacts.py tests/test_public_api_boundary.py
PYTHONPATH=src python3 -m unittest tests/test_artifacts.py tests/test_public_api_boundary.py
python3 -m py_compile src/missionforge/permissions.py src/missionforge/runtime_control.py src/missionforge/task_contract.py src/missionforge/task_projection.py src/missionforge/workspace_runtime.py src/missionforge/adapters/pi_agent_runtime.py src/missionforge/kernel/compiler.py tests/test_permissions.py tests/test_runtime_control.py tests/test_workspace_runtime.py tests/test_task_contracts.py tests/test_pi_agent_runtime_adapter.py
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src:integrations/deepresearch/src python3 -m unittest discover -s integrations/deepresearch/tests
```

Observed results:

- ContextEngine/public API focused tests: 13 run, OK.
- Core tests: 272 run, OK, 1 skipped.
- DeepResearch integration tests: 50 run, OK.
- Pi agent runtime tests were not rerun for this Python-only ContextEngine
  slice; the last known node baseline remains 11 test files OK.
