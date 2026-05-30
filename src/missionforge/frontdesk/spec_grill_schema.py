"""Spec-grill FrontDesk artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable, Mapping, TypeVar

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_confidence,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from .schema import ApprovalAuthority, reject_raw_authoring_fields


WORKSPACE_FACTS_SCHEMA_VERSION = "missionforge.frontdesk_workspace_facts.v1"
PROFILE_CATALOG_SNAPSHOT_SCHEMA_VERSION = "missionforge.frontdesk_profile_catalog_snapshot.v1"
DOMAIN_LANGUAGE_SCHEMA_VERSION = "missionforge.frontdesk_domain_language.v1"
SOURCE_ADMISSION_REPORT_SCHEMA_VERSION = "missionforge.frontdesk_source_admission_report.v1"
DECISION_TREE_SCHEMA_VERSION = "missionforge.frontdesk_decision_tree.v1"
CORE_NEED_BRIEF_SCHEMA_VERSION = "missionforge.frontdesk_core_need_brief.v1"
NEED_GRILLING_REPORT_SCHEMA_VERSION = "missionforge.frontdesk_need_grilling_report.v1"
SEMANTIC_COVERAGE_SCHEMA_VERSION = "missionforge.frontdesk_semantic_coverage.v1"
SOLUTION_PLAN_SCHEMA_VERSION = "missionforge.frontdesk_solution_plan.v1"
PLAN_RISK_REGISTER_SCHEMA_VERSION = "missionforge.frontdesk_plan_risk_register.v1"
PLAN_REVIEW_SCHEMA_VERSION = "missionforge.frontdesk_plan_review.v1"
MISSION_MAPPING_REPORT_SCHEMA_VERSION = "missionforge.frontdesk_mission_mapping_report.v1"
FREEZE_GATE_RESULT_SCHEMA_VERSION = "missionforge.frontdesk_freeze_gate_result.v1"


class FactConfidence(StrEnum):
    """Confidence source for a workspace fact."""

    OBSERVED = "observed"
    INFERRED = "inferred"
    ASSUMED = "assumed"


class DecisionStatus(StrEnum):
    """Spec-grill decision state."""

    OPEN = "open"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class QuestionAnswerType(StrEnum):
    """Expected answer shape for a grilling question."""

    CHOICE_OR_FREE_TEXT = "choice_or_free_text"
    RANKED_CHOICES_OR_FREE_TEXT = "ranked_choices_or_free_text"
    FREE_TEXT = "free_text"
    ENUM = "enum"
    BOOLEAN = "boolean"
    NUMBER = "number"
    FILE = "file"
    EXAMPLE = "example"


class NeedGrillingReadiness(StrEnum):
    """Readiness route produced by NeedGriller."""

    NEEDS_CLARIFICATION = "needs_clarification"
    CORE_NEED_READY = "core_need_ready"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    FAILED_CLOSED = "failed_closed"


class SemanticCoverageStatus(StrEnum):
    """Overall semantic coverage status."""

    PASSED = "passed"
    FAILED = "failed"


class SemanticCoverageItemStatus(StrEnum):
    """Coverage status for one source signal."""

    COVERED = "covered"
    UNMAPPED = "unmapped"
    REJECTED = "rejected"


class SolutionPlanStatus(StrEnum):
    """Solution plan lifecycle status."""

    DRAFT = "draft"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"


class PlanReviewDecision(StrEnum):
    """Plan review decision."""

    APPROVE = "approve"
    REQUEST_REVISION = "request_revision"
    REJECT = "reject"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class MappingStatus(StrEnum):
    """Requirement mapping status."""

    MAPPED = "mapped"
    DROPPED = "dropped"
    UNMAPPED = "unmapped"
    ROUTED = "routed"


class MissionAuditRoute(StrEnum):
    """Spec-grill audit route."""

    APPROVE = "approve"
    NEEDS_CLARIFICATION = "needs_clarification"
    PROFILE_EXTENSION = "profile_extension"
    VALIDATOR_EXTENSION = "validator_extension"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    UNSUPPORTED = "unsupported"
    FAILED_CLOSED = "failed_closed"


class FreezeGateDecision(StrEnum):
    """Deterministic freeze gate decision."""

    FREEZE = "freeze"
    NEEDS_CLARIFICATION = "needs_clarification"
    PROFILE_EXTENSION = "profile_extension"
    VALIDATOR_EXTENSION = "validator_extension"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    UNSUPPORTED = "unsupported"
    FAILED_CLOSED = "failed_closed"


T = TypeVar("T")


@dataclass(frozen=True)
class WorkspaceFact:
    """One discovered workspace/profile fact."""

    fact_id: str
    summary: str
    source_refs: list[str] = field(default_factory=list)
    confidence: FactConfidence = FactConfidence.OBSERVED
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkspaceFact":
        data = _strict_mapping(payload, "workspace_fact", {"fact_id", "summary", "source_refs", "confidence", "metadata"})
        item = cls(
            fact_id=require_non_empty_str(data.get("fact_id"), "workspace_fact.fact_id"),
            summary=require_non_empty_str(data.get("summary"), "workspace_fact.summary"),
            source_refs=require_str_list(data.get("source_refs", []), "workspace_fact.source_refs"),
            confidence=require_enum(data.get("confidence", FactConfidence.OBSERVED.value), FactConfidence, "workspace_fact.confidence"),
            metadata=require_mapping(data.get("metadata", {}), "workspace_fact.metadata"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.fact_id, "workspace_fact.fact_id")
        require_non_empty_str(self.summary, "workspace_fact.summary")
        _validate_ref_list(self.source_refs, "workspace_fact.source_refs")
        require_enum(self.confidence, FactConfidence, "workspace_fact.confidence")
        _safe_payload(self.metadata, "workspace_fact.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "fact_id": self.fact_id,
            "summary": self.summary,
            "source_refs": list(self.source_refs),
            "confidence": self.confidence.value,
            "metadata": ensure_json_value(self.metadata, "workspace_fact.metadata"),
        }


@dataclass(frozen=True)
class WorkspaceFacts:
    """Facts discovered before asking the user more questions."""

    session_id: str
    facts: list[WorkspaceFact] = field(default_factory=list)
    questions_answered_by_workspace: list[str] = field(default_factory=list)
    unsafe_or_excluded_refs: list[str] = field(default_factory=list)
    schema_version: str = WORKSPACE_FACTS_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkspaceFacts":
        data = _strict_mapping(
            payload,
            "workspace_facts",
            {"schema_version", "session_id", "facts", "questions_answered_by_workspace", "unsafe_or_excluded_refs"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "workspace_facts.session_id"),
            facts=_item_list(data.get("facts", []), "workspace_facts.facts", WorkspaceFact.from_dict),
            questions_answered_by_workspace=require_str_list(
                data.get("questions_answered_by_workspace", []),
                "workspace_facts.questions_answered_by_workspace",
            ),
            unsafe_or_excluded_refs=require_str_list(
                data.get("unsafe_or_excluded_refs", []),
                "workspace_facts.unsafe_or_excluded_refs",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", WORKSPACE_FACTS_SCHEMA_VERSION),
                "workspace_facts.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, WORKSPACE_FACTS_SCHEMA_VERSION, "workspace_facts.schema_version")
        require_non_empty_str(self.session_id, "workspace_facts.session_id")
        _require_unique([fact.fact_id for fact in self.facts], "workspace_facts.facts.fact_id")
        for fact in self.facts:
            fact.validate()
        require_str_list(self.questions_answered_by_workspace, "workspace_facts.questions_answered_by_workspace")
        require_str_list(self.unsafe_or_excluded_refs, "workspace_facts.unsafe_or_excluded_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "workspace_facts")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "facts": [fact.to_dict() for fact in self.facts],
            "questions_answered_by_workspace": list(self.questions_answered_by_workspace),
            "unsafe_or_excluded_refs": list(self.unsafe_or_excluded_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class ProfileCatalogSnapshot:
    """Profile ids visible to FrontDesk at authoring time."""

    session_id: str
    capability_profile_ids: list[str] = field(default_factory=list)
    verification_profile_ids: list[str] = field(default_factory=list)
    profile_pack_refs: list[str] = field(default_factory=list)
    schema_version: str = PROFILE_CATALOG_SNAPSHOT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProfileCatalogSnapshot":
        data = _strict_mapping(
            payload,
            "profile_catalog_snapshot",
            {"schema_version", "session_id", "capability_profile_ids", "verification_profile_ids", "profile_pack_refs"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "profile_catalog_snapshot.session_id"),
            capability_profile_ids=require_str_list(
                data.get("capability_profile_ids", []),
                "profile_catalog_snapshot.capability_profile_ids",
            ),
            verification_profile_ids=require_str_list(
                data.get("verification_profile_ids", []),
                "profile_catalog_snapshot.verification_profile_ids",
            ),
            profile_pack_refs=require_str_list(data.get("profile_pack_refs", []), "profile_catalog_snapshot.profile_pack_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PROFILE_CATALOG_SNAPSHOT_SCHEMA_VERSION),
                "profile_catalog_snapshot.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            PROFILE_CATALOG_SNAPSHOT_SCHEMA_VERSION,
            "profile_catalog_snapshot.schema_version",
        )
        require_non_empty_str(self.session_id, "profile_catalog_snapshot.session_id")
        require_str_list(self.capability_profile_ids, "profile_catalog_snapshot.capability_profile_ids")
        require_str_list(self.verification_profile_ids, "profile_catalog_snapshot.verification_profile_ids")
        _validate_ref_list(self.profile_pack_refs, "profile_catalog_snapshot.profile_pack_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "profile_catalog_snapshot")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "capability_profile_ids": list(self.capability_profile_ids),
            "verification_profile_ids": list(self.verification_profile_ids),
            "profile_pack_refs": list(self.profile_pack_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class DomainLanguage:
    """Terms preserved from source/user language for later mapping."""

    session_id: str
    terms: list[str] = field(default_factory=list)
    implementation_terms: list[str] = field(default_factory=list)
    risk_terms: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    schema_version: str = DOMAIN_LANGUAGE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DomainLanguage":
        data = _strict_mapping(
            payload,
            "domain_language",
            {"schema_version", "session_id", "terms", "implementation_terms", "risk_terms", "source_refs"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "domain_language.session_id"),
            terms=require_str_list(data.get("terms", []), "domain_language.terms"),
            implementation_terms=require_str_list(
                data.get("implementation_terms", []),
                "domain_language.implementation_terms",
            ),
            risk_terms=require_str_list(data.get("risk_terms", []), "domain_language.risk_terms"),
            source_refs=require_str_list(data.get("source_refs", []), "domain_language.source_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", DOMAIN_LANGUAGE_SCHEMA_VERSION),
                "domain_language.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, DOMAIN_LANGUAGE_SCHEMA_VERSION, "domain_language.schema_version")
        require_non_empty_str(self.session_id, "domain_language.session_id")
        require_str_list(self.terms, "domain_language.terms")
        require_str_list(self.implementation_terms, "domain_language.implementation_terms")
        require_str_list(self.risk_terms, "domain_language.risk_terms")
        _validate_ref_list(self.source_refs, "domain_language.source_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "domain_language")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "terms": list(self.terms),
            "implementation_terms": list(self.implementation_terms),
            "risk_terms": list(self.risk_terms),
            "source_refs": list(self.source_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class SourceAdmissionReport:
    """Source admission and exclusion summary."""

    session_id: str
    admitted_source_refs: list[str] = field(default_factory=list)
    excluded_source_refs: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    schema_version: str = SOURCE_ADMISSION_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceAdmissionReport":
        data = _strict_mapping(
            payload,
            "source_admission_report",
            {"schema_version", "session_id", "admitted_source_refs", "excluded_source_refs", "reasons"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "source_admission_report.session_id"),
            admitted_source_refs=require_str_list(
                data.get("admitted_source_refs", []),
                "source_admission_report.admitted_source_refs",
            ),
            excluded_source_refs=require_str_list(
                data.get("excluded_source_refs", []),
                "source_admission_report.excluded_source_refs",
            ),
            reasons=require_str_list(data.get("reasons", []), "source_admission_report.reasons"),
            schema_version=require_non_empty_str(
                data.get("schema_version", SOURCE_ADMISSION_REPORT_SCHEMA_VERSION),
                "source_admission_report.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            SOURCE_ADMISSION_REPORT_SCHEMA_VERSION,
            "source_admission_report.schema_version",
        )
        require_non_empty_str(self.session_id, "source_admission_report.session_id")
        _validate_ref_list(self.admitted_source_refs, "source_admission_report.admitted_source_refs")
        _validate_ref_list(self.excluded_source_refs, "source_admission_report.excluded_source_refs")
        require_str_list(self.reasons, "source_admission_report.reasons")
        assert_refs_only_payload(self.to_dict_without_validation(), "source_admission_report")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "admitted_source_refs": list(self.admitted_source_refs),
            "excluded_source_refs": list(self.excluded_source_refs),
            "reasons": list(self.reasons),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class DecisionOption:
    """One possible answer/direction in a decision node."""

    option_id: str
    summary: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionOption":
        data = _strict_mapping(payload, "decision_option", {"option_id", "summary"})
        item = cls(
            option_id=require_non_empty_str(data.get("option_id"), "decision_option.option_id"),
            summary=require_non_empty_str(data.get("summary"), "decision_option.summary"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.option_id, "decision_option.option_id")
        require_non_empty_str(self.summary, "decision_option.summary")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"option_id": self.option_id, "summary": self.summary}


@dataclass(frozen=True)
class DecisionNode:
    """One decision NeedGriller is trying to resolve."""

    decision_id: str
    topic: str
    status: DecisionStatus
    current_hypothesis: str
    options: list[DecisionOption] = field(default_factory=list)
    blocking: bool = True
    source_refs: list[str] = field(default_factory=list)
    chosen_option_id: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionNode":
        data = _strict_mapping(
            payload,
            "decision_node",
            {"decision_id", "topic", "status", "current_hypothesis", "options", "blocking", "source_refs", "chosen_option_id"},
        )
        item = cls(
            decision_id=require_non_empty_str(data.get("decision_id"), "decision_node.decision_id"),
            topic=require_non_empty_str(data.get("topic"), "decision_node.topic"),
            status=require_enum(data.get("status"), DecisionStatus, "decision_node.status"),
            current_hypothesis=require_non_empty_str(data.get("current_hypothesis"), "decision_node.current_hypothesis"),
            options=_item_list(data.get("options", []), "decision_node.options", DecisionOption.from_dict),
            blocking=_require_bool(data.get("blocking", True), "decision_node.blocking"),
            source_refs=require_str_list(data.get("source_refs", []), "decision_node.source_refs"),
            chosen_option_id=str(data.get("chosen_option_id", "")),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.decision_id, "decision_node.decision_id")
        require_non_empty_str(self.topic, "decision_node.topic")
        require_enum(self.status, DecisionStatus, "decision_node.status")
        require_non_empty_str(self.current_hypothesis, "decision_node.current_hypothesis")
        _require_unique([option.option_id for option in self.options], "decision_node.options.option_id")
        for option in self.options:
            option.validate()
        if not isinstance(self.blocking, bool):
            raise ContractValidationError("decision_node.blocking must be a boolean")
        _validate_ref_list(self.source_refs, "decision_node.source_refs")
        if self.chosen_option_id:
            require_non_empty_str(self.chosen_option_id, "decision_node.chosen_option_id")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "decision_id": self.decision_id,
            "topic": self.topic,
            "status": self.status.value,
            "current_hypothesis": self.current_hypothesis,
            "options": [option.to_dict() for option in self.options],
            "blocking": self.blocking,
            "source_refs": list(self.source_refs),
            "chosen_option_id": self.chosen_option_id,
        }


@dataclass(frozen=True)
class DecisionTree:
    """NeedGriller decision tree."""

    session_id: str
    decisions: list[DecisionNode] = field(default_factory=list)
    schema_version: str = DECISION_TREE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionTree":
        data = _strict_mapping(payload, "decision_tree", {"schema_version", "session_id", "decisions"})
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "decision_tree.session_id"),
            decisions=_item_list(data.get("decisions", []), "decision_tree.decisions", DecisionNode.from_dict),
            schema_version=require_non_empty_str(
                data.get("schema_version", DECISION_TREE_SCHEMA_VERSION),
                "decision_tree.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, DECISION_TREE_SCHEMA_VERSION, "decision_tree.schema_version")
        require_non_empty_str(self.session_id, "decision_tree.session_id")
        _require_unique([decision.decision_id for decision in self.decisions], "decision_tree.decisions.decision_id")
        for decision in self.decisions:
            decision.validate()
        assert_refs_only_payload(self.to_dict_without_validation(), "decision_tree")

    @property
    def open_blocking_decision_ids(self) -> list[str]:
        return [
            decision.decision_id
            for decision in self.decisions
            if decision.blocking and decision.status == DecisionStatus.OPEN
        ]

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "decisions": [decision.to_dict() for decision in self.decisions],
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class CoreNeedOpenQuestion:
    """Non-blocking refinement question carried by a ready core need brief."""

    question_id: str
    question: str
    impact: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoreNeedOpenQuestion":
        data = _strict_mapping(payload, "core_need_open_question", {"question_id", "question", "impact"})
        item = cls(
            question_id=require_non_empty_str(data.get("question_id"), "core_need_open_question.question_id"),
            question=require_non_empty_str(data.get("question"), "core_need_open_question.question"),
            impact=str(data.get("impact", "")),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.question_id, "core_need_open_question.question_id")
        require_non_empty_str(self.question, "core_need_open_question.question")
        assert_refs_only_payload(self.to_dict(), "core_need_open_question")

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "impact": self.impact,
        }


@dataclass(frozen=True)
class CoreNeedBrief:
    """Structured summary of the true user need."""

    session_id: str
    core_pain: str
    target_users: list[str]
    usage_moment: str
    deliverable_type: str
    desired_outcome: str
    success_signals: list[str]
    constraints: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[CoreNeedOpenQuestion] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    schema_version: str = CORE_NEED_BRIEF_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoreNeedBrief":
        data = _strict_mapping(
            payload,
            "core_need_brief",
            {
                "schema_version",
                "session_id",
                "core_pain",
                "target_users",
                "usage_moment",
                "deliverable_type",
                "desired_outcome",
                "success_signals",
                "constraints",
                "non_goals",
                "assumptions",
                "open_questions",
                "source_refs",
            },
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "core_need_brief.session_id"),
            core_pain=require_non_empty_str(data.get("core_pain"), "core_need_brief.core_pain"),
            target_users=require_str_list(data.get("target_users"), "core_need_brief.target_users"),
            usage_moment=require_non_empty_str(data.get("usage_moment"), "core_need_brief.usage_moment"),
            deliverable_type=require_non_empty_str(data.get("deliverable_type"), "core_need_brief.deliverable_type"),
            desired_outcome=require_non_empty_str(data.get("desired_outcome"), "core_need_brief.desired_outcome"),
            success_signals=require_str_list(data.get("success_signals"), "core_need_brief.success_signals"),
            constraints=require_str_list(data.get("constraints", []), "core_need_brief.constraints"),
            non_goals=require_str_list(data.get("non_goals", []), "core_need_brief.non_goals"),
            assumptions=require_str_list(data.get("assumptions", []), "core_need_brief.assumptions"),
            open_questions=_item_list(
                data.get("open_questions", []),
                "core_need_brief.open_questions",
                CoreNeedOpenQuestion.from_dict,
            ),
            source_refs=require_str_list(data.get("source_refs", []), "core_need_brief.source_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CORE_NEED_BRIEF_SCHEMA_VERSION),
                "core_need_brief.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, CORE_NEED_BRIEF_SCHEMA_VERSION, "core_need_brief.schema_version")
        require_non_empty_str(self.session_id, "core_need_brief.session_id")
        require_non_empty_str(self.core_pain, "core_need_brief.core_pain")
        require_str_list(self.target_users, "core_need_brief.target_users")
        require_non_empty_str(self.usage_moment, "core_need_brief.usage_moment")
        require_non_empty_str(self.deliverable_type, "core_need_brief.deliverable_type")
        require_non_empty_str(self.desired_outcome, "core_need_brief.desired_outcome")
        require_str_list(self.success_signals, "core_need_brief.success_signals")
        require_str_list(self.constraints, "core_need_brief.constraints")
        require_str_list(self.non_goals, "core_need_brief.non_goals")
        require_str_list(self.assumptions, "core_need_brief.assumptions")
        for question in self.open_questions:
            question.validate()
        _validate_ref_list(self.source_refs, "core_need_brief.source_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "core_need_brief")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "core_pain": self.core_pain,
            "target_users": list(self.target_users),
            "usage_moment": self.usage_moment,
            "deliverable_type": self.deliverable_type,
            "desired_outcome": self.desired_outcome,
            "success_signals": list(self.success_signals),
            "constraints": list(self.constraints),
            "non_goals": list(self.non_goals),
            "assumptions": list(self.assumptions),
            "open_questions": [question.to_dict() for question in self.open_questions],
            "source_refs": list(self.source_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class GrillingQuestion:
    """One high-value active clarification question."""

    question_id: str
    inference: str
    recommended_answer: str
    question: str
    why_this_matters: str
    blocks_freeze: bool = True
    expected_answer_type: QuestionAnswerType = QuestionAnswerType.CHOICE_OR_FREE_TEXT
    related_decision_ids: list[str] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GrillingQuestion":
        data = _strict_mapping(
            payload,
            "grilling_question",
            {
                "question_id",
                "inference",
                "recommended_answer",
                "question",
                "why_this_matters",
                "blocks_freeze",
                "expected_answer_type",
                "related_decision_ids",
                "choices",
            },
        )
        item = cls(
            question_id=require_non_empty_str(data.get("question_id"), "grilling_question.question_id"),
            inference=require_non_empty_str(data.get("inference"), "grilling_question.inference"),
            recommended_answer=require_non_empty_str(data.get("recommended_answer"), "grilling_question.recommended_answer"),
            question=require_non_empty_str(data.get("question"), "grilling_question.question"),
            why_this_matters=require_non_empty_str(data.get("why_this_matters"), "grilling_question.why_this_matters"),
            blocks_freeze=_require_bool(data.get("blocks_freeze", True), "grilling_question.blocks_freeze"),
            expected_answer_type=require_enum(
                data.get("expected_answer_type", QuestionAnswerType.CHOICE_OR_FREE_TEXT.value),
                QuestionAnswerType,
                "grilling_question.expected_answer_type",
            ),
            related_decision_ids=require_str_list(
                data.get("related_decision_ids", []),
                "grilling_question.related_decision_ids",
            ),
            choices=require_str_list(data.get("choices", []), "grilling_question.choices"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.question_id, "grilling_question.question_id")
        require_non_empty_str(self.inference, "grilling_question.inference")
        require_non_empty_str(self.recommended_answer, "grilling_question.recommended_answer")
        question = require_non_empty_str(self.question, "grilling_question.question")
        if "provide more detail" in question.lower() or "provide more details" in question.lower():
            raise ContractValidationError("grilling_question.question must be targeted, not a broad detail request")
        require_non_empty_str(self.why_this_matters, "grilling_question.why_this_matters")
        if not isinstance(self.blocks_freeze, bool):
            raise ContractValidationError("grilling_question.blocks_freeze must be a boolean")
        require_enum(self.expected_answer_type, QuestionAnswerType, "grilling_question.expected_answer_type")
        require_str_list(self.related_decision_ids, "grilling_question.related_decision_ids")
        require_str_list(self.choices, "grilling_question.choices")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "question_id": self.question_id,
            "inference": self.inference,
            "recommended_answer": self.recommended_answer,
            "question": self.question,
            "why_this_matters": self.why_this_matters,
            "blocks_freeze": self.blocks_freeze,
            "expected_answer_type": self.expected_answer_type.value,
            "related_decision_ids": list(self.related_decision_ids),
            "choices": list(self.choices),
        }


@dataclass(frozen=True)
class NeedGrillingReport:
    """Validated NeedGriller output."""

    session_id: str
    readiness: NeedGrillingReadiness
    observations: list[str] = field(default_factory=list)
    inferences: list[str] = field(default_factory=list)
    confirmed_requirements: list[str] = field(default_factory=list)
    open_decision_ids: list[str] = field(default_factory=list)
    next_question: GrillingQuestion | None = None
    decision_tree_ref: str = "frontdesk/decision_tree.json"
    core_need_brief_ref: str = ""
    schema_version: str = NEED_GRILLING_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NeedGrillingReport":
        data = _strict_mapping(
            payload,
            "need_grilling_report",
            {
                "schema_version",
                "session_id",
                "readiness",
                "observations",
                "inferences",
                "confirmed_requirements",
                "open_decision_ids",
                "next_question",
                "decision_tree_ref",
                "core_need_brief_ref",
            },
        )
        raw_question = data.get("next_question")
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "need_grilling_report.session_id"),
            readiness=require_enum(data.get("readiness"), NeedGrillingReadiness, "need_grilling_report.readiness"),
            observations=require_str_list(data.get("observations", []), "need_grilling_report.observations"),
            inferences=require_str_list(data.get("inferences", []), "need_grilling_report.inferences"),
            confirmed_requirements=require_str_list(
                data.get("confirmed_requirements", []),
                "need_grilling_report.confirmed_requirements",
            ),
            open_decision_ids=require_str_list(data.get("open_decision_ids", []), "need_grilling_report.open_decision_ids"),
            next_question=GrillingQuestion.from_dict(require_mapping(raw_question, "need_grilling_report.next_question"))
            if raw_question is not None
            else None,
            decision_tree_ref=validate_ref(
                data.get("decision_tree_ref", "frontdesk/decision_tree.json"),
                "need_grilling_report.decision_tree_ref",
            ),
            core_need_brief_ref=str(data.get("core_need_brief_ref", "")),
            schema_version=require_non_empty_str(
                data.get("schema_version", NEED_GRILLING_REPORT_SCHEMA_VERSION),
                "need_grilling_report.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, NEED_GRILLING_REPORT_SCHEMA_VERSION, "need_grilling_report.schema_version")
        require_non_empty_str(self.session_id, "need_grilling_report.session_id")
        require_enum(self.readiness, NeedGrillingReadiness, "need_grilling_report.readiness")
        require_str_list(self.observations, "need_grilling_report.observations")
        require_str_list(self.inferences, "need_grilling_report.inferences")
        require_str_list(self.confirmed_requirements, "need_grilling_report.confirmed_requirements")
        require_str_list(self.open_decision_ids, "need_grilling_report.open_decision_ids")
        validate_ref(self.decision_tree_ref, "need_grilling_report.decision_tree_ref")
        if self.core_need_brief_ref:
            validate_ref(self.core_need_brief_ref, "need_grilling_report.core_need_brief_ref")
        if self.next_question is not None:
            self.next_question.validate()
        if self.readiness == NeedGrillingReadiness.NEEDS_CLARIFICATION and self.next_question is None:
            raise ContractValidationError("need_grilling_report requires next_question when clarity is insufficient")
        if self.readiness == NeedGrillingReadiness.CORE_NEED_READY and not self.core_need_brief_ref:
            raise ContractValidationError("need_grilling_report requires core_need_brief_ref when core need is ready")
        assert_refs_only_payload(self.to_dict_without_validation(), "need_grilling_report")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "readiness": self.readiness.value,
            "observations": list(self.observations),
            "inferences": list(self.inferences),
            "confirmed_requirements": list(self.confirmed_requirements),
            "open_decision_ids": list(self.open_decision_ids),
            "next_question": self.next_question.to_dict() if self.next_question else None,
            "decision_tree_ref": self.decision_tree_ref,
            "core_need_brief_ref": self.core_need_brief_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class SemanticCoverageItem:
    """Coverage status for one source signal."""

    signal_id: str
    source_signal: str
    status: SemanticCoverageItemStatus
    source_refs: list[str] = field(default_factory=list)
    mapped_refs: list[str] = field(default_factory=list)
    notes: str = ""
    blocking: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SemanticCoverageItem":
        data = _strict_mapping(
            payload,
            "semantic_coverage_item",
            {"signal_id", "source_signal", "status", "source_refs", "mapped_refs", "notes", "blocking"},
        )
        item = cls(
            signal_id=require_non_empty_str(data.get("signal_id"), "semantic_coverage_item.signal_id"),
            source_signal=require_non_empty_str(data.get("source_signal"), "semantic_coverage_item.source_signal"),
            status=require_enum(data.get("status"), SemanticCoverageItemStatus, "semantic_coverage_item.status"),
            source_refs=require_str_list(data.get("source_refs", []), "semantic_coverage_item.source_refs"),
            mapped_refs=require_str_list(data.get("mapped_refs", []), "semantic_coverage_item.mapped_refs"),
            notes=str(data.get("notes", "")),
            blocking=_require_bool(data.get("blocking", True), "semantic_coverage_item.blocking"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.signal_id, "semantic_coverage_item.signal_id")
        require_non_empty_str(self.source_signal, "semantic_coverage_item.source_signal")
        require_enum(self.status, SemanticCoverageItemStatus, "semantic_coverage_item.status")
        _validate_ref_list(self.source_refs, "semantic_coverage_item.source_refs")
        _validate_ref_list(self.mapped_refs, "semantic_coverage_item.mapped_refs")
        if self.status == SemanticCoverageItemStatus.COVERED and not self.mapped_refs:
            raise ContractValidationError("semantic_coverage_item covered signals require mapped_refs")
        if not isinstance(self.blocking, bool):
            raise ContractValidationError("semantic_coverage_item.blocking must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "signal_id": self.signal_id,
            "source_signal": self.source_signal,
            "status": self.status.value,
            "source_refs": list(self.source_refs),
            "mapped_refs": list(self.mapped_refs),
            "notes": self.notes,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class MissionSemanticCoverageReport:
    """Deterministic report proving user signals were preserved."""

    session_id: str
    status: SemanticCoverageStatus
    coverage_items: list[SemanticCoverageItem] = field(default_factory=list)
    unmapped_signals: list[str] = field(default_factory=list)
    schema_version: str = SEMANTIC_COVERAGE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionSemanticCoverageReport":
        data = _strict_mapping(
            payload,
            "semantic_coverage_report",
            {"schema_version", "session_id", "status", "coverage_items", "unmapped_signals"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "semantic_coverage_report.session_id"),
            status=require_enum(data.get("status"), SemanticCoverageStatus, "semantic_coverage_report.status"),
            coverage_items=_item_list(
                data.get("coverage_items", []),
                "semantic_coverage_report.coverage_items",
                SemanticCoverageItem.from_dict,
            ),
            unmapped_signals=require_str_list(data.get("unmapped_signals", []), "semantic_coverage_report.unmapped_signals"),
            schema_version=require_non_empty_str(
                data.get("schema_version", SEMANTIC_COVERAGE_SCHEMA_VERSION),
                "semantic_coverage_report.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, SEMANTIC_COVERAGE_SCHEMA_VERSION, "semantic_coverage_report.schema_version")
        require_non_empty_str(self.session_id, "semantic_coverage_report.session_id")
        require_enum(self.status, SemanticCoverageStatus, "semantic_coverage_report.status")
        _require_unique([item.signal_id for item in self.coverage_items], "semantic_coverage_report.coverage_items.signal_id")
        for item in self.coverage_items:
            item.validate()
        require_str_list(self.unmapped_signals, "semantic_coverage_report.unmapped_signals")
        has_blocking_unmapped = any(
            item.blocking and item.status == SemanticCoverageItemStatus.UNMAPPED for item in self.coverage_items
        )
        if self.status == SemanticCoverageStatus.PASSED and (self.unmapped_signals or has_blocking_unmapped):
            raise ContractValidationError("semantic_coverage_report cannot pass with unmapped blocking signals")
        assert_refs_only_payload(self.to_dict_without_validation(), "semantic_coverage_report")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "status": self.status.value,
            "coverage_items": [item.to_dict() for item in self.coverage_items],
            "unmapped_signals": list(self.unmapped_signals),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class MissionSolutionPlan:
    """Product and architecture plan before MissionIR mapping."""

    session_id: str
    status: SolutionPlanStatus
    summary: str
    core_need_ref: str
    mvp_scope: list[str] = field(default_factory=list)
    future_scope: list[str] = field(default_factory=list)
    rejected_directions: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    selected_capability_profile_ids: list[str] = field(default_factory=list)
    selected_verification_profile_ids: list[str] = field(default_factory=list)
    verification_strategy: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    authority_requirements: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    schema_version: str = SOLUTION_PLAN_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionSolutionPlan":
        data = _strict_mapping(
            payload,
            "mission_solution_plan",
            {
                "schema_version",
                "session_id",
                "status",
                "summary",
                "core_need_ref",
                "mvp_scope",
                "future_scope",
                "rejected_directions",
                "expected_artifacts",
                "selected_capability_profile_ids",
                "selected_verification_profile_ids",
                "verification_strategy",
                "risks",
                "authority_requirements",
                "source_refs",
            },
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "mission_solution_plan.session_id"),
            status=require_enum(data.get("status"), SolutionPlanStatus, "mission_solution_plan.status"),
            summary=require_non_empty_str(data.get("summary"), "mission_solution_plan.summary"),
            core_need_ref=validate_ref(data.get("core_need_ref"), "mission_solution_plan.core_need_ref"),
            mvp_scope=require_str_list(data.get("mvp_scope", []), "mission_solution_plan.mvp_scope"),
            future_scope=require_str_list(data.get("future_scope", []), "mission_solution_plan.future_scope"),
            rejected_directions=require_str_list(
                data.get("rejected_directions", []),
                "mission_solution_plan.rejected_directions",
            ),
            expected_artifacts=require_str_list(data.get("expected_artifacts", []), "mission_solution_plan.expected_artifacts"),
            selected_capability_profile_ids=require_str_list(
                data.get("selected_capability_profile_ids", []),
                "mission_solution_plan.selected_capability_profile_ids",
            ),
            selected_verification_profile_ids=require_str_list(
                data.get("selected_verification_profile_ids", []),
                "mission_solution_plan.selected_verification_profile_ids",
            ),
            verification_strategy=require_str_list(
                data.get("verification_strategy", []),
                "mission_solution_plan.verification_strategy",
            ),
            risks=require_str_list(data.get("risks", []), "mission_solution_plan.risks"),
            authority_requirements=require_str_list(
                data.get("authority_requirements", []),
                "mission_solution_plan.authority_requirements",
            ),
            source_refs=require_str_list(data.get("source_refs", []), "mission_solution_plan.source_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", SOLUTION_PLAN_SCHEMA_VERSION),
                "mission_solution_plan.schema_version",
            ),
        )
        item.validate()
        return item

    @property
    def plan_hash(self) -> str:
        return stable_json_hash(self.to_dict())

    def validate(self) -> None:
        _require_schema(self.schema_version, SOLUTION_PLAN_SCHEMA_VERSION, "mission_solution_plan.schema_version")
        require_non_empty_str(self.session_id, "mission_solution_plan.session_id")
        require_enum(self.status, SolutionPlanStatus, "mission_solution_plan.status")
        require_non_empty_str(self.summary, "mission_solution_plan.summary")
        validate_ref(self.core_need_ref, "mission_solution_plan.core_need_ref")
        require_str_list(self.mvp_scope, "mission_solution_plan.mvp_scope")
        require_str_list(self.future_scope, "mission_solution_plan.future_scope")
        require_str_list(self.rejected_directions, "mission_solution_plan.rejected_directions")
        _validate_ref_list(self.expected_artifacts, "mission_solution_plan.expected_artifacts")
        require_str_list(self.selected_capability_profile_ids, "mission_solution_plan.selected_capability_profile_ids")
        require_str_list(self.selected_verification_profile_ids, "mission_solution_plan.selected_verification_profile_ids")
        require_str_list(self.verification_strategy, "mission_solution_plan.verification_strategy")
        require_str_list(self.risks, "mission_solution_plan.risks")
        require_str_list(self.authority_requirements, "mission_solution_plan.authority_requirements")
        _validate_ref_list(self.source_refs, "mission_solution_plan.source_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "mission_solution_plan")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "status": self.status.value,
            "summary": self.summary,
            "core_need_ref": self.core_need_ref,
            "mvp_scope": list(self.mvp_scope),
            "future_scope": list(self.future_scope),
            "rejected_directions": list(self.rejected_directions),
            "expected_artifacts": list(self.expected_artifacts),
            "selected_capability_profile_ids": list(self.selected_capability_profile_ids),
            "selected_verification_profile_ids": list(self.selected_verification_profile_ids),
            "verification_strategy": list(self.verification_strategy),
            "risks": list(self.risks),
            "authority_requirements": list(self.authority_requirements),
            "source_refs": list(self.source_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class PlanRiskRegister:
    """Risk register for the solution plan."""

    session_id: str
    risks: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    schema_version: str = PLAN_RISK_REGISTER_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlanRiskRegister":
        data = _strict_mapping(
            payload,
            "plan_risk_register",
            {"schema_version", "session_id", "risks", "mitigations", "source_refs"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "plan_risk_register.session_id"),
            risks=require_str_list(data.get("risks", []), "plan_risk_register.risks"),
            mitigations=require_str_list(data.get("mitigations", []), "plan_risk_register.mitigations"),
            source_refs=require_str_list(data.get("source_refs", []), "plan_risk_register.source_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PLAN_RISK_REGISTER_SCHEMA_VERSION),
                "plan_risk_register.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, PLAN_RISK_REGISTER_SCHEMA_VERSION, "plan_risk_register.schema_version")
        require_non_empty_str(self.session_id, "plan_risk_register.session_id")
        require_str_list(self.risks, "plan_risk_register.risks")
        require_str_list(self.mitigations, "plan_risk_register.mitigations")
        _validate_ref_list(self.source_refs, "plan_risk_register.source_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "plan_risk_register")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "risks": list(self.risks),
            "mitigations": list(self.mitigations),
            "source_refs": list(self.source_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class PlanReviewRecord:
    """Authority record for solution plan review."""

    session_id: str
    decision: PlanReviewDecision
    reviewed_plan_ref: str
    reviewed_plan_hash: str
    reviewed_by: str
    authority: ApprovalAuthority
    review_notes: list[str] = field(default_factory=list)
    requested_changes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: str = PLAN_REVIEW_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlanReviewRecord":
        data = _strict_mapping(
            payload,
            "plan_review",
            {
                "schema_version",
                "session_id",
                "decision",
                "reviewed_plan_ref",
                "reviewed_plan_hash",
                "reviewed_by",
                "authority",
                "review_notes",
                "requested_changes",
                "created_at",
            },
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "plan_review.session_id"),
            decision=require_enum(data.get("decision"), PlanReviewDecision, "plan_review.decision"),
            reviewed_plan_ref=validate_ref(data.get("reviewed_plan_ref"), "plan_review.reviewed_plan_ref"),
            reviewed_plan_hash=require_non_empty_str(data.get("reviewed_plan_hash"), "plan_review.reviewed_plan_hash"),
            reviewed_by=require_non_empty_str(data.get("reviewed_by"), "plan_review.reviewed_by"),
            authority=require_enum(data.get("authority"), ApprovalAuthority, "plan_review.authority"),
            review_notes=require_str_list(data.get("review_notes", []), "plan_review.review_notes"),
            requested_changes=require_str_list(data.get("requested_changes", []), "plan_review.requested_changes"),
            created_at=require_non_empty_str(data.get("created_at"), "plan_review.created_at"),
            schema_version=require_non_empty_str(data.get("schema_version", PLAN_REVIEW_SCHEMA_VERSION), "plan_review.schema_version"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, PLAN_REVIEW_SCHEMA_VERSION, "plan_review.schema_version")
        require_non_empty_str(self.session_id, "plan_review.session_id")
        require_enum(self.decision, PlanReviewDecision, "plan_review.decision")
        validate_ref(self.reviewed_plan_ref, "plan_review.reviewed_plan_ref")
        _require_sha256(self.reviewed_plan_hash, "plan_review.reviewed_plan_hash")
        require_non_empty_str(self.reviewed_by, "plan_review.reviewed_by")
        require_enum(self.authority, ApprovalAuthority, "plan_review.authority")
        require_str_list(self.review_notes, "plan_review.review_notes")
        require_str_list(self.requested_changes, "plan_review.requested_changes")
        require_non_empty_str(self.created_at, "plan_review.created_at")
        assert_refs_only_payload(self.to_dict_without_validation(), "plan_review")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "decision": self.decision.value,
            "reviewed_plan_ref": self.reviewed_plan_ref,
            "reviewed_plan_hash": self.reviewed_plan_hash,
            "reviewed_by": self.reviewed_by,
            "authority": self.authority.value,
            "review_notes": list(self.review_notes),
            "requested_changes": list(self.requested_changes),
            "created_at": self.created_at,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class RequirementMapping:
    """Mapping from one approved requirement to MissionIR fields."""

    requirement_id: str
    requirement_text: str
    status: MappingStatus
    mission_paths: list[str] = field(default_factory=list)
    mapped_refs: list[str] = field(default_factory=list)
    rationale: str = ""
    blocking: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RequirementMapping":
        data = _strict_mapping(
            payload,
            "requirement_mapping",
            {"requirement_id", "requirement_text", "status", "mission_paths", "mapped_refs", "rationale", "blocking"},
        )
        item = cls(
            requirement_id=require_non_empty_str(data.get("requirement_id"), "requirement_mapping.requirement_id"),
            requirement_text=require_non_empty_str(data.get("requirement_text"), "requirement_mapping.requirement_text"),
            status=require_enum(data.get("status"), MappingStatus, "requirement_mapping.status"),
            mission_paths=require_str_list(data.get("mission_paths", []), "requirement_mapping.mission_paths"),
            mapped_refs=require_str_list(data.get("mapped_refs", []), "requirement_mapping.mapped_refs"),
            rationale=str(data.get("rationale", "")),
            blocking=_require_bool(data.get("blocking", True), "requirement_mapping.blocking"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.requirement_id, "requirement_mapping.requirement_id")
        require_non_empty_str(self.requirement_text, "requirement_mapping.requirement_text")
        require_enum(self.status, MappingStatus, "requirement_mapping.status")
        require_str_list(self.mission_paths, "requirement_mapping.mission_paths")
        _validate_ref_list(self.mapped_refs, "requirement_mapping.mapped_refs")
        if self.status == MappingStatus.MAPPED and not (self.mission_paths or self.mapped_refs):
            raise ContractValidationError("requirement_mapping mapped status requires mission_paths or mapped_refs")
        if self.status in {MappingStatus.DROPPED, MappingStatus.ROUTED} and not self.rationale:
            raise ContractValidationError("requirement_mapping dropped/routed status requires rationale")
        if not isinstance(self.blocking, bool):
            raise ContractValidationError("requirement_mapping.blocking must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "requirement_id": self.requirement_id,
            "requirement_text": self.requirement_text,
            "status": self.status.value,
            "mission_paths": list(self.mission_paths),
            "mapped_refs": list(self.mapped_refs),
            "rationale": self.rationale,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class MissionIRMappingReport:
    """Report proving MissionIR mapping coverage."""

    session_id: str
    draft_mission_ref: str
    requirement_mappings: list[RequirementMapping] = field(default_factory=list)
    unmapped_requirements: list[str] = field(default_factory=list)
    dropped_requirements: list[str] = field(default_factory=list)
    profile_mappings: list[str] = field(default_factory=list)
    validator_mappings: list[str] = field(default_factory=list)
    schema_version: str = MISSION_MAPPING_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionIRMappingReport":
        data = _strict_mapping(
            payload,
            "mission_mapping_report",
            {
                "schema_version",
                "session_id",
                "draft_mission_ref",
                "requirement_mappings",
                "unmapped_requirements",
                "dropped_requirements",
                "profile_mappings",
                "validator_mappings",
            },
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "mission_mapping_report.session_id"),
            draft_mission_ref=validate_ref(data.get("draft_mission_ref"), "mission_mapping_report.draft_mission_ref"),
            requirement_mappings=_item_list(
                data.get("requirement_mappings", []),
                "mission_mapping_report.requirement_mappings",
                RequirementMapping.from_dict,
            ),
            unmapped_requirements=require_str_list(
                data.get("unmapped_requirements", []),
                "mission_mapping_report.unmapped_requirements",
            ),
            dropped_requirements=require_str_list(
                data.get("dropped_requirements", []),
                "mission_mapping_report.dropped_requirements",
            ),
            profile_mappings=require_str_list(data.get("profile_mappings", []), "mission_mapping_report.profile_mappings"),
            validator_mappings=require_str_list(
                data.get("validator_mappings", []),
                "mission_mapping_report.validator_mappings",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", MISSION_MAPPING_REPORT_SCHEMA_VERSION),
                "mission_mapping_report.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, MISSION_MAPPING_REPORT_SCHEMA_VERSION, "mission_mapping_report.schema_version")
        require_non_empty_str(self.session_id, "mission_mapping_report.session_id")
        validate_ref(self.draft_mission_ref, "mission_mapping_report.draft_mission_ref")
        _require_unique(
            [mapping.requirement_id for mapping in self.requirement_mappings],
            "mission_mapping_report.requirement_mappings.requirement_id",
        )
        for mapping in self.requirement_mappings:
            mapping.validate()
        require_str_list(self.unmapped_requirements, "mission_mapping_report.unmapped_requirements")
        require_str_list(self.dropped_requirements, "mission_mapping_report.dropped_requirements")
        require_str_list(self.profile_mappings, "mission_mapping_report.profile_mappings")
        require_str_list(self.validator_mappings, "mission_mapping_report.validator_mappings")
        blocking_unmapped = any(
            mapping.blocking and mapping.status == MappingStatus.UNMAPPED for mapping in self.requirement_mappings
        )
        if blocking_unmapped and not self.unmapped_requirements:
            raise ContractValidationError("mission_mapping_report must list unmapped blocking requirements")
        assert_refs_only_payload(self.to_dict_without_validation(), "mission_mapping_report")

    @property
    def has_blocking_gaps(self) -> bool:
        if self.unmapped_requirements:
            return True
        return any(
            mapping.blocking and mapping.status in {MappingStatus.UNMAPPED, MappingStatus.DROPPED}
            for mapping in self.requirement_mappings
        )

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "draft_mission_ref": self.draft_mission_ref,
            "requirement_mappings": [mapping.to_dict() for mapping in self.requirement_mappings],
            "unmapped_requirements": list(self.unmapped_requirements),
            "dropped_requirements": list(self.dropped_requirements),
            "profile_mappings": list(self.profile_mappings),
            "validator_mappings": list(self.validator_mappings),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class FrontDeskFreezeGateResult:
    """Structured deterministic freeze gate result."""

    session_id: str
    decision: FreezeGateDecision
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    reason: str = ""
    schema_version: str = FREEZE_GATE_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FrontDeskFreezeGateResult":
        data = _strict_mapping(
            payload,
            "frontdesk_freeze_gate_result",
            {"schema_version", "session_id", "decision", "passed_checks", "failed_checks", "artifact_refs", "reason"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "frontdesk_freeze_gate_result.session_id"),
            decision=require_enum(data.get("decision"), FreezeGateDecision, "frontdesk_freeze_gate_result.decision"),
            passed_checks=require_str_list(data.get("passed_checks", []), "frontdesk_freeze_gate_result.passed_checks"),
            failed_checks=require_str_list(data.get("failed_checks", []), "frontdesk_freeze_gate_result.failed_checks"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "frontdesk_freeze_gate_result.artifact_refs"),
            reason=str(data.get("reason", "")),
            schema_version=require_non_empty_str(
                data.get("schema_version", FREEZE_GATE_RESULT_SCHEMA_VERSION),
                "frontdesk_freeze_gate_result.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            FREEZE_GATE_RESULT_SCHEMA_VERSION,
            "frontdesk_freeze_gate_result.schema_version",
        )
        require_non_empty_str(self.session_id, "frontdesk_freeze_gate_result.session_id")
        require_enum(self.decision, FreezeGateDecision, "frontdesk_freeze_gate_result.decision")
        require_str_list(self.passed_checks, "frontdesk_freeze_gate_result.passed_checks")
        require_str_list(self.failed_checks, "frontdesk_freeze_gate_result.failed_checks")
        _validate_ref_list(self.artifact_refs, "frontdesk_freeze_gate_result.artifact_refs")
        if self.decision == FreezeGateDecision.FREEZE and self.failed_checks:
            raise ContractValidationError("frontdesk_freeze_gate_result freeze decision cannot have failed checks")
        if self.decision != FreezeGateDecision.FREEZE and not self.failed_checks:
            raise ContractValidationError("frontdesk_freeze_gate_result non-freeze decision requires failed checks")
        assert_refs_only_payload(self.to_dict_without_validation(), "frontdesk_freeze_gate_result")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "decision": self.decision.value,
            "passed_checks": list(self.passed_checks),
            "failed_checks": list(self.failed_checks),
            "artifact_refs": list(self.artifact_refs),
            "reason": self.reason,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def stable_bundle_hash(*payloads: Mapping[str, Any]) -> str:
    """Return the stable hash for an approved spec-grill authoring bundle."""

    return stable_json_hash({"approved_spec_grill_payloads": [dict(payload) for payload in payloads]})


def _strict_mapping(payload: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
    reject_raw_authoring_fields(data, field_name)
    return data


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"{field_name} is unsupported")


def _validate_ref_list(values: list[str], field_name: str) -> None:
    require_str_list(values, field_name)
    for index, value in enumerate(values):
        validate_ref(value, f"{field_name}[{index}]")


def _require_unique(values: list[str], field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ContractValidationError(f"{field_name} contains duplicate value: {value}")
        seen.add(value)


def _safe_payload(value: Any, field_name: str) -> None:
    reject_raw_authoring_fields(value, field_name)
    assert_refs_only_payload(ensure_json_value(value, field_name), field_name)


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(f"{field_name} must be a boolean")
    return value


def _require_sha256(value: str, field_name: str) -> None:
    if not require_non_empty_str(value, field_name).startswith("sha256:"):
        raise ContractValidationError(f"{field_name} must be a sha256 hash")


def _item_list(value: Any, field_name: str, factory: Callable[[Mapping[str, Any]], T]) -> list[T]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    return [factory(require_mapping(item, f"{field_name}[]")) for item in value]


__all__ = [
    "CoreNeedBrief",
    "CoreNeedOpenQuestion",
    "DecisionNode",
    "DecisionOption",
    "DecisionStatus",
    "DecisionTree",
    "DomainLanguage",
    "FactConfidence",
    "FreezeGateDecision",
    "FrontDeskFreezeGateResult",
    "GrillingQuestion",
    "MappingStatus",
    "MissionAuditRoute",
    "MissionIRMappingReport",
    "MissionSemanticCoverageReport",
    "MissionSolutionPlan",
    "NeedGrillingReadiness",
    "NeedGrillingReport",
    "PlanReviewDecision",
    "PlanReviewRecord",
    "PlanRiskRegister",
    "ProfileCatalogSnapshot",
    "QuestionAnswerType",
    "RequirementMapping",
    "SemanticCoverageItem",
    "SemanticCoverageItemStatus",
    "SemanticCoverageStatus",
    "SolutionPlanStatus",
    "SourceAdmissionReport",
    "WorkspaceFact",
    "WorkspaceFacts",
    "stable_bundle_hash",
]
