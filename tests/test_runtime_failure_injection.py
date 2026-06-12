from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.ir import MissionIR
from missionforge.runner import MissionRuntime
from missionforge.adapters.pi_agent_runtime import PiAgentCommandResult, PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from missionforge.evidence_store import InMemoryEvidenceStore
from missionforge.runtime import RuntimeEngine
from missionforge.work_unit import ExecutionReport, WorkerResult
from missionforge.workers import WorkerAdapterResult
from tests.test_ir import sample_mission_payload
from tests.test_pi_agent_runtime_adapter import RecordingRunner, sample_work_unit


class RuntimeFailureInjectionTests(unittest.TestCase):
    def test_provider_timeout_routes_to_failed_without_verifier_success(self) -> None:
        runner = RecordingRunner(result=PiAgentCommandResult(returncode=-1, timed_out=True), write_output=False)

        with TemporaryDirectory() as tmpdir:
            result = PiAgentRuntimeAdapter(PiAgentRuntimeConfig(command=("pi-agent-runtime",)), runner=runner).run(
                sample_work_unit(),
                workspace=tmpdir,
                evidence_store=InMemoryEvidenceStore(),
            )
            output = json.loads(Path(tmpdir, "attempts/WU-000001/pi_agent_output.json").read_text(encoding="utf-8"))

        self.assertEqual(result.worker_result.status, "failed")
        self.assertEqual(output["verification_status"], "failed")

    def test_invalid_output_is_worker_failure_not_success(self) -> None:
        runner = RecordingRunner(write_output=False)

        with TemporaryDirectory() as tmpdir:
            result = PiAgentRuntimeAdapter(PiAgentRuntimeConfig(command=("pi-agent-runtime",)), runner=runner).run(
                sample_work_unit(),
                workspace=tmpdir,
                evidence_store=InMemoryEvidenceStore(),
            )

        self.assertEqual(result.worker_result.status, "failed")

    def test_unsupported_validator_marks_redesign_required(self) -> None:
        payload = sample_mission_payload()
        payload["verification"]["validators"] = [
            {
                "validator_id": "V-unsupported",
                "constraint_refs": ["C-001"],
                "type": "file_exists",
                "mode": "unsupported",
                "inputs": {"path": "package/SKILL.md"},
            }
        ]
        mission = MissionIR.from_dict(payload)

        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)
            run = json.loads(Path(tmpdir, "runs/run-sample-mission/mission_run.json").read_text(encoding="utf-8"))

        self.assertEqual(result.status, "unsupported_verification_spec")
        self.assertTrue(result.metrics["redesign_required"])
        self.assertEqual(run["latest_decision"], "redesign")

    def test_repair_exhaustion_is_recorded(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            result = RuntimeEngine(workspace=tmpdir, max_attempts=1, worker=_NoArtifactWorker()).run(mission)
            run = json.loads(Path(tmpdir, "runs/run-sample-mission/mission_run.json").read_text(encoding="utf-8"))

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.metrics["repair_exhausted"])
        self.assertEqual(run["next_action"], "inspect_failure")


class _NoArtifactWorker:
    def run(self, work_unit, *, workspace=".", evidence_store=None):
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=[],
            changed_refs=[],
            evidence_refs=[],
            metrics={},
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=f"attempts/{work_unit.work_unit_id}/report.json"),
        )


if __name__ == "__main__":
    unittest.main()
