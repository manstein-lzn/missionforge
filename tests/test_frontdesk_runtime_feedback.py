from __future__ import annotations

import json
import unittest

from missionforge import (
    AuthorityRequirement,
    ContractValidationError,
    MissionResult,
    RuntimeFeedbackAction,
    RuntimeFeedbackRecommendation,
    RuntimeFeedbackSourceKind,
    VerificationResult,
    VerificationStatus,
    ValidatorResult,
)
from missionforge.frontdesk.runtime_feedback import (
    contract_mismatch_feedback,
    human_review_feedback,
    recommend_from_mission_result,
    recommend_from_verification_result,
    unsupported_validator_feedback,
)
from missionforge.revision import MissionRevisionRequest, MissionRevisionWorkflow


class FrontDeskRuntimeFeedbackTests(unittest.TestCase):
    def test_verifier_failure_routes_to_repair_guidance(self) -> None:
        result = VerificationResult(
            status=VerificationStatus.FAILED,
            validator_results=[
                ValidatorResult(
                    validator_id="artifact-exists",
                    passed=False,
                    evidence_refs=["evidence/artifact-exists.json"],
                    message="Missing artifact.",
                )
            ],
            evidence_refs=["evidence/artifact-exists.json"],
            failed_constraint_ids=["C-output"],
        )

        recommendation = recommend_from_verification_result(
            "fd-runtime",
            result,
            source_ref="runs/run-fd/verification.json",
        )

        self.assertEqual(recommendation.recommended_action, RuntimeFeedbackAction.REPAIR)
        self.assertEqual(recommendation.source_kind, RuntimeFeedbackSourceKind.VERIFIER_FAILURE)
        self.assertEqual(recommendation.authority_required, AuthorityRequirement.HARNESS)
        self.assertFalse(recommendation.can_auto_approve_revision)
        self.assertEqual(RuntimeFeedbackRecommendation.from_dict(recommendation.to_dict()), recommendation)

    def test_mission_result_failed_constraints_routes_to_repair(self) -> None:
        result = MissionResult(
            mission_id="sample-mission",
            status="failed",
            evidence_refs=["runs/run-sample/verification.json"],
            failed_constraint_ids=["C-output"],
        )

        recommendation = recommend_from_mission_result(
            "fd-runtime",
            result,
            source_ref="runs/run-sample/result.json",
        )

        self.assertEqual(recommendation.recommended_action, RuntimeFeedbackAction.REPAIR)
        self.assertEqual(recommendation.authority_required, AuthorityRequirement.HARNESS)
        self.assertIn("runs/run-sample/verification.json", recommendation.evidence_refs)

    def test_contract_mismatch_routes_to_revision_without_auto_approval(self) -> None:
        recommendation = contract_mismatch_feedback(
            "fd-runtime",
            source_ref="runs/run-sample/audit.json",
            evidence_refs=["runs/run-sample/contract-diff.json"],
            proposal_refs=["runs/run-sample/proposals/revision-plan.json"],
        )

        self.assertEqual(recommendation.recommended_action, RuntimeFeedbackAction.MISSION_REVISION)
        self.assertEqual(recommendation.authority_required, AuthorityRequirement.REVIEWER)
        self.assertFalse(recommendation.can_auto_approve_revision)

        request = recommendation.draft_revision_request(
            mission_run_id="run-sample",
            base_contract_ref="mission/frozen_contract.json",
            base_contract_hash="sha256:current",
            request_ref="runs/run-sample/revisions/frontdesk-revision-000001/request.json",
        )
        self.assertIsInstance(request, MissionRevisionRequest)
        self.assertEqual(request.authority_required, AuthorityRequirement.REVIEWER)
        decision = MissionRevisionWorkflow().decide(request)
        self.assertEqual(decision.decision, "needs_review")

    def test_unsupported_validator_routes_to_validator_extension(self) -> None:
        result = VerificationResult(
            status=VerificationStatus.UNSUPPORTED_VERIFICATION_SPEC,
            validator_results=[ValidatorResult(validator_id="skill_bundle", passed=False)],
            evidence_refs=["runs/run-sample/unsupported-validator.json"],
        )

        recommendation = recommend_from_verification_result(
            "fd-runtime",
            result,
            source_ref="runs/run-sample/verification.json",
        )

        self.assertEqual(recommendation.source_kind, RuntimeFeedbackSourceKind.UNSUPPORTED_VALIDATOR)
        self.assertEqual(recommendation.recommended_action, RuntimeFeedbackAction.VALIDATOR_EXTENSION)
        self.assertEqual(recommendation.authority_required, AuthorityRequirement.REDESIGN)

        direct = unsupported_validator_feedback("fd-runtime", validator_id="skill_bundle")
        self.assertEqual(direct.recommended_action, RuntimeFeedbackAction.VALIDATOR_EXTENSION)

    def test_user_reserved_authority_remains_human_reserved(self) -> None:
        recommendation = human_review_feedback(
            "fd-runtime",
            reason="User approval is required for this revision.",
            source_refs=["runs/run-sample/revision-diagnosis.json"],
        )

        self.assertEqual(recommendation.recommended_action, RuntimeFeedbackAction.HUMAN_REVIEW)
        self.assertEqual(recommendation.authority_required, AuthorityRequirement.HUMAN)

        result = VerificationResult(
            status=VerificationStatus.HUMAN_ACCEPTANCE_REQUIRED,
            evidence_refs=["runs/run-sample/human-gate.json"],
        )
        from_verifier = recommend_from_verification_result("fd-runtime", result)
        self.assertEqual(from_verifier.authority_required, AuthorityRequirement.HUMAN)

    def test_feedback_rejects_auto_approval_and_raw_payload_fields(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "auto-approve"):
            RuntimeFeedbackRecommendation(
                session_id="fd-runtime",
                source_kind=RuntimeFeedbackSourceKind.CONTRACT_MISMATCH,
                recommended_action=RuntimeFeedbackAction.MISSION_REVISION,
                reason="Revision needed.",
                authority_required=AuthorityRequirement.REVIEWER,
                evidence_refs=["runs/run-sample/diff.json"],
                can_auto_approve_revision=True,
            ).validate()

        payload = contract_mismatch_feedback(
            "fd-runtime",
            source_ref="runs/run-sample/audit.json",
            evidence_refs=["runs/run-sample/diff.json"],
        ).to_dict()
        payload["raw_prompt"] = "hidden provider output"
        with self.assertRaisesRegex(ContractValidationError, "not allowed"):
            RuntimeFeedbackRecommendation.from_dict(payload)

    def test_feedback_payload_is_refs_first(self) -> None:
        recommendation = contract_mismatch_feedback(
            "fd-runtime",
            source_ref="runs/run-sample/audit.json",
            evidence_refs=["runs/run-sample/diff.json"],
        )
        payload = json.dumps(recommendation.to_dict(), sort_keys=True)

        self.assertIn("runs/run-sample/audit.json", payload)
        self.assertNotIn("transcript", payload)
        self.assertNotIn("provider", payload)


if __name__ == "__main__":
    unittest.main()
