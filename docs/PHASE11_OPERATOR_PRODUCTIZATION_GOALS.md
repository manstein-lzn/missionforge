# Phase 11 Operator Productization Goals

This document converts `docs/PHASE11_OPERATOR_PRODUCTIZATION_PLAN.md` into
implementation-ready `/goal` slices.

Phase 11 is the layer that makes Phase 10's durable runtime state operable. It
does not add a new agent brain, worker registry, verifier, dashboard authority,
or SkillFoundry-specific runtime branch.

## Global Goal Contract

Goal:

```text
Expose MissionForge's durable MissionRun state through deterministic operator
commands for run, inspect, diagnose, resume, control halt, review record, and
validate, while keeping MissionForge runtime truth separate from PI session
diagnostics and host product UX.
```

Success:

- operators can make the next operational decision without opening raw JSON by
  hand,
- every command emits refs-only deterministic JSON,
- command exit codes distinguish invalid input, missing state, runtime failure,
  verifier failure, unsupported operation, and review or human gates,
- inspect and diagnose are read-only,
- resume is accepted only from `after_completed_turn` safe points,
- control commands write explicit intent only,
- review commands validate freshness and independence,
- `scripts/validate.sh` remains the canonical repository health check,
- PI Agent session refs remain diagnostic evidence, not MissionForge truth.

Non-goals:

- no PI TUI import,
- no full PI coding-agent CLI import,
- no public multi-worker runtime selection,
- no raw transcript, provider payload, stdout/stderr body, prompt, artifact
  body, or secret in default output,
- no CLI-owned completion authority,
- no host-owned verifier, repair, steering, or runtime mutation,
- no SkillFoundry product semantics in MissionForge core,
- no mid-tool-call resume or active shell-process recovery,
- no mandatory live-provider test in the default validation path.

Protocol shape:

```text
single_node
```

Rationale: all Phase 11 work is in one repository and one operational truth
store. The boundaries are contract boundaries, not separate workspaces. JSONL
RPC may become a later embedding protocol, but it should call the same command
implementations rather than becoming a second runtime.

## Current Foundation

Available implementation that Phase 11 should build on:

- `MissionRuntime.run()`, `MissionRuntime.inspect()`, and
  `MissionRuntime.resume()` in `src/missionforge/runner.py`
- durable runtime records in `src/missionforge/state.py`
- existing optional CLI shell in `src/missionforge/adapters/cli.py`
- read-only observation and halt-intent writer in
  `src/missionforge/adapters/observation.py`
- reviewer freshness and independence validation in
  `src/missionforge/review.py`
- canonical validation script in `scripts/validate.sh`
- PI Agent runtime dependency path in `workers/pi-agent-runtime`

Important PI reuse decision:

```text
Reuse PI command/session/RPC vocabulary as design input.
Do not copy PI's product CLI/TUI as MissionForge Phase 11 implementation.
```

MissionForge truth remains:

- `MissionRun`
- `RuntimeAttempt`
- `RuntimeSafePoint`
- `ArtifactHygieneReport`
- `MissionResult`
- verifier result and evidence refs

PI session refs remain:

- diagnostic refs attached to attempts,
- useful for worker debugging,
- not acceptance authority.

## Command Output Contract

Phase 11 should converge all operator commands on a deterministic envelope:

```json
{
  "schema_version": "missionforge.command_result.v1",
  "command": "inspect",
  "status": "completed",
  "exit_code": 0,
  "data": {},
  "refs": [],
  "error": null
}
```

Required properties:

- `schema_version`, `command`, `status`, and `exit_code` are always present.
- `data` is JSON-compatible and refs-only.
- `refs` contains workspace-relative refs that explain where durable evidence
  lives.
- `error` is either `null` or a structured object with `code`, `message`, and
  optional `refs`.
- key ordering is stable in CLI output.
- default output must be safe to paste into an issue or log.

Suggested exit code taxonomy:

| Exit code | Meaning |
| --- | --- |
| `0` | command completed and no blocking verification failure occurred |
| `2` | invalid input or contract validation error |
| `3` | requested run, mission ref, review ref, or state ref is missing |
| `4` | unsupported operation or unsupported resume boundary |
| `5` | runtime or worker execution failed before verification could complete |
| `6` | blocking verifier failure |
| `7` | review or human-authority gate is pending |
| `8` | environment validation failed |

