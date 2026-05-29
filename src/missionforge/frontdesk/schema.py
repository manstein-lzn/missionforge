"""FrontDesk authoring contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Self

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)


FRONTDESK_SESSION_SCHEMA_VERSION = "missionforge.frontdesk_session.v1"
CONVERSATION_TURN_SCHEMA_VERSION = "missionforge.frontdesk_conversation_turn.v1"
SANITIZED_SOURCE_SET_SCHEMA_VERSION = "missionforge.frontdesk_sanitized_sources.v1"
MISSION_SEMANTIC_LOCK_SCHEMA_VERSION = "missionforge.frontdesk_semantic_lock.v1"
MISSION_BRIEF_SCHEMA_VERSION = "missionforge.frontdesk_mission_brief.v1"
PROFILE_RECOMMENDATION_SCHEMA_VERSION = "missionforge.frontdesk_profile_recommendation.v1"
PROFILE_RECOMMENDATION_SET_SCHEMA_VERSION = "missionforge.frontdesk_profile_recommendations.v1"
MISSION_PLAN_SCHEMA_VERSION = "missionforge.frontdesk_mission_plan.v1"
MISSION_AUTHORING_AUDIT_SCHEMA_VERSION = "missionforge.frontdesk_authoring_audit.v1"
AUTHORING_APPROVAL_SCHEMA_VERSION = "missionforge.frontdesk_authoring_approval.v1"
FREEZE_MANIFEST_SCHEMA_VERSION = "missionforge.frontdesk_freeze_manifest.v1"


class FrontDeskStatus(StrEnum):
    """FrontDesk authoring session lifecycle states."""

    NEW = "new"
    ELICITING = "eliciting"
    DRAFT_READY = "draft_ready"
    AUDIT_REQUIRED = "audit_required"
    NEEDS_CLARIFICATION = "needs_clarification"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    FROZEN = "frozen"
    HANDED_OFF = "handed_off"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    UNSUPPORTED = "unsupported"
    FAILED_CLOSED = "failed_closed"


class ConversationRole(StrEnum):
    """Allowed FrontDesk conversation provenance roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ProfileRecommendationKind(StrEnum):
    """Profile recommendation target."""

    CAPABILITY = "capability"
    VERIFICATION = "verification"


class AuditDecision(StrEnum):
    """FrontDesk audit route."""

    APPROVE = "approve"
    NEEDS_CLARIFICATION = "needs_clarification"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    UNSUPPORTED = "unsupported"
    FAILED_CLOSED = "failed_closed"


class ApprovalAuthority(StrEnum):
    """Authority that approved an authoring contract."""

    USER = "user"
    REVIEWER = "reviewer"
    POLICY = "policy"


RAW_FIELD_NAMES = {
    "api_key",
    "authorization",
    "conversation",
    "credential",
    "credentials",
    "messages",
    "model_output",
    "password",
    "prompt",
    "prompts",
    "raw_model_output",
    "raw_prompt",
    "raw_transcript",
    "secret",
    "transcript",
}
RAW_FIELD_FRAGMENTS = {"credential", "password", "prompt", "secret", "transcript"}


