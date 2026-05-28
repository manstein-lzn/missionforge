# Module: Mission IR

## Goal

Define the domain-neutral mission contract model consumed by MissionForge.
Mission IR is a general closed-loop task contract, not a schema for any
specific task family.

## Scope

- mission identity
- objective
- environment, assumptions, uncertainties, and forbidden sources
- contract constraints, invariants, guarantees, non-goals, and risk policy
- capability profile references and authority/resource/tool policy
- verification profile references and validator language policy
- controlled steering policy, proposal source policy, and control request types
- evidence requirements and provenance policy
- verification declarations and validator semantics
- repair, redesign, review, stop, and escalation policy
- budget and observability metadata
- layered mission objects:
  - `MissionIR`
  - `CapabilityProfile`
  - `VerificationProfile`
  - `ExpandedMission`
  - `FrozenMissionContract`
  - `MissionRun`

## Non-Goals

- no worker execution
- no natural language compilation
- no product-specific task names
- no task-family branches in MissionForge core
- no worker self-report as completion evidence

## Current Status

Theory-level design is documented in `docs/MISSION_IR.md`. Initial dataclasses
and validation exist in `src/missionforge/ir.py`, and Phase 1 added shared
contract primitives in `src/missionforge/contracts.py`.

Phase 1 implemented:

- shared error hierarchy
- stable enum vocabulary
- safe ref validation
- stable JSON hashing
- JSON-compatible validation helpers
- `src/missionforge/mission.py` compatibility surface
- package-root export for `Ref`

Phase 2 implemented:

- `ExpandedMission`
- `FrozenMissionContract`
- `ContractManifest`
- deterministic profile expansion
- stable frozen contract hashing
- profile provenance in expanded fragments and manifests
- locked capability profile ref requirements in expanded mission payloads and
  frozen contract hashes

Layered Mission IR objects still intentionally lag behind the full design until
later phases introduce evidence storage, verification execution, harness
execution, and runtime orchestration.

## Public Contracts

- `MissionIR`
- `MissionObjective`
- `MissionConstraint`
- `CapabilityProfileRef`
- `CapabilityProfile`
- `VerificationProfile`
- `ExpandedMission`
- `FrozenMissionContract`
- `ContractManifest`

To be designed:

- `VerificationSpec`
- `AuthorityPolicy`
- `RevisionPolicy`
- `SteeringPolicy`
- `MissionRun`
- `AdaptiveDecision`

## Invariants

- Mission IR is the operational task truth.
- Raw chat is not task truth.
- Constraint IDs are stable and unique inside one mission.
- Capability profiles are reusable capability compilers, not product names.
- Verification profiles are reusable validator-language compilers, not product
  verifier branches.
- Runtime routing uses expanded constraints and validators, not profile names.
- A locked mission contract can be revised only through an explicit revision.
- Repair does not weaken acceptance; redesign is required when the contract is
  wrong or incomplete.
- Completion requires locked evidence and validators, not worker self-report.
- LLM proposals are not mission truth until accepted through controlled
  steering validation.

## Dependencies

None in the initial kernel.

## Verification Strategy

- JSON-like dict round trip
- schema version rejection
- duplicate constraint rejection
- safe ref validation
- stable JSON hash checks
- profile expansion provenance checks
- frozen contract hash checks
- validator mode/severity validation
- verification profile validator-language checks
- steering policy validation
- repair versus redesign decision tests

## Verification Evidence

Phase 1:

```bash
PYTHONPATH=src python3 -m unittest tests/test_contracts.py
# Ran 7 tests: OK

PYTHONPATH=src python3 -m unittest tests/test_ir.py
# Ran 4 tests: OK

PYTHONPATH=src python3 -m unittest tests/test_freeze.py tests/test_contract_manifest.py
# Ran 4 tests: OK
```

## Open Questions

- Should Mission IR be JSON Schema first, Python dataclass first, or both?
- What is the exact split between MissionIR and FrozenMissionContract fields?
- Should profile expansion be pure data only, or allow registered deterministic
  expansion functions?
- Which validator types belong in the first generic profile?
- What is the minimal MissionRun state needed for reliable resume?
- Which controlled steering rules belong in MissionIR versus runtime policy?
