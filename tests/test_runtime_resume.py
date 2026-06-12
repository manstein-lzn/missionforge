from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import ContractValidationError
from missionforge.ir import MissionIR
from missionforge.runner import MissionRuntime
from missionforge.runtime import RuntimeEngine
from missionforge.work_unit import ExecutionReport, WorkerResult
from missionforge.workers import WorkerAdapterResult
from tests.test_ir import sample_mission_payload


class RuntimeResumeTests(unittest.TestCase):
    def test_resume_uses_completed_turn_safe_point_and_records_resume_attempt(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            runtime = MissionRuntime(workspace=tmpdir)
            runtime.run(mission)
            result = runtime.resume(mission, follow_up_prompt="Continue from the saved turn.")
            summary = runtime.inspect("run-sample-mission")
            initial_output_exists = Path(tmpdir, "attempts/WU-000001/pi_agent_output.json").exists()
            resume_output_exists = Path(tmpdir, "attempts/WU-000002/pi_agent_output.json").exists()

        self.assertEqual(result.status, "completed_verified")
        self.assertEqual(summary["attempt_count"], 2)
        self.assertEqual(summary["mission_run"]["current_attempt"], "attempt-000002")
        self.assertEqual(summary["latest_attempt"]["attempt_kind"], "resume")
        self.assertEqual(summary["latest_attempt"]["work_unit_id"], "WU-000002")
        self.assertTrue(initial_output_exists)
        self.assertTrue(resume_output_exists)
        self.assertEqual(summary["mission_run"]["metrics"]["resume_count"], 1)

    def test_resume_rejects_unsupported_boundary(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        worker = _BoundaryWorker()

        with TemporaryDirectory() as tmpdir:
            RuntimeEngine(workspace=tmpdir, worker=worker).run(mission)
            run_path = f"{tmpdir}/runs/run-sample-mission/mission_run.json"
            with open(run_path, encoding="utf-8") as handle:
                text = handle.read()
            with open(run_path, "w", encoding="utf-8") as handle:
                handle.write(text.replace("after_completed_turn", "mid_tool_call", 1))
            with self.assertRaisesRegex(ContractValidationError, "unsupported resume boundary"):
                RuntimeEngine(workspace=tmpdir, worker=worker).resume(mission)


class _BoundaryWorker:
    def run(self, work_unit, *, workspace=".", evidence_store=None):
        from pathlib import Path

        root = Path(workspace)
        artifact = root / "package/SKILL.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("# ok\n", encoding="utf-8")
        savepoints = root / f"attempts/{work_unit.work_unit_id}/pi_agent_savepoints.jsonl"
        savepoints.parent.mkdir(parents=True, exist_ok=True)
        savepoints.write_text(
            '{"schema_version":"missionforge.pi_agent_runtime_savepoint.v1","turn_index":1,'
            '"resume_hint":{"boundary":"after_completed_turn"}}\n',
            encoding="utf-8",
        )
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=["package/SKILL.md"],
            changed_refs=["package/SKILL.md"],
            evidence_refs=[],
            metrics={
                "input_ref": f"attempts/{work_unit.work_unit_id}/pi_agent_input.json",
                "output_ref": f"attempts/{work_unit.work_unit_id}/pi_agent_output.json",
                "savepoints_ref": f"attempts/{work_unit.work_unit_id}/pi_agent_savepoints.jsonl",
            },
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=f"attempts/{work_unit.work_unit_id}/report.json"),
        )

    def with_resume(self, **kwargs):
        return self


if __name__ == "__main__":
    unittest.main()
