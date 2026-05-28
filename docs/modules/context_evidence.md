# Module: Context and Evidence

## Goal

Carry the ContextForge lessons into MissionForge as a durable context and
evidence plane.

## Scope

- frozen mission contract
- evidence refs
- evidence reliability levels
- contract manifest
- provenance
- raw input exclusion policy
- verification gate
- checkpoint refs
- proposal and decision ledger refs

## Non-Goals

- no worker execution
- no product-specific verifier logic

## Current Status

Phase 1 contract primitives exist. Phase 3 added the first deterministic
append-only evidence ledger.

Implemented in Phase 1:

- `EvidenceRef`
- `ArtifactRef`
- `EvidenceTrustLevel`
- trust comparison helpers

Implemented in Phase 3:

- `EvidenceRecord`
- `EvidenceSnapshot`
- `EvidenceLedger`
- `InMemoryEvidenceStore`
- `FileEvidenceStore`
- deterministic payload hashes and snapshot ledger hashes

## Public Contracts

- `EvidenceRef`
- `EvidenceTrustLevel`
- `ArtifactRef`
- `ContractManifest`
- `EvidenceLedger`

To be designed:

- `CheckpointRef`
- `ContextCheckpoint`
- `DecisionLedgerRef`

## Invariants

- Every worker-visible input is a frozen ref.
- Every verifier decision cites evidence refs.
- Evidence records are append-only and JSON-compatible.
- Evidence payload hashes and snapshot ledger hashes must be stable across dict
  key order.
- Raw conversation and raw private material are provenance-only unless the
  Mission IR explicitly allows a sanitized derivative.
- Worker claims and LLM interpretations are recorded with low trust levels and
  never become acceptance evidence by themselves.
- Every state correction cites evidence refs and evidence reliability.
- Context checkpoints are compact recovery summaries, not transcripts or memory
  stores.

## Dependencies

- Mission IR

## Verification Strategy

- hash/freshness tests
- raw input exclusion tests
- ledger replay tests
- evidence reliability routing tests
- state correction provenance tests
- context checkpoint size/content tests

## Verification Evidence

Phase 1:

```bash
PYTHONPATH=src python3 -m unittest tests/test_evidence_contracts.py
# Ran 4 tests: OK
```

Phase 3:

```bash
PYTHONPATH=src python3 -m unittest tests/test_evidence_ledger.py
# Ran 4 tests: OK
```

## Open Questions

- Should a later phase add SQLite behind the same ledger protocol?
- How much ContextForge code should be adapted versus redesigned?
- Should proposal artifacts be stored as ledger events, artifacts, or both?
