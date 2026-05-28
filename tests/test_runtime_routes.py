from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge import MissionIR, MissionRuntime
from missionforge.runtime import RuntimeEngine
from missionforge.work_unit import ExecutionReport, WorkerResult
from missionforge.workers import WorkerAdapterResult
from tests.test_ir import sample_mission_payload


class RuntimeRouteTests(unittest.TestCase):
    def test_missing_artifact_routes_to_failed_with_constraint_ids(self) -> None:
        payload = sample_mission_payload()
        payload["outputs"]["required_artifacts"] = ["package/SKILL.md", "package/MISSING.md"]
        mission = MissionIR.from_dict(payload)

        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failed_constraint_ids, ["C-001"])

    def test_manual_gate_routes_to_review_required(self) -> None:
        payload = sample_mission_payload()
        payload["verification"]["manual_gates"] = [{"authority": "reviewer", "severity": "blocking"}]
        mission = MissionIR.from_dict(payload)

        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)

        self.assertEqual(result.status, "review_required")

    def test_unsupported_validator_routes_to_unsupported_verification_spec(self) -> None:
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

        self.assertEqual(result.status, "unsupported_verification_spec")

    def test_verifier_failure_routes_to_bounded_repair_attempt(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        worker = _RepairableWorker()

        with TemporaryDirectory() as tmpdir:
            result = RuntimeEngine(workspace=tmpdir, max_attempts=2, worker=worker).run(mission)

        self.assertEqual(result.status, "completed_verified")
        self.assertEqual(result.metrics["attempt_count"], 2)
        self.assertTrue(result.metrics["repair_attempted"])
        self.assertEqual(worker.calls, ["initial", "with_repair", "repair"])


class _RepairableWorker:
    def __init__(self, *, repaired: bool = False, calls: list[str] | None = None) -> None:
        self.repaired = repaired
        self.calls = calls if calls is not None else []

    def run(self, work_unit, *, workspace=".", evidence_store=None):
        from pathlib import Path

        self.calls.append("repair" if self.repaired else "initial")
        produced = []
        if self.repaired:
            artifact = Path(workspace, "package/SKILL.md")
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("# repaired\n", encoding="utf-8")
            produced = ["package/SKILL.md"]
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=produced,
            changed_refs=produced,
            evidence_refs=[],
            worker_claims=["done"],
            metrics={"repaired": self.repaired},
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=f"attempts/{work_unit.work_unit_id}/report.json"),
        )

    def with_repair(self, **kwargs):
        self.calls.append("with_repair")
        return _RepairableWorker(repaired=True, calls=self.calls)


if __name__ == "__main__":
    unittest.main()
