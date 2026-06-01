"""Revision pending/application controller for TaskContract agentic flow."""

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
from .agentic_repair import (
    TaskRevisionAuthority,
    TaskRevisionDecision,
    TaskRevisionDecisionStatus,
    TaskRevisionRequest,
    validate_revision_request_for_judge,
)
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
from .task_contract import TaskContract, TaskContractRevision
from .workspace_runtime import RunWorkspace


REVISION_PENDING_RECORD_SCHEMA_VERSION = "revision_pending_record.v1"
REVISION_APPLIED_RECORD_SCHEMA_VERSION = "revision_applied_record.v1"


class RevisionPendingStatus(StrEnum):
    """Status for a revision request awaiting authority/application."""

    PENDING = "pending"


class RevisionAppliedStatus(StrEnum):
    """Status for an applied TaskContract revision."""

    APPLIED = "applied"


@dataclass(frozen=True)
class RevisionPendingRecord:
    """Refs-only record that binds a judge revision request to a flow result."""

    pending_id: str
    pending_hash: str
    run_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    request_id: str
    source_result_ref: str
    source_judge_report_ref: str
    source_revision_request_ref: str
    execution_packet_ref: str
    execution_report_ref: str
    judge_packet_ref: str
    judge_report_ref: str
    authority_required: TaskRevisionAuthority
    evidence_refs: list[str] = field(default_factory=list)
    status: RevisionPendingStatus = RevisionPendingStatus.PENDING
    schema_version: str = REVISION_PENDING_RECORD_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RevisionPendingRecord":
        data = _strict_mapping(
            payload,
            "revision_pending_record",
            {
                "schema_version",
                "pending_id",
                "pending_hash",
                "run_id",
                "contract_id",
                "contract_hash",
                "contract_ref",
                "request_id",
                "source_result_ref",
                "source_judge_report_ref",
                "source_revision_request_ref",
                "execution_packet_ref",
                "execution_report_ref",
                "judge_packet_ref",
                "judge_report_ref",
                "authority_required",
                "evidence_refs",
                "status",
            },
        )
        record = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", REVISION_PENDING_RECORD_SCHEMA_VERSION),
                "revision_pending_record.schema_version",
            ),
            pending_id=_validate_id(data.get("pending_id"), "revision_pending_record.pending_id"),
            pending_hash=_validate_hash(data.get("pending_hash"), "revision_pending_record.pending_hash"),
            run_id=require_non_empty_str(data.get("run_id"), "revision_pending_record.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "revision_pending_record.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "revision_pending_record.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "revision_pending_record.contract_ref"),
            request_id=require_non_empty_str(data.get("request_id"), "revision_pending_record.request_id"),
            source_result_ref=validate_ref(
                data.get("source_result_ref"),
                "revision_pending_record.source_result_ref",
            ),
            source_judge_report_ref=validate_ref(
                data.get("source_judge_report_ref"),
                "revision_pending_record.source_judge_report_ref",
            ),
            source_revision_request_ref=validate_ref(
                data.get("source_revision_request_ref"),
                "revision_pending_record.source_revision_request_ref",
            ),
            execution_packet_ref=validate_ref(
                data.get("execution_packet_ref"),
                "revision_pending_record.execution_packet_ref",
            ),
            execution_report_ref=validate_ref(
                data.get("execution_report_ref"),
                "revision_pending_record.execution_report_ref",
            ),
            judge_packet_ref=validate_ref(data.get("judge_packet_ref"), "revision_pending_record.judge_packet_ref"),
            judge_report_ref=validate_ref(data.get("judge_report_ref"), "revision_pending_record.judge_report_ref"),
            authority_required=require_enum(
                data.get("authority_required"),
                TaskRevisionAuthority,
                "revision_pending_record.authority_required",
            ),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "revision_pending_record.evidence_refs"),
            status=require_enum(
                data.get("status", RevisionPendingStatus.PENDING.value),
                RevisionPendingStatus,
                "revision_pending_record.status",
            ),
        )
        record.validate()
        return record

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            REVISION_PENDING_RECORD_SCHEMA_VERSION,
            "revision_pending_record.schema_version",
        )
        _validate_id(self.pending_id, "revision_pending_record.pending_id")
        _validate_hash(self.pending_hash, "revision_pending_record.pending_hash")
        require_non_empty_str(self.run_id, "revision_pending_record.run_id")
        require_non_empty_str(self.contract_id, "revision_pending_record.contract_id")
        _validate_hash(self.contract_hash, "revision_pending_record.contract_hash")
        validate_ref(self.contract_ref, "revision_pending_record.contract_ref")
        require_non_empty_str(self.request_id, "revision_pending_record.request_id")
        validate_ref(self.source_result_ref, "revision_pending_record.source_result_ref")
        if _is_checkpoint_ref(self.source_result_ref):
            raise ContractValidationError("revision_pending_record.source_result_ref cannot be a checkpoint ref")
        validate_ref(self.source_judge_report_ref, "revision_pending_record.source_judge_report_ref")
        validate_ref(self.source_revision_request_ref, "revision_pending_record.source_revision_request_ref")
        validate_ref(self.execution_packet_ref, "revision_pending_record.execution_packet_ref")
        validate_ref(self.execution_report_ref, "revision_pending_record.execution_report_ref")
        validate_ref(self.judge_packet_ref, "revision_pending_record.judge_packet_ref")
        validate_ref(self.judge_report_ref, "revision_pending_record.judge_report_ref")
        require_enum(self.authority_required, TaskRevisionAuthority, "revision_pending_record.authority_required")
        _validate_unique_refs(self.evidence_refs, "revision_pending_record.evidence_refs")
        require_enum(self.status, RevisionPendingStatus, "revision_pending_record.status")
        expected_id = _revision_pending_id(
            run_id=self.run_id,
            contract_hash=self.contract_hash,
            source_result_ref=self.source_result_ref,
            source_revision_request_ref=self.source_revision_request_ref,
        )
        if self.pending_id != expected_id:
            raise ContractValidationError("revision_pending_record.pending_id does not match deterministic id seed")
        expected_hash = stable_json_hash(self.to_dict_without_hash())
        if self.pending_hash != expected_hash:
            raise ContractValidationError("revision_pending_record.pending_hash does not match record content")
        assert_refs_only_payload(self.to_dict_without_validation(), "revision_pending_record")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pending_id": self.pending_id,
            "run_id": self.run_id,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "request_id": self.request_id,
            "source_result_ref": self.source_result_ref,
            "source_judge_report_ref": self.source_judge_report_ref,
            "source_revision_request_ref": self.source_revision_request_ref,
            "execution_packet_ref": self.execution_packet_ref,
            "execution_report_ref": self.execution_report_ref,
            "judge_packet_ref": self.judge_packet_ref,
            "judge_report_ref": self.judge_report_ref,
            "authority_required": require_enum(
                self.authority_required,
                TaskRevisionAuthority,
                "revision_pending_record.authority_required",
            ).value,
            "evidence_refs": list(self.evidence_refs),
            "status": require_enum(self.status, RevisionPendingStatus, "revision_pending_record.status").value,
        }

    def to_dict_without_validation(self) -> dict[str, Any]:
        payload = self.to_dict_without_hash()
        payload["pending_hash"] = self.pending_hash
        return payload

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class RevisionAppliedRecord:
    """Refs-only record for an approved TaskContract revision application."""

    applied_id: str
    applied_hash: str
    run_id: str
    contract_id: str
    previous_contract_hash: str
    revised_contract_hash: str
    pending_ref: str
    pending_hash: str
    task_revision_decision_ref: str
    task_contract_revision_ref: str
    previous_contract_ref: str
    revised_contract_ref: str
    source_revision_request_ref: str
    status: RevisionAppliedStatus = RevisionAppliedStatus.APPLIED
    schema_version: str = REVISION_APPLIED_RECORD_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RevisionAppliedRecord":
        data = _strict_mapping(
            payload,
            "revision_applied_record",
            {
                "schema_version",
                "applied_id",
                "applied_hash",
                "run_id",
                "contract_id",
                "previous_contract_hash",
                "revised_contract_hash",
                "pending_ref",
                "pending_hash",
                "task_revision_decision_ref",
                "task_contract_revision_ref",
                "previous_contract_ref",
                "revised_contract_ref",
                "source_revision_request_ref",
                "status",
            },
        )
        record = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", REVISION_APPLIED_RECORD_SCHEMA_VERSION),
                "revision_applied_record.schema_version",
            ),
            applied_id=_validate_id(data.get("applied_id"), "revision_applied_record.applied_id"),
            applied_hash=_validate_hash(data.get("applied_hash"), "revision_applied_record.applied_hash"),
            run_id=require_non_empty_str(data.get("run_id"), "revision_applied_record.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "revision_applied_record.contract_id"),
            previous_contract_hash=_validate_hash(
                data.get("previous_contract_hash"),
                "revision_applied_record.previous_contract_hash",
            ),
            revised_contract_hash=_validate_hash(
                data.get("revised_contract_hash"),
                "revision_applied_record.revised_contract_hash",
            ),
            pending_ref=validate_ref(data.get("pending_ref"), "revision_applied_record.pending_ref"),
            pending_hash=_validate_hash(data.get("pending_hash"), "revision_applied_record.pending_hash"),
            task_revision_decision_ref=validate_ref(
                data.get("task_revision_decision_ref"),
                "revision_applied_record.task_revision_decision_ref",
            ),
            task_contract_revision_ref=validate_ref(
                data.get("task_contract_revision_ref"),
                "revision_applied_record.task_contract_revision_ref",
            ),
            previous_contract_ref=validate_ref(
                data.get("previous_contract_ref"),
                "revision_applied_record.previous_contract_ref",
            ),
            revised_contract_ref=validate_ref(
                data.get("revised_contract_ref"),
                "revision_applied_record.revised_contract_ref",
            ),
            source_revision_request_ref=validate_ref(
                data.get("source_revision_request_ref"),
                "revision_applied_record.source_revision_request_ref",
            ),
            status=require_enum(
                data.get("status", RevisionAppliedStatus.APPLIED.value),
                RevisionAppliedStatus,
                "revision_applied_record.status",
            ),
        )
        record.validate()
        return record

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            REVISION_APPLIED_RECORD_SCHEMA_VERSION,
            "revision_applied_record.schema_version",
        )
        _validate_id(self.applied_id, "revision_applied_record.applied_id")
        _validate_hash(self.applied_hash, "revision_applied_record.applied_hash")
        require_non_empty_str(self.run_id, "revision_applied_record.run_id")
        require_non_empty_str(self.contract_id, "revision_applied_record.contract_id")
        _validate_hash(self.previous_contract_hash, "revision_applied_record.previous_contract_hash")
        _validate_hash(self.revised_contract_hash, "revision_applied_record.revised_contract_hash")
        if self.previous_contract_hash == self.revised_contract_hash:
            raise ContractValidationError("revision_applied_record must change contract hash")
        validate_ref(self.pending_ref, "revision_applied_record.pending_ref")
        _validate_hash(self.pending_hash, "revision_applied_record.pending_hash")
        validate_ref(self.task_revision_decision_ref, "revision_applied_record.task_revision_decision_ref")
        validate_ref(self.task_contract_revision_ref, "revision_applied_record.task_contract_revision_ref")
        validate_ref(self.previous_contract_ref, "revision_applied_record.previous_contract_ref")
        validate_ref(self.revised_contract_ref, "revision_applied_record.revised_contract_ref")
        validate_ref(self.source_revision_request_ref, "revision_applied_record.source_revision_request_ref")
        require_enum(self.status, RevisionAppliedStatus, "revision_applied_record.status")
        expected_id = _revision_applied_id(
            pending_ref=self.pending_ref,
            pending_hash=self.pending_hash,
            revised_contract_hash=self.revised_contract_hash,
        )
        if self.applied_id != expected_id:
            raise ContractValidationError("revision_applied_record.applied_id does not match deterministic id seed")
        expected_hash = stable_json_hash(self.to_dict_without_hash())
        if self.applied_hash != expected_hash:
            raise ContractValidationError("revision_applied_record.applied_hash does not match record content")
        assert_refs_only_payload(self.to_dict_without_validation(), "revision_applied_record")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "applied_id": self.applied_id,
            "run_id": self.run_id,
            "contract_id": self.contract_id,
            "previous_contract_hash": self.previous_contract_hash,
            "revised_contract_hash": self.revised_contract_hash,
            "pending_ref": self.pending_ref,
            "pending_hash": self.pending_hash,
            "task_revision_decision_ref": self.task_revision_decision_ref,
            "task_contract_revision_ref": self.task_contract_revision_ref,
            "previous_contract_ref": self.previous_contract_ref,
            "revised_contract_ref": self.revised_contract_ref,
            "source_revision_request_ref": self.source_revision_request_ref,
            "status": require_enum(self.status, RevisionAppliedStatus, "revision_applied_record.status").value,
        }

    def to_dict_without_validation(self) -> dict[str, Any]:
        payload = self.to_dict_without_hash()
        payload["applied_hash"] = self.applied_hash
        return payload

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def build_revision_pending_record(
    *,
    contract: TaskContract,
    result: AgenticFlowResult,
    revision_request: TaskRevisionRequest,
    judge_packet: JudgePacket,
    judge_report: JudgeReport,
    workspace: RunWorkspace,
    source_result_ref: str | None = None,
) -> RevisionPendingRecord:
    """Build and persist a pending revision record for a revision-required result."""

    contract.to_dict()
    result.validate()
    revision_request.validate()
    judge_packet.validate()
    judge_report.validate()
    workspace.permission_manifest.validate()

    if result.status is not AgenticFlowStatus.REVISION_REQUIRED:
        raise ContractValidationError("revision_pending_record requires agentic_flow_result.status=revision_required")
    if result.judge_decision is not JudgeReportDecision.REVISION_REQUIRED:
        raise ContractValidationError("revision_pending_record requires judge_decision=revision_required")
    if result.revision_request_ref is None:
        raise ContractValidationError("revision_pending_record requires result.revision_request_ref")
    if result.contract_id != contract.contract_id or result.contract_hash != contract.contract_hash:
        raise ContractValidationError("revision_pending_record result does not match active contract")
    if revision_request.run_id != result.run_id:
        raise ContractValidationError("revision_pending_record request run_id does not match result")
    if revision_request.contract_id != contract.contract_id or revision_request.contract_hash != contract.contract_hash:
        raise ContractValidationError("revision_pending_record request does not match active contract")
    if judge_report.decision is not JudgeReportDecision.REVISION_REQUIRED:
        raise ContractValidationError("revision_pending_record requires revision_required judge report")
    if judge_report.revision_request_ref != result.revision_request_ref:
        raise ContractValidationError("revision_pending_record judge report revision_request_ref does not match result")
    if judge_packet.execution_packet_ref != result.refs.execution_packet_ref:
        raise ContractValidationError("revision_pending_record judge packet execution_packet_ref does not match result")

    validate_revision_request_for_judge(
        revision_request,
        judge_packet,
        judge_report,
        run_id=result.run_id,
    )

    result_ref = _source_result_ref(source_result_ref, result)
    if result_ref == result.refs.checkpoint_ref or _is_checkpoint_ref(result_ref):
        raise ContractValidationError("revision_pending_record.source_result_ref cannot be a checkpoint ref")
    if source_result_ref is None:
        _write_or_match_json(workspace, result_ref, result.to_dict(), "agentic_flow_result")
    else:
        _match_existing_json(workspace, result_ref, result.to_dict(), "agentic_flow_result")
    _load_and_match(workspace, result_ref, AgenticFlowResult, result, "agentic_flow_result")
    _load_and_match(workspace, result.refs.contract_ref, TaskContract, contract, "task_contract")
    _load_and_match(workspace, result.refs.judge_packet_ref, JudgePacket, judge_packet, "judge_packet")
    _load_and_match(workspace, result.refs.judge_report_ref, JudgeReport, judge_report, "judge_report")
    _load_and_match(
        workspace,
        result.revision_request_ref,
        TaskRevisionRequest,
        revision_request,
        "task_revision_request",
    )

    execution_packet = _read_artifact(
        workspace,
        result.refs.execution_packet_ref,
        AgentExecutionPacket,
        "agent_execution_packet",
    )
    execution_report = _read_artifact(
        workspace,
        result.refs.execution_report_ref,
        AgentExecutionReport,
        "agent_execution_report",
    )
    validate_judge_packet_for_execution(
        judge_packet,
        execution_packet,
        execution_report,
        execution_packet_ref=result.refs.execution_packet_ref,
        execution_report_ref=result.refs.execution_report_ref,
    )

    if revision_request.judge_packet_ref != result.refs.judge_packet_ref:
        raise ContractValidationError("revision_pending_record request judge packet ref does not match result")
    if revision_request.judge_report_ref != result.refs.judge_report_ref:
        raise ContractValidationError("revision_pending_record request judge report ref does not match result")
    if revision_request.execution_report_ref != result.refs.execution_report_ref:
        raise ContractValidationError("revision_pending_record request execution report ref does not match result")

    payload_without_hash: dict[str, Any] = {
        "schema_version": REVISION_PENDING_RECORD_SCHEMA_VERSION,
        "pending_id": _revision_pending_id(
            run_id=result.run_id,
            contract_hash=contract.contract_hash,
            source_result_ref=result_ref,
            source_revision_request_ref=result.revision_request_ref,
        ),
        "run_id": result.run_id,
        "contract_id": contract.contract_id,
        "contract_hash": contract.contract_hash,
        "contract_ref": result.refs.contract_ref,
        "request_id": revision_request.request_id,
        "source_result_ref": result_ref,
        "source_judge_report_ref": result.refs.judge_report_ref,
        "source_revision_request_ref": result.revision_request_ref,
        "execution_packet_ref": result.refs.execution_packet_ref,
        "execution_report_ref": revision_request.execution_report_ref,
        "judge_packet_ref": revision_request.judge_packet_ref,
        "judge_report_ref": revision_request.judge_report_ref,
        "authority_required": revision_request.authority_required.value,
        "evidence_refs": list(revision_request.evidence_refs),
        "status": RevisionPendingStatus.PENDING.value,
    }
    record = RevisionPendingRecord(
        schema_version=REVISION_PENDING_RECORD_SCHEMA_VERSION,
        pending_id=_revision_pending_id(
            run_id=result.run_id,
            contract_hash=contract.contract_hash,
            source_result_ref=result_ref,
            source_revision_request_ref=result.revision_request_ref,
        ),
        pending_hash=stable_json_hash(payload_without_hash),
        run_id=result.run_id,
        contract_id=contract.contract_id,
        contract_hash=contract.contract_hash,
        contract_ref=result.refs.contract_ref,
        request_id=revision_request.request_id,
        source_result_ref=result_ref,
        source_judge_report_ref=result.refs.judge_report_ref,
        source_revision_request_ref=result.revision_request_ref,
        execution_packet_ref=result.refs.execution_packet_ref,
        execution_report_ref=revision_request.execution_report_ref,
        judge_packet_ref=revision_request.judge_packet_ref,
        judge_report_ref=revision_request.judge_report_ref,
        authority_required=revision_request.authority_required,
        evidence_refs=list(revision_request.evidence_refs),
        status=RevisionPendingStatus.PENDING,
    )
    return _write_or_replay_pending(workspace, record)


