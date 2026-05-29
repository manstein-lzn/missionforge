from __future__ import annotations

import tempfile
import unittest

from missionforge import FrontDesk
from missionforge.frontdesk.need_griller import NeedGriller
from missionforge.frontdesk.scout import WorkspaceScout
from missionforge.frontdesk.semantic_coverage import SemanticCoverageChecker


class FrontDeskSemanticCoverageTests(unittest.TestCase):
    def test_semantic_coverage_preserves_rust_and_privacy_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md for a local mission. Success means docs/output.md exists. Use Rust only if needed for performance and preserve privacy.",
                session_id="fd-coverage",
            )
            WorkspaceScout().scout(session=session, workspace=frontdesk.workspace)
            NeedGriller().grill(session=session, workspace=frontdesk.workspace)

            result = SemanticCoverageChecker().cover(session=session, workspace=frontdesk.workspace)

            self.assertEqual(result.coverage_report.status.value, "passed")
            covered_signals = {item.source_signal for item in result.coverage_report.coverage_items}
            self.assertIn("Rust", covered_signals)
            self.assertIn("privacy", covered_signals)
            self.assertIn("Rust", " ".join(result.semantic_lock.requirement_clauses))
            self.assertIn("privacy", " ".join(result.semantic_lock.risks))
            self.assertEqual(result.sanitized_sources.excluded_source_refs, ["frontdesk/conversation.jsonl"])
            self.assertTrue(frontdesk.workspace.exists("frontdesk/semantic_coverage.json"))


if __name__ == "__main__":
    unittest.main()
