from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge.piworker_call import (
    PIWORKER_CALL_RESULT_SCHEMA_VERSION,
    PIWORKER_CALL_SCHEMA_VERSION,
    PiWorkerCall,
    PiWorkerCallResult,
    PiWorkerCallResultStatus,
    PiWorkerCallRole,
)
from missionforge.runtime_results import ExecutionReport, WorkerResult
from missionforge.runtime_results import WorkerAdapterResult


HASH_A = "sha256:" + "a" * 64


def piworker_call_payload() -> dict[str, object]:
    return {
        "call_id": "call-001",
        "schema_version": PIWORKER_CALL_SCHEMA_VERSION,
        "role": "executor_piworker",
        "contract_id": "contract-001",
        "contract_hash": HASH_A,
        "contract_ref": "contract/task_contract.json",
        "objective": "Produce expected artifacts.",
        "visible_refs": [
            "contract/task_contract.json",
            "projections/worker_brief.json",
            "policy/permission_manifest.json",
        ],
        "writable_refs": ["artifacts", "reports"],
        "expected_output_refs": ["artifacts/final.md"],
        "permission_manifest_ref": "policy/permission_manifest.json",
        "source_packet_ref": "packets/execution_packet.json",
        "source_packet_hash": "sha256:" + "b" * 64,
        "evidence_refs": ["evidence/input.json"],
        "output_schema_ref": "schemas/agent_execution_report.json",
        "validation_policy_ref": "validation/piworker_executor_policy.json",
        "runtime_budget": {"max_turns": 4, "timeout_seconds": 300},
        "metadata": {"runtime_config_ref": "runtime/pi_agent_runtime.json"},
    }


def piworker_call_result_payload() -> dict[str, object]:
    return {
        "result_id": "call-001-result",
        "schema_version": PIWORKER_CALL_RESULT_SCHEMA_VERSION,
        "call_id": "call-001",
        "role": "executor_piworker",
        "contract_id": "contract-001",
        "contract_hash": HASH_A,
        "contract_ref": "contract/task_contract.json",
        "status": "completed",
        "execution_report_ref": "attempts/call-001/pi_agent_execution_report.json",
        "output_refs": ["artifacts/final.md"],
        "runtime_refs": [
            "attempts/call-001/pi_agent_execution_report.json",
            "attempts/call-001/pi_agent_output.json",
        ],
        "evidence_refs": ["evidence/adapter_event_001.json"],
        "metric_refs": ["attempts/call-001/pi_agent_metrics.json"],
        "validation_report_ref": "attempts/call-001/piworker_call_validation.json",
        "error_ref": None,
        "metadata": {"runtime_config_ref": "runtime/pi_agent_runtime.json"},
    }


def worker_adapter_result(*, status: str = "completed", produced_refs: list[str] | None = None) -> WorkerAdapterResult:
    safe_produced_refs = produced_refs if produced_refs is not None else ["artifacts/final.md"]
    report = ExecutionReport(
        report_id="R-call-001",
        call_id="call-001",
        status=status,
        produced_artifacts=safe_produced_refs,
        changed_refs=[
            *safe_produced_refs,
            "attempts/call-001/pi_agent_output.json",
            "attempts/call-001/pi_agent_metrics.json",
        ],
        evidence_refs=["evidence/adapter_event_001.json"],
        metrics={"metrics_ref": "attempts/call-001/pi_agent_metrics.json"},
    )
    return WorkerAdapterResult(
        execution_report=report,
        worker_result=WorkerResult(
            status=status,
            execution_report_ref="attempts/call-001/pi_agent_execution_report.json",
        ),
        event_evidence_refs=["evidence/adapter_event_002.json"],
        metrics={"duration_ms": 1},
    )


