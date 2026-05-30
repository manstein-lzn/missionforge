from __future__ import annotations

import tempfile
import unittest

from missionforge import FrontDesk
from missionforge.frontdesk.scout import WorkspaceScout
from missionforge.frontdesk.semantic_coverage import SemanticCoverageChecker
from missionforge.frontdesk.spec_grill_schema import CoreNeedBrief, DomainLanguage
from missionforge.frontdesk.state import CORE_NEED_BRIEF_REF, DOMAIN_LANGUAGE_REF


class FrontDeskSemanticCoverageTests(unittest.TestCase):
    def test_semantic_coverage_preserves_explicit_ai_authored_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            session = frontdesk.start(
                "Build docs/output.md for a local mission. Success means docs/output.md exists.",
                session_id="fd-coverage",
            )
            WorkspaceScout().scout(session=session, workspace=frontdesk.workspace)
            frontdesk.workspace.write_json(
                CORE_NEED_BRIEF_REF,
                CoreNeedBrief(
                    session_id=session.session_id,
                    core_pain="The mission intent must survive into the authored contract.",
                    target_users=["missionforge_user"],
                    usage_moment="Before runtime starts.",
                    deliverable_type="documentation_change",
                    desired_outcome="Build docs/output.md for a local mission.",
                    success_signals=["docs/output.md exists."],
                    constraints=["Use Rust only if needed for performance.", "Preserve privacy boundaries."],
                    non_goals=["Do not leak raw conversation into runtime truth."],
                    source_refs=["frontdesk/session.json"],
                ).to_dict(),
            )
            frontdesk.workspace.write_json(
                DOMAIN_LANGUAGE_REF,
                DomainLanguage(
                    session_id=session.session_id,
                    terms=["docs/output.md"],
                    implementation_terms=["Rust"],
                    risk_terms=["privacy"],
                    source_refs=["frontdesk/conversation.jsonl"],
                ).to_dict(),
            )

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
