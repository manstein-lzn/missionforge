from __future__ import annotations

import unittest

from missionforge.agent_packets import AgentExecutionPacket, JudgePacket
from missionforge.agentic_repair import TaskRevisionAuthority
from missionforge.agentic_repair_controller import RepairExecutionDirective
from missionforge.agentic_revision_controller import RevisionPendingRecord
from missionforge.contracts import ContractValidationError, stable_json_hash
from missionforge.piworker_call import (
    PIWORKER_CALL_RESULT_SCHEMA_VERSION,
    PIWORKER_CALL_SCHEMA_VERSION,
    PiWorkerCall,
    PiWorkerCallResult,
    PiWorkerCallResultStatus,
    PiWorkerCallRole,
)
from missionforge.work_unit import ExecutionReport, WorkerResult
from missionforge.workers import WorkerAdapterResult


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


def execution_packet() -> AgentExecutionPacket:
    return AgentExecutionPacket.from_dict(
        {
            "packet_id": "WU-000001",
            "schema_version": "agent_execution_packet.v1",
            "role": "executor_piworker",
            "contract_id": "contract-001",
            "contract_hash": HASH_A,
            "contract_ref": "contract/task_contract.json",
            "worker_brief_ref": "projections/worker_brief.json",
            "workspace_policy_ref": "policy/workspace_policy.json",
            "permission_manifest_ref": "policy/permission_manifest.json",
            "report_ref": "reports/execution_report.json",
            "expected_artifact_refs": ["artifacts/final.md"],
            "allowed_input_refs": ["contract/task_contract.json", "frontdesk/intent_bundle.json"],
            "writable_refs": ["artifacts", "reports"],
        }
    )


def judge_packet() -> JudgePacket:
    return JudgePacket.from_dict(
        {
            "packet_id": "judge-packet-001",
            "schema_version": "judge_packet.v1",
            "role": "judge_piworker",
            "contract_id": "contract-001",
            "contract_hash": HASH_A,
            "contract_ref": "contract/task_contract.json",
            "judge_rubric_ref": "projections/judge_rubric.json",
            "execution_packet_ref": "packets/execution_packet.json",
            "execution_report_ref": "reports/execution_report.json",
            "report_ref": "reports/judge_report.json",
            "hard_check_status": "passed",
            "artifact_refs": ["artifacts/final.md"],
            "evidence_refs": ["evidence/tool_events.jsonl"],
            "hard_check_refs": ["reports/hard_checks.json"],
        }
    )


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


def repair_directive() -> RepairExecutionDirective:
    repair_ticket_ref = "repairs/repair-ticket-001/repair_ticket.json"
    repair_ticket_hash = "sha256:" + "c" * 64
    directive_id = "repair-execution-" + stable_json_hash(
        {
            "schema_version": "repair_execution_directive.v1",
            "repair_ticket_ref": repair_ticket_ref,
            "repair_ticket_hash": repair_ticket_hash,
        }
    ).split(":", 1)[1]
    payload = {
        "schema_version": "repair_execution_directive.v1",
        "directive_id": directive_id,
        "run_id": "run-001",
        "contract_id": "contract-001",
        "contract_hash": HASH_A,
        "repair_ticket_ref": repair_ticket_ref,
        "repair_ticket_hash": repair_ticket_hash,
        "source_result_ref": "results/result-run-001.json",
        "source_repair_brief_ref": "repairs/repair-ticket-001/repair_brief.json",
        "worker_brief_ref": "projections/worker_brief.json",
        "execution_packet_ref": "repairs/repair-ticket-001/execution_packet.json",
        "execution_report_ref": "reports/repair_execution_report.json",
        "target_artifact_refs": ["artifacts/final.md"],
        "context_refs": [
            "repairs/repair-ticket-001/repair_ticket.json",
            "repairs/repair-ticket-001/repair_brief.json",
        ],
        "status": "ready",
    }
    payload["directive_hash"] = stable_json_hash(payload)
    return RepairExecutionDirective.from_dict(payload)


def revision_pending_record() -> RevisionPendingRecord:
    source_result_ref = "results/result-run-001.json"
    source_revision_request_ref = "revisions/revision-request-001/request.json"
    pending_id = "revision-pending-" + stable_json_hash(
        {
            "schema_version": "revision_pending_record.v1",
            "run_id": "run-001",
            "contract_hash": HASH_A,
            "source_result_ref": source_result_ref,
            "source_revision_request_ref": source_revision_request_ref,
        }
    ).split(":", 1)[1]
    payload = {
        "schema_version": "revision_pending_record.v1",
        "pending_id": pending_id,
        "run_id": "run-001",
        "contract_id": "contract-001",
        "contract_hash": HASH_A,
        "contract_ref": "contract/task_contract.json",
        "request_id": "revision-request-001",
        "source_result_ref": source_result_ref,
        "source_judge_report_ref": "reports/judge_report.json",
        "source_revision_request_ref": source_revision_request_ref,
        "execution_packet_ref": "packets/execution_packet.json",
        "execution_report_ref": "reports/execution_report.json",
        "judge_packet_ref": "packets/judge_packet.json",
        "judge_report_ref": "reports/judge_report.json",
        "authority_required": TaskRevisionAuthority.PRODUCT_INTEGRATION.value,
        "evidence_refs": ["reports/execution_report.json"],
        "status": "pending",
    }
    payload["pending_hash"] = stable_json_hash(payload)
    return RevisionPendingRecord.from_dict(payload)


