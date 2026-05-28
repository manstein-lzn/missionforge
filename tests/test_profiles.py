from __future__ import annotations

import unittest

from missionforge import CapabilityProfile, MissionIR, ProfileRegistry, VerificationProfile
from missionforge.contracts import ContractValidationError
from missionforge.freeze import expand_mission
from tests.test_ir import sample_mission_payload


class ProfileExpansionTests(unittest.TestCase):
    def test_builtin_capability_profile_expands_with_provenance(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        expanded = expand_mission(mission)

        expansion = expanded.profile_expansions[0]
        self.assertEqual(expansion.source_profile_id, "user_provided_evidence_only")
        self.assertEqual(expansion.source_profile_version, "1.0")
        self.assertTrue(expansion.source_profile_hash.startswith("sha256:"))
        self.assertTrue(expansion.source_ref_hash.startswith("sha256:"))
        self.assertEqual(expansion.source_ref_requirements, {})
        self.assertIn("P-user_provided_evidence_only-C-001", [item.constraint_id for item in expanded.constraints])
        self.assertIn("evidence/source_manifest.json", expanded.evidence_requirements)

    def test_capability_profile_ref_requirements_are_locked_in_expansion(self) -> None:
        payload = sample_mission_payload()
        payload["capability_profiles"][0]["requirements"] = {
            "allowed_source_manifest": "sources/task_contract.json",
            "max_source_age_days": 7,
        }
        mission = MissionIR.from_dict(payload)
        expanded = expand_mission(mission)

        expansion_payload = expanded.profile_expansions[0].to_dict()
        self.assertEqual(
            expansion_payload["source_ref_requirements"],
            {
                "allowed_source_manifest": "sources/task_contract.json",
                "max_source_age_days": 7,
            },
        )
        self.assertTrue(expansion_payload["source_ref_hash"].startswith("sha256:"))

    def test_unknown_capability_profile_is_rejected(self) -> None:
        payload = sample_mission_payload()
        payload["capability_profiles"] = [{"profile_id": "unknown_profile", "requirements": {}}]
        mission = MissionIR.from_dict(payload)

        with self.assertRaises(ContractValidationError):
            expand_mission(mission)

    def test_unknown_verification_profile_is_rejected(self) -> None:
        payload = sample_mission_payload()
        payload["verification"]["verification_profiles"] = [{"profile_id": "unknown_verification"}]
        mission = MissionIR.from_dict(payload)

        with self.assertRaises(ContractValidationError):
            expand_mission(mission)

    def test_unknown_validator_type_is_rejected(self) -> None:
        payload = sample_mission_payload()
        payload["verification"]["validators"] = [
            {
                "validator_id": "V-001",
                "constraint_refs": ["C-001"],
                "type": "future_validator",
            }
        ]
        mission = MissionIR.from_dict(payload)

        with self.assertRaises(ContractValidationError):
            expand_mission(mission)

    def test_declared_validator_type_is_accepted(self) -> None:
        payload = sample_mission_payload()
        payload["verification"]["validators"] = [
            {
                "validator_id": "V-001",
                "constraint_refs": ["C-001"],
                "type": "file_exists",
            }
        ]
        mission = MissionIR.from_dict(payload)
        expanded = expand_mission(mission)

        self.assertEqual(expanded.validators[0].type, "file_exists")

    def test_custom_registry_can_declare_validator_language(self) -> None:
        registry = ProfileRegistry(
            capability_profiles=[
                CapabilityProfile(
                    profile_id="minimal_capability",
                    version="1.0",
                    constraints=[],
                )
            ],
            verification_profiles=[
                VerificationProfile(
                    profile_id="custom_verification",
                    version="1.0",
                    validator_types=["future_validator"],
                )
            ],
        )
        payload = sample_mission_payload()
        payload["capability_profiles"] = [{"profile_id": "minimal_capability", "requirements": {}}]
        payload["verification"]["verification_profiles"] = [{"profile_id": "custom_verification"}]
        payload["verification"]["validators"] = [
            {
                "validator_id": "V-001",
                "constraint_refs": ["C-001"],
                "type": "future_validator",
            }
        ]
        mission = MissionIR.from_dict(payload)
        expanded = expand_mission(mission, registry=registry)

        self.assertEqual(expanded.validators[0].type, "future_validator")


if __name__ == "__main__":
    unittest.main()
