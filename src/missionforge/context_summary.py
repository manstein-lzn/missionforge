"""Explicit context summary artifact contracts.

These schemas validate PiWorker/Judge-authored semantic artifacts. They do not
summarize content, mutate runtime state, or grant read access to cited refs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from .piworker_call import PiWorkerCallRole


CONTEXT_SUMMARY_ARTIFACT_SCHEMA_VERSION = "missionforge.context_summary_artifact.v1"


class ContextSummaryKind(StrEnum):
    """Product-neutral purpose for an explicit semantic summary artifact."""

    WORKING_KNOWLEDGE = "working_knowledge"
    COMPACTION = "compaction"
    JUDGE_EVIDENCE = "judge_evidence"
    REPAIR_CONTEXT = "repair_context"


@dataclass(frozen=True)
class ContextSummarySource:
    """One cited source backing a summary claim."""

    source_id: str
    observation_id: str
    ref: str
    content_hash: str
    source_role: PiWorkerCallRole
    permission_manifest_ref: str
    range_hint: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextSummarySource":
        data = _refs_only_mapping(payload, "context_summary_source")
        source = cls(
            source_id=require_non_empty_str(data.get("source_id"), "context_summary_source.source_id"),
            observation_id=require_non_empty_str(
                data.get("observation_id"),
                "context_summary_source.observation_id",
            ),
            ref=validate_ref(data.get("ref"), "context_summary_source.ref"),
            content_hash=_validate_hash(data.get("content_hash"), "context_summary_source.content_hash"),
            source_role=require_enum(
                data.get("source_role"),
                PiWorkerCallRole,
                "context_summary_source.source_role",
            ),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_summary_source.permission_manifest_ref",
            ),
            range_hint=_optional_non_empty_str(data.get("range_hint"), "context_summary_source.range_hint"),
            metadata=_safe_mapping(data.get("metadata", {}), "context_summary_source.metadata"),
        )
        source.validate()
        return source

    def validate(self) -> None:
        require_non_empty_str(self.source_id, "context_summary_source.source_id")
        require_non_empty_str(self.observation_id, "context_summary_source.observation_id")
        validate_ref(self.ref, "context_summary_source.ref")
        _validate_hash(self.content_hash, "context_summary_source.content_hash")
        require_enum(self.source_role, PiWorkerCallRole, "context_summary_source.source_role")
        validate_ref(self.permission_manifest_ref, "context_summary_source.permission_manifest_ref")
        if self.range_hint is not None:
            require_non_empty_str(self.range_hint, "context_summary_source.range_hint")
        _safe_mapping(self.metadata, "context_summary_source.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "source_id": self.source_id,
            "observation_id": self.observation_id,
            "ref": self.ref,
            "content_hash": self.content_hash,
            "source_role": self.source_role.value,
            "permission_manifest_ref": self.permission_manifest_ref,
            "range_hint": self.range_hint,
            "metadata": ensure_json_value(dict(self.metadata), "context_summary_source.metadata"),
        }


@dataclass(frozen=True)
class ContextSummaryArtifact:
    """A PiWorker/Judge-authored semantic summary with explicit source refs."""

    summary_id: str
    call_id: str
    role: PiWorkerCallRole
    kind: ContextSummaryKind
    summary_text: str
    sources: list[ContextSummarySource]
    permission_manifest_ref: str
    created_by: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_SUMMARY_ARTIFACT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextSummaryArtifact":
        data = _refs_only_mapping(payload, "context_summary_artifact")
        artifact = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_SUMMARY_ARTIFACT_SCHEMA_VERSION),
                "context_summary_artifact.schema_version",
            ),
            summary_id=require_non_empty_str(data.get("summary_id"), "context_summary_artifact.summary_id"),
            call_id=require_non_empty_str(data.get("call_id"), "context_summary_artifact.call_id"),
            role=require_enum(data.get("role"), PiWorkerCallRole, "context_summary_artifact.role"),
            kind=require_enum(data.get("kind"), ContextSummaryKind, "context_summary_artifact.kind"),
            summary_text=require_non_empty_str(
                data.get("summary_text"),
                "context_summary_artifact.summary_text",
            ),
            sources=[
                ContextSummarySource.from_dict(require_mapping(item, "context_summary_artifact.sources[]"))
                for item in _required_list(data.get("sources"), "context_summary_artifact.sources")
            ],
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_summary_artifact.permission_manifest_ref",
            ),
            created_by=require_non_empty_str(data.get("created_by"), "context_summary_artifact.created_by"),
            metadata=_safe_mapping(data.get("metadata", {}), "context_summary_artifact.metadata"),
        )
        artifact.validate()
        return artifact

    def validate(self) -> None:
        if self.schema_version != CONTEXT_SUMMARY_ARTIFACT_SCHEMA_VERSION:
            raise ContractValidationError("context_summary_artifact.schema_version is unsupported")
        require_non_empty_str(self.summary_id, "context_summary_artifact.summary_id")
        require_non_empty_str(self.call_id, "context_summary_artifact.call_id")
        require_enum(self.role, PiWorkerCallRole, "context_summary_artifact.role")
        require_enum(self.kind, ContextSummaryKind, "context_summary_artifact.kind")
        require_non_empty_str(self.summary_text, "context_summary_artifact.summary_text")
        if not self.sources:
            raise ContractValidationError("context_summary_artifact.sources must not be empty")
        seen_source_ids: set[str] = set()
        for source in self.sources:
            source.validate()
            if source.source_id in seen_source_ids:
                raise ContractValidationError("context_summary_artifact.sources source_id values must be unique")
            seen_source_ids.add(source.source_id)
        validate_ref(self.permission_manifest_ref, "context_summary_artifact.permission_manifest_ref")
        require_non_empty_str(self.created_by, "context_summary_artifact.created_by")
        _safe_mapping(self.metadata, "context_summary_artifact.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "summary_id": self.summary_id,
            "call_id": self.call_id,
            "role": self.role.value,
            "kind": self.kind.value,
            "summary_text": self.summary_text,
            "sources": [source.to_dict() for source in self.sources],
            "permission_manifest_ref": self.permission_manifest_ref,
            "created_by": self.created_by,
            "metadata": ensure_json_value(dict(self.metadata), "context_summary_artifact.metadata"),
        }


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return require_mapping(assert_refs_only_payload(payload, field_name), field_name)


def _required_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    return list(value)


def _safe_mapping(value: Any, field_name: str) -> dict[str, Any]:
    return require_mapping(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name)


def _optional_non_empty_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return require_non_empty_str(value, field_name)


def _validate_hash(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not text.startswith(prefix) or len(text) != len(prefix) + 64:
        raise ContractValidationError(f"{field_name} must be a sha256 hash")
    suffix = text[len(prefix):]
    if any(char not in "0123456789abcdef" for char in suffix):
        raise ContractValidationError(f"{field_name} must be a lowercase sha256 hash")
    return text
