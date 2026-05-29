from __future__ import annotations

import tempfile
import unittest

from missionforge import FrontDesk


class FrontDeskSpecGrillAcceptanceTests(unittest.TestCase):
    def test_vague_implementation_input_routes_to_grilling_question(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("I think this should be implemented in Rust.", session_id="fd-accept-vague")

            session = frontdesk.draft(session.session_ref)
            report = frontdesk.workspace.read_json("frontdesk/need_grilling_report.json")

            self.assertEqual(session.status.value, "needs_clarification")
            self.assertEqual(session.next_action, "answer_question")
            self.assertEqual(report["readiness"], "needs_clarification")
            self.assertIn("implementation hypothesis", report["next_question"]["inference"])
            self.assertIn("recommended_answer", report["next_question"])
            self.assertFalse(frontdesk.workspace.exists("frontdesk/draft_mission.json"))

    def test_complete_input_reaches_frozen_contract_through_spec_grill(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists and privacy remains protected.",
                session_id="fd-accept-complete",
            )

            session = frontdesk.draft(session.session_ref)
            audit = frontdesk.audit(session.session_ref)
            frontdesk.approve(session.session_ref, approved_by="user")
            result = frontdesk.freeze(session.session_ref)

            self.assertEqual(session.status.value, "draft_ready")
            self.assertEqual(audit.decision.value, "approve")
            self.assertTrue(frontdesk.workspace.exists("frontdesk/semantic_coverage.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/solution_plan.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/plan_review.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/mission_mapping_report.json"))
            self.assertTrue(frontdesk.workspace.exists(result.frozen_contract_ref))


if __name__ == "__main__":
    unittest.main()
