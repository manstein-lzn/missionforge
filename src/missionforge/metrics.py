"""Typed diagnostic metric contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


METRIC_EVENT_SCHEMA_VERSION = "missionforge.metric_event.v1"
METRIC_PROJECTION_SCHEMA_VERSION = "missionforge.metric_projection.v1"


class MetricTrustLevel(StrEnum):
    """Diagnostic trust levels for metric events."""

    RUNTIME_DIAGNOSTIC = "runtime_diagnostic"
    ADAPTER_DIAGNOSTIC = "adapter_diagnostic"
    WORKER_REPORTED = "worker_reported"
    PROVIDER_REPORTED = "provider_reported"
    OPERATOR_DIAGNOSTIC = "operator_diagnostic"
    STORE_DIAGNOSTIC = "store_diagnostic"
    INTEGRATION_DIAGNOSTIC = "integration_diagnostic"


METRIC_KINDS = {"counter", "gauge", "status", "duration", "summary"}
ALLOWED_MISSIONFORGE_METRIC_NAMESPACES = {
    "missionforge.runtime",
    "missionforge.verifier",
    "missionforge.worker.pi_agent",
    "missionforge.steering",
    "missionforge.operator.cli",
    "missionforge.operator.rpc",
    "missionforge.store.json",
}


@dataclass(frozen=True)
class MetricEvent:
    """Refs-first diagnostic metric event.

    Metric events are not evidence and must not carry raw prompts, transcripts,
    provider payloads, stdout/stderr bodies, artifact bodies, or secrets.
    """

    metric_id: str
    mission_run_id: str
    namespace: str
    metric_kind: str
    values: dict[str, Any] = field(default_factory=dict)
    trust_level: str = MetricTrustLevel.RUNTIME_DIAGNOSTIC.value
    source_ref: str = ""
    evidence_ref: str = ""
    run_ref: str = ""
    tags: list[str] = field(default_factory=list)
    schema_version: str = METRIC_EVENT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MetricEvent":
        data = require_mapping(payload, "metric_event")
        if data.get("schema_version") != METRIC_EVENT_SCHEMA_VERSION:
            raise ContractValidationError("metric_event.schema_version is unsupported")
        event = cls(
            metric_id=require_non_empty_str(data.get("metric_id"), "metric_event.metric_id"),
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "metric_event.mission_run_id"),
            namespace=require_non_empty_str(data.get("namespace"), "metric_event.namespace"),
            metric_kind=require_non_empty_str(data.get("metric_kind"), "metric_event.metric_kind"),
            values=require_mapping(data.get("values", {}), "metric_event.values"),
            trust_level=require_non_empty_str(data.get("trust_level"), "metric_event.trust_level"),
            source_ref=data.get("source_ref", ""),
            evidence_ref=data.get("evidence_ref", ""),
            run_ref=data.get("run_ref", ""),
            tags=require_str_list(data.get("tags", []), "metric_event.tags"),
            schema_version=require_non_empty_str(data.get("schema_version"), "metric_event.schema_version"),
        )
        event.validate()
        return event

    def validate(self) -> None:
        require_non_empty_str(self.metric_id, "metric_event.metric_id")
        require_non_empty_str(self.mission_run_id, "metric_event.mission_run_id")
        validate_metric_namespace(self.namespace)
        if self.metric_kind not in METRIC_KINDS:
            raise ContractValidationError(f"metric_event.metric_kind must be one of {sorted(METRIC_KINDS)}")
        if self.trust_level not in {level.value for level in MetricTrustLevel}:
            raise ContractValidationError(
                f"metric_event.trust_level must be one of {sorted(level.value for level in MetricTrustLevel)}"
            )
        if self.source_ref:
            validate_ref(self.source_ref, "metric_event.source_ref")
        if self.evidence_ref:
            validate_ref(self.evidence_ref, "metric_event.evidence_ref")
        if self.run_ref:
            validate_ref(self.run_ref, "metric_event.run_ref")
        if not any([self.source_ref, self.evidence_ref, self.run_ref]):
            raise ContractValidationError("metric_event requires source_ref, evidence_ref, or run_ref")
        require_str_list(self.tags, "metric_event.tags")
        _validate_metric_values(self.values, "metric_event.values")
        assert_refs_only_payload({"values": self.values}, "metric_event")
        if self.schema_version != METRIC_EVENT_SCHEMA_VERSION:
            raise ContractValidationError("metric_event.schema_version is unsupported")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "metric_id": self.metric_id,
            "mission_run_id": self.mission_run_id,
            "namespace": self.namespace,
            "source_ref": self.source_ref,
            "evidence_ref": self.evidence_ref,
            "run_ref": self.run_ref,
            "metric_kind": self.metric_kind,
            "values": ensure_json_value(self.values, "metric_event.values"),
            "trust_level": self.trust_level,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class MetricProjection:
    """Deterministic operator-facing metric summary."""

    mission_run_id: str
    metric_event_refs: list[str] = field(default_factory=list)
    namespaces: dict[str, dict[str, Any]] = field(default_factory=dict)
    diagnostic_flags: list[str] = field(default_factory=list)
    schema_version: str = METRIC_PROJECTION_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MetricProjection":
        data = require_mapping(payload, "metric_projection")
        if data.get("schema_version") != METRIC_PROJECTION_SCHEMA_VERSION:
            raise ContractValidationError("metric_projection.schema_version is unsupported")
        namespaces_payload = require_mapping(data.get("namespaces", {}), "metric_projection.namespaces")
        projection = cls(
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "metric_projection.mission_run_id"),
            metric_event_refs=require_str_list(
                data.get("metric_event_refs", []),
                "metric_projection.metric_event_refs",
            ),
            namespaces={
                require_non_empty_str(namespace, "metric_projection.namespaces[]"): require_mapping(
                    values,
                    f"metric_projection.namespaces.{namespace}",
                )
                for namespace, values in namespaces_payload.items()
            },
            diagnostic_flags=require_str_list(
                data.get("diagnostic_flags", []),
                "metric_projection.diagnostic_flags",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version"),
                "metric_projection.schema_version",
            ),
        )
        projection.validate()
        return projection

    def validate(self) -> None:
        require_non_empty_str(self.mission_run_id, "metric_projection.mission_run_id")
        for ref in self.metric_event_refs:
            validate_ref(ref, "metric_projection.metric_event_refs[]")
        for namespace, values in self.namespaces.items():
            validate_metric_namespace(namespace)
            _validate_metric_values(values, f"metric_projection.namespaces.{namespace}")
            assert_refs_only_payload({"values": values}, f"metric_projection.namespaces.{namespace}")
        require_str_list(self.diagnostic_flags, "metric_projection.diagnostic_flags")
        if self.schema_version != METRIC_PROJECTION_SCHEMA_VERSION:
            raise ContractValidationError("metric_projection.schema_version is unsupported")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "mission_run_id": self.mission_run_id,
            "metric_event_refs": list(self.metric_event_refs),
            "namespaces": {
                namespace: ensure_json_value(values, f"metric_projection.namespaces.{namespace}")
                for namespace, values in sorted(self.namespaces.items())
            },
            "diagnostic_flags": sorted(set(self.diagnostic_flags)),
        }


def validate_metric_namespace(namespace: str) -> str:
    safe = require_non_empty_str(namespace, "metric_namespace")
    parts = safe.split(".")
    if any(not part or part.lower() != part or not part.replace("_", "").isalnum() for part in parts):
        raise ContractValidationError("metric namespace must be lower-case dotted alphanumeric names")
    if parts[0] not in {"missionforge", "integration"}:
        raise ContractValidationError("metric namespace must start with missionforge or integration")
    if parts[0] == "missionforge" and len(parts) < 2:
        raise ContractValidationError("missionforge metric namespace requires a module segment")
    if parts[0] == "integration" and len(parts) < 2:
        raise ContractValidationError("integration metric namespace requires a product segment")
    if parts[0] == "missionforge" and not any(
        safe == allowed or safe.startswith(f"{allowed}.")
        for allowed in ALLOWED_MISSIONFORGE_METRIC_NAMESPACES
    ):
        raise ContractValidationError("metric namespace is not an allowed missionforge module namespace")
    return safe


def project_metric_events(
    *,
    mission_run_id: str,
    events: list[MetricEvent],
    metric_event_refs: list[str],
) -> MetricProjection:
    namespaces: dict[str, dict[str, Any]] = {}
    for event in sorted(events, key=lambda item: item.metric_id):
        event.validate()
        if event.mission_run_id != mission_run_id:
            raise ContractValidationError("metric projection cannot mix mission_run_id values")
        bucket = namespaces.setdefault(event.namespace, {})
        for key, value in sorted(event.values.items()):
            if _is_number(value) and _is_number(bucket.get(key)):
                bucket[key] = bucket[key] + value
            else:
                bucket[key] = value
    return MetricProjection(
        mission_run_id=mission_run_id,
        metric_event_refs=list(metric_event_refs),
        namespaces=namespaces,
        diagnostic_flags=_diagnostic_flags(namespaces),
    )


def safe_metric_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow scalar-only metric mapping."""

    result: dict[str, Any] = {}
    for key, value in require_mapping(values, "metric_values").items():
        if not isinstance(key, str) or not key:
            raise ContractValidationError("metric values keys must be non-empty strings")
        if value is None:
            continue
        if isinstance(value, (str, bool)) or (isinstance(value, (int, float)) and not isinstance(value, bool)):
            result[key] = ensure_json_value(value, f"metric_values.{key}")
    _validate_metric_values(result, "metric_values")
    assert_refs_only_payload({"values": result}, "metric_values")
    return result


