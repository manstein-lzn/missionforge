from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI
from tests.test_operator_cli_run import write_mission


class OperatorMetricProjectionTests(unittest.TestCase):
    def test_inspect_surfaces_metric_projection_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])

            result = MissionCLI().run_command(["inspect", "--workspace", str(root), "--run", "run-sample-mission"])

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["metric_events_ref"], "runs/run-sample-mission/metrics/events.jsonl")
            self.assertEqual(result.data["metric_projection_ref"], "runs/run-sample-mission/metrics/projection.json")
            self.assertIn("missionforge.runtime", result.data["metric_projection"]["namespaces"])
            self.assertIn("runs/run-sample-mission/metrics/projection.json", result.refs)

    def test_diagnose_reads_projection_flags_not_runtime_metric_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])
            run_path = root / "runs/run-sample-mission/mission_run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["status"] = "failed"
            run["latest_safe_point"] = None
            run["metrics"]["rejected_proposal_count"] = 1
            run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")

            result = MissionCLI().run_command(["diagnose", "--workspace", str(root), "--run", "run-sample-mission"])

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["diagnosis"], "no_resume_safe_point")


if __name__ == "__main__":
    unittest.main()