def worker_adapter_result(*, status: str = "completed", produced_refs: list[str] | None = None) -> WorkerAdapterResult:
    safe_produced_refs = produced_refs if produced_refs is not None else ["artifacts/final.md"]
    report = ExecutionReport(
        report_id="R-call-001",
        work_unit_id="call-001",
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
    def test_round_trip_and_work_unit_projection(self) -> None:
        call = PiWorkerCall.from_dict(piworker_call_payload())

        self.assertEqual(call.role, PiWorkerCallRole.EXECUTOR)
        self.assertEqual(PiWorkerCall.from_dict(call.to_dict()), call)

        work_unit = call.to_work_unit_contract(
            exit_criteria=["Artifacts exist."],
            stop_conditions=["Runtime failed."],
        )
        self.assertEqual(work_unit.work_unit_id, "call-001")
        self.assertEqual(work_unit.mission_id, "contract-001")
        self.assertEqual(work_unit.next_objective, "Produce expected artifacts.")
        self.assertEqual(work_unit.allowed_scope, ["artifacts", "reports"])
        self.assertEqual(work_unit.expected_outputs, ["artifacts/final.md"])
        self.assertEqual(work_unit.visible_refs.count("policy/permission_manifest.json"), 1)
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

    def test_execution_packet_projection_binds_source_packet_hash(self) -> None:
        packet = execution_packet()

        call = PiWorkerCall.from_execution_packet(
            packet,
            packet_ref="packets/execution_packet.json",
        )

        self.assertEqual(call.call_id, "WU-000001")
        self.assertEqual(call.role, PiWorkerCallRole.EXECUTOR)
        self.assertEqual(call.source_packet_hash, stable_json_hash(packet.to_dict()))
        self.assertEqual(call.expected_output_refs, ["artifacts/final.md"])
        self.assertEqual(call.writable_refs, ["artifacts", "reports"])
        self.assertEqual(call.visible_refs.count("contract/task_contract.json"), 1)

    def test_judge_packet_projection_is_report_only_writable(self) -> None:
        packet = judge_packet()

        call = PiWorkerCall.from_judge_packet(
            packet,
            packet_ref="packets/judge_packet.json",
            spec_ref="attempts/judge-packet-001/judge_node_spec.json",
        )
        work_unit = call.to_work_unit_contract()

        self.assertEqual(call.role, PiWorkerCallRole.JUDGE)
        self.assertEqual(call.metadata, {"hard_check_status": "passed"})
        self.assertEqual(work_unit.allowed_scope, ["reports/judge_report.json"])
        self.assertEqual(work_unit.expected_outputs, ["reports/judge_report.json"])
        self.assertEqual(work_unit.visible_refs[0], "attempts/judge-packet-001/judge_node_spec.json")

    def test_repair_directive_projection_uses_same_piworker_call_boundary(self) -> None:
        directive = repair_directive()

        call = PiWorkerCall.from_repair_directive(
            directive,
            directive_ref="repairs/repair-ticket-001/repair_execution_directive.json",
            contract_ref="contract/task_contract.json",
            permission_manifest_ref="policy/permission_manifest.json",
            writable_refs=["artifacts", "reports"],
        )

        self.assertEqual(call.role, PiWorkerCallRole.REPAIR)
        self.assertEqual(call.contract_hash, HASH_A)
        self.assertEqual(call.expected_output_refs, ["artifacts/final.md"])
        self.assertEqual(call.source_packet_hash, stable_json_hash(directive.to_dict()))
        self.assertIn("repairs/repair-ticket-001/repair_brief.json", call.visible_refs)
        self.assertEqual(call.output_schema_ref, "schemas/agent_execution_report.json")
        self.assertEqual(call.validation_policy_ref, "validation/piworker_repair_policy.json")

    def test_revision_pending_projection_uses_same_piworker_call_boundary(self) -> None:
        pending = revision_pending_record()

        call = PiWorkerCall.from_revision_pending_record(
            pending,
            pending_ref="revisions/revision-request-001/revision_pending.json",
            permission_manifest_ref="policy/permission_manifest.json",
            writable_refs=["revisions/revision-request-001"],
            expected_output_ref="revisions/revision-request-001/revised_task_contract.json",
        )

        self.assertEqual(call.role, PiWorkerCallRole.REVISION_DRAFTER)
        self.assertEqual(call.contract_ref, "contract/task_contract.json")
        self.assertEqual(call.expected_output_refs, ["revisions/revision-request-001/revised_task_contract.json"])
        self.assertEqual(call.source_packet_hash, stable_json_hash(pending.to_dict()))
        self.assertIn("revisions/revision-request-001/request.json", call.visible_refs)
        self.assertEqual(call.metadata, {"authority_required": "product_integration"})
        self.assertEqual(call.output_schema_ref, "schemas/task_contract_revision_draft.json")
        self.assertEqual(call.validation_policy_ref, "validation/piworker_revision_policy.json")

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
