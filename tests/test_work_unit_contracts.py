from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge.work_unit import AttemptInputManifest, ExecutionReport, WorkUnitContract, WorkerResult


class WorkUnitContractTests(unittest.TestCase):
    def test_work_unit_contract_round_trip(self) -> None:
        contract = WorkUnitContract.from_dict(
            {
                "work_unit_id": "WU-001",
                "mission_id": "mission-001",
                "iteration": 1,
                "next_objective": "Write the required artifact.",
                "allowed_scope": ["package", "attempts/001"],
                "visible_refs": ["mission/frozen_contract.json"],
                "expected_outputs": ["attempts/001/execution_report.json"],
                "exit_criteria": ["Execution report is written."],
                "stop_conditions": ["Scope expansion is required."],
            }
        )

        self.assertEqual(WorkUnitContract.from_dict(contract.to_dict()), contract)

    def test_work_unit_contract_rejects_unsafe_expected_output(self) -> None:
        with self.assertRaises(ContractValidationError):
            WorkUnitContract.from_dict(
                {
                    "work_unit_id": "WU-001",
                    "mission_id": "mission-001",
                    "iteration": 1,
                    "next_objective": "Write the required artifact.",
                    "expected_outputs": ["../outside"],
                }
            )

    def test_execution_report_round_trip(self) -> None:
        report = ExecutionReport.from_dict(
            {
                "report_id": "R-001",
                "work_unit_id": "WU-001",
                "status": "completed",
                "produced_artifacts": ["package/SKILL.md"],
                "changed_refs": ["package/SKILL.md"],
                "evidence_refs": ["attempts/001/report.json"],
                "worker_claims": ["Worker says done."],
                "metrics": {"duration_ms": 1},
            }
        )

        self.assertEqual(ExecutionReport.from_dict(report.to_dict()), report)

    def test_attempt_manifest_and_worker_result_validate_refs(self) -> None:
        manifest = AttemptInputManifest(
            attempt_id="attempt-001",
            work_unit_id="WU-001",
            visible_refs=["mission/frozen_contract.json"],
        )
        result = WorkerResult(status="completed", execution_report_ref="attempts/001/report.json")

        self.assertEqual(AttemptInputManifest.from_dict(manifest.to_dict()), manifest)
        self.assertEqual(WorkerResult.from_dict(result.to_dict()), result)


if __name__ == "__main__":
    unittest.main()
