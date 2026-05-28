"""Reviewer decision contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import ContractValidationError, require_int_at_least, require_mapping, require_non_empty_str, require_str_list


REVIEW_DECISIONS = {"approved", "needs_changes", "rejected"}


@dataclass(frozen=True)
class ReviewerDecision:
    """Independent reviewer decision bound to a locked contract."""

    reviewer_id: str
    decision: str
    contract_hash: str
    capsule_id: str = ""
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
