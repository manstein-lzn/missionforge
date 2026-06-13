from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI
from tests.operator_state_fixtures import seed_operator_run


class OperatorCLIControlTests(unittest.TestCase):
    def test_control_halt_writes_intent_only_without_mutating_mission_run(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            seed_operator_run(root)
            run_path = root / "runs/run-sample-mission/mission_run.json"
            before = run_path.read_text(encoding="utf-8")

            result = MissionCLI().run_command(
                [
                    "control",
                    "halt",
                    "--workspace",
                    str(root),
                    "--run",
                    "run-sample-mission",
                    "--reason",
                    "Pause before the next attempt.",
                ]
            )
            after = run_path.read_text(encoding="utf-8")
            control_payload = json.loads((root / result.data["control_ref"]).read_text(encoding="utf-8"))

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.command, "control halt")
            self.assertEqual(result.data["control_ref"], "control/run-sample-mission.halt.json")
            self.assertEqual(before, after)
            self.assertEqual(control_payload["control_type"], "halt")
            self.assertEqual(control_payload["reason"], "Pause before the next attempt.")

    def test_control_halt_missing_run_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = MissionCLI().run_command(
                [
                    "control",
                    "halt",
                    "--workspace",
                    tempdir,
                    "--run",
                    "run-missing",
                    "--reason",
                    "Pause.",
                ]
            )

            self.assertEqual(result.exit_code, 3)
            self.assertEqual(result.error.code if result.error else "", "missing_state")


if __name__ == "__main__":
    unittest.main()
