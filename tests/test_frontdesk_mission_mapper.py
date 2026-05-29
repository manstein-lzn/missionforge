from __future__ import annotations

import tempfile
import unittest

from missionforge import FrontDesk, MissionIR
from missionforge.frontdesk.schema import ApprovalAuthority


class FrontDeskMissionMapperTests(unittest.TestCase):
    def test_mapper_writes_draft_mission_and_mapping_report(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists and privacy remains protected.",
                session_id="fd-map",
            )
            frontdesk.scout(session.session_ref)
            frontdesk.grill(session.session_ref)
            frontdesk.cover_semantics(session.session_ref)
            frontdesk.plan_solution(session.session_ref)
            frontdesk.review_plan(session.session_ref, reviewed_by="user", authority=ApprovalAuthority.USER)

            result = frontdesk.map_mission(session.session_ref)

            self.assertEqual(result.mission_plan.expected_artifacts, ["docs/output.md"])
            self.assertFalse(result.mapping_report.has_blocking_gaps)
            mission = MissionIR.from_dict(frontdesk.workspace.read_json("frontdesk/draft_mission.json"))
            self.assertEqual(mission.outputs["required_artifacts"], ["docs/output.md"])
            mapped_text = " ".join(mapping.requirement_text for mapping in result.mapping_report.requirement_mappings)
            self.assertIn("privacy", mapped_text)


if __name__ == "__main__":
    unittest.main()
