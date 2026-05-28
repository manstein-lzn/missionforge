"""Deterministic local validators."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    EvidenceTrustLevel,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    validate_ref,
)
from .evidence_store import EvidenceLedger, InMemoryEvidenceStore
from .verification import ValidatorResult, ValidatorSpec


def run_validator(
    spec: ValidatorSpec,
    *,
    workspace: str | Path = ".",
    evidence_store: EvidenceLedger | None = None,
) -> ValidatorResult:
    """Execute one deterministic local validator."""

    spec.validate()
    store = evidence_store or InMemoryEvidenceStore()
    validator_type = spec.type
    if validator_type == "file_exists":
        return _file_exists(spec, workspace=workspace, evidence_store=store)
    if validator_type == "file_contains":
        return _file_contains(spec, workspace=workspace, evidence_store=store)
    if validator_type == "forbidden_path":
        return _forbidden_path(spec, workspace=workspace, evidence_store=store)
    if validator_type == "json_field_exists":
        return _json_field_exists(spec, workspace=workspace, evidence_store=store)
    if validator_type == "artifact_hash":
        return _artifact_hash(spec, workspace=workspace, evidence_store=store)
    if validator_type == "command":
        return _command(spec, workspace=workspace, evidence_store=store)
    raise ContractValidationError(f"unsupported executable validator type: {validator_type}")


def _file_exists(
    spec: ValidatorSpec,
    *,
    workspace: str | Path,
    evidence_store: EvidenceLedger,
) -> ValidatorResult:
    path_ref = _input_ref(spec.inputs)
    path = _resolve_ref(workspace, path_ref)
    exists = path.exists()
    evidence_ref = evidence_store.append(
        payload={"validator_id": spec.validator_id, "type": spec.type, "path": path_ref, "exists": exists},
        trust_level=EvidenceTrustLevel.SCHEMA_VALIDATION,
        kind="validator_result",
    )
    return ValidatorResult(
        validator_id=spec.validator_id,
        passed=exists,
        evidence_refs=[evidence_ref.evidence_id],
        message="exists" if exists else f"missing path: {path_ref}",
    )


def _file_contains(
    spec: ValidatorSpec,
    *,
    workspace: str | Path,
    evidence_store: EvidenceLedger,
) -> ValidatorResult:
    path_ref = _input_ref(spec.inputs)
    contains = spec.inputs.get("contains")
    not_contains = spec.inputs.get("not_contains")
    if contains is None and not_contains is None:
        raise ContractValidationError("file_contains requires contains or not_contains input")
    if contains is not None:
        contains = require_non_empty_str(contains, "validator.inputs.contains")
    if not_contains is not None:
        not_contains = require_non_empty_str(not_contains, "validator.inputs.not_contains")
    path = _resolve_ref(workspace, path_ref)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    passed = path.exists()
    if contains is not None:
        passed = passed and contains in text
    if not_contains is not None:
        passed = passed and not_contains not in text
    evidence_ref = evidence_store.append(
        payload={
            "validator_id": spec.validator_id,
            "type": spec.type,
            "path": path_ref,
            "contains": contains,
            "not_contains": not_contains,
            "passed": passed,
        },
        trust_level=EvidenceTrustLevel.SCHEMA_VALIDATION,
        kind="validator_result",
    )
    return ValidatorResult(
        validator_id=spec.validator_id,
        passed=passed,
        evidence_refs=[evidence_ref.evidence_id],
        message="content check passed" if passed else f"content check failed: {path_ref}",
    )


def _forbidden_path(
    spec: ValidatorSpec,
    *,
    workspace: str | Path,
    evidence_store: EvidenceLedger,
) -> ValidatorResult:
    path_ref = _input_ref(spec.inputs)
    path = _resolve_ref(workspace, path_ref)
    passed = not path.exists()
    evidence_ref = evidence_store.append(
        payload={"validator_id": spec.validator_id, "type": spec.type, "path": path_ref, "exists": path.exists()},
        trust_level=EvidenceTrustLevel.SCHEMA_VALIDATION,
        kind="validator_result",
    )
    return ValidatorResult(
        validator_id=spec.validator_id,
        passed=passed,
        evidence_refs=[evidence_ref.evidence_id],
        message="forbidden path absent" if passed else f"forbidden path exists: {path_ref}",
    )


def _json_field_exists(
    spec: ValidatorSpec,
    *,
    workspace: str | Path,
    evidence_store: EvidenceLedger,
) -> ValidatorResult:
    path_ref = _input_ref(spec.inputs)
    field = require_non_empty_str(spec.inputs.get("field"), "validator.inputs.field")
    path = _resolve_ref(workspace, path_ref)
    passed = False
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        passed = _has_field(data, field)
    evidence_ref = evidence_store.append(
        payload={"validator_id": spec.validator_id, "type": spec.type, "path": path_ref, "field": field, "passed": passed},
        trust_level=EvidenceTrustLevel.SCHEMA_VALIDATION,
        kind="validator_result",
    )
    return ValidatorResult(
        validator_id=spec.validator_id,
        passed=passed,
        evidence_refs=[evidence_ref.evidence_id],
        message="json field exists" if passed else f"missing json field: {field}",
    )


def _artifact_hash(
    spec: ValidatorSpec,
    *,
    workspace: str | Path,
    evidence_store: EvidenceLedger,
) -> ValidatorResult:
    path_ref = _input_ref(spec.inputs)
    expected = require_non_empty_str(spec.inputs.get("sha256"), "validator.inputs.sha256")
    path = _resolve_ref(workspace, path_ref)
    actual = _sha256(path) if path.exists() else None
    passed = actual == expected
    evidence_ref = evidence_store.append(
        payload={
            "validator_id": spec.validator_id,
            "type": spec.type,
            "path": path_ref,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "passed": passed,
        },
        trust_level=EvidenceTrustLevel.SCHEMA_VALIDATION,
        kind="validator_result",
    )
    return ValidatorResult(
        validator_id=spec.validator_id,
        passed=passed,
        evidence_refs=[evidence_ref.evidence_id],
        message="artifact hash matched" if passed else f"artifact hash mismatch: {path_ref}",
    )


def _command(
    spec: ValidatorSpec,
    *,
    workspace: str | Path,
    evidence_store: EvidenceLedger,
) -> ValidatorResult:
    command = _command_input(spec.inputs)
    timeout = require_int_at_least(spec.inputs.get("timeout", 30), "validator.inputs.timeout", 1)
    expected_exit_code = require_int_at_least(
        spec.inputs.get("expected_exit_code", 0),
        "validator.inputs.expected_exit_code",
        0,
    )
    completed = subprocess.run(
        command,
        cwd=Path(workspace),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    passed = completed.returncode == expected_exit_code
    evidence_ref = evidence_store.append(
        payload={
            "validator_id": spec.validator_id,
            "type": spec.type,
            "command": command,
            "exit_code": completed.returncode,
            "expected_exit_code": expected_exit_code,
            "stdout_summary": _summary(completed.stdout),
            "stderr_summary": _summary(completed.stderr),
            "passed": passed,
        },
        trust_level=EvidenceTrustLevel.COMMAND_RESULT,
        kind="validator_result",
    )
    return ValidatorResult(
        validator_id=spec.validator_id,
        passed=passed,
        evidence_refs=[evidence_ref.evidence_id],
        message="command passed" if passed else f"command exited {completed.returncode}",
    )


def _input_ref(inputs: Mapping[str, Any]) -> str:
    data = require_mapping(inputs, "validator.inputs")
    raw_ref = data.get("path", data.get("ref"))
    return validate_ref(raw_ref, "validator.inputs.path")


def _resolve_ref(workspace: str | Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "validator.inputs.path")
    root = Path(workspace).resolve()
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("validator input path escapes workspace")
    return path


def _has_field(data: Any, field: str) -> bool:
    current = data
    for part in field.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _command_input(inputs: Mapping[str, Any]) -> list[str]:
    data = require_mapping(inputs, "validator.inputs")
    command = data.get("command")
    if isinstance(command, str):
        return shlex.split(command)
    if isinstance(command, list) and all(isinstance(item, str) and item for item in command):
        return list(command)
    raise ContractValidationError("validator.inputs.command must be a string or list of strings")


def _summary(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[truncated]"
