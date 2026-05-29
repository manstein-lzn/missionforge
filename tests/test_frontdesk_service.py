from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from missionforge import FrontDesk, MissionIR


class FrontDeskServiceTests(unittest.TestCase):
    def test_start_answer_draft_audit_approve_freeze_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("Build a README for a local package.", session_id="fd-service")
            session = frontdesk.answer(session.session_ref, "The expected output is package/README.md.")
            session = frontdesk.draft(session.session_ref)
            audit = frontdesk.audit(session.session_ref)
            approval = frontdesk.approve(session.session_ref, approved_by="user")
            result = frontdesk.freeze(session.session_ref)
            inspect = frontdesk.inspect(session.session_ref)

            self.assertEqual(audit.decision.value, "approve")
            self.assertTrue(approval.approved_hash.startswith("sha256:"))
            self.assertTrue((Path(tempdir) / result.mission_ir_ref).exists())
            self.assertEqual(inspect.status, "frozen")
            mission = MissionIR.from_dict(frontdesk.workspace.read_json(result.mission_ir_ref))
            self.assertEqual(mission.outputs["required_artifacts"], ["package/README.md"])

    def test_inspect_is_refs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("Secret raw wording should stay in provenance only.", session_id="fd-inspect")
            inspect_text = str(frontdesk.inspect(session.session_ref).to_dict())

            self.assertIn("frontdesk/session.json", inspect_text)
            self.assertNotIn("Secret raw wording", inspect_text)

    def test_draft_writes_structured_artifacts_without_raw_text_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start("Build docs for the public API.", session_id="fd-draft")
            frontdesk.draft(session.session_ref)
            semantic_lock = frontdesk.workspace.read_json("frontdesk/semantic_lock.json")

            self.assertIn("requirement_clauses", semantic_lock)
            self.assertNotIn("conversation", semantic_lock)
            self.assertEqual(
                frontdesk.workspace.read_json("frontdesk/sanitized_sources.json")["excluded_source_refs"],
                ["frontdesk/conversation.jsonl"],
            )


if __name__ == "__main__":
    unittest.main()
