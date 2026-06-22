# User Manual

MissionForge lets Python programmers compose bounded PiWorker calls with hard
workspace, contract, evidence, and permission boundaries.

## Mental Model

```text
Python declares refs, permissions, expected outputs, and role
PiWorker performs semantic work
MissionForge validates boundaries and records refs-first evidence
An independent judge or product integration decides acceptance
```

MissionForge is not a deterministic expert system. Product meaning belongs in
contracts, manuals, rubrics, tools, evidence refs, and integration packages.

## Root Imports

```python
from missionforge import (
    PermissionManifest,
    PiWorkerCall,
    PiWorkerCallRole,
    TaskContract,
    WorkspacePolicy,
    run_piworker_call,
)
```

Use explicit modules for adapter configuration:

```python
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig
```

## One PiWorker Call

```python
from missionforge import PiWorkerCall, PiWorkerCallRole, run_piworker_call

call = PiWorkerCall(
    call_id="call-001",
    role=PiWorkerCallRole.EXECUTOR,
    contract_id="contract-001",
    contract_hash="sha256:" + "a" * 64,
    contract_ref="contract/task_contract.json",
    objective="Write the requested artifact under package/.",
    visible_refs=["contract/task_contract.json", "inputs/request.json"],
    writable_refs=["package", "reports"],
    expected_output_refs=["package/SKILL.md"],
    permission_manifest_ref="policy/permission_manifest.json",
)

result = run_piworker_call(call, workspace="/tmp/my-run")
```

`result.status` says whether the runtime boundary completed. It does not mean
the artifact is semantically accepted.

## Build A Product

A product integration normally does this:

1. Discover or receive user intent.
2. Compile intent into `TaskContract`, `WorkspacePolicy`, and
   `PermissionManifest`.
3. Write manuals, prompts, rubrics, output schemas, and source packets as refs.
4. Run one or more role-specific `PiWorkerCall`s.
5. Let an independent reviewer/judge role decide readiness or acceptance.
6. Package refs, metrics, and usage summaries for the user.

Use Python for boundaries and mechanical projection. Use PiWorker for semantic
research, synthesis, critique, repair planning, and judgment.

## Live Runtime

Prefer Codex current provider config for local development:

```python
config = PiAgentRuntimeConfig(
    provider_mode="live",
    provider_config_source="codex_current",
)
```

Then pass `piworker_config=config` to `run_piworker_call(...)`.

## DeepResearch v2

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

The CLI prints absolute report paths and token usage when available.
