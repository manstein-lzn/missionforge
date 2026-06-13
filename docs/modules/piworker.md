# Module: PiWorker

## Goal

PiWorker is MissionForge's single first-class intelligent worker direction.
MissionForge treats one PiWorker call as an unreliable intelligence RPC:
deterministic code declares refs, write scope, expected outputs, contract
binding, role, and permission boundary; the PiWorker decides how to do the
semantic work inside those boundaries.

Current production lane:

```text
PiWorkerCall -> PiAgentRuntimeInput -> workers/pi-agent-runtime -> PiWorkerCallResult
```

## Current Status

TaskContract-native execution constructs role-separated
`AgentExecutionPacket` and `JudgePacket` objects, projects each runtime call
through `PiWorkerCall`, then writes a direct `PiAgentRuntimeInput` for
`PiAgentRuntimeAdapter`.

The Node sidecar still receives a small field named `contract` for runtime
compatibility, but MissionForge authority is the `PiWorkerCall` boundary:

- packets carry role-specific semantic context and hash bindings;
- `PiWorkerCall` carries the shared invocation boundary;
- `PiAgentRuntimeInput` carries call id, refs, expected outputs, permission
  manifest, runtime metadata, repair/resume envelope, and the minimal sidecar
  projection;
- PI Agent runtime owns the inner loop, tools, hooks, session artifacts, and
  model calls.

FrontDesk authoring, executor, judge, repair, and revision-drafting nodes all
use the same direct boundary with role-specific `PiWorkerCallRole` values. Call
results are persisted under `attempts/<call_id>/piworker_call_result.json` and
can be cited by ledgers and repair/revision controllers without reading PI chat
memory.

The adapter rejects raw prompt/transcript/payload/body/stdout/stderr/secret
fields, validates safe refs and hashes, requires expected outputs, and rejects
outputs outside writable refs.

Default tests run the PI Agent runtime in faux provider mode. Live provider
execution is opt-in through `provider_mode="live"` and current Codex config
resolution when requested. Provider credentials are passed only through child
process environment variables and are never serialized into MissionForge input
artifacts, evidence, execution reports, metrics, docs, or logs.

## Public Contracts

- `PiWorkerCall`
- `PiWorkerCallRole`
- `PiWorkerCallResult`
- `PiWorkerCallResultStatus`
- `PiWorkerCallAdapter`
- `PiWorkerRuntimeFactory`
- `create_default_piworker_adapter`
- `create_default_task_contract_flow`
- `run_repair_directive_with_default_piworker`
- `run_revision_draft_with_default_piworker`

Adapter internals such as `PiAgentRuntimeAdapter`, `PiAgentRuntimeConfig`,
`PiAgentExecutorNode`, and `PiAgentJudgeNode` live under
`missionforge.adapters.pi_agent_runtime` and are intentionally not exported
from the package root.

## Contract Sketch

```json
{
  "call_id": "WU-000001",
  "schema_version": "piworker_call.v1",
  "role": "executor_piworker",
  "contract_id": "contract-001",
  "contract_hash": "sha256:...",
  "contract_ref": "contract/task_contract.json",
  "objective": "Produce expected artifacts for contract-001.",
  "visible_refs": [
    "contract/task_contract.json",
    "projections/worker_brief.json",
    "policy/workspace_policy.json",
    "policy/permission_manifest.json"
  ],
  "writable_refs": ["artifacts", "reports"],
  "expected_output_refs": ["artifacts/final.md"],
  "permission_manifest_ref": "policy/permission_manifest.json",
  "source_packet_ref": "packets/execution_packet.json",
  "source_packet_hash": "sha256:...",
  "evidence_refs": [],
  "metadata": {}
}
```

The sidecar input wraps that call with runtime refs and permission data:

```json
{
  "schema_version": "missionforge.pi_agent_runtime_input.v1",
  "call_id": "WU-000001",
  "mission_id": "contract-001",
  "input_ref": "attempts/WU-000001/pi_agent_input.json",
  "output_ref": "attempts/WU-000001/pi_agent_output.json",
  "piworker_call": {
    "schema_version": "piworker_call.v1",
    "call_id": "WU-000001"
  },
  "contract": {
    "call_id": "WU-000001",
    "mission_id": "contract-001",
    "allowed_scope": ["artifacts", "reports"],
    "visible_refs": [
      "contract/task_contract.json",
      "projections/worker_brief.json",
      "policy/permission_manifest.json"
    ],
    "expected_outputs": ["artifacts/final.md"]
  },
  "permission_manifest": {
    "schema_version": "permission_manifest.v1",
    "writable_refs": ["artifacts", "reports"],
    "network_policy": "disabled"
  }
}
```

Provider, cache, token, and tool metrics are diagnostics and evidence. They are
not semantic route or acceptance authority.

## Invariants

- PiWorker receives a bounded call/runtime contract.
- PiWorker writes only through allowed tools or write scopes.
- PiWorker output is evidence, not acceptance.
- The executor may not self-accept its own work.
- Contract changes require explicit revision records and authority.
- Live provider credentials remain child-process environment only.
- Core default construction uses the narrow PiWorker runtime boundary, not a
  public worker registry.
- Offline faux-provider tests must pass before live PiWorker smoke tests.

## Attribution

The PI GitHub project is MIT-licensed. MissionForge is inspired by PI. Any
copied or adapted PI source must retain required attribution.