@dataclass(frozen=True)
class ConversationTurn:
    """One optional FrontDesk provenance turn."""

    turn_id: str
    role: ConversationRole
    content_ref: str
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CONVERSATION_TURN_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "conversation_turn",
            {"schema_version", "turn_id", "role", "content_ref", "created_at", "metadata"},
        )
        item = cls(
            turn_id=require_non_empty_str(data.get("turn_id"), "conversation_turn.turn_id"),
            role=require_enum(data.get("role"), ConversationRole, "conversation_turn.role"),
            content_ref=validate_ref(data.get("content_ref"), "conversation_turn.content_ref"),
            created_at=str(data.get("created_at", "")),
            metadata=require_mapping(data.get("metadata", {}), "conversation_turn.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONVERSATION_TURN_SCHEMA_VERSION),
                "conversation_turn.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, CONVERSATION_TURN_SCHEMA_VERSION, "conversation_turn.schema_version")
        require_non_empty_str(self.turn_id, "conversation_turn.turn_id")
        require_enum(self.role, ConversationRole, "conversation_turn.role")
        validate_ref(self.content_ref, "conversation_turn.content_ref")
        _safe_metadata(self.metadata, "conversation_turn.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "turn_id": self.turn_id,
            "role": self.role.value,
            "content_ref": self.content_ref,
            "created_at": self.created_at,
            "metadata": ensure_json_value(self.metadata, "conversation_turn.metadata"),
        }


@dataclass(frozen=True)
class SanitizedSourceSet:
    """Admitted and excluded source refs for MissionIR authoring."""

    session_id: str
    admitted_source_refs: list[str] = field(default_factory=list)
    excluded_source_refs: list[str] = field(default_factory=list)
    redaction_notes: list[str] = field(default_factory=list)
    schema_version: str = SANITIZED_SOURCE_SET_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "sanitized_source_set",
            {"schema_version", "session_id", "admitted_source_refs", "excluded_source_refs", "redaction_notes"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "sanitized_source_set.session_id"),
            admitted_source_refs=require_str_list(
                data.get("admitted_source_refs", []),
                "sanitized_source_set.admitted_source_refs",
            ),
            excluded_source_refs=require_str_list(
                data.get("excluded_source_refs", []),
                "sanitized_source_set.excluded_source_refs",
            ),
            redaction_notes=require_str_list(data.get("redaction_notes", []), "sanitized_source_set.redaction_notes"),
            schema_version=require_non_empty_str(
                data.get("schema_version", SANITIZED_SOURCE_SET_SCHEMA_VERSION),
                "sanitized_source_set.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, SANITIZED_SOURCE_SET_SCHEMA_VERSION, "sanitized_source_set.schema_version")
        require_non_empty_str(self.session_id, "sanitized_source_set.session_id")
        _validate_ref_list(self.admitted_source_refs, "sanitized_source_set.admitted_source_refs")
        _validate_ref_list(self.excluded_source_refs, "sanitized_source_set.excluded_source_refs")
        require_str_list(self.redaction_notes, "sanitized_source_set.redaction_notes")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "admitted_source_refs": list(self.admitted_source_refs),
            "excluded_source_refs": list(self.excluded_source_refs),
            "redaction_notes": list(self.redaction_notes),
        }


@dataclass(frozen=True)
class MissionSemanticLock:
    """Structured task truth extracted for MissionIR authoring."""

    session_id: str
    summary: str
    requirement_clauses: list[str]
    source_refs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    schema_version: str = MISSION_SEMANTIC_LOCK_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "mission_semantic_lock",
            {
                "schema_version",
                "session_id",
                "summary",
                "requirement_clauses",
                "source_refs",
                "assumptions",
                "non_goals",
                "risks",
            },
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "mission_semantic_lock.session_id"),
            summary=require_non_empty_str(data.get("summary"), "mission_semantic_lock.summary"),
            requirement_clauses=require_str_list(
                data.get("requirement_clauses"),
                "mission_semantic_lock.requirement_clauses",
            ),
            source_refs=require_str_list(data.get("source_refs", []), "mission_semantic_lock.source_refs"),
            assumptions=require_str_list(data.get("assumptions", []), "mission_semantic_lock.assumptions"),
            non_goals=require_str_list(data.get("non_goals", []), "mission_semantic_lock.non_goals"),
            risks=require_str_list(data.get("risks", []), "mission_semantic_lock.risks"),
            schema_version=require_non_empty_str(
                data.get("schema_version", MISSION_SEMANTIC_LOCK_SCHEMA_VERSION),
                "mission_semantic_lock.schema_version",
            ),
        )
        item.validate()
        return item

    @property
    def semantic_hash(self) -> str:
        return stable_json_hash(self.to_dict())

    def validate(self) -> None:
        _require_schema(self.schema_version, MISSION_SEMANTIC_LOCK_SCHEMA_VERSION, "mission_semantic_lock.schema_version")
        require_non_empty_str(self.session_id, "mission_semantic_lock.session_id")
        require_non_empty_str(self.summary, "mission_semantic_lock.summary")
        require_str_list(self.requirement_clauses, "mission_semantic_lock.requirement_clauses")
        _validate_ref_list(self.source_refs, "mission_semantic_lock.source_refs")
        require_str_list(self.assumptions, "mission_semantic_lock.assumptions")
        require_str_list(self.non_goals, "mission_semantic_lock.non_goals")
        require_str_list(self.risks, "mission_semantic_lock.risks")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "summary": self.summary,
            "requirement_clauses": list(self.requirement_clauses),
            "source_refs": list(self.source_refs),
            "assumptions": list(self.assumptions),
            "non_goals": list(self.non_goals),
            "risks": list(self.risks),
        }


