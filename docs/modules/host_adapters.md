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

Phase 11 productizes this host-adapter foundation into operator commands. The
scope is tracked in `docs/PHASE11_OPERATOR_PRODUCTIZATION_PLAN.md`, and the
implementation-ready `/goal` slices are in
`docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md`.

## Public Contracts

Implemented in Goal 6C:

- `MissionCLI`
- `MissionCLIResult`
- `MissionRunView`
- `ControlRequestWriter`
- `ControlRequestWriteResult`

Implemented in Phase 11 Goal 11.0:

- `MissionCommandResult`
- `MissionCommandError`
- command exit code mapping helpers
- refs-only command output validator

Implemented in Phase 11 operator productization:

- `MissionCLI.run_command()`
- `MissionJSONLRPC`
- operator commands for `run`, `inspect`, `diagnose`, `resume`,
  `control halt`, `review record`, and `validate`
- controlled steering refs in read-only `inspect` and deterministic
  steering-related diagnosis reason codes

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
- `MissionCommandResult` and `MissionCommandError` define the Phase 11
  operator command envelope before adding command implementations.
- The command output validator rejects raw body, prompt, transcript, provider
  message, stdout/stderr, secret-shaped fields, and unsafe refs recursively.
- `MissionCLI.run_command()` routes product-facing subcommands while preserving
  the older `MissionCLI.run()` compatibility path.
- `inspect` and `diagnose` read durable runtime state without mutating run
  files.
- `resume` exposes only the completed-turn runtime resume path and reuses the
  verifier-owned `MissionResult` flow.
- `control halt` writes explicit `ControlRequest` intent only.
- `review record` writes refs-only review metadata and does not override
  verifier state.
- `validate` delegates to `scripts/validate.sh` and returns a validation log
  ref, not raw command output.
- `MissionJSONLRPC` is an optional JSONL request/response adapter that maps
  requests to the same command implementations as CLI.
- `inspect` surfaces run-local controlled steering refs and latest steering ref
  maps without embedding proposal, review, prompt, provider, or artifact bodies.
- `diagnose` can report steering provider failure, rejected steering proposal,
  and unsafe steering proposal rejection as operator-actionable reason codes.
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

Phase 11 Goal 11.0 focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_operator_cli_contracts.py
# Ran 9 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 202 tests: OK (skipped=2)

MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
# Node tests: 17 passed
# Python tests: Ran 202 tests: OK (skipped=2)
# MissionForge validation passed
```

Phase 11 operator productization focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests/test_operator_cli_run.py tests/test_operator_cli_inspect.py tests/test_operator_cli_diagnose.py tests/test_operator_cli_resume.py tests/test_operator_cli_control.py tests/test_operator_cli_review.py tests/test_operator_cli_validate.py tests/test_operator_skillfoundry_smoke.py tests/test_operator_jsonl_rpc.py tests/test_host_import_boundaries.py tests/test_adapter_import_boundaries.py
# Ran 31 tests: OK

PYTHONPATH=src python3 -m unittest tests/test_operator_cli_contracts.py tests/test_operator_cli_run.py tests/test_operator_cli_inspect.py tests/test_operator_cli_diagnose.py tests/test_operator_cli_resume.py tests/test_operator_cli_control.py tests/test_operator_cli_review.py tests/test_operator_cli_validate.py tests/test_operator_skillfoundry_smoke.py tests/test_operator_jsonl_rpc.py tests/test_host_cli_adapter.py tests/test_host_observation_adapter.py tests/test_host_import_boundaries.py tests/test_adapter_import_boundaries.py
# Ran 44 tests: OK
```

Controlled steering operator surface:

```bash
PYTHONPATH=src python3 -m unittest tests/test_operator_controlled_steering_surface.py tests/test_controlled_steering_import_boundaries.py
# passed
```

## Follow-On Goal

Recommended launch prompt:

```text
/goal 使用 $metaloop 按 docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md 的
Goal 11.0 推进 MissionForge Phase 11 Command Contract Preflight。只定义
command result/error envelope、exit code mapping 和 refs-only output policy；
不要实现 dashboard、JSONL RPC、PI TUI、PI full CLI 或 runtime 新语义。
```

## Open Questions

- What is the smallest host state mapping?
- Should adapters support streaming observation events?
- Phase 11 starts with halt as the only CLI control request. Additional
  controls should wait until a concrete runtime safe-point consumer exists.
