# MissionForge

MissionForge is a minimal delegation kernel around Pi.

Pi runs the intelligent agent loop. MissionForge freezes the task contract,
bounds tools and workspace access, records refs-first evidence, validates
outputs, routes independent judgment, and makes repair or revision explicit.

The current core formula is:

```text
MissionForge = Pi Agent loop + hard MissionForge boundary + deterministic validation
```

MissionForge is not a broad workflow framework, a provider marketplace, or a
product-specific automation system. It is a thin, inspectable shell for safely
delegating work to an unreliable but capable model.

## Default Runtime Shape

New work should use the TaskContract-native path:

```text
FrontDeskIntentBundle
  -> ProductIntegration
  -> TaskContract
  -> WorkerBrief + JudgeRubric + WorkspacePolicy + PermissionManifest
  -> PiWorkerCall(role=executor_piworker)
  -> PiAgentRuntimeInput
  -> workers/pi-agent-runtime
  -> PiWorkerCallResult + AgentExecutionReport
  -> hard checks
  -> PiWorkerCall(role=judge_piworker)
  -> JudgeReport
  -> accepted | repair | revision_required | rejected
  -> FinalPackage | RepairBrief | TaskRevisionRequest
  -> append-only DecisionLedger
```

The important distinction is authority:

- `TaskContract` is durable task truth.
- `PiWorkerCall` is the only intelligent invocation boundary.
- `PiAgentRuntimeInput` is the direct Pi runtime input.
- `PiWorkerCallResult` is boundary evidence, not acceptance.
- `JudgeReport` is the semantic decision surface.
- `FinalPackage` and `DecisionLedger` are the operator handoff and replay
  surface.

`WorkUnitContract` still exists as a compatibility projection for older code
and for the current Node sidecar prompt builder. It should not be treated as
the conceptual runtime API for new MissionForge work.

## What MissionForge Guarantees

MissionForge code owns hard boundaries:

- frozen `TaskContract` authority and content hashes;
- refs-only packets, reports, ledgers, and final packages;
- readable refs, writable refs, denied refs, and runtime-owned refs;
- command, network, environment, and unsupported hard-policy checks;
- executor/judge role separation;
- no executor self-acceptance;
- explicit same-contract repair;
- explicit contract revision before task truth changes;
- secret and raw transcript/provider/stdout/stderr/artifact-body exclusion from
  durable operational truth.

PiWorker nodes own semantic work:

- FrontDesk requirement discovery;
- executor artifact production;
- independent judging;
- repair execution;
- revision drafting.

## Repository Layout

```text
src/missionforge/
  agent_packets.py          Executor and judge packets/reports
  agentic_flow.py           Minimal TaskContract executor -> judge flow
  agentic_ledger.py         DecisionLedger, FinalPackage, replay summary
  agentic_repair.py         RepairBrief and TaskRevisionRequest contracts
  agentic_repair_controller.py
                            RepairTicket and RepairExecutionDirective
  agentic_revision_controller.py
                            RevisionPendingRecord and RevisionAppliedRecord
  piworker_call.py          Single intelligent RPC boundary
  piworker_runtime.py       Narrow Pi runtime construction and repair/revision bridge
  task_contract.py          TaskContract, WorkspacePolicy, PermissionManifest
  task_projection.py        WorkerBrief and JudgeRubric projections
  workspace_runtime.py      Workspace ref enforcement
  adapters/
    pi_agent_runtime.py     Pi Agent runtime adapter and PiAgentRuntimeInput
  frontdesk/
    pi_node_runner.py       FrontDesk PiWorker authoring boundary

workers/pi-agent-runtime/
  src/contract.ts           Node-side runtime input/output parser
  src/runtime.ts            Pi Agent loop sidecar
  src/tools.ts              Permission-aware file/bash tools

integrations/skillfoundry/
  External product integration that compiles product meaning into
  TaskContract-shaped MissionForge inputs.

docs/
  PI_BASED_MINIMAL_KERNEL_DEVELOPMENT_PLAN.md
  TASKCONTRACT_NATIVE_CUTOVER_PLAN.md
  modules/
```

Benchmark/value-benchmark code has been removed from the active product lane.
MissionForge core is now focused on the PiWorker kernel and one real external
integration, SkillFoundry.

## Quick Start For Development

Use the Node version declared in `.nvmrc` for `workers/pi-agent-runtime`.

Run the full local validation suite:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
```

Use the integration validator for SkillFoundry:

```bash
./scripts/validate_integrations.sh skillfoundry
```

If dependencies need a clean install, run without `MISSIONFORGE_SKIP_NPM_CI`:

```bash
./scripts/validate.sh
```

## Using The Default TaskContract Flow

Programmatic callers should assemble the default TaskContract-native Pi lane
through the narrow factory:

```python
from missionforge import create_default_task_contract_flow
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig

preset = create_default_task_contract_flow(
    "/tmp/missionforge-run",
    piworker_config=PiAgentRuntimeConfig(),
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

The caller supplies a frozen `TaskContract`, `WorkspacePolicy`, and
`PermissionManifest`. Product-specific meaning should be compiled outside
`src/missionforge`, then passed in through these contracts and refs.

The run writes refs such as:

```text
contract/task_contract.json
projections/worker_brief.json
projections/judge_rubric.json
packets/execution_packet.json
reports/execution_report.json
packets/judge_packet.json
reports/judge_report.json
ledgers/decision_ledger.jsonl
packages/final_package.json
checkpoints/latest.json
```

Replay the ledger without reading Pi chat memory:

```python
from missionforge import replay_decision_ledger

summary = replay_decision_ledger(
    "/tmp/missionforge-run/runs/run-001",
    decision_ledger_ref="ledgers/decision_ledger.jsonl",
)
```

## Repair And Revision

Repair preserves the same frozen contract hash. A judge repair decision creates
a `RepairBrief`, which can be bound into a `RepairTicket`, then into a
`RepairExecutionDirective`, then executed through the same PiWorker boundary:

```python
from missionforge import run_repair_directive_with_default_piworker

call_result = run_repair_directive_with_default_piworker(
    directive,
    workspace="/tmp/missionforge-run/runs/run-001",
    contract_ref="contract/task_contract.json",
    permission_manifest_ref="policy/permission_manifest.json",
    writable_refs=["artifacts", "reports"],
)
```

Revision changes task truth only after an explicit pending record, authority
decision, revised contract, and applied record:

```python
from missionforge import run_revision_draft_with_default_piworker

draft_result = run_revision_draft_with_default_piworker(
    pending,
    workspace="/tmp/missionforge-run/runs/run-001",
    permission_manifest_ref="policy/permission_manifest.json",
    writable_refs=["revisions/revision-request-001"],
    expected_output_ref="revisions/revision-request-001/revised_task_contract.json",
)
```

## Public API Guidance

Use these as the primary MissionForge kernel surface:

- `TaskContract`
- `WorkspacePolicy`
- `PermissionManifest`
- `WorkerBrief`
- `JudgeRubric`
- `AgenticFlowRunner`
- `create_default_task_contract_flow`
- `PiWorkerCall`
- `PiWorkerCallResult`
- `FinalPackage`
- `TaskContractDecisionLedgerEntry`
- `replay_decision_ledger`
- `run_repair_directive_with_default_piworker`
- `run_revision_draft_with_default_piworker`

Adapter internals such as `PiAgentRuntimeAdapter` are intentionally not
exported from the package root. Import them directly only when building or
testing adapter-specific behavior.

MissionIR and the older deterministic runtime remain in the repository as
compatibility/high-detail surfaces. New product work should prefer
TaskContract-native PiWorker calls.

## Operator Surface

The optional CLI adapter emits refs-only command envelopes:

```bash
python -m missionforge.adapters.cli run --workspace . --mission-ref missions/input.mission.json
python -m missionforge.adapters.cli inspect --workspace . --run run-sample-mission
python -m missionforge.adapters.cli diagnose --workspace . --run run-sample-mission
python -m missionforge.adapters.cli resume --workspace . --run run-sample-mission --mission-ref missions/input.mission.json
python -m missionforge.adapters.cli control halt --workspace . --run run-sample-mission --reason "Pause before the next attempt."
python -m missionforge.adapters.cli review record --workspace . --run run-sample-mission --decision approved --review-ref reviews/reviewer-decision.json
python -m missionforge.adapters.cli validate
```

Operator output is observation and control. It does not grant semantic
acceptance by itself.

## Design Documents

Start here:

- [Pi-Based Minimal Kernel Development Plan](docs/PI_BASED_MINIMAL_KERNEL_DEVELOPMENT_PLAN.md)
- [TaskContract Native Cutover Plan](docs/TASKCONTRACT_NATIVE_CUTOVER_PLAN.md)
- [Module: PiWorker](docs/modules/piworker.md)
- [Module: Agentic Flow](docs/modules/agentic_flow.md)
- [Module: FrontDesk](docs/modules/frontdesk.md)
- [Product Integration Boundary](docs/PRODUCT_INTEGRATION_BOUNDARY.md)

The short version: Pi is the intelligent loop. MissionForge is the deterministic
contract, permission, evidence, validation, judge, repair, revision, and replay
kernel around it.