@dataclass(frozen=True)
class MissionBrief:
    """User-readable mission brief used to draft MissionIR."""

    session_id: str
    goal: str
    deliverable_type: str
    success_signals: list[str]
    target_users: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    schema_version: str = MISSION_BRIEF_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "mission_brief",
            {
                "schema_version",
                "session_id",
                "goal",
                "deliverable_type",
                "success_signals",
                "target_users",
                "non_goals",
                "open_questions",
            },
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "mission_brief.session_id"),
            goal=require_non_empty_str(data.get("goal"), "mission_brief.goal"),
            deliverable_type=require_non_empty_str(data.get("deliverable_type"), "mission_brief.deliverable_type"),
            success_signals=require_str_list(data.get("success_signals"), "mission_brief.success_signals"),
            target_users=require_str_list(data.get("target_users", []), "mission_brief.target_users"),
            non_goals=require_str_list(data.get("non_goals", []), "mission_brief.non_goals"),
            open_questions=require_str_list(data.get("open_questions", []), "mission_brief.open_questions"),
            schema_version=require_non_empty_str(data.get("schema_version", MISSION_BRIEF_SCHEMA_VERSION), "mission_brief.schema_version"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, MISSION_BRIEF_SCHEMA_VERSION, "mission_brief.schema_version")
        require_non_empty_str(self.session_id, "mission_brief.session_id")
        require_non_empty_str(self.goal, "mission_brief.goal")
        require_non_empty_str(self.deliverable_type, "mission_brief.deliverable_type")
        require_str_list(self.success_signals, "mission_brief.success_signals")
        require_str_list(self.target_users, "mission_brief.target_users")
        require_str_list(self.non_goals, "mission_brief.non_goals")
        require_str_list(self.open_questions, "mission_brief.open_questions")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "goal": self.goal,
            "deliverable_type": self.deliverable_type,
            "success_signals": list(self.success_signals),
            "target_users": list(self.target_users),
            "non_goals": list(self.non_goals),
            "open_questions": list(self.open_questions),
        }


