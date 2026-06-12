# Getting Started

MissionForge is a TaskContract-first PiWorker runtime. The normal entry path
is:

```text
TaskContract
  -> WorkspacePolicy
  -> PermissionManifest
  -> create_default_task_contract_flow()
  -> executor
  -> judge
  -> refs-first result
```

## Install

```bash
python3 -m pip install -e .
```

If you are working on SkillFoundry:

```bash
python3 -m pip install -e integrations/skillfoundry
```

## Run The Default Lane

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
- Judge acceptance requires completed execution plus passed hard checks.
- `attempts/<call_id>/...` is runtime audit material.
- `reports/piworker_runtime/<call_id>/...` is the runtime evidence projection
  used by the outer flow.

## Validate

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
./scripts/validate_integrations.sh skillfoundry
```
