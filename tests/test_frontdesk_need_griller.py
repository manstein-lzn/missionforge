from __future__ import annotations

import tempfile
import unittest

from missionforge import FrontDesk
from missionforge.frontdesk.need_griller import NeedGriller
from missionforge.frontdesk.scout import WorkspaceScout


class FrontDeskNeedGrillerTests(unittest.TestCase):
    def test_vague_rust_input_gets_one_targeted_question(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("I think this should be implemented in Rust.", session_id="fd-grill")
            WorkspaceScout().scout(session=session, workspace=frontdesk.workspace)

            result = NeedGriller().grill(session=session, workspace=frontdesk.workspace)

            self.assertEqual(result.report.readiness.value, "needs_clarification")
            self.assertIsNotNone(result.report.next_question)
            assert result.report.next_question is not None
            self.assertIn("implementation hypothesis", result.report.next_question.inference)
            self.assertIn("performance", result.report.next_question.question)
            self.assertIn("recommended_answer", result.report.next_question.to_dict())
            self.assertEqual(result.report.next_question.related_decision_ids, ["D-core-need"])
            self.assertTrue(frontdesk.workspace.exists("frontdesk/decision_tree.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/need_grilling_report.json"))
            self.assertFalse(frontdesk.workspace.exists("frontdesk/core_need_brief.json"))

    def test_workspace_profile_facts_suppress_profile_inventory_question(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("Which profile should I use?", session_id="fd-profile-question")
            WorkspaceScout().scout(session=session, workspace=frontdesk.workspace)

            result = NeedGriller().grill(session=session, workspace=frontdesk.workspace)

            assert result.report.next_question is not None
            self.assertNotIn("which profiles exist", result.report.next_question.question.lower())
            self.assertIn("observable output", result.report.next_question.question.lower())

    def test_specific_output_gets_core_need_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build a README for a local package. The expected output is package/README.md and success means the file exists.",
                session_id="fd-ready",
            )
            WorkspaceScout().scout(session=session, workspace=frontdesk.workspace)

            result = NeedGriller().grill(session=session, workspace=frontdesk.workspace)

            self.assertEqual(result.report.readiness.value, "core_need_ready")
            self.assertIsNotNone(result.core_need_brief)
            assert result.core_need_brief is not None
            self.assertEqual(result.core_need_brief.success_signals, ["package/README.md exists."])
            self.assertTrue(frontdesk.workspace.exists("frontdesk/core_need_brief.json"))


if __name__ == "__main__":
    unittest.main()
