# MissionForge

MissionForge is a minimal delegation kernel around Pi.

Pi runs the intelligent agent loop. MissionForge freezes the task contract,
bounds tools and workspace access, records refs-first evidence, validates
outputs, routes independent judgment, and makes repair or revision explicit.

The core formula is:

```text
MissionForge = Pi Agent loop + hard MissionForge boundary + deterministic validation
```

MissionForge is not a broad workflow framework, a provider marketplace, or a
product-specific automation system. It is a thin, inspectable shell for safely
delegating work to an unreliable but capable model.

If you are using MissionForge as a programmer, start here:

- [Getting Started](docs/GETTING_STARTED.md)
- [User Manual](docs/USER_MANUAL.md)
- [Primitive Reference](docs/PRIMITIVE_REFERENCE.md)
- [Cookbook](docs/COOKBOOK.md)
- [Migration Guide](docs/MIGRATION_GUIDE.md)
- [Live Runtime Guide](docs/LIVE_RUNTIME_GUIDE.md)

## Current Status

This branch is centered on the TaskContract-native PiWorker runtime:

- `PiWorkerCall` is the single intelligent invocation boundary.
- `TaskContract`, `WorkspacePolicy`, and `PermissionManifest` are the durable
  task, workspace, and tool authority.
- `WorkerBrief` and `JudgeRubric` are projections from the frozen contract.
- Executor and judge are separate PiWorker roles.
- `DecisionLedger`, `FinalPackage`, repair, revision, and replay are refs-first
  runtime surfaces.
- SkillFoundry is the active external product integration.
- The old active value-benchmark lane has been removed from the product path.

`MissionIR` remains importable from `missionforge.ir` only as a high-detail
compatibility data shape. The old deterministic runtime, harness, work-unit, and
fake-worker modules have been removed. New product work should use the
TaskContract-native PiWorker path.

## Runtime Shape

Use this shape for new work:

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

Authority is deliberately narrow:

- Raw chat is not task truth.
- `TaskContract` is durable task truth.
- `PiWorkerCallResult` is boundary evidence, not acceptance.
- `JudgeReport` is the semantic decision surface.
- The executor cannot accept its own work.
- Contract changes after execution starts require explicit revision records.

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

## What MissionForge Does Not Do

MissionForge core does not infer product intent with deterministic if/else
logic, own product-specific semantics, expose a provider zoo, or use Pi session
summaries as task authority. Product meaning belongs in external integrations,
inquiry profiles, task contracts, judge rubrics, artifact refs, and product
packages.

## Repository Layout

```text
src/missionforge/
  task_contract.py          TaskContract, WorkspacePolicy, PermissionManifest
  task_projection.py        WorkerBrief and JudgeRubric projections
  piworker_call.py          Single intelligent RPC boundary
  piworker_runtime.py       Default PiWorker runtime factories
  agent_packets.py          Executor and judge packets/reports
  agentic_flow.py           Minimal TaskContract executor -> judge flow
  agentic_ledger.py         DecisionLedger, FinalPackage, replay summary
  agentic_repair.py         RepairBrief and TaskRevisionRequest contracts
  agentic_repair_controller.py
                            RepairTicket and RepairExecutionDirective
  agentic_revision_controller.py
                            Revision pending/applied records
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
  External product integration that compiles SkillFoundry meaning into
  TaskContract-shaped MissionForge inputs.

docs/
  GETTING_STARTED.md
  USER_MANUAL.md
  PRIMITIVE_REFERENCE.md
  COOKBOOK.md
  API_BOUNDARY.md
  modules/
```

## Requirements

- Python 3.11 or newer.
- Node 22.19.0 or newer for `workers/pi-agent-runtime`; the checkout includes
  `.nvmrc`.
- npm for the Pi sidecar dependencies.
- A live model provider only when using `provider_mode="live"`. The default
  development path uses the faux provider and needs no secret.

## Install From A Checkout

Create a Python environment and install the core package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Install and build the Pi Agent runtime sidecar:

```bash
npm ci --ignore-scripts --prefix workers/pi-agent-runtime
npm run build --prefix workers/pi-agent-runtime
```

Install the SkillFoundry integration when working on that product shell:

```bash
python3 -m pip install -e integrations/skillfoundry
```

## Validate

