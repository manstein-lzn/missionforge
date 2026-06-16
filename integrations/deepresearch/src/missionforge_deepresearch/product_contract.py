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


_REPORT_SECTION_DEFINITIONS = [
    {
        "section_id": "scope_and_method",
        "canonical_title": "Scope And Method",
        "localized_titles": {"zh": "范围与方法"},
        "aliases": ["Scope & Method", "方法与范围"],
        "purpose": "Define the research question, time window, method, source strategy, and limits of the run.",
    },
    {
        "section_id": "evidence_base",
        "canonical_title": "Evidence Base",
        "localized_titles": {"zh": "证据基础"},
        "aliases": ["Evidence"],
        "purpose": "Summarize source coverage, source types, recentness, and evidence strength before drawing conclusions.",
    },
    {
        "section_id": "major_lines_of_work",
        "canonical_title": "Major Lines Of Work",
        "localized_titles": {"zh": "主要研究路线"},
        "aliases": ["Research Lines", "主要路线"],
        "purpose": "Organize the field into major technical schools, systems, papers, repositories, or benchmarks.",
    },
    {
        "section_id": "comparison_matrix",
        "canonical_title": "Comparison Matrix",
        "localized_titles": {"zh": "对比矩阵"},
        "aliases": ["Comparison Table", "对比表"],
        "purpose": "Compare methods by task, assumptions, benchmarks, reproducibility, evidence strength, and limitations.",
    },
    {
        "section_id": "counterevidence_and_failure_modes",
        "canonical_title": "Counterevidence And Failure Modes",
        "localized_titles": {"zh": "反证与失败模式"},
        "aliases": ["Counterevidence", "Failure Modes", "反证", "失败模式"],
        "purpose": "Surface negative evidence, weak claims, failed assumptions, competing interpretations, and risks.",
    },
    {
        "section_id": "research_delta",
        "canonical_title": "Research Delta",
        "localized_titles": {"zh": "研究变化"},
        "aliases": ["Delta", "变化分析"],
        "purpose": "Compare with previous run refs when present, or clearly mark the run as a baseline.",
    },
    {
        "section_id": "source_gaps",
        "canonical_title": "Source Gaps",
        "localized_titles": {"zh": "证据缺口"},
        "aliases": ["Evidence Gaps", "信息缺口"],
        "purpose": "Record missing sources, unresolved questions, inaccessible evidence, and follow-up searches.",
    },
    {
        "section_id": "references",
        "canonical_title": "References",
        "localized_titles": {"zh": "参考文献"},
        "aliases": ["Bibliography"],
        "purpose": "List every cited source id with title and a stable locator.",
    },
]

_QUALITY_DIMENSIONS = [
    {
        "dimension_id": "coverage",
        "standard": "Cover the major schools of work, not only the first sources found.",
        "user_visible_value": "broader source coverage",
    },
    {
        "dimension_id": "freshness",
        "standard": "Separate recent findings from historical background and stale claims.",
        "user_visible_value": "fewer outdated conclusions",
    },
    {
        "dimension_id": "citation_integrity",
        "standard": "Tie material claims to source ids and expose source provenance.",
        "user_visible_value": "stronger citations",
    },
    {
        "dimension_id": "synthesis",
        "standard": "Explain relationships, tradeoffs, and disagreement instead of listing papers.",
        "user_visible_value": "clearer field understanding",
    },
    {
        "dimension_id": "delta",
        "standard": "Compare with previous run refs or explicitly state that the run is a baseline.",
        "user_visible_value": "clearer changes over time",
    },
    {
        "dimension_id": "gaps_and_counterevidence",
        "standard": "Expose source gaps, weak evidence, counterevidence, and failure modes.",
        "user_visible_value": "less overclaiming",
    },
]


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
    min_source_records: int
    min_distinct_source_types: int
    min_recent_source_records: int
    required_report_sections: list[str]
    required_source_record_fields: list[str]
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
            "min_source_records": self.min_source_records,
            "min_distinct_source_types": self.min_distinct_source_types,
            "min_recent_source_records": self.min_recent_source_records,
            "required_report_sections": list(self.required_report_sections),
            "required_source_record_fields": list(self.required_source_record_fields),
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
    required_report_sections = [item["canonical_title"] for item in _REPORT_SECTION_DEFINITIONS]
    required_source_record_fields = [
        "source_id",
        "title",
        "source_type",
        "year",
        "accessed_at",
        "evidence_note",
        "evidence_strength",
    ]
    profiles = {
        ResearchIntensity.QUICK: ResearchIntensityProfile(
            intensity=ResearchIntensity.QUICK,
            max_sources=10,
            max_search_queries=3,
            min_source_records=3,
            min_distinct_source_types=1,
            min_recent_source_records=1,
            required_report_sections=required_report_sections,
            required_source_record_fields=required_source_record_fields,
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
            min_source_records=8,
            min_distinct_source_types=2,
            min_recent_source_records=3,
            required_report_sections=required_report_sections,
            required_source_record_fields=required_source_record_fields,
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
            min_source_records=16,
            min_distinct_source_types=3,
            min_recent_source_records=6,
            required_report_sections=required_report_sections,
            required_source_record_fields=required_source_record_fields,
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


def research_report_section_specs(language: str = "en") -> list[dict[str, Any]]:
    """Return stable section ids with language-specific display titles."""

    language_key = _language_key(language)
    specs: list[dict[str, Any]] = []
    for item in _REPORT_SECTION_DEFINITIONS:
        localized_titles = item["localized_titles"]
        title = localized_titles.get(language_key, item["canonical_title"])
        aliases = _dedupe_strings(
            [
                item["canonical_title"],
                *localized_titles.values(),
                *item["aliases"],
            ]
        )
        specs.append(
            {
                "section_id": item["section_id"],
                "title": title,
                "canonical_title": item["canonical_title"],
                "aliases": aliases,
                "required": True,
                "purpose": item["purpose"],
            }
        )
    return specs


def research_report_section_titles(language: str = "en") -> list[str]:
    """Return the expected report headings for a language."""

    return [item["title"] for item in research_report_section_specs(language)]


def deepresearch_quality_dimensions() -> list[dict[str, str]]:
    """Return product-level DeepResearch quality dimensions for worker and judge prompts."""

    return [dict(item) for item in _QUALITY_DIMENSIONS]


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


def _language_key(language: str) -> str:
    value = str(language).strip().lower()
    return "zh" if value.startswith("zh") else "en"


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
