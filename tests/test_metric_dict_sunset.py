from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI
from tests.test_operator_cli_run import write_mission


class MetricDictSunsetTests(unittest.TestCase):
    def test_operator_diagnose_ignores_loose_runtime_metric_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])
            run_path = root / "runs/run-sample-mission/mission_run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["status"] = "failed"
            run["metrics"]["repair_exhausted"] = True
            run["metrics"]["redesign_required"] = True
            run["metrics"]["unsafe_proposal_rejection_count"] = 1
            run["metrics"]["adapter_private_route"] = "stop"
            run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")

            result = MissionCLI().run_command(["diagnose", "--workspace", str(root), "--run", "run-sample-mission"])

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["diagnosis"], "repairable_verifier_failure")

    def test_operator_diagnose_uses_metric_projection_for_diagnostic_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])
            run_path = root / "runs/run-sample-mission/mission_run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["status"] = "failed"
            run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")
            projection_path = root / "runs/run-sample-mission/metrics/projection.json"
            projection = json.loads(projection_path.read_text(encoding="utf-8"))
            projection["diagnostic_flags"] = ["repair_exhausted"]
            projection_path.write_text(json.dumps(projection, sort_keys=True), encoding="utf-8")

            result = MissionCLI().run_command(["diagnose", "--workspace", str(root), "--run", "run-sample-mission"])

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["diagnosis"], "repair_exhausted")


if __name__ == "__main__":
    unittest.main()
