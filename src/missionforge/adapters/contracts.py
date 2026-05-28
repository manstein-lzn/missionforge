"""Shared refs-only adapter contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..contracts import (
    ContractValidationError,
    ensure_json_value,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)


ADAPTER_RESULT_STATUSES = {"completed", "failed", "blocked", "unsupported"}
DIAGNOSTIC_SEVERITIES = {"info", "warning", "error"}
FORBIDDEN_RAW_FIELDS = {
    "access_token",
    "api_key",
    "body",
    "credential",
    "credentials",
    "id_token",
    "passphrase",
    "password",
    "payload",
    "private_key",
    "prompt",
    "raw",
    "raw_body",
    "raw_payload",
    "raw_prompt",
    "raw_transcript",
    "refresh_token",
    "secret",
    "secret_key",
    "transcript",
}
FORBIDDEN_KEY_FRAGMENTS = {"credential", "password", "prompt", "secret", "transcript"}
FORBIDDEN_KEY_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_body",
    "_payload",
    "_private_key",
    "_refresh_token",
)


@dataclass(frozen=True)
class AdapterBoundary:
    """Static declaration for an optional adapter boundary."""

    adapter_id: str
    adapter_type: str
    version: str
    input_contract_refs: list[str] = field(default_factory=list)
    output_contract_refs: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AdapterBoundary":
        data = _contract_mapping(
            payload,
            "adapter_boundary",
            {
                "adapter_id",
                "adapter_type",
                "version",
                "input_contract_refs",
                "output_contract_refs",
                "capabilities",
            },
        )
        boundary = cls(
            adapter_id=require_non_empty_str(data.get("adapter_id"), "adapter_boundary.adapter_id"),
            adapter_type=require_non_empty_str(data.get("adapter_type"), "adapter_boundary.adapter_type"),
            version=require_non_empty_str(data.get("version"), "adapter_boundary.version"),
            input_contract_refs=require_str_list(
                data.get("input_contract_refs", []),
                "adapter_boundary.input_contract_refs",
            ),
            output_contract_refs=require_str_list(
                data.get("output_contract_refs", []),
                "adapter_boundary.output_contract_refs",
            ),
            capabilities=require_str_list(data.get("capabilities", []), "adapter_boundary.capabilities"),
        )
        boundary.validate()
        return boundary

    @property
    def boundary_hash(self) -> str:
        return stable_json_hash(self.to_dict())

    def validate(self) -> None:
        require_non_empty_str(self.adapter_id, "adapter_boundary.adapter_id")
        require_non_empty_str(self.adapter_type, "adapter_boundary.adapter_type")
        require_non_empty_str(self.version, "adapter_boundary.version")
        for ref in self.input_contract_refs:
            validate_ref(ref, "adapter_boundary.input_contract_refs[]")
        for ref in self.output_contract_refs:
            validate_ref(ref, "adapter_boundary.output_contract_refs[]")
        require_str_list(self.capabilities, "adapter_boundary.capabilities")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "adapter_id": self.adapter_id,
            "adapter_type": self.adapter_type,
            "version": self.version,
            "input_contract_refs": list(self.input_contract_refs),
            "output_contract_refs": list(self.output_contract_refs),
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class AdapterInvocation:
    """One adapter invocation request expressed only through refs."""

    invocation_id: str
    adapter_id: str
    input_refs: list[str] = field(default_factory=list)
    config_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AdapterInvocation":
        data = _contract_mapping(
            payload,
            "adapter_invocation",
            {"invocation_id", "adapter_id", "input_refs", "config_refs", "evidence_refs"},
        )
        invocation = cls(
            invocation_id=require_non_empty_str(data.get("invocation_id"), "adapter_invocation.invocation_id"),
            adapter_id=require_non_empty_str(data.get("adapter_id"), "adapter_invocation.adapter_id"),
            input_refs=require_str_list(data.get("input_refs", []), "adapter_invocation.input_refs"),
            config_refs=require_str_list(data.get("config_refs", []), "adapter_invocation.config_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "adapter_invocation.evidence_refs"),
        )
        invocation.validate()
        return invocation

    def validate(self) -> None:
        require_non_empty_str(self.invocation_id, "adapter_invocation.invocation_id")
        require_non_empty_str(self.adapter_id, "adapter_invocation.adapter_id")
        for ref in self.input_refs:
            validate_ref(ref, "adapter_invocation.input_refs[]")
        for ref in self.config_refs:
            validate_ref(ref, "adapter_invocation.config_refs[]")
        for ref in self.evidence_refs:
            validate_ref(ref, "adapter_invocation.evidence_refs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "invocation_id": self.invocation_id,
            "adapter_id": self.adapter_id,
            "input_refs": list(self.input_refs),
            "config_refs": list(self.config_refs),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class AdapterDiagnostic:
    """Refs-backed adapter diagnostic summary."""

    diagnostic_id: str
    severity: str
    message: str
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AdapterDiagnostic":
        data = _contract_mapping(
            payload,
            "adapter_diagnostic",
            {"diagnostic_id", "severity", "message", "evidence_refs"},
        )
        diagnostic = cls(
            diagnostic_id=require_non_empty_str(data.get("diagnostic_id"), "adapter_diagnostic.diagnostic_id"),
            severity=require_non_empty_str(data.get("severity"), "adapter_diagnostic.severity"),
            message=require_non_empty_str(data.get("message"), "adapter_diagnostic.message"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "adapter_diagnostic.evidence_refs"),
        )
        diagnostic.validate()
        return diagnostic

    def validate(self) -> None:
        require_non_empty_str(self.diagnostic_id, "adapter_diagnostic.diagnostic_id")
        if self.severity not in DIAGNOSTIC_SEVERITIES:
            raise ContractValidationError(
                f"adapter_diagnostic.severity must be one of {sorted(DIAGNOSTIC_SEVERITIES)}"
            )
        require_non_empty_str(self.message, "adapter_diagnostic.message")
        for ref in self.evidence_refs:
            validate_ref(ref, "adapter_diagnostic.evidence_refs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "diagnostic_id": self.diagnostic_id,
            "severity": self.severity,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class AdapterResult:
    """Refs-only adapter result envelope."""

    invocation_id: str
    adapter_id: str
    status: str
    output_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    diagnostic_refs: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AdapterResult":
        data = _contract_mapping(
            payload,
            "adapter_result",
            {
                "invocation_id",
                "adapter_id",
                "status",
                "output_refs",
                "evidence_refs",
                "diagnostic_refs",
                "metrics",
            },
        )
        result = cls(
            invocation_id=require_non_empty_str(data.get("invocation_id"), "adapter_result.invocation_id"),
            adapter_id=require_non_empty_str(data.get("adapter_id"), "adapter_result.adapter_id"),
            status=require_non_empty_str(data.get("status"), "adapter_result.status"),
            output_refs=require_str_list(data.get("output_refs", []), "adapter_result.output_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "adapter_result.evidence_refs"),
            diagnostic_refs=require_str_list(data.get("diagnostic_refs", []), "adapter_result.diagnostic_refs"),
            metrics=ensure_json_value(require_mapping(data.get("metrics", {}), "adapter_result.metrics"), "adapter_result.metrics"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.invocation_id, "adapter_result.invocation_id")
        require_non_empty_str(self.adapter_id, "adapter_result.adapter_id")
        if self.status not in ADAPTER_RESULT_STATUSES:
            raise ContractValidationError(f"adapter_result.status must be one of {sorted(ADAPTER_RESULT_STATUSES)}")
        for ref in self.output_refs:
            validate_ref(ref, "adapter_result.output_refs[]")
        for ref in self.evidence_refs:
            validate_ref(ref, "adapter_result.evidence_refs[]")
        for ref in self.diagnostic_refs:
            validate_ref(ref, "adapter_result.diagnostic_refs[]")
        _reject_forbidden_raw_fields(self.metrics, "adapter_result.metrics")
        ensure_json_value(require_mapping(self.metrics, "adapter_result.metrics"), "adapter_result.metrics")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "invocation_id": self.invocation_id,
            "adapter_id": self.adapter_id,
            "status": self.status,
            "output_refs": list(self.output_refs),
            "evidence_refs": list(self.evidence_refs),
            "diagnostic_refs": list(self.diagnostic_refs),
            "metrics": ensure_json_value(self.metrics, "adapter_result.metrics"),
        }


def _contract_mapping(payload: Mapping[str, Any], field_name: str, allowed_keys: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    _reject_unknown_keys(data, field_name, allowed_keys)
    _reject_forbidden_raw_fields(data, field_name)
    return data


def _reject_unknown_keys(data: Mapping[str, Any], field_name: str, allowed_keys: set[str]) -> None:
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unsupported fields: {unknown}")


def _reject_forbidden_raw_fields(value: Any, field_name: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = key.lower()
            if (
                lowered in FORBIDDEN_RAW_FIELDS
                or any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS)
                or any(lowered.endswith(suffix) for suffix in FORBIDDEN_KEY_SUFFIXES)
            ):
                raise ContractValidationError(f"{field_name}.{key} is not allowed in adapter contracts")
            _reject_forbidden_raw_fields(item, f"{field_name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_raw_fields(item, f"{field_name}[{index}]")