def _validate_metric_values(values: Mapping[str, Any], field_name: str) -> None:
    normalized = ensure_json_value(require_mapping(values, field_name), field_name)
    for key, value in normalized.items():
        if not isinstance(key, str) or not key:
            raise ContractValidationError(f"{field_name} keys must be non-empty strings")
        if not _is_scalar_metric_value(value):
            raise ContractValidationError(f"{field_name}.{key} must be a scalar metric value")


def _diagnostic_flags(namespaces: Mapping[str, Mapping[str, Any]]) -> list[str]:
    flags: list[str] = []
    steering = namespaces.get("missionforge.steering", {})
    runtime = namespaces.get("missionforge.runtime", {})
    if steering.get("provider_failure_count"):
        flags.append("steering_provider_failure")
    if steering.get("rejected_proposal_count"):
        flags.append("steering_proposal_rejected")
    if steering.get("unsafe_proposal_rejection_count"):
        flags.append("unsafe_steering_proposal_rejected")
    if runtime.get("redesign_required"):
        flags.append("redesign_required")
    if runtime.get("repair_exhausted"):
        flags.append("repair_exhausted")
    return sorted(set(flags))


def _is_scalar_metric_value(value: Any) -> bool:
    return isinstance(value, (str, bool, int, float)) and not (
        isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")})
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
