# Profile Extension Kit

Last updated: 2026-05-29

Status: `reference`

## Goal

Give application teams a stable way to express reusable task features without
modifying MissionForge core.

The extension kit is intentionally data-first:

```text
ProfilePack
  -> CapabilityProfile[]
  -> VerificationProfile[]
  -> ProfileRegistry
  -> expand_mission / freeze_mission
```

It does not register runtime callbacks, workers, product branches, or hidden
completion rules.

## Profile Pack Shape

An external pack is a JSON-compatible object:

```json
{
  "pack_id": "integration.example",
  "capability_profiles": [
    {
      "profile_id": "artifact_manifest_required",
      "version": "1.0",
      "constraints": [
        {
          "constraint_id": "P-artifact_manifest_required-C-001",
          "kind": "evidence_boundary",
          "priority": "must",
          "statement": "Produce a manifest that lists declared artifacts by ref.",
          "source_refs": [],
          "evidence_obligations": ["evidence/artifact_manifest.json"],
          "repair_hints": ["Write the manifest under the declared evidence root."]
        }
      ],
      "evidence_requirements": ["evidence/artifact_manifest.json"],
      "required_artifacts": []
    }
  ],
  "verification_profiles": [
    {
      "profile_id": "portable_local_verification",
      "version": "1.0",
      "validator_types": ["file_exists", "artifact_hash"],
      "review_questions": ["Are external checks represented as evidence refs?"],
      "known_gaps": []
    }
  ]
}
```

The corresponding Python shape is `ProfilePack`.

## Usage

External integration code should build or load a pack, convert it to a registry,
and pass the registry into MissionForge expansion or freezing:

```python
from missionforge import ProfilePack
from missionforge.freeze import expand_mission, freeze_mission
from missionforge.ir import MissionIR

pack = ProfilePack.from_dict(profile_pack_payload)
registry = pack.to_registry(include_builtins=True)

mission = MissionIR.from_dict(mission_payload)
expanded = expand_mission(mission, registry=registry)
contract = freeze_mission(mission, registry=registry)
```

Using `include_builtins=False` is valid for isolated tests or product packs that
intentionally do not depend on built-in profiles.

## Capability Profiles

Capability profiles express reusable mission features:

- constraints;
- required artifacts;
- evidence requirements;
- repair hints.

Names should be capability-oriented:

- `artifact_manifest_required`
- `explicit_output_root`
- `source_manifest_required`
- `no_raw_log_or_secret_ingestion`

Names should not be product-oriented:

- `skillfoundry_pack`
- `customer_x_contract`
- `benchmark_y_policy`

Product concepts may compile into capability profiles externally, but the
profile names and generated constraints should remain reusable.

## Verification Profiles

Verification profiles declare the validator language a mission may use.

They do not implement validator behavior by themselves. They only declare which
validator types are allowed in the frozen contract.

Executable validators must still be implemented by `run_validator()` or by a
future explicit validator boundary. If a verification profile declares
`future_validator` but no implementation exists, execution fails closed with
`ContractValidationError`.

Manual and unsupported validators are valid contract states:

- `mode="manual"` with reviewer authority routes to `review_required`;
- `mode="manual"` with user authority routes to
  `human_acceptance_required`;
- `mode="unsupported"` with blocking severity routes to
  `unsupported_verification_spec`.

## What Belongs In An External Integration

External integrations may:

- compile product documents into `MissionIR`;
- provide `ProfilePack` data;
- choose profile refs and requirements;
- generate validator specs;
- collect external evidence and expose it as refs;
- emit `integration.*` metric namespaces.

External integrations must not:

- patch `src/missionforge/runtime.py`;
- add product branches under `src/missionforge/adapters`;
- use `missionforge.*` metric namespaces for product facts;
- rely on adapter-private metric dict keys for routing;
- bypass verifier-owned closure.

## Failure Rules

The extension kit fails closed when:

- a profile id is unknown;
- a verification profile id is unknown;
- a validator type is not declared by active verification profiles;
- a declared executable validator has no implementation;
- duplicate profile ids appear inside one registry;
- duplicate constraint or validator ids appear after expansion.

These failures are intentional. They protect core from silent product-specific
behavior.

## Testing Pattern

Every external profile pack should have tests proving:

- pack round-trip through `ProfilePack.from_dict(...).to_dict()`;
- mission expansion succeeds with the external registry;
- frozen contract hash changes when profile requirements change;
- unknown executable validators fail closed;
- manual and unsupported validators route to authority states;
- no imports from product integration code appear under `src/missionforge`.
