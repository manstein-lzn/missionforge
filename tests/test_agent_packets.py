from __future__ import annotations

import unittest

from missionforge.agent_packets import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    AgentRole,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
    validate_execution_report_for_packet,
    validate_judge_packet_for_execution,
    validate_judge_report_for_packet,
)
from missionforge.contracts import ContractValidationError, stable_json_hash


def execution_packet_payload() -> dict[str, object]:
    return {
        "packet_id": "exec-packet-001",
        "schema_version": "agent_execution_packet.v1",
        "role": "executor_piworker",
        "contract_id": "contract-001",
        "contract_hash": "sha256:" + "a" * 64,
        "contract_ref": "contract/task_contract.json",
        "worker_brief_ref": "projections/worker_brief.json",
        "workspace_policy_ref": "policy/workspace_policy.json",
        "permission_manifest_ref": "policy/permission_manifest.json",
        "report_ref": "reports/execution_report.json",
        "expected_artifact_refs": ["artifacts/final.md"],
        "allowed_input_refs": ["frontdesk/intent_bundle.json"],
        "writable_refs": ["artifacts"],
    }


def execution_report_payload() -> dict[str, object]:
    return {
        "report_id": "exec-report-001",
        "schema_version": "agent_execution_report.v1",
        "role": "executor_piworker",
        "packet_id": "exec-packet-001",
        "packet_ref": "packets/execution_packet.json",
        "contract_id": "contract-001",
        "contract_hash": "sha256:" + "a" * 64,
        "contract_ref": "contract/task_contract.json",
        "status": "completed",
        "produced_artifact_refs": ["artifacts/final.md"],
        "changed_refs": ["artifacts/final.md"],
        "evidence_refs": ["reports/tool_events.jsonl"],
        "metric_refs": ["ledgers/metrics.jsonl"],
    }


def judge_packet_payload() -> dict[str, object]:
    return {
        "packet_id": "judge-packet-001",
        "schema_version": "judge_packet.v1",
        "role": "judge_piworker",
        "contract_id": "contract-001",
        "contract_hash": "sha256:" + "a" * 64,
        "contract_ref": "contract/task_contract.json",
        "judge_rubric_ref": "projections/judge_rubric.json",
        "execution_packet_ref": "packets/execution_packet.json",
        "execution_report_ref": "reports/execution_report.json",
        "report_ref": "reports/judge_report.json",
        "hard_check_status": "passed",
        "artifact_refs": ["artifacts/final.md"],
        "evidence_refs": ["reports/tool_events.jsonl"],
        "hard_check_refs": ["reports/hard_checks.json"],
    }


def judge_report_payload(decision: str = "accepted") -> dict[str, object]:
    return {
        "report_id": "judge-report-001",
        "schema_version": "judge_report.v1",
        "role": "judge_piworker",
        "packet_id": "judge-packet-001",
        "packet_ref": "packets/judge_packet.json",
        "contract_id": "contract-001",
        "contract_hash": "sha256:" + "a" * 64,
        "contract_ref": "contract/task_contract.json",
        "decision": decision,
        "hard_check_status": "passed",
        "rationale_refs": ["reports/judge_rationale.md"],
        "evidence_refs": ["reports/execution_report.json"],
        "accepted_artifact_refs": ["artifacts/final.md"],
    }


