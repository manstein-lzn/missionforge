# User Manual

MissionForge lets Python programmers compose code and model calls in the same
system. Treat a PiWorker call as an unreliable but capable RPC:

```text
Python code defines intent, refs, permissions, and expected outputs
PiWorker decides how to do the semantic work
Python code validates boundaries and decides the next step
```

The package provides primitives. It does not prescribe how to build your
product.

## Core Mental Model

Old code calls deterministic functions:

```python
value = function(input)
```

MissionForge calls bounded intelligence:

```python
result = run_piworker_call(call, workspace=workspace)
```

That call is not trusted by default. It is surrounded by:

- `TaskContract`: frozen task authority;
- `WorkspacePolicy`: where files may live;
- `PermissionManifest`: what the worker may read, write, run, or access;
- `PiWorkerCall`: one bounded model invocation;
- `PiWorkerCallResult`: refs-first evidence that the call completed or failed;
- optional independent judge and ledger layers built from the same primitives.

For fine-grained autonomy, the runtime should also create a short-lived
capability grant for each agent role. The grant selects the sandbox, workspace
view, command policy, network policy, and runtime budget for that agent. The
sandbox is the hard boundary; the grant is the authority ticket.

In the bundled Pi runtime, the Python adapter now emits both
`capability_grant` and `sandbox_profile` into the runtime input envelope, and
the TypeScript worker validates that they match the permission manifest before
tools start. That keeps the boundary white-box and lets you compose your own
runtime without hand-authoring those envelopes in every caller.

In the bundled Pi runtime, file and shell tools enter through a `ToolGateway`.
The gateway authorizes refs and command scope, then records safe audit events.
Those events contain refs, command hashes, cwd refs, environment variable names,
decision status, and reason codes. They do not contain artifact bodies, raw
commands, stdout/stderr bodies, environment values, provider payloads, or
secrets.

## Root Imports

Normal application code should start from the root kernel:

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

Use explicit modules only when you need a higher-level composition:

```python
from missionforge.agentic_flow import AgenticFlowRunner
from missionforge.agent_packets import JudgeReport
from missionforge.frontdesk import FrontDesk
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig
```

This keeps the default surface small while leaving the system white-box.

## One PiWorker Call

A direct call needs a contract binding, visible refs, writable refs, and
expected output refs:

```python
from missionforge import PiWorkerCall, PiWorkerCallRole, run_piworker_call

call = PiWorkerCall(
    call_id="call-001",
    role=PiWorkerCallRole.EXECUTOR,
    contract_id=contract.contract_id,
    contract_hash=contract.contract_hash,
    contract_ref="contract/task_contract.json",
    objective="Write the requested artifact under package/.",
    visible_refs=[
        "contract/task_contract.json",
        "policy/permission_manifest.json",
        "inputs/request.json",
    ],
    writable_refs=["package", "reports"],
    expected_output_refs=["package/SKILL.md"],
    permission_manifest_ref="policy/permission_manifest.json",
)

result = run_piworker_call(call, workspace="/tmp/my-run")
```

`result.status` tells you whether the boundary completed. It does not mean the
artifact is semantically accepted.

## Build Your Own System

Your application can compose these primitives however it wants:

```text
single PiWorkerCall
single call + your own validator
executor call + independent judge call
executor + judge + repair loop
FrontDesk + ProductIntegration + TaskContract flow
larger distributed system with MissionForge calls as nodes
```

MissionForge's rule is narrow: core code owns schemas, refs, workspace
boundaries, permission manifests, evidence, role separation, and ledgers.
Product meaning stays in your application, product integration, contracts,
rubrics, artifacts, and tests.

## TaskContract

`TaskContract` is durable task truth. Raw chat is not.

Use it to capture:

- objective;
- required output refs;
- hard constraints;
- semantic acceptance criteria;
- source refs;
- workspace and permission refs;
- explicit revision policy.

Product code may construct it directly or compile it from a UI, config file,
FrontDesk intent bundle, ticket, issue, design document, or another system.

## Workspace And Permissions

`WorkspacePolicy` declares the filesystem plane:

- input refs;
- artifact roots;
- scratch roots;
- denied refs.

`PermissionManifest` declares the operation boundary:

- readable refs;
- writable refs;
- denied refs;
- allowed commands;
- network policy;
- environment allowlist.

Do not rely on prompts alone for safety. Put hard boundaries in these
structures and in the runtime/tool layer.

In the bundled Pi runtime, file tools enforce readable/writable/denied refs
directly. If `allowed_commands` is non-empty, the bash tool is exposed only for
exact command strings and executes inside a `bubblewrap` sandbox view: readable
refs are readonly, writable refs are writable, denied refs are masked, and the
environment is reduced to `env_allowlist` plus minimal runtime variables.
`network_policy: restricted` still fails closed because domain-level network
enforcement is not implemented.

If you need multiple agents, do not share one writable Python process and hope
for soft isolation. Give each agent its own sandboxed execution context and
exchange state through refs, ledgers, or explicit promoted artifacts.

## Independent Judgment

The executor must not accept its own work. If you need semantic acceptance,
compose a judge call or use `missionforge.agentic_flow`.

The bundled flow is available as a convenience:

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

The flow is not a mandate. It is one composition built from the same
TaskContract, projection, PiWorkerCall, packet, evidence, and ledger
primitives.

## Repair And Revision

Same-contract repair and explicit contract revision live in advanced modules:

- `missionforge.agentic_repair`
- `missionforge.agentic_repair_controller`
- `missionforge.agentic_revision_controller`
- `missionforge.piworker_runtime`

Use them when you want the standard governance path:

```text
judge says repair
  -> same contract hash
  -> repair worker
  -> independent rejudge

judge says revision_required
  -> pending revision
  -> revised TaskContract proposal
  -> explicit approval
  -> new contract hash
  -> execution resumes under new authority
```

These modules are explicit imports because they are higher-level governance
composition, not the minimal model-call kernel.

## Standalone Example

Run the standalone product shell:

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

That file shows how product code can compile a tiny request into MissionForge
primitives, run an executor and independent judge, and replay the ledger
without product branches in core.

## Live Pi

Default development should use faux execution. Use live Pi only when explicitly
dogfooding or smoke-testing a real model channel. See
`docs/LIVE_RUNTIME_GUIDE.md`.

## Validation

Run both suites before treating a change as done:

```bash
MISSIONFORGE_SKIP_NPM_CI=1 ./scripts/validate.sh
./scripts/validate_integrations.sh skillfoundry
```
