# Module: PiWorker

## Goal

Provide the only first-class worker path for MissionForge's first design cycle.

## Scope

- PiWorker work-unit input
- PiWorker event stream
- tool-mediated workspace reads/writes
- provider usage metrics
- cache metrics
- refs-only output evidence

## Non-Goals

- no CodexWorker support
- no multi-worker abstraction
- no provider-specific policy in core runtime

## Current Status

Design-only in MissionForge. The reference behavior is the current
SkillFoundry PiWorker integration and the PI GitHub project runtime model.

## Attribution

The PI GitHub project is MIT-licensed. MissionForge is inspired by PI. The
initial MissionForge skeleton does not copy PI source code. Any future copied or
adapted PI source must retain required attribution.

## Public Contracts

To be designed:

- `PiWorkerInput`
- `PiWorkerOutput`
- `PiWorkerEvent`
- `PiWorkerMetrics`

## Invariants

- PiWorker receives a bounded work-unit contract.
- PiWorker writes only through allowed tools or write scopes.
- PiWorker output is evidence, not acceptance.
- Metrics are preserved in MissionResult evidence.

## Dependencies

- Mission IR
- work-unit harness
- context/evidence

## Verification Strategy

- faux PiWorker fixture
- live PiWorker smoke after deterministic path is stable
- event stream completeness checks
- token/cache metrics checks

## Open Questions

- How should user steering interrupt a live PiWorker session?
- Which PI runtime concepts should remain internal to the adapter?
- How should provider profiles be declared without leaking credentials?