These codes are product-facing conventions. They do not replace
`VerificationResult.status`, `MissionRun.status`, or `MissionResult.status`.

## Goal Order

Recommended order:

```text
Goal 11.0: Command Contract Preflight
Goal 11A: CLI Router And Run Command
Goal 11B: Inspect And Diagnose Commands
Goal 11C: Resume Command
Goal 11D: Control Halt And Review Record Commands
Goal 11E: Validate Command And SkillFoundry Smoke
Goal 11F: Optional JSONL RPC
```

Goal 11F was implemented after the CLI command semantics stabilized. It remains
optional for host products to use, but it is covered by the same command
contract and refs-only policy as CLI.

## Goal 11.0: Command Contract Preflight

Status: `completed_verified`

Intent:

```text
Define the Phase 11 command result envelope, command router boundary, exit code
mapping, and refs-only output policy before expanding the CLI.
```

Primary files:

- `src/missionforge/adapters/cli.py`
- `tests/test_operator_cli_contracts.py`
- `docs/modules/host_adapters.md`
- `docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md`

Expected contracts:

- `MissionCommandResult`
- `MissionCommandError`
- exit code mapping helper
- refs-only output validator for CLI command payloads

Non-goals:

- no new command behavior beyond contract scaffolding,
- no dashboard,
- no JSONL RPC,
- no PI TUI or coding-agent CLI import,
- no change to runtime decision semantics.

Acceptance:

- command result and error envelopes round-trip through `from_dict()` and
  `to_dict()`,
- raw payload, body, transcript, prompt, provider message, stdout/stderr body,
  and secret-shaped fields are rejected from command output,
- exit code mapping is deterministic and tested,
- current `MissionCLIResult` compatibility is preserved or explicitly wrapped,
- default test suite still passes.

Implemented in this goal:

- `MissionCommandResult` and `MissionCommandError` command envelopes in
  `src/missionforge/adapters/cli.py`
- Phase 11 command route names for `run`, `inspect`, `diagnose`, `resume`,
  `control halt`, `review record`, and `validate`
- deterministic exit code helpers for success, invalid input, missing state,
  unsupported operation, runtime failure, verifier failure, authority pending,
  and environment validation failure
- mission-status-to-command-exit mapping for the current verifier-routed
  `MissionResult.status` values
- `assert_refs_only_command_payload()` for recursive raw body, prompt,
  transcript, provider message, stdout/stderr, secret-shaped field, and unsafe
  ref rejection
- `MissionCommandResult.from_cli_result()` wrapper preserving the existing
  `MissionCLIResult` contract without changing CLI execution behavior
- focused Goal 11.0 tests in `tests/test_operator_cli_contracts.py`

Verification:

```bash
PYTHONPATH=src python3 -m unittest tests/test_operator_cli_contracts.py
# Ran 9 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 202 tests: OK (skipped=2)

git diff --check
# passed

MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
# Node tests: 17 passed
# Python tests: Ran 202 tests: OK (skipped=2)
# MissionForge validation passed
```

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md 的
Goal 11.0 推进 MissionForge Phase 11 Command Contract Preflight。只定义
command result/error envelope、exit code mapping 和 refs-only output policy；
不要实现 dashboard、JSONL RPC、PI TUI、PI full CLI 或 runtime 新语义。
```

## Goal 11A: CLI Router And Run Command

Status: `completed_verified`

Intent:

```text
Promote the existing optional CLI shell into a subcommand router and implement
the product-facing `run` command on top of MissionRuntime.run().
```

Primary files:

- `src/missionforge/adapters/cli.py`
- optional module entrypoint if chosen by implementation:
  `src/missionforge/__main__.py`
- `tests/test_operator_cli_run.py`
- `README.md`
- `docs/modules/host_adapters.md`

Command shape:

```bash
missionforge run --workspace . --mission-ref missions/input.mission.json
missionforge run --workspace . --mission-ref missions/input.mission.json --json
```

Implementation guidance:

- reuse `MissionCLI.run_mission_ref()` where it still matches the command
  contract,
- keep adapter code under `missionforge.adapters` unless a tiny module
  entrypoint is needed,
- do not import host adapter modules from core runtime modules or the package
  root,
- write `MissionResult` refs under `host_results/` unless the caller provides a
  workspace-relative result ref.

Acceptance:

- `run` validates the MissionIR ref before dispatch,
- successful runs emit `missionforge.command_result.v1`,
- failed verifier status maps to a nonzero blocking verification exit code,
- invalid input maps to invalid-input exit code,
- command output includes `mission_result_ref`, `evidence_refs`,
  `artifact_refs`, `failed_constraint_ids`, and relevant metrics,
- no raw artifacts, transcript bodies, prompts, or provider payloads appear in
  stdout,
- current host CLI tests still pass.

Implemented in this goal:

- `MissionCLI.run_command()` subcommand router
- product-facing `run` command returning `MissionCommandResult`
- backward-compatible `MissionCLI.run()` and `MissionCLI.run_mission_ref()`
- `main()` output through the refs-only command envelope
- focused tests in `tests/test_operator_cli_run.py`

Verification:

```bash
PYTHONPATH=src python3 -m unittest tests/test_host_cli_adapter.py tests/test_operator_cli_run.py
# passed

PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md 的
Goal 11A 实现 MissionForge CLI Router And Run Command。基于现有
MissionRuntime.run 和 MissionCLI，输出 deterministic refs-only JSON；
不要引入 PI TUI/full CLI、HTTP、LangGraph 或新的 runtime completion 语义。
```

## Goal 11B: Inspect And Diagnose Commands

Status: `completed_verified`

Intent:

```text
Expose read-only operator views over MissionRun, RuntimeAttempt, safe point,
artifact hygiene, verifier status, and next action.
```

Primary files:

- `src/missionforge/adapters/cli.py`
- `src/missionforge/state.py`
- optional small diagnosis helper module if the CLI file becomes too large:
  `src/missionforge/adapters/diagnosis.py`
- `tests/test_operator_cli_inspect.py`
- `tests/test_operator_cli_diagnose.py`

Command shape:

```bash
missionforge inspect --workspace . --run run-sample-mission
missionforge diagnose --workspace . --run run-sample-mission
```

Inspect output must include:

- `mission_run_id`
- `mission_id`
- `status`
- `current_attempt`
- `latest_work_unit_id`
- `latest_decision`
- `next_action`
- `latest_safe_point`
- `attempt_count`
- `latest_attempt`
- `failed_constraint_ids`
- `artifact_refs`
- `evidence_refs`
- `artifact_hygiene`

Diagnosis reason codes:

| Reason code | Meaning |
| --- | --- |
| `complete` | verifier completed successfully |
| `no_resume_safe_point` | no latest safe point is available |
| `unsupported_resume_boundary` | safe point exists but is not resumable |
| `worker_failure` | worker/runtime failed before usable verified output |
| `repairable_verifier_failure` | verifier failed and repair budget remains |
| `repair_exhausted` | verifier failed after available repair attempts |
| `redesign_required` | contract, validator, authority, or proposal issue requires redesign |
| `review_required` | independent review gate is pending |
| `human_acceptance_required` | explicit human authority is pending |
| `artifact_hygiene_failed` | hygiene report failed or required refs are unsafe |
| `missing_state` | requested MissionRun state is missing |

Acceptance:

- `inspect` and `diagnose` do not mutate files,
- missing run state returns a structured `missing_state` error,
- diagnosis is deterministic and based only on durable records,
- diagnosis cites refs used for the recommendation,
- latest attempt and safe-point data are visible without opening PI session
  messages,
- artifact hygiene failure takes precedence over ordinary resume advice.

Implemented in this goal:

- `inspect` command over `MissionRun`, `RuntimeAttempt`, safe point, refs, and
  artifact hygiene state
- `diagnose` command with deterministic reason codes and operator actions
- read-only command behavior that does not mutate run files
- focused tests in `tests/test_operator_cli_inspect.py` and
  `tests/test_operator_cli_diagnose.py`

Verification:

```bash
PYTHONPATH=src python3 -m unittest tests/test_operator_cli_inspect.py tests/test_operator_cli_diagnose.py
# passed

PYTHONPATH=src python3 -m unittest tests/test_runtime_state_ledger.py tests/test_runtime_resume.py
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md 的
Goal 11B 实现 MissionForge inspect 和 diagnose commands。它们必须是
read-only deterministic views，只引用 MissionRun/RuntimeAttempt/hygiene refs；
不要读取或输出 raw PI transcript/provider payload。
```

## Goal 11C: Resume Command

Status: `completed_verified`

Intent:

```text
Expose MissionRuntime.resume() through the operator CLI while preserving Phase
10's completed-turn-only resume boundary.
```

Primary files:

- `src/missionforge/adapters/cli.py`
- `tests/test_operator_cli_resume.py`
- `tests/test_runtime_resume.py`

Command shape:

```bash
missionforge resume \
  --workspace . \
  --run run-sample-mission \
  --mission-ref missions/input.mission.json \
  --prompt "Continue from the latest completed turn."
