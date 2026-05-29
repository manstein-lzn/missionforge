from __future__ import annotations

import tempfile
import unittest

from missionforge import FrontDesk
from missionforge.frontdesk.need_griller import NeedGriller
from missionforge.frontdesk.scout import WorkspaceScout
from missionforge.frontdesk.semantic_coverage import SemanticCoverageChecker
from missionforge.frontdesk.solution_architect import SolutionArchitect


class FrontDeskSolutionArchitectTests(unittest.TestCase):
    def test_solution_architect_writes_plan_and_known_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build a README for a local package. The expected output is package/README.md and success means the file exists.",
                session_id="fd-plan",
            )
            WorkspaceScout().scout(session=session, workspace=frontdesk.workspace)
            NeedGriller().grill(session=session, workspace=frontdesk.workspace)
            SemanticCoverageChecker().cover(session=session, workspace=frontdesk.workspace)

            result = SolutionArchitect().plan(session=session, workspace=frontdesk.workspace)

            self.assertEqual(result.solution_plan.status.value, "awaiting_review")
            self.assertEqual(result.solution_plan.expected_artifacts, ["package/README.md"])
            self.assertIn("explicit_output_root", result.solution_plan.selected_capability_profile_ids)
            self.assertIn("generic_local_verification", result.solution_plan.selected_verification_profile_ids)
            self.assertTrue(frontdesk.workspace.exists("frontdesk/solution_plan.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/solution_plan.md"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/profile_recommendations.json"))


if __name__ == "__main__":
    unittest.main()
