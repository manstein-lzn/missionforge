from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge import ContractValidationError
from missionforge.freeze import expand_mission
from missionforge.ir import MissionIR
from missionforge.profiles import CapabilityProfile, ProfilePack, VerificationProfile
from missionforge.validators import run_validator
from missionforge.verification import ValidatorMode, ValidatorSeverity, ValidatorSpec, VerificationSpec, VerificationStatus
from missionforge.verifier import verify_spec
from tests.test_ir import sample_mission_payload


class ProfileExtensionKitTests(unittest.TestCase):
    def test_external_profile_pack_expands_mission_without_core_product_branches(self) -> None:
        pack = _external_pack()
        registry = pack.to_registry(include_builtins=False)
        payload = sample_mission_payload()
        payload["capability_profiles"] = [
            {
                "profile_id": "artifact_manifest_required",
                "requirements": {"manifest_ref": "evidence/artifact_manifest.json"},
            }
        ]
        payload["verification"]["verification_profiles"] = [
            {"profile_id": "portable_local_verification"}
        ]
        payload["verification"]["validators"] = [
            {
                "validator_id": "V-manifest",
                "constraint_refs": ["P-artifact_manifest_required-C-001"],
                "type": "file_exists",
                "inputs": {"path": "evidence/artifact_manifest.json"},
            }
        ]

        expanded = expand_mission(MissionIR.from_dict(payload), registry=registry)

        self.assertEqual(registry.capability_profile_ids(), ["artifact_manifest_required"])
        self.assertEqual(registry.verification_profile_ids(), ["portable_local_verification"])
        self.assertIn("P-artifact_manifest_required-C-001", [item.constraint_id for item in expanded.constraints])
        self.assertEqual(expanded.validators[0].type, "file_exists")

    def test_profile_pack_round_trips_as_data(self) -> None:
        pack = _external_pack()

        self.assertEqual(ProfilePack.from_dict(pack.to_dict()), pack)

    def test_declared_but_unimplemented_executable_validator_fails_closed(self) -> None:
        spec = ValidatorSpec(
            validator_id="V-future",
            constraint_refs=["C-001"],
            type="future_validator",
        )

        with TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ContractValidationError, "unsupported executable validator type"):
                run_validator(spec, workspace=tmpdir)

    def test_manual_and_unsupported_validators_route_to_authority_states(self) -> None:
        review_result = verify_spec(
            VerificationSpec(
                validators=[
                    ValidatorSpec(
                        validator_id="V-review",
                        constraint_refs=["C-001"],
                        type="review_check",
                        mode=ValidatorMode.MANUAL,
                        inputs={"authority": "reviewer"},
                    )
                ]
            )
        )
        human_result = verify_spec(
            VerificationSpec(
                validators=[
                    ValidatorSpec(
                        validator_id="V-human",
                        constraint_refs=["C-001"],
                        type="human_check",
                        mode=ValidatorMode.MANUAL,
                        inputs={"requires_user_confirmation": True},
                    )
                ]
            )
        )
        unsupported_result = verify_spec(
            VerificationSpec(
                validators=[
                    ValidatorSpec(
                        validator_id="V-unsupported",
                        constraint_refs=["C-001"],
                        type="external_system_check",
                        mode=ValidatorMode.UNSUPPORTED,
                        severity=ValidatorSeverity.BLOCKING,
                    )
                ]
            )
        )

        self.assertEqual(review_result.status, VerificationStatus.REVIEW_REQUIRED)
        self.assertEqual(human_result.status, VerificationStatus.HUMAN_ACCEPTANCE_REQUIRED)
        self.assertEqual(unsupported_result.status, VerificationStatus.UNSUPPORTED_VERIFICATION_SPEC)


def _external_pack() -> ProfilePack:
    return ProfilePack(
        pack_id="integration.portable_fixture",
        capability_profiles=[
            CapabilityProfile(
                profile_id="artifact_manifest_required",
                version="1.0",
                constraints=[
                    {
                        "constraint_id": "P-artifact_manifest_required-C-001",
                        "kind": "evidence_boundary",
                        "priority": "must",
                        "statement": "Produce a manifest that lists declared artifacts by ref.",
                        "source_refs": [],
                        "evidence_obligations": ["evidence/artifact_manifest.json"],
                        "repair_hints": ["Write the manifest under the declared evidence root."],
                    }
                ],
                evidence_requirements=["evidence/artifact_manifest.json"],
            )
        ],
        verification_profiles=[
            VerificationProfile(
                profile_id="portable_local_verification",
                version="1.0",
                validator_types=["file_exists", "future_validator"],
                review_questions=["Are external checks represented as evidence refs?"],
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()
