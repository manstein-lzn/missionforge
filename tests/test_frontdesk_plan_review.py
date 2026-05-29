from __future__ import annotations

import tempfile
import unittest

from missionforge import ContractValidationError, FrontDesk
from missionforge.frontdesk.schema import ApprovalAuthority
from missionforge.frontdesk.spec_grill_schema import PlanReviewDecision


class FrontDeskPlanReviewTests(unittest.TestCase):
    def test_plan_review_hash_blocks_stale_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-review",
            )
            frontdesk.scout(session.session_ref)
            frontdesk.grill(session.session_ref)
            frontdesk.cover_semantics(session.session_ref)
            frontdesk.plan_solution(session.session_ref)
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
                frontdesk.map_mission(session.session_ref)

    def test_non_approved_plan_review_blocks_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-review-reject",
            )
            frontdesk.scout(session.session_ref)
            frontdesk.grill(session.session_ref)
            frontdesk.cover_semantics(session.session_ref)
            frontdesk.plan_solution(session.session_ref)
            frontdesk.review_plan(
                session.session_ref,
                reviewed_by="user",
                decision=PlanReviewDecision.REQUEST_REVISION,
                authority=ApprovalAuthority.USER,
            )

            with self.assertRaisesRegex(ContractValidationError, "approved plan review"):
                frontdesk.map_mission(session.session_ref)


if __name__ == "__main__":
    unittest.main()
