# Module: Profiles

## Goal

Represent reusable capability compilers as data-first ProfileSpecs.

Profiles convert domain or capability concepts into MissionForge primitives:
constraints, artifacts, validators, evidence requirements, risk checks, repair
hints, and worker guidance.

## Scope

- profile declarations
- profile requirements
- profile expansion provenance
- profile-provided validators
- profile-provided evidence requirements
- profile-provided risk and review checks
- profile repair hints
- profile versioning

## Non-Goals

- no product-name profiles
- no imperative task branches in core runtime
- no profile-name-specific routing in runtime
- no hidden task completion shortcuts

## Current Status

Design-only. `docs/MISSION_IR.md` now treats profiles as capability compilers
that expand MissionIR into an ExpandedMission before freeze.

## Candidate Profiles

- `capability_bundle`
- `explicit_output_root`
- `user_provided_evidence_only`
- `no_raw_log_or_secret_ingestion`
- `local_file_path_safety`
- `no_overwrite_conflict_policy`
- `rust_helper_runtime`
- `synthetic_fixture_pack`
- `reference_documentation_pack`
- `markdown_output_contract`

## Invariants

- Complex missions are profile compositions.
- Profiles are reusable across unrelated missions.
- Profile names describe capabilities, not products or benchmarks.
- Profile expansion must be deterministic and provenance-preserving.
- Runtime decisions must use expanded constraints and validators, not profile
  names.
- A profile may declare unsupported or manual validators, but it must not
  pretend they are executable.

## Dependencies

- Mission IR
- verifier/repair module

## Verification Strategy

- one capability-bundle mission and one unrelated mission share profiles
- profile validation expands into constraints and validators
- expanded fragments cite source profile id and version
- duplicate generated IDs are rejected
- unknown validator types are rejected unless declared as manual or unsupported

## Open Questions

- Should profiles be JSON, Python packages, or both?
- Can FrontDesk generate new profile instances safely?
- How are profile hashes represented in FrozenMissionContract?
