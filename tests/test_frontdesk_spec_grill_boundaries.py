from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge import FrontDesk


class FrontDeskSpecGrillBoundaryTests(unittest.TestCase):
    def test_runtime_facing_artifacts_do_not_embed_raw_user_text(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            frontdesk = FrontDesk(workspace=tempdir)
            secret_phrase = "PRIVATE-BRAINSTORM-DO-NOT-RUNTIME"
            session = frontdesk.start(
                f"Build artifact named {secret_phrase}. Success means artifacts/frontdesk_output.md exists.",
                session_id="fd-boundary",
            )

            frontdesk.draft(session.session_ref)
            runtime_refs = [
                "frontdesk/sanitized_sources.json",
                "frontdesk/semantic_lock.json",
                "frontdesk/mission_brief.json",
                "frontdesk/profile_recommendations.json",
                "frontdesk/mission_plan.json",
                "frontdesk/draft_mission.json",
            ]

            for ref in runtime_refs:
                payload = (Path(tempdir) / ref).read_text(encoding="utf-8")
                self.assertNotIn(secret_phrase, payload, ref)

    def test_frontdesk_core_has_no_product_route_branches(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "missionforge" / "frontdesk"
        joined = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

        self.assertNotIn("if skillfoundry", joined.lower())
        self.assertNotIn("if codexarium", joined.lower())
        self.assertNotIn("SkillFoundryMissionCompiler", joined)


if __name__ == "__main__":
    unittest.main()
