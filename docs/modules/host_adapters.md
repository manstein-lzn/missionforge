# Module: Host Adapters

## Goal

Expose MissionForge to external orchestrators without making them core
dependencies.

## Scope

- Python API
- CLI
- optional LangGraph node
- future HTTP service
- read-only observation surfaces
- explicit control request writers

## Non-Goals

- no LangGraph dependency in `missionforge` core
- no host-owned mission semantics
- no host-owned verifier, repair, or steering semantics
- no dashboard-owned routing or hidden runtime mutation

## Current Status

Goal 6C now implements an optional offline host adapter shell. It keeps the
primary integration path as `MissionIR -> MissionRuntime.run() ->
MissionResult`, adds a small CLI/Python wrapper around that path, adds
read-only observation summaries, and adds a writer for explicit
`ControlRequest` intent.

No required LangGraph dependency, HTTP service, dashboard, network client, or
host-owned verifier/runtime semantics were added.

## Public Contracts

Implemented in Goal 6C:

- `MissionCLI`
- `MissionCLIResult`
- `MissionRunView`
- `ControlRequestWriter`
- `ControlRequestWriteResult`

## Adapter Shapes

The stable Python shape is already:

```text
MissionIR -> MissionRuntime.run() -> MissionResult
```

Host adapters must preserve that shape. A host shell may translate host state
into a MissionIR ref and write a MissionResult summary back to the host, but it
must not own verifier, repair, steering, or completion semantics.

Observation surfaces are read-only:

```text
MissionResult + EvidenceLedger snapshot -> MissionRunView
```

Control surfaces write explicit intent:

```text
user or host control -> ControlRequest
```

## Implemented Adapter Behavior

- `MissionCLI` accepts a workspace-relative MissionIR JSON ref, calls
  `MissionRuntime.run()`, writes a workspace-relative `MissionResult` JSON ref,
  and returns `MissionCLIResult`.
- `MissionCLIResult` is refs-only: mission id, status, result ref, evidence
  refs, artifact refs, failed constraint ids, and metrics.
- `MissionRunView` summarizes `MissionResult` and optional evidence snapshot
  counts without mutating runtime state or evidence.
- `ControlRequestWriter` writes explicit halt intent as `ControlRequest` JSON
  under `control/`; it does not dispatch, route, approve, or mutate runtime
  state.
- Host adapter modules remain optional under `missionforge.adapters`; core
  modules and package root do not import or re-export them.

## Invariants

- Hosts pass Mission IR in and receive MissionResult out.
- Host adapters do not inspect private runtime internals.
- Host adapters do not own verifier or repair semantics.
- Observation adapters are read-only.
- Control adapters write explicit intent requests that runtime consumes at safe
  points.
- Host state may store refs and summaries, not raw prompts, transcripts, or
  private runtime internals.
- Optional host dependencies must stay outside `missionforge` core imports.

## Dependencies

- runtime engine

## Verification Strategy

- standalone Python API first
- CLI smoke
- optional LangGraph adapter after core runtime is stable
- read-only observation summary smoke
- control request intent write/read smoke
- import-boundary tests for optional dependencies

## Verification Evidence

Goal 6C focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_host_cli_adapter.py tests/test_host_observation_adapter.py tests/test_host_import_boundaries.py tests/test_adapter_import_boundaries.py tests/test_piworker_import_boundaries.py tests/test_skillfoundry_import_boundaries.py
# Ran 17 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 131 tests: OK

git diff --check
# passed
```

Independent reviewer `Confucius` approved Goal 6C, and MetaLoop verification
reached `completed_verified`.

## Follow-On Goal

Recommended launch prompt:

```text
/goal 使用 $metaloop 按 docs/FOLLOW_ON_GOALS.md 的 Goal 6C 设计并实现
MissionForge optional host adapter shell。保持 host adapter 可选，core 不依赖
LangGraph/HTTP；observation read-only，control 只写 ControlRequest intent。
```

## Open Questions

- What is the smallest host state mapping?
- Should adapters support streaming observation events?
- Which control requests should be exposed by CLI before HTTP service exists?
