from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI, MissionCLIResult, MissionCommandResult
from tests.test_ir import sample_mission_payload


def write_mission(root: Path, ref: str = "missions/input.mission.json") -> str:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sample_mission_payload(), sort_keys=True), encoding="utf-8")
    return ref


class OperatorCLIRunTests(unittest.TestCase):
    def test_run_command_emits_command_result_and_writes_mission_result_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)

            result = MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])

            payload = result.to_dict()
            self.assertEqual(MissionCommandResult.from_dict(payload), result)
            self.assertEqual(result.command, "run")
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.data["mission_result_ref"], "host_results/sample-mission.mission_result.json")
            self.assertTrue((root / result.data["mission_result_ref"]).exists())
            self.assertNotIn("Build a verified local capability bundle", json.dumps(payload, sort_keys=True))

    def test_run_command_rejects_invalid_mission_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = MissionCLI().run_command(
                ["run", "--workspace", tempdir, "--mission-ref", "../outside.json"]
            )

            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")

    def test_failed_runtime_status_maps_to_verification_failure_exit(self) -> None:
        result = _FailedMissionCLI().run_command(
            ["run", "--workspace", ".", "--mission-ref", "missions/input.mission.json"]
        )

        self.assertEqual(result.exit_code, 6)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error.code if result.error else "", "verification_failed")
        self.assertEqual(result.data["failed_constraint_ids"], ["C-001"])


class _FailedMissionCLI(MissionCLI):
    def run_mission_ref(self, mission_ref, *, workspace=".", result_ref=None, max_attempts=1):
        return MissionCLIResult(
            mission_id="sample-mission",
            status="failed",
            mission_result_ref="host_results/sample-mission.mission_result.json",
            failed_constraint_ids=["C-001"],
            metrics={"verification_status": "failed"},
        )


if __name__ == "__main__":
    unittest.main()
