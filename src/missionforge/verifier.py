"""Evidence-first verifier routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .contracts import (
    ContractValidationError,
    EvidenceTrustLevel,
    ValidatorMode,
    ValidatorSeverity,
    VerificationStatus,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
)
from .evidence import trust_satisfies
from .evidence_store import EvidenceLedger, InMemoryEvidenceStore
from .review import ReviewerDecision
from .validators import run_validator
from .verification import FailedConstraint, MissingEvidence, VerificationResult, VerificationSpec, ValidatorResult


@dataclass
class Verifier:
    """Deterministic verifier for a locked verification spec."""

    workspace: str | Path = "."
    evidence_store: EvidenceLedger = field(default_factory=InMemoryEvidenceStore)
    contract_hash: str = "unbound-contract"
    capsule_id: str | None = None
    capsule_revision: int | None = None

    def verify(
        self,
        spec: VerificationSpec,
        *,
        reviewer_decision: ReviewerDecision | None = None,
    ) -> VerificationResult:
        return verify_spec(
            spec,
            workspace=self.workspace,
            evidence_store=self.evidence_store,
            contract_hash=self.contract_hash,
            capsule_id=self.capsule_id,
            capsule_revision=self.capsule_revision,
            reviewer_decision=reviewer_decision,
        )


def verify_spec(
    spec: VerificationSpec,
    *,
    workspace: str | Path = ".",
    evidence_store: EvidenceLedger | None = None,
    contract_hash: str = "unbound-contract",
    capsule_id: str | None = None,
    capsule_revision: int | None = None,
    reviewer_decision: ReviewerDecision | None = None,
) -> VerificationResult:
    """Run verifier routing for executable, manual, and unsupported validators."""

    spec.validate()
    store = evidence_store or InMemoryEvidenceStore()
    validator_results: list[ValidatorResult] = []
    evidence_refs: list[str] = []
    failed_constraints: list[FailedConstraint] = []
    missing_evidence: list[MissingEvidence] = []
    warnings: list[str] = []
    has_blocking_failure = False
    has_blocking_review = False
    has_blocking_human = False
    has_blocking_unsupported = False

    for validator in spec.validators:
        mode = require_enum(validator.mode, ValidatorMode, "validator.mode")
        severity = require_enum(validator.severity, ValidatorSeverity, "validator.severity")
        if mode == ValidatorMode.UNSUPPORTED:
            result = ValidatorResult(
                validator_id=validator.validator_id,
                passed=False,
                message=f"unsupported validator type: {validator.type}",
            )
            validator_results.append(result)
            if severity == ValidatorSeverity.BLOCKING:
                has_blocking_unsupported = True
            else:
                warnings.append(result.message)
            continue
        if mode == ValidatorMode.MANUAL:
            result, status_flag = _route_manual_validator(
                validator_id=validator.validator_id,
                inputs=validator.inputs,
                severity=severity,
                reviewer_decision=reviewer_decision,
                contract_hash=contract_hash,
                capsule_id=capsule_id,
                capsule_revision=capsule_revision,
            )
            validator_results.append(result)
            evidence_refs.extend(result.evidence_refs)
            if status_flag == "human":
                has_blocking_human = True
            elif status_flag == "review":
                has_blocking_review = True
            elif status_flag == "warning":
                warnings.append(result.message)
            continue

        result = run_validator(validator, workspace=workspace, evidence_store=store)
        trust_failures = _check_required_evidence(validator, store)
        if trust_failures:
            missing_evidence.extend(trust_failures)
            result = ValidatorResult(
                validator_id=result.validator_id,
                passed=False,
                evidence_refs=list(result.evidence_refs),
                message="required evidence did not satisfy trust requirements",
            )
        validator_results.append(result)
        evidence_refs.extend(result.evidence_refs)
        if not result.passed:
            if severity == ValidatorSeverity.BLOCKING:
                has_blocking_failure = True
                failed_constraints.extend(_failed_constraints(validator, result))
            else:
                warnings.append(result.message)

    manual_status = _route_manual_gates(
        spec,
        reviewer_decision=reviewer_decision,
        contract_hash=contract_hash,
        capsule_id=capsule_id,
        capsule_revision=capsule_revision,
    )
    if manual_status == "human":
        has_blocking_human = True
    elif manual_status == "review":
        has_blocking_review = True

    if has_blocking_unsupported:
        status = VerificationStatus.UNSUPPORTED_VERIFICATION_SPEC
    elif has_blocking_failure:
        status = VerificationStatus.FAILED
    elif has_blocking_human:
        status = VerificationStatus.HUMAN_ACCEPTANCE_REQUIRED
    elif has_blocking_review:
        status = VerificationStatus.REVIEW_REQUIRED
    else:
        status = VerificationStatus.COMPLETED_VERIFIED

    return VerificationResult(
        status=status,
        validator_results=validator_results,
        evidence_refs=_dedupe(evidence_refs),
        failed_constraints=failed_constraints,
        missing_evidence=missing_evidence,
        failed_constraint_ids=_dedupe([failure.constraint_id for failure in failed_constraints]),
        warnings=[warning for warning in warnings if warning],
    )


def _route_manual_validator(
    *,
    validator_id: str,
    inputs: dict[str, object],
    severity: ValidatorSeverity,
    reviewer_decision: ReviewerDecision | None,
    contract_hash: str,
    capsule_id: str | None,
    capsule_revision: int | None,
) -> tuple[ValidatorResult, str | None]:
    authority = _authority(inputs)
    if reviewer_decision is not None and authority != "user":
        reviewer_decision.validate_current(
            contract_hash=contract_hash,
            capsule_id=capsule_id,
            capsule_revision=capsule_revision,
        )
        return (
            ValidatorResult(
                validator_id=validator_id,
                passed=True,
                evidence_refs=list(reviewer_decision.evidence_refs),
                message="manual gate approved by independent reviewer",
            ),
            None,
        )
    result = ValidatorResult(
        validator_id=validator_id,
        passed=False,
        message="manual gate requires user acceptance" if authority == "user" else "manual gate requires reviewer",
    )
    if severity != ValidatorSeverity.BLOCKING:
        return result, "warning"
    return result, "human" if authority == "user" else "review"


def _route_manual_gates(
    spec: VerificationSpec,
    *,
    reviewer_decision: ReviewerDecision | None,
    contract_hash: str,
    capsule_id: str | None,
    capsule_revision: int | None,
) -> str | None:
    status: str | None = None
    for gate in spec.manual_gates:
        data = require_mapping(gate, "verification_spec.manual_gates[]")
        severity = require_enum(data.get("severity", ValidatorSeverity.BLOCKING.value), ValidatorSeverity, "manual_gate.severity")
        if severity != ValidatorSeverity.BLOCKING:
            continue
        authority = _authority(data)
        if reviewer_decision is not None and authority != "user":
            reviewer_decision.validate_current(
                contract_hash=contract_hash,
                capsule_id=capsule_id,
                capsule_revision=capsule_revision,
            )
            continue
        if authority == "user":
            status = "human"
        elif status != "human":
            status = "review"
    return status


def _authority(inputs: dict[str, object]) -> str:
    data = require_mapping(inputs, "validator.inputs")
    if data.get("requires_user_confirmation") is True:
        return "user"
    authority = data.get("authority", "reviewer")
    if authority not in {"reviewer", "user"}:
        raise ContractValidationError("manual authority must be reviewer or user")
    return authority


def _check_required_evidence(
    validator,
    evidence_store: EvidenceLedger,
) -> list[MissingEvidence]:
    inputs = require_mapping(validator.inputs, "validator.inputs")
    required_ids = require_str_list(inputs.get("required_evidence_ids", []), "validator.inputs.required_evidence_ids")
    if not required_ids:
        return []
    required_trust = require_enum(
        inputs.get("minimum_trust_level", EvidenceTrustLevel.VERIFIER_RESULT.value),
        EvidenceTrustLevel,
        "validator.inputs.minimum_trust_level",
    )
    failures: list[MissingEvidence] = []
    for evidence_id in required_ids:
        try:
            record = evidence_store.get(evidence_id)
        except ContractValidationError:
            failures.append(
                MissingEvidence(
                    evidence_id=evidence_id,
                    validator_id=validator.validator_id,
                    required_trust_level=required_trust.value,
                    actual_trust_level=None,
                    message="required evidence is missing",
                )
            )
            continue
        actual = record.evidence_ref.trust_level
        if not trust_satisfies(actual, required_trust):
            failures.append(
                MissingEvidence(
                    evidence_id=evidence_id,
                    validator_id=validator.validator_id,
                    required_trust_level=required_trust.value,
                    actual_trust_level=actual.value,
                    message="required evidence trust is too low",
                )
            )
    return failures


def _failed_constraints(validator, result: ValidatorResult) -> list[FailedConstraint]:
    failures: list[FailedConstraint] = []
    for constraint_id in validator.constraint_refs:
        failures.append(
            FailedConstraint(
                constraint_id=require_non_empty_str(constraint_id, "validator.constraint_refs[]"),
                validator_id=validator.validator_id,
                evidence_refs=list(result.evidence_refs),
                message=result.message,
            )
        )
    return failures


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
