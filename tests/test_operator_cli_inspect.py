from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI
from tests.operator_state_fixtures import seed_operator_run, workspace_snapshot


class OperatorCLIInspectTests(unittest.TestCase):
    def test_inspect_command_returns_read_only_runtime_view(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            seed_operator_run(root)
            before = workspace_snapshot(root)

            result = MissionCLI().run_command(["inspect", "--workspace", str(root), "--run", "run-sample-mission"])
            after = workspace_snapshot(root)

            self.assertEqual(before, after)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["mission_run_id"], "run-sample-mission")
            self.assertEqual(result.data["mission_id"], "sample-mission")
            self.assertEqual(result.data["status"], "completed_verified")
            self.assertEqual(result.data["current_attempt"], "attempt-000001")
            self.assertEqual(result.data["latest_call_id"], "WU-000001")
            self.assertEqual(result.data["attempt_count"], 1)
            self.assertIn("latest_safe_point", result.data)
            self.assertEqual(result.data["latest_attempt"]["attempt_kind"], "initial")
            self.assertEqual(result.data["artifact_refs"], ["package/SKILL.md"])
            self.assertEqual(result.data["artifact_hygiene"]["passed"], True)
            self.assertIn("runs/run-sample-mission/attempts.jsonl", result.refs)

    def test_inspect_missing_run_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = MissionCLI().run_command(["inspect", "--workspace", tempdir, "--run", "run-missing"])

            self.assertEqual(result.exit_code, 3)
            self.assertEqual(result.error.code if result.error else "", "missing_state")

    def test_inspect_output_rejects_hygiene_body_if_it_appears(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            seed_operator_run(root)
            hygiene_path = root / "runs/run-sample-mission/artifact_hygiene.json"
            hygiene = json.loads(hygiene_path.read_text(encoding="utf-8"))
            hygiene["checks"] = [{"raw_payload": "not allowed"}]
            hygiene_path.write_text(json.dumps(hygiene, sort_keys=True), encoding="utf-8")

            result = MissionCLI().run_command(["inspect", "--workspace", str(root), "--run", "run-sample-mission"])

            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")


if __name__ == "__main__":
    unittest.main()
