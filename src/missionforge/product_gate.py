"""Generic ProductGate result protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Self

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str,
    require_str_list,
    validate_ref,
)


PRODUCT_GATE_SPEC_SCHEMA_VERSION = "missionforge.product_gate_spec.v1"
PRODUCT_GATE_RESULT_SCHEMA_VERSION = "missionforge.product_gate_result.v1"


class ProductGateStatus(StrEnum):
    """Generic ProductGate result state."""

    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    UNSUPPORTED = "unsupported"
    CANDIDATE = "candidate"
    PRODUCT_GRADE = "product_grade"
    QUARANTINED = "quarantined"


class ProductGateSeverity(StrEnum):
    """ProductGate finding severity."""

    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True)
class ProductGateCheck:
    """Opaque product-specific gate check declaration."""

    check_id: str
    purpose: str
    blocking: bool = True
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(payload, "product_gate_check", {"check_id", "purpose", "blocking", "evidence_refs"})
        item = cls(
            check_id=require_non_empty_str(data.get("check_id"), "product_gate_check.check_id"),
            purpose=require_non_empty_str(data.get("purpose"), "product_gate_check.purpose"),
            blocking=_require_bool(data.get("blocking", True), "product_gate_check.blocking"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "product_gate_check.evidence_refs"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.check_id, "product_gate_check.check_id")
        require_non_empty_str(self.purpose, "product_gate_check.purpose")
        if not isinstance(self.blocking, bool):
            raise ContractValidationError("product_gate_check.blocking must be a boolean")
        _validate_ref_list(self.evidence_refs, "product_gate_check.evidence_refs")
        assert_refs_only_payload(self.to_dict(), "product_gate_check")

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "purpose": self.purpose,
            "blocking": self.blocking,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class ProductGateSpec:
    """Generic envelope for product-specific ProductGate criteria."""

    product_id: str
    gate_id: str
    checks: list[ProductGateCheck]
    source_refs: list[str] = field(default_factory=list)
    schema_version: str = PRODUCT_GATE_SPEC_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_gate_spec",
            {"schema_version", "product_id", "gate_id", "checks", "source_refs"},
        )
        item = cls(
            product_id=require_non_empty_str(data.get("product_id"), "product_gate_spec.product_id"),
            gate_id=require_non_empty_str(data.get("gate_id"), "product_gate_spec.gate_id"),
            checks=[
                ProductGateCheck.from_dict(require_mapping(child, "product_gate_spec.checks[]"))
                for child in data.get("checks", [])
            ],
            source_refs=require_str_list(data.get("source_refs", []), "product_gate_spec.source_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_GATE_SPEC_SCHEMA_VERSION),
                "product_gate_spec.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        if self.schema_version != PRODUCT_GATE_SPEC_SCHEMA_VERSION:
            raise ContractValidationError("product_gate_spec.schema_version is unsupported")
        require_non_empty_str(self.product_id, "product_gate_spec.product_id")
        require_non_empty_str(self.gate_id, "product_gate_spec.gate_id")
        if not self.checks:
            raise ContractValidationError("product_gate_spec.checks must not be empty")
        check_ids = [check.check_id for check in self.checks]
        _require_unique(check_ids, "product_gate_spec.checks[].check_id")
        for check in self.checks:
            check.validate()
        _validate_ref_list(self.source_refs, "product_gate_spec.source_refs")
        assert_refs_only_payload(self.to_dict(), "product_gate_spec")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "gate_id": self.gate_id,
            "checks": [check.to_dict() for check in self.checks],
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class ProductGateFinding:
    """One product-specific gate finding."""

    check_id: str
    severity: ProductGateSeverity
    message: str
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(payload, "product_gate_finding", {"check_id", "severity", "message", "evidence_refs"})
        item = cls(
            check_id=require_non_empty_str(data.get("check_id"), "product_gate_finding.check_id"),
            severity=require_enum(data.get("severity"), ProductGateSeverity, "product_gate_finding.severity"),
            message=require_non_empty_str(data.get("message"), "product_gate_finding.message"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "product_gate_finding.evidence_refs"),
        )
        item.validate()
        return item

    @property
    def blocking(self) -> bool:
        return self.severity == ProductGateSeverity.BLOCKING

    def validate(self) -> None:
        require_non_empty_str(self.check_id, "product_gate_finding.check_id")
        require_enum(self.severity, ProductGateSeverity, "product_gate_finding.severity")
        require_non_empty_str(self.message, "product_gate_finding.message")
        _validate_ref_list(self.evidence_refs, "product_gate_finding.evidence_refs")
        assert_refs_only_payload(self.to_dict(), "product_gate_finding")

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity.value,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class ProductGateResult:
    """Generic envelope around product-specific readiness evaluation."""

    product_id: str
    status: ProductGateStatus
    gate_spec_ref: str
    findings: list[ProductGateFinding] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    reason: str = ""
    schema_version: str = PRODUCT_GATE_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_gate_result",
            {
                "schema_version",
                "product_id",
                "status",
                "gate_spec_ref",
                "findings",
                "evidence_refs",
                "reason",
            },
        )
        item = cls(
            product_id=require_non_empty_str(data.get("product_id"), "product_gate_result.product_id"),
            status=require_enum(data.get("status"), ProductGateStatus, "product_gate_result.status"),
            gate_spec_ref=validate_ref(data.get("gate_spec_ref"), "product_gate_result.gate_spec_ref"),
            findings=[
                ProductGateFinding.from_dict(require_mapping(child, "product_gate_result.findings[]"))
                for child in data.get("findings", [])
            ],
            evidence_refs=require_str_list(data.get("evidence_refs", []), "product_gate_result.evidence_refs"),
            reason=require_str(data.get("reason", ""), "product_gate_result.reason"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_GATE_RESULT_SCHEMA_VERSION),
                "product_gate_result.schema_version",
            ),
        )
        item.validate()
        return item

    @property
    def has_blocking_findings(self) -> bool:
        return any(finding.blocking for finding in self.findings)

    def validate(self) -> None:
        if self.schema_version != PRODUCT_GATE_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("product_gate_result.schema_version is unsupported")
        require_non_empty_str(self.product_id, "product_gate_result.product_id")
        status = require_enum(self.status, ProductGateStatus, "product_gate_result.status")
        validate_ref(self.gate_spec_ref, "product_gate_result.gate_spec_ref")
        for finding in self.findings:
            finding.validate()
        _validate_ref_list(self.evidence_refs, "product_gate_result.evidence_refs")
        if self.has_blocking_findings and status in {ProductGateStatus.PASSED, ProductGateStatus.PRODUCT_GRADE}:
            raise ContractValidationError("blocking product gate findings prevent passed/product_grade status")
        assert_refs_only_payload(self.to_dict(), "product_gate_result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "status": self.status.value,
            "gate_spec_ref": self.gate_spec_ref,
            "findings": [finding.to_dict() for finding in self.findings],
            "evidence_refs": list(self.evidence_refs),
            "reason": self.reason,
        }


def _strict_mapping(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(value, field_name)
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
    return data


def _validate_ref_list(values: list[str], field_name: str) -> None:
    require_str_list(values, field_name)
    for ref in values:
        validate_ref(ref, f"{field_name}[]")


def _require_unique(values: list[str], field_name: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise ContractValidationError(f"{field_name} contains duplicate value(s): {sorted(set(duplicates))}")


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(f"{field_name} must be a boolean")
    return value


__all__ = [
    "PRODUCT_GATE_RESULT_SCHEMA_VERSION",
    "PRODUCT_GATE_SPEC_SCHEMA_VERSION",
    "ProductGateCheck",
    "ProductGateFinding",
    "ProductGateResult",
    "ProductGateSeverity",
    "ProductGateSpec",
    "ProductGateStatus",
]
