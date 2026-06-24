# MissionForge Status

Last updated: 2026-06-24

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
| DeepResearch | Product integration; useful pressure test, not core architecture |
| Data model | Minimal `ArtifactRecord` / versioned ref slice implemented with durable filesystem and volatile memory stores |
| Context management | Phase 3 first slice implemented: refs-only `ContextView` diagnostics are emitted without changing PiWorker prompt behavior |
| Observation/control | Phase 4 first slices implemented: refs-only `RunEvent`, `RunSnapshot`, safe-point `ControlPort`, and Kernel run inspection primitives exist |
| Permission gates | Phase 1 hard `ReadGate` / `WriteGate` / `allowed_tools` boundaries implemented |

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

## In Progress

- Extend the ref-addressed information kernel beyond the first data-plane slice:
  - broader storage integration after hard gates
  - context projection over versioned artifact refs
  - runtime adoption without changing product integration semantics
- Harden context and observation adoption:
  - express more existing refs as `ArtifactRecord`;
  - pass richer context diagnostics through runtime/provider observations;
  - add debug stepping and replay helpers for fixture flows;
  - teach product UIs to consume `RunSnapshot`, `RunEvent`, and Kernel run
    inspection directly.

## Next Milestones

1. Keep `ReadGate`, `WriteGate`, and `ToolGateway` in front of all new storage
   behavior.
2. Adopt `ArtifactRecord` in more existing step/output refs without weakening
   filesystem compatibility.
3. Extend the minimal Kernel inspect hook toward fixture-flow debug stepping.
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

Latest known passing checks on 2026-06-24:

```bash
python3 -m py_compile src/missionforge/artifacts.py src/missionforge/__init__.py tests/test_artifacts.py tests/test_public_api_boundary.py
PYTHONPATH=src python3 -m unittest tests/test_artifacts.py tests/test_public_api_boundary.py
python3 -m py_compile src/missionforge/permissions.py src/missionforge/runtime_control.py src/missionforge/task_contract.py src/missionforge/task_projection.py src/missionforge/workspace_runtime.py src/missionforge/adapters/pi_agent_runtime.py src/missionforge/kernel/compiler.py tests/test_permissions.py tests/test_runtime_control.py tests/test_workspace_runtime.py tests/test_task_contracts.py tests/test_pi_agent_runtime_adapter.py
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src:integrations/deepresearch/src python3 -m unittest discover -s integrations/deepresearch/tests
cd workers/pi-agent-runtime && npm test
```

Observed results:

- Context/observation/kernel inspection/public API focused tests: 22 run, OK.
- Core tests: 249 run, OK, 1 skipped.
- DeepResearch integration tests: 45 run, OK.
- Pi agent runtime tests: 11 node test files, OK.