def apply_task_contract_revision(
    *,
    pending: RevisionPendingRecord,
    decision: TaskRevisionDecision,
    revised_contract: TaskContract,
    workspace: RunWorkspace,
    pending_ref: str | None = None,
    decision_ref: str | None = None,
) -> RevisionAppliedRecord:
    """Apply an approved TaskContract revision without mutating runtime state."""

    pending.validate()
    decision.validate()
    revised_contract.to_dict()
    workspace.permission_manifest.validate()
    resolved_pending_ref = pending_ref or _pending_ref(pending.request_id)
    resolved_decision_ref = decision_ref or _decision_ref(pending.request_id)

    _load_and_match(workspace, resolved_pending_ref, RevisionPendingRecord, pending, "revision_pending_record")
    _require_pending_source_bindings(pending, workspace)
    if decision.decision is not TaskRevisionDecisionStatus.APPROVED:
        raise ContractValidationError("revision_applied_record requires an approved task revision decision")
    decision_authority = require_enum(decision.authority, TaskRevisionAuthority, "task_revision_decision.authority")
    pending_authority = require_enum(
        pending.authority_required,
        TaskRevisionAuthority,
        "revision_pending_record.authority_required",
    )
    if decision_authority is not pending_authority:
        raise ContractValidationError("revision_applied_record decision authority does not match pending requirement")
    if decision.request_id != pending.request_id:
        raise ContractValidationError("revision_applied_record decision request_id does not match pending record")
    if decision.request_ref != pending.source_revision_request_ref:
        raise ContractValidationError("revision_applied_record decision request_ref does not match pending record")
    if decision.current_contract_ref != pending.contract_ref:
        raise ContractValidationError("revision_applied_record decision current_contract_ref does not match pending")
    if decision.current_contract_hash != pending.contract_hash:
        raise ContractValidationError("revision_applied_record decision current_contract_hash does not match pending")
    if revised_contract.contract_id != pending.contract_id:
        raise ContractValidationError("revision_applied_record revised contract_id does not match pending")
    if revised_contract.contract_hash != decision.revised_contract_hash:
        raise ContractValidationError("revision_applied_record revised contract hash does not match decision")
    if revised_contract.contract_hash == pending.contract_hash:
        raise ContractValidationError("revision_applied_record revised contract must change hash")

    _match_existing_json(
        workspace,
        decision.revised_contract_ref,
        revised_contract.to_dict(),
        "revised_task_contract",
    )
    _write_or_match_json(workspace, resolved_decision_ref, decision.to_dict(), "task_revision_decision")

    revision_ref = _task_contract_revision_ref(pending.request_id)
    task_revision = TaskContractRevision(
        revision_id=pending.request_id,
        previous_contract_ref=pending.contract_ref,
        previous_contract_hash=pending.contract_hash,
        revised_contract_ref=decision.revised_contract_ref,
        revised_contract_hash=decision.revised_contract_hash,
        reason=f"Approved task revision request {pending.request_id}.",
        requested_by="judge_piworker",
        approved_by=decision.decided_by,
        evidence_refs=_unique_refs(
            [
                pending.source_revision_request_ref,
                pending.source_judge_report_ref,
                *pending.evidence_refs,
                *decision.rationale_refs,
            ]
        ),
    )
    _write_or_match_json(workspace, revision_ref, task_revision.to_dict(), "task_contract_revision")

    payload_without_hash = {
        "schema_version": REVISION_APPLIED_RECORD_SCHEMA_VERSION,
        "applied_id": _revision_applied_id(
            pending_ref=resolved_pending_ref,
            pending_hash=pending.pending_hash,
            revised_contract_hash=decision.revised_contract_hash,
        ),
        "run_id": pending.run_id,
        "contract_id": pending.contract_id,
        "previous_contract_hash": pending.contract_hash,
        "revised_contract_hash": decision.revised_contract_hash,
        "pending_ref": resolved_pending_ref,
        "pending_hash": pending.pending_hash,
        "task_revision_decision_ref": resolved_decision_ref,
        "task_contract_revision_ref": revision_ref,
        "previous_contract_ref": pending.contract_ref,
        "revised_contract_ref": decision.revised_contract_ref,
        "source_revision_request_ref": pending.source_revision_request_ref,
        "status": RevisionAppliedStatus.APPLIED.value,
    }
    applied = RevisionAppliedRecord(
        applied_hash=stable_json_hash(payload_without_hash),
        status=RevisionAppliedStatus.APPLIED,
        **{key: value for key, value in payload_without_hash.items() if key != "status"},
    )
    return _write_or_replay_applied(workspace, applied)


