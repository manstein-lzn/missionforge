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

- Extend the ref-addressed information kernel beyond the first data-plane slice:
  - broader storage integration after hard gates
  - context projection over versioned artifact refs
  - runtime adoption without changing product integration semantics
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

1. Keep `ReadGate`, `WriteGate`, and `ToolGateway` in front of all new storage
   behavior.
2. Add `ContextView` diagnostics without changing PiWorker behavior yet.
3. Upgrade Kernel API to compile steps against the new data/context primitives.
4. Use DeepResearch only as an integration pressure test after core boundaries
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
python3 -m py_compile src/missionforge/artifacts.py src/missionforge/__init__.py tests/test_artifacts.py tests/test_public_api_boundary.py
PYTHONPATH=src python3 -m unittest tests/test_artifacts.py tests/test_public_api_boundary.py
python3 -m py_compile src/missionforge/permissions.py src/missionforge/runtime_control.py src/missionforge/task_contract.py src/missionforge/task_projection.py src/missionforge/workspace_runtime.py src/missionforge/adapters/pi_agent_runtime.py src/missionforge/kernel/compiler.py tests/test_permissions.py tests/test_runtime_control.py tests/test_workspace_runtime.py tests/test_task_contracts.py tests/test_pi_agent_runtime_adapter.py
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src:integrations/deepresearch/src python3 -m unittest discover -s integrations/deepresearch/tests
cd workers/pi-agent-runtime && npm test
```

Observed results:

- Artifact/public API focused tests: 15 run, OK.
- Core tests: 232 run, OK, 1 skipped.
- DeepResearch integration tests: 45 run, OK.
- Pi agent runtime tests: 88 passed.
