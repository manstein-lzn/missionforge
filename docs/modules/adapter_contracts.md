# Module: Adapter Contracts

Status: supporting refs-only adapter data.

Adapter contracts define generic refs-only envelopes for optional host/provider
boundaries. They do not implement execution, judging, product behavior, or a
worker registry.

## Scope

- adapter boundary declarations;
- adapter invocation refs;
- adapter result refs;
- adapter diagnostic refs;
- raw payload and secret-shaped field rejection.

## Current Boundary

The active intelligent worker boundary is `PiWorkerCall`.

Adapter contracts may support host or provider shells, but they must not
reintroduce old runtime, harness, work-unit, or product-specific execution paths.

## Public Contracts

- `AdapterBoundary`
- `AdapterInvocation`
- `AdapterDiagnostic`
- `AdapterResult`

## Invariants

- Adapter contracts are refs-only.
- Adapter contracts are JSON-compatible.
- Raw body, raw payload, raw prompt, raw transcript, and secret-shaped fields are
  rejected.
- Adapter modules may import MissionForge contracts.
- MissionForge package root does not re-export concrete adapter internals.
- MissionForge adapters must not contain product-specific task semantics.
- Product integrations depend on MissionForge; MissionForge does not depend on
  product integrations.
- Adapter results are evidence or diagnostics, not acceptance.
