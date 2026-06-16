"""Product contracts for the thin academic DeepResearch integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from missionforge.contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


RESEARCH_REQUEST_SCHEMA_VERSION = "missionforge_deepresearch.research_request.v1"
RUN_RESULT_SCHEMA_VERSION = "missionforge_deepresearch.run_result.v1"
REVIEWED_RUN_RESULT_SCHEMA_VERSION = "missionforge_deepresearch.reviewed_run_result.v1"


class ResearchIntensity(StrEnum):
    """User-facing research depth budget for DeepResearch runs."""

    QUICK = "quick"
    STANDARD = "standard"
    INTENSIVE = "intensive"


class DeepResearchRunStatus(StrEnum):
    """Product facade status for the single-agent baseline."""

    DRAFT_READY = "draft_ready"
    FAILED = "failed"
    BLOCKED = "blocked"


class DeepResearchReviewedRunStatus(StrEnum):
    """Product facade status for reviewer-guided draft runs."""

    DRAFT_READY = "draft_ready"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ResearchIntensityProfile:
    """Mechanical budget and rubric preset derived from research intensity."""

    intensity: ResearchIntensity
    max_sources: int
    max_search_queries: int
    default_review_rounds: int
    max_review_rounds: int
    search_intent_max_turns: int
    researcher_max_turns: int
    reviewer_max_turns: int
    judge_max_turns: int
    piworker_timeout_seconds: int
    piworker_reasoning: str
    guidance: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "intensity": self.intensity.value,
            "max_sources": self.max_sources,
            "max_search_queries": self.max_search_queries,
            "default_review_rounds": self.default_review_rounds,
            "max_review_rounds": self.max_review_rounds,
            "search_intent_max_turns": self.search_intent_max_turns,
            "researcher_max_turns": self.researcher_max_turns,
            "reviewer_max_turns": self.reviewer_max_turns,
            "judge_max_turns": self.judge_max_turns,
            "piworker_timeout_seconds": self.piworker_timeout_seconds,
            "piworker_reasoning": self.piworker_reasoning,
            "guidance": self.guidance,
        }


def research_intensity_profile(value: ResearchIntensity | str) -> ResearchIntensityProfile:
    """Return the product-layer budget preset for a research intensity."""

    intensity = require_enum(value, ResearchIntensity, "research_intensity")
    profiles = {
        ResearchIntensity.QUICK: ResearchIntensityProfile(
            intensity=ResearchIntensity.QUICK,
            max_sources=10,
            max_search_queries=3,
            default_review_rounds=1,
            max_review_rounds=1,
            search_intent_max_turns=3,
            researcher_max_turns=12,
            reviewer_max_turns=4,
            judge_max_turns=4,
            piworker_timeout_seconds=600,
            piworker_reasoning="medium",
            guidance=(
                "Produce a concise scan. Prioritize the most central sources, "
                "state uncertainty clearly, and avoid exhaustive coverage claims."
            ),
        ),
        ResearchIntensity.STANDARD: ResearchIntensityProfile(
            intensity=ResearchIntensity.STANDARD,
            max_sources=24,
            max_search_queries=6,
            default_review_rounds=2,
            max_review_rounds=2,
            search_intent_max_turns=4,
            researcher_max_turns=20,
            reviewer_max_turns=6,
            judge_max_turns=6,
            piworker_timeout_seconds=900,
            piworker_reasoning="medium",
            guidance=(
                "Produce a balanced deep research report with representative "
                "coverage, current evidence, citations, deltas, and explicit gaps."
            ),
        ),
        ResearchIntensity.INTENSIVE: ResearchIntensityProfile(
            intensity=ResearchIntensity.INTENSIVE,
            max_sources=48,
            max_search_queries=12,
            default_review_rounds=3,
            max_review_rounds=4,
            search_intent_max_turns=6,
            researcher_max_turns=40,
            reviewer_max_turns=8,
            judge_max_turns=8,
            piworker_timeout_seconds=1800,
            piworker_reasoning="high",
            guidance=(
                "Produce a higher-recall investigation. Use broader query "
                "coverage, cross-check claims across source types, surface "
                "competing evidence, and make gaps explicit instead of compressing them away."
            ),
        ),
    }
    return profiles[intensity]


@dataclass(frozen=True)
class AcademicResearchRequest:
    """Sanitized academic research request."""

    request_id: str
    topic: str
    audience: str = "R&D team"
    language: str = "zh"
    research_intensity: ResearchIntensity = ResearchIntensity.STANDARD
    previous_run_refs: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    schema_version: str = RESEARCH_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "research_intensity",
            require_enum(
                self.research_intensity,
                ResearchIntensity,
                "academic_research_request.research_intensity",
            ),
        )

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
                "research_intensity",
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
            research_intensity=require_enum(
                data.get("research_intensity", ResearchIntensity.STANDARD.value),
                ResearchIntensity,
                "academic_research_request.research_intensity",
            ),
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
        require_enum(
            self.research_intensity,
            ResearchIntensity,
            "academic_research_request.research_intensity",
        )
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
            "research_intensity": require_enum(
                self.research_intensity,
                ResearchIntensity,
                "academic_research_request.research_intensity",
            ).value,
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


@dataclass(frozen=True)
class DeepResearchReviewedRunResult:
    """Refs-first product result for reviewer-guided research updates."""

    request_id: str
    status: DeepResearchReviewedRunStatus
    run_workspace_ref: str
    reviewed_run_result_ref: str
    final_run_result_ref: str
    review_round_count: int
    reviewer_report_refs: list[str]
    research_state_refs: list[str]
    reviewer_call_refs: list[str]
    reviewer_call_result_refs: list[str]
    revision_call_refs: list[str]
    revision_call_result_refs: list[str]
    evidence_refs: list[str]
    metric_refs: list[str]
    contract_hash: str
    schema_version: str = REVIEWED_RUN_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeepResearchReviewedRunResult":
        data = require_mapping(payload, "deepresearch_reviewed_run_result")
        result = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", REVIEWED_RUN_RESULT_SCHEMA_VERSION),
                "deepresearch_reviewed_run_result.schema_version",
            ),
            request_id=require_non_empty_str(data.get("request_id"), "deepresearch_reviewed_run_result.request_id"),
            status=require_enum(
                data.get("status"),
                DeepResearchReviewedRunStatus,
                "deepresearch_reviewed_run_result.status",
            ),
            run_workspace_ref=validate_ref(
                data.get("run_workspace_ref"),
                "deepresearch_reviewed_run_result.run_workspace_ref",
            ),
            reviewed_run_result_ref=validate_ref(
                data.get("reviewed_run_result_ref"),
                "deepresearch_reviewed_run_result.reviewed_run_result_ref",
            ),
            final_run_result_ref=validate_ref(
                data.get("final_run_result_ref"),
                "deepresearch_reviewed_run_result.final_run_result_ref",
            ),
            review_round_count=require_int_at_least(
                data.get("review_round_count"),
                "deepresearch_reviewed_run_result.review_round_count",
                0,
            ),
            reviewer_report_refs=_ref_list(
                data.get("reviewer_report_refs", []),
                "deepresearch_reviewed_run_result.reviewer_report_refs",
            ),
            research_state_refs=_ref_list(
                data.get("research_state_refs", []),
                "deepresearch_reviewed_run_result.research_state_refs",
            ),
            reviewer_call_refs=_ref_list(
                data.get("reviewer_call_refs", []),
                "deepresearch_reviewed_run_result.reviewer_call_refs",
            ),
            reviewer_call_result_refs=_ref_list(
                data.get("reviewer_call_result_refs", []),
                "deepresearch_reviewed_run_result.reviewer_call_result_refs",
            ),
            revision_call_refs=_ref_list(
                data.get("revision_call_refs", []),
                "deepresearch_reviewed_run_result.revision_call_refs",
            ),
            revision_call_result_refs=_ref_list(
                data.get("revision_call_result_refs", []),
                "deepresearch_reviewed_run_result.revision_call_result_refs",
            ),
            evidence_refs=_ref_list(data.get("evidence_refs", []), "deepresearch_reviewed_run_result.evidence_refs"),
            metric_refs=_ref_list(data.get("metric_refs", []), "deepresearch_reviewed_run_result.metric_refs"),
            contract_hash=require_non_empty_str(
                data.get("contract_hash"),
                "deepresearch_reviewed_run_result.contract_hash",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != REVIEWED_RUN_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("deepresearch_reviewed_run_result.schema_version is unsupported")
        require_non_empty_str(self.request_id, "deepresearch_reviewed_run_result.request_id")
        require_enum(self.status, DeepResearchReviewedRunStatus, "deepresearch_reviewed_run_result.status")
        for field_name in ("run_workspace_ref", "reviewed_run_result_ref", "final_run_result_ref"):
            validate_ref(getattr(self, field_name), f"deepresearch_reviewed_run_result.{field_name}")
        require_int_at_least(self.review_round_count, "deepresearch_reviewed_run_result.review_round_count", 0)
        _validate_unique_refs(self.reviewer_report_refs, "deepresearch_reviewed_run_result.reviewer_report_refs")
        _validate_unique_refs(self.research_state_refs, "deepresearch_reviewed_run_result.research_state_refs")
        _validate_unique_refs(self.reviewer_call_refs, "deepresearch_reviewed_run_result.reviewer_call_refs")
        _validate_unique_refs(
            self.reviewer_call_result_refs,
            "deepresearch_reviewed_run_result.reviewer_call_result_refs",
        )
        _validate_unique_refs(self.revision_call_refs, "deepresearch_reviewed_run_result.revision_call_refs")
        _validate_unique_refs(
            self.revision_call_result_refs,
            "deepresearch_reviewed_run_result.revision_call_result_refs",
        )
        _validate_unique_refs(self.evidence_refs, "deepresearch_reviewed_run_result.evidence_refs")
        _validate_unique_refs(self.metric_refs, "deepresearch_reviewed_run_result.metric_refs")
        require_non_empty_str(self.contract_hash, "deepresearch_reviewed_run_result.contract_hash")
        assert_refs_only_payload(self.to_dict_without_validation(), "deepresearch_reviewed_run_result")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "status": self.status.value,
            "run_workspace_ref": self.run_workspace_ref,
            "reviewed_run_result_ref": self.reviewed_run_result_ref,
            "final_run_result_ref": self.final_run_result_ref,
            "review_round_count": self.review_round_count,
            "reviewer_report_refs": list(self.reviewer_report_refs),
            "research_state_refs": list(self.research_state_refs),
            "reviewer_call_refs": list(self.reviewer_call_refs),
            "reviewer_call_result_refs": list(self.reviewer_call_result_refs),
            "revision_call_refs": list(self.revision_call_refs),
            "revision_call_result_refs": list(self.revision_call_result_refs),
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
