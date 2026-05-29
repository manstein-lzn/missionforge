from __future__ import annotations

import tempfile
import unittest

from missionforge import FrontDesk


class FrontDeskMappingAuditorTests(unittest.TestCase):
    def test_audit_blocks_mapping_report_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md. Success means docs/output.md exists.",
                session_id="fd-audit-gap",
            )
            frontdesk.draft(session.session_ref)
            report = frontdesk.workspace.read_json("frontdesk/mission_mapping_report.json")
            report["requirement_mappings"][0]["status"] = "unmapped"
            report["requirement_mappings"][0]["mission_paths"] = []
            report["requirement_mappings"][0]["mapped_refs"] = []
            report["unmapped_requirements"] = [report["requirement_mappings"][0]["requirement_id"]]
            frontdesk.workspace.write_json("frontdesk/mission_mapping_report.json", report)

            audit = frontdesk.audit(session.session_ref)

            self.assertEqual(audit.decision.value, "needs_clarification")
            self.assertIn("MissionIR mapping report has blocking gaps.", audit.findings)


if __name__ == "__main__":
    unittest.main()
