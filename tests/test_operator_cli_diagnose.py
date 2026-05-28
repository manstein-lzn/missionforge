from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI
from tests.test_operator_cli_run import write_mission


class OperatorCLIDiagnoseTests(unittest.TestCase):
    def test_diagnose_complete_run(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])

            result = MissionCLI().run_command(["diagnose", "--workspace", str(root), "--run", "run-sample-mission"])

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["diagnosis"], "complete")
            self.assertEqual(result.data["operator_action"], "no_action")
            self.assertIn("runs/run-sample-mission/artifact_hygiene.json", result.refs)

    def test_diagnose_missing_run_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = MissionCLI().run_command(["diagnose", "--workspace", tempdir, "--run", "run-missing"])

            self.assertEqual(result.exit_code, 3)
            self.assertEqual(result.data["diagnosis"], "missing_state")
            self.assertEqual(result.error.code if result.error else "", "missing_state")

    def test_diagnose_artifact_hygiene_failure_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])
            hygiene_path = root / "runs/run-sample-mission/artifact_hygiene.json"
            hygiene = json.loads(hygiene_path.read_text(encoding="utf-8"))
            hygiene["passed"] = False
            hygiene["failures"] = ["required_ref_exists: package/SKILL.md"]
            hygiene_path.write_text(json.dumps(hygiene, sort_keys=True), encoding="utf-8")

            result = MissionCLI().run_command(["diagnose", "--workspace", str(root), "--run", "run-sample-mission"])

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["diagnosis"], "artifact_hygiene_failed")
            self.assertEqual(result.data["operator_action"], "inspect_hygiene_report")

    def test_diagnose_no_safe_point_and_unsupported_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])
            run_path = root / "runs/run-sample-mission/mission_run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["status"] = "failed"
            run["latest_safe_point"] = None
            run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")

            result = MissionCLI().run_command(["diagnose", "--workspace", str(root), "--run", "run-sample-mission"])
            self.assertEqual(result.data["diagnosis"], "no_resume_safe_point")

            run["latest_safe_point"] = {"kind": "mid_tool_call", "savepoint_ref": "attempts/WU-000001/pi_agent_savepoints.jsonl"}
            run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")
            result = MissionCLI().run_command(["diagnose", "--workspace", str(root), "--run", "run-sample-mission"])
            self.assertEqual(result.data["diagnosis"], "unsupported_resume_boundary")


if __name__ == "__main__":
    unittest.main()
