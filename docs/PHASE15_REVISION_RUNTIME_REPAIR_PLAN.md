# Phase 15 Repair: Runtime Revision Consumption

Last updated: 2026-05-29

Status: `implemented`

## Document Role

Phase 15 introduced mission revision contracts and a conservative revision
store. The contracts are useful, but the runtime does not yet consume a
recorded revision as the current contract for later work.

This repair plan closes that gap.

The goal is deliberately narrow:

```text
recorded MissionRevision -> MissionRun current contract state ->
runtime resumes under that contract hash
```

This is not a new workflow engine. It is a correction to the Phase 15 state
transition boundary.

## Implementation Summary

Implemented in this repair:

- active frozen contract loading and run-local base contract refs
- `RuntimeStateWriter` preservation of current contract refs, hashes, and
  revision refs
- runtime resume under `MissionRun.current_contract_ref`
- frozen-contract-derived runtime view for required artifacts, scopes,
  validators, constraints, manual gates, and objective summary
- operator inspect surface for current contract refs and revision refs
- durable `apply_mission_revision()` helper
- revised MissionIR storage under the revision directory
- stale or missing active contract fail-closed behavior

## Current Failure

The current implementation can write a revision record and update
`MissionRun.current_contract_ref`, `MissionRun.current_contract_hash`, and
`MissionRun.revision_refs` through `MissionRevisionStore`.

However, the next runtime write replaces that state with the legacy base
contract state:

```text
current_contract_ref = mission/frozen_contract.json
revision_refs = []
```

The runtime also freezes the caller-provided `MissionIR` again on each
`run()` or `resume()` call. That means a revised frozen contract can be
recorded but is not the active contract for subsequent work.

Observed behavior:

```json
{
  "before_current_contract_ref": "runs/run-sample-mission/revisions/revision-000001/frozen_contract.json",
  "before_revision_refs": ["runs/run-sample-mission/revisions/revision-000001/revision.json"],
  "after_current_contract_ref": "mission/frozen_contract.json",
  "after_revision_refs": []
}
```

## Repair Intent

Make MissionRun's current contract fields authoritative for runtime resume and
future work after a revision has been recorded.

The runtime should:

1. preserve revision refs and current contract refs when writing state,
2. expose revision refs through operator inspect,
3. fail closed if a current contract ref/hash is stale or inconsistent,
4. use the current frozen contract hash in steering context, review packets,
   verification, metric summaries, and MissionResult compatibility metrics,
5. avoid re-freezing the original authoring MissionIR over an already-recorded
   revision.

## Non-Goals

- no workflow engine
- no multi-step orchestration DSL
- no live LLM default
- no automatic contract expansion
- no automatic authority expansion
- no weakening executable validators
- no reviewer prose overriding failed executable validators
- no dashboard-owned revision
- no public multi-worker support
- no SQLite or remote store work in this repair
- no broad runtime rewrite beyond the contract-state boundary needed here

## Core Invariants

1. `FrozenMissionContract.contract_hash` remains the runtime truth hash.
2. `MissionRun.current_contract_ref` and `MissionRun.current_contract_hash`
   identify the active contract after the run exists.
3. A runtime write must never silently clear `revision_refs`.
4. A revision becomes active only after the revision record and revised frozen
   contract are durable.
5. Runtime may validate the caller-provided `MissionIR` as an identity or
   compatibility input, but it must not let that input overwrite an active
   revised contract without an explicit new revision.
6. If the active contract cannot be loaded or its hash does not match
   `MissionRun.current_contract_hash`, runtime fails closed.
7. Operator surfaces expose refs and hashes, never raw contract bodies.
8. Revision remains a controlled state transition, not a general mutation API.

## Target State

### Before First Run

No `MissionRun` exists yet.

The runtime may freeze the submitted `MissionIR` and write the initial contract
as the active contract.

Preferred layout:

```text
runs/{mission_run_id}/contracts/base/frozen_contract.json
runs/{mission_run_id}/mission_run.json
```

Compatibility note:

- Existing tests and artifacts may still reference `mission/frozen_contract.json`.
- The repair may keep writing the legacy ref as a compatibility alias during
  the transition.
- `MissionRun.current_contract_ref` should point to the authoritative active
  contract ref.

### After Revision

