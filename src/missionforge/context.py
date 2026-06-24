"""Refs-first context projection contracts.

The context plane describes what a role is expected to see without embedding
raw prompt bodies, tool output bodies, provider messages, or hidden semantic
memory in durable runtime records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_confidence,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)


CONTEXT_SEGMENT_SCHEMA_VERSION = "missionforge.context_segment.v1"
CONTEXT_VIEW_SCHEMA_VERSION = "missionforge.context_view.v1"
TOOL_OBSERVATION_SCHEMA_VERSION = "missionforge.pi_agent_tool_observation.v1"
CONTEXT_PRESSURE_SCHEMA_VERSION = "missionforge.context_pressure.v1"


class ContextSegmentKind(StrEnum):
    """Product-neutral segment classes used for context diagnostics."""

    AUTHORITY = "authority"
    INSTRUCTION = "instruction"
    ARTIFACT_PREVIEW = "artifact_preview"
    ARTIFACT_REF = "artifact_ref"
    TOOL_OBSERVATION = "tool_observation"
    RUNTIME_DIAGNOSTIC = "runtime_diagnostic"
    SEMANTIC_SUMMARY = "semantic_summary"
    ARCHIVE_STUB = "archive_stub"


class ContextCachePolicy(StrEnum):
    """Prompt-cache stability policy for one segment."""

    STABLE = "stable"
    SEMI_STABLE = "semi_stable"
    VOLATILE = "volatile"
    NO_CACHE = "no_cache"


class ContextInlinePolicy(StrEnum):
    """How a segment body may be projected into provider-facing context."""

    INLINE = "inline"
    PREVIEW = "preview"
    REF_ONLY = "ref_only"
    WINDOWED = "windowed"
    OMITTED = "omitted"


class ToolObservationStatus(StrEnum):
    """Tool observation status."""

    OK = "ok"
    ERROR = "error"


class ToolObservationInlinePolicy(StrEnum):
    """Current-turn projection policy for one tool observation."""

    KEEP = "keep"
    DEMOTE_AFTER_TURN = "demote_after_turn"
    REF_ONLY = "ref_only"


class ContextPressureAction(StrEnum):
    """Runtime action recommendation for context pressure."""

    CONTINUE = "continue"
    PREPARE_CHECKPOINT = "prepare_checkpoint"
    CHECKPOINT_BEFORE_NEXT_TURN = "checkpoint_before_next_turn"


@dataclass(frozen=True)
class ContextSegment:
    """One refs-first unit of model-context assembly."""

    segment_id: str
    kind: ContextSegmentKind
    source_refs: list[str] = field(default_factory=list)
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    cache_policy: ContextCachePolicy = ContextCachePolicy.VOLATILE
    inline_policy: ContextInlinePolicy = ContextInlinePolicy.REF_ONLY
    token_estimate: int = 0
    priority: int = 0
    role_scope: list[str] = field(default_factory=list)
    body_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_SEGMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextSegment":
        data = _refs_only_mapping(payload, "context_segment")
        segment = cls(
            segment_id=_safe_id(data.get("segment_id"), "context_segment.segment_id"),
            kind=require_enum(data.get("kind"), ContextSegmentKind, "context_segment.kind"),
            source_refs=_ref_list(data.get("source_refs", []), "context_segment.source_refs"),
            source_hashes=_hash_mapping(data.get("source_hashes", {}), "context_segment.source_hashes"),
            cache_policy=require_enum(
                data.get("cache_policy", ContextCachePolicy.VOLATILE.value),
                ContextCachePolicy,
                "context_segment.cache_policy",
            ),
            inline_policy=require_enum(
                data.get("inline_policy", ContextInlinePolicy.REF_ONLY.value),
                ContextInlinePolicy,
                "context_segment.inline_policy",
            ),
            token_estimate=require_int_at_least(data.get("token_estimate", 0), "context_segment.token_estimate", 0),
            priority=require_int_at_least(data.get("priority", 0), "context_segment.priority", 0),
            role_scope=require_str_list(data.get("role_scope", []), "context_segment.role_scope"),
            body_ref=_optional_ref(data.get("body_ref"), "context_segment.body_ref"),
            metadata=_metadata(data.get("metadata", {}), "context_segment.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_SEGMENT_SCHEMA_VERSION),
                "context_segment.schema_version",
            ),
        )
        segment.validate()
        return segment

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_SEGMENT_SCHEMA_VERSION, "context_segment.schema_version")
        _safe_id(self.segment_id, "context_segment.segment_id")
        require_enum(self.kind, ContextSegmentKind, "context_segment.kind")
        _unique_refs(self.source_refs, "context_segment.source_refs")
        _hash_mapping(self.source_hashes, "context_segment.source_hashes")
        for ref in self.source_hashes:
            if ref not in self.source_refs:
                raise ContractValidationError("context_segment.source_hashes keys must appear in source_refs")
        require_enum(self.cache_policy, ContextCachePolicy, "context_segment.cache_policy")
        require_enum(self.inline_policy, ContextInlinePolicy, "context_segment.inline_policy")
        require_int_at_least(self.token_estimate, "context_segment.token_estimate", 0)
        require_int_at_least(self.priority, "context_segment.priority", 0)
        _unique_non_empty_strings(self.role_scope, "context_segment.role_scope")
        _optional_ref(self.body_ref, "context_segment.body_ref")
        _metadata(self.metadata, "context_segment.metadata")
        if self.inline_policy is ContextInlinePolicy.INLINE and self.body_ref is None:
            raise ContractValidationError("context_segment.inline body must be represented by body_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "segment_id": self.segment_id,
            "kind": self.kind.value,
            "source_refs": list(self.source_refs),
            "source_hashes": dict(self.source_hashes),
            "cache_policy": self.cache_policy.value,
            "inline_policy": self.inline_policy.value,
            "token_estimate": self.token_estimate,
            "priority": self.priority,
            "role_scope": list(self.role_scope),
            "body_ref": self.body_ref,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ToolObservation:
    """Refs-first metadata for one tool result.

    This mirrors the Pi sidecar observation shape. It intentionally excludes
    raw tool output bodies; large outputs are represented by `raw_ref`,
    `source_ref`, hashes, byte counts, and optional read ranges.
    """

    observation_id: str
    call_id: str
    turn_index: int
    tool_call_id: str
    tool_name: str
    status: ToolObservationStatus
    content_hash: str
    content_bytes: int
    content_lines: int
    inline_policy: ToolObservationInlinePolicy
    raw_ref: str | None = None
    source_ref: str | None = None
    source_range: Mapping[str, int] = field(default_factory=dict)
    source_hash: str | None = None
    source_bytes: int | None = None
    schema_version: str = TOOL_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToolObservation":
        data = _refs_only_mapping(payload, "tool_observation")
        observation = cls(
            observation_id=_safe_id(data.get("observation_id"), "tool_observation.observation_id"),
            call_id=require_non_empty_str(data.get("call_id"), "tool_observation.call_id"),
            turn_index=require_int_at_least(data.get("turn_index"), "tool_observation.turn_index", 0),
            tool_call_id=require_non_empty_str(data.get("tool_call_id"), "tool_observation.tool_call_id"),
            tool_name=require_non_empty_str(data.get("tool_name"), "tool_observation.tool_name"),
            status=require_enum(data.get("status"), ToolObservationStatus, "tool_observation.status"),
            content_hash=_hash(data.get("content_hash"), "tool_observation.content_hash"),
            content_bytes=require_int_at_least(data.get("content_bytes"), "tool_observation.content_bytes", 0),
            content_lines=require_int_at_least(data.get("content_lines"), "tool_observation.content_lines", 0),
            inline_policy=require_enum(
                data.get("inline_policy"),
                ToolObservationInlinePolicy,
                "tool_observation.inline_policy",
            ),
            raw_ref=_optional_ref(data.get("raw_ref"), "tool_observation.raw_ref"),
            source_ref=_optional_ref(data.get("source_ref"), "tool_observation.source_ref"),
            source_range=_source_range(data.get("source_range", {}), "tool_observation.source_range"),
            source_hash=_optional_hash(data.get("source_hash"), "tool_observation.source_hash"),
            source_bytes=_optional_int_at_least(data.get("source_bytes"), "tool_observation.source_bytes", 0),
            schema_version=require_non_empty_str(
                data.get("schema_version", TOOL_OBSERVATION_SCHEMA_VERSION),
                "tool_observation.schema_version",
            ),
        )
        observation.validate()
        return observation

    def validate(self) -> None:
        _require_schema(self.schema_version, TOOL_OBSERVATION_SCHEMA_VERSION, "tool_observation.schema_version")
        _safe_id(self.observation_id, "tool_observation.observation_id")
        require_non_empty_str(self.call_id, "tool_observation.call_id")
        require_int_at_least(self.turn_index, "tool_observation.turn_index", 0)
        require_non_empty_str(self.tool_call_id, "tool_observation.tool_call_id")
        require_non_empty_str(self.tool_name, "tool_observation.tool_name")
        require_enum(self.status, ToolObservationStatus, "tool_observation.status")
        _hash(self.content_hash, "tool_observation.content_hash")
        require_int_at_least(self.content_bytes, "tool_observation.content_bytes", 0)
        require_int_at_least(self.content_lines, "tool_observation.content_lines", 0)
        require_enum(self.inline_policy, ToolObservationInlinePolicy, "tool_observation.inline_policy")
        _optional_ref(self.raw_ref, "tool_observation.raw_ref")
        _optional_ref(self.source_ref, "tool_observation.source_ref")
        _source_range(self.source_range, "tool_observation.source_range")
        _optional_hash(self.source_hash, "tool_observation.source_hash")
        _optional_int_at_least(self.source_bytes, "tool_observation.source_bytes", 0)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "call_id": self.call_id,
            "turn_index": self.turn_index,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "content_hash": self.content_hash,
            "content_bytes": self.content_bytes,
            "content_lines": self.content_lines,
            "inline_policy": self.inline_policy.value,
            "raw_ref": self.raw_ref,
            "source_ref": self.source_ref,
            "source_range": dict(self.source_range),
            "source_hash": self.source_hash,
            "source_bytes": self.source_bytes,
        }

    def to_segment(self) -> ContextSegment:
        """Return a metadata-only context segment for this observation."""

        source_refs = [ref for ref in [self.source_ref, self.raw_ref] if ref]
        inline_policy = (
            ContextInlinePolicy.OMITTED
            if self.inline_policy is ToolObservationInlinePolicy.DEMOTE_AFTER_TURN
            else ContextInlinePolicy.REF_ONLY
        )
        return ContextSegment(
            segment_id=f"tool_{self.observation_id}",
            kind=ContextSegmentKind.TOOL_OBSERVATION,
            source_refs=source_refs,
            cache_policy=ContextCachePolicy.VOLATILE,
            inline_policy=inline_policy,
            token_estimate=0,
            priority=250,
            metadata={
                "observation_ref": source_refs[0] if source_refs else "",
                "tool_name": self.tool_name,
            },
        )


@dataclass(frozen=True)
class ContextView:
    """Provider-facing context plan for one role/call.

    The view is diagnostic authority only at this phase. It describes segment
    placement and refs; it does not contain raw prompt text.
    """

    view_id: str
    role: str
    contract_ref: str
    contract_hash: str
    permission_manifest_ref: str
    stable_prefix: list[ContextSegment] = field(default_factory=list)
    semi_stable_context: list[ContextSegment] = field(default_factory=list)
    volatile_tail: list[ContextSegment] = field(default_factory=list)
    omitted_segments: list[ContextSegment] = field(default_factory=list)
    token_budget: int | None = None
    diagnostics_ref: str | None = None
    schema_version: str = CONTEXT_VIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextView":
        data = _refs_only_mapping(payload, "context_view")
        view = cls(
            view_id=_safe_id(data.get("view_id"), "context_view.view_id"),
            role=require_non_empty_str(data.get("role"), "context_view.role"),
            contract_ref=validate_ref(data.get("contract_ref"), "context_view.contract_ref"),
            contract_hash=_hash(data.get("contract_hash"), "context_view.contract_hash"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_view.permission_manifest_ref",
            ),
            stable_prefix=_segments(data.get("stable_prefix", []), "context_view.stable_prefix"),
            semi_stable_context=_segments(
                data.get("semi_stable_context", []),
                "context_view.semi_stable_context",
            ),
            volatile_tail=_segments(data.get("volatile_tail", []), "context_view.volatile_tail"),
            omitted_segments=_segments(data.get("omitted_segments", []), "context_view.omitted_segments"),
            token_budget=_optional_int_at_least(data.get("token_budget"), "context_view.token_budget", 1),
            diagnostics_ref=_optional_ref(data.get("diagnostics_ref"), "context_view.diagnostics_ref"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_VIEW_SCHEMA_VERSION),
                "context_view.schema_version",
            ),
        )
        view.validate()
        if "context_hash" in data and require_non_empty_str(data["context_hash"], "context_view.context_hash") != view.context_hash:
            raise ContractValidationError("context_view.context_hash does not match content")
        return view

    @property
    def context_hash(self) -> str:
        return stable_json_hash(self._content_dict(include_hash=False))

    @property
    def all_segments(self) -> list[ContextSegment]:
        return [
            *self.stable_prefix,
            *self.semi_stable_context,
            *self.volatile_tail,
            *self.omitted_segments,
        ]

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_VIEW_SCHEMA_VERSION, "context_view.schema_version")
        _safe_id(self.view_id, "context_view.view_id")
        require_non_empty_str(self.role, "context_view.role")
        validate_ref(self.contract_ref, "context_view.contract_ref")
        _hash(self.contract_hash, "context_view.contract_hash")
        validate_ref(self.permission_manifest_ref, "context_view.permission_manifest_ref")
        _validate_segment_bucket(self.stable_prefix, "context_view.stable_prefix", {ContextCachePolicy.STABLE})
        _validate_segment_bucket(
            self.semi_stable_context,
            "context_view.semi_stable_context",
            {ContextCachePolicy.STABLE, ContextCachePolicy.SEMI_STABLE},
        )
        _validate_segment_bucket(
            self.volatile_tail,
            "context_view.volatile_tail",
            {ContextCachePolicy.VOLATILE, ContextCachePolicy.NO_CACHE},
        )
        _validate_segment_bucket(self.omitted_segments, "context_view.omitted_segments", set(ContextCachePolicy))
        if self.token_budget is not None:
            require_int_at_least(self.token_budget, "context_view.token_budget", 1)
        _optional_ref(self.diagnostics_ref, "context_view.diagnostics_ref")
        segment_ids = [segment.segment_id for segment in self.all_segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ContractValidationError("context_view segment ids must be unique")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self._content_dict(include_hash=True)
        return payload

    def _content_dict(self, *, include_hash: bool) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "view_id": self.view_id,
            "role": self.role,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "permission_manifest_ref": self.permission_manifest_ref,
            "token_budget": self.token_budget,
            "stable_prefix": [segment.to_dict() for segment in self.stable_prefix],
            "semi_stable_context": [segment.to_dict() for segment in self.semi_stable_context],
            "volatile_tail": [segment.to_dict() for segment in self.volatile_tail],
            "omitted_segments": [segment.to_dict() for segment in self.omitted_segments],
            "diagnostics_ref": self.diagnostics_ref,
        }
        if include_hash:
            payload["context_hash"] = self.context_hash
        return payload


@dataclass(frozen=True)
class ContextPressureDiagnostics:
    """Refs-only runtime pressure diagnostics for one context view."""

    view_ref: str
    context_hash: str
    estimated_input_tokens: int
    token_budget: int
    pressure_ratio: float
    recommended_action: ContextPressureAction
    checkpoint_ref: str | None = None
    schema_version: str = CONTEXT_PRESSURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextPressureDiagnostics":
        data = _refs_only_mapping(payload, "context_pressure")
        diagnostics = cls(
            view_ref=validate_ref(data.get("view_ref"), "context_pressure.view_ref"),
            context_hash=_hash(data.get("context_hash"), "context_pressure.context_hash"),
            estimated_input_tokens=require_int_at_least(
                data.get("estimated_input_tokens"),
                "context_pressure.estimated_input_tokens",
                0,
            ),
            token_budget=require_int_at_least(data.get("token_budget"), "context_pressure.token_budget", 1),
            pressure_ratio=require_confidence(data.get("pressure_ratio"), "context_pressure.pressure_ratio"),
            recommended_action=require_enum(
                data.get("recommended_action"),
                ContextPressureAction,
                "context_pressure.recommended_action",
            ),
            checkpoint_ref=_optional_ref(data.get("checkpoint_ref"), "context_pressure.checkpoint_ref"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_PRESSURE_SCHEMA_VERSION),
                "context_pressure.schema_version",
            ),
        )
        diagnostics.validate()
        return diagnostics

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_PRESSURE_SCHEMA_VERSION, "context_pressure.schema_version")
        validate_ref(self.view_ref, "context_pressure.view_ref")
        _hash(self.context_hash, "context_pressure.context_hash")
        require_int_at_least(self.estimated_input_tokens, "context_pressure.estimated_input_tokens", 0)
        require_int_at_least(self.token_budget, "context_pressure.token_budget", 1)
        require_confidence(self.pressure_ratio, "context_pressure.pressure_ratio")
        require_enum(self.recommended_action, ContextPressureAction, "context_pressure.recommended_action")
        _optional_ref(self.checkpoint_ref, "context_pressure.checkpoint_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "view_ref": self.view_ref,
            "context_hash": self.context_hash,
            "estimated_input_tokens": self.estimated_input_tokens,
            "token_budget": self.token_budget,
            "pressure_ratio": self.pressure_ratio,
            "recommended_action": self.recommended_action.value,
            "checkpoint_ref": self.checkpoint_ref,
        }


def build_call_context_view(
    *,
    view_id: str,
    role: str,
    contract_ref: str,
    contract_hash: str,
    permission_manifest_ref: str,
    visible_refs: list[str],
    expected_output_refs: list[str],
    evidence_refs: list[str] | None = None,
    runtime_refs: list[str] | None = None,
    token_budget: int | None = None,
    diagnostics_ref: str | None = None,
) -> ContextView:
    """Build a conservative refs-only diagnostic view for one PiWorker call."""

    contract_ref = validate_ref(contract_ref, "context_view.contract_ref")
    stable = [
        ContextSegment(
            segment_id="authority_contract",
            kind=ContextSegmentKind.AUTHORITY,
            source_refs=[contract_ref],
            cache_policy=ContextCachePolicy.STABLE,
            inline_policy=ContextInlinePolicy.REF_ONLY,
            priority=1000,
            role_scope=[role],
        ),
        ContextSegment(
            segment_id="authority_permission_manifest",
            kind=ContextSegmentKind.AUTHORITY,
            source_refs=[permission_manifest_ref],
            cache_policy=ContextCachePolicy.STABLE,
            inline_policy=ContextInlinePolicy.REF_ONLY,
            priority=950,
            role_scope=[role],
        ),
    ]
    volatile_refs = [
        ref for ref in _dedupe_refs(visible_refs)
        if ref not in {contract_ref, permission_manifest_ref}
    ]
    volatile = [
        ContextSegment(
            segment_id="visible_input_refs",
            kind=ContextSegmentKind.ARTIFACT_REF,
            source_refs=volatile_refs,
            cache_policy=ContextCachePolicy.VOLATILE,
            inline_policy=ContextInlinePolicy.REF_ONLY,
            priority=500,
            role_scope=[role],
            metadata={"expected_output_refs": list(_dedupe_refs(expected_output_refs))},
        )
    ]
    omitted: list[ContextSegment] = []
    evidence = _dedupe_refs(evidence_refs or [])
    if evidence:
        omitted.append(
            ContextSegment(
                segment_id="evidence_ref_stubs",
                kind=ContextSegmentKind.ARTIFACT_REF,
                source_refs=evidence,
                cache_policy=ContextCachePolicy.VOLATILE,
                inline_policy=ContextInlinePolicy.OMITTED,
                priority=300,
                role_scope=[role],
            )
        )
    runtime = _dedupe_refs(runtime_refs or [])
    if runtime:
        omitted.append(
            ContextSegment(
                segment_id="runtime_ref_stubs",
                kind=ContextSegmentKind.RUNTIME_DIAGNOSTIC,
                source_refs=runtime,
                cache_policy=ContextCachePolicy.NO_CACHE,
                inline_policy=ContextInlinePolicy.OMITTED,
                priority=100,
                role_scope=[role],
            )
        )
    return ContextView(
        view_id=view_id,
        role=role,
        contract_ref=contract_ref,
        contract_hash=contract_hash,
        permission_manifest_ref=permission_manifest_ref,
        stable_prefix=stable,
        volatile_tail=volatile,
        omitted_segments=omitted,
        token_budget=token_budget,
        diagnostics_ref=diagnostics_ref,
    )


def build_context_pressure_diagnostics(
    *,
    view_ref: str,
    view: ContextView,
    estimated_input_tokens: int,
    token_budget: int | None = None,
    soft_ratio: float = 0.70,
    hard_ratio: float = 0.90,
    checkpoint_ref: str | None = None,
) -> ContextPressureDiagnostics:
    """Build runtime pressure diagnostics without semantic routing authority."""

    budget = token_budget if token_budget is not None else view.token_budget
    if budget is None:
        budget = max(1, estimated_input_tokens)
    budget = require_int_at_least(budget, "context_pressure.token_budget", 1)
    estimated = require_int_at_least(estimated_input_tokens, "context_pressure.estimated_input_tokens", 0)
    pressure_ratio = min(1.0, estimated / budget)
    if pressure_ratio >= hard_ratio:
        action = ContextPressureAction.CHECKPOINT_BEFORE_NEXT_TURN
    elif pressure_ratio >= soft_ratio:
        action = ContextPressureAction.PREPARE_CHECKPOINT
    else:
        action = ContextPressureAction.CONTINUE
    return ContextPressureDiagnostics(
        view_ref=view_ref,
        context_hash=view.context_hash,
        estimated_input_tokens=estimated,
        token_budget=budget,
        pressure_ratio=pressure_ratio,
        recommended_action=action,
        checkpoint_ref=checkpoint_ref,
    )


def _segments(value: Any, field_name: str) -> list[ContextSegment]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    return [ContextSegment.from_dict(require_mapping(item, f"{field_name}[]")) for item in value]


def _validate_segment_bucket(
    segments: list[ContextSegment],
    field_name: str,
    allowed_cache_policies: set[ContextCachePolicy],
) -> None:
    for segment in segments:
        if not isinstance(segment, ContextSegment):
            raise ContractValidationError(f"{field_name} must contain ContextSegment values")
        segment.validate()
        if segment.cache_policy not in allowed_cache_policies:
            raise ContractValidationError(f"{field_name} contains segment with wrong cache policy")


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(payload, field_name), field_name))


def _metadata(value: Any, field_name: str) -> dict[str, Any]:
    return dict(ensure_json_value(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name))


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _unique_refs(values: list[str], field_name: str) -> list[str]:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")
    return refs


def _dedupe_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        ref = validate_ref(value, "context.ref")
        if ref not in seen:
            result.append(ref)
            seen.add(ref)
    return result


def _unique_non_empty_strings(values: list[str], field_name: str) -> list[str]:
    items = require_str_list(values, field_name)
    if len(items) != len(set(items)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")
    return items


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


def _optional_int_at_least(value: Any, field_name: str, minimum: int) -> int | None:
    if value is None:
        return None
    return require_int_at_least(value, field_name, minimum)


def _source_range(value: Any, field_name: str) -> dict[str, int]:
    data = require_mapping(value, field_name)
    allowed = {"offset", "limit"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unknown fields: {unknown}")
    result: dict[str, int] = {}
    for key, item in data.items():
        result[key] = require_int_at_least(item, f"{field_name}.{key}", 0)
    return result


def _hash_mapping(value: Any, field_name: str) -> dict[str, str]:
    data = _refs_only_mapping(require_mapping(value, field_name), field_name)
    return {validate_ref(key, f"{field_name}.key"): _hash(item, f"{field_name}.{key}") for key, item in data.items()}


def _hash(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not text.startswith(prefix) or len(text) != len(prefix) + 64:
        raise ContractValidationError(f"{field_name} must be a sha256 hash")
    hex_part = text[len(prefix):]
    if any(char not in "0123456789abcdef" for char in hex_part):
        raise ContractValidationError(f"{field_name} must be a lowercase sha256 digest")
    return text


def _optional_hash(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    return _hash(value, field_name)


def _require_schema(value: str, expected: str, field_name: str) -> None:
    actual = require_non_empty_str(value, field_name)
    if actual != expected:
        raise ContractValidationError(f"{field_name} must be {expected}")
