from __future__ import annotations

import tempfile
import unittest

from missionforge import ContractValidationError
from missionforge.profiles import CapabilityProfile, ProfileRegistry, VerificationProfile
from missionforge.frontdesk.compiler import compile_frontdesk_artifacts
from missionforge.frontdesk.schema import ProfileRecommendation, ProfileRecommendationKind, ProfileRecommendationSet
from tests.test_frontdesk_compiler import sample_frontdesk_artifacts


class FrontDeskProfileIntegrationTests(unittest.TestCase):
    def test_unknown_capability_profile_fails_closed(self) -> None:
        semantic_lock, brief, _profiles, plan, approval, sources = sample_frontdesk_artifacts()
        profiles = ProfileRecommendationSet(
            session_id=semantic_lock.session_id,
            recommendations=[
                ProfileRecommendation(
                    profile_id="unknown_capability",
                    kind=ProfileRecommendationKind.CAPABILITY,
                    rationale="bad",
                ),
                ProfileRecommendation(
                    profile_id="generic_local_verification",
                    kind=ProfileRecommendationKind.VERIFICATION,
                    rationale="ok",
                ),
            ],
        )
        with self.assertRaisesRegex(ContractValidationError, "unknown capability profile"):
            compile_frontdesk_artifacts(
                semantic_lock=semantic_lock,
                mission_brief=brief,
                profile_recommendations=profiles,
                mission_plan=plan,
                approval=approval,
                sanitized_sources=sources,
            )

    def test_unknown_verification_profile_fails_closed(self) -> None:
        semantic_lock, brief, _profiles, plan, approval, sources = sample_frontdesk_artifacts()
        profiles = ProfileRecommendationSet(
            session_id=semantic_lock.session_id,
            recommendations=[
                ProfileRecommendation(
                    profile_id="user_provided_evidence_only",
                    kind=ProfileRecommendationKind.CAPABILITY,
                    rationale="ok",
                ),
                ProfileRecommendation(
                    profile_id="unknown_verification",
                    kind=ProfileRecommendationKind.VERIFICATION,
                    rationale="bad",
                ),
            ],
        )
        with self.assertRaisesRegex(ContractValidationError, "unknown verification profile"):
            compile_frontdesk_artifacts(
                semantic_lock=semantic_lock,
                mission_brief=brief,
                profile_recommendations=profiles,
                mission_plan=plan,
                approval=approval,
                sanitized_sources=sources,
            )

    def test_validator_type_not_declared_fails_closed(self) -> None:
        semantic_lock, brief, profiles, plan, approval, sources = sample_frontdesk_artifacts()
        bad_plan = type(plan)(
            session_id=plan.session_id,
            expected_artifacts=plan.expected_artifacts,
            validators=[
                {
                    "validator_id": "V-future",
                    "constraint_refs": [f"FD-{semantic_lock.session_id}-C-authoring-contract"],
                    "type": "future_validator",
                }
            ],
        )
        with self.assertRaisesRegex(ContractValidationError, "not declared"):
            compile_frontdesk_artifacts(
                semantic_lock=semantic_lock,
                mission_brief=brief,
                profile_recommendations=profiles,
                mission_plan=bad_plan,
                approval=approval,
                sanitized_sources=sources,
            )

    def test_external_profile_pack_registry_can_be_supplied(self) -> None:
        semantic_lock, brief, _profiles, plan, approval, sources = sample_frontdesk_artifacts()
        profiles = ProfileRecommendationSet(
            session_id=semantic_lock.session_id,
            recommendations=[
                ProfileRecommendation(
                    profile_id="artifact_manifest_required",
                    kind=ProfileRecommendationKind.CAPABILITY,
                    rationale="Require artifact manifest.",
                ),
                ProfileRecommendation(
                    profile_id="custom_local_verification",
                    kind=ProfileRecommendationKind.VERIFICATION,
                    rationale="Custom file checks.",
                ),
            ],
        )
        registry = ProfileRegistry(
            capability_profiles=[
                CapabilityProfile(
                    profile_id="artifact_manifest_required",
                    version="1.0",
                    constraints=[],
                    evidence_requirements=["evidence/artifact_manifest.json"],
                )
            ],
            verification_profiles=[
                VerificationProfile(
                    profile_id="custom_local_verification",
                    version="1.0",
                    validator_types=["file_exists"],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tempdir:
            result = compile_frontdesk_artifacts(
                semantic_lock=semantic_lock,
                mission_brief=brief,
                profile_recommendations=profiles,
                mission_plan=plan,
                approval=approval,
                sanitized_sources=sources,
                workspace=tempdir,
                registry=registry,
            )

        self.assertIn("artifact_manifest_required", result.profile_ids)


if __name__ == "__main__":
    unittest.main()
