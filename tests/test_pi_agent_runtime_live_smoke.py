from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from missionforge.adapters.pi_agent_provider_config import load_codex_current_provider
from missionforge.evidence_store import InMemoryEvidenceStore
from missionforge.work_unit import WorkUnitContract


class PiAgentRuntimeLiveSmokeTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("MISSIONFORGE_PI_AGENT_LIVE_SMOKE") == "1",
        "set MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 to run the live PI Agent smoke",
    )
    def test_live_codex_current_smoke_writes_expected_artifact_without_secret_leak(self) -> None:
        config = PiAgentRuntimeConfig(
            timeout_seconds=int(os.environ.get("MISSIONFORGE_PI_AGENT_LIVE_TIMEOUT_SECONDS", "180")),
            provider_mode="live",
            provider_config_source="codex_current",
            metadata={"phase": "phase6_live_smoke"},
        )
        work_unit = WorkUnitContract(
            work_unit_id="WU-LIVE-000001",
            mission_id="mission-live-smoke",
            iteration=1,
            next_objective=(
                "Create exactly one small live smoke artifact at attempts/WU-LIVE-000001/live_smoke.txt "
                "containing the line MissionForge live provider smoke passed."
            ),
            allowed_scope=["attempts/WU-LIVE-000001"],
            visible_refs=[],
            expected_outputs=["attempts/WU-LIVE-000001/live_smoke.txt"],
            exit_criteria=["Expected artifact exists."],
            stop_conditions=["Stop after writing the expected artifact."],
        )

        with tempfile.TemporaryDirectory() as tempdir:
            provider = load_codex_current_provider()
            result = PiAgentRuntimeAdapter(config).run(
                work_unit,
                workspace=tempdir,
                evidence_store=InMemoryEvidenceStore(),
            )
            root = Path(tempdir)
            output_path = root / "attempts/WU-LIVE-000001/pi_agent_output.json"
            artifact_path = root / "attempts/WU-LIVE-000001/live_smoke.txt"
            output = json.loads(output_path.read_text(encoding="utf-8"))
            artifact_exists = artifact_path.exists()
            artifact_text = artifact_path.read_text(encoding="utf-8") if artifact_exists else ""
            serialized_workspace = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in root.rglob("*")
                if path.is_file()
            )

        self.assertEqual(result.worker_result.status, "completed")
        self.assertEqual(output["status"], "completed")
        self.assertTrue(artifact_exists)
        self.assertIn("MissionForge live provider smoke passed", artifact_text)
        self.assertFalse(provider["api_key"] in serialized_workspace, "live API key leaked into workspace artifacts")
        self.assertNotIn("OPENAI_API_KEY", serialized_workspace)


if __name__ == "__main__":
    unittest.main()
