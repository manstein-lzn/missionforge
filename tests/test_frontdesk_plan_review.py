from __future__ import annotations

import tempfile
import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk import FrontDesk
from missionforge.frontdesk.mission_mapper import MissionIRMapper
from missionforge.frontdesk.schema import ApprovalAuthority
from missionforge.frontdesk.spec_grill_schema import PlanReviewDecision
from tests.frontdesk_llm_fixtures import seed_llm_authored_frontdesk_artifacts


class FrontDeskPlanReviewTests(unittest.TestCase):
    def test_plan_review_hash_blocks_stale_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-review",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["docs/output.md"],
            )
            review = frontdesk.review_plan(
                session.session_ref,
                reviewed_by="user",
                authority=ApprovalAuthority.USER,
            )
            plan = frontdesk.workspace.read_json("frontdesk/solution_plan.json")
            plan["summary"] = "Changed after review."
            frontdesk.workspace.write_json("frontdesk/solution_plan.json", plan)

            self.assertEqual(review.decision, PlanReviewDecision.APPROVE)
            with self.assertRaisesRegex(ContractValidationError, "plan review hash"):
                MissionIRMapper().map(session=frontdesk.load_session(session.session_ref), workspace=frontdesk.workspace)

    def test_non_approved_plan_review_blocks_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-review-reject",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["docs/output.md"],
            )
            frontdesk.review_plan(
                session.session_ref,
                reviewed_by="user",
                decision=PlanReviewDecision.REQUEST_REVISION,
                authority=ApprovalAuthority.USER,
            )

            with self.assertRaisesRegex(ContractValidationError, "approved plan review"):
                MissionIRMapper().map(session=frontdesk.load_session(session.session_ref), workspace=frontdesk.workspace)


if __name__ == "__main__":
    unittest.main()