@dataclass(frozen=True)
class ProfileRecommendation:
    """One selected or candidate profile recommendation."""

    profile_id: str
    kind: ProfileRecommendationKind
    rationale: str
    requirements: dict[str, Any] = field(default_factory=dict)
    selected: bool = True
    schema_version: str = PROFILE_RECOMMENDATION_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "profile_recommendation",
            {"schema_version", "profile_id", "kind", "rationale", "requirements", "selected"},
        )
        item = cls(
            profile_id=require_non_empty_str(data.get("profile_id"), "profile_recommendation.profile_id"),
            kind=require_enum(data.get("kind"), ProfileRecommendationKind, "profile_recommendation.kind"),
            rationale=require_non_empty_str(data.get("rationale"), "profile_recommendation.rationale"),
            requirements=require_mapping(data.get("requirements", {}), "profile_recommendation.requirements"),
            selected=bool(data.get("selected", True)),
            schema_version=require_non_empty_str(
                data.get("schema_version", PROFILE_RECOMMENDATION_SCHEMA_VERSION),
                "profile_recommendation.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, PROFILE_RECOMMENDATION_SCHEMA_VERSION, "profile_recommendation.schema_version")
        require_non_empty_str(self.profile_id, "profile_recommendation.profile_id")
        require_enum(self.kind, ProfileRecommendationKind, "profile_recommendation.kind")
        require_non_empty_str(self.rationale, "profile_recommendation.rationale")
        _safe_metadata(self.requirements, "profile_recommendation.requirements")
        if not isinstance(self.selected, bool):
            raise ContractValidationError("profile_recommendation.selected must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "kind": self.kind.value,
            "rationale": self.rationale,
            "requirements": ensure_json_value(self.requirements, "profile_recommendation.requirements"),
            "selected": self.selected,
        }


@dataclass(frozen=True)
class ProfileRecommendationSet:
    """Profile recommendations chosen for an authoring session."""

    session_id: str
    recommendations: list[ProfileRecommendation]
    rejected_profile_ids: list[str] = field(default_factory=list)
    schema_version: str = PROFILE_RECOMMENDATION_SET_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "profile_recommendation_set",
            {"schema_version", "session_id", "recommendations", "rejected_profile_ids"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "profile_recommendation_set.session_id"),
            recommendations=[
                ProfileRecommendation.from_dict(require_mapping(child, "profile_recommendation_set.recommendations[]"))
                for child in data.get("recommendations", [])
            ],
            rejected_profile_ids=require_str_list(
                data.get("rejected_profile_ids", []),
                "profile_recommendation_set.rejected_profile_ids",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", PROFILE_RECOMMENDATION_SET_SCHEMA_VERSION),
                "profile_recommendation_set.schema_version",
            ),
        )
        item.validate()
        return item

    @property
    def selected_capability_profiles(self) -> list[ProfileRecommendation]:
        return [item for item in self.recommendations if item.selected and item.kind == ProfileRecommendationKind.CAPABILITY]

    @property
    def selected_verification_profiles(self) -> list[ProfileRecommendation]:
        return [item for item in self.recommendations if item.selected and item.kind == ProfileRecommendationKind.VERIFICATION]

    def validate(self) -> None:
        _require_schema(self.schema_version, PROFILE_RECOMMENDATION_SET_SCHEMA_VERSION, "profile_recommendation_set.schema_version")
        require_non_empty_str(self.session_id, "profile_recommendation_set.session_id")
        selected_keys: set[tuple[str, ProfileRecommendationKind]] = set()
        for item in self.recommendations:
            item.validate()
            key = (item.profile_id, item.kind)
            if item.selected and key in selected_keys:
                raise ContractValidationError("profile_recommendation_set contains duplicate selected profile")
            if item.selected:
                selected_keys.add(key)
        require_str_list(self.rejected_profile_ids, "profile_recommendation_set.rejected_profile_ids")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "recommendations": [item.to_dict() for item in self.recommendations],
            "rejected_profile_ids": list(self.rejected_profile_ids),
        }


@dataclass(frozen=True)
class MissionPlan:
    """Planned MissionIR outputs, constraints, and verification shape."""

    session_id: str
    expected_artifacts: list[str]
    constraints: list[dict[str, Any]] = field(default_factory=list)
    validators: list[dict[str, Any]] = field(default_factory=list)
    manual_gates: list[dict[str, Any]] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    schema_version: str = MISSION_PLAN_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "mission_plan",
            {
                "schema_version",
                "session_id",
                "expected_artifacts",
                "constraints",
                "validators",
                "manual_gates",
                "risk_notes",
            },
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "mission_plan.session_id"),
            expected_artifacts=require_str_list(data.get("expected_artifacts"), "mission_plan.expected_artifacts"),
            constraints=[require_mapping(child, "mission_plan.constraints[]") for child in data.get("constraints", [])],
            validators=[require_mapping(child, "mission_plan.validators[]") for child in data.get("validators", [])],
            manual_gates=[require_mapping(child, "mission_plan.manual_gates[]") for child in data.get("manual_gates", [])],
            risk_notes=require_str_list(data.get("risk_notes", []), "mission_plan.risk_notes"),
            schema_version=require_non_empty_str(data.get("schema_version", MISSION_PLAN_SCHEMA_VERSION), "mission_plan.schema_version"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, MISSION_PLAN_SCHEMA_VERSION, "mission_plan.schema_version")
        require_non_empty_str(self.session_id, "mission_plan.session_id")
        _validate_ref_list(self.expected_artifacts, "mission_plan.expected_artifacts")
        _safe_metadata(self.constraints, "mission_plan.constraints")
        _safe_metadata(self.validators, "mission_plan.validators")
        _safe_metadata(self.manual_gates, "mission_plan.manual_gates")
        require_str_list(self.risk_notes, "mission_plan.risk_notes")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "expected_artifacts": list(self.expected_artifacts),
            "constraints": ensure_json_value(self.constraints, "mission_plan.constraints"),
            "validators": ensure_json_value(self.validators, "mission_plan.validators"),
            "manual_gates": ensure_json_value(self.manual_gates, "mission_plan.manual_gates"),
            "risk_notes": list(self.risk_notes),
        }


