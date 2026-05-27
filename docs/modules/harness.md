# Module: Work-Unit Harness

## Goal

Carry the ForgeUnit lessons into MissionForge as a worker attempt harness.

## Scope

- work-unit contract
- attempt input manifest
- worker invocation record
- execution report
- artifact write scope
- metrics and timing

## Non-Goals

- no mission semantic interpretation
- no provider-specific reasoning policy

## Current Status

Design-only.

## Public Contracts

To be designed:

- `WorkUnitContract`
- `AttemptInputManifest`
- `WorkerInvocation`
- `ExecutionReport`
- `WorkerResult`

## Invariants

- Every attempt has an input manifest and execution report.
- Work-unit outputs are refs-only.
- The harness records what happened; it does not decide acceptance.

## Dependencies

- Mission IR
- context/evidence module

## Verification Strategy

- deterministic worker writes one artifact
- unsafe paths fail closed
- execution reports remain valid when worker fails

## Open Questions

- What is the minimal work-unit contract PiWorker needs?
- How should tool events map into execution reports?