class PiWorkerCallTests(unittest.TestCase):
    def test_round_trip_preserves_piworker_call_authority(self) -> None:
        call = PiWorkerCall.from_dict(piworker_call_payload())

        self.assertEqual(call.role, PiWorkerCallRole.EXECUTOR)
        self.assertEqual(PiWorkerCall.from_dict(call.to_dict()), call)
        self.assertEqual(call.call_id, "call-001")
        self.assertEqual(call.contract_id, "contract-001")
        self.assertEqual(call.objective, "Produce expected artifacts.")
        self.assertEqual(call.writable_refs, ["artifacts", "reports"])
        self.assertEqual(call.expected_output_refs, ["artifacts/final.md"])
        self.assertEqual(call.visible_refs.count("policy/permission_manifest.json"), 1)
        self.assertEqual(call.output_schema_ref, "schemas/agent_execution_report.json")
        self.assertEqual(call.validation_policy_ref, "validation/piworker_executor_policy.json")
        self.assertEqual(call.runtime_budget, {"max_turns": 4, "timeout_seconds": 300})

    def test_rejects_raw_payload_secret_and_authority_fields(self) -> None:
        payload = piworker_call_payload()
        payload["raw_prompt"] = "do the work"
        with self.assertRaises(ContractValidationError):
            PiWorkerCall.from_dict(payload)

        payload = piworker_call_payload()
        payload["metadata"] = {"secret_key": "not allowed"}
        with self.assertRaises(ContractValidationError):
            PiWorkerCall.from_dict(payload)

        payload = piworker_call_payload()
        payload["metadata"] = {"decision": "accepted"}
        with self.assertRaises(ContractValidationError):
            PiWorkerCall.from_dict(payload)

    def test_rejects_unsafe_refs_and_outputs_outside_writable_refs(self) -> None:
        payload = piworker_call_payload()
        payload["contract_ref"] = "../contract.json"
        with self.assertRaises(ContractValidationError):
            PiWorkerCall.from_dict(payload)

        payload = piworker_call_payload()
        payload["expected_output_refs"] = ["outside/final.md"]
        with self.assertRaisesRegex(ContractValidationError, "outside writable"):
            PiWorkerCall.from_dict(payload)

        payload = piworker_call_payload()
        payload["expected_output_refs"] = []
        with self.assertRaisesRegex(ContractValidationError, "expected_output_refs"):
            PiWorkerCall.from_dict(payload)

        payload = piworker_call_payload()
        payload["runtime_budget"] = {"max_turns": 0}
        with self.assertRaises(ContractValidationError):
            PiWorkerCall.from_dict(payload)

    def test_result_round_trip_and_call_binding(self) -> None:
        call = PiWorkerCall.from_dict(piworker_call_payload())
        result = PiWorkerCallResult.from_dict(piworker_call_result_payload())

        result.validate_against_call(call)

        self.assertEqual(result.status, PiWorkerCallResultStatus.COMPLETED)
        self.assertEqual(PiWorkerCallResult.from_dict(result.to_dict()), result)

    def test_result_from_worker_adapter_result_separates_outputs_from_runtime_refs(self) -> None:
        call = PiWorkerCall.from_dict(piworker_call_payload())

        result = PiWorkerCallResult.from_worker_adapter_result(
            call,
            worker_adapter_result(),
            validation_report_ref="attempts/call-001/piworker_call_validation.json",
        )

        self.assertEqual(result.result_id, "call-001-result")
        self.assertEqual(result.status, PiWorkerCallResultStatus.COMPLETED)
        self.assertEqual(result.output_refs, ["artifacts/final.md"])
        self.assertIn("attempts/call-001/pi_agent_output.json", result.runtime_refs)
        self.assertNotIn("artifacts/final.md", result.runtime_refs)
        self.assertEqual(result.metric_refs, ["attempts/call-001/pi_agent_metrics.json"])
        self.assertEqual(
            result.evidence_refs,
            ["evidence/adapter_event_001.json", "evidence/adapter_event_002.json"],
        )

    def test_result_rejects_completed_missing_expected_output(self) -> None:
        call = PiWorkerCall.from_dict(piworker_call_payload())
        payload = piworker_call_result_payload()
        payload["output_refs"] = []

        with self.assertRaisesRegex(ContractValidationError, "missing expected output"):
            PiWorkerCallResult.from_dict(payload).validate_against_call(call)

        with self.assertRaisesRegex(ContractValidationError, "missing expected output"):
            PiWorkerCallResult.from_worker_adapter_result(call, worker_adapter_result(produced_refs=[]))

    def test_result_rejects_output_outside_call_writable_refs(self) -> None:
        call = PiWorkerCall.from_dict(piworker_call_payload())
        payload = piworker_call_result_payload()
        payload["output_refs"] = ["outside/final.md"]

        with self.assertRaisesRegex(ContractValidationError, "outside writable"):
            PiWorkerCallResult.from_dict(payload).validate_against_call(call)

        with self.assertRaisesRegex(ContractValidationError, "outside writable"):
            PiWorkerCallResult.from_worker_adapter_result(
                call,
                worker_adapter_result(produced_refs=["outside/final.md"]),
            )

    def test_result_rejects_acceptance_authority(self) -> None:
        payload = piworker_call_result_payload()
        payload["status"] = "accepted"
        with self.assertRaises(ContractValidationError):
            PiWorkerCallResult.from_dict(payload)

        payload = piworker_call_result_payload()
        payload["metadata"] = {"decision": "accepted"}
        with self.assertRaises(ContractValidationError):
            PiWorkerCallResult.from_dict(payload)

        call = PiWorkerCall.from_dict(piworker_call_payload())
        with self.assertRaisesRegex(ContractValidationError, "acceptance authority"):
            PiWorkerCallResult.from_worker_adapter_result(call, worker_adapter_result(status="accepted"))


if __name__ == "__main__":
    unittest.main()