def _require_pending_source_bindings(pending: RevisionPendingRecord, workspace: RunWorkspace) -> None:
    result = _read_artifact(workspace, pending.source_result_ref, AgenticFlowResult, "agentic_flow_result")
    if result.status is not AgenticFlowStatus.REVISION_REQUIRED:
        raise ContractValidationError("revision_pending_record source result is not revision_required")
    if result.run_id != pending.run_id:
        raise ContractValidationError("revision_pending_record source result run_id does not match pending")
    if result.contract_id != pending.contract_id or result.contract_hash != pending.contract_hash:
        raise ContractValidationError("revision_pending_record source result contract does not match pending")
    if result.revision_request_ref != pending.source_revision_request_ref:
        raise ContractValidationError("revision_pending_record source result request ref does not match pending")
    if result.refs.contract_ref != pending.contract_ref:
        raise ContractValidationError("revision_pending_record source result contract ref does not match pending")
    if result.refs.judge_report_ref != pending.source_judge_report_ref:
        raise ContractValidationError("revision_pending_record source result judge report ref does not match pending")
    if result.refs.execution_packet_ref != pending.execution_packet_ref:
        raise ContractValidationError("revision_pending_record source result execution packet ref does not match pending")
    if result.refs.execution_report_ref != pending.execution_report_ref:
        raise ContractValidationError("revision_pending_record source result execution report ref does not match pending")
    if result.refs.judge_packet_ref != pending.judge_packet_ref:
        raise ContractValidationError("revision_pending_record source result judge packet ref does not match pending")
    if result.refs.judge_report_ref != pending.judge_report_ref:
        raise ContractValidationError("revision_pending_record source result judge report ref does not match pending")

    request = _read_artifact(
        workspace,
        pending.source_revision_request_ref,
        TaskRevisionRequest,
        "task_revision_request",
    )
    if request.request_id != pending.request_id:
        raise ContractValidationError("revision_pending_record request_id does not match source request")
    if request.run_id != pending.run_id:
        raise ContractValidationError("revision_pending_record request run_id does not match pending")
    if request.contract_id != pending.contract_id or request.contract_hash != pending.contract_hash:
        raise ContractValidationError("revision_pending_record request contract does not match pending")
    if request.contract_ref != pending.contract_ref:
        raise ContractValidationError("revision_pending_record request contract_ref does not match pending")
    request_authority = require_enum(
        request.authority_required,
        TaskRevisionAuthority,
        "task_revision_request.authority_required",
    )
    pending_authority = require_enum(
        pending.authority_required,
        TaskRevisionAuthority,
        "revision_pending_record.authority_required",
    )
    if request_authority is not pending_authority:
        raise ContractValidationError("revision_pending_record authority does not match source request")
    if request.judge_packet_ref != pending.judge_packet_ref:
        raise ContractValidationError("revision_pending_record request judge packet ref does not match pending")
    if request.judge_report_ref != pending.judge_report_ref:
        raise ContractValidationError("revision_pending_record request judge report ref does not match pending")
    if request.execution_report_ref != pending.execution_report_ref:
        raise ContractValidationError("revision_pending_record request execution report ref does not match pending")

    judge_packet = _read_artifact(workspace, pending.judge_packet_ref, JudgePacket, "judge_packet")
    judge_report = _read_artifact(workspace, pending.judge_report_ref, JudgeReport, "judge_report")
    if judge_report.decision is not JudgeReportDecision.REVISION_REQUIRED:
        raise ContractValidationError("revision_pending_record judge report is not revision_required")
    if judge_report.revision_request_ref != pending.source_revision_request_ref:
        raise ContractValidationError("revision_pending_record judge report request ref does not match pending")
    execution_packet = _read_artifact(
        workspace,
        pending.execution_packet_ref,
        AgentExecutionPacket,
        "agent_execution_packet",
    )
    execution_report = _read_artifact(
        workspace,
        pending.execution_report_ref,
        AgentExecutionReport,
        "agent_execution_report",
    )
    validate_revision_request_for_judge(request, judge_packet, judge_report, run_id=pending.run_id)
    validate_judge_packet_for_execution(
        judge_packet,
        execution_packet,
        execution_report,
        execution_packet_ref=pending.execution_packet_ref,
        execution_report_ref=pending.execution_report_ref,
    )


