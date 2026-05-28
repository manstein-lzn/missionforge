"""Controlled steering contract objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import (
    AdaptiveDecision,
    ContractValidationError,
    EvidenceTrustLevel,
    ProposalValidationStatus,
    require_confidence,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


@dataclass(frozen=True)
class SteeringProposal:
    """Proposal for the next bounded runtime decision."""

    proposal_id: str
    mission_run_id: str
    iteration: int
    input_refs: list[str]
    recommended_route: AdaptiveDecision
    proposed_contract: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    risks: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SteeringProposal":
        data = require_mapping(payload, "steering_proposal")
        proposal = cls(
            proposal_id=require_non_empty_str(data.get("proposal_id"), "steering_proposal.proposal_id"),
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "steering_proposal.mission_run_id"),
            iteration=require_int_at_least(data.get("iteration"), "steering_proposal.iteration", 1),
            input_refs=require_str_list(data.get("input_refs", []), "steering_proposal.input_refs"),
            recommended_route=require_enum(data.get("recommended_route"), AdaptiveDecision, "steering_proposal.recommended_route"),
            proposed_contract=require_mapping(data.get("proposed_contract", {}), "steering_proposal.proposed_contract"),
            rationale=data.get("rationale", ""),
            risks=require_str_list(data.get("risks", []), "steering_proposal.risks"),
            confidence=require_confidence(data.get("confidence", 0.0), "steering_proposal.confidence"),
        )
        proposal.validate()
        return proposal

    def validate(self) -> None:
        require_non_empty_str(self.proposal_id, "steering_proposal.proposal_id")
        require_non_empty_str(self.mission_run_id, "steering_proposal.mission_run_id")
        require_int_at_least(self.iteration, "steering_proposal.iteration", 1)
        for ref in self.input_refs:
            validate_ref(ref, "steering_proposal.input_refs[]")
        route = require_enum(self.recommended_route, AdaptiveDecision, "steering_proposal.recommended_route")
        if route == AdaptiveDecision.COMPLETE:
            raise ContractValidationError("steering_proposal.recommended_route cannot close a mission")
        require_mapping(self.proposed_contract, "steering_proposal.proposed_contract")
        if self.rationale:
            require_non_empty_str(self.rationale, "steering_proposal.rationale")
        require_str_list(self.risks, "steering_proposal.risks")
        require_confidence(self.confidence, "steering_proposal.confidence")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "proposal_id": self.proposal_id,
            "mission_run_id": self.mission_run_id,
            "iteration": self.iteration,
            "input_refs": list(self.input_refs),
            "recommended_route": self.recommended_route.value,
            "proposed_contract": dict(self.proposed_contract),
            "rationale": self.rationale,
            "risks": list(self.risks),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ProposalValidationResult:
    """Accepted or rejected proposal decision."""

    proposal_id: str
    status: ProposalValidationStatus
    reasons: list[str] = field(default_factory=list)
    accepted_contract_ref: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProposalValidationResult":
        data = require_mapping(payload, "proposal_validation")
        accepted_contract_ref = data.get("accepted_contract_ref")
        result = cls(
            proposal_id=require_non_empty_str(data.get("proposal_id"), "proposal_validation.proposal_id"),
            status=require_enum(data.get("status"), ProposalValidationStatus, "proposal_validation.status"),
            reasons=require_str_list(data.get("reasons", []), "proposal_validation.reasons"),
            accepted_contract_ref=(
                validate_ref(accepted_contract_ref, "proposal_validation.accepted_contract_ref")
                if accepted_contract_ref is not None
                else None
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.proposal_id, "proposal_validation.proposal_id")
        require_enum(self.status, ProposalValidationStatus, "proposal_validation.status")
        require_str_list(self.reasons, "proposal_validation.reasons")
        if self.status == ProposalValidationStatus.REJECTED and not self.reasons:
            raise ContractValidationError("proposal_validation.reasons must explain rejection")
        if self.accepted_contract_ref is not None:
            validate_ref(self.accepted_contract_ref, "proposal_validation.accepted_contract_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "proposal_id": self.proposal_id,
            "status": self.status.value,
            "reasons": list(self.reasons),
            "accepted_contract_ref": self.accepted_contract_ref,
        }


@dataclass(frozen=True)
class DecisionLedgerEntry:
    """Recorded accept/reject decision for a steering proposal."""

    entry_id: str
    proposal_id: str
    status: ProposalValidationStatus
    reasons: list[str] = field(default_factory=list)
    accepted_contract_ref: str | None = None
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionLedgerEntry":
        data = require_mapping(payload, "decision_ledger_entry")
        accepted_contract_ref = data.get("accepted_contract_ref")
        entry = cls(
            entry_id=require_non_empty_str(data.get("entry_id"), "decision_ledger_entry.entry_id"),
            proposal_id=require_non_empty_str(data.get("proposal_id"), "decision_ledger_entry.proposal_id"),
            status=require_enum(data.get("status"), ProposalValidationStatus, "decision_ledger_entry.status"),
            reasons=require_str_list(data.get("reasons", []), "decision_ledger_entry.reasons"),
            accepted_contract_ref=(
                validate_ref(accepted_contract_ref, "decision_ledger_entry.accepted_contract_ref")
                if accepted_contract_ref is not None
                else None
            ),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "decision_ledger_entry.evidence_refs"),
        )
        entry.validate()
        return entry

    def validate(self) -> None:
        require_non_empty_str(self.entry_id, "decision_ledger_entry.entry_id")
        require_non_empty_str(self.proposal_id, "decision_ledger_entry.proposal_id")
        require_enum(self.status, ProposalValidationStatus, "decision_ledger_entry.status")
        require_str_list(self.reasons, "decision_ledger_entry.reasons")
        if self.status == ProposalValidationStatus.REJECTED and not self.reasons:
            raise ContractValidationError("decision_ledger_entry.reasons must explain rejection")
        if self.accepted_contract_ref is not None:
            validate_ref(self.accepted_contract_ref, "decision_ledger_entry.accepted_contract_ref")
        for ref in self.evidence_refs:
            validate_ref(ref, "decision_ledger_entry.evidence_refs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "entry_id": self.entry_id,
            "proposal_id": self.proposal_id,
            "status": self.status.value,
            "reasons": list(self.reasons),
            "accepted_contract_ref": self.accepted_contract_ref,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class StateCorrection:
    """Evidence-backed correction to mission state."""

    corrected_field: str
    source_ref: str
    trust_level: EvidenceTrustLevel
    correction: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StateCorrection":
        data = require_mapping(payload, "state_correction")
        correction = cls(
            corrected_field=require_non_empty_str(data.get("corrected_field"), "state_correction.corrected_field"),
            source_ref=validate_ref(data.get("source_ref"), "state_correction.source_ref"),
            trust_level=require_enum(data.get("trust_level"), EvidenceTrustLevel, "state_correction.trust_level"),
            correction=require_non_empty_str(data.get("correction"), "state_correction.correction"),
        )
        correction.validate()
        return correction

    def validate(self) -> None:
        require_non_empty_str(self.corrected_field, "state_correction.corrected_field")
        validate_ref(self.source_ref, "state_correction.source_ref")
        require_enum(self.trust_level, EvidenceTrustLevel, "state_correction.trust_level")
        require_non_empty_str(self.correction, "state_correction.correction")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "corrected_field": self.corrected_field,
            "source_ref": self.source_ref,
            "trust_level": self.trust_level.value,
            "correction": self.correction,
        }
