"""ContextPackage restore checks.

This module is product-neutral. It validates whether a previously persisted
ContextPackage can be reused directly for a role, or whether the caller must
ask ContextEngine/runtime to recompile from refs, checkpoints, and working
sets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_bool,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from .context_engine import ContextPackage
from .ref_store import FileRefStore, RefStore


CONTEXT_PACKAGE_RESTORE_EXPECTATION_SCHEMA_VERSION = "missionforge.context_package_restore_expectation.v1"
CONTEXT_PACKAGE_RESTORE_DECISION_SCHEMA_VERSION = "missionforge.context_package_restore_decision.v1"


class ContextPackageRestoreStatus(StrEnum):
    """Direct ContextPackage restore decision."""

    REUSABLE = "reusable"
    STALE = "stale"
    INVALID = "invalid"


@dataclass(frozen=True)
class ContextPackageRestoreExpectation:
    """Hard fingerprints a package must match before direct reuse."""

    role: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    contract_ref: str | None = None
    contract_hash: str | None = None
    permission_manifest_ref: str | None = None
    permission_manifest_hash: str | None = None
    step_spec_hash: str | None = None
    tool_schema_hash: str | None = None
    context_compiler_version: str | None = None
    visible_ref_hashes: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = CONTEXT_PACKAGE_RESTORE_EXPECTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextPackageRestoreExpectation":
        data = require_mapping(payload, "context_package_restore_expectation")
        expectation = cls(
            role=_optional_str(data.get("role"), "context_package_restore_expectation.role"),
            run_id=_optional_str(data.get("run_id"), "context_package_restore_expectation.run_id"),
            step_id=_optional_str(data.get("step_id"), "context_package_restore_expectation.step_id"),
            contract_ref=_optional_ref(
                data.get("contract_ref"),
                "context_package_restore_expectation.contract_ref",
            ),
            contract_hash=_optional_hash(
                data.get("contract_hash"),
                "context_package_restore_expectation.contract_hash",
            ),
            permission_manifest_ref=_optional_ref(
                data.get("permission_manifest_ref"),
                "context_package_restore_expectation.permission_manifest_ref",
            ),
            permission_manifest_hash=_optional_hash(
                data.get("permission_manifest_hash"),
                "context_package_restore_expectation.permission_manifest_hash",
            ),
            step_spec_hash=_optional_hash(
                data.get("step_spec_hash"),
                "context_package_restore_expectation.step_spec_hash",
            ),
            tool_schema_hash=_optional_hash(
                data.get("tool_schema_hash"),
                "context_package_restore_expectation.tool_schema_hash",
            ),
            context_compiler_version=_optional_str(
                data.get("context_compiler_version"),
                "context_package_restore_expectation.context_compiler_version",
            ),
            visible_ref_hashes=_hash_mapping(
                data.get("visible_ref_hashes", {}),
                "context_package_restore_expectation.visible_ref_hashes",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_PACKAGE_RESTORE_EXPECTATION_SCHEMA_VERSION),
                "context_package_restore_expectation.schema_version",
            ),
        )
        expectation.validate()
        return expectation

    def validate(self) -> None:
        if self.schema_version != CONTEXT_PACKAGE_RESTORE_EXPECTATION_SCHEMA_VERSION:
            raise ContractValidationError("context_package_restore_expectation.schema_version is unsupported")
        _optional_str(self.role, "context_package_restore_expectation.role")
        _optional_str(self.run_id, "context_package_restore_expectation.run_id")
        _optional_str(self.step_id, "context_package_restore_expectation.step_id")
        _optional_ref(self.contract_ref, "context_package_restore_expectation.contract_ref")
        _optional_hash(self.contract_hash, "context_package_restore_expectation.contract_hash")
        _optional_ref(
            self.permission_manifest_ref,
            "context_package_restore_expectation.permission_manifest_ref",
        )
        _optional_hash(
            self.permission_manifest_hash,
            "context_package_restore_expectation.permission_manifest_hash",
        )
        _optional_hash(self.step_spec_hash, "context_package_restore_expectation.step_spec_hash")
        _optional_hash(self.tool_schema_hash, "context_package_restore_expectation.tool_schema_hash")
        _optional_str(
            self.context_compiler_version,
            "context_package_restore_expectation.context_compiler_version",
        )
        _hash_mapping(self.visible_ref_hashes, "context_package_restore_expectation.visible_ref_hashes")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = {
            "schema_version": self.schema_version,
            "role": self.role,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "permission_manifest_ref": self.permission_manifest_ref,
            "permission_manifest_hash": self.permission_manifest_hash,
            "step_spec_hash": self.step_spec_hash,
            "tool_schema_hash": self.tool_schema_hash,
            "context_compiler_version": self.context_compiler_version,
            "visible_ref_hashes": dict(self.visible_ref_hashes),
        }
        assert_refs_only_payload(payload, "context_package_restore_expectation")
        return payload


@dataclass(frozen=True)
class ContextPackageRestoreDecision:
    """Refs-only restore decision for one ContextPackage."""

    package_ref: str
    status: ContextPackageRestoreStatus
    reason_codes: list[str] = field(default_factory=list)
    recompile_required: bool = False
    package_hash: str = ""
    role: str = ""
    run_id: str = ""
    step_id: str = ""
    context_view_ref: str = ""
    context_hash: str = ""
    turn_safe_point_ref: str = ""
    checkpoint_ref: str = ""
    working_set_ref: str = ""
    schema_version: str = CONTEXT_PACKAGE_RESTORE_DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextPackageRestoreDecision":
        data = require_mapping(payload, "context_package_restore_decision")
        decision = cls(
            package_ref=validate_ref(data.get("package_ref"), "context_package_restore_decision.package_ref"),
            status=require_enum(
                data.get("status"),
                ContextPackageRestoreStatus,
                "context_package_restore_decision.status",
            ),
            reason_codes=require_str_list(
                data.get("reason_codes", []),
                "context_package_restore_decision.reason_codes",
            ),
            recompile_required=require_bool(
                data.get("recompile_required", False),
                "context_package_restore_decision.recompile_required",
            ),
            package_hash=_optional_hash(data.get("package_hash"), "context_package_restore_decision.package_hash")
            or "",
            role=_optional_str(data.get("role"), "context_package_restore_decision.role") or "",
            run_id=_optional_str(data.get("run_id"), "context_package_restore_decision.run_id") or "",
            step_id=_optional_str(data.get("step_id"), "context_package_restore_decision.step_id") or "",
            context_view_ref=_optional_ref(
                data.get("context_view_ref"),
                "context_package_restore_decision.context_view_ref",
            )
            or "",
            context_hash=_optional_hash(data.get("context_hash"), "context_package_restore_decision.context_hash")
            or "",
            turn_safe_point_ref=_optional_ref(
                data.get("turn_safe_point_ref"),
                "context_package_restore_decision.turn_safe_point_ref",
            )
            or "",
            checkpoint_ref=_optional_ref(
                data.get("checkpoint_ref"),
                "context_package_restore_decision.checkpoint_ref",
            )
            or "",
            working_set_ref=_optional_ref(
                data.get("working_set_ref"),
                "context_package_restore_decision.working_set_ref",
            )
            or "",
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_PACKAGE_RESTORE_DECISION_SCHEMA_VERSION),
                "context_package_restore_decision.schema_version",
            ),
        )
        decision.validate()
        return decision

    def validate(self) -> None:
        if self.schema_version != CONTEXT_PACKAGE_RESTORE_DECISION_SCHEMA_VERSION:
            raise ContractValidationError("context_package_restore_decision.schema_version is unsupported")
        validate_ref(self.package_ref, "context_package_restore_decision.package_ref")
        require_enum(self.status, ContextPackageRestoreStatus, "context_package_restore_decision.status")
        require_str_list(self.reason_codes, "context_package_restore_decision.reason_codes")
        require_bool(self.recompile_required, "context_package_restore_decision.recompile_required")
        _optional_hash(self.package_hash or None, "context_package_restore_decision.package_hash")
        _optional_ref(self.context_view_ref or None, "context_package_restore_decision.context_view_ref")
        _optional_hash(self.context_hash or None, "context_package_restore_decision.context_hash")
        _optional_ref(self.turn_safe_point_ref or None, "context_package_restore_decision.turn_safe_point_ref")
        _optional_ref(self.checkpoint_ref or None, "context_package_restore_decision.checkpoint_ref")
        _optional_ref(self.working_set_ref or None, "context_package_restore_decision.working_set_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = {
            "schema_version": self.schema_version,
            "package_ref": self.package_ref,
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
            "recompile_required": self.recompile_required,
            "package_hash": self.package_hash,
            "role": self.role,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "context_view_ref": self.context_view_ref,
            "context_hash": self.context_hash,
            "turn_safe_point_ref": self.turn_safe_point_ref,
            "checkpoint_ref": self.checkpoint_ref,
            "working_set_ref": self.working_set_ref,
        }
        assert_refs_only_payload(payload, "context_package_restore_decision")
        return payload


def evaluate_context_package_ref(
    workspace: Any,
    package_ref: str,
    *,
    expectation: ContextPackageRestoreExpectation | None = None,
) -> ContextPackageRestoreDecision:
    """Evaluate whether a package ref can be reused directly."""

    safe_ref = validate_ref(package_ref, "context_package_restore.package_ref")
    store = _store_for(workspace)
    if not store.exists(safe_ref):
        return ContextPackageRestoreDecision(
            package_ref=safe_ref,
            status=ContextPackageRestoreStatus.INVALID,
            reason_codes=["context_package_missing"],
            recompile_required=True,
        )
    try:
        package = ContextPackage.from_dict(store.read_json(safe_ref))
    except (ContractValidationError, OSError, ValueError):
        return ContextPackageRestoreDecision(
            package_ref=safe_ref,
            status=ContextPackageRestoreStatus.INVALID,
            reason_codes=["context_package_invalid"],
            recompile_required=True,
        )
    return evaluate_context_package_restore(
        package,
        package_ref=safe_ref,
        workspace=store,
        expectation=expectation,
    )


def evaluate_context_package_restore(
    package: ContextPackage,
    *,
    package_ref: str,
    workspace: Any | None = None,
    expectation: ContextPackageRestoreExpectation | None = None,
) -> ContextPackageRestoreDecision:
    """Evaluate hard ContextPackage fingerprints.

    A reusable decision means the package can be used as the restored package
    for the same role. Any stale or invalid decision requires recompile or
    denial before provider use.
    """

    package.validate()
    safe_ref = validate_ref(package_ref, "context_package_restore.package_ref")
    expected = expectation or ContextPackageRestoreExpectation()
    reasons: list[str] = []

    _compare_optional(expected.role, package.role, "role_mismatch", reasons)
    _compare_optional(expected.run_id, package.run_id, "run_id_mismatch", reasons)
    _compare_optional(expected.step_id, package.step_id, "step_id_mismatch", reasons)
    _compare_optional(expected.contract_ref, package.contract_ref, "contract_ref_mismatch", reasons)
    _compare_optional(expected.contract_hash, package.contract_hash, "contract_hash_mismatch", reasons)
    _compare_optional(
        expected.permission_manifest_ref,
        package.permission_manifest_ref,
        "permission_manifest_ref_mismatch",
        reasons,
    )
    _compare_optional(
        expected.permission_manifest_hash,
        package.permission_manifest_hash,
        "permission_manifest_hash_mismatch",
        reasons,
    )
    _compare_optional(expected.step_spec_hash, package.step_spec_hash, "step_spec_hash_mismatch", reasons)
    _compare_optional(expected.tool_schema_hash, package.tool_schema_hash, "tool_schema_hash_mismatch", reasons)
    _compare_optional(
        expected.context_compiler_version,
        package.context_compiler_version,
        "context_compiler_version_mismatch",
        reasons,
    )

    if expected.visible_ref_hashes and dict(expected.visible_ref_hashes) != dict(package.visible_ref_hashes):
        reasons.append("expected_visible_ref_hashes_mismatch")

    if workspace is not None:
        _check_ref_hashes(
            workspace,
            package.visible_ref_hashes,
            missing_reason="visible_ref_missing",
            mismatch_reason="visible_ref_hash_mismatch",
            reasons=reasons,
        )
        _check_ref_hashes(
            workspace,
            package.context_record_hashes,
            missing_reason="context_record_missing",
            mismatch_reason="context_record_hash_mismatch",
            reasons=reasons,
        )

    invalid_reason_codes = {
        "role_mismatch",
        "run_id_mismatch",
        "step_id_mismatch",
        "permission_manifest_ref_mismatch",
        "context_package_missing",
        "context_package_invalid",
    }
    status = (
        ContextPackageRestoreStatus.REUSABLE
        if not reasons
        else ContextPackageRestoreStatus.INVALID
        if any(reason in invalid_reason_codes for reason in reasons)
        else ContextPackageRestoreStatus.STALE
    )
    return ContextPackageRestoreDecision(
        package_ref=safe_ref,
        status=status,
        reason_codes=_dedupe_reason_codes(reasons),
        recompile_required=status is not ContextPackageRestoreStatus.REUSABLE,
        package_hash=package.context_package_hash,
        role=package.role,
        run_id=package.run_id,
        step_id=package.step_id,
        context_view_ref=package.context_view_ref,
        context_hash=package.context_hash,
        turn_safe_point_ref=package.turn_safe_point_ref,
        checkpoint_ref=package.checkpoint_ref or "",
        working_set_ref=package.working_set_ref or "",
    )


def _check_ref_hashes(
    workspace: Any,
    expected_hashes: Mapping[str, str],
    *,
    missing_reason: str,
    mismatch_reason: str,
    reasons: list[str],
) -> None:
    for ref, expected_hash in expected_hashes.items():
        safe_ref = validate_ref(ref, "context_package_restore.hash_ref")
        store = _store_for(workspace)
        if not store.exists(safe_ref):
            reasons.append(missing_reason)
            continue
        if store.hash_ref(safe_ref) != expected_hash:
            reasons.append(mismatch_reason)


def _compare_optional(expected: str | None, actual: str | None, reason_code: str, reasons: list[str]) -> None:
    if expected is None:
        return
    if expected != actual:
        reasons.append(reason_code)


def _dedupe_reason_codes(reason_codes: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for code in reason_codes:
        value = require_non_empty_str(code, "context_package_restore.reason_code")
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _optional_str(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return require_non_empty_str(value, field_name)


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return validate_ref(value, field_name)


def _optional_hash(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    text = require_non_empty_str(value, field_name)
    if not text.startswith("sha256:") or len(text) != len("sha256:") + 64:
        raise ContractValidationError(f"{field_name} must be a sha256 hash")
    return text


def _hash_mapping(value: Any, field_name: str) -> dict[str, str]:
    data = require_mapping(value, field_name)
    result: dict[str, str] = {}
    for key, item in data.items():
        ref = validate_ref(key, f"{field_name}.key")
        result[ref] = _hash(item, f"{field_name}.{ref}")
    return result


def _hash(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if not text.startswith("sha256:") or len(text) != len("sha256:") + 64:
        raise ContractValidationError(f"{field_name} must be a sha256 hash")
    return text


def _store_for(workspace: Any) -> RefStore:
    if isinstance(workspace, (str, Path)):
        return FileRefStore(workspace)
    return workspace
