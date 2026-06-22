# Module: PiWorker

PiWorker is MissionForge's only first-class intelligent worker direction.

MissionForge treats one PiWorker call as an unreliable intelligence RPC:
deterministic code declares refs, write scope, expected outputs, contract
binding, role, and permission boundary; PiWorker decides how to do semantic
work inside those boundaries.

## Runtime Lane

```text
PiWorkerCall
  -> PiAgentRuntimeInput
  -> workers/pi-agent-runtime
  -> PiWorkerCallResult
```

## Public Contracts

- `PiWorkerCall`
- `PiWorkerCallRole`
- `PiWorkerCallResult`
- `PiWorkerCallResultStatus`
- `PiWorkerCallAdapter`
- `create_default_piworker_adapter`
- `run_piworker_call`

Adapter internals such as `PiAgentRuntimeAdapter` and
`PiAgentRuntimeConfig` live under `missionforge.adapters.pi_agent_runtime`.
They are not exported from the package root.

## Boundary Guarantees

- The call must bind to a contract id/hash/ref.
- Expected outputs must be under writable refs.
- Permission manifests are enforced before runtime invocation.
- Output refs, runtime refs, evidence refs, and metrics refs stay separate.
- Result metadata cannot claim semantic acceptance.
- Secrets and raw provider payloads are not durable task truth.

## Context Pressure

The Pi sidecar preserves large tool output behind refs and projects compact
context diagnostics into later model calls. It can report input tokens,
cache-read/write tokens, context pressure, and resume checkpoints without
turning hidden memory into task authority.
