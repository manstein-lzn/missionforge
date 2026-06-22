"""FrontDesk authoring session state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Self

from ..contracts import ContractValidationError, require_mapping, require_non_empty_str, require_str_list, validate_ref
from .schema import FRONTDESK_SESSION_SCHEMA_VERSION, FrontDeskStatus


SESSION_REF = "frontdesk/session.json"
CONVERSATION_REF = "frontdesk/conversation.jsonl"
SANITIZED_SOURCES_REF = "frontdesk/sanitized_sources.json"
SEMANTIC_LOCK_REF = "frontdesk/semantic_lock.json"
MISSION_BRIEF_REF = "frontdesk/mission_brief.json"
PROFILE_RECOMMENDATIONS_REF = "frontdesk/profile_recommendations.json"
MISSION_PLAN_REF = "frontdesk/mission_plan.json"
DRAFT_MISSION_REF = "frontdesk/draft_mission.json"
MISSION_AUDIT_REF = "frontdesk/mission_audit.json"
AUTHORING_APPROVAL_REF = "frontdesk/authoring_approval.json"
FREEZE_MANIFEST_REF = "frontdesk/freeze_manifest.json"
WORKSPACE_FACTS_REF = "frontdesk/workspace_facts.json"
PROFILE_CATALOG_SNAPSHOT_REF = "frontdesk/profile_catalog_snapshot.json"
DOMAIN_LANGUAGE_REF = "frontdesk/domain_language.json"
SOURCE_ADMISSION_REPORT_REF = "frontdesk/source_admission_report.json"
DECISION_TREE_REF = "frontdesk/decision_tree.json"
CORE_NEED_BRIEF_REF = "frontdesk/core_need_brief.json"
NEED_GRILLING_REPORT_REF = "frontdesk/need_grilling_report.json"
SEMANTIC_COVERAGE_REF = "frontdesk/semantic_coverage.json"
SOLUTION_PLAN_REF = "frontdesk/solution_plan.json"
SOLUTION_PLAN_MARKDOWN_REF = "frontdesk/solution_plan.md"
PLAN_RISK_REGISTER_REF = "frontdesk/plan_risk_register.json"
PLAN_REVIEW_REF = "frontdesk/plan_review.json"
MISSION_MAPPING_REPORT_REF = "frontdesk/mission_mapping_report.json"
FREEZE_GATE_RESULT_REF = "frontdesk/freeze_gate_result.json"
PRODUCT_INQUIRY_PROFILE_REF = "frontdesk/product_inquiry_profile.json"
INTENT_BUNDLE_CANDIDATE_REF = "frontdesk/intent_bundle_candidate.json"
INTENT_BUNDLE_REF = "frontdesk/intent_bundle.json"


ALLOWED_TRANSITIONS: dict[FrontDeskStatus, set[FrontDeskStatus]] = {
    FrontDeskStatus.NEW: {FrontDeskStatus.ELICITING, FrontDeskStatus.FAILED_CLOSED},
    FrontDeskStatus.ELICITING: {
        FrontDeskStatus.NEEDS_CLARIFICATION,
        FrontDeskStatus.DRAFT_READY,
        FrontDeskStatus.HUMAN_REVIEW_REQUIRED,
        FrontDeskStatus.UNSUPPORTED,
        FrontDeskStatus.FAILED_CLOSED,
    },
    FrontDeskStatus.NEEDS_CLARIFICATION: {
        FrontDeskStatus.ELICITING,
        FrontDeskStatus.DRAFT_READY,
        FrontDeskStatus.HUMAN_REVIEW_REQUIRED,
        FrontDeskStatus.FAILED_CLOSED,
    },
    FrontDeskStatus.DRAFT_READY: {
        FrontDeskStatus.AUDIT_REQUIRED,
        FrontDeskStatus.APPROVAL_REQUIRED,
        FrontDeskStatus.NEEDS_CLARIFICATION,
        FrontDeskStatus.FAILED_CLOSED,
    },
    FrontDeskStatus.AUDIT_REQUIRED: {
        FrontDeskStatus.APPROVAL_REQUIRED,
        FrontDeskStatus.NEEDS_CLARIFICATION,
        FrontDeskStatus.HUMAN_REVIEW_REQUIRED,
        FrontDeskStatus.UNSUPPORTED,
        FrontDeskStatus.FAILED_CLOSED,
    },
    FrontDeskStatus.APPROVAL_REQUIRED: {
        FrontDeskStatus.APPROVED,
        FrontDeskStatus.NEEDS_CLARIFICATION,
        FrontDeskStatus.HUMAN_REVIEW_REQUIRED,
        FrontDeskStatus.FAILED_CLOSED,
    },
    FrontDeskStatus.APPROVED: {FrontDeskStatus.FROZEN, FrontDeskStatus.FAILED_CLOSED},
    FrontDeskStatus.FROZEN: {FrontDeskStatus.HANDED_OFF},
    FrontDeskStatus.HANDED_OFF: set(),
    FrontDeskStatus.HUMAN_REVIEW_REQUIRED: {FrontDeskStatus.ELICITING, FrontDeskStatus.FAILED_CLOSED},
    FrontDeskStatus.UNSUPPORTED: {FrontDeskStatus.ELICITING, FrontDeskStatus.FAILED_CLOSED},
    FrontDeskStatus.FAILED_CLOSED: set(),
}


@dataclass(frozen=True)
class FrontDeskAuthoringSession:
    """Refs-only FrontDesk authoring state."""

    session_id: str
    status: FrontDeskStatus = FrontDeskStatus.NEW
    session_ref: str = SESSION_REF
    conversation_ref: str = CONVERSATION_REF
    sanitized_sources_ref: str = SANITIZED_SOURCES_REF
    semantic_lock_ref: str = SEMANTIC_LOCK_REF
    mission_brief_ref: str = MISSION_BRIEF_REF
    profile_recommendations_ref: str = PROFILE_RECOMMENDATIONS_REF
    mission_plan_ref: str = MISSION_PLAN_REF
    draft_mission_ref: str = DRAFT_MISSION_REF
    product_inquiry_profile_ref: str = PRODUCT_INQUIRY_PROFILE_REF
    intent_bundle_ref: str = INTENT_BUNDLE_REF
    mission_audit_ref: str = MISSION_AUDIT_REF
    authoring_approval_ref: str = AUTHORING_APPROVAL_REF
    freeze_manifest_ref: str = FREEZE_MANIFEST_REF
    mission_ir_ref: str = ""
    frozen_contract_ref: str = ""
    contract_hash: str = ""
    next_action: str = "elicit"
    warnings: list[str] = field(default_factory=list)
    schema_version: str = FRONTDESK_SESSION_SCHEMA_VERSION

    @classmethod
    def new(cls, session_id: str) -> "FrontDeskAuthoringSession":
        session = cls(session_id=require_non_empty_str(session_id, "frontdesk_session.session_id"))
        session.validate()
        return session

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = require_mapping(payload, "frontdesk_session")
        allowed = {
            "schema_version",
            "session_id",
            "status",
            "session_ref",
            "conversation_ref",
            "sanitized_sources_ref",
            "semantic_lock_ref",
            "mission_brief_ref",
            "profile_recommendations_ref",
            "mission_plan_ref",
            "draft_mission_ref",
            "product_inquiry_profile_ref",
            "intent_bundle_ref",
            "mission_audit_ref",
            "authoring_approval_ref",
            "freeze_manifest_ref",
            "mission_ir_ref",
            "frozen_contract_ref",
            "contract_hash",
            "next_action",
            "warnings",
        }
        extra = sorted(set(data) - allowed)
        if extra:
            raise ContractValidationError(f"frontdesk_session contains unknown field(s): {', '.join(extra)}")
        session = cls(
            session_id=require_non_empty_str(data.get("session_id"), "frontdesk_session.session_id"),
            status=FrontDeskStatus(data.get("status", FrontDeskStatus.NEW.value)),
            session_ref=validate_ref(data.get("session_ref", SESSION_REF), "frontdesk_session.session_ref"),
            conversation_ref=validate_ref(
                data.get("conversation_ref", CONVERSATION_REF),
                "frontdesk_session.conversation_ref",
            ),
            sanitized_sources_ref=validate_ref(
                data.get("sanitized_sources_ref", SANITIZED_SOURCES_REF),
                "frontdesk_session.sanitized_sources_ref",
            ),
            semantic_lock_ref=validate_ref(
                data.get("semantic_lock_ref", SEMANTIC_LOCK_REF),
                "frontdesk_session.semantic_lock_ref",
            ),
            mission_brief_ref=validate_ref(
                data.get("mission_brief_ref", MISSION_BRIEF_REF),
                "frontdesk_session.mission_brief_ref",
            ),
            profile_recommendations_ref=validate_ref(
                data.get("profile_recommendations_ref", PROFILE_RECOMMENDATIONS_REF),
                "frontdesk_session.profile_recommendations_ref",
            ),
            mission_plan_ref=validate_ref(
                data.get("mission_plan_ref", MISSION_PLAN_REF),
                "frontdesk_session.mission_plan_ref",
            ),
            draft_mission_ref=validate_ref(
                data.get("draft_mission_ref", DRAFT_MISSION_REF),
                "frontdesk_session.draft_mission_ref",
            ),
            product_inquiry_profile_ref=validate_ref(
                data.get("product_inquiry_profile_ref", PRODUCT_INQUIRY_PROFILE_REF),
                "frontdesk_session.product_inquiry_profile_ref",
            ),
            intent_bundle_ref=validate_ref(
                data.get("intent_bundle_ref", INTENT_BUNDLE_REF),
                "frontdesk_session.intent_bundle_ref",
            ),
            mission_audit_ref=validate_ref(
                data.get("mission_audit_ref", MISSION_AUDIT_REF),
                "frontdesk_session.mission_audit_ref",
            ),
            authoring_approval_ref=validate_ref(
                data.get("authoring_approval_ref", AUTHORING_APPROVAL_REF),
                "frontdesk_session.authoring_approval_ref",
            ),
            freeze_manifest_ref=validate_ref(
                data.get("freeze_manifest_ref", FREEZE_MANIFEST_REF),
                "frontdesk_session.freeze_manifest_ref",
            ),
            mission_ir_ref=str(data.get("mission_ir_ref", "")),
            frozen_contract_ref=str(data.get("frozen_contract_ref", "")),
            contract_hash=str(data.get("contract_hash", "")),
            next_action=require_non_empty_str(data.get("next_action", "elicit"), "frontdesk_session.next_action"),
            warnings=require_str_list(data.get("warnings", []), "frontdesk_session.warnings"),
            schema_version=require_non_empty_str(
                data.get("schema_version", FRONTDESK_SESSION_SCHEMA_VERSION),
                "frontdesk_session.schema_version",
            ),
        )
        session.validate()
        return session

    def transition(self, status: FrontDeskStatus | str, *, next_action: str | None = None) -> "FrontDeskAuthoringSession":
        target = FrontDeskStatus(status)
        if target != self.status and target not in ALLOWED_TRANSITIONS[self.status]:
            raise ContractValidationError(f"invalid FrontDesk transition: {self.status.value} -> {target.value}")
        updated = FrontDeskAuthoringSession(
            session_id=self.session_id,
            status=target,
            session_ref=self.session_ref,
            conversation_ref=self.conversation_ref,
            sanitized_sources_ref=self.sanitized_sources_ref,
            semantic_lock_ref=self.semantic_lock_ref,
            mission_brief_ref=self.mission_brief_ref,
            profile_recommendations_ref=self.profile_recommendations_ref,
            mission_plan_ref=self.mission_plan_ref,
            draft_mission_ref=self.draft_mission_ref,
            product_inquiry_profile_ref=self.product_inquiry_profile_ref,
            intent_bundle_ref=self.intent_bundle_ref,
            mission_audit_ref=self.mission_audit_ref,
            authoring_approval_ref=self.authoring_approval_ref,
            freeze_manifest_ref=self.freeze_manifest_ref,
            mission_ir_ref=self.mission_ir_ref,
            frozen_contract_ref=self.frozen_contract_ref,
            contract_hash=self.contract_hash,
            next_action=next_action or _default_next_action(target),
            warnings=list(self.warnings),
            schema_version=self.schema_version,
        )
        updated.validate()
        return updated

    def with_freeze(self, *, mission_ir_ref: str, frozen_contract_ref: str, contract_hash: str) -> "FrontDeskAuthoringSession":
        updated = FrontDeskAuthoringSession(
            session_id=self.session_id,
            status=FrontDeskStatus.FROZEN,
            session_ref=self.session_ref,
            conversation_ref=self.conversation_ref,
            sanitized_sources_ref=self.sanitized_sources_ref,
            semantic_lock_ref=self.semantic_lock_ref,
            mission_brief_ref=self.mission_brief_ref,
            profile_recommendations_ref=self.profile_recommendations_ref,
            mission_plan_ref=self.mission_plan_ref,
            draft_mission_ref=self.draft_mission_ref,
            product_inquiry_profile_ref=self.product_inquiry_profile_ref,
            intent_bundle_ref=self.intent_bundle_ref,
            mission_audit_ref=self.mission_audit_ref,
            authoring_approval_ref=self.authoring_approval_ref,
            freeze_manifest_ref=self.freeze_manifest_ref,
            mission_ir_ref=validate_ref(mission_ir_ref, "frontdesk_session.mission_ir_ref"),
            frozen_contract_ref=validate_ref(frozen_contract_ref, "frontdesk_session.frozen_contract_ref"),
            contract_hash=require_non_empty_str(contract_hash, "frontdesk_session.contract_hash"),
            next_action="handoff_task_contract",
            warnings=list(self.warnings),
            schema_version=self.schema_version,
        )
        updated.validate()
        return updated

    def validate(self) -> None:
        if self.schema_version != FRONTDESK_SESSION_SCHEMA_VERSION:
            raise ContractValidationError("frontdesk_session.schema_version is unsupported")
        require_non_empty_str(self.session_id, "frontdesk_session.session_id")
        if not isinstance(self.status, FrontDeskStatus):
            raise ContractValidationError("frontdesk_session.status must be a FrontDeskStatus")
        for name in (
            "session_ref",
            "conversation_ref",
            "sanitized_sources_ref",
            "semantic_lock_ref",
            "mission_brief_ref",
            "profile_recommendations_ref",
            "mission_plan_ref",
            "draft_mission_ref",
            "product_inquiry_profile_ref",
            "intent_bundle_ref",
            "mission_audit_ref",
            "authoring_approval_ref",
            "freeze_manifest_ref",
        ):
            validate_ref(getattr(self, name), f"frontdesk_session.{name}")
        if self.mission_ir_ref:
            validate_ref(self.mission_ir_ref, "frontdesk_session.mission_ir_ref")
        if self.frozen_contract_ref:
            validate_ref(self.frozen_contract_ref, "frontdesk_session.frozen_contract_ref")
        if self.status == FrontDeskStatus.APPROVED:
            validate_ref(self.authoring_approval_ref, "frontdesk_session.authoring_approval_ref")
        if self.status in {FrontDeskStatus.FROZEN, FrontDeskStatus.HANDED_OFF}:
            validate_ref(self.mission_ir_ref, "frontdesk_session.mission_ir_ref")
            validate_ref(self.frozen_contract_ref, "frontdesk_session.frozen_contract_ref")
            if not require_non_empty_str(self.contract_hash, "frontdesk_session.contract_hash").startswith("sha256:"):
                raise ContractValidationError("frontdesk_session.contract_hash must be a sha256 hash")
        require_non_empty_str(self.next_action, "frontdesk_session.next_action")
        require_str_list(self.warnings, "frontdesk_session.warnings")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "status": self.status.value,
            "session_ref": self.session_ref,
            "conversation_ref": self.conversation_ref,
            "sanitized_sources_ref": self.sanitized_sources_ref,
            "semantic_lock_ref": self.semantic_lock_ref,
            "mission_brief_ref": self.mission_brief_ref,
            "profile_recommendations_ref": self.profile_recommendations_ref,
            "mission_plan_ref": self.mission_plan_ref,
            "draft_mission_ref": self.draft_mission_ref,
            "product_inquiry_profile_ref": self.product_inquiry_profile_ref,
            "intent_bundle_ref": self.intent_bundle_ref,
            "mission_audit_ref": self.mission_audit_ref,
            "authoring_approval_ref": self.authoring_approval_ref,
            "freeze_manifest_ref": self.freeze_manifest_ref,
            "mission_ir_ref": self.mission_ir_ref,
            "frozen_contract_ref": self.frozen_contract_ref,
            "contract_hash": self.contract_hash,
            "next_action": self.next_action,
            "warnings": list(self.warnings),
        }


FrontDeskState = FrontDeskAuthoringSession


def _default_next_action(status: FrontDeskStatus) -> str:
    return {
        FrontDeskStatus.NEW: "elicit",
        FrontDeskStatus.ELICITING: "answer",
        FrontDeskStatus.NEEDS_CLARIFICATION: "answer",
        FrontDeskStatus.DRAFT_READY: "audit",
        FrontDeskStatus.AUDIT_REQUIRED: "audit",
        FrontDeskStatus.APPROVAL_REQUIRED: "approve",
        FrontDeskStatus.APPROVED: "freeze",
        FrontDeskStatus.FROZEN: "handoff_task_contract",
        FrontDeskStatus.HANDED_OFF: "inspect_handoff",
        FrontDeskStatus.HUMAN_REVIEW_REQUIRED: "review",
        FrontDeskStatus.UNSUPPORTED: "redesign",
        FrontDeskStatus.FAILED_CLOSED: "inspect_failure",
    }[status]
