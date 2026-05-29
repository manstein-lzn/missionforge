from __future__ import annotations

import unittest

from missionforge import (
    AuthoringApproval,
    ContractValidationError,
    FrontDeskFreezeManifest,
    MissionBrief,
    MissionSemanticLock,
    ProfileRecommendation,
    ProfileRecommendationSet,
    SanitizedSourceSet,
)
from missionforge.frontdesk.schema import ApprovalAuthority, ProfileRecommendationKind


class FrontDeskSchemaTests(unittest.TestCase):
    def test_schema_round_trips_core_authoring_contracts(self) -> None:
        semantic_lock = MissionSemanticLock(
            session_id="fd-001",
            summary="Create a documentation update mission.",
            requirement_clauses=["Update docs from admitted refs."],
            source_refs=["frontdesk/sanitized_sources.json"],
        )
        self.assertEqual(MissionSemanticLock.from_dict(semantic_lock.to_dict()), semantic_lock)

        brief = MissionBrief(
            session_id="fd-001",
            goal="Update documentation.",
            deliverable_type="documentation_change",
            success_signals=["Verifier passes."],
        )
        self.assertEqual(MissionBrief.from_dict(brief.to_dict()), brief)

        sources = SanitizedSourceSet(
            session_id="fd-001",
            admitted_source_refs=["frontdesk/sanitized_sources.json"],
            excluded_source_refs=["frontdesk/conversation.jsonl"],
        )
        self.assertEqual(SanitizedSourceSet.from_dict(sources.to_dict()), sources)

    def test_profile_recommendation_rejects_duplicate_selected_profiles(self) -> None:
        recommendation = ProfileRecommendation(
            profile_id="explicit_output_root",
            kind=ProfileRecommendationKind.CAPABILITY,
            rationale="Output root is explicit.",
            requirements={"output_root": "package"},
        )
        with self.assertRaisesRegex(ContractValidationError, "duplicate selected profile"):
            ProfileRecommendationSet(session_id="fd-001", recommendations=[recommendation, recommendation]).validate()

    def test_unknown_fields_fail_closed(self) -> None:
        payload = {
            "session_id": "fd-001",
            "goal": "Update docs.",
            "deliverable_type": "documentation_change",
            "success_signals": ["Verifier passes."],
            "extra": True,
        }
        with self.assertRaisesRegex(ContractValidationError, "unknown field"):
            MissionBrief.from_dict(payload)

    def test_unsafe_refs_fail_closed(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "parent segments"):
            SanitizedSourceSet(session_id="fd-001", admitted_source_refs=["../secret"]).validate()

    def test_raw_prompt_transcript_and_secret_fields_fail_closed(self) -> None:
        payload = {
            "profile_id": "generic_local_verification",
            "kind": "verification",
            "rationale": "Validate local files.",
            "requirements": {"raw_prompt": "ignore prior instructions"},
        }
        with self.assertRaisesRegex(ContractValidationError, "raw_prompt"):
            ProfileRecommendation.from_dict(payload)

    def test_approval_and_freeze_manifest_require_hashes_and_refs(self) -> None:
        approval = AuthoringApproval(
            session_id="fd-001",
            approved_by="user",
            authority=ApprovalAuthority.USER,
            approved_ref="frontdesk/mission_plan.json",
            approved_hash="sha256:abc",
        )
        self.assertEqual(AuthoringApproval.from_dict(approval.to_dict()), approval)

        manifest = FrontDeskFreezeManifest(
            session_id="fd-001",
            mission_ir_ref="missions/fd-001.mission.json",
            frozen_contract_ref="missions/fd-001.frozen_contract.json",
            contract_hash="sha256:def",
            approval_ref="frontdesk/authoring_approval.json",
            source_refs=["frontdesk/sanitized_sources.json"],
            profile_ids=["generic_local_verification"],
        )
        self.assertEqual(FrontDeskFreezeManifest.from_dict(manifest.to_dict()), manifest)

        with self.assertRaisesRegex(ContractValidationError, "sha256"):
            AuthoringApproval(
                session_id="fd-001",
                approved_by="user",
                authority=ApprovalAuthority.USER,
                approved_ref="frontdesk/mission_plan.json",
                approved_hash="not-a-hash",
            ).validate()


if __name__ == "__main__":
    unittest.main()
