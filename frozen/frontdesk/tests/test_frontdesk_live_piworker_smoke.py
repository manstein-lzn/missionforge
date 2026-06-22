from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.pi_agent_provider_config import load_codex_current_provider
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig
from missionforge.frontdesk import FrontDesk
from missionforge.frontdesk.spec_grill_schema import NeedGrillingReadiness
from missionforge.frontdesk.state import CORE_NEED_BRIEF_REF, DECISION_TREE_REF, NEED_GRILLING_REPORT_REF


class FrontDeskLivePiWorkerSmokeTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("MISSIONFORGE_FRONTDESK_LIVE_SMOKE") == "1",
        "set MISSIONFORGE_FRONTDESK_LIVE_SMOKE=1 to run the live FrontDesk PiWorker smoke",
    )
    def test_live_codex_current_grill_writes_structured_need_artifacts_without_secret_leak(self) -> None:
        config = PiAgentRuntimeConfig(
            timeout_seconds=int(os.environ.get("MISSIONFORGE_PI_AGENT_LIVE_TIMEOUT_SECONDS", "180")),
            provider_mode="live",
            provider_config_source="codex_current",
            metadata={"phase": "frontdesk_live_smoke"},
        )

        with tempfile.TemporaryDirectory() as tempdir:
            provider = load_codex_current_provider()
            frontdesk = FrontDesk.with_default_piworker(workspace=tempdir, piworker_config=config)
            session = frontdesk.start(
                "Build docs/live_frontdesk_smoke.md. Success means the file exists and contains "
                "MissionForge FrontDesk live smoke passed.",
                session_id="fd-live-smoke",
            )
            frontdesk.scout(session.session_ref)

            report = frontdesk.grill(session.session_ref)

            root = Path(tempdir)
            serialized_workspace = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in root.rglob("*")
                if path.is_file()
            )
            decision_tree = json.loads((root / DECISION_TREE_REF).read_text(encoding="utf-8"))
            need_report = json.loads((root / NEED_GRILLING_REPORT_REF).read_text(encoding="utf-8"))
            core_need = json.loads((root / CORE_NEED_BRIEF_REF).read_text(encoding="utf-8"))

        self.assertEqual(report.report.session_id, "fd-live-smoke")
        self.assertEqual(report.report.readiness, NeedGrillingReadiness.CORE_NEED_READY)
        self.assertEqual(decision_tree["schema_version"], "missionforge.frontdesk_decision_tree.v1")
        self.assertEqual(need_report["schema_version"], "missionforge.frontdesk_need_grilling_report.v1")
        self.assertEqual(core_need["schema_version"], "missionforge.frontdesk_core_need_brief.v1")
        self.assertIn("docs/live_frontdesk_smoke.md", json.dumps(core_need, sort_keys=True))
        self.assertFalse(provider["api_key"] in serialized_workspace, "live API key leaked into workspace artifacts")
        self.assertNotIn("OPENAI_API_KEY", serialized_workspace)
        self.assertNotIn("MISSIONFORGE_PI_AGENT_API_KEY", serialized_workspace)


if __name__ == "__main__":
    unittest.main()
