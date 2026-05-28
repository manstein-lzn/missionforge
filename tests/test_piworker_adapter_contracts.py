from __future__ import annotations

import unittest

from missionforge.adapters.piworker import (
    ContractAdjustmentEvidence,
    PiWorkerEvent,
    PiWorkerInput,
    PiWorkerMetrics,
    PiWorkerOutput,
)
from missionforge.contracts import ContractValidationError
from missionforge.work_unit import WorkUnitContract


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


class PiWorkerAdapterContractTests(unittest.TestCase):
    def test_piworker_input_from_work_unit_round_trip(self) -> None:
        piworker_input = PiWorkerInput.from_work_unit(sample_work_unit())

        self.assertEqual(piworker_input.work_unit_id, "WU-000001")
        self.assertEqual(piworker_input.expected_outputs, ["attempts/WU-000001/artifact.txt"])
        self.assertEqual(PiWorkerInput.from_dict(piworker_input.to_dict()), piworker_input)

    def test_piworker_event_round_trip(self) -> None:
        event = PiWorkerEvent(
            event_id="event-001",
            work_unit_id="WU-000001",
            event_type="artifact_written",
            artifact_refs=["attempts/WU-000001/artifact.txt"],
            evidence_refs=["E-000001"],
            metrics=PiWorkerMetrics(tool_call_count=1, cache_miss_count=1, token_count=10),
        )

        self.assertEqual(PiWorkerEvent.from_dict(event.to_dict()), event)

    def test_piworker_output_round_trip(self) -> None:
        output = PiWorkerOutput(
            work_unit_id="WU-000001",
            status="completed",
            produced_artifacts=["attempts/WU-000001/artifact.txt"],
            event_evidence_refs=["E-000001"],
            execution_report_ref="attempts/WU-000001/piworker_execution_report.json",
            metrics=PiWorkerMetrics(tool_call_count=1),
        )

        self.assertEqual(PiWorkerOutput.from_dict(output.to_dict()), output)

    def test_contract_adjustment_evidence_round_trip(self) -> None:
        evidence = ContractAdjustmentEvidence(
            request_id="adjust-WU-000001",
            work_unit_id="WU-000001",
            requested_change="review_required",
            reason="Adapter requests review.",
            evidence_refs=["E-000001"],
        )

        self.assertEqual(ContractAdjustmentEvidence.from_dict(evidence.to_dict()), evidence)

    def test_invalid_contract_values_are_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            PiWorkerEvent(
                event_id="event-001",
                work_unit_id="WU-000001",
                event_type="live_provider_call",
            ).validate()

        with self.assertRaises(ContractValidationError):
            PiWorkerOutput(
                work_unit_id="WU-000001",
                status="accepted",
                execution_report_ref="attempts/WU-000001/report.json",
            ).validate()

        with self.assertRaises(ContractValidationError):
            ContractAdjustmentEvidence(
                request_id="adjust-WU-000001",
                work_unit_id="WU-000001",
                requested_change="expand",
                reason="Needs broader scope.",
                authority_required="worker",
            ).validate()


if __name__ == "__main__":
    unittest.main()
