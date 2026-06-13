from __future__ import annotations

import tempfile
import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk import FrontDesk
from missionforge.frontdesk.solution_architect import SolutionArchitect, solution_architect_node_template


class FrontDeskSolutionArchitectTests(unittest.TestCase):
    def test_solution_architect_fails_closed_without_llm_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build a README for a local package. The expected output is package/README.md.",
                session_id="fd-plan",
            )

            with self.assertRaisesRegex(
                ContractValidationError,
                "deterministic solution planning has been removed",
            ):
                SolutionArchitect().plan(session=session, workspace=frontdesk.workspace)

            self.assertFalse(frontdesk.workspace.exists("frontdesk/solution_plan.json"))
            self.assertFalse(frontdesk.workspace.exists("frontdesk/solution_plan.md"))
            self.assertFalse(frontdesk.workspace.exists("frontdesk/profile_recommendations.json"))

    def test_solution_architect_node_template_exposes_role_and_outputs(self) -> None:
        template = solution_architect_node_template("fd-plan")

        self.assertEqual(template["node"], "frontdesk.solution_architect")
        self.assertEqual(template["session_id"], "fd-plan")
        self.assertIn("frontdesk/core_need_brief.json", template["visible_refs"])
        self.assertIn("frontdesk/semantic_coverage.json", template["visible_refs"])
        self.assertIn("frontdesk/profile_catalog_snapshot.json", template["visible_refs"])
        self.assertEqual(
            template["expected_outputs"],
            [
                "frontdesk/solution_plan.json",
                "frontdesk/solution_plan.md",
                "frontdesk/plan_risk_register.json",
                "frontdesk/profile_recommendations.json",
                "frontdesk/mission_plan.json",
            ],
        )
        self.assertIn("Do not compile MissionIR.", template["rules"])


if __name__ == "__main__":
    unittest.main()
