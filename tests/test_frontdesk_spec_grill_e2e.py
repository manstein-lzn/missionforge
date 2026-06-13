from __future__ import annotations

import tempfile
import unittest

from missionforge.frontdesk import FrontDesk
from missionforge.ir import MissionIR
from missionforge.frontdesk.mission_mapper import MissionIRMapper
from missionforge.frontdesk.schema import ApprovalAuthority
from tests.frontdesk_llm_fixtures import seed_llm_authored_frontdesk_artifacts


class FrontDeskSpecGrillE2ETests(unittest.TestCase):
    def test_end_to_end_spec_grill_authors_freezes_and_runs_mission(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists and privacy remains protected.",
                session_id="fd-e2e",
            )

            seed_llm_authored_frontdesk_artifacts(
                frontdesk,
                session.session_ref,
                expected_artifacts=["docs/output.md"],
                constraints=["privacy remains protected"],
            )
            frontdesk.review_plan(session.session_ref, reviewed_by="user", authority=ApprovalAuthority.USER)
            MissionIRMapper().map(session=frontdesk.load_session(session.session_ref), workspace=frontdesk.workspace)
            audit = frontdesk.audit(session.session_ref)
            approval = frontdesk.approve(session.session_ref, approved_by="user")
            compile_result = frontdesk.freeze(session.session_ref)
            inspect = frontdesk.inspect(session.session_ref)

            mission = MissionIR.from_dict(frontdesk.workspace.read_json(compile_result.mission_ir_ref))
            self.assertEqual(audit.decision.value, "approve")
            self.assertTrue(approval.approved_hash.startswith("sha256:"))
            self.assertEqual(mission.outputs["required_artifacts"], ["docs/output.md"])
            self.assertTrue(inspect.freeze_ready)
            self.assertFalse(inspect.failed_gates)
            self.assertEqual(frontdesk.workspace.read_json("frontdesk/freeze_gate_result.json")["decision"], "freeze")


if __name__ == "__main__":
    unittest.main()
