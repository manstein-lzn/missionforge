from __future__ import annotations

import tempfile
import unittest

from missionforge import FrontDesk, MissionIR


class FrontDeskSpecGrillE2ETests(unittest.TestCase):
    def test_end_to_end_spec_grill_authors_freezes_and_runs_mission(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists and privacy remains protected.",
                session_id="fd-e2e",
            )

            draft_session = frontdesk.draft(session.session_ref)
            audit = frontdesk.audit(draft_session.session_ref)
            approval = frontdesk.approve(draft_session.session_ref, approved_by="user")
            compile_result = frontdesk.freeze(draft_session.session_ref)
            inspect = frontdesk.inspect(draft_session.session_ref)

            mission = MissionIR.from_dict(frontdesk.workspace.read_json(compile_result.mission_ir_ref))
            self.assertEqual(audit.decision.value, "approve")
            self.assertTrue(approval.approved_hash.startswith("sha256:"))
            self.assertEqual(mission.outputs["required_artifacts"], ["docs/output.md"])
            self.assertTrue(inspect.freeze_ready)
            self.assertFalse(inspect.failed_gates)
            self.assertEqual(frontdesk.workspace.read_json("frontdesk/freeze_gate_result.json")["decision"], "freeze")


if __name__ == "__main__":
    unittest.main()
