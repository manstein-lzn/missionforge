"""Hidden/public acceptance checks for benchmark trials."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping, Self

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from .contracts import BenchmarkStatus, BenchmarkSummary


ACCEPTANCE_PACK_SCHEMA_VERSION = "missionforge.benchmark_acceptance_pack.v1"
ACCEPTANCE_RESULT_SCHEMA_VERSION = "missionforge.benchmark_acceptance_result.v1"


class AcceptanceVisibility(StrEnum):
    """Whether a check pack is worker-visible."""

    PUBLIC = "public"
    HIDDEN = "hidden"


class AcceptanceCheckKind(StrEnum):
    """Deterministic acceptance check kinds supported by the benchmark harness."""

    FILE_EXISTS = "file_exists"
    FILE_CONTAINS = "file_contains"
    FILE_NOT_CONTAINS = "file_not_contains"
    JSON_FIELD_EQUALS = "json_field_equals"


@dataclass(frozen=True)
class AcceptanceCheck:
    """One evaluator-only or public acceptance check."""

    check_id: str
    kind: AcceptanceCheckKind
    ref: str
    expected_text: str = ""
    forbidden_text: str = ""
    json_field: str = ""
    expected_value: Any = None
    blocking: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "acceptance_check",
            {
                "check_id",
                "kind",
                "ref",
                "expected_text",
                "forbidden_text",
                "json_field",
                "expected_value",
                "blocking",
            },
        )
        check = cls(
            check_id=require_non_empty_str(data.get("check_id"), "acceptance_check.check_id"),
            kind=require_enum(data.get("kind"), AcceptanceCheckKind, "acceptance_check.kind"),
            ref=validate_ref(data.get("ref"), "acceptance_check.ref"),
            expected_text=str(data.get("expected_text", "")),
            forbidden_text=str(data.get("forbidden_text", "")),
            json_field=str(data.get("json_field", "")),
            expected_value=ensure_json_value(data.get("expected_value"), "acceptance_check.expected_value")
            if "expected_value" in data
            else None,
            blocking=_require_bool(data.get("blocking", True), "acceptance_check.blocking"),
        )
        check.validate()
        return check

    def validate(self) -> None:
        require_non_empty_str(self.check_id, "acceptance_check.check_id")
        require_enum(self.kind, AcceptanceCheckKind, "acceptance_check.kind")
        validate_ref(self.ref, "acceptance_check.ref")
        if self.kind == AcceptanceCheckKind.FILE_CONTAINS and not self.expected_text:
            raise ContractValidationError("file_contains acceptance check requires expected_text")
        if self.kind == AcceptanceCheckKind.FILE_NOT_CONTAINS and not self.forbidden_text:
            raise ContractValidationError("file_not_contains acceptance check requires forbidden_text")
        if self.kind == AcceptanceCheckKind.JSON_FIELD_EQUALS and not self.json_field:
            raise ContractValidationError("json_field_equals acceptance check requires json_field")
        _require_bool(self.blocking, "acceptance_check.blocking")
        assert_refs_only_payload(self.to_dict(), "acceptance_check")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "check_id": self.check_id,
            "kind": self.kind.value,
            "ref": self.ref,
            "blocking": self.blocking,
        }
        if self.expected_text:
            payload["expected_text"] = self.expected_text
        if self.forbidden_text:
            payload["forbidden_text"] = self.forbidden_text
        if self.json_field:
            payload["json_field"] = self.json_field
        if self.expected_value is not None:
            payload["expected_value"] = ensure_json_value(self.expected_value, "acceptance_check.expected_value")
        return payload


@dataclass(frozen=True)
class AcceptancePack:
    """A deterministic acceptance pack referenced by BenchmarkTask.acceptance_refs."""

    pack_id: str
    task_id: str
    visibility: AcceptanceVisibility
    checks: list[AcceptanceCheck]
    rubric_ref: str = ""
    schema_version: str = ACCEPTANCE_PACK_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "acceptance_pack",
            {"schema_version", "pack_id", "task_id", "visibility", "checks", "rubric_ref"},
        )
        pack = cls(
            pack_id=require_non_empty_str(data.get("pack_id"), "acceptance_pack.pack_id"),
            task_id=require_non_empty_str(data.get("task_id"), "acceptance_pack.task_id"),
            visibility=require_enum(data.get("visibility"), AcceptanceVisibility, "acceptance_pack.visibility"),
            checks=[AcceptanceCheck.from_dict(require_mapping(item, "acceptance_pack.checks[]")) for item in data.get("checks", [])],
            rubric_ref=str(data.get("rubric_ref", "")),
            schema_version=require_non_empty_str(
                data.get("schema_version", ACCEPTANCE_PACK_SCHEMA_VERSION),
                "acceptance_pack.schema_version",
            ),
        )
        pack.validate()
        return pack

    def validate(self) -> None:
        if self.schema_version != ACCEPTANCE_PACK_SCHEMA_VERSION:
            raise ContractValidationError("acceptance_pack.schema_version is unsupported")
        require_non_empty_str(self.pack_id, "acceptance_pack.pack_id")
        require_non_empty_str(self.task_id, "acceptance_pack.task_id")
        require_enum(self.visibility, AcceptanceVisibility, "acceptance_pack.visibility")
        if not self.checks:
            raise ContractValidationError("acceptance_pack.checks must not be empty")
        check_ids = [check.check_id for check in self.checks]
        if len(set(check_ids)) != len(check_ids):
            raise ContractValidationError("acceptance_pack.check_id values must be unique")
        for check in self.checks:
            check.validate()
        if self.rubric_ref:
            validate_ref(self.rubric_ref, "acceptance_pack.rubric_ref")
        assert_refs_only_payload(self.to_dict(), "acceptance_pack")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pack_id": self.pack_id,
            "task_id": self.task_id,
            "visibility": self.visibility.value,
            "checks": [check.to_dict() for check in self.checks],
            "rubric_ref": self.rubric_ref,
        }


@dataclass(frozen=True)
class AcceptanceCheckResult:
    """Outcome for one check without embedding hidden expected strings."""

    check_id: str
    kind: AcceptanceCheckKind
    passed: bool
    blocking: bool = True
    evidence_refs: list[str] = field(default_factory=list)
    message: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "acceptance_check_result",
            {"check_id", "kind", "passed", "blocking", "evidence_refs", "message"},
        )
        result = cls(
            check_id=require_non_empty_str(data.get("check_id"), "acceptance_check_result.check_id"),
            kind=require_enum(data.get("kind"), AcceptanceCheckKind, "acceptance_check_result.kind"),
            passed=_require_bool(data.get("passed"), "acceptance_check_result.passed"),
            blocking=_require_bool(data.get("blocking", True), "acceptance_check_result.blocking"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "acceptance_check_result.evidence_refs"),
            message=str(data.get("message", "")),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.check_id, "acceptance_check_result.check_id")
        require_enum(self.kind, AcceptanceCheckKind, "acceptance_check_result.kind")
        _require_bool(self.passed, "acceptance_check_result.passed")
        _require_bool(self.blocking, "acceptance_check_result.blocking")
        for ref in self.evidence_refs:
            validate_ref(ref, "acceptance_check_result.evidence_refs[]")
        assert_refs_only_payload(self.to_dict(), "acceptance_check_result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "kind": self.kind.value,
            "passed": self.passed,
            "blocking": self.blocking,
            "evidence_refs": list(self.evidence_refs),
            "message": self.message,
        }


@dataclass(frozen=True)
class AcceptanceResult:
    """Result for one acceptance pack evaluation."""

    pack_id: str
    task_id: str
    visibility: AcceptanceVisibility
    passed: bool
    check_results: list[AcceptanceCheckResult]
    result_ref: str = ""
    schema_version: str = ACCEPTANCE_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "acceptance_result",
            {"schema_version", "pack_id", "task_id", "visibility", "passed", "check_results", "result_ref"},
        )
        result = cls(
            pack_id=require_non_empty_str(data.get("pack_id"), "acceptance_result.pack_id"),
            task_id=require_non_empty_str(data.get("task_id"), "acceptance_result.task_id"),
            visibility=require_enum(data.get("visibility"), AcceptanceVisibility, "acceptance_result.visibility"),
            passed=_require_bool(data.get("passed"), "acceptance_result.passed"),
            check_results=[
                AcceptanceCheckResult.from_dict(require_mapping(item, "acceptance_result.check_results[]"))
                for item in data.get("check_results", [])
            ],
            result_ref=str(data.get("result_ref", "")),
            schema_version=require_non_empty_str(
                data.get("schema_version", ACCEPTANCE_RESULT_SCHEMA_VERSION),
                "acceptance_result.schema_version",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != ACCEPTANCE_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("acceptance_result.schema_version is unsupported")
        require_non_empty_str(self.pack_id, "acceptance_result.pack_id")
        require_non_empty_str(self.task_id, "acceptance_result.task_id")
        require_enum(self.visibility, AcceptanceVisibility, "acceptance_result.visibility")
        _require_bool(self.passed, "acceptance_result.passed")
        if not self.check_results:
            raise ContractValidationError("acceptance_result.check_results must not be empty")
        for result in self.check_results:
            result.validate()
        if self.result_ref:
            validate_ref(self.result_ref, "acceptance_result.result_ref")
        assert_refs_only_payload(self.to_dict(), "acceptance_result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pack_id": self.pack_id,
            "task_id": self.task_id,
            "visibility": self.visibility.value,
            "passed": self.passed,
            "check_results": [result.to_dict() for result in self.check_results],
            "result_ref": self.result_ref,
        }


def load_acceptance_pack(workspace: str | Path, ref: str) -> AcceptancePack:
    """Load an acceptance pack from a workspace ref."""

    path = _resolve_ref(Path(workspace), ref)
    payload = require_mapping(json.loads(path.read_text(encoding="utf-8")), "acceptance_pack")
    return AcceptancePack.from_dict(payload)


def evaluate_acceptance_pack(
    *,
    workspace: str | Path,
    trial_workspace_ref: str,
    pack: AcceptancePack,
    result_ref: str = "",
) -> AcceptanceResult:
    """Evaluate a check pack against a trial workspace."""

    root = Path(workspace).resolve()
    trial_root = _resolve_ref(root, trial_workspace_ref)
    results = [_evaluate_check(root=root, trial_root=trial_root, trial_workspace_ref=trial_workspace_ref, check=check) for check in pack.checks]
    passed = all(result.passed or not result.blocking for result in results)
    acceptance = AcceptanceResult(
        pack_id=pack.pack_id,
        task_id=pack.task_id,
        visibility=pack.visibility,
        passed=passed,
        check_results=results,
        result_ref=result_ref,
    )
    acceptance.validate()
    return acceptance


def apply_hidden_acceptance(summary: BenchmarkSummary, result: AcceptanceResult) -> BenchmarkSummary:
    """Return a summary with hidden acceptance joined into accepted status."""

    result.validate()
    if result.visibility != AcceptanceVisibility.HIDDEN:
        raise ContractValidationError("apply_hidden_acceptance requires a hidden acceptance result")
    failure_taxonomy = list(summary.failure_taxonomy)
    if not result.passed and "hidden_acceptance_failed" not in failure_taxonomy:
        failure_taxonomy.append("hidden_acceptance_failed")
    accepted = summary.accepted and result.passed
    status = BenchmarkStatus.ACCEPTED if accepted else BenchmarkStatus.FAILED
    return replace(
        summary,
        accepted=accepted,
        status=status,
        hidden_acceptance_passed=result.passed,
        failure_taxonomy=sorted(set(failure_taxonomy)),
    )


def _evaluate_check(*, root: Path, trial_root: Path, trial_workspace_ref: str, check: AcceptanceCheck) -> AcceptanceCheckResult:
    target = (trial_root / check.ref).resolve()
    if trial_root not in target.parents and target != trial_root:
        raise ContractValidationError("acceptance check ref escapes trial workspace")
    evidence_ref = _join_ref(trial_workspace_ref, check.ref)
    exists = target.is_file()
    passed = False
    message = "failed"
    if check.kind == AcceptanceCheckKind.FILE_EXISTS:
        passed = exists
        message = "file exists" if passed else "file missing"
    elif check.kind == AcceptanceCheckKind.FILE_CONTAINS:
        text = target.read_text(encoding="utf-8") if exists else ""
        passed = check.expected_text in text
        message = "expected content present" if passed else "expected content missing"
    elif check.kind == AcceptanceCheckKind.FILE_NOT_CONTAINS:
        text = target.read_text(encoding="utf-8") if exists else ""
        passed = exists and check.forbidden_text not in text
        message = "forbidden content absent" if passed else "forbidden content present or file missing"
    elif check.kind == AcceptanceCheckKind.JSON_FIELD_EQUALS:
        value = _json_field(target, check.json_field) if exists else None
        passed = value == check.expected_value
        message = "json field matches" if passed else "json field mismatch"
    else:
        raise ContractValidationError("acceptance check kind is unsupported")
    return AcceptanceCheckResult(
        check_id=check.check_id,
        kind=check.kind,
        passed=passed,
        blocking=check.blocking,
        evidence_refs=[evidence_ref] if exists else [],
        message=message,
    )


def _json_field(path: Path, dotted_field: str) -> Any:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    for part in dotted_field.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return ensure_json_value(value, "acceptance_json_field")


def _resolve_ref(root: Path, ref: str) -> Path:
    safe = validate_ref(ref, "acceptance.ref")
    workspace = root.resolve()
    path = (workspace / safe).resolve()
    if workspace not in path.parents and path != workspace:
        raise ContractValidationError("acceptance ref escapes workspace")
    return path


def _join_ref(prefix: str, ref: str) -> str:
    safe_prefix = validate_ref(prefix, "acceptance.ref_prefix")
    safe_ref = validate_ref(ref, "acceptance.ref")
    return f"{safe_prefix.rstrip('/')}/{safe_ref.lstrip('/')}" if safe_prefix else safe_ref


def _strict_mapping(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(value, field_name)
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
    return data


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(f"{field_name} must be a boolean")
    return value


__all__ = [
    "ACCEPTANCE_PACK_SCHEMA_VERSION",
    "ACCEPTANCE_RESULT_SCHEMA_VERSION",
    "AcceptanceCheck",
    "AcceptanceCheckKind",
    "AcceptanceCheckResult",
    "AcceptancePack",
    "AcceptanceResult",
    "AcceptanceVisibility",
    "apply_hidden_acceptance",
    "evaluate_acceptance_pack",
    "load_acceptance_pack",
]
