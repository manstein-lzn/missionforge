# Getting Started

MissionForge is a small Python kernel for bounded model calls. Start with the
direct primitive, then opt into higher-level flows only when you need them.

## Install

```bash
python3 -m pip install -e .
```

If you are working on SkillFoundry:

```bash
python3 -m pip install -e integrations/skillfoundry
```

## Minimal Shape

```text
TaskContract + WorkspacePolicy + PermissionManifest
  -> PiWorkerCall
  -> run_piworker_call(...)
  -> PiWorkerCallResult
```

The result is boundary evidence. It is not semantic acceptance.

## Direct Call

```python
from missionforge import PiWorkerCall, PiWorkerCallRole, run_piworker_call

call = PiWorkerCall(
    call_id="call-001",
    role=PiWorkerCallRole.EXECUTOR,
    contract_id="contract-001",
    contract_hash="sha256:...",
    contract_ref="contract/task_contract.json",
    objective="Produce package/output.md from the visible refs.",
    visible_refs=["contract/task_contract.json", "inputs/request.json"],
    writable_refs=["package", "reports"],
    expected_output_refs=["package/output.md"],
    permission_manifest_ref="policy/permission_manifest.json",
)

result = run_piworker_call(call, workspace="/tmp/missionforge-run")
```

## Default Executor/Judge Lane

Use the bundled flow when you want the standard executor -> independent judge
composition:

```python
from missionforge import create_default_task_contract_flow
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig

preset = create_default_task_contract_flow(
    "/tmp/missionforge-run",
    piworker_config=PiAgentRuntimeConfig(provider_mode="faux"),
)

result = preset.runner.run(
    run_id="run-001",
    contract=task_contract,
    workspace_policy=workspace_policy,
    permission_manifest=permission_manifest,
    executor=preset.executor,
    judge=preset.judge,
    hard_check_status=hard_check_status,
    hard_check_refs=hard_check_refs,
)
```

The runner writes:

- `contract/task_contract.json`
- `projections/worker_brief.json`
- `packets/execution_packet.json`
- `reports/execution_report.json`
- `packets/judge_packet.json`
- `reports/judge_report.json`
- `ledgers/decision_ledger.jsonl`
- `packages/final_package.json` when accepted

## Fast Rules

- `TaskContract` is frozen task truth.
- `PiWorkerCallResult` is boundary evidence, not acceptance.
- The executor cannot accept its own work.
- Judge acceptance requires completed execution plus passed hard checks.
- Runtime state should cite refs, not raw prompts, provider payloads, stdout,
  stderr, artifact bodies, or secrets.

## Standalone Example

```bash
PYTHONPATH=src python3 examples/standalone_product_shell.py /tmp/mf-standalone-demo
```

## Validate

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
./scripts/validate_integrations.sh skillfoundry
```
