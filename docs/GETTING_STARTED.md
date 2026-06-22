# Getting Started

MissionForge is a small kernel for bounded PiWorker calls.

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
    contract_hash="sha256:" + "a" * 64,
    contract_ref="contract/task_contract.json",
    objective="Produce package/output.md from visible refs.",
    visible_refs=["contract/task_contract.json", "inputs/request.json"],
    writable_refs=["package", "reports"],
    expected_output_refs=["package/output.md"],
    permission_manifest_ref="policy/permission_manifest.json",
)

result = run_piworker_call(call, workspace="/tmp/missionforge-run")
```

## Rules

- `TaskContract` is frozen task truth.
- `PiWorkerCallResult` records whether the worker boundary completed.
- The executor cannot accept its own work.
- Acceptance belongs to an independent judge PiWorker or product integration.
- Runtime state should cite refs, not raw prompts, provider payloads, stdout,
  stderr, artifact bodies, or secrets.

## Validate

```bash
PYTHONPATH=src python3 -m unittest tests.test_kernel_api tests.test_piworker_call
PYTHONPATH=src:integrations/deepresearch/src python3 -m unittest integrations.deepresearch.tests.test_kernel_v2
```
