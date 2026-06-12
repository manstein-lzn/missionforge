from __future__ import annotations

import os
import unittest

from missionforge.ir import MissionIR
from missionforge.runner import MissionRuntime
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig
from tests.test_ir import sample_mission_payload


class PiAgentRuntimeLiveSoakTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("MISSIONFORGE_PI_AGENT_LIVE_SOAK") == "1",
        "set MISSIONFORGE_PI_AGENT_LIVE_SOAK=1 to run the live PI Agent soak",
    )
    def test_live_soak_runs_through_mission_runtime_with_ledgers(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        config = PiAgentRuntimeConfig(
            timeout_seconds=int(os.environ.get("MISSIONFORGE_PI_AGENT_LIVE_TIMEOUT_SECONDS", "240")),
            provider_mode="live",
            provider_config_source="codex_current",
            metadata={"phase": "phase10_live_soak"},
        )

        with self.subTest("opt-in live provider"):
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                result = MissionRuntime(workspace=tmpdir, pi_agent_config=config).run(mission)
                summary = MissionRuntime(workspace=tmpdir, pi_agent_config=config).inspect("run-sample-mission")

        self.assertEqual(result.status, "completed_verified")
        self.assertGreaterEqual(summary["attempt_count"], 1)
        self.assertEqual(summary["mission_run"]["latest_safe_point"]["kind"], "after_completed_turn")


if __name__ == "__main__":
    unittest.main()
