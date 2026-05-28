"""Verification contract objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    ValidatorMode,
    ValidatorSeverity,
    VerificationStatus,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
)


@dataclass(frozen=True)
class FailedConstraint:
    """Structured failure tied back to a mission constraint."""

    constraint_id: str
    validator_id: str
    evidence_refs: list[str] = field(default_factory=list)
    message: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FailedConstraint":
        data = require_mapping(payload, "failed_constraint")
        failure = cls(
            constraint_id=require_non_empty_str(data.get("constraint_id"), "failed_constraint.constraint_id"),
            validator_id=require_non_empty_str(data.get("validator_id"), "failed_constraint.validator_id"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "failed_constraint.evidence_refs"),
            message=data.get("message", ""),
        )
        failure.validate()
        return failure

    def validate(self) -> None:
        require_non_empty_str(self.constraint_id, "failed_constraint.constraint_id")
        require_non_empty_str(self.validator_id, "failed_constraint.validator_id")
        require_str_list(self.evidence_refs, "failed_constraint.evidence_refs")
        if self.message:
            require_non_empty_str(self.message, "failed_constraint.message")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "constraint_id": self.constraint_id,
            "validator_id": self.validator_id,
            "evidence_refs": list(self.evidence_refs),
            "message": self.message,
        }


@dataclass(frozen=True)
class MissingEvidence:
    """Evidence requirement that was not satisfied."""

    evidence_id: str
    validator_id: str
    required_trust_level: str
    actual_trust_level: str | None = None
    message: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissingEvidence":
        data = require_mapping(payload, "missing_evidence")
        actual_trust_level = data.get("actual_trust_level")
        missing = cls(
            evidence_id=require_non_empty_str(data.get("evidence_id"), "missing_evidence.evidence_id"),
            validator_id=require_non_empty_str(data.get("validator_id"), "missing_evidence.validator_id"),
            required_trust_level=require_non_empty_str(
                data.get("required_trust_level"),
                "missing_evidence.required_trust_level",
            ),
            actual_trust_level=require_non_empty_str(
                actual_trust_level,
                "missing_evidence.actual_trust_level",
            )
            if actual_trust_level is not None
            else None,
            message=data.get("message", ""),
        )
        missing.validate()
        return missing

    def validate(self) -> None:
        require_non_empty_str(self.evidence_id, "missing_evidence.evidence_id")
        require_non_empty_str(self.validator_id, "missing_evidence.validator_id")
        require_non_empty_str(self.required_trust_level, "missing_evidence.required_trust_level")
        if self.actual_trust_level is not None:
            require_non_empty_str(self.actual_trust_level, "missing_evidence.actual_trust_level")
        if self.message:
            require_non_empty_str(self.message, "missing_evidence.message")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "evidence_id": self.evidence_id,
            "validator_id": self.validator_id,
            "required_trust_level": self.required_trust_level,
            "actual_trust_level": self.actual_trust_level,
            "message": self.message,
        }


@dataclass(frozen=True)
class ValidatorSpec:
    """One locked validator declaration."""

    validator_id: str
    constraint_refs: list[str]
    type: str
    mode: ValidatorMode = ValidatorMode.EXECUTABLE
    severity: ValidatorSeverity = ValidatorSeverity.BLOCKING
    description: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidatorSpec":
        data = require_mapping(payload, "validator")
        description = data.get("description", "")
        return cls(
            validator_id=require_non_empty_str(data.get("validator_id"), "validator.validator_id"),
            constraint_refs=require_str_list(data.get("constraint_refs", []), "validator.constraint_refs"),
            type=require_non_empty_str(data.get("type"), "validator.type"),
            mode=require_enum(data.get("mode", ValidatorMode.EXECUTABLE.value), ValidatorMode, "validator.mode"),
            severity=require_enum(data.get("severity", ValidatorSeverity.BLOCKING.value), ValidatorSeverity, "validator.severity"),
            description=require_non_empty_str(description, "validator.description") if description else "",
            inputs=require_mapping(data.get("inputs", {}), "validator.inputs"),
        )

    def validate(self) -> None:
        require_non_empty_str(self.validator_id, "validator.validator_id")
        require_str_list(self.constraint_refs, "validator.constraint_refs")
        require_non_empty_str(self.type, "validator.type")
        require_enum(self.mode, ValidatorMode, "validator.mode")
        require_enum(self.severity, ValidatorSeverity, "validator.severity")
        if self.description:
            require_non_empty_str(self.description, "validator.description")
        require_mapping(self.inputs, "validator.inputs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "validator_id": self.validator_id,
            "constraint_refs": list(self.constraint_refs),
            "type": self.type,
            "mode": self.mode.value,
            "severity": self.severity.value,
            "description": self.description,
            "inputs": dict(self.inputs),
        }


@dataclass(frozen=True)
class VerificationSpec:
    """Locked mission verification plan."""

    validators: list[ValidatorSpec] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    manual_gates: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerificationSpec":
        data = require_mapping(payload, "verification_spec")
        spec = cls(
            validators=[
                ValidatorSpec.from_dict(require_mapping(item, "verification_spec.validators[]"))
                for item in data.get("validators", [])
            ],
            evidence_requirements=require_str_list(data.get("evidence_requirements", []), "verification_spec.evidence_requirements"),
            manual_gates=[
                require_mapping(item, "verification_spec.manual_gates[]")
                for item in data.get("manual_gates", [])
            ],
        )
        spec.validate()
        return spec

    def validate(self) -> None:
        seen: set[str] = set()
        for validator in self.validators:
            validator.validate()
            if validator.validator_id in seen:
                raise ContractValidationError(f"duplicate validator_id: {validator.validator_id}")
            seen.add(validator.validator_id)
        require_str_list(self.evidence_requirements, "verification_spec.evidence_requirements")
        for gate in self.manual_gates:
            require_mapping(gate, "verification_spec.manual_gates[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "validators": [validator.to_dict() for validator in self.validators],
            "evidence_requirements": list(self.evidence_requirements),
            "manual_gates": [dict(gate) for gate in self.manual_gates],
        }


@dataclass(frozen=True)
class ValidatorResult:
    """Result for one validator."""

    validator_id: str
    passed: bool
    evidence_refs: list[str] = field(default_factory=list)
    message: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidatorResult":
        data = require_mapping(payload, "validator_result")
        result = cls(
            validator_id=require_non_empty_str(data.get("validator_id"), "validator_result.validator_id"),
            passed=data.get("passed"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "validator_result.evidence_refs"),
            message=data.get("message", ""),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.validator_id, "validator_result.validator_id")
        if not isinstance(self.passed, bool):
            raise ContractValidationError("validator_result.passed must be a boolean")
        require_str_list(self.evidence_refs, "validator_result.evidence_refs")
        if self.message:
            require_non_empty_str(self.message, "validator_result.message")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "validator_id": self.validator_id,
            "passed": self.passed,
            "evidence_refs": list(self.evidence_refs),
            "message": self.message,
        }


@dataclass(frozen=True)
class VerificationResult:
    """Refs-only verification result envelope."""

    status: VerificationStatus
    validator_results: list[ValidatorResult] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    failed_constraints: list[FailedConstraint] = field(default_factory=list)
    missing_evidence: list[MissingEvidence] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerificationResult":
        data = require_mapping(payload, "verification_result")
        result = cls(
            status=require_enum(data.get("status"), VerificationStatus, "verification_result.status"),
            validator_results=[
                ValidatorResult.from_dict(require_mapping(item, "verification_result.validator_results[]"))
                for item in [require_mapping(item, "verification_result.validator_results[]") for item in data.get("validator_results", [])]
            ],
            evidence_refs=require_str_list(data.get("evidence_refs", []), "verification_result.evidence_refs"),
            failed_constraints=[
                FailedConstraint.from_dict(require_mapping(item, "verification_result.failed_constraints[]"))
                for item in data.get("failed_constraints", [])
            ],
            missing_evidence=[
                MissingEvidence.from_dict(require_mapping(item, "verification_result.missing_evidence[]"))
                for item in data.get("missing_evidence", [])
            ],
            failed_constraint_ids=require_str_list(data.get("failed_constraint_ids", []), "verification_result.failed_constraint_ids"),
            warnings=require_str_list(data.get("warnings", []), "verification_result.warnings"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_enum(self.status, VerificationStatus, "verification_result.status")
        for result in self.validator_results:
            result.validate()
        require_str_list(self.evidence_refs, "verification_result.evidence_refs")
        for failure in self.failed_constraints:
            failure.validate()
        for missing in self.missing_evidence:
            missing.validate()
        require_str_list(self.failed_constraint_ids, "verification_result.failed_constraint_ids")
        require_str_list(self.warnings, "verification_result.warnings")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "status": self.status.value,
            "validator_results": [result.to_dict() for result in self.validator_results],
            "evidence_refs": list(self.evidence_refs),
            "failed_constraints": [failure.to_dict() for failure in self.failed_constraints],
            "missing_evidence": [missing.to_dict() for missing in self.missing_evidence],
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "warnings": list(self.warnings),
        }
