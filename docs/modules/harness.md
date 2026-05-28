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
- proposal boundary validation
- control safe-point checks before worker dispatch

## Non-Goals

- no mission semantic interpretation
- no provider-specific reasoning policy
- no acceptance decisions
- no LLM proposal generation

## Current Status

Phase 1 contract primitives exist. Phase 4 added deterministic proposal
boundary validation, work-unit compilation, fake worker dispatch, decision
ledger entries, and halt safe-point checks.

Implemented in Phase 1:

- `WorkUnitContract`
- `AttemptInputManifest`
- `ExecutionReport`
- `WorkerResult`
- JSON-compatible round-trip helpers for implemented contracts

Implemented in Phase 4:

- `WorkerInvocation`
- `ProposalProvider`
- `DeterministicProposalProvider`
- `ProposalValidator`
- `WorkUnitCompiler`
- `WorkUnitHarness`
- deterministic `FakeWorker`
- `ControlRequest` safe-point handling before worker dispatch

## Public Contracts

- `WorkUnitContract`
- `AttemptInputManifest`
- `ExecutionReport`
- `WorkerResult`
- `WorkerInvocation`
- `ProposalBoundaryValidation`

## Invariants

- Every attempt has an input manifest and execution report.
- Work-unit outputs are refs-only.
- The harness records what happened; it does not decide acceptance.
- Proposed work units must fail closed when refs, scopes, expected outputs, or
  authority are invalid.
- Proposal validation requires explicit boundary context; missing context is
  rejected instead of treated as broad authority.
- Harness validation accepts a committed work-unit contract, not a raw LLM
  proposal.
- Fake worker output is evidence and execution reporting only; it is not
  mission acceptance.
- Halt controls are checked before worker dispatch.

## Dependencies

- Mission IR
- context/evidence module

## Verification Strategy

- deterministic worker writes one artifact
- unsafe paths fail closed
- execution reports remain valid when worker fails
- unsafe proposed scope is rejected before worker dispatch
- control requests are checked at safe points

## Verification Evidence

Phase 1:

```bash
PYTHONPATH=src python3 -m unittest tests/test_work_unit_contracts.py
# Ran 4 tests: OK
```

Phase 4:

```bash
PYTHONPATH=src python3 -m unittest tests/test_harness.py tests/test_fake_worker.py tests/test_control_requests.py
# Ran 7 tests: OK
```

## Open Questions

- What is the minimal work-unit contract PiWorker needs?
- How should tool events map into execution reports?
- Which proposal validation rules belong in harness versus runtime?
