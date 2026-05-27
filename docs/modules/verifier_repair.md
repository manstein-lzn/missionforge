# Module: Verification and Repair

## Goal

Verify mission evidence and convert failures into structured repair contracts.

## Scope

- validator result schema
- failed constraint record
- missing evidence record
- validator mode and severity semantics
- repair contract
- redesign contract
- review and authority gates

## Non-Goals

- no task-name verifier branches
- no log-string repair routing

## Current Status

Design-only.

## Public Contracts

To be designed:

- `ValidatorResult`
- `FailedConstraint`
- `VerificationResult`
- `RepairContract`
- `RedesignRequest`
- `ReviewGate`

## Invariants

- Every failure should cite a Mission IR constraint ID when possible.
- Repair contracts are generated from structured failures.
- Manual authority gates are explicit and cannot be auto-approved.
- Worker self-report is never acceptance.
- Blocking unsupported verification requires redesign or explicit authority
  escalation.
- Advisory failures are surfaced as warnings, not hard proof.

## Dependencies

- Mission IR
- context/evidence
- harness reports

## Verification Strategy

- failing constraint creates failed constraint record
- failed constraint creates repair contract
- repair loop does not inspect free-form failure text
- executable/manual/unsupported validator modes route to distinct statuses
- blocking/advisory severities affect completion status correctly

## Open Questions

- How are generated tests represented as validators?
- How are unverifiable requirements escalated?
- Which generic validators ship in the first ProfileSpec registry?
