# User Manual

MissionForge is a deterministic kernel around a PiWorker intelligence layer.
Use it by composing contracts, not by reading runtime source.

## Mental Model

```text
Product Integration
  -> TaskContract
  -> PiWorkerCall
  -> Pi Agent runtime
  -> executor artifacts
  -> independent judge
  -> accepted | repair | revision_required | rejected
```

## What You Build

You usually provide:

- a frozen `TaskContract`
- `WorkspacePolicy`
- `PermissionManifest`
- worker and judge projections
- hard-check refs
- optional product-specific integration code outside `src/missionforge`

## Build A Product Shell

A product shell is ordinary application code outside `src/missionforge`. It
does three things:

1. Compile product meaning into MissionForge contracts.
2. Provide an executor and independent judge, usually PiWorker-backed in real
   use and deterministic in tests.
3. Read refs-first results, ledgers, and final packages.

The smallest standalone example is
`examples/standalone_product_shell.py`. Run it from the repository root:

```bash
PYTHONPATH=src python3 examples/standalone_product_shell.py /tmp/mf-standalone-demo
```

Expected shape:

```text
status=accepted
replay_status=accepted
final_package_ref=packages/final_package.json
accepted_artifact_refs=['package/README.md']
```

That file is intentionally standalone product code. It imports public
MissionForge primitives, compiles a small product request into `TaskContract`,
`WorkspacePolicy`, and `PermissionManifest`, runs an executor and a separate
judge, then replays the decision ledger. It should be the first file to copy
when proving that a new product shell can be built without reading
MissionForge internals.

## Main Entry Points

- `create_default_task_contract_flow(...)`
- `PiWorkerRuntimeFactory`
- `PiWorkerCallAdapter`
- `run_repair_directive_with_default_piworker(...)`
- `build_repair_rejudge_packet(...)`
- `run_revision_draft_with_default_piworker(...)`
- `load_revision_draft_contract(...)`
- `build_revision_execution_directive(...)`
- `build_revision_rejudge_packet(...)`
- `build_revision_judge_result(...)`
- `AgenticFlowRunner`

## What The Flow Guarantees

- The executor cannot accept its own work.
- The judge must use the frozen contract and evidence refs.
- Runtime-owned refs stay in the runtime evidence plane.
- Raw prompts, transcripts, payload bodies, stdout/stderr bodies, and secrets
  do not become durable task truth.

## When To Use SkillFoundry

Use `integrations/skillfoundry` when you want a real external product example.
It compiles product intent into the MissionForge contracts and proves the core
boundary without adding product branches to core.

The TaskContract-native product facade is
`run_skillfoundry_task_contract_bundle_build(...)`. The older
`run_skillfoundry_bundle_build(...)` facade has been removed.

## When To Use Live Pi

Use live Pi only for explicit dogfood or smoke validation. Default development
should stay on faux execution.

## Repair Continuation

When a judge returns `repair`, the repair path is still under the same frozen
contract hash:

```text
JudgeReport(decision=repair)
  -> RepairBrief
  -> RepairTicket
  -> RepairExecutionDirective
  -> PiWorkerCall(role=repair_piworker)
  -> PiWorkerCallResult
  -> build_repair_rejudge_packet(...)
  -> JudgePacket
  -> independent JudgeReport
```

`build_repair_rejudge_packet(...)` records the repair execution report and
builds the next judge packet. It does not accept the work. A separate judge
must still read the frozen contract, rubric, repaired artifact refs, evidence
refs, and hard-check refs before deciding `accepted`, `repair`,
`revision_required`, or `rejected`.

The controller needs read access to the refs-only
`attempts/<call_id>/piworker_call_result.json` written by the runtime. It does
not need write access to `attempts`.

## Revision Continuation

When a judge returns `revision_required`, the current contract stays
authoritative until an explicit revision is approved and applied:

```text
JudgeReport(decision=revision_required)
  -> TaskRevisionRequest
  -> RevisionPendingRecord
  -> PiWorkerCall(role=revision_drafter_piworker)
  -> PiWorkerCallResult
  -> load_revision_draft_contract(...)
  -> TaskRevisionDecision(approved)
  -> apply_task_contract_revision(...)
  -> RevisionAppliedRecord + TaskContractRevision
  -> build_revision_execution_directive(...)
  -> revised-contract AgentExecutionPacket
  -> PiWorkerCallResult
  -> build_revision_rejudge_packet(...)
  -> independent revised-contract JudgePacket
  -> build_revision_judge_result(...)
  -> accepted | repair | revision_required | rejected
```

`load_revision_draft_contract(...)` loads the drafter's revised
`TaskContract` proposal and checks that it is bound to the pending revision
record, came from the revision-drafter role, completed, and changes the
contract hash. It does not approve the revision. Approval remains an explicit
authority record.

`build_revision_execution_directive(...)` is the next deterministic bridge. It
checks the applied revision, revised contract, workspace policy, and permission
manifest, then writes a revised-contract `WorkerBrief` and `AgentExecutionPacket`
under `revisions/{request_id}/...`. It does not run the worker and does not
judge the result.

`build_revision_rejudge_packet(...)` records the revised-contract execution
result as an `AgentExecutionReport`, writes a revised `JudgeRubric`, and builds
the independent judge packet. It still does not accept the work; acceptance
requires a separate judge result over the revised contract.

`build_revision_judge_result(...)` validates the revised judge report and writes
the revised `AgenticFlowResult`. If the revised judge accepts, it writes a final
package under `revisions/{request_id}/packages/`. The decision ledger records
the explicit `revision_applied` transition before revised judge/final events, so
ledger replay can explain the contract hash change.

## Validation

Run both suites before treating a change as done:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
./scripts/validate_integrations.sh skillfoundry
```