def _source_result_ref(source_result_ref: str | None, result: AgenticFlowResult) -> str:
    if source_result_ref is not None:
        return validate_ref(source_result_ref, "source_result_ref")
    result_hash = stable_json_hash(result.to_dict()).split(":", 1)[1]
    return f"results/result-{result_hash}.json"


def _pending_ref(request_id: str) -> str:
    safe_request_id = _validate_id(request_id, "revision_pending_record.request_id")
    return f"revisions/{safe_request_id}/revision_pending.json"


def _decision_ref(request_id: str) -> str:
    safe_request_id = _validate_id(request_id, "revision_pending_record.request_id")
    return f"revisions/{safe_request_id}/task_revision_decision.json"


def _task_contract_revision_ref(request_id: str) -> str:
    safe_request_id = _validate_id(request_id, "revision_pending_record.request_id")
    return f"revisions/{safe_request_id}/task_contract_revision.json"


def _applied_ref(applied: RevisionAppliedRecord) -> str:
    parts = applied.task_contract_revision_ref.split("/")
    if len(parts) >= 2 and parts[-1] == "task_contract_revision.json":
        request_id = parts[-2]
    else:
        request_id = applied.applied_id
    return f"revisions/{_validate_id(request_id, 'revision_applied_record.request_id')}/revision_applied.json"


