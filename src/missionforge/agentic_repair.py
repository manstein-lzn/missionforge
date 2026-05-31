"""TaskContract-native repair and revision artifacts for agentic flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .agent_packets import JudgePacket, JudgeReport
from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


REPAIR_BRIEF_SCHEMA_VERSION = "repair_brief.v1"
TASK_REVISION_REQUEST_SCHEMA_VERSION = "task_revision_request.v1"
TASK_REVISION_DECISION_SCHEMA_VERSION = "task_revision_decision.v1"


class TaskRevisionAuthority(StrEnum):
    """Authority that must review a requested contract revision."""

    PRODUCT_INTEGRATION = "product_integration"
    OPERATOR = "operator"
    HUMAN = "human"


class TaskRevisionDecisionStatus(StrEnum):
    """Decision over a TaskContract revision request."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REDESIGN = "needs_redesign"


@dataclass(frozen=True)
class RepairBrief:
    """Judge-authored repair instructions that preserve the frozen contract."""

    brief_id: str
    run_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    judge_packet_ref: str
    judge_report_ref: str
    execution_report_ref: str
    reason: str
    repair_steps: list[str]
    target_artifact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    schema_version: str = REPAIR_BRIEF_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairBrief":
        data = _strict_mapping(
            payload,
            "repair_brief",
            {
                "schema_version",
                "brief_id",
                "run_id",
                "contract_id",
                "contract_hash",
                "contract_ref",
                "judge_packet_ref",
                "judge_report_ref",
                "execution_report_ref",
                "reason",
                "repair_steps",
                "target_artifact_refs",
                "evidence_refs",
            },
        )
        brief = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", REPAIR_BRIEF_SCHEMA_VERSION),
                "repair_brief.schema_version",
            ),
            brief_id=require_non_empty_str(data.get("brief_id"), "repair_brief.brief_id"),
            run_id=require_non_empty_str(data.get("run_id"), "repair_brief.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "repair_brief.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "repair_brief.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "repair_brief.contract_ref"),
            judge_packet_ref=validate_ref(data.get("judge_packet_ref"), "repair_brief.judge_packet_ref"),
            judge_report_ref=validate_ref(data.get("judge_report_ref"), "repair_brief.judge_report_ref"),
            execution_report_ref=validate_ref(
                data.get("execution_report_ref"),
                "repair_brief.execution_report_ref",
            ),
            reason=require_non_empty_str(data.get("reason"), "repair_brief.reason"),
            repair_steps=require_str_list(data.get("repair_steps"), "repair_brief.repair_steps"),
            target_artifact_refs=_ref_list(data.get("target_artifact_refs", []), "repair_brief.target_artifact_refs"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "repair_brief.evidence_refs"),
        )
        brief.validate()
        return brief

    def validate(self) -> None:
        _require_schema(self.schema_version, REPAIR_BRIEF_SCHEMA_VERSION, "repair_brief.schema_version")
        require_non_empty_str(self.brief_id, "repair_brief.brief_id")
        require_non_empty_str(self.run_id, "repair_brief.run_id")
        require_non_empty_str(self.contract_id, "repair_brief.contract_id")
        _validate_hash(self.contract_hash, "repair_brief.contract_hash")
        validate_ref(self.contract_ref, "repair_brief.contract_ref")
        validate_ref(self.judge_packet_ref, "repair_brief.judge_packet_ref")
        validate_ref(self.judge_report_ref, "repair_brief.judge_report_ref")
        validate_ref(self.execution_report_ref, "repair_brief.execution_report_ref")
        require_non_empty_str(self.reason, "repair_brief.reason")
        if not require_str_list(self.repair_steps, "repair_brief.repair_steps"):
            raise ContractValidationError("repair_brief.repair_steps must not be empty")
        _validate_unique_refs(self.target_artifact_refs, "repair_brief.target_artifact_refs")
        _validate_unique_refs(self.evidence_refs, "repair_brief.evidence_refs")
        if self.execution_report_ref not in self.evidence_refs:
            raise ContractValidationError("repair_brief.evidence_refs must cite execution_report_ref")
        assert_refs_only_payload(self.to_dict_without_validation(), "repair_brief")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "brief_id": self.brief_id,
            "run_id": self.run_id,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "judge_packet_ref": self.judge_packet_ref,
            "judge_report_ref": self.judge_report_ref,
            "execution_report_ref": self.execution_report_ref,
            "reason": self.reason,
            "repair_steps": list(self.repair_steps),
            "target_artifact_refs": list(self.target_artifact_refs),
            "evidence_refs": list(self.evidence_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class TaskRevisionRequest:
    """Judge-authored request to revise the frozen TaskContract."""

    request_id: str
    run_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    judge_packet_ref: str
    judge_report_ref: str
    execution_report_ref: str
    reason: str
    proposed_contract_changes: list[str]
    authority_required: TaskRevisionAuthority = TaskRevisionAuthority.PRODUCT_INTEGRATION
    evidence_refs: list[str] = field(default_factory=list)
    schema_version: str = TASK_REVISION_REQUEST_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskRevisionRequest":
        data = _strict_mapping(
            payload,
            "task_revision_request",
            {
                "schema_version",
                "request_id",
                "run_id",
                "contract_id",
                "contract_hash",
                "contract_ref",
                "judge_packet_ref",
                "judge_report_ref",
                "execution_report_ref",
                "reason",
                "proposed_contract_changes",
                "authority_required",
                "evidence_refs",
            },
        )
        request = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", TASK_REVISION_REQUEST_SCHEMA_VERSION),
                "task_revision_request.schema_version",
            ),
            request_id=require_non_empty_str(data.get("request_id"), "task_revision_request.request_id"),
            run_id=require_non_empty_str(data.get("run_id"), "task_revision_request.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "task_revision_request.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "task_revision_request.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "task_revision_request.contract_ref"),
            judge_packet_ref=validate_ref(
                data.get("judge_packet_ref"),
                "task_revision_request.judge_packet_ref",
            ),
            judge_report_ref=validate_ref(
                data.get("judge_report_ref"),
                "task_revision_request.judge_report_ref",
            ),
            execution_report_ref=validate_ref(
                data.get("execution_report_ref"),
                "task_revision_request.execution_report_ref",
            ),
            reason=require_non_empty_str(data.get("reason"), "task_revision_request.reason"),
            proposed_contract_changes=require_str_list(
                data.get("proposed_contract_changes"),
                "task_revision_request.proposed_contract_changes",
            ),
            authority_required=require_enum(
                data.get("authority_required", TaskRevisionAuthority.PRODUCT_INTEGRATION.value),
                TaskRevisionAuthority,
                "task_revision_request.authority_required",
            ),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "task_revision_request.evidence_refs"),
        )
        request.validate()
        return request

    def validate(self) -> None:
        _require_schema(self.schema_version, TASK_REVISION_REQUEST_SCHEMA_VERSION, "task_revision_request.schema_version")
        require_non_empty_str(self.request_id, "task_revision_request.request_id")
        require_non_empty_str(self.run_id, "task_revision_request.run_id")
        require_non_empty_str(self.contract_id, "task_revision_request.contract_id")
        _validate_hash(self.contract_hash, "task_revision_request.contract_hash")
        validate_ref(self.contract_ref, "task_revision_request.contract_ref")
        validate_ref(self.judge_packet_ref, "task_revision_request.judge_packet_ref")
        validate_ref(self.judge_report_ref, "task_revision_request.judge_report_ref")
        validate_ref(self.execution_report_ref, "task_revision_request.execution_report_ref")
        require_non_empty_str(self.reason, "task_revision_request.reason")
        if not require_str_list(self.proposed_contract_changes, "task_revision_request.proposed_contract_changes"):
            raise ContractValidationError("task_revision_request.proposed_contract_changes must not be empty")
        require_enum(self.authority_required, TaskRevisionAuthority, "task_revision_request.authority_required")
        _validate_unique_refs(self.evidence_refs, "task_revision_request.evidence_refs")
        if self.execution_report_ref not in self.evidence_refs:
            raise ContractValidationError("task_revision_request.evidence_refs must cite execution_report_ref")
        assert_refs_only_payload(self.to_dict_without_validation(), "task_revision_request")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "judge_packet_ref": self.judge_packet_ref,
            "judge_report_ref": self.judge_report_ref,
            "execution_report_ref": self.execution_report_ref,
            "reason": self.reason,
            "proposed_contract_changes": list(self.proposed_contract_changes),
            "authority_required": self.authority_required.value,
            "evidence_refs": list(self.evidence_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class TaskRevisionDecision:
    """Authority decision over a TaskContract revision request."""

    decision_id: str
    request_ref: str
    request_id: str
    current_contract_ref: str
    current_contract_hash: str
    decision: TaskRevisionDecisionStatus
    decided_by: str
    authority: TaskRevisionAuthority = TaskRevisionAuthority.PRODUCT_INTEGRATION
    rationale_refs: list[str] = field(default_factory=list)
    revised_contract_ref: str = ""
    revised_contract_hash: str = ""
    schema_version: str = TASK_REVISION_DECISION_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskRevisionDecision":
        data = _strict_mapping(
            payload,
            "task_revision_decision",
            {
                "schema_version",
                "decision_id",
                "request_ref",
                "request_id",
                "current_contract_ref",
                "current_contract_hash",
                "decision",
                "decided_by",
                "authority",
                "rationale_refs",
                "revised_contract_ref",
                "revised_contract_hash",
            },
        )
        decision = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", TASK_REVISION_DECISION_SCHEMA_VERSION),
                "task_revision_decision.schema_version",
            ),
            decision_id=require_non_empty_str(data.get("decision_id"), "task_revision_decision.decision_id"),
            request_ref=validate_ref(data.get("request_ref"), "task_revision_decision.request_ref"),
            request_id=require_non_empty_str(data.get("request_id"), "task_revision_decision.request_id"),
            current_contract_ref=validate_ref(
                data.get("current_contract_ref"),
                "task_revision_decision.current_contract_ref",
            ),
            current_contract_hash=_validate_hash(
                data.get("current_contract_hash"),
                "task_revision_decision.current_contract_hash",
            ),
            decision=require_enum(data.get("decision"), TaskRevisionDecisionStatus, "task_revision_decision.decision"),
            decided_by=require_non_empty_str(data.get("decided_by"), "task_revision_decision.decided_by"),
            authority=require_enum(
                data.get("authority", TaskRevisionAuthority.PRODUCT_INTEGRATION.value),
                TaskRevisionAuthority,
                "task_revision_decision.authority",
            ),
            rationale_refs=_ref_list(data.get("rationale_refs", []), "task_revision_decision.rationale_refs"),
            revised_contract_ref=_optional_empty_ref(
                data.get("revised_contract_ref", ""),
                "task_revision_decision.revised_contract_ref",
            ),
            revised_contract_hash=_optional_empty_str(
                data.get("revised_contract_hash", ""),
                "task_revision_decision.revised_contract_hash",
            ),
        )
        decision.validate()
        return decision

    def validate(self) -> None:
        _require_schema(self.schema_version, TASK_REVISION_DECISION_SCHEMA_VERSION, "task_revision_decision.schema_version")
        require_non_empty_str(self.decision_id, "task_revision_decision.decision_id")
        validate_ref(self.request_ref, "task_revision_decision.request_ref")
        require_non_empty_str(self.request_id, "task_revision_decision.request_id")
        validate_ref(self.current_contract_ref, "task_revision_decision.current_contract_ref")
        _validate_hash(self.current_contract_hash, "task_revision_decision.current_contract_hash")
        decision = require_enum(self.decision, TaskRevisionDecisionStatus, "task_revision_decision.decision")
        require_non_empty_str(self.decided_by, "task_revision_decision.decided_by")
        require_enum(self.authority, TaskRevisionAuthority, "task_revision_decision.authority")
        _validate_unique_refs(self.rationale_refs, "task_revision_decision.rationale_refs")
        if decision is TaskRevisionDecisionStatus.APPROVED:
            validate_ref(self.revised_contract_ref, "task_revision_decision.revised_contract_ref")
            _validate_hash(self.revised_contract_hash, "task_revision_decision.revised_contract_hash")
            if self.revised_contract_hash == self.current_contract_hash:
                raise ContractValidationError("approved task_revision_decision requires changed contract hash")
        elif self.revised_contract_ref or self.revised_contract_hash:
            raise ContractValidationError("non-approved task_revision_decision cannot include revised contract refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "task_revision_decision")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "request_ref": self.request_ref,
            "request_id": self.request_id,
            "current_contract_ref": self.current_contract_ref,
            "current_contract_hash": self.current_contract_hash,
            "decision": self.decision.value,
            "decided_by": self.decided_by,
            "authority": self.authority.value,
            "rationale_refs": list(self.rationale_refs),
            "revised_contract_ref": self.revised_contract_ref,
            "revised_contract_hash": self.revised_contract_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def validate_repair_brief_for_judge(
    brief: RepairBrief,
    packet: JudgePacket,
    report: JudgeReport,
    *,
    run_id: str | None = None,
) -> None:
    """Validate that a repair brief belongs to a judge decision."""

    brief.validate()
    packet.validate()
    report.validate()
    _require_judge_contract_binding(brief, packet, report, "repair_brief", run_id=run_id)
    _require_subset_refs(brief.target_artifact_refs, packet.artifact_refs, "repair_brief.target_artifact_refs")
    _require_subset_refs(brief.evidence_refs, _judged_evidence_refs(packet, report), "repair_brief.evidence_refs")


def validate_revision_request_for_judge(
    request: TaskRevisionRequest,
    packet: JudgePacket,
    report: JudgeReport,
    *,
    run_id: str | None = None,
) -> None:
    """Validate that a revision request belongs to a judge decision."""

    request.validate()
    packet.validate()
    report.validate()
    _require_judge_contract_binding(request, packet, report, "task_revision_request", run_id=run_id)
    _require_subset_refs(request.evidence_refs, _judged_evidence_refs(packet, report), "task_revision_request.evidence_refs")


def _require_judge_contract_binding(
    artifact: RepairBrief | TaskRevisionRequest,
    packet: JudgePacket,
    report: JudgeReport,
    field_name: str,
    *,
    run_id: str | None,
) -> None:
    if run_id is not None and artifact.run_id != run_id:
        raise ContractValidationError(f"{field_name}.run_id does not match active run")
    if artifact.contract_id != packet.contract_id or artifact.contract_id != report.contract_id:
        raise ContractValidationError(f"{field_name}.contract_id does not match judge packet/report")
    if artifact.contract_hash != packet.contract_hash or artifact.contract_hash != report.contract_hash:
        raise ContractValidationError(f"{field_name}.contract_hash does not match judge packet/report")
    if artifact.contract_ref != packet.contract_ref or artifact.contract_ref != report.contract_ref:
        raise ContractValidationError(f"{field_name}.contract_ref does not match judge packet/report")
    if artifact.judge_packet_ref != report.packet_ref:
        raise ContractValidationError(f"{field_name}.judge_packet_ref does not match judge report packet_ref")
    if artifact.judge_report_ref != packet.report_ref:
        raise ContractValidationError(f"{field_name}.judge_report_ref does not match judge packet report_ref")
    if artifact.execution_report_ref != packet.execution_report_ref:
        raise ContractValidationError(f"{field_name}.execution_report_ref does not match judge packet")


def _judged_evidence_refs(packet: JudgePacket, report: JudgeReport) -> list[str]:
    return _unique_refs([packet.execution_report_ref, *packet.evidence_refs, *packet.hard_check_refs, *report.evidence_refs])


def _require_subset_refs(values: list[str], allowed_values: list[str], field_name: str) -> None:
    allowed = set(_unique_refs(allowed_values))
    for ref in _unique_refs(values):
        if ref not in allowed:
            raise ContractValidationError(f"{field_name} contains ref outside judge packet/report: {ref}")


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
        safe_ref = validate_ref(ref, "agentic_repair.ref")
        if safe_ref not in result:
            result.append(safe_ref)
    return result


def _optional_empty_ref(value: Any, field_name: str) -> str:
    if value == "":
        return ""
    return validate_ref(value, field_name)


def _optional_empty_str(value: Any, field_name: str) -> str:
    if value == "":
        return ""
    return require_non_empty_str(value, field_name)


def _validate_hash(value: Any, field_name: str) -> str:
    hash_value = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not hash_value.startswith(prefix):
        raise ContractValidationError(f"{field_name} must start with {prefix!r}")
    digest = hash_value[len(prefix):]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ContractValidationError(f"{field_name} must be a sha256 hex digest")
    return hash_value


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"unsupported {field_name}: {actual}")


__all__ = [
    "REPAIR_BRIEF_SCHEMA_VERSION",
    "TASK_REVISION_DECISION_SCHEMA_VERSION",
    "TASK_REVISION_REQUEST_SCHEMA_VERSION",
    "RepairBrief",
    "TaskRevisionAuthority",
    "TaskRevisionDecision",
    "TaskRevisionDecisionStatus",
    "TaskRevisionRequest",
    "validate_repair_brief_for_judge",
    "validate_revision_request_for_judge",
]
