from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI
from missionforge.adapters.skillfoundry import SkillFoundryMissionCompiler
from tests.test_skillfoundry_compiler import sample_bundle, write_frontdesk_fixture


class OperatorSkillFoundrySmokeTests(unittest.TestCase):
    def test_compiled_skillfoundry_mission_runs_and_inspects_through_operator_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_frontdesk_fixture(root)
            compile_result = SkillFoundryMissionCompiler().compile(sample_bundle(), workspace=root)

            run = MissionCLI().run_command(
                ["run", "--workspace", str(root), "--mission-ref", compile_result.mission_ir_ref]
            )
            inspect = MissionCLI().run_command(
                ["inspect", "--workspace", str(root), "--run", "run-skillfoundry-capability"]
            )

            self.assertEqual(run.exit_code, 0)
            self.assertEqual(run.data["mission_id"], "skillfoundry-capability")
            self.assertEqual(inspect.exit_code, 0)
            self.assertEqual(inspect.data["mission_id"], "skillfoundry-capability")
            self.assertEqual(inspect.data["artifact_refs"], ["package/SKILL.md"])
            self.assertEqual(inspect.data["status"], "completed_verified")


if __name__ == "__main__":
    unittest.main()
