# Module: Context and Evidence

## Goal

Carry the ContextForge lessons into MissionForge as a durable context and
evidence plane.

## Scope

- frozen mission contract
- evidence refs
- contract manifest
- provenance
- raw input exclusion policy
- verification gate
- checkpoint refs

## Non-Goals

- no worker execution
- no product-specific verifier logic

## Current Status

Design-only.

## Public Contracts

To be designed:

- `EvidenceRef`
- `ContractManifest`
- `EvidenceLedger`
- `VerificationGate`
- `CheckpointRef`

## Invariants

- Every worker-visible input is a frozen ref.
- Every verifier decision cites evidence refs.
- Raw conversation and raw private material are provenance-only unless the
  Mission IR explicitly allows a sanitized derivative.

## Dependencies

- Mission IR

## Verification Strategy

- hash/freshness tests
- raw input exclusion tests
- ledger replay tests

## Open Questions

- Should the ledger be SQLite, JSONL, or pluggable?
- How much ContextForge code should be adapted versus redesigned?
