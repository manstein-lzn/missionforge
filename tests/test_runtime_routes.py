from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge.ir import MissionIR
from missionforge.runner import MissionRuntime
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
            result = RuntimeEngine(workspace=tmpdir, worker=_FirstArtifactOnlyWorker()).run(mission)

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

    def test_initial_work_unit_names_all_expected_outputs(self) -> None:
        payload = sample_mission_payload()
        payload["outputs"]["required_artifacts"] = [
            "package/SKILL.md",
            "package/skillfoundry.bundle.json",
            "package/README.md",
        ]
        mission = MissionIR.from_dict(payload)
        worker = _CapturingWorker()

        with TemporaryDirectory() as tmpdir:
            RuntimeEngine(workspace=tmpdir, worker=worker).run(mission)

        self.assertIsNotNone(worker.work_unit)
        work_unit = worker.work_unit
        self.assertEqual(work_unit.expected_outputs, payload["outputs"]["required_artifacts"])
        for output_ref in payload["outputs"]["required_artifacts"]:
            self.assertIn(output_ref, work_unit.next_objective)
            self.assertTrue(
                any(output_ref in criterion for criterion in work_unit.exit_criteria),
                f"{output_ref} missing from exit criteria",
            )

    def test_initial_work_unit_includes_artifact_contract_guidance(self) -> None:
        payload = sample_mission_payload()
        payload["outputs"]["required_artifacts"] = [
            "package/SKILL.md",
            "package/skillfoundry.bundle.json",
            "package/README.md",
        ]
        payload["outputs"]["artifact_contracts"] = [
            {
                "artifact_ref": "package/skillfoundry.bundle.json",
                "kind": "json",
                "role": "bundle_manifest",
                "required_keys": ["schema_version", "bundle_id", "entrypoint"],
                "forbidden_extra_keys": True,
                "field_contract": {
                    "schema_version": "skillfoundry.bundle.v1",
                    "bundle_id": "demo-skill",
                    "entrypoint": "SKILL.md",
                },
                "notes": ["Use entrypoint exactly SKILL.md."],
            }
        ]
        mission = MissionIR.from_dict(payload)
        worker = _CapturingWorker()

        with TemporaryDirectory() as tmpdir:
            RuntimeEngine(workspace=tmpdir, worker=worker).run(mission)

        self.assertIsNotNone(worker.work_unit)
        work_unit = worker.work_unit
        self.assertIn("package/skillfoundry.bundle.json", work_unit.next_objective)
        self.assertIn("required JSON keys=schema_version, bundle_id, entrypoint", work_unit.next_objective)
        self.assertIn('"entrypoint":"SKILL.md"', work_unit.next_objective)
        self.assertTrue(any("Do not add extra JSON keys" in criterion for criterion in work_unit.exit_criteria))


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


class _CapturingWorker:
    def __init__(self) -> None:
        self.work_unit = None

    def run(self, work_unit, *, workspace=".", evidence_store=None):
        from pathlib import Path

        self.work_unit = work_unit
        produced = []
        for output_ref in work_unit.expected_outputs:
            artifact = Path(workspace, output_ref)
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("# captured\n", encoding="utf-8")
            produced.append(output_ref)
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=produced,
            changed_refs=produced,
            evidence_refs=[],
            worker_claims=["done"],
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=f"attempts/{work_unit.work_unit_id}/report.json"),
        )


class _FirstArtifactOnlyWorker:
    def run(self, work_unit, *, workspace=".", evidence_store=None):
        from pathlib import Path

        produced = []
        if work_unit.expected_outputs:
            artifact = Path(workspace, work_unit.expected_outputs[0])
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("# partial\n", encoding="utf-8")
            produced = [work_unit.expected_outputs[0]]
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=produced,
            changed_refs=produced,
            evidence_refs=[],
            worker_claims=["done"],
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=f"attempts/{work_unit.work_unit_id}/report.json"),
        )


if __name__ == "__main__":
    unittest.main()