A revision writes:

```text
runs/{mission_run_id}/revisions/{revision_id}/request.json
runs/{mission_run_id}/revisions/{revision_id}/decision.json
runs/{mission_run_id}/revisions/{revision_id}/frozen_contract.json
runs/{mission_run_id}/revisions/{revision_id}/revision.json
```

Then `MissionRun` records:

```json
{
  "current_contract_ref": "runs/{mission_run_id}/revisions/{revision_id}/frozen_contract.json",
  "current_contract_hash": "<new hash>",
  "revision_refs": [
    "runs/{mission_run_id}/revisions/{revision_id}/revision.json"
  ]
}
```

### Resume After Revision

On `resume()`, the runtime loads `MissionRun`, then loads and validates the
active frozen contract from `MissionRun.current_contract_ref`.

The next steering context, review packet, verifier contract hash, MissionRun
state, and MissionResult metrics must use the active contract hash.

The caller-provided `MissionIR` is used only to validate identity and provide a
public API compatibility input unless the runtime is starting a new run.

## Design Shape

Keep the design small. Add one contract-state helper rather than a coordinator
family.

Candidate helper:

```python
@dataclass(frozen=True)
class ActiveMissionContract:
    mission_run_id: str
    mission_id: str
    contract_ref: str
    contract_hash: str
    frozen_contract: FrozenMissionContract
    revision_refs: list[str]
```

Candidate helper functions:

```python
def initialize_active_contract(
    *,
    workspace: Path,
    mission: MissionIR,
    mission_run_id: str,
) -> ActiveMissionContract:
    ...

def load_active_contract(
    *,
    workspace: Path,
    run: MissionRun,
) -> ActiveMissionContract:
    ...
```

Rules:

- first run initializes from `MissionIR`;
- resume loads from `MissionRun.current_contract_ref`;
- current contract hash must match loaded `FrozenMissionContract.contract_hash`;
- mission id must match the caller-provided `MissionIR.mission_id`;
- revision refs are preserved and deduped;
- no runtime branch may inspect product names or profile names.

## Runtime Contract View

The runtime should stop relying on raw `MissionIR` fields after freeze when a
frozen contract is available.

The first repair can derive runtime inputs from
`FrozenMissionContract.expanded_mission`:

- mission id
- objective summary
- constraints
- validators
- outputs.required_artifacts
- outputs.allowed_write_scopes
- verification manual gates

This avoids a large rewrite while preventing a revised contract from being
overwritten by the original `MissionIR`.

Candidate helper:

```python
def runtime_contract_view(frozen: FrozenMissionContract) -> RuntimeContractView:
    ...
```

`RuntimeContractView` should be internal. It should not become a public
workflow abstraction.

## Implementation Slices

### Slice 15R-A: Preserve Current Contract State

Files:

- `src/missionforge/runtime_state_writer.py`
- `src/missionforge/revision_store.py`
- `src/missionforge/state.py`
- `tests/test_runtime_revision_preservation.py`

Changes:

- `RuntimeStateWriter.write()` accepts active contract fields:
  - `current_contract_ref`
  - `current_contract_hash`
  - `revision_refs`
- If a previous `MissionRun` exists, state writer preserves its revision refs
  unless the caller supplies a deliberate replacement.
- `MissionRevisionStore.record_on_mission_run()` updates `updated_at`.
- Runtime writes no longer reset `revision_refs` to `[]`.

Acceptance:

- recording a revision then calling runtime state write preserves revision refs;
- duplicate revision refs are deduped;
- current contract ref/hash survive `resume()`;
- stale or unsafe revision refs are rejected.

### Slice 15R-B: Operator Revision Surface

Files:

- `src/missionforge/adapters/cli.py`
- `src/missionforge/adapters/observation.py`
- `tests/test_operator_revision_surface.py`

Changes:

- `inspect` includes:
  - `current_contract_ref`
  - `current_contract_hash`
  - `revision_refs`
  - `latest_revision_ref`
- command refs include revision refs and current contract ref;
- `diagnose` remains projection/status based and must not read raw revision
  bodies.

Acceptance:

- inspect surfaces revision refs without embedding contract or revision bodies;
- inspect remains read-only;
- diagnose output remains refs-only.

