# Cookbook

## Run One PiWorker

```python
from missionforge import PiWorkerCall, PiWorkerCallRole, run_piworker_call

call = PiWorkerCall(
    call_id="researcher-001",
    role=PiWorkerCallRole.EXECUTOR,
    contract_id="contract-001",
    contract_hash="sha256:" + "a" * 64,
    contract_ref="contract/task_contract.json",
    objective="Write reports/final.md.",
    visible_refs=["contract/task_contract.json"],
    writable_refs=["reports"],
    expected_output_refs=["reports/final.md"],
)

result = run_piworker_call(call, workspace="/tmp/mf-run")
```

## Use Codex Current Provider

```python
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig

config = PiAgentRuntimeConfig(
    provider_mode="live",
    provider_config_source="codex_current",
)
```

Pass `config` as `piworker_config=` to `run_piworker_call(...)`.

## Run DeepResearch v2

```bash
PYTHONPATH=src:integrations/deepresearch/src \
python3 -m missionforge_deepresearch.cli academic kernel-v2-run \
  --topic "调研主题" \
  --request-id research-001 \
  --workspace /tmp/mf-dr \
  --research-intensity standard \
  --live-extension-mode \
  --kernel-v2-adapter-mode piworker \
  --piworker-provider-config-source codex_current \
  --stream-progress
```

The command prints absolute output paths and token usage when metrics are
available.
