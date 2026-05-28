from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import MissionIR, MissionRuntime
from missionforge.state import ArtifactHygieneReport, MissionRun, RuntimeAttempt, inspect_runtime
from tests.test_ir import sample_mission_payload


class RuntimeStateLedgerTests(unittest.TestCase):
    def test_run_writes_mission_run_and_attempt_ledgers(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)
            root = Path(tmpdir)
            run_path = root / "runs/run-sample-mission/mission_run.json"
            attempts_path = root / "runs/run-sample-mission/attempts.jsonl"
            hygiene_path = root / "runs/run-sample-mission/artifact_hygiene.json"

            run = MissionRun.from_dict(json.loads(run_path.read_text(encoding="utf-8")))
            attempts = [
                RuntimeAttempt.from_dict(json.loads(line))
                for line in attempts_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            hygiene = ArtifactHygieneReport.from_dict(json.loads(hygiene_path.read_text(encoding="utf-8")))

        self.assertEqual(result.status, "completed_verified")
        self.assertEqual(run.schema_version, "missionforge.mission_run.v1")
        self.assertEqual(run.mission_run_id, "run-sample-mission")
        self.assertEqual(run.latest_safe_point.kind, "after_completed_turn")
        self.assertEqual(run.attempts_ref, "runs/run-sample-mission/attempts.jsonl")
        self.assertEqual(run.artifact_hygiene_ref, "runs/run-sample-mission/artifact_hygiene.json")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].schema_version, "missionforge.runtime_attempt.v1")
        self.assertEqual(attempts[0].attempt_kind, "initial")
        self.assertEqual(attempts[0].input_ref, "attempts/WU-000001/pi_agent_input.json")
        self.assertEqual(attempts[0].savepoints_ref, "attempts/WU-000001/pi_agent_savepoints.jsonl")
        self.assertTrue(hygiene.passed)

    def test_inspect_runtime_is_read_only_summary(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            MissionRuntime(workspace=tmpdir).run(mission)
            before = sorted(path.relative_to(tmpdir).as_posix() for path in Path(tmpdir).rglob("*") if path.is_file())
            summary = inspect_runtime(tmpdir)
            after = sorted(path.relative_to(tmpdir).as_posix() for path in Path(tmpdir).rglob("*") if path.is_file())

        self.assertEqual(before, after)
        self.assertEqual(summary["schema_version"], "missionforge.runtime_inspection.v1")
        self.assertEqual(summary["mission_run"]["latest_safe_point"]["kind"], "after_completed_turn")
        self.assertEqual(summary["attempt_count"], 1)
        self.assertEqual(summary["latest_attempt"]["attempt_kind"], "initial")


if __name__ == "__main__":
    unittest.main()
