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
- evidence requirements and provenance policy
- verification declarations and validator semantics
- repair, redesign, review, stop, and escalation policy
- budget and observability metadata
- layered mission objects:
  - `MissionIR`
  - `ProfileSpec`
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
and validation exist in `src/missionforge/ir.py`, but they intentionally lag
behind the full design until the schema is reviewed.

## Public Contracts

- `MissionIR`
- `MissionObjective`
- `MissionConstraint`
- `CapabilityProfileRef`

To be designed:

- `ProfileSpec`
- `ExpandedMission`
- `FrozenMissionContract`
- `VerificationSpec`
- `MissionRun`
- `AdaptiveDecision`

## Invariants

- Mission IR is the operational task truth.
- Raw chat is not task truth.
- Constraint IDs are stable and unique inside one mission.
- Profiles are reusable capability compilers, not product names.
- Runtime routing uses expanded constraints and validators, not profile names.
- A locked mission contract can be revised only through an explicit revision.
- Repair does not weaken acceptance; redesign is required when the contract is
  wrong or incomplete.
- Completion requires locked evidence and validators, not worker self-report.

## Dependencies

None in the initial kernel.

## Verification Strategy

- JSON-like dict round trip
- schema version rejection
- duplicate constraint rejection
- profile expansion provenance checks
- frozen contract hash checks
- validator mode/severity validation
- repair versus redesign decision tests

## Open Questions

- Should Mission IR be JSON Schema first, Python dataclass first, or both?
- What is the exact split between MissionIR and FrozenMissionContract fields?
- Should profile expansion be pure data only, or allow registered deterministic
  expansion functions?
- Which validator types belong in the first generic profile?
- What is the minimal MissionRun state needed for reliable resume?
