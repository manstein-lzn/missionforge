from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    AgentWorkspace,
    AgenticFlowRunner,
    AgenticFlowStatus,
    ContractValidationError,
    HardCheckStatus,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
    PermissionManifest,
    RepairBrief,
    RepairTicket,
    RepairTicketStatus,
    RunWorkspace,
    TaskContract,
    WorkspacePolicy,
    build_repair_ticket,
    stable_json_hash,
)


def sample_contract() -> TaskContract:
    return TaskContract.from_dict(
        {
            "schema_version": "task_contract.v1",
            "contract_id": "contract-001",
            "product_id": "product.generic",
            "objective": "Produce the requested deliverable inside the declared workspace.",
            "background": "Compiled by product integration.",
            "users_or_audience": ["operator"],
            "non_goals": ["Do not change unrelated files."],
            "assumptions": ["Inputs are available by ref."],
            "required_outputs": [
                {
                    "output_id": "out-001",
                    "description": "Write the declared final artifact.",
                    "artifact_refs": ["artifacts/final.md"],
                }
            ],
            "hard_constraints": [
                {
                    "constraint_id": "hc-001",
                    "statement": "Stay inside declared writable roots.",
                    "source_refs": ["policy/permission_manifest.json"],
                }
            ],
            "semantic_acceptance": [
                {
                    "criterion_id": "acc-001",
                    "statement": "The artifact satisfies the frozen task objective.",
                    "evidence_refs": ["reports/execution_report.json"],
                }
            ],
            "risk_notes": ["Ask for explicit revision if the contract is wrong."],
            "source_refs": ["frontdesk/intent_bundle.json"],
            "workspace_policy_ref": "policy/workspace_policy.json",
            "permission_manifest_ref": "policy/permission_manifest.json",
            "judge_rubric_ref": "projections/judge_rubric.json",
            "revision_policy": {"mode": "explicit_revision_required"},
            "created_by": "product.integration",
            "created_at": "2026-05-31T00:00:00Z",
        }
    )


def sample_workspace_policy() -> WorkspacePolicy:
    return WorkspacePolicy.from_dict(
        {
            "policy_id": "workspace-001",
            "workspace_root_ref": "runs/run-001",
            "input_refs": ["frontdesk"],
            "artifact_root_refs": ["artifacts"],
            "scratch_root_refs": ["scratch"],
            "denied_refs": ["secrets"],
        }
    )


def worker_permission_manifest() -> PermissionManifest:
    return PermissionManifest.from_dict(
        {
            "manifest_id": "perm-worker",
            "workspace_policy_ref": "policy/workspace_policy.json",
            "readable_refs": ["frontdesk", "policy", "contract"],
            "writable_refs": ["artifacts", "reports", "ledgers"],
            "denied_refs": ["secrets"],
            "network_policy": "disabled",
        }
    )


def controller_permission_manifest() -> PermissionManifest:
    return PermissionManifest.from_dict(
        {
            "manifest_id": "perm-controller",
            "workspace_policy_ref": "policy/workspace_policy.json",
            "readable_refs": [
                "artifacts",
                "contract",
                "ledgers",
                "packets",
                "policy",
                "projections",
                "reports",
                "repairs",
                "results",
            ],
            "writable_refs": ["repairs", "results", "reports", "projections"],
            "denied_refs": ["secrets"],
            "network_policy": "disabled",
        }
    )


class CompletingExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        workspace.write_text("artifacts/final.md", "deliverable")
        workspace.write_text("reports/executor_evidence.md", "execution evidence")
        return AgentExecutionReport(
            report_id="execution-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.COMPLETED,
            produced_artifact_refs=["artifacts/final.md"],
            changed_refs=["artifacts/final.md"],
            evidence_refs=["reports/executor_evidence.md"],
        )


class RepairJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        repair_brief_ref = "projections/repair_brief.json"
        workspace.write_json(
            repair_brief_ref,
            RepairBrief(
                brief_id="repair-brief-001",
                run_id="run-001",
                contract_id=packet.contract_id,
                contract_hash=packet.contract_hash,
                contract_ref=packet.contract_ref,
                judge_packet_ref=packet_ref,
                judge_report_ref=packet.report_ref,
                execution_report_ref=packet.execution_report_ref,
                reason="Artifact needs a targeted repair while preserving the frozen contract.",
                repair_steps=["Update the produced artifact to satisfy the judge rubric."],
                target_artifact_refs=list(packet.artifact_refs),
                evidence_refs=[packet.execution_report_ref],
            ).to_dict(),
        )
        return JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.REPAIR,
            hard_check_status=packet.hard_check_status,
            evidence_refs=[packet.execution_report_ref],
            repair_brief_ref=repair_brief_ref,
        )


