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
| Data model | Current implementation remains filesystem-ref-backed; ref-addressed data model is planned |
| Context management | Current context path is still mostly file/projection based; `ContextView` plan is next |
| Observation/control | Basic progress and interaction safe points exist; richer inspect/debug/control plane is planned |
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

## In Progress

- Define the ref-addressed information kernel:
  - `ArtifactRecord`
  - versioned refs
  - storage-independent artifact identity
  - durable vs volatile materialization states
- Prepare the next data-plane slice after gates:
  - `ArtifactRecord`
  - versioned refs
  - storage-independent artifact identity
  - durable vs volatile materialization states
- Define context management primitives:
  - `ContextSegment`
  - `ContextView`
  - stable prefix / semi-stable context / volatile tail
  - tool observation demotion and compaction rules
- Define observation and control interfaces:
  - event stream
  - run snapshot
  - safe-point intervention
  - debug stepping

## Next Milestones

1. Add minimal core contracts for `ArtifactRecord` and versioned refs.
2. Keep `ReadGate`, `WriteGate`, and `ToolGateway` in front of all new storage
   behavior.
3. Add `ContextView` diagnostics without changing PiWorker behavior yet.
4. Upgrade Kernel API to compile steps against the new data/context primitives.
5. Use DeepResearch only as an integration pressure test after core boundaries
   are proven.

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
python3 -m py_compile src/missionforge/permissions.py src/missionforge/runtime_control.py src/missionforge/task_contract.py src/missionforge/task_projection.py src/missionforge/workspace_runtime.py src/missionforge/adapters/pi_agent_runtime.py src/missionforge/kernel/compiler.py tests/test_permissions.py tests/test_runtime_control.py tests/test_workspace_runtime.py tests/test_task_contracts.py tests/test_pi_agent_runtime_adapter.py
PYTHONPATH=src python3 -m unittest discover -s tests
cd workers/pi-agent-runtime && npm test
```

Observed results:

- Core tests: 219 run, OK, 1 skipped.
- Pi agent runtime tests: 86 passed.
