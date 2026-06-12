"""Minimal PiWorker call boundary.

One PiWorker call is treated as an unreliable intelligence RPC: MissionForge
declares the refs, write scope, expected outputs, and contract binding; the
worker decides how to do semantic work inside those boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .agentic_repair_controller import RepairExecutionDirective
from .agentic_revision_controller import RevisionPendingRecord
from .agent_packets import AgentExecutionPacket, JudgePacket
from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from .workers import WorkerAdapterResult


PIWORKER_CALL_SCHEMA_VERSION = "piworker_call.v1"
PIWORKER_CALL_RESULT_SCHEMA_VERSION = "piworker_call_result.v1"


class PiWorkerCallRole(StrEnum):
    """Role-specific PiWorker call authority."""

    FRONTDESK_AUTHOR = "frontdesk_author_piworker"
    EXECUTOR = "executor_piworker"
    JUDGE = "judge_piworker"
    REPAIR = "repair_piworker"
    REVISION_DRAFTER = "revision_drafter_piworker"


class PiWorkerCallResultStatus(StrEnum):
    """Deterministic boundary status for one unreliable intelligence call."""

    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    INVALID_OUTPUT = "invalid_output"
    UNAUTHORIZED_OUTPUT = "unauthorized_output"
    RUNTIME_ERROR = "runtime_error"


@dataclass(frozen=True)
class PiWorkerCall:
    """Refs-first contract for one bounded PiWorker/LLM invocation."""

    call_id: str
    role: PiWorkerCallRole
    contract_id: str
    contract_hash: str
    contract_ref: str
    objective: str
    visible_refs: list[str] = field(default_factory=list)
    writable_refs: list[str] = field(default_factory=list)
    expected_output_refs: list[str] = field(default_factory=list)
    permission_manifest_ref: str | None = None
    source_packet_ref: str | None = None
    source_packet_hash: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    output_schema_ref: str | None = None
    validation_policy_ref: str | None = None
    runtime_budget: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = PIWORKER_CALL_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PiWorkerCall":
        data = _refs_only_mapping(payload, "piworker_call")
        _reject_unknown_fields(data, _PIWORKER_CALL_FIELDS, "piworker_call")
        call = cls(
            call_id=require_non_empty_str(data.get("call_id"), "piworker_call.call_id"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PIWORKER_CALL_SCHEMA_VERSION),
                "piworker_call.schema_version",
            ),
            role=require_enum(data.get("role"), PiWorkerCallRole, "piworker_call.role"),
            contract_id=require_non_empty_str(data.get("contract_id"), "piworker_call.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "piworker_call.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "piworker_call.contract_ref"),
            objective=require_non_empty_str(data.get("objective"), "piworker_call.objective"),
            visible_refs=_ref_list(data.get("visible_refs", []), "piworker_call.visible_refs"),
            writable_refs=_ref_list(data.get("writable_refs", []), "piworker_call.writable_refs"),
            expected_output_refs=_ref_list(
                data.get("expected_output_refs", []),
                "piworker_call.expected_output_refs",
            ),
            permission_manifest_ref=_optional_ref(
                data.get("permission_manifest_ref"),
                "piworker_call.permission_manifest_ref",
            ),
            source_packet_ref=_optional_ref(data.get("source_packet_ref"), "piworker_call.source_packet_ref"),
            source_packet_hash=_optional_hash(data.get("source_packet_hash"), "piworker_call.source_packet_hash"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "piworker_call.evidence_refs"),
            output_schema_ref=_optional_ref(data.get("output_schema_ref"), "piworker_call.output_schema_ref"),
            validation_policy_ref=_optional_ref(
                data.get("validation_policy_ref"),
                "piworker_call.validation_policy_ref",
            ),
            runtime_budget=_runtime_budget(data.get("runtime_budget", {})),
            metadata=_metadata(data.get("metadata", {})),
        )
        call.validate()
        return call

    @classmethod
    def from_execution_packet(
        cls,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        objective: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "PiWorkerCall":
        """Build an executor call from a role-separated execution packet."""

        packet.validate()
        packet_hash = stable_json_hash(packet.to_dict())
        call = cls(
            call_id=packet.packet_id,
            role=PiWorkerCallRole.EXECUTOR,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            objective=objective or f"Produce expected artifacts for {packet.contract_id}.",
            visible_refs=_dedupe_refs(
                [
                    packet.contract_ref,
                    packet.worker_brief_ref,
                    packet.workspace_policy_ref,
                    packet.permission_manifest_ref,
                    *packet.allowed_input_refs,
                ]
            ),
            writable_refs=list(packet.writable_refs),
            expected_output_refs=list(packet.expected_artifact_refs),
            permission_manifest_ref=packet.permission_manifest_ref,
            source_packet_ref=packet_ref,
            source_packet_hash=packet_hash,
            output_schema_ref="schemas/agent_execution_report.json",
            validation_policy_ref="validation/piworker_executor_policy.json",
            metadata=metadata or {},
        )
        call.validate()
        return call

    @classmethod
    def from_judge_packet(
        cls,
        packet: JudgePacket,
        *,
        packet_ref: str,
        spec_ref: str,
        packet_hash: str | None = None,
        objective: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "PiWorkerCall":
        """Build a judge call from a role-separated judge packet."""

        packet.validate()
        effective_packet_hash = packet_hash or stable_json_hash(packet.to_dict())
        call = cls(
            call_id=packet.packet_id,
            role=PiWorkerCallRole.JUDGE,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            objective=objective or f"Judge execution evidence for {packet.contract_id} and write JudgeReport JSON only.",
            visible_refs=_dedupe_refs(
                [
                    validate_ref(spec_ref, "piworker_call.spec_ref"),
                    packet_ref,
                    packet.contract_ref,
                    packet.judge_rubric_ref,
                    packet.execution_packet_ref,
                    packet.execution_report_ref,
                    *packet.artifact_refs,
                    *packet.evidence_refs,
                    *packet.hard_check_refs,
                ]
            ),
            writable_refs=_dedupe_refs(
                [
                    packet.report_ref,
                    "reports/judge_rationale.md",
                    "projections/repair_brief.json",
                    "revisions/request.json",
                ]
            ),
            expected_output_refs=[packet.report_ref],
            source_packet_ref=packet_ref,
            source_packet_hash=effective_packet_hash,
            output_schema_ref="schemas/judge_report.json",
            validation_policy_ref="validation/piworker_judge_policy.json",
            metadata=metadata or {"hard_check_status": packet.hard_check_status.value},
        )
        call.validate()
        return call

    @classmethod
    def from_repair_directive(
        cls,
        directive: RepairExecutionDirective,
        *,
        directive_ref: str,
        contract_ref: str,
        permission_manifest_ref: str,
        writable_refs: list[str],
        objective: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "PiWorkerCall":
        """Build a repair call from a frozen same-contract repair directive."""

        directive.validate()
        directive_hash = stable_json_hash(directive.to_dict())
        call = cls(
            call_id=directive.directive_id,
            role=PiWorkerCallRole.REPAIR,
            contract_id=directive.contract_id,
            contract_hash=directive.contract_hash,
            contract_ref=validate_ref(contract_ref, "piworker_call.contract_ref"),
            objective=objective or f"Repair artifacts for {directive.contract_id} without changing the frozen contract.",
            visible_refs=_dedupe_refs(
                [
                    validate_ref(directive_ref, "piworker_call.directive_ref"),
                    contract_ref,
                    directive.repair_ticket_ref,
                    directive.source_result_ref,
                    directive.source_repair_brief_ref,
                    directive.worker_brief_ref,
                    permission_manifest_ref,
                    *directive.context_refs,
                ]
            ),
            writable_refs=list(writable_refs),
            expected_output_refs=list(directive.target_artifact_refs),
            permission_manifest_ref=permission_manifest_ref,
            source_packet_ref=directive_ref,
            source_packet_hash=directive_hash,
            evidence_refs=_dedupe_refs(
                [
                    directive.source_result_ref,
                    directive.source_repair_brief_ref,
                    directive.repair_ticket_ref,
                ]
            ),
            output_schema_ref="schemas/agent_execution_report.json",
            validation_policy_ref="validation/piworker_repair_policy.json",
            metadata=metadata or {"repair_ticket_ref": directive.repair_ticket_ref},
        )
        call.validate()
        return call

    @classmethod
    def from_revision_pending_record(
        cls,
        pending: RevisionPendingRecord,
        *,
        pending_ref: str,
        permission_manifest_ref: str,
        writable_refs: list[str],
        expected_output_ref: str,
        objective: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "PiWorkerCall":
        """Build a revision-drafting call from an explicit revision request."""

        pending.validate()
        pending_hash = stable_json_hash(pending.to_dict())
        call = cls(
            call_id=pending.pending_id,
            role=PiWorkerCallRole.REVISION_DRAFTER,
            contract_id=pending.contract_id,
            contract_hash=pending.contract_hash,
            contract_ref=pending.contract_ref,
            objective=objective or f"Draft a revised TaskContract proposal for {pending.contract_id}.",
            visible_refs=_dedupe_refs(
                [
                    validate_ref(pending_ref, "piworker_call.pending_ref"),
                    pending.contract_ref,
                    pending.source_result_ref,
                    pending.source_judge_report_ref,
                    pending.source_revision_request_ref,
                    pending.execution_packet_ref,
                    pending.execution_report_ref,
                    pending.judge_packet_ref,
                    pending.judge_report_ref,
                    permission_manifest_ref,
                    *pending.evidence_refs,
                ]
            ),
            writable_refs=list(writable_refs),
            expected_output_refs=[validate_ref(expected_output_ref, "piworker_call.expected_output_ref")],
            permission_manifest_ref=permission_manifest_ref,
            source_packet_ref=pending_ref,
            source_packet_hash=pending_hash,
            evidence_refs=_dedupe_refs(
                [
                    pending.source_result_ref,
                    pending.source_judge_report_ref,
                    pending.source_revision_request_ref,
                    *pending.evidence_refs,
                ]
            ),
            output_schema_ref="schemas/task_contract_revision_draft.json",
            validation_policy_ref="validation/piworker_revision_policy.json",
            metadata=metadata or {"authority_required": pending.authority_required.value},
        )
        call.validate()
        return call

    def validate(self) -> None:
        if self.schema_version != PIWORKER_CALL_SCHEMA_VERSION:
            raise ContractValidationError(f"unsupported piworker_call.schema_version: {self.schema_version}")
        require_non_empty_str(self.call_id, "piworker_call.call_id")
        require_enum(self.role, PiWorkerCallRole, "piworker_call.role")
        require_non_empty_str(self.contract_id, "piworker_call.contract_id")
        _validate_hash(self.contract_hash, "piworker_call.contract_hash")
        validate_ref(self.contract_ref, "piworker_call.contract_ref")
        require_non_empty_str(self.objective, "piworker_call.objective")
        _validate_unique_refs(self.visible_refs, "piworker_call.visible_refs")
        _validate_unique_refs(self.writable_refs, "piworker_call.writable_refs")
        _validate_unique_refs(self.expected_output_refs, "piworker_call.expected_output_refs")
        _validate_unique_refs(self.evidence_refs, "piworker_call.evidence_refs")
        if not self.expected_output_refs:
            raise ContractValidationError("piworker_call.expected_output_refs must contain at least one ref")
        _validate_refs_under_roots(
            self.expected_output_refs,
            self.writable_refs,
            "piworker_call.expected_output_refs",
        )
        _optional_ref(self.permission_manifest_ref, "piworker_call.permission_manifest_ref")
        _optional_ref(self.source_packet_ref, "piworker_call.source_packet_ref")
        _optional_hash(self.source_packet_hash, "piworker_call.source_packet_hash")
        _optional_ref(self.output_schema_ref, "piworker_call.output_schema_ref")
        _optional_ref(self.validation_policy_ref, "piworker_call.validation_policy_ref")
        _runtime_budget(self.runtime_budget)
        _metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "call_id": self.call_id,
            "schema_version": self.schema_version,
            "role": self.role.value,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "objective": self.objective,
            "visible_refs": list(self.visible_refs),
            "writable_refs": list(self.writable_refs),
            "expected_output_refs": list(self.expected_output_refs),
            "permission_manifest_ref": self.permission_manifest_ref,
            "source_packet_ref": self.source_packet_ref,
            "source_packet_hash": self.source_packet_hash,
            "evidence_refs": list(self.evidence_refs),
            "output_schema_ref": self.output_schema_ref,
            "validation_policy_ref": self.validation_policy_ref,
            "runtime_budget": dict(self.runtime_budget),
            "metadata": dict(self.metadata),
        }

@dataclass(frozen=True)
class PiWorkerCallResult:
    """Refs-first result envelope for one bounded PiWorker invocation.

    This result records whether the call boundary completed. It does not grant
    semantic acceptance; acceptance must come from an independent judge artifact.
    """

    result_id: str
    call_id: str
    role: PiWorkerCallRole
    contract_id: str
    contract_hash: str
    contract_ref: str
    status: PiWorkerCallResultStatus
    execution_report_ref: str
    output_refs: list[str] = field(default_factory=list)
    runtime_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    validation_report_ref: str | None = None
    error_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = PIWORKER_CALL_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PiWorkerCallResult":
        data = _refs_only_mapping(payload, "piworker_call_result")
        _reject_unknown_fields(data, _PIWORKER_CALL_RESULT_FIELDS, "piworker_call_result")
        result = cls(
            result_id=require_non_empty_str(data.get("result_id"), "piworker_call_result.result_id"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PIWORKER_CALL_RESULT_SCHEMA_VERSION),
                "piworker_call_result.schema_version",
            ),
            call_id=require_non_empty_str(data.get("call_id"), "piworker_call_result.call_id"),
            role=require_enum(data.get("role"), PiWorkerCallRole, "piworker_call_result.role"),
            contract_id=require_non_empty_str(data.get("contract_id"), "piworker_call_result.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "piworker_call_result.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "piworker_call_result.contract_ref"),
            status=require_enum(data.get("status"), PiWorkerCallResultStatus, "piworker_call_result.status"),
            execution_report_ref=validate_ref(
                data.get("execution_report_ref"),
                "piworker_call_result.execution_report_ref",
            ),
            output_refs=_ref_list(data.get("output_refs", []), "piworker_call_result.output_refs"),
            runtime_refs=_ref_list(data.get("runtime_refs", []), "piworker_call_result.runtime_refs"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "piworker_call_result.evidence_refs"),
            metric_refs=_ref_list(data.get("metric_refs", []), "piworker_call_result.metric_refs"),
            validation_report_ref=_optional_ref(
                data.get("validation_report_ref"),
                "piworker_call_result.validation_report_ref",
            ),
            error_ref=_optional_ref(data.get("error_ref"), "piworker_call_result.error_ref"),
            metadata=_metadata(data.get("metadata", {}), "piworker_call_result.metadata"),
        )
        result.validate()
        return result

    @classmethod
    def from_worker_adapter_result(
        cls,
        call: PiWorkerCall,
        worker_result: WorkerAdapterResult,
        *,
        result_id: str | None = None,
        validation_report_ref: str | None = None,
        error_ref: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "PiWorkerCallResult":
        """Normalize the legacy worker adapter envelope into PiWorkerCallResult."""

        call.validate()
        worker_result.validate()
        report = worker_result.execution_report
        if report.work_unit_id != call.call_id:
            raise ContractValidationError("worker_result.execution_report.work_unit_id does not match PiWorkerCall")
        output_refs = list(report.produced_artifacts)
        output_ref_set = set(output_refs)
        metric_refs = _metric_refs_from_mapping(report.metrics)
        runtime_refs = _dedupe_refs(
            [
                worker_result.worker_result.execution_report_ref,
                *[ref for ref in report.changed_refs if ref not in output_ref_set],
            ]
        )
        result = cls(
            result_id=result_id or f"{call.call_id}-result",
            call_id=call.call_id,
            role=call.role,
            contract_id=call.contract_id,
            contract_hash=call.contract_hash,
            contract_ref=call.contract_ref,
            status=_call_result_status(worker_result.worker_result.status),
            execution_report_ref=worker_result.worker_result.execution_report_ref,
            output_refs=output_refs,
            runtime_refs=runtime_refs,
            evidence_refs=_dedupe_refs([*report.evidence_refs, *worker_result.event_evidence_refs]),
            metric_refs=metric_refs,
            validation_report_ref=validation_report_ref,
            error_ref=error_ref,
            metadata=metadata or {},
        )
        result.validate_against_call(call)
        return result

    def validate(self) -> None:
        if self.schema_version != PIWORKER_CALL_RESULT_SCHEMA_VERSION:
            raise ContractValidationError(
                f"unsupported piworker_call_result.schema_version: {self.schema_version}"
            )
        require_non_empty_str(self.result_id, "piworker_call_result.result_id")
        require_non_empty_str(self.call_id, "piworker_call_result.call_id")
        require_enum(self.role, PiWorkerCallRole, "piworker_call_result.role")
        require_non_empty_str(self.contract_id, "piworker_call_result.contract_id")
        _validate_hash(self.contract_hash, "piworker_call_result.contract_hash")
        validate_ref(self.contract_ref, "piworker_call_result.contract_ref")
        require_enum(self.status, PiWorkerCallResultStatus, "piworker_call_result.status")
        validate_ref(self.execution_report_ref, "piworker_call_result.execution_report_ref")
        _validate_unique_refs(self.output_refs, "piworker_call_result.output_refs")
        _validate_unique_refs(self.runtime_refs, "piworker_call_result.runtime_refs")
        _validate_unique_refs(self.evidence_refs, "piworker_call_result.evidence_refs")
        _validate_unique_refs(self.metric_refs, "piworker_call_result.metric_refs")
        _optional_ref(self.validation_report_ref, "piworker_call_result.validation_report_ref")
        _optional_ref(self.error_ref, "piworker_call_result.error_ref")
        if self.status == PiWorkerCallResultStatus.COMPLETED and self.error_ref is not None:
            raise ContractValidationError("completed piworker_call_result must not have error_ref")
        _metadata(self.metadata, "piworker_call_result.metadata")

    def validate_against_call(self, call: PiWorkerCall) -> None:
        """Validate result authority against the frozen PiWorkerCall."""

        self.validate()
        call.validate()
        if self.call_id != call.call_id:
            raise ContractValidationError("piworker_call_result.call_id does not match call")
        if self.role != call.role:
            raise ContractValidationError("piworker_call_result.role does not match call")
        if self.contract_id != call.contract_id:
            raise ContractValidationError("piworker_call_result.contract_id does not match call")
        if self.contract_hash != call.contract_hash:
            raise ContractValidationError("piworker_call_result.contract_hash does not match call")
        if self.contract_ref != call.contract_ref:
            raise ContractValidationError("piworker_call_result.contract_ref does not match call")
        _validate_refs_under_roots(
            self.output_refs,
            call.writable_refs,
            "piworker_call_result.output_refs",
        )
        if self.status == PiWorkerCallResultStatus.COMPLETED:
            missing = sorted(set(call.expected_output_refs) - set(self.output_refs))
            if missing:
                raise ContractValidationError(
                    f"completed piworker_call_result is missing expected output refs: {missing}"
                )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "result_id": self.result_id,
            "schema_version": self.schema_version,
            "call_id": self.call_id,
            "role": self.role.value,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "status": self.status.value,
            "execution_report_ref": self.execution_report_ref,
            "output_refs": list(self.output_refs),
            "runtime_refs": list(self.runtime_refs),
            "evidence_refs": list(self.evidence_refs),
            "metric_refs": list(self.metric_refs),
            "validation_report_ref": self.validation_report_ref,
            "error_ref": self.error_ref,
            "metadata": dict(self.metadata),
        }


_PIWORKER_CALL_FIELDS = {
    "call_id",
    "schema_version",
    "role",
    "contract_id",
    "contract_hash",
    "contract_ref",
    "objective",
    "visible_refs",
    "writable_refs",
    "expected_output_refs",
    "permission_manifest_ref",
    "source_packet_ref",
    "source_packet_hash",
    "evidence_refs",
    "output_schema_ref",
    "validation_policy_ref",
    "runtime_budget",
    "metadata",
}

_PIWORKER_CALL_RESULT_FIELDS = {
    "result_id",
    "schema_version",
    "call_id",
    "role",
    "contract_id",
    "contract_hash",
    "contract_ref",
    "status",
    "execution_report_ref",
    "output_refs",
    "runtime_refs",
    "evidence_refs",
    "metric_refs",
    "validation_report_ref",
    "error_ref",
    "metadata",
}

_FORBIDDEN_METADATA_AUTHORITY_FIELDS = {
    "accepted",
    "acceptance",
    "decision",
    "final_decision",
    "judge_decision",
    "semantic_acceptance",
}


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(payload, field_name), field_name))


def _metadata(value: Any, field_name: str = "piworker_call.metadata") -> dict[str, Any]:
    metadata = _refs_only_mapping(require_mapping(value, field_name), field_name)
    _reject_forbidden_metadata_authority(metadata, field_name)
    return dict(ensure_json_value(metadata, field_name))


def _runtime_budget(value: Any) -> dict[str, Any]:
    budget = _refs_only_mapping(require_mapping(value, "piworker_call.runtime_budget"), "piworker_call.runtime_budget")
    allowed_fields = {"max_turns", "timeout_seconds", "max_tool_calls", "max_output_refs"}
    _reject_unknown_fields(budget, allowed_fields, "piworker_call.runtime_budget")
    result: dict[str, Any] = {}
    for key, item in budget.items():
        result[key] = require_int_at_least(item, f"piworker_call.runtime_budget.{key}", 1)
    return result


def _reject_forbidden_metadata_authority(value: Any, field_name: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = key.lower()
            if lowered in _FORBIDDEN_METADATA_AUTHORITY_FIELDS:
                raise ContractValidationError(f"{field_name}.{key} is not allowed to carry PiWorker authority")
            _reject_forbidden_metadata_authority(item, f"{field_name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_metadata_authority(item, f"{field_name}[{index}]")


def _reject_unknown_fields(data: Mapping[str, Any], allowed_fields: set[str], field_name: str) -> None:
    unknown = sorted(set(data) - allowed_fields)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unknown fields: {unknown}")


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return validate_ref(value, field_name)


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")


def _validate_refs_under_roots(refs: list[str], root_refs: list[str], field_name: str) -> None:
    if not root_refs:
        raise ContractValidationError(f"{field_name} requires writable_refs")
    for ref in refs:
        if not any(_ref_is_under(ref, root_ref) for root_ref in root_refs):
            raise ContractValidationError(f"{field_name} contains ref outside writable refs: {ref}")


def _ref_is_under(ref: str, root_ref: str) -> bool:
    safe_ref = validate_ref(ref, "ref")
    safe_root = validate_ref(root_ref, "root_ref")
    return safe_ref == safe_root or safe_ref.startswith(f"{safe_root}/")


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe_ref = validate_ref(ref, "ref")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result


def _validate_hash(value: Any, field_name: str) -> str:
    hash_value = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not hash_value.startswith(prefix):
        raise ContractValidationError(f"{field_name} must start with {prefix!r}")
    digest = hash_value[len(prefix):]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ContractValidationError(f"{field_name} must be a sha256 hex digest")
    return hash_value


def _optional_hash(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_hash(value, field_name)


def _call_result_status(status: str) -> PiWorkerCallResultStatus:
    normalized = require_non_empty_str(status, "worker_result.status").lower()
    if normalized in {"success", "succeeded"}:
        return PiWorkerCallResultStatus.COMPLETED
    if normalized in {"accepted", "acceptance", "approved"}:
        raise ContractValidationError("worker_result.status must not claim PiWorker acceptance authority")
    try:
        return PiWorkerCallResultStatus(normalized)
    except ValueError:
        return PiWorkerCallResultStatus.FAILED


def _metric_refs_from_mapping(metrics: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key, value in metrics.items():
        if key in {"metric_ref", "metrics_ref"} and isinstance(value, str):
            refs.append(validate_ref(value, f"worker_result.metrics.{key}"))
    return _dedupe_refs(refs)