class AgenticRepairControllerTests(unittest.TestCase):
    def test_build_repair_ticket_snapshots_result_and_writes_refs_only_ticket(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)

            ticket = build_repair_ticket(
                contract=contract,
                result=result,
                repair_brief=brief,
                judge_packet=packet,
                judge_report=report,
                workspace=workspace,
            )

            self.assertEqual(ticket.status, RepairTicketStatus.READY)
            self.assertEqual(ticket.run_id, result.run_id)
            self.assertEqual(ticket.contract_hash, contract.contract_hash)
            self.assertEqual(ticket.source_judge_report_ref, result.refs.judge_report_ref)
            self.assertEqual(ticket.source_repair_brief_ref, result.repair_brief_ref)
            self.assertEqual(ticket.worker_brief_ref, result.refs.worker_brief_ref)
            self.assertNotEqual(ticket.source_result_ref, result.refs.checkpoint_ref)
            self.assertTrue(ticket.source_result_ref.startswith("results/result-"))

            ticket_ref = f"repairs/{ticket.ticket_id}/repair_ticket.json"
            payload = workspace.read_json(ticket_ref)
            self.assertEqual(RepairTicket.from_dict(payload), ticket)
            self.assertNotIn("reason", payload)
            self.assertNotIn("repair_steps", payload)
            self.assertNotIn("raw_transcript", json.dumps(payload, sort_keys=True))
            self.assertEqual(workspace.read_json(ticket.source_result_ref), result.to_dict())

    def test_build_repair_ticket_rejects_non_repair_result(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)
            accepted_result = replace(
                result,
                status=AgenticFlowStatus.ACCEPTED,
                judge_decision=JudgeReportDecision.ACCEPTED,
            )

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=accepted_result,
                    repair_brief=brief,
                    judge_packet=packet,
                    judge_report=report,
                    workspace=workspace,
                )

            for non_repair_result in (
                replace(
                    result,
                    status=AgenticFlowStatus.REVISION_REQUIRED,
                    judge_decision=JudgeReportDecision.REVISION_REQUIRED,
                    repair_brief_ref=None,
                    revision_request_ref="revisions/request.json",
                ),
                replace(
                    result,
                    status=AgenticFlowStatus.REJECTED,
                    judge_decision=JudgeReportDecision.REJECTED,
                    repair_brief_ref=None,
                ),
            ):
                with self.assertRaises(ContractValidationError):
                    build_repair_ticket(
                        contract=contract,
                        result=non_repair_result,
                        repair_brief=brief,
                        judge_packet=packet,
                        judge_report=report,
                        workspace=workspace,
                    )

    def test_build_repair_ticket_revalidates_foreign_run_and_unreviewed_target(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=replace(brief, run_id="foreign-run"),
                    judge_packet=packet,
                    judge_report=report,
                    workspace=workspace,
                )

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=replace(brief, target_artifact_refs=["artifacts/not-reviewed.md"]),
                    judge_packet=packet,
                    judge_report=report,
                    workspace=workspace,
                )

    def test_build_repair_ticket_rejects_mutable_checkpoint_source_ref(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=brief,
                    judge_packet=packet,
                    judge_report=report,
                    workspace=workspace,
                    source_result_ref=result.refs.checkpoint_ref,
                )

    def test_build_repair_ticket_rejects_ref_content_drift(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)
            workspace.write_json(
                result.refs.judge_report_ref,
                replace(report, report_id="judge-report-drifted").to_dict(),
            )

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=brief,
                    judge_packet=packet,
                    judge_report=report,
                    workspace=workspace,
                )

    def test_build_repair_ticket_rejects_cross_ref_binding_drift(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)
            drifted_report = replace(report, repair_brief_ref="projections/other_repair_brief.json")
            workspace.write_json(result.refs.judge_report_ref, drifted_report.to_dict())

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=brief,
                    judge_packet=packet,
                    judge_report=drifted_report,
                    workspace=workspace,
                )

        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)
            drifted_packet = replace(packet, execution_packet_ref="packets/other_execution_packet.json")
            _force_write_json(workspace, result.refs.judge_packet_ref, drifted_packet.to_dict())

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=brief,
                    judge_packet=drifted_packet,
                    judge_report=report,
                    workspace=workspace,
                )

    def test_build_repair_ticket_rejects_worker_and_execution_packet_drift(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)
            worker_payload = workspace.read_json(result.refs.worker_brief_ref)
            worker_payload["contract_hash"] = "sha256:" + "0" * 64
            workspace.write_json(result.refs.worker_brief_ref, worker_payload)

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=brief,
                    judge_packet=packet,
                    judge_report=report,
                    workspace=workspace,
                )

        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)
            execution_packet_payload = workspace.read_json(result.refs.execution_packet_ref)
            execution_packet_payload["worker_brief_ref"] = "projections/other_worker_brief.json"
            _force_write_json(workspace, result.refs.execution_packet_ref, execution_packet_payload)

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=brief,
                    judge_packet=packet,
                    judge_report=report,
                    workspace=workspace,
                )

    def test_build_repair_ticket_rejects_supplied_immutable_result_ref_mismatch(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)
            workspace.write_json(
                "results/manual-result.json",
                replace(
                    result,
                    status=AgenticFlowStatus.REJECTED,
                    judge_decision=JudgeReportDecision.REJECTED,
                    repair_brief_ref=None,
                ).to_dict(),
            )

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=brief,
                    judge_packet=packet,
                    judge_report=report,
                    workspace=workspace,
                    source_result_ref="results/manual-result.json",
                )

    def test_build_repair_ticket_is_replay_safe_and_rejects_conflict(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)

            first = build_repair_ticket(
                contract=contract,
                result=result,
                repair_brief=brief,
                judge_packet=packet,
                judge_report=report,
                workspace=workspace,
            )
            second = build_repair_ticket(
                contract=contract,
                result=result,
                repair_brief=brief,
                judge_packet=packet,
                judge_report=report,
                workspace=workspace,
            )
            self.assertEqual(second, first)

            ticket_ref = f"repairs/{first.ticket_id}/repair_ticket.json"
            conflicted_payload = first.to_dict()
            conflicted_payload["evidence_refs"] = []
            conflicted_payload["ticket_hash"] = stable_json_hash(
                {key: value for key, value in conflicted_payload.items() if key != "ticket_hash"}
            )
            workspace.write_json(ticket_ref, conflicted_payload)

            with self.assertRaises(ContractValidationError):
                build_repair_ticket(
                    contract=contract,
                    result=result,
                    repair_brief=brief,
                    judge_packet=packet,
                    judge_report=report,
                    workspace=workspace,
                )

    def test_repair_ticket_schema_rejects_mutable_source_and_wrong_deterministic_id(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result, workspace = _repair_flow(tmpdir)
            contract, brief, packet, report = _repair_inputs(workspace, result)
            ticket = build_repair_ticket(
                contract=contract,
                result=result,
                repair_brief=brief,
                judge_packet=packet,
                judge_report=report,
                workspace=workspace,
            )

            mutable_source_payload = ticket.to_dict()
            mutable_source_payload["source_result_ref"] = "checkpoints/latest.json"
            mutable_source_payload["ticket_hash"] = stable_json_hash(
                {key: value for key, value in mutable_source_payload.items() if key != "ticket_hash"}
            )
            with self.assertRaises(ContractValidationError):
                RepairTicket.from_dict(mutable_source_payload)

            wrong_id_payload = ticket.to_dict()
            wrong_id_payload["ticket_id"] = "repair-" + "0" * 64
            wrong_id_payload["ticket_hash"] = stable_json_hash(
                {key: value for key, value in wrong_id_payload.items() if key != "ticket_hash"}
            )
            with self.assertRaises(ContractValidationError):
                RepairTicket.from_dict(wrong_id_payload)


def _repair_flow(tmpdir: str) -> tuple[object, RunWorkspace]:
    _write_hard_check(tmpdir)
    result = AgenticFlowRunner(tmpdir, now=lambda: "2026-05-31T00:00:00Z").run(
        run_id="run-001",
        contract=sample_contract(),
        workspace_policy=sample_workspace_policy(),
        permission_manifest=worker_permission_manifest(),
        executor=CompletingExecutor(),
        judge=RepairJudge(),
        hard_check_status=HardCheckStatus.PASSED,
        hard_check_refs=["reports/hard_checks.json"],
    )
    workspace = RunWorkspace(
        tmpdir,
        sample_workspace_policy(),
        controller_permission_manifest(),
    )
    return result, workspace


def _repair_inputs(workspace: RunWorkspace, result: object) -> tuple[TaskContract, RepairBrief, JudgePacket, JudgeReport]:
    assert hasattr(result, "refs")
    assert hasattr(result, "repair_brief_ref")
    contract = TaskContract.from_dict(workspace.read_json(result.refs.contract_ref))
    brief = RepairBrief.from_dict(workspace.read_json(result.repair_brief_ref))
    packet = JudgePacket.from_dict(workspace.read_json(result.refs.judge_packet_ref))
    report = JudgeReport.from_dict(workspace.read_json(result.refs.judge_report_ref))
    return contract, brief, packet, report


def _write_hard_check(tmpdir: str) -> None:
    path = Path(tmpdir) / "runs/run-001/reports/hard_checks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"status": "passed"}\n', encoding="utf-8")


def _force_write_json(workspace: RunWorkspace, ref: str, payload: dict[str, object]) -> None:
    path = workspace.resolve_ref(ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
