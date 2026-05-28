from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.piworker import FauxPiWorkerAdapter
from missionforge.contracts import AdaptiveDecision, ContractValidationError, EvidenceTrustLevel, VerificationStatus
from missionforge.evidence_store import InMemoryEvidenceStore
from missionforge.ir import MissionIR, MissionObjective
from missionforge.steering import SteeringProposal
from missionforge.verification import VerificationSpec, ValidatorSpec
from missionforge.verifier import Verifier
from missionforge.work_unit import ExecutionReport, WorkUnitContract


def sample_work_unit() -> WorkUnitContract:
    return WorkUnitContract(
        work_unit_id="WU-000001",
        mission_id="mission-001",
        iteration=1,
        next_objective="Produce deterministic PiWorker fixture output.",
        allowed_scope=["attempts/WU-000001"],
        visible_refs=["mission/frozen_contract.json"],
        expected_outputs=["attempts/WU-000001/artifact.txt"],
        exit_criteria=["Verifier runs."],
        stop_conditions=["Halt control is active."],
    )


class FauxPiWorkerAdapterTests(unittest.TestCase):
    def test_adapter_writes_deterministic_artifact_and_refs_only_report(self) -> None:
        work_unit = sample_work_unit()
        store = InMemoryEvidenceStore()

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            result = FauxPiWorkerAdapter().run(work_unit, workspace=root, evidence_store=store)

            artifact_path = root / "attempts/WU-000001/artifact.txt"
            report_path = root / "attempts/WU-000001/piworker_execution_report.json"
            artifact_body = "faux piworker artifact for WU-000001 output 1\n"

            self.assertEqual(artifact_path.read_text(encoding="utf-8"), artifact_body)
            self.assertTrue(report_path.exists())
            self.assertEqual(result.worker_result.status, "completed")
            self.assertEqual(result.worker_result.execution_report_ref, "attempts/WU-000001/piworker_execution_report.json")
            self.assertEqual(result.execution_report.produced_artifacts, ["attempts/WU-000001/artifact.txt"])
            self.assertEqual(result.execution_report.changed_refs, ["attempts/WU-000001/artifact.txt"])
            self.assertEqual(result.execution_report.worker_claims, [])

            report_data = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(ExecutionReport.from_dict(report_data), result.execution_report)
            self.assertEqual(report_data["worker_claims"], [])
            self.assertEqual(report_data["evidence_refs"], result.event_evidence_refs)
            self.assertNotIn(artifact_body.strip(), json.dumps(report_data, sort_keys=True))

            records = store.snapshot().records
            self.assertEqual(result.event_evidence_refs, [record.evidence_id for record in records])
            self.assertEqual([record.evidence_ref.kind for record in records], ["piworker_event"] * 4)
            self.assertEqual(
                [record.evidence_ref.trust_level for record in records],
                [EvidenceTrustLevel.ARTIFACT_REF] * 4,
            )
            self.assertEqual(
                [record.payload["event_type"] for record in records],
                ["invocation_started", "artifact_written", "metrics_recorded", "invocation_completed"],
            )
            self.assertEqual(records[1].payload["artifact_refs"], ["attempts/WU-000001/artifact.txt"])
            self.assertIn("sha256", records[1].payload)

    def test_adapter_consumes_work_unit_contract_not_raw_mission_or_steering(self) -> None:
        adapter = FauxPiWorkerAdapter()
        mission = MissionIR(
            mission_id="mission-001",
            objective=MissionObjective(
                summary="Compile a mission.",
                deliverable_type="artifact",
                success_signals=["Verifier result."],
            ),
        )
        proposal = SteeringProposal(
            proposal_id="proposal-001",
            mission_run_id="run-001",
            iteration=1,
            input_refs=["mission/frozen_contract.json"],
            recommended_route=AdaptiveDecision.CONTINUE,
        )

        with self.assertRaisesRegex(ContractValidationError, "WorkUnitContract"):
            adapter.run(mission)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ContractValidationError, "WorkUnitContract"):
            adapter.run(proposal)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ContractValidationError, "WorkUnitContract"):
            adapter.run({"work_unit_id": "WU-000001"})  # type: ignore[arg-type]

    def test_adapter_rejects_outputs_outside_allowed_scope(self) -> None:
        work_unit = replace(sample_work_unit(), expected_outputs=["outside/WU-000001/artifact.txt"])

        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "outside allowed scope"):
                FauxPiWorkerAdapter().run(work_unit, workspace=tempdir, evidence_store=InMemoryEvidenceStore())

    def test_contract_adjustment_is_evidence_not_work_unit_mutation(self) -> None:
        work_unit = sample_work_unit()
        before = work_unit.to_dict()
        store = InMemoryEvidenceStore()

        with tempfile.TemporaryDirectory() as tempdir:
            result = FauxPiWorkerAdapter(request_contract_adjustment=True).run(
                work_unit,
                workspace=tempdir,
                evidence_store=store,
            )

        self.assertEqual(work_unit.to_dict(), before)
        adjustment_records = [
            record for record in store.snapshot().records if record.evidence_ref.kind == "contract_adjustment_request"
        ]
        self.assertEqual(len(adjustment_records), 1)
        adjustment = adjustment_records[0]
        self.assertEqual(adjustment.evidence_ref.trust_level, EvidenceTrustLevel.ARTIFACT_REF)
        self.assertEqual(adjustment.payload["work_unit_id"], "WU-000001")
        self.assertEqual(adjustment.payload["requested_change"], "review_required")
        self.assertNotIn(adjustment.evidence_id, result.event_evidence_refs)
        self.assertIn(adjustment.evidence_id, result.execution_report.evidence_refs)
        self.assertEqual(result.execution_report.metrics["contract_adjustment_ref"], adjustment.evidence_id)

    def test_adapter_completion_and_metrics_do_not_grant_verifier_completion(self) -> None:
        work_unit = sample_work_unit()
        store = InMemoryEvidenceStore()

        with tempfile.TemporaryDirectory() as tempdir:
            result = FauxPiWorkerAdapter().run(work_unit, workspace=tempdir, evidence_store=store)
            spec = VerificationSpec(
                validators=[
                    ValidatorSpec(
                        validator_id="artifact_requires_verifier_evidence",
                        constraint_refs=["completion_authority"],
                        type="file_exists",
                        inputs={
                            "path": "attempts/WU-000001/artifact.txt",
                            "required_evidence_ids": list(result.event_evidence_refs),
                            "minimum_trust_level": EvidenceTrustLevel.VERIFIER_RESULT.value,
                        },
                    )
                ]
            )
            verification = Verifier(workspace=tempdir, evidence_store=store).verify(spec)

        self.assertEqual(result.execution_report.status, "completed")
        self.assertEqual(result.metrics["adapter_result_status"], "completed")
        self.assertEqual(verification.status, VerificationStatus.FAILED)
        self.assertEqual(verification.failed_constraint_ids, ["completion_authority"])
        self.assertEqual(
            sorted({missing.required_trust_level for missing in verification.missing_evidence}),
            [EvidenceTrustLevel.VERIFIER_RESULT.value],
        )


if __name__ == "__main__":
    unittest.main()
