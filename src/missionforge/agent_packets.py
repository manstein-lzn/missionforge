"""Role-separated agent packets for the simplified PiWorker path."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


EXECUTION_PACKET_SCHEMA_VERSION = "agent_execution_packet.v1"
AGENT_EXECUTION_REPORT_SCHEMA_VERSION = "agent_execution_report.v1"
JUDGE_PACKET_SCHEMA_VERSION = "judge_packet.v1"
JUDGE_REPORT_SCHEMA_VERSION = "judge_report.v1"


class AgentRole(StrEnum):
    """Role authority for a PiWorker packet or report."""

    EXECUTOR = "executor_piworker"
    JUDGE = "judge_piworker"


class AgentExecutionStatus(StrEnum):
    """Executor report status without final acceptance authority."""

    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    REPAIR_REQUESTED = "repair_requested"
    REVISION_REQUESTED = "revision_requested"


class JudgeReportDecision(StrEnum):
    """Independent judge decision vocabulary."""

    ACCEPTED = "accepted"
    REPAIR = "repair"
    REVISION_REQUIRED = "revision_required"
    REJECTED = "rejected"


class HardCheckStatus(StrEnum):
    """Product-neutral hard-check gate status visible to the judge."""

    PASSED = "passed"
    FAILED = "failed"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class AgentExecutionPacket:
    """Executor-facing packet derived from a WorkerBrief and permissions."""

    packet_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    worker_brief_ref: str
    workspace_policy_ref: str
    permission_manifest_ref: str
    report_ref: str
    expected_artifact_refs: list[str] = field(default_factory=list)
    allowed_input_refs: list[str] = field(default_factory=list)
    writable_refs: list[str] = field(default_factory=list)
    role: AgentRole = AgentRole.EXECUTOR
    schema_version: str = EXECUTION_PACKET_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgentExecutionPacket":
        data = _refs_only_mapping(payload, "agent_execution_packet")
        _reject_unknown_fields(data, _EXECUTION_PACKET_FIELDS, "agent_execution_packet")
        packet = cls(
            packet_id=require_non_empty_str(data.get("packet_id"), "agent_execution_packet.packet_id"),
            schema_version=require_non_empty_str(
                data.get("schema_version", EXECUTION_PACKET_SCHEMA_VERSION),
                "agent_execution_packet.schema_version",
            ),
            role=require_enum(data.get("role", AgentRole.EXECUTOR.value), AgentRole, "agent_execution_packet.role"),
            contract_id=require_non_empty_str(data.get("contract_id"), "agent_execution_packet.contract_id"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "agent_execution_packet.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "agent_execution_packet.contract_ref"),
            worker_brief_ref=validate_ref(data.get("worker_brief_ref"), "agent_execution_packet.worker_brief_ref"),
            workspace_policy_ref=validate_ref(
                data.get("workspace_policy_ref"),
                "agent_execution_packet.workspace_policy_ref",
            ),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "agent_execution_packet.permission_manifest_ref",
            ),
            report_ref=validate_ref(data.get("report_ref"), "agent_execution_packet.report_ref"),
            expected_artifact_refs=_ref_list(
                data.get("expected_artifact_refs", []),
                "agent_execution_packet.expected_artifact_refs",
            ),
            allowed_input_refs=_ref_list(
                data.get("allowed_input_refs", []),
                "agent_execution_packet.allowed_input_refs",
            ),
            writable_refs=_ref_list(data.get("writable_refs", []), "agent_execution_packet.writable_refs"),
        )
        packet.validate()
        return packet

    def validate(self) -> None:
        _require_schema(self.schema_version, EXECUTION_PACKET_SCHEMA_VERSION, "agent_execution_packet.schema_version")
        _require_role(self.role, AgentRole.EXECUTOR, "agent_execution_packet.role")
        require_non_empty_str(self.packet_id, "agent_execution_packet.packet_id")
        require_non_empty_str(self.contract_id, "agent_execution_packet.contract_id")
        _validate_hash(self.contract_hash, "agent_execution_packet.contract_hash")
        validate_ref(self.contract_ref, "agent_execution_packet.contract_ref")
        validate_ref(self.worker_brief_ref, "agent_execution_packet.worker_brief_ref")
        validate_ref(self.workspace_policy_ref, "agent_execution_packet.workspace_policy_ref")
        validate_ref(self.permission_manifest_ref, "agent_execution_packet.permission_manifest_ref")
        validate_ref(self.report_ref, "agent_execution_packet.report_ref")
        _validate_unique_refs(self.expected_artifact_refs, "agent_execution_packet.expected_artifact_refs")
        _validate_unique_refs(self.allowed_input_refs, "agent_execution_packet.allowed_input_refs")
        _validate_unique_refs(self.writable_refs, "agent_execution_packet.writable_refs")
        _validate_refs_under_roots(
            self.expected_artifact_refs,
            self.writable_refs,
            "agent_execution_packet.expected_artifact_refs",
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "packet_id": self.packet_id,
            "schema_version": self.schema_version,
            "role": self.role.value,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "worker_brief_ref": self.worker_brief_ref,
            "workspace_policy_ref": self.workspace_policy_ref,
            "permission_manifest_ref": self.permission_manifest_ref,
            "report_ref": self.report_ref,
            "expected_artifact_refs": list(self.expected_artifact_refs),
            "allowed_input_refs": list(self.allowed_input_refs),
            "writable_refs": list(self.writable_refs),
        }


@dataclass(frozen=True)
class AgentExecutionReport:
    """Executor report that cannot grant final acceptance."""

    report_id: str
    packet_id: str
    packet_ref: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    status: AgentExecutionStatus
    produced_artifact_refs: list[str] = field(default_factory=list)
    changed_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    repair_request_ref: str | None = None
    revision_request_ref: str | None = None
    role: AgentRole = AgentRole.EXECUTOR
    schema_version: str = AGENT_EXECUTION_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgentExecutionReport":
        data = _refs_only_mapping(payload, "agent_execution_report")
        _reject_unknown_fields(data, _AGENT_EXECUTION_REPORT_FIELDS, "agent_execution_report")
        _reject_executor_acceptance_fields(data)
        report = cls(
            report_id=require_non_empty_str(data.get("report_id"), "agent_execution_report.report_id"),
            schema_version=require_non_empty_str(
                data.get("schema_version", AGENT_EXECUTION_REPORT_SCHEMA_VERSION),
                "agent_execution_report.schema_version",
            ),
            role=require_enum(data.get("role", AgentRole.EXECUTOR.value), AgentRole, "agent_execution_report.role"),
            packet_id=require_non_empty_str(data.get("packet_id"), "agent_execution_report.packet_id"),
            packet_ref=validate_ref(data.get("packet_ref"), "agent_execution_report.packet_ref"),
            contract_id=require_non_empty_str(data.get("contract_id"), "agent_execution_report.contract_id"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "agent_execution_report.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "agent_execution_report.contract_ref"),
            status=require_enum(data.get("status"), AgentExecutionStatus, "agent_execution_report.status"),
            produced_artifact_refs=_ref_list(
                data.get("produced_artifact_refs", []),
                "agent_execution_report.produced_artifact_refs",
            ),
            changed_refs=_ref_list(data.get("changed_refs", []), "agent_execution_report.changed_refs"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "agent_execution_report.evidence_refs"),
            metric_refs=_ref_list(data.get("metric_refs", []), "agent_execution_report.metric_refs"),
            repair_request_ref=_optional_ref(
                data.get("repair_request_ref"),
                "agent_execution_report.repair_request_ref",
            ),
            revision_request_ref=_optional_ref(
                data.get("revision_request_ref"),
                "agent_execution_report.revision_request_ref",
            ),
        )
        report.validate()
        return report

    def validate(self) -> None:
        _require_schema(self.schema_version, AGENT_EXECUTION_REPORT_SCHEMA_VERSION, "agent_execution_report.schema_version")
        _require_role(self.role, AgentRole.EXECUTOR, "agent_execution_report.role")
        require_non_empty_str(self.report_id, "agent_execution_report.report_id")
        require_non_empty_str(self.packet_id, "agent_execution_report.packet_id")
        validate_ref(self.packet_ref, "agent_execution_report.packet_ref")
        require_non_empty_str(self.contract_id, "agent_execution_report.contract_id")
        _validate_hash(self.contract_hash, "agent_execution_report.contract_hash")
        validate_ref(self.contract_ref, "agent_execution_report.contract_ref")
        require_enum(self.status, AgentExecutionStatus, "agent_execution_report.status")
        _validate_unique_refs(self.produced_artifact_refs, "agent_execution_report.produced_artifact_refs")
        _validate_unique_refs(self.changed_refs, "agent_execution_report.changed_refs")
        _validate_unique_refs(self.evidence_refs, "agent_execution_report.evidence_refs")
        _validate_unique_refs(self.metric_refs, "agent_execution_report.metric_refs")
        _optional_ref(self.repair_request_ref, "agent_execution_report.repair_request_ref")
        _optional_ref(self.revision_request_ref, "agent_execution_report.revision_request_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "report_id": self.report_id,
            "schema_version": self.schema_version,
            "role": self.role.value,
            "packet_id": self.packet_id,
            "packet_ref": self.packet_ref,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "status": self.status.value,
            "produced_artifact_refs": list(self.produced_artifact_refs),
            "changed_refs": list(self.changed_refs),
            "evidence_refs": list(self.evidence_refs),
            "metric_refs": list(self.metric_refs),
            "repair_request_ref": self.repair_request_ref,
            "revision_request_ref": self.revision_request_ref,
        }


@dataclass(frozen=True)
class JudgePacket:
    """Judge-facing packet derived from JudgeRubric and execution evidence."""

    packet_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    judge_rubric_ref: str
    execution_packet_ref: str
    execution_report_ref: str
    report_ref: str
    hard_check_status: HardCheckStatus = HardCheckStatus.MISSING
    artifact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    hard_check_refs: list[str] = field(default_factory=list)
    role: AgentRole = AgentRole.JUDGE
    schema_version: str = JUDGE_PACKET_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JudgePacket":
        data = _refs_only_mapping(payload, "judge_packet")
        _reject_unknown_fields(data, _JUDGE_PACKET_FIELDS, "judge_packet")
        packet = cls(
            packet_id=require_non_empty_str(data.get("packet_id"), "judge_packet.packet_id"),
            schema_version=require_non_empty_str(
                data.get("schema_version", JUDGE_PACKET_SCHEMA_VERSION),
                "judge_packet.schema_version",
            ),
            role=require_enum(data.get("role", AgentRole.JUDGE.value), AgentRole, "judge_packet.role"),
            contract_id=require_non_empty_str(data.get("contract_id"), "judge_packet.contract_id"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "judge_packet.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "judge_packet.contract_ref"),
            judge_rubric_ref=validate_ref(data.get("judge_rubric_ref"), "judge_packet.judge_rubric_ref"),
            execution_packet_ref=validate_ref(data.get("execution_packet_ref"), "judge_packet.execution_packet_ref"),
            execution_report_ref=validate_ref(data.get("execution_report_ref"), "judge_packet.execution_report_ref"),
            report_ref=validate_ref(data.get("report_ref"), "judge_packet.report_ref"),
            hard_check_status=require_enum(
                data.get("hard_check_status", HardCheckStatus.MISSING.value),
                HardCheckStatus,
                "judge_packet.hard_check_status",
            ),
            artifact_refs=_ref_list(data.get("artifact_refs", []), "judge_packet.artifact_refs"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "judge_packet.evidence_refs"),
            hard_check_refs=_ref_list(data.get("hard_check_refs", []), "judge_packet.hard_check_refs"),
        )
        packet.validate()
        return packet

    def validate(self) -> None:
        _require_schema(self.schema_version, JUDGE_PACKET_SCHEMA_VERSION, "judge_packet.schema_version")
        _require_role(self.role, AgentRole.JUDGE, "judge_packet.role")
        require_non_empty_str(self.packet_id, "judge_packet.packet_id")
        require_non_empty_str(self.contract_id, "judge_packet.contract_id")
        _validate_hash(self.contract_hash, "judge_packet.contract_hash")
        validate_ref(self.contract_ref, "judge_packet.contract_ref")
        validate_ref(self.judge_rubric_ref, "judge_packet.judge_rubric_ref")
        validate_ref(self.execution_packet_ref, "judge_packet.execution_packet_ref")
        validate_ref(self.execution_report_ref, "judge_packet.execution_report_ref")
        validate_ref(self.report_ref, "judge_packet.report_ref")
        require_enum(self.hard_check_status, HardCheckStatus, "judge_packet.hard_check_status")
        _validate_unique_refs(self.artifact_refs, "judge_packet.artifact_refs")
        _validate_unique_refs(self.evidence_refs, "judge_packet.evidence_refs")
        _validate_unique_refs(self.hard_check_refs, "judge_packet.hard_check_refs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "packet_id": self.packet_id,
            "schema_version": self.schema_version,
            "role": self.role.value,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "judge_rubric_ref": self.judge_rubric_ref,
            "execution_packet_ref": self.execution_packet_ref,
            "execution_report_ref": self.execution_report_ref,
            "report_ref": self.report_ref,
            "hard_check_status": self.hard_check_status.value,
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "hard_check_refs": list(self.hard_check_refs),
        }


@dataclass(frozen=True)
class JudgeReport:
    """Independent judge decision over contract, rubric, artifacts, and evidence."""

    report_id: str
    packet_id: str
    packet_ref: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    decision: JudgeReportDecision
    hard_check_status: HardCheckStatus
    rationale_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    accepted_artifact_refs: list[str] = field(default_factory=list)
    repair_brief_ref: str | None = None
    revision_request_ref: str | None = None
    role: AgentRole = AgentRole.JUDGE
    schema_version: str = JUDGE_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JudgeReport":
        data = _refs_only_mapping(payload, "judge_report")
        _reject_unknown_fields(data, _JUDGE_REPORT_FIELDS, "judge_report")
        report = cls(
            report_id=require_non_empty_str(data.get("report_id"), "judge_report.report_id"),
            schema_version=require_non_empty_str(
                data.get("schema_version", JUDGE_REPORT_SCHEMA_VERSION),
                "judge_report.schema_version",
            ),
            role=require_enum(data.get("role", AgentRole.JUDGE.value), AgentRole, "judge_report.role"),
            packet_id=require_non_empty_str(data.get("packet_id"), "judge_report.packet_id"),
            packet_ref=validate_ref(data.get("packet_ref"), "judge_report.packet_ref"),
            contract_id=require_non_empty_str(data.get("contract_id"), "judge_report.contract_id"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "judge_report.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "judge_report.contract_ref"),
            decision=require_enum(data.get("decision"), JudgeReportDecision, "judge_report.decision"),
            hard_check_status=require_enum(
                data.get("hard_check_status", HardCheckStatus.MISSING.value),
                HardCheckStatus,
                "judge_report.hard_check_status",
            ),
            rationale_refs=_ref_list(data.get("rationale_refs", []), "judge_report.rationale_refs"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "judge_report.evidence_refs"),
            accepted_artifact_refs=_ref_list(
                data.get("accepted_artifact_refs", []),
                "judge_report.accepted_artifact_refs",
            ),
            repair_brief_ref=_optional_ref(data.get("repair_brief_ref"), "judge_report.repair_brief_ref"),
            revision_request_ref=_optional_ref(
                data.get("revision_request_ref"),
                "judge_report.revision_request_ref",
            ),
        )
        report.validate()
        return report

    def validate(self) -> None:
        _require_schema(self.schema_version, JUDGE_REPORT_SCHEMA_VERSION, "judge_report.schema_version")
        _require_role(self.role, AgentRole.JUDGE, "judge_report.role")
        require_non_empty_str(self.report_id, "judge_report.report_id")
        require_non_empty_str(self.packet_id, "judge_report.packet_id")
        validate_ref(self.packet_ref, "judge_report.packet_ref")
        require_non_empty_str(self.contract_id, "judge_report.contract_id")
        _validate_hash(self.contract_hash, "judge_report.contract_hash")
        validate_ref(self.contract_ref, "judge_report.contract_ref")
        require_enum(self.decision, JudgeReportDecision, "judge_report.decision")
        require_enum(self.hard_check_status, HardCheckStatus, "judge_report.hard_check_status")
        _validate_unique_refs(self.rationale_refs, "judge_report.rationale_refs")
        _validate_unique_refs(self.evidence_refs, "judge_report.evidence_refs")
        _validate_unique_refs(self.accepted_artifact_refs, "judge_report.accepted_artifact_refs")
        _optional_ref(self.repair_brief_ref, "judge_report.repair_brief_ref")
        _optional_ref(self.revision_request_ref, "judge_report.revision_request_ref")
        if self.decision is JudgeReportDecision.REPAIR and self.repair_brief_ref is None:
            raise ContractValidationError("judge_report.repair requires repair_brief_ref")
        if self.decision is JudgeReportDecision.REVISION_REQUIRED and self.revision_request_ref is None:
            raise ContractValidationError("judge_report.revision_required requires revision_request_ref")
        if self.decision is JudgeReportDecision.ACCEPTED and (self.repair_brief_ref or self.revision_request_ref):
            raise ContractValidationError("judge_report.accepted cannot include repair or revision refs")
        if self.decision is JudgeReportDecision.ACCEPTED and self.hard_check_status is not HardCheckStatus.PASSED:
            raise ContractValidationError("judge_report.accepted requires passed hard checks")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "report_id": self.report_id,
            "schema_version": self.schema_version,
            "role": self.role.value,
            "packet_id": self.packet_id,
            "packet_ref": self.packet_ref,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "decision": self.decision.value,
            "hard_check_status": self.hard_check_status.value,
            "rationale_refs": list(self.rationale_refs),
            "evidence_refs": list(self.evidence_refs),
            "accepted_artifact_refs": list(self.accepted_artifact_refs),
            "repair_brief_ref": self.repair_brief_ref,
            "revision_request_ref": self.revision_request_ref,
        }


def validate_execution_report_for_packet(
    report: AgentExecutionReport,
    packet: AgentExecutionPacket,
    *,
    packet_ref: str,
) -> None:
    """Validate that an executor report belongs to its execution packet."""

    report.validate()
    packet.validate()
    expected_packet_ref = validate_ref(packet_ref, "packet_ref")
    if report.packet_id != packet.packet_id:
        raise ContractValidationError("agent_execution_report packet_id does not match packet")
    if report.packet_ref != expected_packet_ref:
        raise ContractValidationError("agent_execution_report packet_ref does not match packet ref")
    _require_same_contract(report, packet, "agent_execution_report")


def validate_judge_report_for_packet(
    report: JudgeReport,
    packet: JudgePacket,
    *,
    packet_ref: str,
) -> None:
    """Validate that a judge report belongs to its judge packet."""

    report.validate()
    packet.validate()
    expected_packet_ref = validate_ref(packet_ref, "packet_ref")
    if report.packet_id != packet.packet_id:
        raise ContractValidationError("judge_report packet_id does not match packet")
    if report.packet_ref != expected_packet_ref:
        raise ContractValidationError("judge_report packet_ref does not match packet ref")
    _require_same_contract(report, packet, "judge_report")
    if report.hard_check_status is not packet.hard_check_status:
        raise ContractValidationError("judge_report hard_check_status does not match packet")
    if report.decision is JudgeReportDecision.ACCEPTED and packet.hard_check_status is not HardCheckStatus.PASSED:
        raise ContractValidationError("judge_report accepted requires packet hard checks to pass")
    for ref in report.accepted_artifact_refs:
        if ref not in packet.artifact_refs:
            raise ContractValidationError("judge_report accepted artifact was not in judge packet artifacts")


def validate_judge_packet_for_execution(
    judge_packet: JudgePacket,
    execution_packet: AgentExecutionPacket,
    execution_report: AgentExecutionReport,
    *,
    execution_packet_ref: str,
    execution_report_ref: str,
) -> None:
    """Validate that a judge packet is bound to executor artifacts and reports."""

    judge_packet.validate()
    validate_execution_report_for_packet(
        execution_report,
        execution_packet,
        packet_ref=execution_packet_ref,
    )
    expected_report_ref = validate_ref(execution_report_ref, "execution_report_ref")
    if judge_packet.execution_packet_ref != validate_ref(execution_packet_ref, "execution_packet_ref"):
        raise ContractValidationError("judge_packet execution_packet_ref does not match execution packet ref")
    if judge_packet.execution_report_ref != expected_report_ref:
        raise ContractValidationError("judge_packet execution_report_ref does not match execution report ref")
    _require_same_contract(judge_packet, execution_packet, "judge_packet")
    _require_same_contract(judge_packet, execution_report, "judge_packet")
    for ref in judge_packet.artifact_refs:
        if ref not in execution_report.produced_artifact_refs:
            raise ContractValidationError("judge_packet artifact was not produced by execution report")


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(payload, field_name), field_name))


_EXECUTION_PACKET_FIELDS = {
    "packet_id",
    "schema_version",
    "role",
    "contract_id",
    "contract_hash",
    "contract_ref",
    "worker_brief_ref",
    "workspace_policy_ref",
    "permission_manifest_ref",
    "report_ref",
    "expected_artifact_refs",
    "allowed_input_refs",
    "writable_refs",
}

_AGENT_EXECUTION_REPORT_FIELDS = {
    "report_id",
    "schema_version",
    "role",
    "packet_id",
    "packet_ref",
    "contract_id",
    "contract_hash",
    "contract_ref",
    "status",
    "produced_artifact_refs",
    "changed_refs",
    "evidence_refs",
    "metric_refs",
    "repair_request_ref",
    "revision_request_ref",
}

_JUDGE_PACKET_FIELDS = {
    "packet_id",
    "schema_version",
    "role",
    "contract_id",
    "contract_hash",
    "contract_ref",
    "judge_rubric_ref",
    "execution_packet_ref",
    "execution_report_ref",
    "report_ref",
    "hard_check_status",
    "artifact_refs",
    "evidence_refs",
    "hard_check_refs",
}

_JUDGE_REPORT_FIELDS = {
    "report_id",
    "schema_version",
    "role",
    "packet_id",
    "packet_ref",
    "contract_id",
    "contract_hash",
    "contract_ref",
    "decision",
    "hard_check_status",
    "rationale_refs",
    "evidence_refs",
    "accepted_artifact_refs",
    "repair_brief_ref",
    "revision_request_ref",
}


def _reject_unknown_fields(data: Mapping[str, Any], allowed_fields: set[str], field_name: str) -> None:
    unknown = sorted(set(data) - allowed_fields)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unknown fields: {unknown}")


def _reject_executor_acceptance_fields(data: Mapping[str, Any]) -> None:
    forbidden = {"accepted", "acceptance", "decision", "judge_decision", "final_decision"}
    present = sorted(key for key in data if key in forbidden)
    if present:
        raise ContractValidationError(f"executor report cannot contain acceptance fields: {present}")
    status = data.get("status")
    if status == JudgeReportDecision.ACCEPTED.value:
        raise ContractValidationError("executor report status cannot be accepted")


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")


def _validate_refs_under_roots(refs: list[str], root_refs: list[str], field_name: str) -> None:
    for ref in refs:
        if not any(_ref_is_under(ref, root_ref) for root_ref in root_refs):
            raise ContractValidationError(f"{field_name} contains ref outside writable roots: {ref}")


def _ref_is_under(ref: str, root_ref: str) -> bool:
    safe_ref = validate_ref(ref, "ref")
    safe_root = validate_ref(root_ref, "root_ref")
    return safe_ref == safe_root or safe_ref.startswith(f"{safe_root}/")


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return validate_ref(value, field_name)


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"unsupported {field_name}: {actual}")


def _require_role(actual: AgentRole, expected: AgentRole, field_name: str) -> None:
    role = require_enum(actual, AgentRole, field_name)
    if role is not expected:
        raise ContractValidationError(f"{field_name} must be {expected.value}")


def _validate_hash(value: Any, field_name: str) -> str:
    hash_value = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not hash_value.startswith(prefix):
        raise ContractValidationError(f"{field_name} must start with {prefix!r}")
    digest = hash_value[len(prefix):]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ContractValidationError(f"{field_name} must be a sha256 hex digest")
    return hash_value


def _require_same_contract(left: Any, right: Any, field_name: str) -> None:
    if left.contract_id != right.contract_id:
        raise ContractValidationError(f"{field_name} contract_id does not match packet")
    if left.contract_hash != right.contract_hash:
        raise ContractValidationError(f"{field_name} contract_hash does not match packet")
    if left.contract_ref != right.contract_ref:
        raise ContractValidationError(f"{field_name} contract_ref does not match packet")
