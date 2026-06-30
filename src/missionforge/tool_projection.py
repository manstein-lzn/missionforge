"""Bounded tool-output projection contracts.

Tool output is split into raw evidence refs, structured observations, and a
bounded model projection. This module owns the product-neutral projection record
and deterministic bounding helper; it does not execute tools or infer semantic
importance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    stable_json_hash,
    validate_ref,
)


TOOL_OUTPUT_PROJECTION_SCHEMA_VERSION = "missionforge.tool_output_projection.v1"
DEFAULT_TOOL_PROJECTION_MAX_CHARS = 8_192


class ToolOutputProjectionPolicy(StrEnum):
    """How a tool output is projected into model-visible context."""

    KEEP = "keep"
    BOUNDED_PREVIEW = "bounded_preview"
    REF_STUB = "ref_stub"
    OMITTED = "omitted"


@dataclass(frozen=True)
class ToolOutputProjection:
    """Refs-first metadata for one bounded tool output projection."""

    projection_id: str
    tool_observation_id: str
    policy: ToolOutputProjectionPolicy
    projection_ref: str
    projection_hash: str
    projection_bytes: int
    original_bytes: int
    raw_ref: str | None = None
    structured_ref: str | None = None
    content_hash: str | None = None
    permission_manifest_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = TOOL_OUTPUT_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToolOutputProjection":
        data = _refs_only_mapping(payload, "tool_output_projection")
        projection = cls(
            projection_id=_safe_id(data.get("projection_id"), "tool_output_projection.projection_id"),
            tool_observation_id=require_non_empty_str(
                data.get("tool_observation_id"),
                "tool_output_projection.tool_observation_id",
            ),
            policy=require_enum(data.get("policy"), ToolOutputProjectionPolicy, "tool_output_projection.policy"),
            projection_ref=validate_ref(data.get("projection_ref"), "tool_output_projection.projection_ref"),
            projection_hash=_hash(data.get("projection_hash"), "tool_output_projection.projection_hash"),
            projection_bytes=require_int_at_least(
                data.get("projection_bytes"),
                "tool_output_projection.projection_bytes",
                0,
            ),
            original_bytes=require_int_at_least(
                data.get("original_bytes"),
                "tool_output_projection.original_bytes",
                0,
            ),
            raw_ref=_optional_ref(data.get("raw_ref"), "tool_output_projection.raw_ref"),
            structured_ref=_optional_ref(data.get("structured_ref"), "tool_output_projection.structured_ref"),
            content_hash=_optional_hash(data.get("content_hash"), "tool_output_projection.content_hash"),
            permission_manifest_ref=_optional_ref(
                data.get("permission_manifest_ref"),
                "tool_output_projection.permission_manifest_ref",
            ),
            metadata=_metadata(data.get("metadata", {}), "tool_output_projection.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", TOOL_OUTPUT_PROJECTION_SCHEMA_VERSION),
                "tool_output_projection.schema_version",
            ),
        )
        projection.validate()
        return projection

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            TOOL_OUTPUT_PROJECTION_SCHEMA_VERSION,
            "tool_output_projection.schema_version",
        )
        _safe_id(self.projection_id, "tool_output_projection.projection_id")
        require_non_empty_str(self.tool_observation_id, "tool_output_projection.tool_observation_id")
        require_enum(self.policy, ToolOutputProjectionPolicy, "tool_output_projection.policy")
        validate_ref(self.projection_ref, "tool_output_projection.projection_ref")
        _hash(self.projection_hash, "tool_output_projection.projection_hash")
        require_int_at_least(self.projection_bytes, "tool_output_projection.projection_bytes", 0)
        require_int_at_least(self.original_bytes, "tool_output_projection.original_bytes", 0)
        if self.projection_bytes > self.original_bytes and self.policy is not ToolOutputProjectionPolicy.REF_STUB:
            raise ContractValidationError("tool_output_projection.projection_bytes must not exceed original_bytes")
        _optional_ref(self.raw_ref, "tool_output_projection.raw_ref")
        _optional_ref(self.structured_ref, "tool_output_projection.structured_ref")
        _optional_hash(self.content_hash, "tool_output_projection.content_hash")
        _optional_ref(self.permission_manifest_ref, "tool_output_projection.permission_manifest_ref")
        _metadata(self.metadata, "tool_output_projection.metadata")
        if self.policy is ToolOutputProjectionPolicy.BOUNDED_PREVIEW and not self.raw_ref:
            raise ContractValidationError("tool_output_projection bounded_preview policy requires raw_ref")
        if self.policy is ToolOutputProjectionPolicy.REF_STUB and not (self.raw_ref or self.structured_ref):
            raise ContractValidationError("tool_output_projection ref_stub policy requires raw_ref or structured_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "projection_id": self.projection_id,
            "tool_observation_id": self.tool_observation_id,
            "policy": self.policy.value,
            "projection_ref": self.projection_ref,
            "projection_hash": self.projection_hash,
            "projection_bytes": self.projection_bytes,
            "original_bytes": self.original_bytes,
            "raw_ref": self.raw_ref,
            "structured_ref": self.structured_ref,
            "content_hash": self.content_hash,
            "permission_manifest_ref": self.permission_manifest_ref,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class BoundedToolOutput:
    """Bounded text plus refs-first projection metadata."""

    projection: ToolOutputProjection
    text: str

    def __post_init__(self) -> None:
        self.projection.validate()
        if not isinstance(self.text, str):
            raise ContractValidationError("bounded_tool_output.text must be a string")


def bound_tool_output(
    *,
    projection_id: str,
    tool_observation_id: str,
    text: str,
    projection_ref: str,
    raw_ref: str | None = None,
    structured_ref: str | None = None,
    permission_manifest_ref: str | None = None,
    max_chars: int = DEFAULT_TOOL_PROJECTION_MAX_CHARS,
) -> BoundedToolOutput:
    """Return a bounded model projection without storing raw bodies in metadata."""

    if not isinstance(text, str):
        raise ContractValidationError("tool_output.text must be a string")
    max_chars = require_int_at_least(max_chars, "tool_output.max_chars", 1)
    original_bytes = len(text.encode("utf-8"))
    content_hash = stable_json_hash({"tool_output_text": text})
    if len(text) <= max_chars:
        policy = ToolOutputProjectionPolicy.KEEP
        projected = text
    elif raw_ref:
        policy = ToolOutputProjectionPolicy.BOUNDED_PREVIEW
        projected = _head_tail_preview(text, max_chars, marker=f"... output truncated; full content ref: {raw_ref} ...")
    else:
        policy = ToolOutputProjectionPolicy.OMITTED
        projected = "[tool output omitted: raw output ref unavailable]"
    projection_hash = "sha256:" + hashlib.sha256(projected.encode("utf-8")).hexdigest()
    projection = ToolOutputProjection(
        projection_id=projection_id,
        tool_observation_id=tool_observation_id,
        policy=policy,
        projection_ref=projection_ref,
        projection_hash=projection_hash,
        projection_bytes=len(projected.encode("utf-8")),
        original_bytes=original_bytes,
        raw_ref=raw_ref,
        structured_ref=structured_ref,
        content_hash=content_hash,
        permission_manifest_ref=permission_manifest_ref,
        metadata={"max_chars": max_chars},
    )
    return BoundedToolOutput(projection=projection, text=projected)


def _head_tail_preview(text: str, max_chars: int, *, marker: str) -> str:
    if max_chars <= len(marker) + 4:
        return marker[:max_chars]
    budget = max_chars - len(marker) - 4
    head_len = (budget + 1) // 2
    tail_len = budget // 2
    head = text[:head_len]
    tail = text[-tail_len:] if tail_len > 0 else ""
    return f"{head}\n\n{marker}\n\n{tail}" if tail else f"{head}\n\n{marker}"


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(payload, field_name), field_name))


def _metadata(value: Any, field_name: str) -> dict[str, Any]:
    return dict(ensure_json_value(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name))


def _safe_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a single safe id segment")
    validate_ref(text, field_name)
    return text


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return validate_ref(value, field_name)


def _hash(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not text.startswith(prefix) or len(text) != len(prefix) + 64:
        raise ContractValidationError(f"{field_name} must be a sha256 hash")
    suffix = text[len(prefix):]
    if any(char not in "0123456789abcdef" for char in suffix):
        raise ContractValidationError(f"{field_name} must be a lowercase sha256 hash")
    return text


def _optional_hash(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return _hash(value, field_name)


def _require_schema(value: str, expected: str, field_name: str) -> None:
    if require_non_empty_str(value, field_name) != expected:
        raise ContractValidationError(f"{field_name} must be {expected}")