### Slice 15R-C: Active Contract Loading On Resume

Files:

- `src/missionforge/runtime.py`
- `src/missionforge/freeze.py`
- `src/missionforge/runtime_state_writer.py`
- `tests/test_runtime_revision_consumption.py`

Changes:

- `RuntimeEngine.resume()` loads `MissionRun` first, then loads the active
  frozen contract ref from the run.
- Runtime validates:
  - caller mission id matches run mission id,
  - active contract ref exists,
  - loaded contract hash matches run current contract hash,
  - loaded contract mission id matches run mission id.
- Steering context uses active contract ref/hash.
- Review packet uses active contract ref/hash.
- Verifier is initialized with active contract hash.
- MissionResult metrics report active contract hash.

Acceptance:

- after a revision is recorded, resume produces a next attempt whose runtime
  state still points at the revised contract;
- steering context visible refs contain the revised contract ref;
- stale active contract hash fails closed;
- missing active contract ref fails closed;
- passing the original MissionIR to `resume()` does not overwrite revision
  state.

### Slice 15R-D: Runtime Contract View

Files:

- `src/missionforge/runtime.py`
- possibly `src/missionforge/runtime_contract.py`
- `tests/test_runtime_revision_consumption.py`
- `tests/test_runtime_routes.py`

Changes:

- internal runtime helpers read required artifacts, allowed scopes, validators,
  constraints, and objective from the active frozen contract view after freeze;
- initial run behavior remains compatible;
- no public API change is introduced.

Acceptance:

- deterministic initial run output remains unchanged except intentional contract
  ref migration if the repair chooses a run-local base ref;
- revision metadata in frozen contract changes the active contract hash used by
  subsequent runtime work;
- runtime does not re-freeze the original MissionIR after a revision is active.

### Slice 15R-E: Revision Application Entry Point

Files:

- `src/missionforge/revision.py`
- `src/missionforge/revision_store.py`
- possibly `src/missionforge/runner.py`
- `tests/test_mission_revision_workflow.py`

Changes:

- provide one internal/public-enough helper for the full durable transition:

```python
def apply_mission_revision(
    *,
    workspace: Path,
    mission: MissionIR,
    adjustment: ContractAdjustmentRequest,
    reviewer_decision: ReviewerDecision | None = None,
) -> MissionRevision:
    ...
```

This helper should:

1. load the current `MissionRun`,
2. load the current frozen contract,
3. build `MissionRevisionRequest`,
4. decide authority,
5. apply only approved conservative changes,
6. write request, decision, revised contract, and revision record,
7. update `MissionRun.current_contract_ref/hash/revision_refs`.

Acceptance:

- no partial activation: if any artifact write fails, MissionRun is not moved
  to the new contract;
- unapproved decisions do not update current contract state;
- reviewer decisions must match the current active contract hash;
- human authority routes remain pending and do not auto-apply.

This helper is not a dashboard endpoint or workflow engine.

## Test Plan

Add or update:

- `tests/test_runtime_revision_preservation.py`
- `tests/test_operator_revision_surface.py`
- `tests/test_runtime_revision_consumption.py`
- `tests/test_mission_revision_workflow.py`
- `tests/test_revision_authority_boundaries.py`
- `tests/test_controlled_steering_runtime.py`
- `tests/test_runtime_resume.py`
- `tests/test_runtime_store_integration.py`

Focused commands:

```bash
PYTHONPATH=src python3 -m unittest tests/test_runtime_revision_preservation.py tests/test_operator_revision_surface.py
PYTHONPATH=src python3 -m unittest tests/test_runtime_revision_consumption.py tests/test_mission_revision_workflow.py
PYTHONPATH=src python3 -m unittest tests/test_revision_authority_boundaries.py tests/test_runtime_resume.py
PYTHONPATH=src python3 -m unittest tests/test_controlled_steering_runtime.py tests/test_runtime_store_integration.py
PYTHONPATH=src python3 -m unittest discover -s tests
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
git diff --check
```

If SkillFoundry integration behavior is touched:

```bash
./scripts/validate_integrations.sh skillfoundry
```

## Required Regression Tests

### Revision State Is Not Cleared

Scenario:

1. run mission,
2. record a split revision,
3. call `resume()`,
4. inspect `MissionRun`.