class AgentPacketTests(unittest.TestCase):
    def test_execution_packet_round_trip(self) -> None:
        packet = AgentExecutionPacket.from_dict(execution_packet_payload())

        self.assertEqual(packet.role, AgentRole.EXECUTOR)
        self.assertEqual(AgentExecutionPacket.from_dict(packet.to_dict()), packet)

    def test_execution_packet_rejects_judge_role_and_unsafe_refs(self) -> None:
        payload = execution_packet_payload()
        payload["role"] = "judge_piworker"
        with self.assertRaises(ContractValidationError):
            AgentExecutionPacket.from_dict(payload)

        payload = execution_packet_payload()
        payload["semantic_acceptance"] = []
        with self.assertRaises(ContractValidationError):
            AgentExecutionPacket.from_dict(payload)

        payload = execution_packet_payload()
        payload["contract_hash"] = "not-a-hash"
        with self.assertRaises(ContractValidationError):
            AgentExecutionPacket.from_dict(payload)

        payload = execution_packet_payload()
        payload["worker_brief_ref"] = "../brief.json"
        with self.assertRaises(ContractValidationError):
            AgentExecutionPacket.from_dict(payload)

        payload = execution_packet_payload()
        payload["expected_artifact_refs"] = ["reports/final.md"]
        with self.assertRaises(ContractValidationError):
            AgentExecutionPacket.from_dict(payload)

    def test_execution_report_round_trip_without_acceptance_authority(self) -> None:
        report = AgentExecutionReport.from_dict(execution_report_payload())

        self.assertEqual(report.status, AgentExecutionStatus.COMPLETED)
        self.assertEqual(AgentExecutionReport.from_dict(report.to_dict()), report)

    def test_execution_report_rejects_self_acceptance(self) -> None:
        payload = execution_report_payload()
        payload["decision"] = "accepted"
        with self.assertRaises(ContractValidationError):
            AgentExecutionReport.from_dict(payload)

        payload = execution_report_payload()
        payload["status"] = "accepted"
        with self.assertRaises(ContractValidationError):
            AgentExecutionReport.from_dict(payload)

    def test_execution_report_rejects_raw_payload_fields(self) -> None:
        payload = execution_report_payload()
        payload["raw_transcript"] = "not allowed"
        with self.assertRaises(ContractValidationError):
            AgentExecutionReport.from_dict(payload)

    def test_execution_report_binds_to_execution_packet(self) -> None:
        packet = AgentExecutionPacket.from_dict(execution_packet_payload())
        report = AgentExecutionReport.from_dict(execution_report_payload())

        validate_execution_report_for_packet(
            report,
            packet,
            packet_ref="packets/execution_packet.json",
        )

        bad_payload = execution_report_payload()
        bad_payload["contract_hash"] = "sha256:" + "b" * 64
        bad_report = AgentExecutionReport.from_dict(bad_payload)
        with self.assertRaises(ContractValidationError):
            validate_execution_report_for_packet(
                bad_report,
                packet,
                packet_ref="packets/execution_packet.json",
            )

        packet_hash = stable_json_hash(packet.to_dict())
        hash_payload = execution_report_payload()
        hash_payload["packet_hash"] = packet_hash
        hash_bound_report = AgentExecutionReport.from_dict(hash_payload)
        validate_execution_report_for_packet(
            hash_bound_report,
            packet,
            packet_ref="packets/execution_packet.json",
            packet_hash=packet_hash,
        )

        bad_hash_payload = execution_report_payload()
        bad_hash_payload["packet_hash"] = "sha256:" + "b" * 64
        bad_hash_report = AgentExecutionReport.from_dict(bad_hash_payload)
        with self.assertRaisesRegex(ContractValidationError, "packet_hash"):
            validate_execution_report_for_packet(
                bad_hash_report,
                packet,
                packet_ref="packets/execution_packet.json",
                packet_hash=packet_hash,
            )
    def test_judge_packet_round_trip(self) -> None:
        packet = JudgePacket.from_dict(judge_packet_payload())

        self.assertEqual(packet.role, AgentRole.JUDGE)
        self.assertEqual(JudgePacket.from_dict(packet.to_dict()), packet)

    def test_judge_packet_rejects_unknown_fields(self) -> None:
        payload = judge_packet_payload()
        payload["raw_rationale"] = "not allowed"

        with self.assertRaises(ContractValidationError):
            JudgePacket.from_dict(payload)

    def test_judge_report_acceptance_round_trip(self) -> None:
        report = JudgeReport.from_dict(judge_report_payload())

        self.assertEqual(report.decision, JudgeReportDecision.ACCEPTED)
        self.assertEqual(JudgeReport.from_dict(report.to_dict()), report)

    def test_judge_report_repair_requires_repair_brief_ref(self) -> None:
        payload = judge_report_payload("repair")
        payload["accepted_artifact_refs"] = []
        with self.assertRaises(ContractValidationError):
            JudgeReport.from_dict(payload)

        payload["repair_brief_ref"] = "projections/repair_brief.md"
        report = JudgeReport.from_dict(payload)
        self.assertEqual(report.decision, JudgeReportDecision.REPAIR)

    def test_judge_report_revision_requires_revision_request_ref(self) -> None:
        payload = judge_report_payload("revision_required")
        payload["accepted_artifact_refs"] = []
        with self.assertRaises(ContractValidationError):
            JudgeReport.from_dict(payload)

        payload["revision_request_ref"] = "revisions/request.json"
        report = JudgeReport.from_dict(payload)
        self.assertEqual(report.decision, JudgeReportDecision.REVISION_REQUIRED)

    def test_judge_report_accepted_rejects_repair_or_revision_refs(self) -> None:
        payload = judge_report_payload("accepted")
        payload["repair_brief_ref"] = "projections/repair_brief.md"

        with self.assertRaises(ContractValidationError):
            JudgeReport.from_dict(payload)

    def test_judge_report_accepted_requires_passed_hard_checks(self) -> None:
        payload = judge_report_payload("accepted")
        payload["hard_check_status"] = "failed"

        with self.assertRaises(ContractValidationError):
            JudgeReport.from_dict(payload)

    def test_judge_report_binds_to_packet_and_artifact_refs(self) -> None:
        packet = JudgePacket.from_dict(judge_packet_payload())
        report = JudgeReport.from_dict(judge_report_payload())

        validate_judge_report_for_packet(
            report,
            packet,
            packet_ref="packets/judge_packet.json",
        )

        bad_payload = judge_report_payload()
        bad_payload["accepted_artifact_refs"] = ["frontdesk/intent_bundle.json"]
        bad_report = JudgeReport.from_dict(bad_payload)
        with self.assertRaises(ContractValidationError):
            validate_judge_report_for_packet(
                bad_report,
                packet,
                packet_ref="packets/judge_packet.json",
            )

        bad_payload = judge_report_payload()
        bad_payload["packet_ref"] = "packets/other_judge_packet.json"
        bad_report = JudgeReport.from_dict(bad_payload)
        with self.assertRaises(ContractValidationError):
            validate_judge_report_for_packet(
                bad_report,
                packet,
                packet_ref="packets/judge_packet.json",
            )

        failed_packet_payload = judge_packet_payload()
        failed_packet_payload["hard_check_status"] = "failed"
        failed_packet = JudgePacket.from_dict(failed_packet_payload)
        with self.assertRaises(ContractValidationError):
            validate_judge_report_for_packet(
                report,
                failed_packet,
                packet_ref="packets/judge_packet.json",
            )

        packet_hash = stable_json_hash(packet.to_dict())
        hash_payload = judge_report_payload()
        hash_payload["packet_hash"] = packet_hash
        hash_bound_report = JudgeReport.from_dict(hash_payload)
        validate_judge_report_for_packet(
            hash_bound_report,
            packet,
            packet_ref="packets/judge_packet.json",
            packet_hash=packet_hash,
        )

        bad_hash_payload = judge_report_payload()
        bad_hash_payload["packet_hash"] = "sha256:" + "b" * 64
        bad_hash_report = JudgeReport.from_dict(bad_hash_payload)
        with self.assertRaisesRegex(ContractValidationError, "packet_hash"):
            validate_judge_report_for_packet(
                bad_hash_report,
                packet,
                packet_ref="packets/judge_packet.json",
                packet_hash=packet_hash,
            )

    def test_judge_packet_binds_to_execution_packet_and_report_artifacts(self) -> None:
        execution_packet = AgentExecutionPacket.from_dict(execution_packet_payload())
        execution_report = AgentExecutionReport.from_dict(execution_report_payload())
        judge_packet = JudgePacket.from_dict(judge_packet_payload())

        validate_judge_packet_for_execution(
            judge_packet,
            execution_packet,
            execution_report,
            execution_packet_ref="packets/execution_packet.json",
            execution_report_ref="reports/execution_report.json",
        )

        bad_packet_payload = judge_packet_payload()
        bad_packet_payload["artifact_refs"] = ["frontdesk/intent_bundle.json"]
        bad_packet = JudgePacket.from_dict(bad_packet_payload)
        with self.assertRaises(ContractValidationError):
            validate_judge_packet_for_execution(
                bad_packet,
                execution_packet,
                execution_report,
                execution_packet_ref="packets/execution_packet.json",
                execution_report_ref="reports/execution_report.json",
            )

        bad_packet_payload = judge_packet_payload()
        bad_packet_payload["execution_report_ref"] = "reports/other_execution_report.json"
        bad_packet = JudgePacket.from_dict(bad_packet_payload)
        with self.assertRaises(ContractValidationError):
            validate_judge_packet_for_execution(
                bad_packet,
                execution_packet,
                execution_report,
                execution_packet_ref="packets/execution_packet.json",
                execution_report_ref="reports/execution_report.json",
            )

        execution_packet_hash = stable_json_hash(execution_packet.to_dict())
        execution_report_hash = stable_json_hash(execution_report.to_dict())
        hash_packet_payload = judge_packet_payload()
        hash_packet_payload["execution_packet_hash"] = execution_packet_hash
        hash_packet_payload["execution_report_hash"] = execution_report_hash
        hash_bound_packet = JudgePacket.from_dict(hash_packet_payload)
        validate_judge_packet_for_execution(
            hash_bound_packet,
            execution_packet,
            execution_report,
            execution_packet_ref="packets/execution_packet.json",
            execution_report_ref="reports/execution_report.json",
            execution_packet_hash=execution_packet_hash,
            execution_report_hash=execution_report_hash,
        )

        bad_hash_packet_payload = judge_packet_payload()
        bad_hash_packet_payload["execution_packet_hash"] = "sha256:" + "b" * 64
        bad_hash_packet = JudgePacket.from_dict(bad_hash_packet_payload)
        with self.assertRaisesRegex(ContractValidationError, "execution_packet_hash"):
            validate_judge_packet_for_execution(
                bad_hash_packet,
                execution_packet,
                execution_report,
                execution_packet_ref="packets/execution_packet.json",
                execution_report_ref="reports/execution_report.json",
                execution_packet_hash=execution_packet_hash,
                execution_report_hash=execution_report_hash,
            )

if __name__ == "__main__":
    unittest.main()
