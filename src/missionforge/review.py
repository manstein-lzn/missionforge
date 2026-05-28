"""Reviewer decision contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


REVIEW_DECISIONS = {"approved", "needs_changes", "rejected"}
REVIEW_PACKET_SCHEMA_VERSION = "missionforge.review_packet.v1"


@dataclass(frozen=True)
class ReviewPacket:
    """Refs-only packet requesting independent review."""

    review_packet_id: str
    mission_run_id: str
    iteration: int
    reason: str
    contract_ref: str
    contract_hash: str
    mission_run_ref: str
    attempt_refs: list[str] = field(default_factory=list)
    verification_refs: list[str] = field(default_factory=list)
    proposal_refs: list[str] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    forbidden_decisions: list[str] = field(default_factory=list)
    schema_version: str = REVIEW_PACKET_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReviewPacket":
        data = _strict_mapping(
            payload,
            "review_packet",
            {
                "schema_version",
                "review_packet_id",
                "mission_run_id",
                "iteration",
                "reason",
                "contract_ref",
                "contract_hash",
                "mission_run_ref",
                "attempt_refs",
                "verification_refs",
                "proposal_refs",
                "failed_constraint_ids",
                "questions",
                "forbidden_decisions",
            },
        )
        packet = cls(
            review_packet_id=require_non_empty_str(data.get("review_packet_id"), "review_packet.review_packet_id"),
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "review_packet.mission_run_id"),
            iteration=require_int_at_least(data.get("iteration"), "review_packet.iteration", 1),
            reason=require_non_empty_str(data.get("reason"), "review_packet.reason"),
            contract_ref=validate_ref(data.get("contract_ref"), "review_packet.contract_ref"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "review_packet.contract_hash"),
            mission_run_ref=validate_ref(data.get("mission_run_ref"), "review_packet.mission_run_ref"),
            attempt_refs=require_str_list(data.get("attempt_refs", []), "review_packet.attempt_refs"),
            verification_refs=require_str_list(data.get("verification_refs", []), "review_packet.verification_refs"),
            proposal_refs=require_str_list(data.get("proposal_refs", []), "review_packet.proposal_refs"),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "review_packet.failed_constraint_ids",
            ),
            questions=require_str_list(data.get("questions", []), "review_packet.questions"),
            forbidden_decisions=require_str_list(
                data.get("forbidden_decisions", []),
                "review_packet.forbidden_decisions",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", REVIEW_PACKET_SCHEMA_VERSION),
                "review_packet.schema_version",
            ),
        )
        packet.validate()
        return packet

    def validate(self) -> None:
        if self.schema_version != REVIEW_PACKET_SCHEMA_VERSION:
            raise ContractValidationError("review_packet.schema_version is unsupported")
        require_non_empty_str(self.review_packet_id, "review_packet.review_packet_id")
        require_non_empty_str(self.mission_run_id, "review_packet.mission_run_id")
        require_int_at_least(self.iteration, "review_packet.iteration", 1)
        require_non_empty_str(self.reason, "review_packet.reason")
        validate_ref(self.contract_ref, "review_packet.contract_ref")
        require_non_empty_str(self.contract_hash, "review_packet.contract_hash")
        validate_ref(self.mission_run_ref, "review_packet.mission_run_ref")
        for ref in self.attempt_refs:
            validate_ref(ref, "review_packet.attempt_refs[]")
        for ref in self.verification_refs:
            validate_ref(ref, "review_packet.verification_refs[]")
        for ref in self.proposal_refs:
            validate_ref(ref, "review_packet.proposal_refs[]")
        require_str_list(self.failed_constraint_ids, "review_packet.failed_constraint_ids")
        require_str_list(self.questions, "review_packet.questions")
        require_str_list(self.forbidden_decisions, "review_packet.forbidden_decisions")
        assert_refs_only_payload(self.to_dict_without_validation(), "review_packet")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "review_packet_id": self.review_packet_id,
            "mission_run_id": self.mission_run_id,
            "iteration": self.iteration,
            "reason": self.reason,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "mission_run_ref": self.mission_run_ref,
            "attempt_refs": list(self.attempt_refs),
            "verification_refs": list(self.verification_refs),
            "proposal_refs": list(self.proposal_refs),
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "questions": list(self.questions),
            "forbidden_decisions": list(self.forbidden_decisions),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class ReviewerDecision:
    """Independent reviewer decision bound to a locked contract."""

    reviewer_id: str
    decision: str
    contract_hash: str
    capsule_id: str = "unbound"
    capsule_revision: int = 1
    author_role: str = "reviewer"
    evidence_refs: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReviewerDecision":
        data = require_mapping(payload, "reviewer_decision")
        decision = cls(
            reviewer_id=require_non_empty_str(data.get("reviewer_id"), "reviewer_decision.reviewer_id"),
            decision=require_non_empty_str(data.get("decision"), "reviewer_decision.decision"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "reviewer_decision.contract_hash"),
            capsule_id=require_non_empty_str(data.get("capsule_id", "unbound"), "reviewer_decision.capsule_id"),
            capsule_revision=require_int_at_least(
                data.get("capsule_revision", 1),
                "reviewer_decision.capsule_revision",
                1,
            ),
            author_role=require_non_empty_str(data.get("author_role", "reviewer"), "reviewer_decision.author_role"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "reviewer_decision.evidence_refs"),
            notes=data.get("notes", ""),
        )
        decision.validate()
        return decision

    def validate(self) -> None:
        require_non_empty_str(self.reviewer_id, "reviewer_decision.reviewer_id")
        require_non_empty_str(self.contract_hash, "reviewer_decision.contract_hash")
        require_non_empty_str(self.capsule_id, "reviewer_decision.capsule_id")
        require_int_at_least(self.capsule_revision, "reviewer_decision.capsule_revision", 1)
        if self.decision not in REVIEW_DECISIONS:
            raise ContractValidationError(f"reviewer_decision.decision must be one of {sorted(REVIEW_DECISIONS)}")
        role = require_non_empty_str(self.author_role, "reviewer_decision.author_role")
        if role == "worker":
            raise ContractValidationError("worker-authored reviewer decisions are not accepted")
        require_str_list(self.evidence_refs, "reviewer_decision.evidence_refs")
        if self.notes:
            require_non_empty_str(self.notes, "reviewer_decision.notes")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "reviewer_id": self.reviewer_id,
            "decision": self.decision,
            "contract_hash": self.contract_hash,
            "capsule_id": self.capsule_id,
            "capsule_revision": self.capsule_revision,
            "author_role": self.author_role,
            "evidence_refs": list(self.evidence_refs),
            "notes": self.notes,
        }

    def validate_current(
        self,
        *,
        contract_hash: str,
        capsule_id: str | None = None,
        capsule_revision: int | None = None,
    ) -> None:
        """Fail if the decision is not current for the locked contract."""

        self.validate()
        if self.contract_hash != require_non_empty_str(contract_hash, "contract_hash"):
            raise ContractValidationError("reviewer decision is stale for contract_hash")
        if capsule_id is not None and self.capsule_id != require_non_empty_str(capsule_id, "capsule_id"):
            raise ContractValidationError("reviewer decision is stale for capsule_id")
        if capsule_revision is not None and self.capsule_revision != require_int_at_least(
            capsule_revision,
            "capsule_revision",
            1,
        ):
            raise ContractValidationError("reviewer decision is stale for capsule_revision")
        if self.decision != "approved":
            raise ContractValidationError(f"reviewer decision is not approved: {self.decision}")


def _strict_mapping(payload: Mapping[str, Any], field_name: str, allowed_keys: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    assert_refs_only_payload(data, field_name)
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unsupported fields: {unknown}")
    return data
