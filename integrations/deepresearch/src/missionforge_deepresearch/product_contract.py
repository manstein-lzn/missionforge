"""Product contracts for the thin academic DeepResearch integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from missionforge.contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


RESEARCH_REQUEST_SCHEMA_VERSION = "missionforge_deepresearch.research_request.v1"
RUN_RESULT_SCHEMA_VERSION = "missionforge_deepresearch.run_result.v1"


class DeepResearchRunStatus(StrEnum):
    """Product facade status for the single-agent baseline."""

    DRAFT_READY = "draft_ready"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AcademicResearchRequest:
    """Sanitized academic research request."""

    request_id: str
    topic: str
    audience: str = "R&D team"
    language: str = "zh"
    previous_run_refs: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    schema_version: str = RESEARCH_REQUEST_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AcademicResearchRequest":
        data = _strict_mapping(
            payload,
            "academic_research_request",
            {
                "schema_version",
                "request_id",
                "topic",
                "audience",
                "language",
                "previous_run_refs",
                "constraints",
                "non_goals",
            },
        )
        request = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", RESEARCH_REQUEST_SCHEMA_VERSION),
                "academic_research_request.schema_version",
            ),
            request_id=require_non_empty_str(data.get("request_id"), "academic_research_request.request_id"),
            topic=require_non_empty_str(data.get("topic"), "academic_research_request.topic"),
            audience=require_non_empty_str(data.get("audience", "R&D team"), "academic_research_request.audience"),
            language=require_non_empty_str(data.get("language", "zh"), "academic_research_request.language"),
            previous_run_refs=_ref_list(
                data.get("previous_run_refs", []),
                "academic_research_request.previous_run_refs",
            ),
            constraints=require_str_list(data.get("constraints", []), "academic_research_request.constraints"),
            non_goals=require_str_list(data.get("non_goals", []), "academic_research_request.non_goals"),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if self.schema_version != RESEARCH_REQUEST_SCHEMA_VERSION:
            raise ContractValidationError("academic_research_request.schema_version is unsupported")
        require_non_empty_str(self.request_id, "academic_research_request.request_id")
        _validate_request_id(self.request_id)
        require_non_empty_str(self.topic, "academic_research_request.topic")
        require_non_empty_str(self.audience, "academic_research_request.audience")
        require_non_empty_str(self.language, "academic_research_request.language")
        _validate_unique_refs(self.previous_run_refs, "academic_research_request.previous_run_refs")
        require_str_list(self.constraints, "academic_research_request.constraints")
        require_str_list(self.non_goals, "academic_research_request.non_goals")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "topic": self.topic,
            "audience": self.audience,
            "language": self.language,
            "previous_run_refs": list(self.previous_run_refs),
            "constraints": list(self.constraints),
            "non_goals": list(self.non_goals),
        }


@dataclass(frozen=True)
class DeepResearchRunResult:
    """Refs-first product run result for Phase 1."""

    request_id: str
    status: DeepResearchRunStatus
    run_workspace_ref: str
    run_result_ref: str
    task_contract_ref: str
    manual_ref: str
    source_packet_ref: str
    output_contract_ref: str
    researcher_call_ref: str
    researcher_call_result_ref: str
    structural_check_ref: str
    draft_artifact_refs: list[str]
    evidence_refs: list[str]
    metric_refs: list[str]
    contract_hash: str
    schema_version: str = RUN_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeepResearchRunResult":
        data = require_mapping(payload, "deepresearch_run_result")
        result = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", RUN_RESULT_SCHEMA_VERSION),
                "deepresearch_run_result.schema_version",
            ),
            request_id=require_non_empty_str(data.get("request_id"), "deepresearch_run_result.request_id"),
            status=require_enum(data.get("status"), DeepResearchRunStatus, "deepresearch_run_result.status"),
            run_workspace_ref=validate_ref(data.get("run_workspace_ref"), "deepresearch_run_result.run_workspace_ref"),
            run_result_ref=validate_ref(data.get("run_result_ref"), "deepresearch_run_result.run_result_ref"),
            task_contract_ref=validate_ref(data.get("task_contract_ref"), "deepresearch_run_result.task_contract_ref"),
            manual_ref=validate_ref(data.get("manual_ref"), "deepresearch_run_result.manual_ref"),
            source_packet_ref=validate_ref(data.get("source_packet_ref"), "deepresearch_run_result.source_packet_ref"),
            output_contract_ref=validate_ref(
                data.get("output_contract_ref"),
                "deepresearch_run_result.output_contract_ref",
            ),
            researcher_call_ref=validate_ref(
                data.get("researcher_call_ref"),
                "deepresearch_run_result.researcher_call_ref",
            ),
            researcher_call_result_ref=validate_ref(
                data.get("researcher_call_result_ref"),
                "deepresearch_run_result.researcher_call_result_ref",
            ),
            structural_check_ref=validate_ref(
                data.get("structural_check_ref"),
                "deepresearch_run_result.structural_check_ref",
            ),
            draft_artifact_refs=_ref_list(data.get("draft_artifact_refs", []), "deepresearch_run_result.draft_artifact_refs"),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "deepresearch_run_result.evidence_refs"),
            metric_refs=_ref_list(data.get("metric_refs", []), "deepresearch_run_result.metric_refs"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "deepresearch_run_result.contract_hash"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != RUN_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("deepresearch_run_result.schema_version is unsupported")
        require_non_empty_str(self.request_id, "deepresearch_run_result.request_id")
        require_enum(self.status, DeepResearchRunStatus, "deepresearch_run_result.status")
        for field_name in (
            "run_workspace_ref",
            "run_result_ref",
            "task_contract_ref",
            "manual_ref",
            "source_packet_ref",
            "output_contract_ref",
            "researcher_call_ref",
            "researcher_call_result_ref",
            "structural_check_ref",
        ):
            validate_ref(getattr(self, field_name), f"deepresearch_run_result.{field_name}")
        _validate_unique_refs(self.draft_artifact_refs, "deepresearch_run_result.draft_artifact_refs")
        _validate_unique_refs(self.evidence_refs, "deepresearch_run_result.evidence_refs")
        _validate_unique_refs(self.metric_refs, "deepresearch_run_result.metric_refs")
        require_non_empty_str(self.contract_hash, "deepresearch_run_result.contract_hash")
        assert_refs_only_payload(self.to_dict_without_validation(), "deepresearch_run_result")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "status": self.status.value,
            "run_workspace_ref": self.run_workspace_ref,
            "run_result_ref": self.run_result_ref,
            "task_contract_ref": self.task_contract_ref,
            "manual_ref": self.manual_ref,
            "source_packet_ref": self.source_packet_ref,
            "output_contract_ref": self.output_contract_ref,
            "researcher_call_ref": self.researcher_call_ref,
            "researcher_call_result_ref": self.researcher_call_result_ref,
            "structural_check_ref": self.structural_check_ref,
            "draft_artifact_refs": list(self.draft_artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "metric_refs": list(self.metric_refs),
            "contract_hash": self.contract_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def _strict_mapping(payload: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unknown fields: {unknown}")
    return data


def _validate_request_id(request_id: str) -> None:
    validate_ref(f"runs/{request_id}", "academic_research_request.request_id")
    if "/" in request_id:
        raise ContractValidationError("academic_research_request.request_id must be one ref segment")


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")
