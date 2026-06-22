"""LLM-assisted FrontDesk audit boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ContractValidationError, ensure_json_value, require_mapping, require_non_empty_str
from ..freeze import expand_mission
from ..profiles import ProfileRegistry
from .compiler import build_mission_ir
from .elicitor import FrontDeskLLMClient
from .schema import (
    AuditDecision,
    AuthoringApproval,
    MissionAuthoringAudit,
    MissionBrief,
    MissionPlan,
    MissionSemanticLock,
    ProfileRecommendationSet,
    reject_raw_authoring_fields,
)


@dataclass(frozen=True)
class AuditResult:
    """Validated FrontDesk auditor output."""

    session_id: str
    audit: MissionAuthoringAudit

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AuditResult":
        data = require_mapping(payload, "audit_result")
        _reject_unknown(data, {"session_id", "audit"}, "audit_result")
        reject_raw_authoring_fields(data, "audit_result")
        result = cls(
            session_id=require_non_empty_str(data.get("session_id"), "audit_result.session_id"),
            audit=MissionAuthoringAudit.from_dict(require_mapping(data.get("audit"), "audit_result.audit")),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.audit.session_id != self.session_id:
            raise ContractValidationError("audit_result session ids do not match")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"session_id": self.session_id, "audit": self.audit.to_dict()}


class SpecAuditor:
    """Schema-validating auditor wrapper."""

    def __init__(self, *, registry: ProfileRegistry | None = None) -> None:
        self.registry = registry

    def audit(self, *, session_id: str, plan: dict[str, Any], client: FrontDeskLLMClient) -> AuditResult:
        payload = {
            "node": "spec_auditor",
            "session_id": session_id,
            "plan": plan,
            "contract": "Return AuditResult JSON only. Do not approve or freeze.",
        }
        response = ensure_json_value(client.complete_json(payload), "auditor.response")
        return AuditResult.from_dict(require_mapping(response, "auditor.response"))


def deterministic_contract_audit(
    *,
    semantic_lock: MissionSemanticLock,
    mission_brief: MissionBrief,
    profile_recommendations: ProfileRecommendationSet,
    mission_plan: MissionPlan,
    approval: AuthoringApproval,
    registry: ProfileRegistry | None = None,
) -> MissionAuthoringAudit:
    """Audit draft by attempting deterministic MissionIR expansion."""

    try:
        mission = build_mission_ir(
            semantic_lock=semantic_lock,
            mission_brief=mission_brief,
            profile_recommendations=profile_recommendations,
            mission_plan=mission_plan,
            approval=approval,
        )
        expand_mission(mission, registry=registry)
    except Exception as exc:
        return MissionAuthoringAudit(
            session_id=semantic_lock.session_id,
            decision=AuditDecision.FAILED_CLOSED,
            findings=[str(exc)],
        )
    return MissionAuthoringAudit(session_id=semantic_lock.session_id, decision=AuditDecision.APPROVE)


def _reject_unknown(data: dict[str, Any], allowed: set[str], field_name: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
