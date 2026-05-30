from __future__ import annotations

import tempfile
import unittest

from missionforge import ContractValidationError, FrontDesk
from missionforge.frontdesk.need_griller import NeedGriller, need_griller_node_template


class FrontDeskNeedGrillerTests(unittest.TestCase):
    def test_need_griller_fails_closed_without_llm_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("I think this should be implemented in Rust.", session_id="fd-grill")

            with self.assertRaisesRegex(
                ContractValidationError,
                "deterministic need grilling has been removed",
            ):
                NeedGriller().grill(session=session, workspace=frontdesk.workspace)

            self.assertFalse(frontdesk.workspace.exists("frontdesk/decision_tree.json"))
            self.assertFalse(frontdesk.workspace.exists("frontdesk/need_grilling_report.json"))
            self.assertFalse(frontdesk.workspace.exists("frontdesk/core_need_brief.json"))

    def test_need_griller_node_template_exposes_role_and_refs(self) -> None:
        template = need_griller_node_template("fd-grill")

        self.assertEqual(template["node"], "frontdesk.need_griller")
        self.assertEqual(template["session_id"], "fd-grill")
        self.assertIn("frontdesk/conversation.jsonl", template["visible_refs"])
        self.assertIn("frontdesk/workspace_facts.json", template["visible_refs"])
        self.assertIn("frontdesk/source_admission_report.json", template["visible_refs"])
        self.assertEqual(template["expected_outputs"], ["frontdesk/decision_tree.json", "frontdesk/need_grilling_report.json"])
        self.assertEqual(template["optional_outputs"], ["frontdesk/core_need_brief.json"])
        self.assertIn("Do not copy raw conversation into runtime truth.", template["rules"])


if __name__ == "__main__":
    unittest.main()