def _write_or_replay_pending(workspace: RunWorkspace, record: RevisionPendingRecord) -> RevisionPendingRecord:
    record_ref = _pending_ref(record.request_id)
    record.validate()
    try:
        existing_payload = workspace.read_json(record_ref)
    except FileNotFoundError:
        workspace.write_json(record_ref, record.to_dict())
        return record
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"revision_pending_record is unreadable: {record_ref}") from exc

    existing_record = RevisionPendingRecord.from_dict(existing_payload)
    if existing_record.pending_hash != record.pending_hash:
        raise ContractValidationError("revision_pending_record replay conflict for deterministic pending_id")
    return existing_record


def _write_or_replay_applied(workspace: RunWorkspace, record: RevisionAppliedRecord) -> RevisionAppliedRecord:
    record_ref = _applied_ref(record)
    record.validate()
    try:
        existing_payload = workspace.read_json(record_ref)
    except FileNotFoundError:
        workspace.write_json(record_ref, record.to_dict())
        return record
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"revision_applied_record is unreadable: {record_ref}") from exc

    existing_record = RevisionAppliedRecord.from_dict(existing_payload)
    if existing_record.applied_hash != record.applied_hash:
        raise ContractValidationError("revision_applied_record replay conflict for deterministic applied_id")
    return existing_record


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