```

Acceptance:

- resume reads the requested run's latest safe point,
- missing safe point fails closed,
- unsupported safe-point kind fails closed,
- resume appends a new `RuntimeAttempt` and preserves previous attempts,
- verifier remains the only completion authority after resume,
- follow-up prompt is passed as worker input but is not printed back in default
  command output,
- stale or mismatched mission/run identity fails closed.

Implemented in this goal:

- `resume` command over `MissionRuntime.resume()`
- completed-turn-only safe-point preflight
- run/mission identity check
- resumed `MissionResult` ref output
- focused tests in `tests/test_operator_cli_resume.py`

Verification:

```bash
PYTHONPATH=src python3 -m unittest tests/test_operator_cli_resume.py tests/test_runtime_resume.py
# passed

PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md 的
Goal 11C 实现 MissionForge resume command。只支持 latest
after_completed_turn safe point，resume 后追加 RuntimeAttempt 并重新走 verifier；
不要实现 mid-tool-call resume、active shell recovery 或 PI session truth。
```

## Goal 11D: Control Halt And Review Record Commands

Status: `completed_verified`

Intent:

```text
Expose explicit halt intent and independent review recording without granting
the host or CLI authority to mutate runtime truth or override executable
validators.
```

Primary files:

- `src/missionforge/adapters/cli.py`
- `src/missionforge/adapters/observation.py`
- `src/missionforge/review.py`
- optional review adapter helper if needed:
  `src/missionforge/adapters/review.py`
- `tests/test_operator_cli_control.py`
- `tests/test_operator_cli_review.py`
- `tests/test_reviewer_decision.py`

Command shape:

```bash
missionforge control halt \
  --workspace . \
  --run run-sample-mission \
  --reason "Pause before the next attempt."

missionforge review record \
  --workspace . \
  --run run-sample-mission \
  --decision approved \
  --review-ref reviews/reviewer-decision.json
```

Acceptance:

- `control halt` writes a `ControlRequest` ref only,
- `control halt` does not mutate `MissionRun` or append runtime attempts,
- `review record` validates a `ReviewerDecision` against the current contract
  hash and available run/capsule identity,
- stale review decisions fail closed,
- worker-authored review decisions fail closed,
- review approval cannot override failed executable validators,
- command output cites the control or review refs, not raw notes bodies.

Implemented in this goal:

- `control halt` command using `ControlRequestWriter`
- `review record` command over `ReviewerDecision` refs
- review freshness check against current run contract hash
- refs-only review record output that does not copy notes bodies
- tests proving halt/review do not mutate `MissionRun`
- focused tests in `tests/test_operator_cli_control.py` and
  `tests/test_operator_cli_review.py`

Verification:

```bash
PYTHONPATH=src python3 -m unittest tests/test_operator_cli_control.py tests/test_operator_cli_review.py tests/test_host_observation_adapter.py tests/test_reviewer_decision.py
# passed

PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md 的
Goal 11D 实现 MissionForge control halt 和 review record commands。control
只写 intent ref，review 只记录并校验 independent reviewer decision；
不要让 CLI/dashboard 覆盖 verifier 或直接修改 MissionRun。
```

## Goal 11E: Validate Command And SkillFoundry Smoke

Status: `completed_verified`

Intent:

```text
Make repository validation an operator workflow and prove a SkillFoundry-style
compiled MissionIR can pass through the operator run/inspect path without
putting SkillFoundry semantics into runtime core.
```

Primary files:

- `src/missionforge/adapters/cli.py`
- `scripts/validate.sh`
- `src/missionforge/adapters/skillfoundry.py`
- `tests/test_operator_cli_validate.py`
- `tests/test_operator_skillfoundry_smoke.py`
- `docs/modules/skillfoundry_adapter.md`

Command shape:

```bash
missionforge validate
MISSIONFORGE_SKIP_NPM_CI=1 missionforge validate
```

Acceptance:

- `validate` delegates to `scripts/validate.sh` or a thin equivalent wrapper,
- default validation checks Node runtime tests, Python tests, and whitespace,
- fast mode is explicit and does not become the default,
- live-provider validation remains opt-in,
- SkillFoundry smoke compiles adapter source refs into MissionIR, runs through
  the operator path, and inspects resulting MissionRun state,
- SkillFoundry-specific behavior stays in adapter/profile data, not runtime
  branches.

Implemented in this goal:

- `validate` command delegating to `scripts/validate.sh`
- validation log written by ref under `host_results/validation/`
- command output includes refs and return code, not raw validation output
- SkillFoundry compiled MissionIR operator smoke
- focused tests in `tests/test_operator_cli_validate.py` and
  `tests/test_operator_skillfoundry_smoke.py`

Verification:

```bash
PYTHONPATH=src python3 -m unittest tests/test_operator_cli_validate.py tests/test_operator_skillfoundry_smoke.py
# passed

MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
git diff --check
```

Full validation, when network/cache conditions allow:

```bash
./scripts/validate.sh
```

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md 的
Goal 11E 实现 MissionForge validate command 和 SkillFoundry operator smoke。
validate 走 scripts/validate.sh；SkillFoundry 只通过 adapter 编译 MissionIR；
不要在 runtime core 加 SkillFoundry 分支或 live-provider 默认测试。
```

## Goal 11F: Optional JSONL RPC

Status: `completed_verified`

Intent:

```text
Add a refs-only headless JSONL protocol only after CLI semantics are stable and
a host embedding use case needs request/response correlation.
```

Primary files:

- optional `src/missionforge/adapters/rpc.py`
- `tests/test_operator_jsonl_rpc.py`

Non-goals:

- no new command semantics,
- no streaming provider payloads,
- no dashboard write endpoints,
- no hidden control mutation,
- no replacement for CLI tests.

Acceptance:

- every RPC command maps to the same implementation as the CLI command,
- every request and response has a correlation id,
- protocol output is refs-only,
- malformed requests fail closed with structured errors,
- event messages are observation only and cannot mutate runtime truth.

Implemented in this goal:

- optional `MissionJSONLRPC` in `src/missionforge/adapters/rpc.py`
- JSONL request/response handling over the same `MissionCLI.run_command()`
  implementation used by CLI commands
- request id correlation
- malformed request fail-closed structured errors
- tests in `tests/test_operator_jsonl_rpc.py`

Verification:

```bash
PYTHONPATH=src python3 -m unittest tests/test_operator_jsonl_rpc.py
# passed
```

Suggested `/goal` prompt:

```text
/goal 使用 $metaloop 按 docs/PHASE11_OPERATOR_PRODUCTIZATION_GOALS.md 的
Goal 11F 设计 MissionForge optional JSONL RPC。只有在 CLI semantics 已稳定时
才做；RPC 必须复用 CLI command implementation，refs-only，不能新增 runtime
authority 或 dashboard mutation。
```

## Cross-Cutting Verification

Every Phase 11 implementation slice should run at least:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 202 tests: OK (skipped=2)

git diff --check
# passed
```

For changes touching `workers/pi-agent-runtime` or validation behavior:

```bash
npm test --prefix workers/pi-agent-runtime
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
```

Full closeout should run:

```bash
./scripts/validate.sh
```

Current full closeout evidence:

```bash
./scripts/validate.sh
# npm ci: added 231 packages, 0 vulnerabilities
# Node tests: 17 passed
# Python tests: Ran 202 tests: OK (skipped=2)
# MissionForge validation passed
```

## Redesign Triggers

Stop and redesign the active goal if implementation pressure creates any of
these conditions:

- command output needs raw transcript or provider payload to be useful,
- CLI wants to decide completion without verifier status,
- review approval is being used to override executable validator failure,
- resume needs a boundary other than `after_completed_turn`,
- SkillFoundry semantics start appearing in runtime core branches,
- PI session state starts replacing `MissionRun` or `RuntimeAttempt` as truth,
- JSONL RPC would require semantics not already present in CLI command
  implementations.

## Phase 11 Completion

Phase 11 is `completed_verified` when:

- Goals 11.0 through 11E are implemented and verified,
- Goal 11F is either implemented and verified or explicitly deferred with no
  current host embedding requirement,
- `./scripts/validate.sh` passes,
- docs and tests prove the operator surface is refs-only,
- an operator can run, inspect, diagnose, resume, halt, review, and validate
  without relying on worker self-report or PI product UI as acceptance truth.
