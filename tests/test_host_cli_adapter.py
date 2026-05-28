from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI, MissionCLIResult
from missionforge.runner import MissionResult
from tests.test_ir import sample_mission_payload


def write_mission(root: Path, ref: str = "missions/input.mission.json") -> str:
    path = root / ref
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(sample_mission_payload(), sort_keys=True), encoding="utf-8")
    return ref


class HostCLIAdapterTests(unittest.TestCase):
    def test_cli_shell_passes_mission_ir_in_and_receives_mission_result_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)

            result = MissionCLI().run_mission_ref(mission_ref, workspace=root)
            result_path = root / result.mission_result_ref
            mission_result = MissionResult.from_dict(json.loads(result_path.read_text(encoding="utf-8")))

            self.assertEqual(result.status, "completed_verified")
            self.assertEqual(result.mission_id, "sample-mission")
            self.assertEqual(mission_result.status, "completed_verified")
            self.assertEqual(MissionCLIResult.from_dict(result.to_dict()), result)

    def test_cli_argument_shell_writes_requested_result_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)

            result = MissionCLI().run(
                [
                    "--workspace",
                    str(root),
                    "--mission-ref",
                    mission_ref,
                    "--result-ref",
                    "host_results/custom_result.json",
                ]
            )

            self.assertEqual(result.mission_result_ref, "host_results/custom_result.json")
            self.assertTrue((root / "host_results/custom_result.json").exists())


if __name__ == "__main__":
    unittest.main()
