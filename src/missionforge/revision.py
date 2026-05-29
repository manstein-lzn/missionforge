"""Mission revision contracts and conservative workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import (
    AuthorityRequirement,
    ContractAdjustmentChange,
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from .freeze import FrozenMissionContract, freeze_mission
from .ir import MissionIR
from .review import ReviewerDecision
from .steering import ContractAdjustmentRequest, HARNESS_AUTHORIZED_ADJUSTMENTS


MISSION_REVISION_REQUEST_SCHEMA_VERSION = "missionforge.mission_revision_request.v1"
MISSION_REVISION_DECISION_SCHEMA_VERSION = "missionforge.mission_revision_decision.v1"
MISSION_REVISION_SCHEMA_VERSION = "missionforge.mission_revision.v1"
REVISION_DECISIONS = {"approved", "rejected", "needs_review", "human_authority_required", "redesign_required"}


@dataclass(frozen=True)
class MissionRevisionRequest:
    """Request to create a new frozen mission contract version."""

    revision_id: str
    mission_run_id: str
    base_contract_ref: str
    base_contract_hash: str
    request_ref: str
    requested_change: ContractAdjustmentChange
    authority_required: AuthorityRequirement
    evidence_refs: list[str] = field(default_factory=list)
    proposal_refs: list[str] = field(default_factory=list)
    reason: str = ""
    risk_if_rejected: str = ""
    schema_version: str = MISSION_REVISION_REQUEST_SCHEMA_VERSION

    @classmethod
    def from_adjustment(
        cls,
        adjustment: ContractAdjustmentRequest,
        *,
        base_contract_ref: str,
        base_contract_hash: str,
        request_ref: str,
        revision_id: str | None = None,
    ) -> "MissionRevisionRequest":
        adjustment.validate()
        request = cls(
            revision_id=revision_id or f"revision-{adjustment.iteration:06d}",
            mission_run_id=adjustment.mission_run_id,
            base_contract_ref=base_contract_ref,
            base_contract_hash=base_contract_hash,
            request_ref=request_ref,
            requested_change=adjustment.requested_change,
            authority_required=adjustment.authority_required,
            evidence_refs=list(adjustment.evidence_refs),
            proposal_refs=list(adjustment.proposed_contract_refs),
            reason=adjustment.reason,
            risk_if_rejected=adjustment.risk_if_rejected,
        )
        request.validate()
        return request

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionRevisionRequest":
        data = _strict_mapping(
            payload,
            "mission_revision_request",
            {
                "schema_version",
                "revision_id",
                "mission_run_id",
                "base_contract_ref",
                "base_contract_hash",
                "request_ref",
                "requested_change",
                "authority_required",
                "evidence_refs",
                "proposal_refs",
                "reason",
                "risk_if_rejected",
            },
        )
        request = cls(
            revision_id=require_non_empty_str(data.get("revision_id"), "mission_revision_request.revision_id"),
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "mission_revision_request.mission_run_id"),
            base_contract_ref=validate_ref(data.get("base_contract_ref"), "mission_revision_request.base_contract_ref"),
            base_contract_hash=require_non_empty_str(
                data.get("base_contract_hash"),
                "mission_revision_request.base_contract_hash",
            ),
            request_ref=validate_ref(data.get("request_ref"), "mission_revision_request.request_ref"),
            requested_change=require_enum(
                data.get("requested_change"),
                ContractAdjustmentChange,
                "mission_revision_request.requested_change",
            ),
            authority_required=require_enum(
                data.get("authority_required"),
                AuthorityRequirement,
                "mission_revision_request.authority_required",
            ),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_revision_request.evidence_refs"),
            proposal_refs=require_str_list(data.get("proposal_refs", []), "mission_revision_request.proposal_refs"),
            reason=data.get("reason", ""),
            risk_if_rejected=data.get("risk_if_rejected", ""),
            schema_version=require_non_empty_str(
                data.get("schema_version", MISSION_REVISION_REQUEST_SCHEMA_VERSION),
                "mission_revision_request.schema_version",
            ),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if self.schema_version != MISSION_REVISION_REQUEST_SCHEMA_VERSION:
            raise ContractValidationError("mission_revision_request.schema_version is unsupported")
        require_non_empty_str(self.revision_id, "mission_revision_request.revision_id")
        require_non_empty_str(self.mission_run_id, "mission_revision_request.mission_run_id")
        validate_ref(self.base_contract_ref, "mission_revision_request.base_contract_ref")
        require_non_empty_str(self.base_contract_hash, "mission_revision_request.base_contract_hash")
        validate_ref(self.request_ref, "mission_revision_request.request_ref")
        require_enum(self.requested_change, ContractAdjustmentChange, "mission_revision_request.requested_change")
        require_enum(self.authority_required, AuthorityRequirement, "mission_revision_request.authority_required")
        for ref in self.evidence_refs:
            validate_ref(ref, "mission_revision_request.evidence_refs[]")
        for ref in self.proposal_refs:
            validate_ref(ref, "mission_revision_request.proposal_refs[]")
        if self.reason:
            require_non_empty_str(self.reason, "mission_revision_request.reason")
        if self.risk_if_rejected:
            require_non_empty_str(self.risk_if_rejected, "mission_revision_request.risk_if_rejected")
        if self.requested_change not in HARNESS_AUTHORIZED_ADJUSTMENTS and self.authority_required == AuthorityRequirement.HARNESS:
            raise ContractValidationError("mission_revision_request authority is too weak for requested_change")
        assert_refs_only_payload(self.to_dict_without_validation(), "mission_revision_request")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision_id": self.revision_id,
            "mission_run_id": self.mission_run_id,
            "base_contract_ref": self.base_contract_ref,
            "base_contract_hash": self.base_contract_hash,
            "request_ref": self.request_ref,
            "requested_change": self.requested_change.value,
            "authority_required": self.authority_required.value,
            "evidence_refs": list(self.evidence_refs),
            "proposal_refs": list(self.proposal_refs),
            "reason": self.reason,
            "risk_if_rejected": self.risk_if_rejected,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class MissionRevisionDecision:
    """Authority outcome for a mission revision request."""

    revision_id: str
    mission_run_id: str
    decision: str
    authority_route: str
    reason: str
    reviewer_decision_ref: str = ""
    decided_by: str = "missionforge"
    contract_hash: str = ""
    schema_version: str = MISSION_REVISION_DECISION_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionRevisionDecision":
        data = _strict_mapping(
            payload,
            "mission_revision_decision",
            {
                "schema_version",
                "revision_id",
                "mission_run_id",
                "decision",
                "authority_route",
                "reason",
                "reviewer_decision_ref",
                "decided_by",
                "contract_hash",
            },
        )
        decision = cls(
            revision_id=require_non_empty_str(data.get("revision_id"), "mission_revision_decision.revision_id"),
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "mission_revision_decision.mission_run_id"),
            decision=require_non_empty_str(data.get("decision"), "mission_revision_decision.decision"),
            authority_route=require_non_empty_str(
                data.get("authority_route"),
                "mission_revision_decision.authority_route",
            ),
            reason=require_non_empty_str(data.get("reason"), "mission_revision_decision.reason"),
            reviewer_decision_ref=data.get("reviewer_decision_ref", ""),
            decided_by=require_non_empty_str(data.get("decided_by", "missionforge"), "mission_revision_decision.decided_by"),
            contract_hash=data.get("contract_hash", ""),
            schema_version=require_non_empty_str(
                data.get("schema_version", MISSION_REVISION_DECISION_SCHEMA_VERSION),
                "mission_revision_decision.schema_version",
            ),
        )
        decision.validate()
        return decision

    def validate(self) -> None:
        if self.schema_version != MISSION_REVISION_DECISION_SCHEMA_VERSION:
            raise ContractValidationError("mission_revision_decision.schema_version is unsupported")
        require_non_empty_str(self.revision_id, "mission_revision_decision.revision_id")
        require_non_empty_str(self.mission_run_id, "mission_revision_decision.mission_run_id")
        if self.decision not in REVISION_DECISIONS:
            raise ContractValidationError(f"mission_revision_decision.decision must be one of {sorted(REVISION_DECISIONS)}")
        require_non_empty_str(self.authority_route, "mission_revision_decision.authority_route")
        require_non_empty_str(self.reason, "mission_revision_decision.reason")
        if self.reviewer_decision_ref:
            validate_ref(self.reviewer_decision_ref, "mission_revision_decision.reviewer_decision_ref")
        require_non_empty_str(self.decided_by, "mission_revision_decision.decided_by")
        if self.contract_hash:
            require_non_empty_str(self.contract_hash, "mission_revision_decision.contract_hash")
        assert_refs_only_payload(self.to_dict_without_validation(), "mission_revision_decision")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision_id": self.revision_id,
            "mission_run_id": self.mission_run_id,
            "decision": self.decision,
            "authority_route": self.authority_route,
            "reason": self.reason,
            "reviewer_decision_ref": self.reviewer_decision_ref,
            "decided_by": self.decided_by,
            "contract_hash": self.contract_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class MissionRevision:
    """Durable mission contract transition record."""

    revision_id: str
    mission_run_id: str
    old_contract_ref: str
    old_contract_hash: str
    new_contract_ref: str
    new_contract_hash: str
    revision_request_ref: str
    revision_decision_ref: str
    new_mission_ref: str = ""
    changed_fields: list[str] = field(default_factory=list)
    carried_evidence_refs: list[str] = field(default_factory=list)
    invalidated_refs: list[str] = field(default_factory=list)
    next_runtime_route: str = "resume"
    schema_version: str = MISSION_REVISION_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionRevision":
        data = _strict_mapping(
            payload,
            "mission_revision",
            {
                "schema_version",
                "revision_id",
                "mission_run_id",
                "old_contract_ref",
                "old_contract_hash",
                "new_contract_ref",
                "new_contract_hash",
                "revision_request_ref",
                "revision_decision_ref",
                "new_mission_ref",
                "changed_fields",
                "carried_evidence_refs",
                "invalidated_refs",
                "next_runtime_route",
            },
        )
        revision = cls(
            revision_id=require_non_empty_str(data.get("revision_id"), "mission_revision.revision_id"),
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "mission_revision.mission_run_id"),
            old_contract_ref=validate_ref(data.get("old_contract_ref"), "mission_revision.old_contract_ref"),
            old_contract_hash=require_non_empty_str(data.get("old_contract_hash"), "mission_revision.old_contract_hash"),
            new_contract_ref=validate_ref(data.get("new_contract_ref"), "mission_revision.new_contract_ref"),
            new_contract_hash=require_non_empty_str(data.get("new_contract_hash"), "mission_revision.new_contract_hash"),
            revision_request_ref=validate_ref(data.get("revision_request_ref"), "mission_revision.revision_request_ref"),
            revision_decision_ref=validate_ref(data.get("revision_decision_ref"), "mission_revision.revision_decision_ref"),
            new_mission_ref=data.get("new_mission_ref", ""),
            changed_fields=require_str_list(data.get("changed_fields", []), "mission_revision.changed_fields"),
            carried_evidence_refs=require_str_list(
                data.get("carried_evidence_refs", []),
                "mission_revision.carried_evidence_refs",
            ),
            invalidated_refs=require_str_list(data.get("invalidated_refs", []), "mission_revision.invalidated_refs"),
            next_runtime_route=require_non_empty_str(data.get("next_runtime_route", "resume"), "mission_revision.next_runtime_route"),
            schema_version=require_non_empty_str(
                data.get("schema_version", MISSION_REVISION_SCHEMA_VERSION),
                "mission_revision.schema_version",
            ),
        )
        revision.validate()
        return revision

    def validate(self) -> None:
        if self.schema_version != MISSION_REVISION_SCHEMA_VERSION:
            raise ContractValidationError("mission_revision.schema_version is unsupported")
        require_non_empty_str(self.revision_id, "mission_revision.revision_id")
        require_non_empty_str(self.mission_run_id, "mission_revision.mission_run_id")
        for field_name in ("old_contract_ref", "new_contract_ref", "revision_request_ref", "revision_decision_ref"):
            validate_ref(getattr(self, field_name), f"mission_revision.{field_name}")
        if self.new_mission_ref:
            validate_ref(self.new_mission_ref, "mission_revision.new_mission_ref")
        require_non_empty_str(self.old_contract_hash, "mission_revision.old_contract_hash")
        require_non_empty_str(self.new_contract_hash, "mission_revision.new_contract_hash")
        if self.old_contract_hash == self.new_contract_hash:
            raise ContractValidationError("mission_revision requires a changed frozen contract hash")
        require_str_list(self.changed_fields, "mission_revision.changed_fields")
        for ref in self.carried_evidence_refs:
            validate_ref(ref, "mission_revision.carried_evidence_refs[]")
        for ref in self.invalidated_refs:
            validate_ref(ref, "mission_revision.invalidated_refs[]")
        require_non_empty_str(self.next_runtime_route, "mission_revision.next_runtime_route")
        assert_refs_only_payload(self.to_dict_without_validation(), "mission_revision")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision_id": self.revision_id,
            "mission_run_id": self.mission_run_id,
            "old_contract_ref": self.old_contract_ref,
            "old_contract_hash": self.old_contract_hash,
            "new_contract_ref": self.new_contract_ref,
            "new_contract_hash": self.new_contract_hash,
            "revision_request_ref": self.revision_request_ref,
            "revision_decision_ref": self.revision_decision_ref,
            "new_mission_ref": self.new_mission_ref,
            "changed_fields": list(self.changed_fields),
            "carried_evidence_refs": list(self.carried_evidence_refs),
            "invalidated_refs": list(self.invalidated_refs),
            "next_runtime_route": self.next_runtime_route,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class MissionRevisionWorkflow:
    """Conservative contract adjustment workflow."""

    def decide(
        self,
        request: MissionRevisionRequest,
        *,
        reviewer_decision: ReviewerDecision | None = None,
        reviewer_decision_ref: str = "",
    ) -> MissionRevisionDecision:
        request.validate()
        route = _authority_route(request)
        if route == "harness_authorized":
            return MissionRevisionDecision(
                revision_id=request.revision_id,
                mission_run_id=request.mission_run_id,
                decision="approved",
                authority_route=route,
                reason="Harness-authorized conservative revision.",
                contract_hash=request.base_contract_hash,
            )
        if route == "human_authority_required":
            return MissionRevisionDecision(
                revision_id=request.revision_id,
                mission_run_id=request.mission_run_id,
                decision="human_authority_required",
                authority_route=route,
                reason="Revision requires user-reserved human authority.",
                contract_hash=request.base_contract_hash,
            )
        if route == "redesign_required":
            return MissionRevisionDecision(
                revision_id=request.revision_id,
                mission_run_id=request.mission_run_id,
                decision="redesign_required",
                authority_route=route,
                reason="Revision requires redesign before a new contract can be frozen.",
                contract_hash=request.base_contract_hash,
            )
        if reviewer_decision is None:
            return MissionRevisionDecision(
                revision_id=request.revision_id,
                mission_run_id=request.mission_run_id,
                decision="needs_review",
                authority_route=route,
                reason="Revision requires reviewer approval.",
                contract_hash=request.base_contract_hash,
            )
        reviewer_decision.validate_current(contract_hash=request.base_contract_hash)
        return MissionRevisionDecision(
            revision_id=request.revision_id,
            mission_run_id=request.mission_run_id,
            decision="approved",
            authority_route=route,
            reason="Reviewer approved revision for current contract hash.",
            reviewer_decision_ref=reviewer_decision_ref,
            decided_by=reviewer_decision.reviewer_id,
            contract_hash=request.base_contract_hash,
        )

    def apply(
        self,
        mission: MissionIR,
        request: MissionRevisionRequest,
        decision: MissionRevisionDecision,
        *,
        old_contract: FrozenMissionContract,
        new_contract_ref: str,
        decision_ref: str,
        new_mission_ref: str = "",
    ) -> tuple[MissionIR, FrozenMissionContract, MissionRevision]:
        mission.validate()
        request.validate()
        decision.validate()
        if decision.decision != "approved":
            raise ContractValidationError("mission revision cannot apply without approved decision")
        if request.base_contract_hash != old_contract.contract_hash:
            raise ContractValidationError("mission revision request is stale for base contract hash")
        if decision.contract_hash and decision.contract_hash != old_contract.contract_hash:
            raise ContractValidationError("mission revision decision is stale for base contract hash")
        revised_mission, changed_fields = apply_conservative_revision(mission, request)
        new_contract = freeze_mission(revised_mission)
        revision = MissionRevision(
            revision_id=request.revision_id,
            mission_run_id=request.mission_run_id,
            old_contract_ref=request.base_contract_ref,
            old_contract_hash=old_contract.contract_hash,
            new_contract_ref=new_contract_ref,
            new_contract_hash=new_contract.contract_hash,
            revision_request_ref=request.request_ref,
            revision_decision_ref=decision_ref,
            new_mission_ref=new_mission_ref,
            changed_fields=changed_fields,
            carried_evidence_refs=list(request.evidence_refs),
            invalidated_refs=[],
            next_runtime_route="resume",
        )
        revision.validate()
        return revised_mission, new_contract, revision


def apply_conservative_revision(mission: MissionIR, request: MissionRevisionRequest) -> tuple[MissionIR, list[str]]:
    """Apply only non-expanding revision metadata to MissionIR."""

    if request.requested_change not in {
        ContractAdjustmentChange.SHRINK,
        ContractAdjustmentChange.SPLIT,
        ContractAdjustmentChange.REORDER,
        ContractAdjustmentChange.REVIEW_REQUIRED,
    }:
        raise ContractValidationError("unsupported mission revision change fails closed")
    payload = mission.to_dict()
    outputs = dict(payload.get("outputs", {}))
    outputs["mission_revision"] = {
        "revision_id": request.revision_id,
        "requested_change": request.requested_change.value,
        "request_ref": request.request_ref,
    }
    payload["outputs"] = outputs
    repair_policy = dict(payload.get("repair_policy", {}))
    revision_history = list(repair_policy.get("mission_revisions", []))
    revision_history.append(
        {
            "revision_id": request.revision_id,
            "requested_change": request.requested_change.value,
            "request_ref": request.request_ref,
            "reason": request.reason,
        }
    )
    repair_policy["mission_revisions"] = ensure_json_value(revision_history, "mission_revision.repair_policy")
    payload["repair_policy"] = repair_policy
    changed_fields = ["outputs.mission_revision", "repair_policy.mission_revisions"]
    if request.requested_change == ContractAdjustmentChange.REVIEW_REQUIRED:
        verification = dict(payload.get("verification", {}))
        manual_gates = list(verification.get("manual_gates", []))
        gate_id = f"revision:{request.revision_id}"
        if gate_id not in manual_gates:
            manual_gates.append(gate_id)
        verification["manual_gates"] = manual_gates
        payload["verification"] = verification
        changed_fields.append("verification.manual_gates")
    revised = MissionIR.from_dict(payload)
    return revised, changed_fields


def _authority_route(request: MissionRevisionRequest) -> str:
    if request.requested_change in HARNESS_AUTHORIZED_ADJUSTMENTS:
        return "harness_authorized"
    if request.authority_required == AuthorityRequirement.HUMAN:
        return "human_authority_required"
    if request.authority_required == AuthorityRequirement.REDESIGN:
        return "redesign_required"
    return "review_required"


def _strict_mapping(payload: Mapping[str, Any], field_name: str, allowed_keys: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    assert_refs_only_payload(data, field_name)
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unsupported fields: {unknown}")
    return data
