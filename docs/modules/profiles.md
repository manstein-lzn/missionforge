# Module: Profiles

## Goal

Represent reusable capability and verification compilers as data-first profiles.

Capability profiles convert domain or capability concepts into MissionForge
primitives: constraints, artifacts, evidence requirements, risk checks, repair
hints, and worker guidance.

Verification profiles declare the validation language for a mission:
validator types, modes, severities, manual gates, unsupported checks, review
questions, known gaps, and authority rules.

## Scope

- profile declarations
- profile requirements
- profile expansion provenance
- capability profile expansion
- verification profile expansion
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
- no unknown validators outside a locked verification profile

## Current Status

Phase 2 implemented the first deterministic profile kernel.

Implemented:

- `CapabilityProfile`
- `VerificationProfile`
- `ProfilePack`
- `ProfileExpansion`
- `ProfileRegistry`
- built-in `user_provided_evidence_only`
- built-in `explicit_output_root`
- built-in `generic_local_verification`
- deterministic capability and verification profile expansion
- external profile pack composition through `ProfilePack.to_registry()`
- validator type checks against active verification profiles
- locked capability profile ref requirements in expansion payloads and frozen
  contract hashes

The first implementation is intentionally small. Larger profile libraries,
imperative profile expansion, and product adapters remain out of scope.

Phase 20 added the external extension kit documented in
`docs/PROFILE_EXTENSION_KIT.md`. External integrations can now ship data-first
profile packs and compose them with built-ins without adding product-specific
runtime branches.

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
- `generic_local_verification`
- `manual_review_gate`

## Invariants

- Complex missions are profile compositions.
- Profiles are reusable across unrelated missions.
- Profile names describe capabilities, not products or benchmarks.
- Profile expansion must be deterministic and provenance-preserving.
- Profile ref requirements are contract inputs; changing them must either change
  the frozen contract hash or fail closed.
- Runtime decisions must use expanded constraints and validators, not profile
  names.
- A profile may declare unsupported or manual validators, but it must not
  pretend they are executable.
- Validator types must be declared by locked verification profiles before they
  appear in VerificationSpec.
- Review questions and known gaps are surfaced in verification results.

## Dependencies

- Mission IR
- verifier/repair module

## Verification Strategy

- one capability-bundle mission and one unrelated mission share profiles
- profile validation expands into constraints and validators
- expanded fragments cite source profile id and version
- expanded fragments preserve the locked profile ref requirements and ref hash
- duplicate generated IDs are rejected
- unknown validator types are rejected unless declared as manual or unsupported
- verification profile expansion declares validator language and authority gates
- profile composition does not grant proposal or closure authority

## Verification Evidence

Phase 2:

```bash
PYTHONPATH=src python3 -m unittest tests/test_profiles.py
# Ran 7 tests: OK
```

Phase 20:

```bash
PYTHONPATH=src python3 -m unittest tests/test_profile_extension_kit.py
```

## Open Questions

- Should profiles be JSON, Python packages, or both?
- Can external product integrations generate new profile instances safely?
- How are profile hashes represented in FrozenMissionContract?
- Should capability and verification profiles share one registry or separate
  registries?
