"""Repair-ticket controller for TaskContract agentic flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from typing import Any, Mapping

from .agent_packets import (
    AgentExecutionPacket,
    AgentExecutionReport,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
    validate_judge_packet_for_execution,
)
from .agentic_flow import AgenticFlowResult, AgenticFlowStatus
from .agentic_repair import RepairBrief, validate_repair_brief_for_judge
from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from .task_contract import TaskContract
from .task_projection import WorkerBrief
from .workspace_runtime import RunWorkspace


REPAIR_TICKET_SCHEMA_VERSION = "repair_ticket.v1"
REPAIR_EXECUTION_DIRECTIVE_SCHEMA_VERSION = "repair_execution_directive.v1"


class RepairTicketStatus(StrEnum):
    """Durable lifecycle state for the first repair-controller slice."""

    READY = "ready"


class RepairExecutionDirectiveStatus(StrEnum):
    """Durable lifecycle state for a prepared repair execution directive."""

    READY = "ready"


@dataclass(frozen=True)
class RepairTicket:
    """Refs-only directive for the next repair execution attempt."""

    ticket_id: str
    ticket_hash: str
    run_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    source_result_ref: str
    source_judge_report_ref: str
    source_repair_brief_ref: str
    execution_packet_ref: str
    execution_report_ref: str
    judge_packet_ref: str
    judge_report_ref: str
    target_artifact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    worker_brief_ref: str = ""
    status: RepairTicketStatus = RepairTicketStatus.READY
    schema_version: str = REPAIR_TICKET_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairTicket":
        data = _strict_mapping(
            payload,
            "repair_ticket",
            {
                "schema_version",
                "ticket_id",
                "ticket_hash",
                "run_id",
                "contract_id",
                "contract_hash",
                "contract_ref",
                "source_result_ref",
                "source_judge_report_ref",
                "source_repair_brief_ref",
                "execution_packet_ref",
                "execution_report_ref",
                "judge_packet_ref",
                "judge_report_ref",
                "target_artifact_refs",
                "evidence_refs",
                "worker_brief_ref",
                "status",
            },
        )
        ticket = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", REPAIR_TICKET_SCHEMA_VERSION),
                "repair_ticket.schema_version",
            ),
            ticket_id=_validate_id(data.get("ticket_id"), "repair_ticket.ticket_id"),
            ticket_hash=_validate_hash(data.get("ticket_hash"), "repair_ticket.ticket_hash"),
            run_id=require_non_empty_str(data.get("run_id"), "repair_ticket.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "repair_ticket.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "repair_ticket.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "repair_ticket.contract_ref"),
            source_result_ref=validate_ref(data.get("source_result_ref"), "repair_ticket.source_result_ref"),
            source_judge_report_ref=validate_ref(
                data.get("source_judge_report_ref"),
                "repair_ticket.source_judge_report_ref",
            ),
            source_repair_brief_ref=validate_ref(
                data.get("source_repair_brief_ref"),
                "repair_ticket.source_repair_brief_ref",
            ),
            execution_packet_ref=validate_ref(data.get("execution_packet_ref"), "repair_ticket.execution_packet_ref"),
            execution_report_ref=validate_ref(data.get("execution_report_ref"), "repair_ticket.execution_report_ref"),
            judge_packet_ref=validate_ref(data.get("judge_packet_ref"), "repair_ticket.judge_packet_ref"),
            judge_report_ref=validate_ref(data.get("judge_report_ref"), "repair_ticket.judge_report_ref"),
            target_artifact_refs=_ref_list(data.get("target_artifact_refs", []), "repair_ticket.target_artifact_refs"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "repair_ticket.evidence_refs"),
            worker_brief_ref=validate_ref(data.get("worker_brief_ref"), "repair_ticket.worker_brief_ref"),
            status=require_enum(
                data.get("status", RepairTicketStatus.READY.value),
                RepairTicketStatus,
                "repair_ticket.status",
            ),
        )
        ticket.validate()
        return ticket

    def validate(self) -> None:
        _require_schema(self.schema_version, REPAIR_TICKET_SCHEMA_VERSION, "repair_ticket.schema_version")
        _validate_id(self.ticket_id, "repair_ticket.ticket_id")
        _validate_hash(self.ticket_hash, "repair_ticket.ticket_hash")
        require_non_empty_str(self.run_id, "repair_ticket.run_id")
        require_non_empty_str(self.contract_id, "repair_ticket.contract_id")
        _validate_hash(self.contract_hash, "repair_ticket.contract_hash")
        validate_ref(self.contract_ref, "repair_ticket.contract_ref")
        validate_ref(self.source_result_ref, "repair_ticket.source_result_ref")
        if _is_checkpoint_ref(self.source_result_ref):
            raise ContractValidationError("repair_ticket.source_result_ref cannot be a mutable checkpoint ref")
        validate_ref(self.source_judge_report_ref, "repair_ticket.source_judge_report_ref")
        validate_ref(self.source_repair_brief_ref, "repair_ticket.source_repair_brief_ref")
        validate_ref(self.execution_packet_ref, "repair_ticket.execution_packet_ref")
        validate_ref(self.execution_report_ref, "repair_ticket.execution_report_ref")
        validate_ref(self.judge_packet_ref, "repair_ticket.judge_packet_ref")
        validate_ref(self.judge_report_ref, "repair_ticket.judge_report_ref")
        _validate_unique_refs(self.target_artifact_refs, "repair_ticket.target_artifact_refs")
        _validate_unique_refs(self.evidence_refs, "repair_ticket.evidence_refs")
        validate_ref(self.worker_brief_ref, "repair_ticket.worker_brief_ref")
        require_enum(self.status, RepairTicketStatus, "repair_ticket.status")
        expected_id = _repair_ticket_id_from_parts(
            run_id=self.run_id,
            contract_hash=self.contract_hash,
            source_result_ref=self.source_result_ref,
            source_repair_brief_ref=self.source_repair_brief_ref,
        )
        if self.ticket_id != expected_id:
            raise ContractValidationError("repair_ticket.ticket_id does not match deterministic id seed")
        expected_hash = stable_json_hash(self.to_dict_without_hash())
        if self.ticket_hash != expected_hash:
            raise ContractValidationError("repair_ticket.ticket_hash does not match ticket content")
        assert_refs_only_payload(self.to_dict_without_validation(), "repair_ticket")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ticket_id": self.ticket_id,
            "run_id": self.run_id,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "source_result_ref": self.source_result_ref,
            "source_judge_report_ref": self.source_judge_report_ref,
            "source_repair_brief_ref": self.source_repair_brief_ref,
            "execution_packet_ref": self.execution_packet_ref,
            "execution_report_ref": self.execution_report_ref,
            "judge_packet_ref": self.judge_packet_ref,
            "judge_report_ref": self.judge_report_ref,
            "target_artifact_refs": list(self.target_artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "worker_brief_ref": self.worker_brief_ref,
            "status": require_enum(self.status, RepairTicketStatus, "repair_ticket.status").value,
        }

    def to_dict_without_validation(self) -> dict[str, Any]:
        payload = self.to_dict_without_hash()
        payload["ticket_hash"] = self.ticket_hash
        return payload

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class RepairExecutionDirective:
    """Refs-only directive that prepares the next repair execution packet."""

    directive_id: str
    directive_hash: str
    run_id: str
    contract_id: str
    contract_hash: str
    repair_ticket_ref: str
    repair_ticket_hash: str
    source_result_ref: str
    source_repair_brief_ref: str
    worker_brief_ref: str
    execution_packet_ref: str
    execution_report_ref: str
    target_artifact_refs: list[str] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    status: RepairExecutionDirectiveStatus = RepairExecutionDirectiveStatus.READY
    schema_version: str = REPAIR_EXECUTION_DIRECTIVE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairExecutionDirective":
        data = _strict_mapping(
            payload,
            "repair_execution_directive",
            {
                "schema_version",
                "directive_id",
                "directive_hash",
                "run_id",
                "contract_id",
                "contract_hash",
                "repair_ticket_ref",
                "repair_ticket_hash",
                "source_result_ref",
                "source_repair_brief_ref",
                "worker_brief_ref",
                "execution_packet_ref",
                "execution_report_ref",
                "target_artifact_refs",
                "context_refs",
                "status",
            },
        )
        directive = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", REPAIR_EXECUTION_DIRECTIVE_SCHEMA_VERSION),
                "repair_execution_directive.schema_version",
            ),
            directive_id=_validate_id(data.get("directive_id"), "repair_execution_directive.directive_id"),
            directive_hash=_validate_hash(data.get("directive_hash"), "repair_execution_directive.directive_hash"),
            run_id=require_non_empty_str(data.get("run_id"), "repair_execution_directive.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "repair_execution_directive.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "repair_execution_directive.contract_hash"),
            repair_ticket_ref=validate_ref(data.get("repair_ticket_ref"), "repair_execution_directive.repair_ticket_ref"),
            repair_ticket_hash=_validate_hash(
                data.get("repair_ticket_hash"),
                "repair_execution_directive.repair_ticket_hash",
            ),
            source_result_ref=validate_ref(
                data.get("source_result_ref"),
                "repair_execution_directive.source_result_ref",
            ),
            source_repair_brief_ref=validate_ref(
                data.get("source_repair_brief_ref"),
                "repair_execution_directive.source_repair_brief_ref",
            ),
            worker_brief_ref=validate_ref(data.get("worker_brief_ref"), "repair_execution_directive.worker_brief_ref"),
            execution_packet_ref=validate_ref(
                data.get("execution_packet_ref"),
                "repair_execution_directive.execution_packet_ref",
            ),
            execution_report_ref=validate_ref(
                data.get("execution_report_ref"),
                "repair_execution_directive.execution_report_ref",
            ),
            target_artifact_refs=_ref_list(
                data.get("target_artifact_refs", []),
                "repair_execution_directive.target_artifact_refs",
            ),
            context_refs=_ref_list(data.get("context_refs", []), "repair_execution_directive.context_refs"),
            status=require_enum(
                data.get("status", RepairExecutionDirectiveStatus.READY.value),
                RepairExecutionDirectiveStatus,
                "repair_execution_directive.status",
            ),
        )
        directive.validate()
        return directive

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            REPAIR_EXECUTION_DIRECTIVE_SCHEMA_VERSION,
            "repair_execution_directive.schema_version",
        )
        _validate_id(self.directive_id, "repair_execution_directive.directive_id")
        _validate_hash(self.directive_hash, "repair_execution_directive.directive_hash")
        require_non_empty_str(self.run_id, "repair_execution_directive.run_id")
        require_non_empty_str(self.contract_id, "repair_execution_directive.contract_id")
        _validate_hash(self.contract_hash, "repair_execution_directive.contract_hash")
        validate_ref(self.repair_ticket_ref, "repair_execution_directive.repair_ticket_ref")
        _validate_hash(self.repair_ticket_hash, "repair_execution_directive.repair_ticket_hash")
        validate_ref(self.source_result_ref, "repair_execution_directive.source_result_ref")
        if _is_checkpoint_ref(self.source_result_ref):
            raise ContractValidationError("repair_execution_directive.source_result_ref cannot be a checkpoint ref")
        validate_ref(self.source_repair_brief_ref, "repair_execution_directive.source_repair_brief_ref")
        validate_ref(self.worker_brief_ref, "repair_execution_directive.worker_brief_ref")
        validate_ref(self.execution_packet_ref, "repair_execution_directive.execution_packet_ref")
        validate_ref(self.execution_report_ref, "repair_execution_directive.execution_report_ref")
        _validate_unique_refs(self.target_artifact_refs, "repair_execution_directive.target_artifact_refs")
        _validate_unique_refs(self.context_refs, "repair_execution_directive.context_refs")
        require_enum(self.status, RepairExecutionDirectiveStatus, "repair_execution_directive.status")
        expected_id = _repair_execution_directive_id(
            repair_ticket_ref=self.repair_ticket_ref,
            repair_ticket_hash=self.repair_ticket_hash,
        )
        if self.directive_id != expected_id:
            raise ContractValidationError("repair_execution_directive.directive_id does not match deterministic id seed")
        expected_hash = stable_json_hash(self.to_dict_without_hash())
        if self.directive_hash != expected_hash:
            raise ContractValidationError("repair_execution_directive.directive_hash does not match directive content")
        assert_refs_only_payload(self.to_dict_without_validation(), "repair_execution_directive")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "directive_id": self.directive_id,
            "run_id": self.run_id,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "repair_ticket_ref": self.repair_ticket_ref,
            "repair_ticket_hash": self.repair_ticket_hash,
            "source_result_ref": self.source_result_ref,
            "source_repair_brief_ref": self.source_repair_brief_ref,
            "worker_brief_ref": self.worker_brief_ref,
            "execution_packet_ref": self.execution_packet_ref,
            "execution_report_ref": self.execution_report_ref,
            "target_artifact_refs": list(self.target_artifact_refs),
            "context_refs": list(self.context_refs),
            "status": require_enum(
                self.status,
                RepairExecutionDirectiveStatus,
                "repair_execution_directive.status",
            ).value,
        }

    def to_dict_without_validation(self) -> dict[str, Any]:
        payload = self.to_dict_without_hash()
        payload["directive_hash"] = self.directive_hash
        return payload

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def build_repair_ticket(
    *,
    contract: TaskContract,
    result: AgenticFlowResult,
    repair_brief: RepairBrief,
    judge_packet: JudgePacket,
    judge_report: JudgeReport,
    workspace: RunWorkspace,
    source_result_ref: str | None = None,
    worker_brief: WorkerBrief | None = None,
    execution_packet: AgentExecutionPacket | None = None,
) -> RepairTicket:
    """Build and durably write an idempotent repair ticket for a repair result."""

    contract.to_dict()
    result.validate()
    repair_brief.validate()
    judge_packet.validate()
    judge_report.validate()
    workspace.permission_manifest.validate()

    if result.status is not AgenticFlowStatus.REPAIR:
        raise ContractValidationError("repair_ticket requires agentic_flow_result.status=repair")
    if result.judge_decision is not JudgeReportDecision.REPAIR:
        raise ContractValidationError("repair_ticket requires judge_decision=repair")
    if result.repair_brief_ref is None:
        raise ContractValidationError("repair_ticket requires result.repair_brief_ref")
    if result.contract_id != contract.contract_id or result.contract_hash != contract.contract_hash:
        raise ContractValidationError("repair_ticket result does not match active contract")
    if repair_brief.run_id != result.run_id:
        raise ContractValidationError("repair_ticket repair brief run_id does not match result")
    if repair_brief.contract_id != contract.contract_id or repair_brief.contract_hash != contract.contract_hash:
        raise ContractValidationError("repair_ticket repair brief does not match active contract")
    if judge_report.decision is not JudgeReportDecision.REPAIR:
        raise ContractValidationError("repair_ticket requires repair judge report")
    if judge_report.repair_brief_ref != result.repair_brief_ref:
        raise ContractValidationError("repair_ticket judge report repair_brief_ref does not match result")
    if judge_packet.execution_packet_ref != result.refs.execution_packet_ref:
        raise ContractValidationError("repair_ticket judge packet execution_packet_ref does not match result")

    validate_repair_brief_for_judge(
        repair_brief,
        judge_packet,
        judge_report,
        run_id=result.run_id,
    )

    expected_result_ref = _source_result_ref(source_result_ref, result)
    if expected_result_ref == result.refs.checkpoint_ref or _is_checkpoint_ref(expected_result_ref):
        raise ContractValidationError("repair_ticket.source_result_ref cannot be a mutable checkpoint ref")
    if source_result_ref is None:
        _write_or_match_json(workspace, expected_result_ref, result.to_dict(), "agentic_flow_result")
    else:
        _match_existing_json(workspace, expected_result_ref, result.to_dict(), "agentic_flow_result")
    _load_and_match(workspace, expected_result_ref, AgenticFlowResult, result, "agentic_flow_result")

    _load_and_match(workspace, result.refs.contract_ref, TaskContract, contract, "task_contract")
    _load_and_match(workspace, result.refs.judge_packet_ref, JudgePacket, judge_packet, "judge_packet")
    _load_and_match(workspace, result.refs.judge_report_ref, JudgeReport, judge_report, "judge_report")
    _load_and_match(workspace, result.repair_brief_ref, RepairBrief, repair_brief, "repair_brief")

    loaded_worker_brief = _read_artifact(workspace, result.refs.worker_brief_ref, WorkerBrief, "worker_brief")
    _require_worker_brief_binding(loaded_worker_brief, contract, result)
    if worker_brief is not None:
        worker_brief.validate()
        _require_same_payload(loaded_worker_brief, worker_brief, "worker_brief")

    loaded_execution_packet = _read_artifact(
        workspace,
        result.refs.execution_packet_ref,
        AgentExecutionPacket,
        "agent_execution_packet",
    )
    _require_execution_packet_binding(loaded_execution_packet, contract, result)
    loaded_execution_report = _read_artifact(
        workspace,
        result.refs.execution_report_ref,
        AgentExecutionReport,
        "agent_execution_report",
    )
    validate_judge_packet_for_execution(
        judge_packet,
        loaded_execution_packet,
        loaded_execution_report,
        execution_packet_ref=result.refs.execution_packet_ref,
        execution_report_ref=result.refs.execution_report_ref,
    )
    if execution_packet is not None:
        execution_packet.validate()
        _require_same_payload(loaded_execution_packet, execution_packet, "agent_execution_packet")

    if repair_brief.judge_report_ref != result.refs.judge_report_ref:
        raise ContractValidationError("repair_ticket repair brief judge report ref does not match result")
    if repair_brief.judge_packet_ref != result.refs.judge_packet_ref:
        raise ContractValidationError("repair_ticket repair brief judge packet ref does not match result")
    if repair_brief.execution_report_ref != result.refs.execution_report_ref:
        raise ContractValidationError("repair_ticket repair brief execution report ref does not match result")

    ticket_payload: dict[str, Any] = {
        "schema_version": REPAIR_TICKET_SCHEMA_VERSION,
        "ticket_id": _ticket_id(result, expected_result_ref),
        "run_id": result.run_id,
        "contract_id": contract.contract_id,
        "contract_hash": contract.contract_hash,
        "contract_ref": result.refs.contract_ref,
        "source_result_ref": expected_result_ref,
        "source_judge_report_ref": result.refs.judge_report_ref,
        "source_repair_brief_ref": result.repair_brief_ref,
        "execution_packet_ref": result.refs.execution_packet_ref,
        "execution_report_ref": repair_brief.execution_report_ref,
        "judge_packet_ref": repair_brief.judge_packet_ref,
        "judge_report_ref": repair_brief.judge_report_ref,
        "target_artifact_refs": list(repair_brief.target_artifact_refs),
        "evidence_refs": list(repair_brief.evidence_refs),
        "worker_brief_ref": result.refs.worker_brief_ref,
        "status": RepairTicketStatus.READY.value,
    }
    ticket = RepairTicket(
        schema_version=REPAIR_TICKET_SCHEMA_VERSION,
        ticket_id=_ticket_id(result, expected_result_ref),
        ticket_hash=stable_json_hash(ticket_payload),
        run_id=result.run_id,
        contract_id=contract.contract_id,
        contract_hash=contract.contract_hash,
        contract_ref=result.refs.contract_ref,
        source_result_ref=expected_result_ref,
        source_judge_report_ref=result.refs.judge_report_ref,
        source_repair_brief_ref=result.repair_brief_ref,
        execution_packet_ref=result.refs.execution_packet_ref,
        execution_report_ref=repair_brief.execution_report_ref,
        judge_packet_ref=repair_brief.judge_packet_ref,
        judge_report_ref=repair_brief.judge_report_ref,
        target_artifact_refs=list(repair_brief.target_artifact_refs),
        evidence_refs=list(repair_brief.evidence_refs),
        worker_brief_ref=result.refs.worker_brief_ref,
        status=RepairTicketStatus.READY,
    )
    return _write_or_replay_ticket(workspace, ticket)


def build_repair_execution_directive(
    *,
    ticket: RepairTicket,
    workspace: RunWorkspace,
    repair_ticket_ref: str | None = None,
    worker_brief: WorkerBrief | None = None,
) -> RepairExecutionDirective:
    """Prepare the next repair execution packet without invoking an executor."""

    ticket.validate()
    workspace.permission_manifest.validate()
    ticket_ref = repair_ticket_ref or f"repairs/{ticket.ticket_id}/repair_ticket.json"
    _load_and_match(workspace, ticket_ref, RepairTicket, ticket, "repair_ticket")

    result = _read_artifact(workspace, ticket.source_result_ref, AgenticFlowResult, "agentic_flow_result")
    if result.run_id != ticket.run_id or result.contract_hash != ticket.contract_hash:
        raise ContractValidationError("repair_execution_directive source result does not match ticket")
    if result.repair_brief_ref != ticket.source_repair_brief_ref:
        raise ContractValidationError("repair_execution_directive source result repair brief ref does not match ticket")
    if result.refs.judge_packet_ref != ticket.judge_packet_ref:
        raise ContractValidationError("repair_execution_directive source result judge packet ref does not match ticket")
    if result.refs.judge_report_ref != ticket.judge_report_ref:
        raise ContractValidationError("repair_execution_directive source result judge report ref does not match ticket")
    if result.refs.execution_packet_ref != ticket.execution_packet_ref:
        raise ContractValidationError("repair_execution_directive source result execution packet ref does not match ticket")
    if result.refs.execution_report_ref != ticket.execution_report_ref:
        raise ContractValidationError("repair_execution_directive source result execution report ref does not match ticket")
    brief = _read_artifact(workspace, ticket.source_repair_brief_ref, RepairBrief, "repair_brief")
    if brief.contract_hash != ticket.contract_hash or brief.run_id != ticket.run_id:
        raise ContractValidationError("repair_execution_directive repair brief does not match ticket")
    if brief.judge_packet_ref != ticket.judge_packet_ref:
        raise ContractValidationError("repair_execution_directive repair brief judge packet ref does not match ticket")
    if brief.judge_report_ref != ticket.judge_report_ref:
        raise ContractValidationError("repair_execution_directive repair brief judge report ref does not match ticket")
    if brief.execution_report_ref != ticket.execution_report_ref:
        raise ContractValidationError("repair_execution_directive repair brief execution report ref does not match ticket")
    if brief.target_artifact_refs != ticket.target_artifact_refs:
        raise ContractValidationError("repair_execution_directive repair brief target refs do not match ticket")
    if brief.evidence_refs != ticket.evidence_refs:
        raise ContractValidationError("repair_execution_directive repair brief evidence refs do not match ticket")
    judge_packet = _read_artifact(workspace, ticket.judge_packet_ref, JudgePacket, "judge_packet")
    judge_report = _read_artifact(workspace, ticket.judge_report_ref, JudgeReport, "judge_report")
    if judge_report.decision is not JudgeReportDecision.REPAIR:
        raise ContractValidationError("repair_execution_directive judge report is not a repair decision")
    if judge_report.repair_brief_ref != ticket.source_repair_brief_ref:
        raise ContractValidationError("repair_execution_directive judge report repair brief ref does not match ticket")
    validate_repair_brief_for_judge(brief, judge_packet, judge_report, run_id=ticket.run_id)
    execution_packet = _read_artifact(
        workspace,
        ticket.execution_packet_ref,
        AgentExecutionPacket,
        "agent_execution_packet",
    )
    execution_report = _read_artifact(
        workspace,
        ticket.execution_report_ref,
        AgentExecutionReport,
        "agent_execution_report",
    )
    validate_judge_packet_for_execution(
        judge_packet,
        execution_packet,
        execution_report,
        execution_packet_ref=ticket.execution_packet_ref,
        execution_report_ref=ticket.execution_report_ref,
    )
    loaded_worker_brief = _read_artifact(workspace, ticket.worker_brief_ref, WorkerBrief, "worker_brief")
    _require_ticket_worker_brief_binding(loaded_worker_brief, ticket)
    if worker_brief is not None:
        worker_brief.validate()
        _require_same_payload(loaded_worker_brief, worker_brief, "worker_brief")

    execution_packet_ref = f"packets/repairs/{ticket.ticket_id}/execution_packet.json"
    execution_report_ref = f"reports/repairs/{ticket.ticket_id}/execution_report.json"
    execution_packet = AgentExecutionPacket(
        packet_id=f"{ticket.ticket_id}-repair-execution-packet",
        contract_id=ticket.contract_id,
        contract_hash=ticket.contract_hash,
        contract_ref=ticket.contract_ref,
        worker_brief_ref=ticket.worker_brief_ref,
        workspace_policy_ref=_required_ref(loaded_worker_brief.workspace_policy_ref, "worker_brief.workspace_policy_ref"),
        permission_manifest_ref=_required_ref(
            loaded_worker_brief.permission_manifest_ref,
            "worker_brief.permission_manifest_ref",
        ),
        report_ref=execution_report_ref,
        worker_brief_hash=stable_json_hash(loaded_worker_brief.to_dict()),
        expected_artifact_refs=list(ticket.target_artifact_refs),
        allowed_input_refs=_unique_refs(
            [
                *loaded_worker_brief.allowed_input_refs,
                ticket_ref,
                ticket.source_result_ref,
                ticket.source_repair_brief_ref,
            ]
        ),
        writable_refs=list(loaded_worker_brief.writable_refs),
    )
    _write_or_match_json(workspace, execution_packet_ref, execution_packet.to_dict(), "repair_execution_packet")

    payload_without_hash: dict[str, Any] = {
        "schema_version": REPAIR_EXECUTION_DIRECTIVE_SCHEMA_VERSION,
        "directive_id": _repair_execution_directive_id(
            repair_ticket_ref=ticket_ref,
            repair_ticket_hash=ticket.ticket_hash,
        ),
        "run_id": ticket.run_id,
        "contract_id": ticket.contract_id,
        "contract_hash": ticket.contract_hash,
        "repair_ticket_ref": ticket_ref,
        "repair_ticket_hash": ticket.ticket_hash,
        "source_result_ref": ticket.source_result_ref,
        "source_repair_brief_ref": ticket.source_repair_brief_ref,
        "worker_brief_ref": ticket.worker_brief_ref,
        "execution_packet_ref": execution_packet_ref,
        "execution_report_ref": execution_report_ref,
        "target_artifact_refs": list(ticket.target_artifact_refs),
        "context_refs": _unique_refs([ticket_ref, ticket.source_result_ref, ticket.source_repair_brief_ref]),
        "status": RepairExecutionDirectiveStatus.READY.value,
    }
    directive = RepairExecutionDirective(
        schema_version=REPAIR_EXECUTION_DIRECTIVE_SCHEMA_VERSION,
        directive_id=_repair_execution_directive_id(
            repair_ticket_ref=ticket_ref,
            repair_ticket_hash=ticket.ticket_hash,
        ),
        directive_hash=stable_json_hash(payload_without_hash),
        run_id=ticket.run_id,
        contract_id=ticket.contract_id,
        contract_hash=ticket.contract_hash,
        repair_ticket_ref=ticket_ref,
        repair_ticket_hash=ticket.ticket_hash,
        source_result_ref=ticket.source_result_ref,
        source_repair_brief_ref=ticket.source_repair_brief_ref,
        worker_brief_ref=ticket.worker_brief_ref,
        execution_packet_ref=execution_packet_ref,
        execution_report_ref=execution_report_ref,
        target_artifact_refs=list(ticket.target_artifact_refs),
        context_refs=_unique_refs([ticket_ref, ticket.source_result_ref, ticket.source_repair_brief_ref]),
        status=RepairExecutionDirectiveStatus.READY,
    )
    return _write_or_replay_repair_execution_directive(workspace, directive)


def _source_result_ref(source_result_ref: str | None, result: AgenticFlowResult) -> str:
    if source_result_ref is not None:
        return validate_ref(source_result_ref, "source_result_ref")
    result_hash = stable_json_hash(result.to_dict()).split(":", 1)[1]
    return f"results/result-{result_hash}.json"


def _is_checkpoint_ref(ref: str) -> bool:
    safe_ref = validate_ref(ref, "checkpoint_ref")
    return safe_ref == "checkpoints" or safe_ref.startswith("checkpoints/")


def _ticket_id(result: AgenticFlowResult, source_result_ref: str) -> str:
    if result.repair_brief_ref is None:
        raise ContractValidationError("repair_ticket requires result.repair_brief_ref")
    return _repair_ticket_id_from_parts(
        run_id=result.run_id,
        contract_hash=result.contract_hash,
        source_result_ref=source_result_ref,
        source_repair_brief_ref=result.repair_brief_ref,
    )


def _repair_ticket_id_from_parts(
    *,
    run_id: str,
    contract_hash: str,
    source_result_ref: str,
    source_repair_brief_ref: str,
) -> str:
    seed = {
        "schema_version": REPAIR_TICKET_SCHEMA_VERSION,
        "run_id": require_non_empty_str(run_id, "repair_ticket_id.run_id"),
        "contract_hash": _validate_hash(contract_hash, "repair_ticket_id.contract_hash"),
        "source_result_ref": validate_ref(source_result_ref, "repair_ticket_id.source_result_ref"),
        "source_repair_brief_ref": validate_ref(
            source_repair_brief_ref,
            "repair_ticket_id.source_repair_brief_ref",
        ),
    }
    return "repair-" + stable_json_hash(seed).split(":", 1)[1]


def _write_or_replay_ticket(workspace: RunWorkspace, ticket: RepairTicket) -> RepairTicket:
    ticket_ref = f"repairs/{ticket.ticket_id}/repair_ticket.json"
    ticket.validate()
    try:
        existing_payload = workspace.read_json(ticket_ref)
    except FileNotFoundError:
        workspace.write_json(ticket_ref, ticket.to_dict())
        return ticket
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"repair_ticket is unreadable: {ticket_ref}") from exc

    existing_ticket = RepairTicket.from_dict(existing_payload)
    if existing_ticket.ticket_hash != ticket.ticket_hash:
        raise ContractValidationError("repair_ticket replay conflict for deterministic ticket_id")
    return existing_ticket


def _write_or_replay_repair_execution_directive(
    workspace: RunWorkspace,
    directive: RepairExecutionDirective,
) -> RepairExecutionDirective:
    directive_ref = f"repairs/{directive.repair_ticket_ref.split('/')[-2]}/repair_execution_directive.json"
    directive.validate()
    try:
        existing_payload = workspace.read_json(directive_ref)
    except FileNotFoundError:
        workspace.write_json(directive_ref, directive.to_dict())
        return directive
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"repair_execution_directive is unreadable: {directive_ref}") from exc

    existing_directive = RepairExecutionDirective.from_dict(existing_payload)
    if existing_directive.directive_hash != directive.directive_hash:
        raise ContractValidationError("repair_execution_directive replay conflict for deterministic directive_id")
    return existing_directive


def _write_or_match_json(
    workspace: RunWorkspace,
    ref: str,
    payload: dict[str, Any],
    field_name: str,
) -> None:
    try:
        existing_payload = workspace.read_json(ref)
    except FileNotFoundError:
        workspace.write_json(ref, payload)
        return
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"{field_name} ref is unreadable: {ref}") from exc
    if stable_json_hash(existing_payload) != stable_json_hash(payload):
        raise ContractValidationError(f"{field_name} immutable ref already contains different content")


def _match_existing_json(
    workspace: RunWorkspace,
    ref: str,
    payload: dict[str, Any],
    field_name: str,
) -> None:
    try:
        existing_payload = workspace.read_json(ref)
    except FileNotFoundError as exc:
        raise ContractValidationError(f"{field_name} immutable ref is missing: {ref}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"{field_name} ref is unreadable: {ref}") from exc
    if stable_json_hash(existing_payload) != stable_json_hash(payload):
        raise ContractValidationError(f"{field_name} immutable ref contains different content")


def _load_and_match(
    workspace: RunWorkspace,
    ref: str,
    artifact_type: type[Any],
    expected: Any,
    field_name: str,
) -> None:
    loaded = _read_artifact(workspace, ref, artifact_type, field_name)
    _require_same_payload(loaded, expected, field_name)


def _read_artifact(workspace: RunWorkspace, ref: str, artifact_type: type[Any], field_name: str) -> Any:
    safe_ref = validate_ref(ref, f"{field_name}_ref")
    try:
        payload = workspace.read_json(safe_ref)
    except FileNotFoundError as exc:
        raise ContractValidationError(f"{field_name} ref is missing: {safe_ref}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"{field_name} ref is unreadable: {safe_ref}") from exc
    try:
        return artifact_type.from_dict(payload)
    except (AttributeError, TypeError) as exc:
        raise ContractValidationError(f"{field_name} type is not loadable from json") from exc


def _require_same_payload(left: Any, right: Any, field_name: str) -> None:
    if stable_json_hash(left.to_dict()) != stable_json_hash(right.to_dict()):
        raise ContractValidationError(f"{field_name} content does not match supplied object")


def _require_worker_brief_binding(brief: WorkerBrief, contract: TaskContract, result: AgenticFlowResult) -> None:
    if brief.contract_id != contract.contract_id or brief.contract_id != result.contract_id:
        raise ContractValidationError("repair_ticket.worker_brief_ref contract_id does not match active contract")
    if brief.contract_hash != contract.contract_hash or brief.contract_hash != result.contract_hash:
        raise ContractValidationError("repair_ticket.worker_brief_ref contract_hash does not match active contract")
    if brief.contract_ref != result.refs.contract_ref:
        raise ContractValidationError("repair_ticket.worker_brief_ref contract_ref does not match result")


def _require_execution_packet_binding(
    packet: AgentExecutionPacket,
    contract: TaskContract,
    result: AgenticFlowResult,
) -> None:
    if packet.contract_id != contract.contract_id or packet.contract_id != result.contract_id:
        raise ContractValidationError("repair_ticket.execution_packet_ref contract_id does not match active contract")
    if packet.contract_hash != contract.contract_hash or packet.contract_hash != result.contract_hash:
        raise ContractValidationError("repair_ticket.execution_packet_ref contract_hash does not match active contract")
    if packet.contract_ref != result.refs.contract_ref:
        raise ContractValidationError("repair_ticket.execution_packet_ref contract_ref does not match result")
    if packet.worker_brief_ref != result.refs.worker_brief_ref:
        raise ContractValidationError("repair_ticket.execution_packet_ref worker_brief_ref does not match result")


def _require_ticket_worker_brief_binding(brief: WorkerBrief, ticket: RepairTicket) -> None:
    if brief.contract_id != ticket.contract_id:
        raise ContractValidationError("repair_execution_directive.worker_brief_ref contract_id does not match ticket")
    if brief.contract_hash != ticket.contract_hash:
        raise ContractValidationError("repair_execution_directive.worker_brief_ref contract_hash does not match ticket")
    if brief.contract_ref != ticket.contract_ref:
        raise ContractValidationError("repair_execution_directive.worker_brief_ref contract_ref does not match ticket")


def _repair_execution_directive_id(*, repair_ticket_ref: str, repair_ticket_hash: str) -> str:
    seed = {
        "schema_version": REPAIR_EXECUTION_DIRECTIVE_SCHEMA_VERSION,
        "repair_ticket_ref": validate_ref(repair_ticket_ref, "repair_execution_directive_id.repair_ticket_ref"),
        "repair_ticket_hash": _validate_hash(
            repair_ticket_hash,
            "repair_execution_directive_id.repair_ticket_hash",
        ),
    }
    return "repair-execution-" + stable_json_hash(seed).split(":", 1)[1]


def _required_ref(value: str | None, field_name: str) -> str:
    if value is None:
        raise ContractValidationError(f"{field_name} is required")
    return validate_ref(value, field_name)


def _strict_mapping(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(value, field_name)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unknown fields: {unknown}")
    return data


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")


def _unique_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        safe_ref = validate_ref(ref, "agentic_repair_controller.ref")
        if safe_ref not in result:
            result.append(safe_ref)
    return result


def _validate_hash(value: Any, field_name: str) -> str:
    hash_value = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not hash_value.startswith(prefix):
        raise ContractValidationError(f"{field_name} must start with {prefix!r}")
    digest = hash_value[len(prefix) :]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ContractValidationError(f"{field_name} must be a sha256 hex digest")
    return hash_value


def _validate_id(value: Any, field_name: str) -> str:
    identifier = require_non_empty_str(value, field_name)
    if "/" in identifier or "\\" in identifier or identifier in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a single safe path segment")
    return identifier


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"unsupported {field_name}: {actual}")


__all__ = [
    "REPAIR_EXECUTION_DIRECTIVE_SCHEMA_VERSION",
    "REPAIR_TICKET_SCHEMA_VERSION",
    "RepairExecutionDirective",
    "RepairExecutionDirectiveStatus",
    "RepairTicket",
    "RepairTicketStatus",
    "build_repair_execution_directive",
    "build_repair_ticket",
]
