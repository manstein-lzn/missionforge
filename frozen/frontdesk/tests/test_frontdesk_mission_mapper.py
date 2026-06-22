from __future__ import annotations

import tempfile
import unittest

from missionforge.frontdesk import FrontDesk
from missionforge.ir import MissionIR
from missionforge.frontdesk.mission_mapper import MissionIRMapper
from missionforge.frontdesk.schema import ApprovalAuthority
from tests.frontdesk_llm_fixtures import seed_llm_authored_frontdesk_artifacts


class FrontDeskMissionMapperTests(unittest.TestCase):
    def test_mapper_writes_draft_mission_and_mapping_report(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists and privacy remains protected.",
                session_id="fd-map",
            )
            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["docs/output.md"],
                constraints=["privacy remains protected"],
            )
            frontdesk.review_plan(session.session_ref, reviewed_by="user", authority=ApprovalAuthority.USER)

            result = MissionIRMapper().map(session=frontdesk.load_session(session.session_ref), workspace=frontdesk.workspace)

            self.assertEqual(result.mission_plan.expected_artifacts, ["docs/output.md"])
            self.assertFalse(result.mapping_report.has_blocking_gaps)
            mission = MissionIR.from_dict(frontdesk.workspace.read_json("frontdesk/draft_mission.json"))
            self.assertEqual(mission.outputs["required_artifacts"], ["docs/output.md"])
            mapped_text = " ".join(mapping.requirement_text for mapping in result.mapping_report.requirement_mappings)
            self.assertIn("privacy", mapped_text)


if __name__ == "__main__":
    unittest.main()
