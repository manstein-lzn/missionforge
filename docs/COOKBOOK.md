# Cookbook

Short composition patterns for programmers.

## 1. Run A Default TaskContract Flow

```python
preset = create_default_task_contract_flow("/tmp/run")
result = preset.runner.run(
    run_id="run-001",
    contract=task_contract,
    workspace_policy=workspace_policy,
    permission_manifest=permission_manifest,
    executor=preset.executor,
    judge=preset.judge,
)
```

## 2. Build A Repair Call

Use `run_repair_directive_with_default_piworker(...)` when the judge produced
`repair`. Feed it a validated `RepairExecutionDirective` and a writable scope
for the repaired artifact roots.

Then bridge the repair result back to an independent judge:

```python
from missionforge.piworker_runtime import run_repair_directive_with_default_piworker
from missionforge.agentic_repair_controller import build_repair_rejudge_packet

call_result = run_repair_directive_with_default_piworker(
    directive,
    workspace=run_root,
    contract_ref="contract/task_contract.json",
    permission_manifest_ref="policy/permission_manifest.json",
    writable_refs=["artifacts", "reports"],
)
judge_packet = build_repair_rejudge_packet(
    directive=directive,
    call_result=call_result,
    workspace=controller_workspace,
)
```

The returned `judge_packet` is not acceptance. It is the next input for a
separate judge.

## 3. Build A Revision Draft

Use `run_revision_draft_with_default_piworker(...)` when the judge produced
`revision_required`. Feed it a validated `RevisionPendingRecord` and a
revision output root.

Then load the draft as a proposal, not as new authority:

```python
from missionforge.agentic_revision_controller import load_revision_draft_contract
from missionforge.piworker_runtime import run_revision_draft_with_default_piworker

call_result = run_revision_draft_with_default_piworker(
    pending,
    workspace=run_root,
    permission_manifest_ref="policy/permission_manifest.json",
    writable_refs=[f"revisions/{pending.request_id}"],
    expected_output_ref=f"revisions/{pending.request_id}/revised_task_contract.json",
)
revised_contract = load_revision_draft_contract(
    pending=pending,
    call_result=call_result,
    workspace=controller_workspace,
    expected_output_ref=f"revisions/{pending.request_id}/revised_task_contract.json",
)
```

Apply it only after the proper authority writes an approved
`TaskRevisionDecision`.

## 4. Keep Product Semantics Outside Core

Compile product-specific intent in `integrations/<product>/...`, then hand
MissionForge only:

- `TaskContract`
- `WorkspacePolicy`
- `PermissionManifest`
- judge rubric refs
- evidence refs

## 5. Run SkillFoundry Through TaskContract

SkillFoundry's TaskContract-native facade stays outside core:

```python
from missionforge_skillfoundry import run_skillfoundry_task_contract_bundle_build

report = run_skillfoundry_task_contract_bundle_build(request, workspace=".")
```

It compiles product intent to TaskContract refs, runs the MissionForge
executor/judge boundary, and writes product reports in the integration
workspace.

## 6. Use Live Pi Only For Dogfood

Keep the default config faux. Switch to live only when you need to verify the
real provider path.

## 7. Start From The Standalone Shell

Run the manual-only product shell example:

```bash
PYTHONPATH=src python3 examples/standalone_product_shell.py /tmp/mf-standalone-demo
```

Use its structure for new integrations:

- request dataclass
- product compiler returning `TaskContract`, `WorkspacePolicy`, and
  `PermissionManifest`
- executor node
- independent judge node
- ledger replay check
