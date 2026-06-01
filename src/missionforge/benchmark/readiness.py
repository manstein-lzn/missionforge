"""Readiness contracts for value benchmark execution gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Self

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_non_empty_str,
    require_str,
    require_str_list,
    validate_ref,
)
from .contracts import BenchmarkMode

BENCHMARK_READINESS_CHECK_SCHEMA_VERSION = "missionforge.benchmark_readiness_check.v1"
BENCHMARK_READINESS_REPORT_SCHEMA_VERSION = "missionforge.benchmark_readiness_report.v1"


class BenchmarkReadinessStatus(StrEnum):
    """Readiness state for benchmark execution."""

    READY = "ready"
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class BenchmarkReadinessCheck:
    """One prerequisite check for a value benchmark run."""

    check_id: str
    status: BenchmarkReadinessStatus
    reason: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    schema_version: str = BENCHMARK_READINESS_CHECK_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "benchmark_readiness_check",
            {"schema_version", "check_id", "status", "reason", "evidence_refs"},
        )
        check = cls(
            check_id=_require_id(data.get("check_id"), "benchmark_readiness_check.check_id"),
            status=require_enum(
                data.get("status"),
                BenchmarkReadinessStatus,
                "benchmark_readiness_check.status",
            ),
            reason=require_str(data.get("reason", ""), "benchmark_readiness_check.reason"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "benchmark_readiness_check.evidence_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", BENCHMARK_READINESS_CHECK_SCHEMA_VERSION),
                "benchmark_readiness_check.schema_version",
            ),
        )
        check.validate()
        return check

    def validate(self) -> None:
        if self.schema_version != BENCHMARK_READINESS_CHECK_SCHEMA_VERSION:
            raise ContractValidationError("benchmark_readiness_check.schema_version is unsupported")
        _require_id(self.check_id, "benchmark_readiness_check.check_id")
        if not isinstance(self.status, BenchmarkReadinessStatus):
            raise ContractValidationError("benchmark_readiness_check.status must be BenchmarkReadinessStatus")
        require_str(self.reason, "benchmark_readiness_check.reason")
        _validate_ref_list(self.evidence_refs, "benchmark_readiness_check.evidence_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "benchmark_readiness_check")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "check_id": self.check_id,
            "status": self.status.value,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class BenchmarkReadinessReport:
    """Refs-first readiness gate output for a benchmark run."""

    benchmark_run_id: str
    status: BenchmarkReadinessStatus
    modes: list[BenchmarkMode]
    checks: list[BenchmarkReadinessCheck]
    ready_modes: list[BenchmarkMode] = field(default_factory=list)
    reason: str = ""
    schema_version: str = BENCHMARK_READINESS_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "benchmark_readiness_report",
            {"schema_version", "benchmark_run_id", "status", "modes", "ready_modes", "checks", "reason"},
        )
        report = cls(
            benchmark_run_id=_require_id(data.get("benchmark_run_id"), "benchmark_readiness_report.benchmark_run_id"),
            status=require_enum(
                data.get("status"),
                BenchmarkReadinessStatus,
                "benchmark_readiness_report.status",
            ),
            modes=[BenchmarkMode(require_non_empty_str(item, "benchmark_readiness_report.modes[]")) for item in data.get("modes", [])],
            ready_modes=[
                BenchmarkMode(require_non_empty_str(item, "benchmark_readiness_report.ready_modes[]"))
                for item in data.get("ready_modes", [])
            ],
            checks=[BenchmarkReadinessCheck.from_dict(_require_mapping(item, "benchmark_readiness_report.checks[]")) for item in data.get("checks", [])],
            reason=require_str(data.get("reason", ""), "benchmark_readiness_report.reason"),
            schema_version=require_non_empty_str(
                data.get("schema_version", BENCHMARK_READINESS_REPORT_SCHEMA_VERSION),
                "benchmark_readiness_report.schema_version",
            ),
        )
        report.validate()
        return report

    def validate(self) -> None:
        if self.schema_version != BENCHMARK_READINESS_REPORT_SCHEMA_VERSION:
            raise ContractValidationError("benchmark_readiness_report.schema_version is unsupported")
        _require_id(self.benchmark_run_id, "benchmark_readiness_report.benchmark_run_id")
        if not isinstance(self.status, BenchmarkReadinessStatus):
            raise ContractValidationError("benchmark_readiness_report.status must be BenchmarkReadinessStatus")
        if not self.modes:
            raise ContractValidationError("benchmark_readiness_report.modes must not be empty")
        for mode in self.modes:
            if not isinstance(mode, BenchmarkMode):
                raise ContractValidationError("benchmark_readiness_report.modes[] must be BenchmarkMode")
        for mode in self.ready_modes:
            if not isinstance(mode, BenchmarkMode):
                raise ContractValidationError("benchmark_readiness_report.ready_modes[] must be BenchmarkMode")
            if mode not in self.modes:
                raise ContractValidationError("benchmark_readiness_report.ready_modes[] must be selected modes")
        if self.status == BenchmarkReadinessStatus.READY and set(self.ready_modes) != set(self.modes):
            raise ContractValidationError("benchmark_readiness_report.ready status requires all selected modes ready")
        if self.status != BenchmarkReadinessStatus.READY and self.ready_modes:
            raise ContractValidationError("benchmark_readiness_report non-ready status must not expose ready modes")
        if not self.checks:
            raise ContractValidationError("benchmark_readiness_report.checks must not be empty")
        for check in self.checks:
            check.validate()
        require_str(self.reason, "benchmark_readiness_report.reason")
        assert_refs_only_payload(self.to_dict_without_validation(), "benchmark_readiness_report")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_run_id": self.benchmark_run_id,
            "status": self.status.value,
            "modes": [mode.value for mode in self.modes],
            "ready_modes": [mode.value for mode in self.ready_modes],
            "checks": [check.to_dict() for check in self.checks],
            "reason": self.reason,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def build_readiness_report(*, benchmark_run_id: str, modes: list[BenchmarkMode], checks: list[BenchmarkReadinessCheck]) -> BenchmarkReadinessReport:
    if any(check.status == BenchmarkReadinessStatus.BLOCKED for check in checks):
        status = BenchmarkReadinessStatus.BLOCKED
        reason = "one or more benchmark prerequisites are blocked"
        ready_modes: list[BenchmarkMode] = []
    elif any(check.status == BenchmarkReadinessStatus.UNAVAILABLE for check in checks):
        status = BenchmarkReadinessStatus.UNAVAILABLE
        reason = "one or more benchmark prerequisites are unavailable"
        ready_modes = []
    else:
        status = BenchmarkReadinessStatus.READY
        reason = "all selected benchmark prerequisites are ready"
        ready_modes = list(modes)
    report = BenchmarkReadinessReport(
        benchmark_run_id=benchmark_run_id,
        status=status,
        modes=list(modes),
        ready_modes=ready_modes,
        checks=list(checks),
        reason=reason,
    )
    report.validate()
    return report


def _strict_mapping(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = _require_mapping(value, field_name)
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unsupported fields: {extra}")
    return dict(data)


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} must be an object")
    return {str(key): item for key, item in value.items()}


def _require_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a safe id, not a path")
    return text


def _validate_ref_list(values: list[str], field_name: str) -> None:
    require_str_list(values, field_name)
    for ref in values:
        validate_ref(ref, f"{field_name}[]")
