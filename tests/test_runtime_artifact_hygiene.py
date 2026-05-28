from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import MissionIR, MissionRuntime
from missionforge.state import scan_artifact_hygiene
from tests.test_ir import sample_mission_payload


class RuntimeArtifactHygieneTests(unittest.TestCase):
    def test_hygiene_report_is_written_and_refs_only(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            MissionRuntime(workspace=tmpdir).run(mission)
            root = Path(tmpdir)
            report = json.loads((root / "runs/run-sample-mission/artifact_hygiene.json").read_text(encoding="utf-8"))
            execution_report = (root / "attempts/WU-000001/pi_agent_execution_report.json").read_text(encoding="utf-8")
            artifact_text = (root / "package/SKILL.md").read_text(encoding="utf-8")

        self.assertEqual(report["schema_version"], "missionforge.artifact_hygiene.v1")
        self.assertTrue(report["passed"])
        self.assertNotIn(artifact_text, execution_report)

    def test_hygiene_scanner_detects_secret_values(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "attempts/WU-000001").mkdir(parents=True)
            (root / "attempts/WU-000001/pi_agent_execution_report.json").write_text("secret-12345\n", encoding="utf-8")
            report = scan_artifact_hygiene(
                root,
                mission_run_id="run-secret",
                expected_artifacts=[],
                report_refs=["attempts/WU-000001/pi_agent_execution_report.json"],
                required_refs=["attempts/WU-000001/pi_agent_execution_report.json"],
                secret_values=["secret-12345"],
            )

        self.assertFalse(report.passed)
        self.assertTrue(any("secret_absent" in failure for failure in report.failures))


if __name__ == "__main__":
    unittest.main()
