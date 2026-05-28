from __future__ import annotations

import unittest

from missionforge.adapters.skillfoundry import (
    FrontDeskArtifactRef,
    SkillFoundryCompileResult,
    SkillFoundrySourceBundle,
    SkillPackageTarget,
)
from missionforge.contracts import ContractValidationError


def sample_source_bundle() -> SkillFoundrySourceBundle:
    return SkillFoundrySourceBundle.from_dict(
        {
            "bundle_id": "sf-source-001",
            "frontdesk_contract_ref": "frontdesk/task_contract.json",
            "source_manifest_ref": "frontdesk/source_manifest.json",
            "target_package_ref": "package/SKILL.md",
            "allowed_write_scopes": ["package", "attempts"],
            "capability_profile_refs": [
                {
                    "profile_id": "user_provided_evidence_only",
                    "requirements": {},
                },
                {
                    "profile_id": "explicit_output_root",
                    "requirements": {"output_root": "package"},
                },
            ],
            "verification_profile_refs": ["generic_local_verification"],
            "source_refs": [
                {
                    "artifact_id": "source-001",
                    "ref": "frontdesk/sanitized_task.json",
                    "artifact_type": "sanitized_source",
                }
            ],
        }
    )


class SkillFoundryAdapterContractTests(unittest.TestCase):
    def test_frontdesk_artifact_ref_round_trip(self) -> None:
        artifact = FrontDeskArtifactRef(
            artifact_id="source-001",
            ref="frontdesk/sanitized_transcript.json",
            artifact_type="sanitized_transcript",
            role="task_source",
        )

        self.assertEqual(FrontDeskArtifactRef.from_dict(artifact.to_dict()), artifact)

    def test_skill_package_target_round_trip(self) -> None:
        target = SkillPackageTarget(
            target_id="target-001",
            package_ref="package/SKILL.md",
            output_root="package",
            allowed_write_scopes=["package", "attempts"],
        )

        self.assertEqual(SkillPackageTarget.from_dict(target.to_dict()), target)

    def test_source_bundle_round_trip(self) -> None:
        bundle = sample_source_bundle()

        self.assertEqual(SkillFoundrySourceBundle.from_dict(bundle.to_dict()), bundle)

    def test_compile_result_round_trip(self) -> None:
        result = SkillFoundryCompileResult(
            bundle_id="sf-source-001",
            mission_ir_ref="missions/sf-source-001.mission.json",
            frozen_contract_ref="missions/sf-source-001.frozen_contract.json",
            contract_hash="sha256:abc123",
            profile_refs=["user_provided_evidence_only"],
            diagnostic_refs=["evidence/sf-source-001.skillfoundry_compile_diagnostics.json"],
            target_package_ref="package/SKILL.md",
        )

        self.assertEqual(SkillFoundryCompileResult.from_dict(result.to_dict()), result)

    def test_raw_transcript_inputs_are_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            FrontDeskArtifactRef(
                artifact_id="source-001",
                ref="frontdesk/raw_transcript.json",
                artifact_type="raw_transcript",
            ).validate()

        with self.assertRaises(ContractValidationError):
            SkillFoundrySourceBundle.from_dict(
                {
                    "bundle_id": "sf-source-001",
                    "frontdesk_contract_ref": "frontdesk/task_contract.json",
                    "source_manifest_ref": "frontdesk/source_manifest.json",
                    "target_package_ref": "package/SKILL.md",
                    "raw_transcript": "not allowed",
                }
            )

    def test_package_target_must_stay_inside_allowed_write_scope(self) -> None:
        with self.assertRaises(ContractValidationError):
            SkillPackageTarget(
                target_id="target-001",
                package_ref="outside/SKILL.md",
                output_root="package",
                allowed_write_scopes=["package"],
            ).validate()

    def test_source_bundle_requires_capability_profiles(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "capability_profile_refs"):
            SkillFoundrySourceBundle.from_dict(
                {
                    "bundle_id": "sf-source-001",
                    "frontdesk_contract_ref": "frontdesk/task_contract.json",
                    "source_manifest_ref": "frontdesk/source_manifest.json",
                    "target_package_ref": "package/SKILL.md",
                    "allowed_write_scopes": ["package"],
                }
            )


if __name__ == "__main__":
    unittest.main()