@dataclass(frozen=True)
class MissionAuthoringAudit:
    """Audit result for a draft authoring contract."""

    session_id: str
    decision: AuditDecision
    findings: list[str] = field(default_factory=list)
    required_followup_questions: list[str] = field(default_factory=list)
    schema_version: str = MISSION_AUTHORING_AUDIT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "mission_authoring_audit",
            {"schema_version", "session_id", "decision", "findings", "required_followup_questions"},
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "mission_authoring_audit.session_id"),
            decision=require_enum(data.get("decision"), AuditDecision, "mission_authoring_audit.decision"),
            findings=require_str_list(data.get("findings", []), "mission_authoring_audit.findings"),
            required_followup_questions=require_str_list(
                data.get("required_followup_questions", []),
                "mission_authoring_audit.required_followup_questions",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", MISSION_AUTHORING_AUDIT_SCHEMA_VERSION),
                "mission_authoring_audit.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, MISSION_AUTHORING_AUDIT_SCHEMA_VERSION, "mission_authoring_audit.schema_version")
        require_non_empty_str(self.session_id, "mission_authoring_audit.session_id")
        require_enum(self.decision, AuditDecision, "mission_authoring_audit.decision")
        require_str_list(self.findings, "mission_authoring_audit.findings")
        require_str_list(self.required_followup_questions, "mission_authoring_audit.required_followup_questions")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "decision": self.decision.value,
            "findings": list(self.findings),
            "required_followup_questions": list(self.required_followup_questions),
        }


@dataclass(frozen=True)
class AuthoringApproval:
    """Authority record required before FrontDesk freeze."""

    session_id: str
    approved_by: str
    authority: ApprovalAuthority
    approved_ref: str
    approved_hash: str
    approval_notes: list[str] = field(default_factory=list)
    schema_version: str = AUTHORING_APPROVAL_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "authoring_approval",
            {
                "schema_version",
                "session_id",
                "approved_by",
                "authority",
                "approved_ref",
                "approved_hash",
                "approval_notes",
            },
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "authoring_approval.session_id"),
            approved_by=require_non_empty_str(data.get("approved_by"), "authoring_approval.approved_by"),
            authority=require_enum(data.get("authority"), ApprovalAuthority, "authoring_approval.authority"),
            approved_ref=validate_ref(data.get("approved_ref"), "authoring_approval.approved_ref"),
            approved_hash=require_non_empty_str(data.get("approved_hash"), "authoring_approval.approved_hash"),
            approval_notes=require_str_list(data.get("approval_notes", []), "authoring_approval.approval_notes"),
            schema_version=require_non_empty_str(
                data.get("schema_version", AUTHORING_APPROVAL_SCHEMA_VERSION),
                "authoring_approval.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, AUTHORING_APPROVAL_SCHEMA_VERSION, "authoring_approval.schema_version")
        require_non_empty_str(self.session_id, "authoring_approval.session_id")
        require_non_empty_str(self.approved_by, "authoring_approval.approved_by")
        require_enum(self.authority, ApprovalAuthority, "authoring_approval.authority")
        validate_ref(self.approved_ref, "authoring_approval.approved_ref")
        if not require_non_empty_str(self.approved_hash, "authoring_approval.approved_hash").startswith("sha256:"):
            raise ContractValidationError("authoring_approval.approved_hash must be a sha256 hash")
        require_str_list(self.approval_notes, "authoring_approval.approval_notes")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "approved_by": self.approved_by,
            "authority": self.authority.value,
            "approved_ref": self.approved_ref,
            "approved_hash": self.approved_hash,
            "approval_notes": list(self.approval_notes),
        }


