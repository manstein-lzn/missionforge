"""Product contracts for the thin academic DeepResearch integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

import missionforge as mf


RESEARCH_REQUEST_SCHEMA_VERSION = "missionforge_deepresearch.research_request.v1"

PROVIDER_POLICIES = {"default_no_key", "openalex_enhanced"}
CITATION_STYLES = {"cite_anchor_v1"}


_REPORT_SECTION_DEFINITIONS = [
    {
        "section_id": "abstract_and_key_findings",
        "canonical_title": "Abstract And Key Findings",
        "localized_titles": {"zh": "摘要与核心发现"},
        "aliases": ["Abstract", "Summary", "摘要", "核心发现", "核心结论"],
        "purpose": "Summarize the research question, scope, key findings, evidence confidence, and main limitations in a neutral tone.",
    },
    {
        "section_id": "scope_and_method",
        "canonical_title": "Scope And Method",
        "localized_titles": {"zh": "范围与方法"},
        "aliases": ["Scope & Method", "方法与范围", "研究范围", "研究方法"],
        "purpose": "Define the research question, time window, source strategy, inclusion criteria, evidence types, and limits of the run.",
    },
    {
        "section_id": "background_and_problem_definition",
        "canonical_title": "Background And Problem Definition",
        "localized_titles": {"zh": "研究背景与问题定义"},
        "aliases": ["Background", "Problem Definition", "背景", "问题定义"],
        "purpose": "Explain the field context, core definitions, problem boundaries, assumptions, and why the topic matters.",
    },
    {
        "section_id": "research_lines_and_representative_work",
        "canonical_title": "Research Lines And Representative Work",
        "localized_titles": {"zh": "研究路线与代表性工作"},
        "aliases": ["Major Lines Of Work", "Research Lines", "主要研究路线", "主要路线", "技术路线", "代表性工作"],
        "purpose": "Organize papers, systems, tools, and repositories by research line and explain the contribution and evidence for each line.",
    },
    {
        "section_id": "comparative_analysis",
        "canonical_title": "Comparative Analysis",
        "localized_titles": {"zh": "比较分析"},
        "aliases": ["Comparison Matrix", "Comparison Table", "对比矩阵", "对比表", "比较"],
        "purpose": "Compare methods by assumptions, techniques, benchmarks, evidence strength, reproducibility, applicability, and limitations.",
    },
    {
        "section_id": "limitations_counterevidence_and_open_questions",
        "canonical_title": "Limitations Counterevidence And Open Questions",
        "localized_titles": {"zh": "局限、反证与开放问题"},
        "aliases": ["Counterevidence", "Failure Modes", "Source Gaps", "Evidence Gaps", "Limitations", "反证", "失败模式", "证据缺口", "局限"],
        "purpose": "Surface negative evidence, weak claims, failed assumptions, unresolved questions, and gaps without turning caveats into the whole report.",
    },
    {
        "section_id": "trends_and_future_directions",
        "canonical_title": "Trends And Future Directions",
        "localized_titles": {"zh": "趋势与未来方向"},
        "aliases": ["Future Work", "Research Agenda", "趋势", "未来方向", "后续研究问题", "工程启示"],
        "purpose": "Synthesize likely research trends, practical implications, and follow-up questions while preserving evidence calibration.",
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
        "dimension_id": "insight_depth",
        "standard": (
            "Present non-obvious field insights that are supported by cross-source evidence "
            "and change how the reader understands the problem, not just what the sources say."
        ),
        "user_visible_value": "deeper expert insight",
    },
    {
        "dimension_id": "narrative_coherence",
        "standard": (
            "Organize the report around a defensible thesis and argument arc; sections should "
            "build on each other instead of reading like independent summary blocks."
        ),
        "user_visible_value": "stronger report storyline",
    },
    {
        "dimension_id": "genre_fit",
        "standard": (
            "Match the requested genre and audience: literature reviews should be neutral, "
            "comprehensive, and evidence-calibrated; strategic memos should be used only "
            "when explicitly requested."
        ),
        "user_visible_value": "better fit to requested report genre",
    },
    {
        "dimension_id": "reader_value",
        "standard": (
            "Every major conclusion should explain why it matters to the target audience and "
            "what decision, assumption, or follow-up work it informs."
        ),
        "user_visible_value": "more actionable conclusions",
    },
    {
        "dimension_id": "delta",
        "standard": "Keep run-to-run changes in research_delta.md and do not leak loop language into the reader report.",
        "user_visible_value": "cleaner reader-facing report boundaries",
    },
    {
        "dimension_id": "gaps_and_counterevidence",
        "standard": "Expose source gaps, weak evidence, counterevidence, and failure modes.",
        "user_visible_value": "less overclaiming",
    },
]


class ResearchIntensity(StrEnum):
    """User-facing research depth budget for DeepResearch runs."""

    STANDARD = "standard"
    INTENSIVE = "intensive"


@dataclass(frozen=True)
class ResearchIntensityProfile:
    """Mechanical budget and rubric preset derived from research intensity."""

    intensity: ResearchIntensity
    max_sources: int
    min_source_records: int
    max_review_rounds: int
    piworker_timeout_seconds: int
    piworker_reasoning: str
    min_final_report_chars: int
    guidance: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "intensity": self.intensity.value,
            "max_sources": self.max_sources,
            "min_source_records": self.min_source_records,
            "max_review_rounds": self.max_review_rounds,
            "piworker_timeout_seconds": self.piworker_timeout_seconds,
            "piworker_reasoning": self.piworker_reasoning,
            "min_final_report_chars": self.min_final_report_chars,
            "guidance": self.guidance,
        }


def research_intensity_profile(value: ResearchIntensity | str) -> ResearchIntensityProfile:
    """Return the product-layer budget preset for a research intensity."""

    intensity = mf.require_enum(value, ResearchIntensity, "research_intensity")
    profiles = {
        ResearchIntensity.STANDARD: ResearchIntensityProfile(
            intensity=ResearchIntensity.STANDARD,
            max_sources=24,
            min_source_records=8,
            max_review_rounds=2,
            piworker_timeout_seconds=900,
            piworker_reasoning="medium",
            min_final_report_chars=4500,
            guidance=(
                "Produce a serious web, paper, and repository-metadata survey. "
                "Use public pages, papers, docs, release notes, and repository "
                "metadata to build a useful synthesis, taxonomy, comparison, "
                "limitations, and citations. Do not claim code-level audit "
                "unless repository files were actually inspected."
            ),
        ),
        ResearchIntensity.INTENSIVE: ResearchIntensityProfile(
            intensity=ResearchIntensity.INTENSIVE,
            max_sources=64,
            min_source_records=24,
            max_review_rounds=4,
            piworker_timeout_seconds=1800,
            piworker_reasoning="high",
            min_final_report_chars=25000,
            guidance=(
                "Produce a repository/code-audit-backed technical report when "
                "the topic involves software systems. Inspect repository files "
                "such as README, docs, examples, tests, configs, source layout, "
                "and entrypoints when tools permit. Classify claims by evidence "
                "type, surface competing evidence, and make gaps explicit. Do "
                "not install projects, run benchmarks, execute untrusted code, "
                "or treat experimental execution as required."
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
class SeedPaper:
    """Optional seed paper locator supplied by the user."""

    kind: str
    value: str
    note: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SeedPaper":
        data = _strict_mapping(payload, "seed_paper", {"kind", "value", "note"})
        seed = cls(
            kind=mf.require_non_empty_str(data.get("kind"), "seed_paper.kind"),
            value=mf.require_non_empty_str(data.get("value"), "seed_paper.value"),
            note=str(data.get("note", "") or "").strip(),
        )
        seed.validate()
        return seed

    def validate(self) -> None:
        kind = mf.require_non_empty_str(self.kind, "seed_paper.kind")
        if kind not in {"title", "doi", "arxiv", "url"}:
            raise mf.ContractValidationError("seed_paper.kind must be title, doi, arxiv, or url")
        value = mf.require_non_empty_str(self.value, "seed_paper.value")
        if kind == "url" and not value.startswith(("http://", "https://")):
            raise mf.ContractValidationError("seed_paper.url value must start with http:// or https://")
        if kind == "doi" and not value.lower().startswith("10."):
            raise mf.ContractValidationError("seed_paper.doi value must start with 10.")

    def to_dict(self) -> dict[str, str]:
        self.validate()
        return {
            "kind": self.kind,
            "value": self.value,
            "note": self.note,
        }


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
    seed_papers: list[SeedPaper] = field(default_factory=list)
    seed_pdf_refs: list[str] = field(default_factory=list)
    sample_report_ref: str | None = None
    target_source_count: int | None = None
    provider_policy: str = "default_no_key"
    requested_provider_families: list[str] = field(default_factory=list)
    optional_provider_families: list[str] = field(default_factory=list)
    citation_style: str = "cite_anchor_v1"
    report_template_id: str = "academic_literature_review.zh"
    schema_version: str = RESEARCH_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "research_intensity",
            mf.require_enum(
                self.research_intensity,
                ResearchIntensity,
                "academic_research_request.research_intensity",
            ),
        )
        object.__setattr__(self, "seed_papers", [_coerce_seed_paper(item) for item in self.seed_papers])

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
                "seed_papers",
                "seed_pdf_refs",
                "sample_report_ref",
                "target_source_count",
                "provider_policy",
                "requested_provider_families",
                "optional_provider_families",
                "citation_style",
                "report_template_id",
            },
        )
        request = cls(
            schema_version=mf.require_non_empty_str(
                data.get("schema_version", RESEARCH_REQUEST_SCHEMA_VERSION),
                "academic_research_request.schema_version",
            ),
            request_id=mf.require_non_empty_str(data.get("request_id"), "academic_research_request.request_id"),
            topic=mf.require_non_empty_str(data.get("topic"), "academic_research_request.topic"),
            audience=mf.require_non_empty_str(data.get("audience", "R&D team"), "academic_research_request.audience"),
            language=mf.require_non_empty_str(data.get("language", "zh"), "academic_research_request.language"),
            research_intensity=mf.require_enum(
                data.get("research_intensity", ResearchIntensity.STANDARD.value),
                ResearchIntensity,
                "academic_research_request.research_intensity",
            ),
            previous_run_refs=_ref_list(
                data.get("previous_run_refs", []),
                "academic_research_request.previous_run_refs",
            ),
            constraints=mf.require_str_list(data.get("constraints", []), "academic_research_request.constraints"),
            non_goals=mf.require_str_list(data.get("non_goals", []), "academic_research_request.non_goals"),
            seed_papers=_seed_paper_list(data.get("seed_papers", []), "academic_research_request.seed_papers"),
            seed_pdf_refs=_ref_list(data.get("seed_pdf_refs", []), "academic_research_request.seed_pdf_refs"),
            sample_report_ref=_optional_ref(data.get("sample_report_ref"), "academic_research_request.sample_report_ref"),
            target_source_count=_optional_positive_int(
                data.get("target_source_count"),
                "academic_research_request.target_source_count",
            ),
            provider_policy=mf.require_non_empty_str(
                data.get("provider_policy", "default_no_key"),
                "academic_research_request.provider_policy",
            ),
            requested_provider_families=mf.require_str_list(
                data.get("requested_provider_families", []),
                "academic_research_request.requested_provider_families",
            ),
            optional_provider_families=mf.require_str_list(
                data.get("optional_provider_families", []),
                "academic_research_request.optional_provider_families",
            ),
            citation_style=mf.require_non_empty_str(
                data.get("citation_style", "cite_anchor_v1"),
                "academic_research_request.citation_style",
            ),
            report_template_id=mf.require_non_empty_str(
                data.get("report_template_id", "academic_literature_review.zh"),
                "academic_research_request.report_template_id",
            ),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if self.schema_version != RESEARCH_REQUEST_SCHEMA_VERSION:
            raise mf.ContractValidationError("academic_research_request.schema_version is unsupported")
        mf.require_non_empty_str(self.request_id, "academic_research_request.request_id")
        _validate_request_id(self.request_id)
        mf.require_non_empty_str(self.topic, "academic_research_request.topic")
        mf.require_non_empty_str(self.audience, "academic_research_request.audience")
        mf.require_non_empty_str(self.language, "academic_research_request.language")
        mf.require_enum(
            self.research_intensity,
            ResearchIntensity,
            "academic_research_request.research_intensity",
        )
        _validate_unique_refs(self.previous_run_refs, "academic_research_request.previous_run_refs")
        mf.require_str_list(self.constraints, "academic_research_request.constraints")
        mf.require_str_list(self.non_goals, "academic_research_request.non_goals")
        _validate_seed_papers(self.seed_papers, "academic_research_request.seed_papers")
        _validate_unique_refs(self.seed_pdf_refs, "academic_research_request.seed_pdf_refs")
        _optional_ref(self.sample_report_ref, "academic_research_request.sample_report_ref")
        _optional_positive_int(self.target_source_count, "academic_research_request.target_source_count")
        if self.provider_policy not in PROVIDER_POLICIES:
            raise mf.ContractValidationError("academic_research_request.provider_policy is unsupported")
        mf.require_str_list(
            self.requested_provider_families,
            "academic_research_request.requested_provider_families",
        )
        mf.require_str_list(
            self.optional_provider_families,
            "academic_research_request.optional_provider_families",
        )
        if self.citation_style not in CITATION_STYLES:
            raise mf.ContractValidationError("academic_research_request.citation_style is unsupported")
        mf.require_non_empty_str(self.report_template_id, "academic_research_request.report_template_id")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "topic": self.topic,
            "audience": self.audience,
            "language": self.language,
            "research_intensity": mf.require_enum(
                self.research_intensity,
                ResearchIntensity,
                "academic_research_request.research_intensity",
            ).value,
            "previous_run_refs": list(self.previous_run_refs),
            "constraints": list(self.constraints),
            "non_goals": list(self.non_goals),
            "seed_papers": [item.to_dict() for item in self.seed_papers],
            "seed_pdf_refs": list(self.seed_pdf_refs),
            "sample_report_ref": self.sample_report_ref,
            "target_source_count": self.target_source_count,
            "provider_policy": self.provider_policy,
            "requested_provider_families": list(self.requested_provider_families),
            "optional_provider_families": list(self.optional_provider_families),
            "citation_style": self.citation_style,
            "report_template_id": self.report_template_id,
        }


def _strict_mapping(payload: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = mf.require_mapping(payload, field_name)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise mf.ContractValidationError(f"{field_name} contains unknown fields: {unknown}")
    return data


def _validate_request_id(request_id: str) -> None:
    mf.validate_ref(f"runs/{request_id}", "academic_research_request.request_id")
    if "/" in request_id:
        raise mf.ContractValidationError("academic_research_request.request_id must be one ref segment")


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [mf.validate_ref(item, f"{field_name}[]") for item in mf.require_str_list(value, field_name)]


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return mf.validate_ref(value, field_name)


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise mf.ContractValidationError(f"{field_name} must not contain duplicate refs")


def _coerce_seed_paper(value: Any) -> SeedPaper:
    if isinstance(value, SeedPaper):
        return value
    if isinstance(value, Mapping):
        return SeedPaper.from_dict(value)
    raise mf.ContractValidationError("seed_paper must be an object")


def _seed_paper_list(value: Any, field_name: str) -> list[SeedPaper]:
    items = _require_list(value, field_name)
    return [_coerce_seed_paper(item) for item in items]


def _validate_seed_papers(values: list[SeedPaper], field_name: str) -> None:
    seen: set[tuple[str, str]] = set()
    for item in values:
        item.validate()
        key = (item.kind, item.value.lower())
        if key in seen:
            raise mf.ContractValidationError(f"{field_name} must not contain duplicate seeds")
        seen.add(key)


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise mf.ContractValidationError(f"{field_name} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise mf.ContractValidationError(f"{field_name} must be a positive integer") from None
    if number <= 0:
        raise mf.ContractValidationError(f"{field_name} must be positive")
    return number


def _require_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise mf.ContractValidationError(f"{field_name} must be a list")
    return value


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
