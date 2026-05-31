from __future__ import annotations

import unittest

from missionforge import (
    AgentRole,
    HardCheckStatus,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
    RepairBrief,
    TaskRevisionAuthority,
    TaskRevisionDecision,
    TaskRevisionDecisionStatus,
    TaskRevisionRequest,
    validate_repair_brief_for_judge,
    validate_revision_request_for_judge,
)
from missionforge.contracts import ContractValidationError


class AgenticRepairTests(unittest.TestCase):
    def test_repair_brief_round_trip(self) -> None:
        brief = RepairBrief(
            brief_id="repair-001",
            run_id="run-001",
            contract_id="contract-001",
            contract_hash="sha256:" + "1" * 64,
            contract_ref="contract/task_contract.json",
            judge_packet_ref="packets/judge_packet.json",
            judge_report_ref="reports/judge_report.json",
            execution_report_ref="reports/execution_report.json",
            reason="Need a small artifact repair.",
            repair_steps=["Adjust the final artifact to satisfy the rubric."],
            target_artifact_refs=["artifacts/final.md"],
            evidence_refs=["reports/execution_report.json"],
        )

        self.assertEqual(RepairBrief.from_dict(brief.to_dict()), brief)

    def test_repair_brief_rejects_unknown_fields(self) -> None:
        payload = RepairBrief(
            brief_id="repair-001",
            run_id="run-001",
            contract_id="contract-001",
            contract_hash="sha256:" + "1" * 64,
            contract_ref="contract/task_contract.json",
            judge_packet_ref="packets/judge_packet.json",
            judge_report_ref="reports/judge_report.json",
            execution_report_ref="reports/execution_report.json",
            reason="Need a small artifact repair.",
            repair_steps=["Adjust the final artifact to satisfy the rubric."],
            target_artifact_refs=["artifacts/final.md"],
            evidence_refs=["reports/execution_report.json"],
        ).to_dict()
        payload["revised_contract_ref"] = "contract/task_contract.v2.json"

        with self.assertRaises(ContractValidationError):
            RepairBrief.from_dict(payload)

    def test_revision_request_and_decision_round_trip(self) -> None:
        request = TaskRevisionRequest(
            request_id="revision-001",
            run_id="run-001",
            contract_id="contract-001",
            contract_hash="sha256:" + "2" * 64,
            contract_ref="contract/task_contract.json",
            judge_packet_ref="packets/judge_packet.json",
            judge_report_ref="reports/judge_report.json",
            execution_report_ref="reports/execution_report.json",
            reason="The contract is incomplete for the product boundary.",
            proposed_contract_changes=["Add a missing acceptance clause."],
            authority_required=TaskRevisionAuthority.PRODUCT_INTEGRATION,
            evidence_refs=["reports/execution_report.json"],
        )
        decision = TaskRevisionDecision(
            decision_id="revision-decision-001",
            request_ref="revisions/request.json",
            request_id=request.request_id,
            current_contract_ref=request.contract_ref,
            current_contract_hash=request.contract_hash,
            decision=TaskRevisionDecisionStatus.APPROVED,
            decided_by="operator",
            rationale_refs=["reports/judge_report.json"],
            revised_contract_ref="contract/task_contract.v2.json",
            revised_contract_hash="sha256:" + "3" * 64,
        )

        self.assertEqual(TaskRevisionRequest.from_dict(request.to_dict()), request)
        self.assertEqual(TaskRevisionDecision.from_dict(decision.to_dict()), decision)

    def test_revision_decision_requires_changed_hash_when_approved(self) -> None:
        with self.assertRaises(ContractValidationError):
            TaskRevisionDecision(
                decision_id="revision-decision-001",
                request_ref="revisions/request.json",
                request_id="revision-001",
                current_contract_ref="contract/task_contract.json",
                current_contract_hash="sha256:" + "2" * 64,
                decision=TaskRevisionDecisionStatus.APPROVED,
                decided_by="operator",
                revised_contract_ref="contract/task_contract.v2.json",
                revised_contract_hash="sha256:" + "2" * 64,
            ).validate()

    def test_repair_and_revision_helpers_bind_to_judge_packet_and_report(self) -> None:
        packet = JudgePacket(
            packet_id="judge-packet-001",
            contract_id="contract-001",
            contract_hash="sha256:" + "1" * 64,
            contract_ref="contract/task_contract.json",
            judge_rubric_ref="contract/judge_rubric.json",
            execution_packet_ref="packets/execution_packet.json",
            execution_report_ref="reports/execution_report.json",
            report_ref="reports/judge_report.json",
            hard_check_status=HardCheckStatus.PASSED,
            artifact_refs=["artifacts/final.md"],
            evidence_refs=["reports/execution_report.json"],
            hard_check_refs=["reports/hard_checks.json"],
            role=AgentRole.JUDGE,
        )
        repair_report = JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref="packets/judge_packet.json",
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.REPAIR,
            hard_check_status=HardCheckStatus.PASSED,
            rationale_refs=["reports/judge_rationale.md"],
            evidence_refs=["reports/execution_report.json"],
            repair_brief_ref="projections/repair_brief.json",
        )
        revision_report = JudgeReport(
            report_id="judge-report-002",
            packet_id=packet.packet_id,
            packet_ref="packets/judge_packet.json",
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.REVISION_REQUIRED,
            hard_check_status=HardCheckStatus.PASSED,
            rationale_refs=["reports/judge_rationale.md"],
            evidence_refs=["reports/execution_report.json"],
            revision_request_ref="revisions/request.json",
        )
        brief = RepairBrief(
            brief_id="repair-001",
            run_id="run-001",
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            judge_packet_ref=repair_report.packet_ref,
            judge_report_ref=packet.report_ref,
            execution_report_ref=packet.execution_report_ref,
            reason="Need a repair.",
            repair_steps=["Adjust the final artifact."],
            target_artifact_refs=packet.artifact_refs,
            evidence_refs=["reports/execution_report.json"],
        )
        request = TaskRevisionRequest(
            request_id="revision-001",
            run_id="run-001",
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            judge_packet_ref=revision_report.packet_ref,
            judge_report_ref=packet.report_ref,
            execution_report_ref=packet.execution_report_ref,
            reason="Need a revision.",
            proposed_contract_changes=["Clarify acceptance."],
            evidence_refs=["reports/execution_report.json"],
        )

        validate_repair_brief_for_judge(brief, packet, repair_report)
        validate_revision_request_for_judge(request, packet, revision_report)

    def test_repair_brief_rejects_foreign_run_id_and_unreviewed_artifacts(self) -> None:
        packet = JudgePacket(
            packet_id="judge-packet-001",
            contract_id="contract-001",
            contract_hash="sha256:" + "1" * 64,
            contract_ref="contract/task_contract.json",
            judge_rubric_ref="contract/judge_rubric.json",
            execution_packet_ref="packets/execution_packet.json",
            execution_report_ref="reports/execution_report.json",
            report_ref="reports/judge_report.json",
            hard_check_status=HardCheckStatus.PASSED,
            artifact_refs=["artifacts/final.md"],
            evidence_refs=["reports/execution_report.json"],
            hard_check_refs=["reports/hard_checks.json"],
            role=AgentRole.JUDGE,
        )
        report = JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref="packets/judge_packet.json",
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.REPAIR,
            hard_check_status=HardCheckStatus.PASSED,
            rationale_refs=["reports/judge_rationale.md"],
            evidence_refs=["reports/execution_report.json"],
            repair_brief_ref="projections/repair_brief.json",
        )
        brief = RepairBrief(
            brief_id="repair-001",
            run_id="foreign-run",
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            judge_packet_ref=report.packet_ref,
            judge_report_ref=packet.report_ref,
            execution_report_ref=packet.execution_report_ref,
            reason="Need a repair.",
            repair_steps=["Adjust the final artifact."],
            target_artifact_refs=["artifacts/not-reviewed.md"],
            evidence_refs=["reports/execution_report.json"],
        )

        with self.assertRaises(ContractValidationError):
            validate_repair_brief_for_judge(brief, packet, report, run_id="run-001")

        valid_brief = RepairBrief(
            brief_id="repair-001",
            run_id="run-001",
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            judge_packet_ref=report.packet_ref,
            judge_report_ref=packet.report_ref,
            execution_report_ref=packet.execution_report_ref,
            reason="Need a repair.",
            repair_steps=["Adjust the final artifact."],
            target_artifact_refs=["artifacts/not-reviewed.md"],
            evidence_refs=["reports/execution_report.json"],
        )

        with self.assertRaises(ContractValidationError):
            validate_repair_brief_for_judge(valid_brief, packet, report, run_id="run-001")

    def test_revision_decision_rejects_non_string_revised_refs(self) -> None:
        payload = TaskRevisionDecision(
            decision_id="revision-decision-001",
            request_ref="revisions/request.json",
            request_id="revision-001",
            current_contract_ref="contract/task_contract.json",
            current_contract_hash="sha256:" + "2" * 64,
            decision=TaskRevisionDecisionStatus.APPROVED,
            decided_by="operator",
            revised_contract_ref="contract/task_contract.v2.json",
            revised_contract_hash="sha256:" + "3" * 64,
        ).to_dict()
        payload["revised_contract_ref"] = 123

        with self.assertRaises(ContractValidationError):
            TaskRevisionDecision.from_dict(payload)

    def test_revision_request_rejects_foreign_run_id(self) -> None:
        packet = JudgePacket(
            packet_id="judge-packet-001",
            contract_id="contract-001",
            contract_hash="sha256:" + "1" * 64,
            contract_ref="contract/task_contract.json",
            judge_rubric_ref="contract/judge_rubric.json",
            execution_packet_ref="packets/execution_packet.json",
            execution_report_ref="reports/execution_report.json",
            report_ref="reports/judge_report.json",
            hard_check_status=HardCheckStatus.PASSED,
            artifact_refs=["artifacts/final.md"],
            evidence_refs=["reports/execution_report.json"],
            hard_check_refs=["reports/hard_checks.json"],
            role=AgentRole.JUDGE,
        )
        report = JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref="packets/judge_packet.json",
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.REVISION_REQUIRED,
            hard_check_status=HardCheckStatus.PASSED,
            rationale_refs=["reports/judge_rationale.md"],
            evidence_refs=["reports/execution_report.json"],
            revision_request_ref="revisions/request.json",
        )
        request = TaskRevisionRequest(
            request_id="revision-001",
            run_id="foreign-run",
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            judge_packet_ref=report.packet_ref,
            judge_report_ref=packet.report_ref,
            execution_report_ref=packet.execution_report_ref,
            reason="Need a revision.",
            proposed_contract_changes=["Clarify acceptance."],
            evidence_refs=["reports/execution_report.json"],
        )

        with self.assertRaises(ContractValidationError):
            validate_revision_request_for_judge(request, packet, report, run_id="run-001")


if __name__ == "__main__":
    unittest.main()