Expected:

- `current_contract_ref` remains the revision frozen contract ref;
- `current_contract_hash` remains the revision hash;
- `revision_refs` still includes the revision record;
- latest attempt is appended, not reset.

### Stale Active Contract Fails Closed

Scenario:

1. record a revision,
2. corrupt `MissionRun.current_contract_hash`,
3. call `resume()`.

Expected:

- runtime raises `ContractValidationError`;
- no new attempt is appended;
- current revision refs remain unchanged.

### Operator Inspect Surfaces Revision Refs

Scenario:

1. record a revision,
2. run `inspect`.

Expected:

- top-level inspect data includes current contract ref/hash and revision refs;
- result refs include the current contract ref and revision refs;
- no raw contract body appears in command output.

### Original MissionIR Cannot Overwrite Active Revision

Scenario:

1. record a revision whose frozen hash differs from the original mission hash,
2. call `resume(original_mission)`.

Expected:

- runtime uses the active revised hash;
- runtime does not write the original hash back into MissionRun;
- MissionResult compatibility metrics report the active revised hash.

## Acceptance

This repair is complete when:

- current contract state is preserved across runtime writes;
- revision refs are visible through operator inspect;
- resume consumes the active contract ref/hash from MissionRun;
- stale or missing active contract refs fail closed;
- the original MissionIR cannot silently roll back a recorded revision;
- verifier, review packet, steering context, metrics, and MissionRun agree on
  the same active contract hash;
- default deterministic runtime behavior still passes;
- SkillFoundry remains outside the core package;
- no new product-specific runtime branch is introduced.

## Suggested Goal Prompt

```text
/goal 使用 $metaloop 按 docs/PHASE15_REVISION_RUNTIME_REPAIR_PLAN.md
修复 Phase15 Mission Revision 的 runtime consumption 缺口。目标是让
MissionRun.current_contract_ref/current_contract_hash/revision_refs 成为
revision 后的运行时真相，并让 resume 在新 frozen contract hash 下继续；
operator inspect 要暴露 revision refs；stale/missing active contract 必须
fail closed。不要引入 workflow engine、live LLM 默认、自动扩权、dashboard
owned revision、SQLite/remote store、public worker registry 或产品特定分支。
```

## Verification Evidence

```bash
PYTHONPATH=src python3 -m unittest tests/test_runtime_revision_preservation.py tests/test_operator_revision_surface.py tests/test_runtime_revision_consumption.py tests/test_mission_revision_workflow.py tests/test_revision_authority_boundaries.py
# Ran 10 tests: OK

PYTHONPATH=src python3 -m unittest tests/test_freeze.py tests/test_runtime_resume.py tests/test_controlled_steering_runtime.py
# Ran 10 tests: OK

PYTHONPATH=src python3 -m unittest tests/test_operator_cli_inspect.py tests/test_operator_cli_diagnose.py tests/test_operator_cli_review.py tests/test_operator_metric_projection.py tests/test_operator_controlled_steering_surface.py
# Ran 14 tests: OK

PYTHONPATH=src python3 -m unittest tests/test_runtime_store_integration.py tests/test_runtime_metric_boundaries.py tests/test_metric_store.py tests/test_metrics_contracts.py tests/test_store_contracts.py tests/test_json_store_backend.py
# Ran 11 tests: OK

PYTHONPATH=src python3 -m unittest tests/test_adapter_import_boundaries.py tests/test_pi_agent_runtime_import_boundaries.py tests/test_piworker_runtime_boundary.py
# Ran 10 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 232 tests: OK (skipped=2)

MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
# Node runtime: 4 tests passed
# Python: Ran 232 tests: OK (skipped=2)
# MissionForge validation passed

./scripts/validate_integrations.sh skillfoundry
# Ran 20 tests: OK

git diff --check
# passed
```

## Follow-On Questions

- The initial base contract now writes
  `runs/{mission_run_id}/contracts/base/frozen_contract.json` and keeps
  `mission/frozen_contract.json` as a compatibility alias.
- `MissionRevision` now records `new_mission_ref`, and runtime derives
  execution data from `FrozenMissionContract.expanded_mission`.
- Revision activation is exposed as a Python helper first. A later operator
  command can wrap the same helper if the operator surface needs it.
