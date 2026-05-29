from __future__ import annotations

import tempfile
import unittest

from missionforge import FrontDesk
from missionforge.frontdesk.schema import ApprovalAuthority


class FrontDeskSpecGrillServiceTests(unittest.TestCase):
    def test_explicit_service_steps_reach_auditable_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-service-steps",
            )

            scout = frontdesk.scout(session.session_ref)
            grill = frontdesk.grill(session.session_ref)
            coverage = frontdesk.cover_semantics(session.session_ref)
            solution = frontdesk.plan_solution(session.session_ref)
            review = frontdesk.review_plan(session.session_ref, reviewed_by="user", authority=ApprovalAuthority.USER)
            mapping = frontdesk.map_mission(session.session_ref)

            self.assertIn("generic_local_verification", scout.profile_catalog_snapshot.verification_profile_ids)
            self.assertEqual(grill.report.readiness.value, "core_need_ready")
            self.assertEqual(coverage.coverage_report.status.value, "passed")
            self.assertEqual(solution.solution_plan.status.value, "awaiting_review")
            self.assertEqual(review.decision.value, "approve")
            self.assertFalse(mapping.mapping_report.has_blocking_gaps)

    def test_draft_uses_full_spec_grill_not_shallow_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-service-draft",
            )

            frontdesk.draft(session.session_ref)

            for ref in (
                "frontdesk/workspace_facts.json",
                "frontdesk/need_grilling_report.json",
                "frontdesk/semantic_coverage.json",
                "frontdesk/solution_plan.json",
                "frontdesk/plan_review.json",
                "frontdesk/mission_mapping_report.json",
            ):
                self.assertTrue(frontdesk.workspace.exists(ref), ref)


if __name__ == "__main__":
    unittest.main()
