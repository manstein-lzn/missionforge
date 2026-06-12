"""Revision pending/application controller for TaskContract agentic flow."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
import json
from typing import Any, Mapping

from .agent_packets import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    HardCheckStatus,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
    validate_judge_packet_for_execution,
    validate_judge_report_for_packet,
)
from .agentic_flow import AgenticFlowRefs, AgenticFlowResult, AgenticFlowStatus
from .agentic_ledger import (
    DecisionLedgerEventKind,
    TaskContractDecisionLedgerEntry,
    append_decision_ledger_entry,
    build_final_package,
    next_ledger_entry_id,
    read_decision_ledger,
)
from .agentic_repair import (
    RepairBrief,
    TaskRevisionAuthority,
    TaskRevisionDecision,
    TaskRevisionDecisionStatus,
    TaskRevisionRequest,
    validate_repair_brief_for_judge,
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
from .permissions import ref_is_under
from .task_contract import PermissionManifest, TaskContract, TaskContractRevision, WorkspacePolicy
from .task_projection import project_judge_rubric, project_worker_brief
from .workspace_runtime import RunWorkspace


REVISION_PENDING_RECORD_SCHEMA_VERSION = "revision_pending_record.v1"
REVISION_APPLIED_RECORD_SCHEMA_VERSION = "revision_applied_record.v1"
REVISION_EXECUTION_DIRECTIVE_SCHEMA_VERSION = "revision_execution_directive.v1"


class RevisionPendingStatus(StrEnum):
    """Status for a revision request awaiting authority/application."""

    PENDING = "pending"


class RevisionAppliedStatus(StrEnum):
    """Status for an applied TaskContract revision."""

    APPLIED = "applied"


class RevisionExecutionDirectiveStatus(StrEnum):
    """Status for a prepared post-revision execution directive."""

    READY = "ready"


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


@dataclass(frozen=True)
class RevisionExecutionDirective:
    """Refs-only directive for the first execution attempt under revised authority."""

    directive_id: str
    directive_hash: str
    run_id: str
    contract_id: str
    contract_hash: str
    previous_contract_hash: str
    revision_applied_ref: str
    revision_applied_hash: str
    task_revision_decision_ref: str
    task_contract_revision_ref: str
    previous_contract_ref: str
    revised_contract_ref: str
    source_revision_request_ref: str
    worker_brief_ref: str
    execution_packet_ref: str
    execution_report_ref: str
    expected_artifact_refs: list[str] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    status: RevisionExecutionDirectiveStatus = RevisionExecutionDirectiveStatus.READY
    schema_version: str = REVISION_EXECUTION_DIRECTIVE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RevisionExecutionDirective":
        data = _strict_mapping(
            payload,
            "revision_execution_directive",
            {
                "schema_version",
                "directive_id",
                "directive_hash",
                "run_id",
                "contract_id",
                "contract_hash",
                "previous_contract_hash",
                "revision_applied_ref",
                "revision_applied_hash",
                "task_revision_decision_ref",
                "task_contract_revision_ref",
                "previous_contract_ref",
                "revised_contract_ref",
                "source_revision_request_ref",
                "worker_brief_ref",
                "execution_packet_ref",
                "execution_report_ref",
                "expected_artifact_refs",
                "context_refs",
                "status",
            },
        )
        directive = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", REVISION_EXECUTION_DIRECTIVE_SCHEMA_VERSION),
                "revision_execution_directive.schema_version",
            ),
            directive_id=_validate_id(data.get("directive_id"), "revision_execution_directive.directive_id"),
            directive_hash=_validate_hash(
                data.get("directive_hash"),
                "revision_execution_directive.directive_hash",
            ),
            run_id=require_non_empty_str(data.get("run_id"), "revision_execution_directive.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "revision_execution_directive.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "revision_execution_directive.contract_hash"),
            previous_contract_hash=_validate_hash(
                data.get("previous_contract_hash"),
                "revision_execution_directive.previous_contract_hash",
            ),
            revision_applied_ref=validate_ref(
                data.get("revision_applied_ref"),
                "revision_execution_directive.revision_applied_ref",
            ),
            revision_applied_hash=_validate_hash(
                data.get("revision_applied_hash"),
                "revision_execution_directive.revision_applied_hash",
            ),
            task_revision_decision_ref=validate_ref(
                data.get("task_revision_decision_ref"),
                "revision_execution_directive.task_revision_decision_ref",
            ),
            task_contract_revision_ref=validate_ref(
                data.get("task_contract_revision_ref"),
                "revision_execution_directive.task_contract_revision_ref",
            ),
            previous_contract_ref=validate_ref(
                data.get("previous_contract_ref"),
                "revision_execution_directive.previous_contract_ref",
            ),
            revised_contract_ref=validate_ref(
                data.get("revised_contract_ref"),
                "revision_execution_directive.revised_contract_ref",
            ),
            source_revision_request_ref=validate_ref(
                data.get("source_revision_request_ref"),
                "revision_execution_directive.source_revision_request_ref",
            ),
            worker_brief_ref=validate_ref(
                data.get("worker_brief_ref"),
                "revision_execution_directive.worker_brief_ref",
            ),
            execution_packet_ref=validate_ref(
                data.get("execution_packet_ref"),
                "revision_execution_directive.execution_packet_ref",
            ),
            execution_report_ref=validate_ref(
                data.get("execution_report_ref"),
                "revision_execution_directive.execution_report_ref",
            ),
            expected_artifact_refs=_ref_list(
                data.get("expected_artifact_refs", []),
                "revision_execution_directive.expected_artifact_refs",
            ),
            context_refs=_ref_list(data.get("context_refs", []), "revision_execution_directive.context_refs"),
            status=require_enum(
                data.get("status", RevisionExecutionDirectiveStatus.READY.value),
                RevisionExecutionDirectiveStatus,
                "revision_execution_directive.status",
            ),
        )
        directive.validate()
        return directive

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            REVISION_EXECUTION_DIRECTIVE_SCHEMA_VERSION,
            "revision_execution_directive.schema_version",
        )
        _validate_id(self.directive_id, "revision_execution_directive.directive_id")
        _validate_hash(self.directive_hash, "revision_execution_directive.directive_hash")
        require_non_empty_str(self.run_id, "revision_execution_directive.run_id")
        require_non_empty_str(self.contract_id, "revision_execution_directive.contract_id")
        _validate_hash(self.contract_hash, "revision_execution_directive.contract_hash")
        _validate_hash(self.previous_contract_hash, "revision_execution_directive.previous_contract_hash")
        if self.contract_hash == self.previous_contract_hash:
            raise ContractValidationError("revision_execution_directive must use the revised contract hash")
        validate_ref(self.revision_applied_ref, "revision_execution_directive.revision_applied_ref")
        _validate_hash(self.revision_applied_hash, "revision_execution_directive.revision_applied_hash")
        validate_ref(self.task_revision_decision_ref, "revision_execution_directive.task_revision_decision_ref")
        validate_ref(self.task_contract_revision_ref, "revision_execution_directive.task_contract_revision_ref")
        validate_ref(self.previous_contract_ref, "revision_execution_directive.previous_contract_ref")
        validate_ref(self.revised_contract_ref, "revision_execution_directive.revised_contract_ref")
        validate_ref(self.source_revision_request_ref, "revision_execution_directive.source_revision_request_ref")
        validate_ref(self.worker_brief_ref, "revision_execution_directive.worker_brief_ref")
        validate_ref(self.execution_packet_ref, "revision_execution_directive.execution_packet_ref")
        validate_ref(self.execution_report_ref, "revision_execution_directive.execution_report_ref")
        _validate_unique_refs(self.expected_artifact_refs, "revision_execution_directive.expected_artifact_refs")
        _validate_unique_refs(self.context_refs, "revision_execution_directive.context_refs")
        require_enum(self.status, RevisionExecutionDirectiveStatus, "revision_execution_directive.status")
        expected_id = _revision_execution_directive_id(
            revision_applied_ref=self.revision_applied_ref,
            revision_applied_hash=self.revision_applied_hash,
            revised_contract_hash=self.contract_hash,
        )
        if self.directive_id != expected_id:
            raise ContractValidationError(
                "revision_execution_directive.directive_id does not match deterministic id seed"
            )
        expected_hash = stable_json_hash(self.to_dict_without_hash())
        if self.directive_hash != expected_hash:
            raise ContractValidationError(
                "revision_execution_directive.directive_hash does not match directive content"
            )
        assert_refs_only_payload(self.to_dict_without_validation(), "revision_execution_directive")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "directive_id": self.directive_id,
            "run_id": self.run_id,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "previous_contract_hash": self.previous_contract_hash,
            "revision_applied_ref": self.revision_applied_ref,
            "revision_applied_hash": self.revision_applied_hash,
            "task_revision_decision_ref": self.task_revision_decision_ref,
            "task_contract_revision_ref": self.task_contract_revision_ref,
            "previous_contract_ref": self.previous_contract_ref,
            "revised_contract_ref": self.revised_contract_ref,
            "source_revision_request_ref": self.source_revision_request_ref,
            "worker_brief_ref": self.worker_brief_ref,
            "execution_packet_ref": self.execution_packet_ref,
            "execution_report_ref": self.execution_report_ref,
            "expected_artifact_refs": list(self.expected_artifact_refs),
            "context_refs": list(self.context_refs),
            "status": require_enum(
                self.status,
                RevisionExecutionDirectiveStatus,
                "revision_execution_directive.status",
            ).value,
        }

    def to_dict_without_validation(self) -> dict[str, Any]:
        payload = self.to_dict_without_hash()
        payload["directive_hash"] = self.directive_hash
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


def load_revision_draft_contract(
    *,
    pending: RevisionPendingRecord,
    call_result: Any,
    workspace: RunWorkspace,
    expected_output_ref: str,
    revision_pending_ref: str | None = None,
) -> TaskContract:
    """Load and validate a revision-drafter TaskContract proposal.

    This validates the PiWorker boundary and revised contract shape only. It
    does not approve or apply the revision; callers must still provide an
    authority-matching TaskRevisionDecision and call
    apply_task_contract_revision(...).
    """

    from .piworker_call import PiWorkerCallResult, PiWorkerCallResultStatus, PiWorkerCallRole

    pending.validate()
    if not isinstance(call_result, PiWorkerCallResult):
        call_result = PiWorkerCallResult.from_dict(require_mapping(call_result, "piworker_call_result"))
    call_result.validate()
    workspace.permission_manifest.validate()

    resolved_pending_ref = revision_pending_ref or _pending_ref(pending.request_id)
    _load_and_match(workspace, resolved_pending_ref, RevisionPendingRecord, pending, "revision_pending_record")
    _require_pending_source_bindings(pending, workspace)

    if call_result.role is not PiWorkerCallRole.REVISION_DRAFTER:
        raise ContractValidationError("revision_draft_contract requires revision_drafter_piworker call result")
    if call_result.call_id != pending.pending_id:
        raise ContractValidationError("revision_draft_contract call result does not match pending record")
    if call_result.contract_id != pending.contract_id:
        raise ContractValidationError("revision_draft_contract call result contract_id does not match pending")
    if call_result.contract_hash != pending.contract_hash:
        raise ContractValidationError("revision_draft_contract call result contract_hash does not match pending")
    if call_result.contract_ref != pending.contract_ref:
        raise ContractValidationError("revision_draft_contract call result contract_ref does not match pending")
    if call_result.status is not PiWorkerCallResultStatus.COMPLETED:
        raise ContractValidationError("revision_draft_contract requires completed PiWorkerCallResult")

    draft_ref = validate_ref(expected_output_ref, "revision_draft_contract.expected_output_ref")
    if draft_ref not in call_result.output_refs:
        raise ContractValidationError("revision_draft_contract expected output ref is missing from call result")
    call_result_ref = _piworker_call_result_ref(call_result.call_id)
    _match_existing_json(workspace, call_result_ref, call_result.to_dict(), "piworker_call_result")
    revised_contract = _read_artifact(workspace, draft_ref, TaskContract, "revision_draft_contract")
    if revised_contract.contract_id != pending.contract_id:
        raise ContractValidationError("revision_draft_contract contract_id does not match pending")
    if revised_contract.contract_hash == pending.contract_hash:
        raise ContractValidationError("revision_draft_contract must change contract hash")
    return revised_contract


def build_revision_execution_directive(
    *,
    applied: RevisionAppliedRecord,
    revised_contract: TaskContract,
    workspace_policy: WorkspacePolicy,
    permission_manifest: PermissionManifest,
    workspace: RunWorkspace,
    revision_applied_ref: str | None = None,
    run_id: str | None = None,
) -> RevisionExecutionDirective:
    """Prepare the first execution packet under explicit revised task authority.

    This is a continuation primitive only. It freezes the revised contract into
    executor-facing projections and a new execution packet, but it does not run
    a worker and does not grant acceptance.
    """

    applied.validate()
    revised_contract.to_dict()
    workspace_policy.validate()
    permission_manifest.validate()
    workspace.permission_manifest.validate()
    if permission_manifest.unsupported_hard_policies:
        raise ContractValidationError("revision_execution_directive cannot run with unsupported hard policies")

    applied_ref = revision_applied_ref or _applied_ref(applied)
    _load_and_match(workspace, applied_ref, RevisionAppliedRecord, applied, "revision_applied_record")
    _require_applied_source_bindings(applied, workspace)
    _load_and_match(workspace, applied.revised_contract_ref, TaskContract, revised_contract, "revised_task_contract")
    if revised_contract.contract_hash != applied.revised_contract_hash:
        raise ContractValidationError("revision_execution_directive revised contract hash does not match applied record")
    if revised_contract.contract_hash == applied.previous_contract_hash:
        raise ContractValidationError("revision_execution_directive requires a changed revised contract")
    _match_existing_json(
        workspace,
        revised_contract.workspace_policy_ref,
        workspace_policy.to_dict(),
        "workspace_policy",
    )
    _match_existing_json(
        workspace,
        revised_contract.permission_manifest_ref,
        permission_manifest.to_dict(),
        "permission_manifest",
    )

    request_id = _request_id_from_revision_ref(applied.task_contract_revision_ref)
    effective_run_id = run_id or applied.run_id
    revision_execution_id = f"{effective_run_id}-revision-{request_id}"
    worker_brief_ref = f"revisions/{request_id}/projections/worker_brief.json"
    execution_packet_ref = f"revisions/{request_id}/packets/execution_packet.json"
    execution_report_ref = f"revisions/{request_id}/reports/execution_report.json"

    expected_artifact_refs = _expected_artifact_refs(revised_contract)
    _ensure_refs_under_artifact_roots(expected_artifact_refs, workspace_policy.artifact_root_refs)
    worker_brief = project_worker_brief(
        revised_contract,
        workspace_policy,
        permission_manifest,
        brief_id=f"{revision_execution_id}-worker-brief",
        contract_ref=applied.revised_contract_ref,
        completion_report_ref=execution_report_ref,
    )
    worker_brief_payload = worker_brief.to_dict()
    _write_or_match_json(workspace, worker_brief_ref, worker_brief_payload, "revision_worker_brief")

    context_refs = _unique_refs(
        [
            applied_ref,
            applied.pending_ref,
            applied.task_revision_decision_ref,
            applied.task_contract_revision_ref,
            applied.source_revision_request_ref,
        ]
    )
    execution_packet = AgentExecutionPacket(
        packet_id=f"{revision_execution_id}-execution-packet",
        contract_id=revised_contract.contract_id,
        contract_hash=revised_contract.contract_hash,
        contract_ref=applied.revised_contract_ref,
        worker_brief_ref=worker_brief_ref,
        workspace_policy_ref=revised_contract.workspace_policy_ref,
        permission_manifest_ref=revised_contract.permission_manifest_ref,
        report_ref=execution_report_ref,
        worker_brief_hash=stable_json_hash(worker_brief_payload),
        workspace_policy_hash=stable_json_hash(workspace_policy.to_dict()),
        permission_manifest_hash=stable_json_hash(permission_manifest.to_dict()),
        expected_artifact_refs=expected_artifact_refs,
        allowed_input_refs=_unique_refs([*worker_brief.allowed_input_refs, *context_refs]),
        writable_refs=list(worker_brief.writable_refs),
    )
    _write_or_match_json(workspace, execution_packet_ref, execution_packet.to_dict(), "revision_execution_packet")

    payload_without_hash: dict[str, Any] = {
        "schema_version": REVISION_EXECUTION_DIRECTIVE_SCHEMA_VERSION,
        "directive_id": _revision_execution_directive_id(
            revision_applied_ref=applied_ref,
            revision_applied_hash=applied.applied_hash,
            revised_contract_hash=applied.revised_contract_hash,
        ),
        "run_id": effective_run_id,
        "contract_id": applied.contract_id,
        "contract_hash": applied.revised_contract_hash,
        "previous_contract_hash": applied.previous_contract_hash,
        "revision_applied_ref": applied_ref,
        "revision_applied_hash": applied.applied_hash,
        "task_revision_decision_ref": applied.task_revision_decision_ref,
        "task_contract_revision_ref": applied.task_contract_revision_ref,
        "previous_contract_ref": applied.previous_contract_ref,
        "revised_contract_ref": applied.revised_contract_ref,
        "source_revision_request_ref": applied.source_revision_request_ref,
        "worker_brief_ref": worker_brief_ref,
        "execution_packet_ref": execution_packet_ref,
        "execution_report_ref": execution_report_ref,
        "expected_artifact_refs": expected_artifact_refs,
        "context_refs": context_refs,
        "status": RevisionExecutionDirectiveStatus.READY.value,
    }
    directive = RevisionExecutionDirective(
        schema_version=REVISION_EXECUTION_DIRECTIVE_SCHEMA_VERSION,
        directive_hash=stable_json_hash(payload_without_hash),
        status=RevisionExecutionDirectiveStatus.READY,
        **{key: value for key, value in payload_without_hash.items() if key not in {"schema_version", "status"}},
    )
    return _write_or_replay_revision_execution_directive(workspace, directive)


def build_revision_rejudge_packet(
    *,
    directive: RevisionExecutionDirective,
    call_result: Any,
    workspace: RunWorkspace,
    revision_execution_directive_ref: str | None = None,
    judge_packet_ref: str | None = None,
    judge_report_ref: str | None = None,
    judge_rubric_ref: str | None = None,
    hard_check_status: HardCheckStatus | str = HardCheckStatus.MISSING,
    hard_check_refs: list[str] | None = None,
) -> JudgePacket:
    """Turn one revised-contract execution result into an independent judge packet.

    This bridge records execution evidence for the revised contract and prepares
    a separate judge packet. It is not an acceptance shortcut.
    """

    from .piworker_call import PiWorkerCallResult, PiWorkerCallResultStatus, PiWorkerCallRole

    directive.validate()
    if not isinstance(call_result, PiWorkerCallResult):
        call_result = PiWorkerCallResult.from_dict(require_mapping(call_result, "piworker_call_result"))
    call_result.validate()
    workspace.permission_manifest.validate()

    directive_ref = revision_execution_directive_ref or _revision_execution_directive_ref(directive)
    _load_and_match(
        workspace,
        directive_ref,
        RevisionExecutionDirective,
        directive,
        "revision_execution_directive",
    )
    applied = _read_artifact(workspace, directive.revision_applied_ref, RevisionAppliedRecord, "revision_applied_record")
    if applied.applied_hash != directive.revision_applied_hash:
        raise ContractValidationError("revision_rejudge_packet applied hash does not match directive")
    if applied.revised_contract_hash != directive.contract_hash:
        raise ContractValidationError("revision_rejudge_packet applied contract hash does not match directive")
    if applied.previous_contract_hash != directive.previous_contract_hash:
        raise ContractValidationError("revision_rejudge_packet previous contract hash does not match directive")
    _require_applied_source_bindings(applied, workspace)

    execution_packet = _read_artifact(
        workspace,
        directive.execution_packet_ref,
        AgentExecutionPacket,
        "revision_execution_packet",
    )
    if execution_packet.contract_hash != directive.contract_hash:
        raise ContractValidationError("revision_rejudge_packet execution packet contract hash does not match directive")
    if execution_packet.contract_ref != directive.revised_contract_ref:
        raise ContractValidationError("revision_rejudge_packet execution packet contract ref does not match directive")
    if execution_packet.report_ref != directive.execution_report_ref:
        raise ContractValidationError("revision_rejudge_packet execution packet report ref does not match directive")
    if execution_packet.expected_artifact_refs != directive.expected_artifact_refs:
        raise ContractValidationError("revision_rejudge_packet execution packet expected refs do not match directive")

    if call_result.role is not PiWorkerCallRole.EXECUTOR:
        raise ContractValidationError("revision_rejudge_packet requires executor_piworker call result")
    if call_result.call_id != execution_packet.packet_id:
        raise ContractValidationError("revision_rejudge_packet call result does not match execution packet")
    if call_result.contract_id != directive.contract_id:
        raise ContractValidationError("revision_rejudge_packet call result contract_id does not match directive")
    if call_result.contract_hash != directive.contract_hash:
        raise ContractValidationError("revision_rejudge_packet call result contract_hash does not match directive")
    if call_result.contract_ref != directive.revised_contract_ref:
        raise ContractValidationError("revision_rejudge_packet call result contract_ref does not match directive")
    if call_result.status is PiWorkerCallResultStatus.COMPLETED:
        missing_outputs = sorted(set(directive.expected_artifact_refs) - set(call_result.output_refs))
        if missing_outputs:
            raise ContractValidationError(f"revision_rejudge_packet missing revised output refs: {missing_outputs}")

    call_result_ref = _piworker_call_result_ref(call_result.call_id)
    _match_existing_json(workspace, call_result_ref, call_result.to_dict(), "piworker_call_result")
    produced_refs = list(call_result.output_refs)
    if call_result.status is PiWorkerCallResultStatus.COMPLETED:
        _ensure_existing_refs(workspace, directive.expected_artifact_refs, "revision_output_refs")

    revision_execution_report = AgentExecutionReport(
        report_id=f"{directive.directive_id}-revision-execution-report",
        packet_id=execution_packet.packet_id,
        packet_ref=directive.execution_packet_ref,
        packet_hash=stable_json_hash(execution_packet.to_dict()),
        contract_id=directive.contract_id,
        contract_hash=directive.contract_hash,
        contract_ref=directive.revised_contract_ref,
        status=_execution_status_from_call_result(call_result.status),
        produced_artifact_refs=produced_refs,
        changed_refs=produced_refs,
        evidence_refs=_unique_refs([call_result_ref, *call_result.evidence_refs]),
        metric_refs=list(call_result.metric_refs),
    )
    revision_execution_report_payload = revision_execution_report.to_dict()
    _write_or_match_json(
        workspace,
        directive.execution_report_ref,
        revision_execution_report_payload,
        "revision_execution_report",
    )

    hard_status = require_enum(hard_check_status, HardCheckStatus, "revision_rejudge_packet.hard_check_status")
    hard_refs = _ref_list(hard_check_refs or [], "hard_check_refs")
    if hard_status is HardCheckStatus.PASSED and not hard_refs:
        raise ContractValidationError("revision_rejudge_packet hard_check_status passed requires hard_check_refs")
    _ensure_existing_refs(workspace, hard_refs, "hard_check_refs")

    revised_contract = _read_artifact(workspace, directive.revised_contract_ref, TaskContract, "revised_task_contract")
    workspace_policy = _read_artifact(
        workspace,
        revised_contract.workspace_policy_ref,
        WorkspacePolicy,
        "workspace_policy",
    )
    request_id = _request_id_from_revision_ref(directive.task_contract_revision_ref)
    effective_judge_rubric_ref = judge_rubric_ref or _revision_judge_rubric_ref(request_id)
    judge_rubric = project_judge_rubric(
        revised_contract,
        workspace_policy,
        rubric_id=f"{directive.run_id}-judge-rubric",
        contract_ref=directive.revised_contract_ref,
        evidence_refs=[directive.execution_report_ref],
        hard_check_refs=hard_refs,
    )
    judge_rubric_payload = judge_rubric.to_dict()
    _write_or_match_json(workspace, effective_judge_rubric_ref, judge_rubric_payload, "revision_judge_rubric")

    next_judge_packet_ref = judge_packet_ref or _revision_judge_packet_ref(request_id)
    next_judge_report_ref = judge_report_ref or _revision_judge_report_ref(request_id)
    rejudge_packet = JudgePacket(
        packet_id=f"{directive.directive_id}-judge-packet",
        contract_id=directive.contract_id,
        contract_hash=directive.contract_hash,
        contract_ref=directive.revised_contract_ref,
        judge_rubric_ref=effective_judge_rubric_ref,
        judge_rubric_hash=stable_json_hash(judge_rubric_payload),
        execution_packet_ref=directive.execution_packet_ref,
        execution_packet_hash=stable_json_hash(execution_packet.to_dict()),
        execution_report_ref=directive.execution_report_ref,
        execution_report_hash=stable_json_hash(revision_execution_report_payload),
        report_ref=next_judge_report_ref,
        hard_check_status=hard_status,
        artifact_refs=produced_refs,
        evidence_refs=_unique_refs(
            [
                directive.execution_report_ref,
                call_result_ref,
                *revision_execution_report.evidence_refs,
                *directive.context_refs,
            ]
        ),
        hard_check_refs=hard_refs,
    )
    validate_judge_packet_for_execution(
        rejudge_packet,
        execution_packet,
        revision_execution_report,
        execution_packet_ref=directive.execution_packet_ref,
        execution_report_ref=directive.execution_report_ref,
        execution_packet_hash=stable_json_hash(execution_packet.to_dict()),
        execution_report_hash=stable_json_hash(revision_execution_report_payload),
    )
    _write_or_match_json(workspace, next_judge_packet_ref, rejudge_packet.to_dict(), "revision_rejudge_packet")
    return rejudge_packet


def build_revision_judge_result(
    *,
    directive: RevisionExecutionDirective,
    judge_packet: JudgePacket,
    judge_report: JudgeReport,
    workspace: RunWorkspace,
    revision_execution_directive_ref: str | None = None,
    judge_packet_ref: str | None = None,
    decision_ledger_ref: str = "ledgers/decision_ledger.jsonl",
) -> AgenticFlowResult:
    """Record an independent revised-contract judge result.

    The result may become accepted, repair, revision_required, or rejected, but
    only after validating the revised execution report and judge report. The
    executor's output alone never grants acceptance.
    """

    directive.validate()
    judge_packet.validate()
    judge_report.validate()
    workspace.permission_manifest.validate()

    directive_ref = revision_execution_directive_ref or _revision_execution_directive_ref(directive)
    packet_ref = judge_packet_ref or _revision_judge_packet_ref(
        _request_id_from_revision_ref(directive.task_contract_revision_ref)
    )
    ledger_ref = validate_ref(decision_ledger_ref, "decision_ledger_ref")

    _load_and_match(
        workspace,
        directive_ref,
        RevisionExecutionDirective,
        directive,
        "revision_execution_directive",
    )
    _load_and_match(workspace, packet_ref, JudgePacket, judge_packet, "revision_judge_packet")
    applied = _read_artifact(workspace, directive.revision_applied_ref, RevisionAppliedRecord, "revision_applied_record")
    if applied.applied_hash != directive.revision_applied_hash:
        raise ContractValidationError("revision_judge_result applied hash does not match directive")
    _require_applied_source_bindings(applied, workspace)

    execution_packet = _read_artifact(
        workspace,
        directive.execution_packet_ref,
        AgentExecutionPacket,
        "revision_execution_packet",
    )
    execution_report = _read_artifact(
        workspace,
        directive.execution_report_ref,
        AgentExecutionReport,
        "revision_execution_report",
    )
    validate_judge_packet_for_execution(
        judge_packet,
        execution_packet,
        execution_report,
        execution_packet_ref=directive.execution_packet_ref,
        execution_report_ref=directive.execution_report_ref,
        execution_packet_hash=stable_json_hash(execution_packet.to_dict()),
        execution_report_hash=stable_json_hash(execution_report.to_dict()),
    )
    judge_packet_hash = stable_json_hash(judge_packet.to_dict())
    if judge_report.packet_hash is None:
        judge_report = replace(judge_report, packet_hash=judge_packet_hash)
    validate_judge_report_for_packet(
        judge_report,
        judge_packet,
        packet_ref=packet_ref,
        packet_hash=judge_packet_hash,
    )
    if (
        judge_report.decision is JudgeReportDecision.ACCEPTED
        and execution_report.status is not AgentExecutionStatus.COMPLETED
    ):
        raise ContractValidationError("revision_judge_result accepted requires completed execution")
    if judge_report.decision is JudgeReportDecision.ACCEPTED:
        _ensure_expected_artifacts_accepted(
            directive.expected_artifact_refs,
            execution_report,
            judge_report,
            workspace,
        )
    _ensure_revision_judge_decision_artifact(directive.run_id, judge_report, judge_packet, workspace)
    judge_report_payload = judge_report.to_dict()
    _write_or_match_json(workspace, judge_packet.report_ref, judge_report_payload, "revision_judge_report")

    request_id = _request_id_from_revision_ref(directive.task_contract_revision_ref)
    flow_refs = AgenticFlowRefs(
        contract_ref=directive.revised_contract_ref,
        worker_brief_ref=directive.worker_brief_ref,
        execution_packet_ref=directive.execution_packet_ref,
        execution_report_ref=directive.execution_report_ref,
        judge_packet_ref=packet_ref,
        judge_report_ref=judge_packet.report_ref,
        decision_ledger_ref=ledger_ref,
        final_package_ref=f"revisions/{request_id}/packages/final_package.json",
        checkpoint_ref=f"revisions/{request_id}/checkpoints/latest.json",
    )
    result = AgenticFlowResult(
        run_id=directive.run_id,
        contract_id=directive.contract_id,
        contract_hash=directive.contract_hash,
        status=_flow_status_from_judge_decision(judge_report.decision),
        execution_status=execution_report.status,
        judge_decision=judge_report.decision,
        accepted_artifact_refs=list(judge_report.accepted_artifact_refs),
        repair_brief_ref=judge_report.repair_brief_ref,
        revision_request_ref=judge_report.revision_request_ref,
        refs=flow_refs,
    )
    result.validate()
    result_ref = _revision_result_ref(request_id, result)
    _write_or_match_json(workspace, result_ref, result.to_dict(), "revision_agentic_flow_result")
    _write_or_match_json(workspace, flow_refs.checkpoint_ref, result.to_dict(), "revision_checkpoint")

    _append_revision_applied_ledger_entry_once(
        workspace=workspace,
        decision_ledger_ref=ledger_ref,
        applied=applied,
    )
    _append_ledger_entry_once(
        workspace=workspace,
        decision_ledger_ref=ledger_ref,
        event_kind=DecisionLedgerEventKind.REVISION_JUDGE_REPORT_RECORDED,
        run_id=directive.run_id,
        contract_id=directive.contract_id,
        contract_hash=directive.contract_hash,
        status=result.status.value,
        refs={
            "revision_execution_directive_ref": directive_ref,
            "revision_applied_ref": directive.revision_applied_ref,
            "task_contract_revision_ref": directive.task_contract_revision_ref,
            "judge_packet_ref": packet_ref,
            "judge_report_ref": judge_packet.report_ref,
            "checkpoint_ref": flow_refs.checkpoint_ref,
            "result_ref": result_ref,
        },
        content_hashes={
            judge_packet.report_ref: stable_json_hash(judge_report_payload),
            result_ref: stable_json_hash(result.to_dict()),
        },
    )

    if result.status is AgenticFlowStatus.ACCEPTED:
        final_package = build_final_package(
            run_id=directive.run_id,
            contract_id=directive.contract_id,
            contract_hash=directive.contract_hash,
            contract_ref=directive.revised_contract_ref,
            judge_report_ref=judge_packet.report_ref,
            decision_ledger_ref=ledger_ref,
            accepted_artifact_refs=result.accepted_artifact_refs,
            hard_check_refs=list(judge_packet.hard_check_refs),
            metric_refs=list(execution_report.metric_refs),
            product_payload_refs=list(directive.context_refs),
        )
        final_package_payload = final_package.to_dict()
        _write_or_match_json(workspace, flow_refs.final_package_ref, final_package_payload, "revision_final_package")
        _append_ledger_entry_once(
            workspace=workspace,
            decision_ledger_ref=ledger_ref,
            event_kind=DecisionLedgerEventKind.FINAL_PACKAGE_EMITTED,
            run_id=directive.run_id,
            contract_id=directive.contract_id,
            contract_hash=directive.contract_hash,
            status=result.status.value,
            refs={
                "final_package_ref": flow_refs.final_package_ref,
                "judge_report_ref": judge_packet.report_ref,
                "decision_ledger_ref": ledger_ref,
                "revision_applied_ref": directive.revision_applied_ref,
                "task_contract_revision_ref": directive.task_contract_revision_ref,
            },
            content_hashes={flow_refs.final_package_ref: stable_json_hash(final_package_payload)},
        )
    return result


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


def _require_applied_source_bindings(applied: RevisionAppliedRecord, workspace: RunWorkspace) -> None:
    pending = _read_artifact(workspace, applied.pending_ref, RevisionPendingRecord, "revision_pending_record")
    if pending.pending_hash != applied.pending_hash:
        raise ContractValidationError("revision_applied_record pending hash does not match pending record")
    if pending.run_id != applied.run_id:
        raise ContractValidationError("revision_applied_record run_id does not match pending")
    if pending.contract_id != applied.contract_id:
        raise ContractValidationError("revision_applied_record contract_id does not match pending")
    if pending.contract_hash != applied.previous_contract_hash:
        raise ContractValidationError("revision_applied_record previous contract hash does not match pending")
    if pending.contract_ref != applied.previous_contract_ref:
        raise ContractValidationError("revision_applied_record previous contract ref does not match pending")
    if pending.source_revision_request_ref != applied.source_revision_request_ref:
        raise ContractValidationError("revision_applied_record source request ref does not match pending")
    _require_pending_source_bindings(pending, workspace)

    decision = _read_artifact(
        workspace,
        applied.task_revision_decision_ref,
        TaskRevisionDecision,
        "task_revision_decision",
    )
    if decision.decision is not TaskRevisionDecisionStatus.APPROVED:
        raise ContractValidationError("revision_applied_record decision is not approved")
    if decision.request_id != pending.request_id:
        raise ContractValidationError("revision_applied_record decision request_id does not match pending")
    if decision.request_ref != applied.source_revision_request_ref:
        raise ContractValidationError("revision_applied_record decision request ref does not match applied")
    if decision.current_contract_ref != applied.previous_contract_ref:
        raise ContractValidationError("revision_applied_record decision current contract ref does not match applied")
    if decision.current_contract_hash != applied.previous_contract_hash:
        raise ContractValidationError("revision_applied_record decision current contract hash does not match applied")
    if decision.revised_contract_ref != applied.revised_contract_ref:
        raise ContractValidationError("revision_applied_record decision revised contract ref does not match applied")
    if decision.revised_contract_hash != applied.revised_contract_hash:
        raise ContractValidationError("revision_applied_record decision revised contract hash does not match applied")

    task_revision = _read_artifact(
        workspace,
        applied.task_contract_revision_ref,
        TaskContractRevision,
        "task_contract_revision",
    )
    if task_revision.previous_contract_ref != applied.previous_contract_ref:
        raise ContractValidationError("task_contract_revision previous contract ref does not match applied")
    if task_revision.previous_contract_hash != applied.previous_contract_hash:
        raise ContractValidationError("task_contract_revision previous contract hash does not match applied")
    if task_revision.revised_contract_ref != applied.revised_contract_ref:
        raise ContractValidationError("task_contract_revision revised contract ref does not match applied")
    if task_revision.revised_contract_hash != applied.revised_contract_hash:
        raise ContractValidationError("task_contract_revision revised contract hash does not match applied")

    previous_contract = _read_artifact(workspace, applied.previous_contract_ref, TaskContract, "previous_task_contract")
    if previous_contract.contract_hash != applied.previous_contract_hash:
        raise ContractValidationError("previous task contract hash does not match applied")
    revised_contract = _read_artifact(workspace, applied.revised_contract_ref, TaskContract, "revised_task_contract")
    if revised_contract.contract_hash != applied.revised_contract_hash:
        raise ContractValidationError("revised task contract hash does not match applied")


def _ensure_revision_judge_decision_artifact(
    run_id: str,
    report: JudgeReport,
    packet: JudgePacket,
    workspace: RunWorkspace,
) -> None:
    if report.decision is JudgeReportDecision.REPAIR:
        if report.repair_brief_ref is None:
            raise ContractValidationError("revision_judge_result repair requires repair_brief_ref")
        brief = _read_artifact(workspace, report.repair_brief_ref, RepairBrief, "repair_brief")
        validate_repair_brief_for_judge(brief, packet, report, run_id=run_id)
    elif report.decision is JudgeReportDecision.REVISION_REQUIRED:
        if report.revision_request_ref is None:
            raise ContractValidationError("revision_judge_result revision_required requires revision_request_ref")
        request = _read_artifact(
            workspace,
            report.revision_request_ref,
            TaskRevisionRequest,
            "task_revision_request",
        )
        validate_revision_request_for_judge(request, packet, report, run_id=run_id)


def _ensure_expected_artifacts_accepted(
    expected_artifact_refs: list[str],
    execution_report: AgentExecutionReport,
    judge_report: JudgeReport,
    workspace: RunWorkspace,
) -> None:
    for ref in expected_artifact_refs:
        if ref not in execution_report.produced_artifact_refs:
            raise ContractValidationError(f"accepted revised run missing produced artifact ref: {ref}")
        if ref not in judge_report.accepted_artifact_refs:
            raise ContractValidationError(f"accepted revised run missing accepted artifact ref: {ref}")
    _ensure_existing_refs(workspace, expected_artifact_refs, "expected_artifact_refs")


def _flow_status_from_judge_decision(decision: JudgeReportDecision) -> AgenticFlowStatus:
    if decision is JudgeReportDecision.ACCEPTED:
        return AgenticFlowStatus.ACCEPTED
    if decision is JudgeReportDecision.REPAIR:
        return AgenticFlowStatus.REPAIR
    if decision is JudgeReportDecision.REVISION_REQUIRED:
        return AgenticFlowStatus.REVISION_REQUIRED
    return AgenticFlowStatus.REJECTED


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


def _revision_execution_directive_ref(directive: RevisionExecutionDirective) -> str:
    request_id = _request_id_from_revision_ref(directive.task_contract_revision_ref)
    return f"revisions/{request_id}/revision_execution_directive.json"


def _revision_judge_rubric_ref(request_id: str) -> str:
    safe_request_id = _validate_id(request_id, "revision_request_id")
    return f"revisions/{safe_request_id}/projections/judge_rubric.json"


def _revision_judge_packet_ref(request_id: str) -> str:
    safe_request_id = _validate_id(request_id, "revision_request_id")
    return f"revisions/{safe_request_id}/packets/judge_packet.json"


def _revision_judge_report_ref(request_id: str) -> str:
    safe_request_id = _validate_id(request_id, "revision_request_id")
    return f"revisions/{safe_request_id}/reports/judge_report.json"


def _revision_result_ref(request_id: str, result: AgenticFlowResult) -> str:
    safe_request_id = _validate_id(request_id, "revision_request_id")
    result_hash = stable_json_hash(result.to_dict()).split(":", 1)[1]
    return f"revisions/{safe_request_id}/results/result-{result_hash}.json"


def _request_id_from_revision_ref(ref: str) -> str:
    safe_ref = validate_ref(ref, "task_contract_revision_ref")
    parts = safe_ref.split("/")
    if len(parts) >= 3 and parts[-1] == "task_contract_revision.json":
        return _validate_id(parts[-2], "task_contract_revision.request_id")
    raise ContractValidationError("task_contract_revision_ref must end with /task_contract_revision.json")


def _piworker_call_result_ref(call_id: str) -> str:
    safe_call_id = _validate_id(call_id, "piworker_call.call_id")
    return f"attempts/{safe_call_id}/piworker_call_result.json"


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


def _write_or_replay_revision_execution_directive(
    workspace: RunWorkspace,
    directive: RevisionExecutionDirective,
) -> RevisionExecutionDirective:
    directive_ref = _revision_execution_directive_ref(directive)
    directive.validate()
    try:
        existing_payload = workspace.read_json(directive_ref)
    except FileNotFoundError:
        workspace.write_json(directive_ref, directive.to_dict())
        return directive
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"revision_execution_directive is unreadable: {directive_ref}") from exc

    existing_directive = RevisionExecutionDirective.from_dict(existing_payload)
    if existing_directive.directive_hash != directive.directive_hash:
        raise ContractValidationError("revision_execution_directive replay conflict for deterministic directive_id")
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


def _ensure_existing_refs(workspace: RunWorkspace, refs: list[str], field_name: str) -> None:
    for ref in refs:
        safe_ref = workspace.ensure_read_ref(ref)
        path = workspace.resolve_ref(safe_ref)
        if not path.exists() or not path.is_file():
            raise ContractValidationError(f"{field_name} does not exist: {safe_ref}")


def _execution_status_from_call_result(status: Any) -> AgentExecutionStatus:
    from .piworker_call import PiWorkerCallResultStatus

    call_status = require_enum(status, PiWorkerCallResultStatus, "piworker_call_result.status")
    if call_status is PiWorkerCallResultStatus.COMPLETED:
        return AgentExecutionStatus.COMPLETED
    if call_status is PiWorkerCallResultStatus.BLOCKED:
        return AgentExecutionStatus.BLOCKED
    return AgentExecutionStatus.FAILED


def _append_revision_applied_ledger_entry_once(
    *,
    workspace: RunWorkspace,
    decision_ledger_ref: str,
    applied: RevisionAppliedRecord,
) -> None:
    _append_ledger_entry_once(
        workspace=workspace,
        decision_ledger_ref=decision_ledger_ref,
        event_kind=DecisionLedgerEventKind.REVISION_APPLIED,
        run_id=applied.run_id,
        contract_id=applied.contract_id,
        contract_hash=applied.revised_contract_hash,
        status=applied.status.value,
        refs={
            "revision_applied_ref": _applied_ref(applied),
            "pending_ref": applied.pending_ref,
            "task_revision_decision_ref": applied.task_revision_decision_ref,
            "task_contract_revision_ref": applied.task_contract_revision_ref,
            "previous_contract_ref": applied.previous_contract_ref,
            "revised_contract_ref": applied.revised_contract_ref,
        },
        content_hashes={_applied_ref(applied): applied.applied_hash},
    )


def _append_ledger_entry_once(
    *,
    workspace: RunWorkspace,
    decision_ledger_ref: str,
    event_kind: DecisionLedgerEventKind,
    run_id: str,
    contract_id: str,
    contract_hash: str,
    status: str,
    refs: dict[str, str],
    content_hashes: dict[str, str],
) -> None:
    ledger_root = workspace.workspace_root_path
    entries = read_decision_ledger(ledger_root, decision_ledger_ref=decision_ledger_ref)
    ref_map = {key: validate_ref(value, f"ledger_ref.{key}") for key, value in refs.items()}
    hash_map = {key: _validate_hash(value, f"ledger_hash.{key}") for key, value in content_hashes.items()}
    for entry in entries:
        if (
            entry.event_kind is event_kind
            and entry.contract_hash == contract_hash
            and entry.status == status
            and dict(entry.ref_map) == ref_map
            and dict(entry.content_hashes) == hash_map
        ):
            return
    entry = TaskContractDecisionLedgerEntry(
        entry_id=next_ledger_entry_id(entries),
        run_id=run_id,
        event_kind=event_kind,
        contract_id=contract_id,
        contract_hash=contract_hash,
        status=status,
        ref_map=ref_map,
        content_hashes=hash_map,
    )
    append_decision_ledger_entry(ledger_root, decision_ledger_ref, entry)


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


def _revision_execution_directive_id(
    *,
    revision_applied_ref: str,
    revision_applied_hash: str,
    revised_contract_hash: str,
) -> str:
    seed = {
        "schema_version": REVISION_EXECUTION_DIRECTIVE_SCHEMA_VERSION,
        "revision_applied_ref": validate_ref(revision_applied_ref, "revision_execution_directive_id.applied_ref"),
        "revision_applied_hash": _validate_hash(
            revision_applied_hash,
            "revision_execution_directive_id.applied_hash",
        ),
        "revised_contract_hash": _validate_hash(
            revised_contract_hash,
            "revision_execution_directive_id.revised_contract_hash",
        ),
    }
    return "revision-execution-" + stable_json_hash(seed).split(":", 1)[1]


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


def _expected_artifact_refs(contract: TaskContract) -> list[str]:
    return _unique_refs([ref for output in contract.required_outputs for ref in output.refs])


def _ensure_refs_under_artifact_roots(refs: list[str], artifact_root_refs: list[str]) -> None:
    roots = _unique_refs(artifact_root_refs)
    for ref in refs:
        if not any(ref_is_under(ref, root) for root in roots):
            raise ContractValidationError(f"artifact ref is outside artifact roots: {ref}")


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
    "REVISION_EXECUTION_DIRECTIVE_SCHEMA_VERSION",
    "REVISION_PENDING_RECORD_SCHEMA_VERSION",
    "RevisionAppliedRecord",
    "RevisionAppliedStatus",
    "RevisionExecutionDirective",
    "RevisionExecutionDirectiveStatus",
    "RevisionPendingRecord",
    "RevisionPendingStatus",
    "apply_task_contract_revision",
    "build_revision_execution_directive",
    "build_revision_judge_result",
    "build_revision_pending_record",
    "build_revision_rejudge_packet",
    "load_revision_draft_contract",
]