Run the full local validation suite:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
```

Run without `MISSIONFORGE_SKIP_NPM_CI` when dependencies need a clean install:

```bash
./scripts/validate.sh
```

Run the active integration suite:

```bash
./scripts/validate_integrations.sh skillfoundry
```

Expected coverage at this point:

- Node Pi runtime tests pass.
- Python MissionForge tests pass.
- SkillFoundry integration tests pass.
- `git diff --check` passes.

## Run The Default TaskContract Lane

Programmatic callers should assemble the default TaskContract-native Pi lane
through the narrow factory:

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

The caller supplies a frozen `TaskContract`, `WorkspacePolicy`, and
`PermissionManifest`. Product-specific meaning should be compiled outside
`src/missionforge`, then passed in through these contracts and refs.

If `hard_check_status` is `passed`, every ref in `hard_check_refs` must already
exist in the run workspace. For example:

```text
/tmp/missionforge-run/runs/run-001/reports/hard_checks.json
```

A complete offline executable fixture is maintained in
`tests/test_agentic_flow.py`. It is the best starting point for adapting a new
product integration because it exercises the same contract, permission, packet,
judge, ledger, and final-package path without requiring a live model.

For a standalone product-shell shape that does not depend on test fixtures, run:

```bash
PYTHONPATH=src python3 examples/standalone_product_shell.py /tmp/mf-standalone-demo
```

That example compiles product meaning into TaskContract-native primitives,
runs a deterministic executor and independent judge, and replays the decision
ledger.

## Configure The Pi Agent Runtime

The default `PiAgentRuntimeConfig` uses the faux provider:

```python
PiAgentRuntimeConfig(provider_mode="faux")
```

Use it for local development, tests, and integration wiring. It proves that the
MissionForge boundary is valid without spending model calls.

For live Pi-backed execution, set the provider mode to `live` and provide model
configuration from environment variables:

```bash
export MISSIONFORGE_PI_AGENT_PROVIDER=live
export MISSIONFORGE_PI_AGENT_MODEL=gpt-5.5
export MISSIONFORGE_PI_AGENT_BASE_URL=https://example.test/v1
export MISSIONFORGE_PI_AGENT_API_KEY=...
export MISSIONFORGE_PI_AGENT_REASONING=xhigh
export MISSIONFORGE_PI_AGENT_MAX_TURNS=12
export MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS=60
```

Then construct the runtime with:

```python
PiAgentRuntimeConfig(provider_mode="live", provider_config_source="env")
```

If the current Codex provider is configured with `wire_api = "responses"`, the
runtime can also read it:

```python
PiAgentRuntimeConfig(provider_mode="live", provider_config_source="codex_current")
```

Secrets are passed only to the child runtime environment and are redacted from
recorded diagnostic evidence.

## Runtime Outputs

A successful run writes refs such as:

```text
contract/task_contract.json
contract/task_contract.hash
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

The replay surface is refs-first. It should not need raw transcripts, provider
payloads, stdout/stderr bodies, artifact bodies, or secrets.

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

## SkillFoundry Integration

SkillFoundry is intentionally outside the `missionforge` Python package:

```text
missionforge_skillfoundry -> missionforge
missionforge -> does not import missionforge_skillfoundry
```

Its default compile path emits `TaskContract`, `WorkspacePolicy`, and
`PermissionManifest` refs under `runs/{bundle_id}/`. SkillFoundry execution does
not go through a MissionForge runtime or work-unit compatibility facade.

Run SkillFoundry tests from the repository root:

```bash
PYTHONPATH=src:integrations/skillfoundry/src \
  python3 -m unittest discover -s integrations/skillfoundry/tests
```

See [SkillFoundry README](integrations/skillfoundry/README.md) for the product
shell details.

## Operator CLI

The optional CLI adapter is an operator shell for inspecting refs-only run state,
recording explicit control intent, recording independent review decisions, and
validating the repository:

```bash
python -m missionforge.adapters.cli inspect --workspace . --run run-sample-mission
python -m missionforge.adapters.cli diagnose --workspace . --run run-sample-mission
python -m missionforge.adapters.cli control halt --workspace . --run run-sample-mission --reason "Pause before the next attempt."
python -m missionforge.adapters.cli review record --workspace . --run run-sample-mission --decision approved --review-ref reviews/reviewer-decision.json
python -m missionforge.adapters.cli validate
```

There is no top-level `run` or `resume` command. Operator output is observation
and control. It does not grant semantic acceptance by itself. Product execution
belongs in the TaskContract-native PiWorker lane.

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
- `PiWorkerCallAdapter`
- `PiWorkerCallResult`
- `FinalPackage`
- `TaskContractDecisionLedgerEntry`
- `replay_decision_ledger`
- `run_repair_directive_with_default_piworker`
- `run_revision_draft_with_default_piworker`

Adapter internals such as `PiAgentRuntimeAdapter` are intentionally not
exported from the package root. Import them directly only when building or
testing adapter-specific behavior.

Retired runtime and work-unit symbols such as `MissionRuntime`, `RuntimeEngine`,
and `WorkUnitContract` have been removed. `MissionIR` remains available from
`missionforge.ir` as a high-detail compatibility data shape, but new product
integrations should compile into `TaskContract` and run through the
TaskContract/PiWorker lane.

## Design Documents

Start here:

- [Getting Started](docs/GETTING_STARTED.md)
- [User Manual](docs/USER_MANUAL.md)
- [Primitive Reference](docs/PRIMITIVE_REFERENCE.md)
- [Cookbook](docs/COOKBOOK.md)
- [Migration Guide](docs/MIGRATION_GUIDE.md)
- [Live Runtime Guide](docs/LIVE_RUNTIME_GUIDE.md)
- [Module: PiWorker](docs/modules/piworker.md)
- [Module: Agentic Flow](docs/modules/agentic_flow.md)
- [Module: FrontDesk](docs/modules/frontdesk.md)
- [Product Integration Boundary](docs/PRODUCT_INTEGRATION_BOUNDARY.md)

The short version: Pi is the intelligent loop. MissionForge is the deterministic
contract, permission, evidence, validation, judge, repair, revision, and replay
kernel around it.
