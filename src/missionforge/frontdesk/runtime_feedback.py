"""FrontDesk runtime feedback interpretation.

This module is not a runtime inner loop. It converts refs-only runtime and
verification outcomes into authoring guidance while existing revision authority
keeps ownership of frozen-contract changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from ..contracts import (
    AuthorityRequirement,
    ContractAdjustmentChange,
    ContractValidationError,
    VerificationStatus,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from ..revision import MissionRevisionRequest
from ..runner import MissionResult
from ..verification import VerificationResult


RUNTIME_FEEDBACK_SCHEMA_VERSION = "missionforge.frontdesk_runtime_feedback.v1"


class RuntimeFeedbackSourceKind(StrEnum):
    """Runtime feedback source interpreted by FrontDesk."""

    MISSION_RESULT = "mission_result"
    VERIFICATION_RESULT = "verification_result"
    VERIFIER_FAILURE = "verifier_failure"
    CONTRACT_MISMATCH = "contract_mismatch"
    UNSUPPORTED_VALIDATOR = "unsupported_validator"
    REVISION_DIAGNOSIS = "revision_diagnosis"


class RuntimeFeedbackAction(StrEnum):
    """Next authoring action recommended by FrontDesk."""

    REPAIR = "repair"
    RESUME = "resume"
    MISSION_REVISION = "mission_revision"
    REDESIGN = "redesign"
    PROFILE_EXTENSION = "profile_extension"
    VALIDATOR_EXTENSION = "validator_extension"
    HUMAN_REVIEW = "human_review"
    STOP = "stop"


@dataclass(frozen=True)
class RuntimeFeedbackRecommendation:
    """Refs-only recommendation for a runtime outcome."""

    session_id: str
    source_kind: RuntimeFeedbackSourceKind
    recommended_action: RuntimeFeedbackAction
    reason: str
    authority_required: AuthorityRequirement
    source_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    proposal_refs: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    can_auto_approve_revision: bool = False
    schema_version: str = RUNTIME_FEEDBACK_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeFeedbackRecommendation":
        data = _strict_mapping(
            payload,
            "frontdesk_runtime_feedback",
            {
                "schema_version",
                "session_id",
                "source_kind",
                "recommended_action",
                "reason",
                "authority_required",
                "source_refs",
                "evidence_refs",
                "proposal_refs",
                "next_steps",
                "can_auto_approve_revision",
            },
        )
        recommendation = cls(
            session_id=require_non_empty_str(data.get("session_id"), "frontdesk_runtime_feedback.session_id"),
            source_kind=require_enum(
                data.get("source_kind"),
                RuntimeFeedbackSourceKind,
                "frontdesk_runtime_feedback.source_kind",
            ),
            recommended_action=require_enum(
                data.get("recommended_action"),
                RuntimeFeedbackAction,
                "frontdesk_runtime_feedback.recommended_action",
            ),
            reason=require_non_empty_str(data.get("reason"), "frontdesk_runtime_feedback.reason"),
            authority_required=require_enum(
                data.get("authority_required"),
                AuthorityRequirement,
                "frontdesk_runtime_feedback.authority_required",
            ),
            source_refs=require_str_list(data.get("source_refs", []), "frontdesk_runtime_feedback.source_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "frontdesk_runtime_feedback.evidence_refs"),
            proposal_refs=require_str_list(data.get("proposal_refs", []), "frontdesk_runtime_feedback.proposal_refs"),
            next_steps=require_str_list(data.get("next_steps", []), "frontdesk_runtime_feedback.next_steps"),
            can_auto_approve_revision=data.get("can_auto_approve_revision", False),
            schema_version=require_non_empty_str(
                data.get("schema_version", RUNTIME_FEEDBACK_SCHEMA_VERSION),
                "frontdesk_runtime_feedback.schema_version",
            ),
        )
        recommendation.validate()
        return recommendation

    def validate(self) -> None:
        if self.schema_version != RUNTIME_FEEDBACK_SCHEMA_VERSION:
            raise ContractValidationError("frontdesk_runtime_feedback.schema_version is unsupported")
        require_non_empty_str(self.session_id, "frontdesk_runtime_feedback.session_id")
        require_enum(self.source_kind, RuntimeFeedbackSourceKind, "frontdesk_runtime_feedback.source_kind")
        require_enum(self.recommended_action, RuntimeFeedbackAction, "frontdesk_runtime_feedback.recommended_action")
        require_non_empty_str(self.reason, "frontdesk_runtime_feedback.reason")
        require_enum(self.authority_required, AuthorityRequirement, "frontdesk_runtime_feedback.authority_required")
        for ref in self.source_refs:
            validate_ref(ref, "frontdesk_runtime_feedback.source_refs[]")
        for ref in self.evidence_refs:
            validate_ref(ref, "frontdesk_runtime_feedback.evidence_refs[]")
        for ref in self.proposal_refs:
            validate_ref(ref, "frontdesk_runtime_feedback.proposal_refs[]")
        require_str_list(self.next_steps, "frontdesk_runtime_feedback.next_steps")
        if not isinstance(self.can_auto_approve_revision, bool):
            raise ContractValidationError("frontdesk_runtime_feedback.can_auto_approve_revision must be a boolean")
        if self.can_auto_approve_revision:
            raise ContractValidationError("frontdesk_runtime_feedback cannot auto-approve revisions")
        if (
            self.recommended_action == RuntimeFeedbackAction.MISSION_REVISION
            and self.authority_required == AuthorityRequirement.HARNESS
        ):
            raise ContractValidationError("mission revision feedback requires reviewer, human, or redesign authority")
        if (
            self.recommended_action == RuntimeFeedbackAction.HUMAN_REVIEW
            and self.authority_required != AuthorityRequirement.HUMAN
        ):
            raise ContractValidationError("human review feedback requires human authority")
        assert_refs_only_payload(self.to_dict_without_validation(), "frontdesk_runtime_feedback")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "source_kind": self.source_kind.value,
            "recommended_action": self.recommended_action.value,
            "reason": self.reason,
            "authority_required": self.authority_required.value,
            "source_refs": list(self.source_refs),
            "evidence_refs": list(self.evidence_refs),
            "proposal_refs": list(self.proposal_refs),
            "next_steps": list(self.next_steps),
            "can_auto_approve_revision": self.can_auto_approve_revision,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()

    def draft_revision_request(
        self,
        *,
        mission_run_id: str,
        base_contract_ref: str,
        base_contract_hash: str,
        request_ref: str,
        revision_id: str = "frontdesk-revision-000001",
        requested_change: ContractAdjustmentChange = ContractAdjustmentChange.REVIEW_REQUIRED,
    ) -> MissionRevisionRequest:
        """Draft a revision request without deciding or applying it."""

        self.validate()
        if self.recommended_action != RuntimeFeedbackAction.MISSION_REVISION:
            raise ContractValidationError("frontdesk feedback can draft revisions only for mission_revision guidance")
        return MissionRevisionRequest(
            revision_id=revision_id,
            mission_run_id=require_non_empty_str(mission_run_id, "frontdesk_runtime_feedback.mission_run_id"),
            base_contract_ref=validate_ref(base_contract_ref, "frontdesk_runtime_feedback.base_contract_ref"),
            base_contract_hash=require_non_empty_str(
                base_contract_hash,
                "frontdesk_runtime_feedback.base_contract_hash",
            ),
            request_ref=validate_ref(request_ref, "frontdesk_runtime_feedback.request_ref"),
            requested_change=requested_change,
            authority_required=self.authority_required,
            evidence_refs=list(self.evidence_refs or self.source_refs),
            proposal_refs=list(self.proposal_refs),
            reason=self.reason,
            risk_if_rejected="Runtime feedback indicates the frozen mission contract may not match the observed run.",
        )


def recommend_from_mission_result(
    session_id: str,
    result: MissionResult,
    *,
    source_ref: str = "",
) -> RuntimeFeedbackRecommendation:
    """Interpret a MissionRuntime result into FrontDesk guidance."""

    result.validate()
    source_refs = [source_ref] if source_ref else []
    evidence_refs = list(result.evidence_refs)
    if result.status in {"completed_verified", "completed"}:
        return RuntimeFeedbackRecommendation(
            session_id=session_id,
            source_kind=RuntimeFeedbackSourceKind.MISSION_RESULT,
            recommended_action=RuntimeFeedbackAction.STOP,
            reason="Mission result is complete; no FrontDesk revision is required.",
            authority_required=AuthorityRequirement.HARNESS,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            next_steps=["Archive the freeze manifest and runtime evidence refs."],
        )
    if result.failed_constraint_ids:
        return RuntimeFeedbackRecommendation(
            session_id=session_id,
            source_kind=RuntimeFeedbackSourceKind.MISSION_RESULT,
            recommended_action=RuntimeFeedbackAction.REPAIR,
            reason="Mission result reports failed constraints that should be repaired before revision.",
            authority_required=AuthorityRequirement.HARNESS,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            next_steps=[
                "Inspect failed constraint ids.",
                "Repair artifacts or verifier inputs without changing the frozen contract.",
            ],
        )
    return RuntimeFeedbackRecommendation(
        session_id=session_id,
        source_kind=RuntimeFeedbackSourceKind.MISSION_RESULT,
        recommended_action=RuntimeFeedbackAction.RESUME,
        reason="Mission result is incomplete without a contract mismatch signal.",
        authority_required=AuthorityRequirement.HARNESS,
        source_refs=source_refs,
        evidence_refs=evidence_refs,
        next_steps=["Resume the mission through the normal runtime path."],
    )


def recommend_from_verification_result(
    session_id: str,
    result: VerificationResult,
    *,
    source_ref: str = "",
) -> RuntimeFeedbackRecommendation:
    """Interpret verifier output into FrontDesk guidance."""

    result.validate()
    source_refs = [source_ref] if source_ref else []
    evidence_refs = list(result.evidence_refs)
    if result.status == VerificationStatus.UNSUPPORTED_VERIFICATION_SPEC:
        return unsupported_validator_feedback(
            session_id,
            validator_id=_first_failed_validator_id(result),
            source_ref=source_ref,
            evidence_refs=evidence_refs,
        )
    if result.status == VerificationStatus.HUMAN_ACCEPTANCE_REQUIRED:
        return human_review_feedback(
            session_id,
            reason="Verification requires user-reserved human acceptance.",
            source_refs=source_refs,
            evidence_refs=evidence_refs,
        )
    if result.status == VerificationStatus.REVIEW_REQUIRED:
        return human_review_feedback(
            session_id,
            reason="Verification requires reviewer or human authority before closure.",
            source_refs=source_refs,
            evidence_refs=evidence_refs,
        )
    if result.status == VerificationStatus.INVALID_CONTRACT:
        return contract_mismatch_feedback(
            session_id,
            source_ref=source_ref,
            evidence_refs=evidence_refs,
            reason="Verification reports an invalid contract.",
        )
    if result.status == VerificationStatus.FAILED or result.failed_constraints:
        return RuntimeFeedbackRecommendation(
            session_id=session_id,
            source_kind=RuntimeFeedbackSourceKind.VERIFIER_FAILURE,
            recommended_action=RuntimeFeedbackAction.REPAIR,
            reason="Verifier failure should be repaired under the existing frozen contract.",
            authority_required=AuthorityRequirement.HARNESS,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            next_steps=[
                "Inspect failed validator and missing evidence refs.",
                "Repair artifacts or evidence collection before requesting mission revision.",
            ],
        )
    if result.status == VerificationStatus.COMPLETED_VERIFIED:
        return RuntimeFeedbackRecommendation(
            session_id=session_id,
            source_kind=RuntimeFeedbackSourceKind.VERIFICATION_RESULT,
            recommended_action=RuntimeFeedbackAction.STOP,
            reason="Verification passed; no FrontDesk runtime feedback action is required.",
            authority_required=AuthorityRequirement.HARNESS,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            next_steps=["Keep the verifier result as closure evidence."],
        )
    return RuntimeFeedbackRecommendation(
        session_id=session_id,
        source_kind=RuntimeFeedbackSourceKind.VERIFICATION_RESULT,
        recommended_action=RuntimeFeedbackAction.RESUME,
        reason="Verification is incomplete but does not require mission revision.",
        authority_required=AuthorityRequirement.HARNESS,
        source_refs=source_refs,
        evidence_refs=evidence_refs,
        next_steps=["Resume or retry the runtime through the normal runtime path."],
    )


def contract_mismatch_feedback(
    session_id: str,
    *,
    source_ref: str,
    evidence_refs: list[str] | None = None,
    proposal_refs: list[str] | None = None,
    reason: str = "Runtime evidence does not match the frozen mission contract.",
    authority_required: AuthorityRequirement = AuthorityRequirement.REVIEWER,
) -> RuntimeFeedbackRecommendation:
    """Recommend mission revision for contract mismatch without approving it."""

    return RuntimeFeedbackRecommendation(
        session_id=session_id,
        source_kind=RuntimeFeedbackSourceKind.CONTRACT_MISMATCH,
        recommended_action=RuntimeFeedbackAction.MISSION_REVISION,
        reason=reason,
        authority_required=authority_required,
        source_refs=[source_ref] if source_ref else [],
        evidence_refs=list(evidence_refs or []),
        proposal_refs=list(proposal_refs or []),
        next_steps=[
            "Draft a MissionRevisionRequest as a proposal artifact.",
            "Submit the request to MissionRevisionWorkflow for authority decision.",
        ],
    )


def unsupported_validator_feedback(
    session_id: str,
    *,
    validator_id: str,
    source_ref: str = "",
    evidence_refs: list[str] | None = None,
) -> RuntimeFeedbackRecommendation:
    """Recommend validator/profile extension for unsupported verification."""

    validator_label = require_non_empty_str(validator_id, "frontdesk_runtime_feedback.validator_id")
    return RuntimeFeedbackRecommendation(
        session_id=session_id,
        source_kind=RuntimeFeedbackSourceKind.UNSUPPORTED_VALIDATOR,
        recommended_action=RuntimeFeedbackAction.VALIDATOR_EXTENSION,
        reason=f"Validator {validator_label} is unsupported by the active verification profiles.",
        authority_required=AuthorityRequirement.REDESIGN,
        source_refs=[source_ref] if source_ref else [],
        evidence_refs=list(evidence_refs or []),
        next_steps=[
            "Add or select a verification profile that declares the validator type.",
            "Add an executable validator implementation or redesign the mission verification plan.",
        ],
    )


def human_review_feedback(
    session_id: str,
    *,
    reason: str,
    source_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> RuntimeFeedbackRecommendation:
    """Route user-reserved authority back to a human gate."""

    return RuntimeFeedbackRecommendation(
        session_id=session_id,
        source_kind=RuntimeFeedbackSourceKind.REVISION_DIAGNOSIS,
        recommended_action=RuntimeFeedbackAction.HUMAN_REVIEW,
        reason=reason,
        authority_required=AuthorityRequirement.HUMAN,
        source_refs=list(source_refs or []),
        evidence_refs=list(evidence_refs or []),
        next_steps=["Request explicit human approval or rejection before changing the frozen contract."],
    )


def _first_failed_validator_id(result: VerificationResult) -> str:
    for validator_result in result.validator_results:
        if not validator_result.passed:
            return validator_result.validator_id
    for failed in result.failed_constraints:
        return failed.validator_id
    return "unknown-validator"


def _strict_mapping(payload: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    assert_refs_only_payload(data, field_name)
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
    return data
