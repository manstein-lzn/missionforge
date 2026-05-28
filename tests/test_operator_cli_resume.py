from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI
from tests.test_operator_cli_run import write_mission


class OperatorCLIResumeTests(unittest.TestCase):
    def test_resume_command_appends_attempt_and_omits_prompt_from_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])

            result = MissionCLI().run_command(
                [
                    "resume",
                    "--workspace",
                    str(root),
                    "--run",
                    "run-sample-mission",
                    "--mission-ref",
                    mission_ref,
                    "--prompt",
                    "Continue from the latest completed turn.",
                ]
            )
            inspect = MissionCLI().run_command(["inspect", "--workspace", str(root), "--run", "run-sample-mission"])
            output = json.dumps(result.to_dict(), sort_keys=True)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.command, "resume")
            self.assertEqual(inspect.data["attempt_count"], 2)
            self.assertEqual(inspect.data["latest_attempt"]["attempt_kind"], "resume")
            self.assertNotIn("Continue from the latest completed turn.", output)

    def test_resume_rejects_missing_or_unsupported_safe_point(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])
            run_path = root / "runs/run-sample-mission/mission_run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["latest_safe_point"] = None
            run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")

            result = MissionCLI().run_command(
                ["resume", "--workspace", str(root), "--run", "run-sample-mission", "--mission-ref", mission_ref]
            )

            self.assertEqual(result.exit_code, 4)
            self.assertEqual(result.error.code if result.error else "", "unsupported_operation")

            run["latest_safe_point"] = {"kind": "mid_tool_call", "savepoint_ref": "attempts/WU-000001/pi_agent_savepoints.jsonl"}
            run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")
            result = MissionCLI().run_command(
                ["resume", "--workspace", str(root), "--run", "run-sample-mission", "--mission-ref", mission_ref]
            )

            self.assertEqual(result.exit_code, 4)
            self.assertIn("unsupported resume boundary", result.error.message if result.error else "")

    def test_resume_rejects_mismatched_mission_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            other_ref = write_mission(root, "missions/other.mission.json")
            other_payload = json.loads((root / other_ref).read_text(encoding="utf-8"))
            other_payload["mission_id"] = "other-mission"
            (root / other_ref).write_text(json.dumps(other_payload, sort_keys=True), encoding="utf-8")
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])

            result = MissionCLI().run_command(
                ["resume", "--workspace", str(root), "--run", "run-sample-mission", "--mission-ref", other_ref]
            )

            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")


if __name__ == "__main__":
    unittest.main()
