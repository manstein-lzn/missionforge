"""Context management policy contracts.

Policies are mechanical controls for MissionForge-owned context maintenance.
They do not rank evidence, infer task meaning, or grant semantic acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_bool,
    require_confidence,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    stable_json_hash,
)


CONTEXT_MANAGEMENT_POLICY_SCHEMA_VERSION = "missionforge.context_management_policy.v1"


@dataclass(frozen=True)
class ContextManagementPolicy:
    """Mechanical policy for package-managed context maintenance."""

    policy_id: str = "default"
    soft_pressure_ratio: float = 0.70
    hard_pressure_ratio: float = 0.90
    reducer_enabled: bool = True
    checkpoint_on_soft_pressure: bool = True
    reducer_on_hard_pressure: bool = True
    reducer_on_thrashing: bool = True
    repeat_read_threshold: int = 2
    working_set_token_cap: int = 4000
    working_set_entry_token_cap: int = 800
    projection_token_cap: int = 1200
    max_reducer_attempts: int = 1
    retry_behavior: str = "fresh_boundary_after_reduction"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_MANAGEMENT_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def default(cls) -> "ContextManagementPolicy":
        return cls()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextManagementPolicy":
        data = _refs_only_mapping(payload, "context_management_policy")
        policy = cls(
            policy_id=_safe_id(data.get("policy_id", "default"), "context_management_policy.policy_id"),
            soft_pressure_ratio=require_confidence(
                data.get("soft_pressure_ratio", 0.70),
                "context_management_policy.soft_pressure_ratio",
            ),
            hard_pressure_ratio=require_confidence(
                data.get("hard_pressure_ratio", 0.90),
                "context_management_policy.hard_pressure_ratio",
            ),
            reducer_enabled=require_bool(
                data.get("reducer_enabled", True),
                "context_management_policy.reducer_enabled",
            ),
            checkpoint_on_soft_pressure=require_bool(
                data.get("checkpoint_on_soft_pressure", True),
                "context_management_policy.checkpoint_on_soft_pressure",
            ),
            reducer_on_hard_pressure=require_bool(
                data.get("reducer_on_hard_pressure", True),
                "context_management_policy.reducer_on_hard_pressure",
            ),
            reducer_on_thrashing=require_bool(
                data.get("reducer_on_thrashing", True),
                "context_management_policy.reducer_on_thrashing",
            ),
            repeat_read_threshold=require_int_at_least(
                data.get("repeat_read_threshold", 2),
                "context_management_policy.repeat_read_threshold",
                1,
            ),
            working_set_token_cap=require_int_at_least(
                data.get("working_set_token_cap", 4000),
                "context_management_policy.working_set_token_cap",
                1,
            ),
            working_set_entry_token_cap=require_int_at_least(
                data.get("working_set_entry_token_cap", 800),
                "context_management_policy.working_set_entry_token_cap",
                1,
            ),
            projection_token_cap=require_int_at_least(
                data.get("projection_token_cap", 1200),
                "context_management_policy.projection_token_cap",
                1,
            ),
            max_reducer_attempts=require_int_at_least(
                data.get("max_reducer_attempts", 1),
                "context_management_policy.max_reducer_attempts",
                0,
            ),
            retry_behavior=_safe_id(
                data.get("retry_behavior", "fresh_boundary_after_reduction"),
                "context_management_policy.retry_behavior",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_management_policy.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_MANAGEMENT_POLICY_SCHEMA_VERSION),
                "context_management_policy.schema_version",
            ),
        )
        policy.validate()
        if (
            "policy_hash" in data
            and require_non_empty_str(data["policy_hash"], "context_management_policy.policy_hash")
            != policy.policy_hash
        ):
            raise ContractValidationError("context_management_policy.policy_hash does not match content")
        return policy

    @property
    def policy_hash(self) -> str:
        return stable_json_hash(self._content_dict(include_hash=False))

    def validate(self) -> None:
        if self.schema_version != CONTEXT_MANAGEMENT_POLICY_SCHEMA_VERSION:
            raise ContractValidationError("context_management_policy.schema_version is unsupported")
        _safe_id(self.policy_id, "context_management_policy.policy_id")
        require_confidence(self.soft_pressure_ratio, "context_management_policy.soft_pressure_ratio")
        require_confidence(self.hard_pressure_ratio, "context_management_policy.hard_pressure_ratio")
        if self.soft_pressure_ratio > self.hard_pressure_ratio:
            raise ContractValidationError("context_management_policy soft ratio must not exceed hard ratio")
        require_bool(self.reducer_enabled, "context_management_policy.reducer_enabled")
        require_bool(self.checkpoint_on_soft_pressure, "context_management_policy.checkpoint_on_soft_pressure")
        require_bool(self.reducer_on_hard_pressure, "context_management_policy.reducer_on_hard_pressure")
        require_bool(self.reducer_on_thrashing, "context_management_policy.reducer_on_thrashing")
        require_int_at_least(self.repeat_read_threshold, "context_management_policy.repeat_read_threshold", 1)
        require_int_at_least(self.working_set_token_cap, "context_management_policy.working_set_token_cap", 1)
        require_int_at_least(self.working_set_entry_token_cap, "context_management_policy.working_set_entry_token_cap", 1)
        if self.working_set_entry_token_cap > self.working_set_token_cap:
            raise ContractValidationError("context_management_policy entry cap must not exceed working-set cap")
        require_int_at_least(self.projection_token_cap, "context_management_policy.projection_token_cap", 1)
        require_int_at_least(self.max_reducer_attempts, "context_management_policy.max_reducer_attempts", 0)
        _safe_id(self.retry_behavior, "context_management_policy.retry_behavior")
        _metadata(self.metadata, "context_management_policy.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self._content_dict(include_hash=True)

    def _content_dict(self, *, include_hash: bool) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "soft_pressure_ratio": self.soft_pressure_ratio,
            "hard_pressure_ratio": self.hard_pressure_ratio,
            "reducer_enabled": self.reducer_enabled,
            "checkpoint_on_soft_pressure": self.checkpoint_on_soft_pressure,
            "reducer_on_hard_pressure": self.reducer_on_hard_pressure,
            "reducer_on_thrashing": self.reducer_on_thrashing,
            "repeat_read_threshold": self.repeat_read_threshold,
            "working_set_token_cap": self.working_set_token_cap,
            "working_set_entry_token_cap": self.working_set_entry_token_cap,
            "projection_token_cap": self.projection_token_cap,
            "max_reducer_attempts": self.max_reducer_attempts,
            "retry_behavior": self.retry_behavior,
            "metadata": dict(self.metadata),
        }
        if include_hash:
            payload["policy_hash"] = self.policy_hash
        return payload


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(payload, field_name), field_name))


def _metadata(value: Any, field_name: str) -> dict[str, Any]:
    return dict(ensure_json_value(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name))


def _safe_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a single safe id segment")
    return text