@dataclass(frozen=True)
class FrontDeskFreezeManifest:
    """Refs-only FrontDesk handoff manifest."""

    session_id: str
    mission_ir_ref: str
    frozen_contract_ref: str
    contract_hash: str
    approval_ref: str
    source_refs: list[str] = field(default_factory=list)
    profile_ids: list[str] = field(default_factory=list)
    schema_version: str = FREEZE_MANIFEST_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "frontdesk_freeze_manifest",
            {
                "schema_version",
                "session_id",
                "mission_ir_ref",
                "frozen_contract_ref",
                "contract_hash",
                "approval_ref",
                "source_refs",
                "profile_ids",
            },
        )
        item = cls(
            session_id=require_non_empty_str(data.get("session_id"), "frontdesk_freeze_manifest.session_id"),
            mission_ir_ref=validate_ref(data.get("mission_ir_ref"), "frontdesk_freeze_manifest.mission_ir_ref"),
            frozen_contract_ref=validate_ref(
                data.get("frozen_contract_ref"),
                "frontdesk_freeze_manifest.frozen_contract_ref",
            ),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "frontdesk_freeze_manifest.contract_hash"),
            approval_ref=validate_ref(data.get("approval_ref"), "frontdesk_freeze_manifest.approval_ref"),
            source_refs=require_str_list(data.get("source_refs", []), "frontdesk_freeze_manifest.source_refs"),
            profile_ids=require_str_list(data.get("profile_ids", []), "frontdesk_freeze_manifest.profile_ids"),
            schema_version=require_non_empty_str(
                data.get("schema_version", FREEZE_MANIFEST_SCHEMA_VERSION),
                "frontdesk_freeze_manifest.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _require_schema(self.schema_version, FREEZE_MANIFEST_SCHEMA_VERSION, "frontdesk_freeze_manifest.schema_version")
        require_non_empty_str(self.session_id, "frontdesk_freeze_manifest.session_id")
        validate_ref(self.mission_ir_ref, "frontdesk_freeze_manifest.mission_ir_ref")
        validate_ref(self.frozen_contract_ref, "frontdesk_freeze_manifest.frozen_contract_ref")
        if not require_non_empty_str(self.contract_hash, "frontdesk_freeze_manifest.contract_hash").startswith("sha256:"):
            raise ContractValidationError("frontdesk_freeze_manifest.contract_hash must be a sha256 hash")
        validate_ref(self.approval_ref, "frontdesk_freeze_manifest.approval_ref")
        _validate_ref_list(self.source_refs, "frontdesk_freeze_manifest.source_refs")
        require_str_list(self.profile_ids, "frontdesk_freeze_manifest.profile_ids")
        assert_refs_only_payload(self.to_dict_without_validation(), "frontdesk_freeze_manifest")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "mission_ir_ref": self.mission_ir_ref,
            "frozen_contract_ref": self.frozen_contract_ref,
            "contract_hash": self.contract_hash,
            "approval_ref": self.approval_ref,
            "source_refs": list(self.source_refs),
            "profile_ids": list(self.profile_ids),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def reject_raw_authoring_fields(value: Any, field_name: str = "frontdesk") -> None:
    """Reject raw prompt/transcript/provider/secret fields recursively."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = key.lower()
            if lowered in RAW_FIELD_NAMES or any(fragment in lowered for fragment in RAW_FIELD_FRAGMENTS):
                raise ContractValidationError(f"{field_name}.{key} is not allowed in FrontDesk runtime-facing data")
            reject_raw_authoring_fields(item, f"{field_name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_raw_authoring_fields(item, f"{field_name}[{index}]")


def _strict_mapping(payload: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
    reject_raw_authoring_fields(data, field_name)
    return data


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if require_non_empty_str(actual, field_name) != expected:
        raise ContractValidationError(f"{field_name} is unsupported")


def _validate_ref_list(values: list[str], field_name: str) -> None:
    require_str_list(values, field_name)
    for index, ref in enumerate(values):
        validate_ref(ref, f"{field_name}[{index}]")


def _safe_metadata(value: Any, field_name: str) -> None:
    ensure_json_value(value, field_name)
    reject_raw_authoring_fields(value, field_name)