def _revision_pending_id(
    *,
    run_id: str,
    contract_hash: str,
    source_result_ref: str,
    source_revision_request_ref: str,
) -> str:
    seed = {
        "schema_version": REVISION_PENDING_RECORD_SCHEMA_VERSION,
        "run_id": require_non_empty_str(run_id, "revision_pending_id.run_id"),
        "contract_hash": _validate_hash(contract_hash, "revision_pending_id.contract_hash"),
        "source_result_ref": validate_ref(source_result_ref, "revision_pending_id.source_result_ref"),
        "source_revision_request_ref": validate_ref(
            source_revision_request_ref,
            "revision_pending_id.source_revision_request_ref",
        ),
    }
    return "revision-pending-" + stable_json_hash(seed).split(":", 1)[1]


def _revision_applied_id(*, pending_ref: str, pending_hash: str, revised_contract_hash: str) -> str:
    seed = {
        "schema_version": REVISION_APPLIED_RECORD_SCHEMA_VERSION,
        "pending_ref": validate_ref(pending_ref, "revision_applied_id.pending_ref"),
        "pending_hash": _validate_hash(pending_hash, "revision_applied_id.pending_hash"),
        "revised_contract_hash": _validate_hash(
            revised_contract_hash,
            "revision_applied_id.revised_contract_hash",
        ),
    }
    return "revision-applied-" + stable_json_hash(seed).split(":", 1)[1]


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
        safe_ref = validate_ref(ref, "agentic_revision_controller.ref")
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


def _is_checkpoint_ref(ref: str) -> bool:
    safe_ref = validate_ref(ref, "checkpoint_ref")
    return safe_ref == "checkpoints" or safe_ref.startswith("checkpoints/")


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"unsupported {field_name}: {actual}")


__all__ = [
    "REVISION_APPLIED_RECORD_SCHEMA_VERSION",
    "REVISION_PENDING_RECORD_SCHEMA_VERSION",
    "RevisionAppliedRecord",
    "RevisionAppliedStatus",
    "RevisionPendingRecord",
    "RevisionPendingStatus",
    "apply_task_contract_revision",
    "build_revision_pending_record",
]
