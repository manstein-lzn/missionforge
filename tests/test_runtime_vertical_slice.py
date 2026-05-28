from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import MissionIR, MissionRuntime
from tests.test_ir import sample_mission_payload


class RuntimeVerticalSliceTests(unittest.TestCase):
    def test_valid_deterministic_mission_reaches_completed_verified(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)

            self.assertEqual(result.status, "completed_verified")
            self.assertEqual(result.artifact_refs, ["package/SKILL.md"])
            self.assertTrue(result.evidence_refs)
            self.assertTrue(Path(tmpdir, "mission/frozen_contract.json").exists())
            self.assertTrue(Path(tmpdir, "package/SKILL.md").exists())
            self.assertEqual(result.metrics["attempt_count"], 1)

    def test_runtime_uses_pi_agent_runtime_artifacts(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)

            self.assertEqual(result.status, "completed_verified")
            self.assertEqual(result.artifact_refs, ["package/SKILL.md"])
            self.assertTrue(Path(tmpdir, "attempts/WU-000001/pi_agent_execution_report.json").exists())
            self.assertTrue(Path(tmpdir, "attempts/WU-000001/pi_agent_events.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
