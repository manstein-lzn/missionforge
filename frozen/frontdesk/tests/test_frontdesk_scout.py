from __future__ import annotations

import tempfile
import unittest

from missionforge.frontdesk import FrontDesk
from missionforge.frontdesk.scout import WorkspaceScout


class FrontDeskScoutTests(unittest.TestCase):
    def test_scout_writes_workspace_and_profile_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "I want a local Rust-friendly authoring flow with privacy boundaries.",
                session_id="fd-scout",
            )

            result = WorkspaceScout().scout(session=session, workspace=frontdesk.workspace)

            self.assertIn("generic_local_verification", result.profile_catalog_snapshot.verification_profile_ids)
            self.assertIn("Which verification profiles are available?", result.workspace_facts.questions_answered_by_workspace)
            self.assertEqual(result.domain_language.terms, [])
            self.assertEqual(result.domain_language.implementation_terms, [])
            self.assertEqual(result.domain_language.risk_terms, [])
            self.assertIn("frontdesk/conversation.jsonl", result.source_admission_report.excluded_source_refs)
            self.assertTrue(frontdesk.workspace.exists("frontdesk/workspace_facts.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/profile_catalog_snapshot.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/domain_language.json"))
            self.assertTrue(frontdesk.workspace.exists("frontdesk/source_admission_report.json"))


if __name__ == "__main__":
    unittest.main()
