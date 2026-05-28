"""Controlled steering contract objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .contracts import (
    AdaptiveDecision,
    AuthorityRequirement,
    ContractAdjustmentChange,
    ContractValidationError,
    EvidenceTrustLevel,
    ObservationSignalType,
    ProposalValidationStatus,
    SteeringProposalKind,
    assert_refs_only_payload,
    ensure_json_value,
    require_confidence,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)

STEERING_CONTEXT_SCHEMA_VERSION = "missionforge.steering_context.v1"
STEERING_PROPOSAL_SCHEMA_VERSION = "missionforge.steering_proposal.v1"
OBSERVATION_SIGNAL_SCHEMA_VERSION = "missionforge.observation_signal.v1"
CONTRACT_ADJUSTMENT_REQUEST_SCHEMA_VERSION = "missionforge.contract_adjustment_request.v1"
REPAIR_STRATEGY_PROPOSAL_SCHEMA_VERSION = "missionforge.repair_strategy_proposal.v1"

HARNESS_AUTHORIZED_ADJUSTMENTS = {
    ContractAdjustmentChange.SHRINK,
    ContractAdjustmentChange.SPLIT,
    ContractAdjustmentChange.REORDER,
}


class ProposalProvider(Protocol):
    """Provider of controlled steering proposals."""

    def next_proposal(self, context: "SteeringContext | None" = None) -> "SteeringProposal":
        """Return the next proposal."""


class ObservationInterpreter(Protocol):
    """Provider of safe observation interpretations."""

    def interpret_observation(self, context: "SteeringContext") -> "ObservationSignal":
        """Return an observation signal for the current context."""


class ReviewerProvider(Protocol):
    """Provider of independent review decisions."""

    def review(self, packet: Any) -> Any:
        """Return a reviewer decision for a review packet."""


@dataclass(frozen=True)
class SteeringContext:
    """Refs-only provider context for controlled steering."""

    mission_run_id: str
    mission_id: str
    iteration: int
    contract_ref: str
    contract_hash: str
    mission_run_ref: str
    attempt_refs: list[str] = field(default_factory=list)
    latest_attempt_ref: str = ""
    verification_refs: list[str] = field(default_factory=list)
    artifact_hygiene_ref: str = ""
    failed_constraint_ids: list[str] = field(default_factory=list)
    allowed_output_roots: list[str] = field(default_factory=list)
    visible_refs: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    authority_policy_ref: str = ""
    safe_summary: str = ""
    schema_version: str = STEERING_CONTEXT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SteeringContext":
        data = _strict_mapping(
            payload,
            "steering_context",
            {
                "schema_version",
                "mission_run_id",
                "mission_id",
                "iteration",
                "contract_ref",
                "contract_hash",
                "mission_run_ref",
                "attempt_refs",
                "latest_attempt_ref",
                "verification_refs",
                "artifact_hygiene_ref",
                "failed_constraint_ids",
                "allowed_output_roots",
                "visible_refs",
                "forbidden_actions",
                "authority_policy_ref",
                "safe_summary",
            },
        )
        context = cls(
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "steering_context.mission_run_id"),
            mission_id=require_non_empty_str(data.get("mission_id"), "steering_context.mission_id"),
            iteration=require_int_at_least(data.get("iteration"), "steering_context.iteration", 1),
            contract_ref=validate_ref(data.get("contract_ref"), "steering_context.contract_ref"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "steering_context.contract_hash"),
            mission_run_ref=validate_ref(data.get("mission_run_ref"), "steering_context.mission_run_ref"),
            attempt_refs=require_str_list(data.get("attempt_refs", []), "steering_context.attempt_refs"),
            latest_attempt_ref=data.get("latest_attempt_ref", ""),
            verification_refs=require_str_list(data.get("verification_refs", []), "steering_context.verification_refs"),
            artifact_hygiene_ref=data.get("artifact_hygiene_ref", ""),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "steering_context.failed_constraint_ids",
            ),
            allowed_output_roots=require_str_list(
                data.get("allowed_output_roots", []),
                "steering_context.allowed_output_roots",
            ),
            visible_refs=require_str_list(data.get("visible_refs", []), "steering_context.visible_refs"),
            forbidden_actions=require_str_list(
                data.get("forbidden_actions", []),
                "steering_context.forbidden_actions",
            ),
            authority_policy_ref=data.get("authority_policy_ref", ""),
            safe_summary=data.get("safe_summary", ""),
            schema_version=require_non_empty_str(
                data.get("schema_version", STEERING_CONTEXT_SCHEMA_VERSION),
                "steering_context.schema_version",
            ),
        )
        context.validate()
        return context

    def validate(self) -> None:
        if self.schema_version != STEERING_CONTEXT_SCHEMA_VERSION:
            raise ContractValidationError("steering_context.schema_version is unsupported")
        require_non_empty_str(self.mission_run_id, "steering_context.mission_run_id")
        require_non_empty_str(self.mission_id, "steering_context.mission_id")
        require_int_at_least(self.iteration, "steering_context.iteration", 1)
        validate_ref(self.contract_ref, "steering_context.contract_ref")
        require_non_empty_str(self.contract_hash, "steering_context.contract_hash")
        validate_ref(self.mission_run_ref, "steering_context.mission_run_ref")
        for ref in self.attempt_refs:
            validate_ref(ref, "steering_context.attempt_refs[]")
        if self.latest_attempt_ref:
            validate_ref(self.latest_attempt_ref, "steering_context.latest_attempt_ref")
        for ref in self.verification_refs:
            validate_ref(ref, "steering_context.verification_refs[]")
        if self.artifact_hygiene_ref:
            validate_ref(self.artifact_hygiene_ref, "steering_context.artifact_hygiene_ref")
        require_str_list(self.failed_constraint_ids, "steering_context.failed_constraint_ids")
        for ref in self.allowed_output_roots:
            validate_ref(ref, "steering_context.allowed_output_roots[]")
        for ref in self.visible_refs:
            validate_ref(ref, "steering_context.visible_refs[]")
        require_str_list(self.forbidden_actions, "steering_context.forbidden_actions")
        if self.authority_policy_ref:
            validate_ref(self.authority_policy_ref, "steering_context.authority_policy_ref")
        if self.safe_summary:
            require_non_empty_str(self.safe_summary, "steering_context.safe_summary")
        assert_refs_only_payload(self.to_dict_without_validation(), "steering_context")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mission_run_id": self.mission_run_id,
            "mission_id": self.mission_id,
            "iteration": self.iteration,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "mission_run_ref": self.mission_run_ref,
            "attempt_refs": list(self.attempt_refs),
            "latest_attempt_ref": self.latest_attempt_ref,
            "verification_refs": list(self.verification_refs),
            "artifact_hygiene_ref": self.artifact_hygiene_ref,
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "allowed_output_roots": list(self.allowed_output_roots),
            "visible_refs": list(self.visible_refs),
            "forbidden_actions": list(self.forbidden_actions),
            "authority_policy_ref": self.authority_policy_ref,
            "safe_summary": self.safe_summary,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


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
    proposal_kind: SteeringProposalKind = SteeringProposalKind.NEXT_WORK_UNIT
    source: str = "deterministic"
    source_refs: list[str] = field(default_factory=list)
    authority_required: AuthorityRequirement = AuthorityRequirement.HARNESS
    trust_level: EvidenceTrustLevel = EvidenceTrustLevel.SCHEMA_VALIDATION
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    provider_diagnostic_refs: list[str] = field(default_factory=list)
    schema_version: str = STEERING_PROPOSAL_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SteeringProposal":
        data = _strict_mapping(
            payload,
            "steering_proposal",
            {
                "schema_version",
                "proposal_id",
                "mission_run_id",
                "iteration",
                "input_refs",
                "recommended_route",
                "proposed_contract",
                "rationale",
                "risks",
                "confidence",
                "proposal_kind",
                "source",
                "source_refs",
                "authority_required",
                "trust_level",
                "alternatives",
                "provider_diagnostic_refs",
            },
        )
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
            proposal_kind=require_enum(
                data.get("proposal_kind", SteeringProposalKind.NEXT_WORK_UNIT.value),
                SteeringProposalKind,
                "steering_proposal.proposal_kind",
            ),
            source=require_non_empty_str(data.get("source", "deterministic"), "steering_proposal.source"),
            source_refs=require_str_list(data.get("source_refs", []), "steering_proposal.source_refs"),
            authority_required=require_enum(
                data.get("authority_required", AuthorityRequirement.HARNESS.value),
                AuthorityRequirement,
                "steering_proposal.authority_required",
            ),
            trust_level=require_enum(
                data.get("trust_level", EvidenceTrustLevel.SCHEMA_VALIDATION.value),
                EvidenceTrustLevel,
                "steering_proposal.trust_level",
            ),
            alternatives=list(data.get("alternatives", [])),
            provider_diagnostic_refs=require_str_list(
                data.get("provider_diagnostic_refs", []),
                "steering_proposal.provider_diagnostic_refs",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", STEERING_PROPOSAL_SCHEMA_VERSION),
                "steering_proposal.schema_version",
            ),
        )
        proposal.validate()
        return proposal

    def validate(self) -> None:
        if self.schema_version != STEERING_PROPOSAL_SCHEMA_VERSION:
            raise ContractValidationError("steering_proposal.schema_version is unsupported")
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
        require_enum(self.proposal_kind, SteeringProposalKind, "steering_proposal.proposal_kind")
        source = require_non_empty_str(self.source, "steering_proposal.source")
        for ref in self.source_refs:
            validate_ref(ref, "steering_proposal.source_refs[]")
        if source != "deterministic" and not self.source_refs:
            raise ContractValidationError("steering_proposal.source_refs must cite provider inputs")
        require_enum(self.authority_required, AuthorityRequirement, "steering_proposal.authority_required")
        require_enum(self.trust_level, EvidenceTrustLevel, "steering_proposal.trust_level")
        assert_refs_only_payload(self.proposed_contract, "steering_proposal.proposed_contract")
        assert_refs_only_payload(self.alternatives, "steering_proposal.alternatives")
        for ref in self.provider_diagnostic_refs:
            validate_ref(ref, "steering_proposal.provider_diagnostic_refs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "mission_run_id": self.mission_run_id,
            "iteration": self.iteration,
            "input_refs": list(self.input_refs),
            "recommended_route": self.recommended_route.value,
            "proposed_contract": dict(self.proposed_contract),
            "rationale": self.rationale,
            "risks": list(self.risks),
            "confidence": self.confidence,
            "proposal_kind": self.proposal_kind.value,
            "source": self.source,
            "source_refs": list(self.source_refs),
            "authority_required": self.authority_required.value,
            "trust_level": self.trust_level.value,
            "alternatives": ensure_json_value(self.alternatives, "steering_proposal.alternatives"),
            "provider_diagnostic_refs": list(self.provider_diagnostic_refs),
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


@dataclass(frozen=True)
class ObservationSignal:
    """Safe interpretation of an observation as hypothesis, not fact."""

    signal_id: str
    mission_run_id: str
    iteration: int
    observation_ref: str
    source_refs: list[str]
    signal_type: ObservationSignalType
    safe_summary: str
    trust_level: EvidenceTrustLevel
    recommended_action: AdaptiveDecision
    affected_contract_fields: list[str] = field(default_factory=list)
    confidence: float = 0.0
    requires_verifier_confirmation: bool = True
    schema_version: str = OBSERVATION_SIGNAL_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObservationSignal":
        data = _strict_mapping(
            payload,
            "observation_signal",
            {
                "schema_version",
                "signal_id",
                "mission_run_id",
                "iteration",
                "observation_ref",
                "source_refs",
                "signal_type",
                "safe_summary",
                "trust_level",
                "recommended_action",
                "affected_contract_fields",
                "confidence",
                "requires_verifier_confirmation",
            },
        )
        signal = cls(
            signal_id=require_non_empty_str(data.get("signal_id"), "observation_signal.signal_id"),
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "observation_signal.mission_run_id"),
            iteration=require_int_at_least(data.get("iteration"), "observation_signal.iteration", 1),
            observation_ref=validate_ref(data.get("observation_ref"), "observation_signal.observation_ref"),
            source_refs=require_str_list(data.get("source_refs", []), "observation_signal.source_refs"),
            signal_type=require_enum(data.get("signal_type"), ObservationSignalType, "observation_signal.signal_type"),
            safe_summary=require_non_empty_str(data.get("safe_summary"), "observation_signal.safe_summary"),
            trust_level=require_enum(data.get("trust_level"), EvidenceTrustLevel, "observation_signal.trust_level"),
            recommended_action=require_enum(
                data.get("recommended_action"),
                AdaptiveDecision,
                "observation_signal.recommended_action",
            ),
            affected_contract_fields=require_str_list(
                data.get("affected_contract_fields", []),
                "observation_signal.affected_contract_fields",
            ),
            confidence=require_confidence(data.get("confidence", 0.0), "observation_signal.confidence"),
            requires_verifier_confirmation=bool(data.get("requires_verifier_confirmation", True)),
            schema_version=require_non_empty_str(
                data.get("schema_version", OBSERVATION_SIGNAL_SCHEMA_VERSION),
                "observation_signal.schema_version",
            ),
        )
        signal.validate()
        return signal

    def validate(self) -> None:
        if self.schema_version != OBSERVATION_SIGNAL_SCHEMA_VERSION:
            raise ContractValidationError("observation_signal.schema_version is unsupported")
        require_non_empty_str(self.signal_id, "observation_signal.signal_id")
        require_non_empty_str(self.mission_run_id, "observation_signal.mission_run_id")
        require_int_at_least(self.iteration, "observation_signal.iteration", 1)
        validate_ref(self.observation_ref, "observation_signal.observation_ref")
        if not self.source_refs:
            raise ContractValidationError("observation_signal.source_refs must not be empty")
        for ref in self.source_refs:
            validate_ref(ref, "observation_signal.source_refs[]")
        require_enum(self.signal_type, ObservationSignalType, "observation_signal.signal_type")
        require_non_empty_str(self.safe_summary, "observation_signal.safe_summary")
        require_enum(self.trust_level, EvidenceTrustLevel, "observation_signal.trust_level")
        action = require_enum(self.recommended_action, AdaptiveDecision, "observation_signal.recommended_action")
        if action == AdaptiveDecision.COMPLETE:
            raise ContractValidationError("observation_signal.recommended_action cannot close a mission")
        require_str_list(self.affected_contract_fields, "observation_signal.affected_contract_fields")
        require_confidence(self.confidence, "observation_signal.confidence")
        if not isinstance(self.requires_verifier_confirmation, bool):
            raise ContractValidationError("observation_signal.requires_verifier_confirmation must be boolean")
        assert_refs_only_payload(self.to_dict_without_validation(), "observation_signal")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "signal_id": self.signal_id,
            "mission_run_id": self.mission_run_id,
            "iteration": self.iteration,
            "observation_ref": self.observation_ref,
            "source_refs": list(self.source_refs),
            "signal_type": self.signal_type.value,
            "safe_summary": self.safe_summary,
            "trust_level": self.trust_level.value,
            "recommended_action": self.recommended_action.value,
            "affected_contract_fields": list(self.affected_contract_fields),
            "confidence": self.confidence,
            "requires_verifier_confirmation": self.requires_verifier_confirmation,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class ContractAdjustmentRequest:
    """Request to alter work shape or route through authority gates."""

    request_id: str
    mission_run_id: str
    iteration: int
    contract_ref: str
    requested_change: ContractAdjustmentChange
    reason: str
    evidence_refs: list[str]
    proposed_contract_refs: list[str] = field(default_factory=list)
    authority_required: AuthorityRequirement = AuthorityRequirement.HARNESS
    risk_if_rejected: str = ""
    schema_version: str = CONTRACT_ADJUSTMENT_REQUEST_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContractAdjustmentRequest":
        data = _strict_mapping(
            payload,
            "contract_adjustment_request",
            {
                "schema_version",
                "request_id",
                "mission_run_id",
                "iteration",
                "contract_ref",
                "requested_change",
                "reason",
                "evidence_refs",
                "proposed_contract_refs",
                "authority_required",
                "risk_if_rejected",
            },
        )
        request = cls(
            request_id=require_non_empty_str(data.get("request_id"), "contract_adjustment_request.request_id"),
            mission_run_id=require_non_empty_str(
                data.get("mission_run_id"),
                "contract_adjustment_request.mission_run_id",
            ),
            iteration=require_int_at_least(data.get("iteration"), "contract_adjustment_request.iteration", 1),
            contract_ref=validate_ref(data.get("contract_ref"), "contract_adjustment_request.contract_ref"),
            requested_change=require_enum(
                data.get("requested_change"),
                ContractAdjustmentChange,
                "contract_adjustment_request.requested_change",
            ),
            reason=require_non_empty_str(data.get("reason"), "contract_adjustment_request.reason"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "contract_adjustment_request.evidence_refs"),
            proposed_contract_refs=require_str_list(
                data.get("proposed_contract_refs", []),
                "contract_adjustment_request.proposed_contract_refs",
            ),
            authority_required=require_enum(
                data.get("authority_required", AuthorityRequirement.HARNESS.value),
                AuthorityRequirement,
                "contract_adjustment_request.authority_required",
            ),
            risk_if_rejected=data.get("risk_if_rejected", ""),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTRACT_ADJUSTMENT_REQUEST_SCHEMA_VERSION),
                "contract_adjustment_request.schema_version",
            ),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if self.schema_version != CONTRACT_ADJUSTMENT_REQUEST_SCHEMA_VERSION:
            raise ContractValidationError("contract_adjustment_request.schema_version is unsupported")
        require_non_empty_str(self.request_id, "contract_adjustment_request.request_id")
        require_non_empty_str(self.mission_run_id, "contract_adjustment_request.mission_run_id")
        require_int_at_least(self.iteration, "contract_adjustment_request.iteration", 1)
        validate_ref(self.contract_ref, "contract_adjustment_request.contract_ref")
        require_enum(self.requested_change, ContractAdjustmentChange, "contract_adjustment_request.requested_change")
        require_non_empty_str(self.reason, "contract_adjustment_request.reason")
        if not self.evidence_refs:
            raise ContractValidationError("contract_adjustment_request.evidence_refs must not be empty")
        for ref in self.evidence_refs:
            validate_ref(ref, "contract_adjustment_request.evidence_refs[]")
        for ref in self.proposed_contract_refs:
            validate_ref(ref, "contract_adjustment_request.proposed_contract_refs[]")
        require_enum(self.authority_required, AuthorityRequirement, "contract_adjustment_request.authority_required")
        if self.risk_if_rejected:
            require_non_empty_str(self.risk_if_rejected, "contract_adjustment_request.risk_if_rejected")
        if self.requested_change not in HARNESS_AUTHORIZED_ADJUSTMENTS and self.authority_required == AuthorityRequirement.HARNESS:
            raise ContractValidationError("contract_adjustment_request authority is too weak for requested_change")
        assert_refs_only_payload(self.to_dict_without_validation(), "contract_adjustment_request")

    def authority_route(self) -> str:
        self.validate()
        if self.requested_change in HARNESS_AUTHORIZED_ADJUSTMENTS:
            return "harness_authorized"
        if self.authority_required == AuthorityRequirement.HUMAN:
            return "human_authority_required"
        if self.authority_required == AuthorityRequirement.REDESIGN:
            return "redesign_required"
        return "review_required"

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "mission_run_id": self.mission_run_id,
            "iteration": self.iteration,
            "contract_ref": self.contract_ref,
            "requested_change": self.requested_change.value,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "proposed_contract_refs": list(self.proposed_contract_refs),
            "authority_required": self.authority_required.value,
            "risk_if_rejected": self.risk_if_rejected,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class RepairStrategyProposal:
    """Proposal for ordering or splitting verifier repair work."""

    strategy_id: str
    mission_run_id: str
    iteration: int
    failure_refs: list[str]
    failed_constraint_ids: list[str]
    repair_order: list[str]
    work_unit_splits: list[dict[str, Any]] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    schema_version: str = REPAIR_STRATEGY_PROPOSAL_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepairStrategyProposal":
        data = _strict_mapping(
            payload,
            "repair_strategy_proposal",
            {
                "schema_version",
                "strategy_id",
                "mission_run_id",
                "iteration",
                "failure_refs",
                "failed_constraint_ids",
                "repair_order",
                "work_unit_splits",
                "risk_notes",
                "stop_conditions",
                "confidence",
            },
        )
        proposal = cls(
            strategy_id=require_non_empty_str(data.get("strategy_id"), "repair_strategy_proposal.strategy_id"),
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "repair_strategy_proposal.mission_run_id"),
            iteration=require_int_at_least(data.get("iteration"), "repair_strategy_proposal.iteration", 1),
            failure_refs=require_str_list(data.get("failure_refs", []), "repair_strategy_proposal.failure_refs"),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "repair_strategy_proposal.failed_constraint_ids",
            ),
            repair_order=require_str_list(data.get("repair_order", []), "repair_strategy_proposal.repair_order"),
            work_unit_splits=list(data.get("work_unit_splits", [])),
            risk_notes=require_str_list(data.get("risk_notes", []), "repair_strategy_proposal.risk_notes"),
            stop_conditions=require_str_list(
                data.get("stop_conditions", []),
                "repair_strategy_proposal.stop_conditions",
            ),
            confidence=require_confidence(data.get("confidence", 0.0), "repair_strategy_proposal.confidence"),
            schema_version=require_non_empty_str(
                data.get("schema_version", REPAIR_STRATEGY_PROPOSAL_SCHEMA_VERSION),
                "repair_strategy_proposal.schema_version",
            ),
        )
        proposal.validate()
        return proposal

    def validate(self) -> None:
        if self.schema_version != REPAIR_STRATEGY_PROPOSAL_SCHEMA_VERSION:
            raise ContractValidationError("repair_strategy_proposal.schema_version is unsupported")
        require_non_empty_str(self.strategy_id, "repair_strategy_proposal.strategy_id")
        require_non_empty_str(self.mission_run_id, "repair_strategy_proposal.mission_run_id")
        require_int_at_least(self.iteration, "repair_strategy_proposal.iteration", 1)
        if not self.failure_refs:
            raise ContractValidationError("repair_strategy_proposal.failure_refs must not be empty")
        for ref in self.failure_refs:
            validate_ref(ref, "repair_strategy_proposal.failure_refs[]")
        require_str_list(self.failed_constraint_ids, "repair_strategy_proposal.failed_constraint_ids")
        require_str_list(self.repair_order, "repair_strategy_proposal.repair_order")
        assert_refs_only_payload(self.work_unit_splits, "repair_strategy_proposal.work_unit_splits")
        require_str_list(self.risk_notes, "repair_strategy_proposal.risk_notes")
        require_str_list(self.stop_conditions, "repair_strategy_proposal.stop_conditions")
        require_confidence(self.confidence, "repair_strategy_proposal.confidence")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "mission_run_id": self.mission_run_id,
            "iteration": self.iteration,
            "failure_refs": list(self.failure_refs),
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "repair_order": list(self.repair_order),
            "work_unit_splits": ensure_json_value(self.work_unit_splits, "repair_strategy_proposal.work_unit_splits"),
            "risk_notes": list(self.risk_notes),
            "stop_conditions": list(self.stop_conditions),
            "confidence": self.confidence,
        }


def _strict_mapping(payload: Mapping[str, Any], field_name: str, allowed_keys: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    assert_refs_only_payload(data, field_name)
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unsupported fields: {unknown}")
    return data
