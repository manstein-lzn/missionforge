"""Refs-first context engine boundary contracts.

The module defines product-neutral context lifecycle records. It does not render
provider prompts, summarize semantic content, rank sources, or mutate task
authority. Provider-facing text remains an ephemeral projection compiled by the
runtime immediately before a model call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_bool,
    require_confidence,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from .context import (
    ContextCachePolicy,
    ContextInlinePolicy,
    ContextPressureAction,
    ContextPressureDiagnostics,
    ContextSegment,
    ContextSegmentKind,
    ContextView,
    build_context_pressure_diagnostics,
)
from .permissions import ReadGate


CONTEXT_SOURCE_SCHEMA_VERSION = "missionforge.context_source.v1"
CONTEXT_SOURCE_SNAPSHOT_SCHEMA_VERSION = "missionforge.context_source_snapshot.v1"
CONTEXT_EPOCH_SCHEMA_VERSION = "missionforge.context_epoch.v1"
CONTEXT_WORKING_SET_SCHEMA_VERSION = "missionforge.context_working_set.v1"
CONTEXT_WORKING_SET_ENTRY_SCHEMA_VERSION = "missionforge.context_working_set_entry.v1"
CONTEXT_CACHE_LAYOUT_SCHEMA_VERSION = "missionforge.context_cache_layout.v1"
CONTEXT_COMPILE_REQUEST_SCHEMA_VERSION = "missionforge.context_compile_request.v1"
CONTEXT_COMPILE_RESULT_SCHEMA_VERSION = "missionforge.context_compile_result.v1"
CONTEXT_TURN_BOUNDARY_SCHEMA_VERSION = "missionforge.context_turn_boundary.v1"
CONTEXT_CHECKPOINT_SCHEMA_VERSION = "missionforge.context_checkpoint.v1"
CONTEXT_PACKAGE_SCHEMA_VERSION = "missionforge.context_package.v1"
CONTEXT_REDUCTION_REQUEST_SCHEMA_VERSION = "missionforge.context_reduction_request.v1"
CONTEXT_REDUCTION_RESULT_SCHEMA_VERSION = "missionforge.context_reduction_result.v1"
CONTEXT_COMPACTION_RECORD_SCHEMA_VERSION = "missionforge.context_compaction_record.v1"
CONTEXT_READ_OBSERVATION_SCHEMA_VERSION = "missionforge.context_read_observation.v1"
CONTEXT_THRASH_DIAGNOSTICS_SCHEMA_VERSION = "missionforge.context_thrash_diagnostics.v1"


_CONTEXT_PACKAGE_FIELDS = {
    "schema_version",
    "package_id",
    "role",
    "run_id",
    "step_id",
    "call_id",
    "contract_ref",
    "contract_hash",
    "permission_manifest_ref",
    "permission_manifest_hash",
    "context_view_ref",
    "context_hash",
    "policy_ref",
    "policy_hash",
    "compile_request_ref",
    "compile_result_ref",
    "source_snapshot_ref",
    "epoch_ref",
    "baseline_ref",
    "cache_layout_ref",
    "pressure_ref",
    "turn_safe_point_ref",
    "turn_boundary_ref",
    "step_spec_ref",
    "step_spec_hash",
    "tool_schema_hash",
    "checkpoint_ref",
    "working_set_ref",
    "visible_refs",
    "visible_ref_hashes",
    "context_record_refs",
    "context_record_hashes",
    "context_feed_refs",
    "diagnostics_refs",
    "context_compiler_version",
    "metadata",
    "created_at",
    "context_package_hash",
}


class ContextSourceKind(StrEnum):
    """Product-neutral context source classes."""

    AUTHORITY = "authority"
    INSTRUCTION = "instruction"
    WORKING_SET = "working_set"
    PRODUCT_STATE = "product_state"
    TOOL_OBSERVATION = "tool_observation"
    SUMMARY = "summary"
    USER_EVENT = "user_event"
    RUNTIME_DIAGNOSTIC = "runtime_diagnostic"


class ContextWorkingSetFreshness(StrEnum):
    """Freshness state for one working-set entry."""

    CURRENT_TURN = "current_turn"
    ACTIVE_PHASE = "active_phase"
    CHECKPOINTED = "checkpointed"
    STALE = "stale"


class ContextWorkingSetPinPolicy(StrEnum):
    """Eviction rule for one working-set entry."""

    PINNED_UNTIL_PHASE_END = "pinned_until_phase_end"
    PINNED_UNTIL_CHECKPOINT = "pinned_until_checkpoint"
    EVICTABLE = "evictable"


class ContextCompileAction(StrEnum):
    """Non-semantic runtime recommendation after context compilation."""

    CONTINUE = "continue"
    PREPARE_CHECKPOINT = "prepare_checkpoint"
    CHECKPOINT_BEFORE_NEXT_TURN = "checkpoint_before_next_turn"
    BLOCKED_BY_UNAVAILABLE_AUTHORITY = "blocked_by_unavailable_authority"
    BLOCKED_BY_DENIED_REQUIRED_SOURCE = "blocked_by_denied_required_source"


class ContextTurnBoundaryStatus(StrEnum):
    """Safe provider-turn boundary status."""

    READY = "ready"
    BLOCKED = "blocked"
    CHECKPOINT_REQUIRED = "checkpoint_required"
    CANCELLED = "cancelled"
    REVISION_REQUESTED = "revision_requested"


class ContextCheckpointCreator(StrEnum):
    """Producer class for one context checkpoint."""

    RUNTIME = "runtime"
    REDUCER_PIWORKER = "reducer_piworker"
    OPERATOR = "operator"


class ContextReductionReason(StrEnum):
    """Reason MissionForge requested managed context reduction."""

    PRESSURE_SOFT = "pressure_soft"
    PRESSURE_HARD = "pressure_hard"
    REPEATED_READ_THRASHING = "repeated_read_thrashing"
    OPERATOR_CHECKPOINT = "operator_checkpoint"
    BEFORE_RESUME = "before_resume"


class ContextReductionStatus(StrEnum):
    """Boundary status for a managed context reduction result."""

    COMPLETED = "completed"
    FAILED = "failed"
    INVALID_OUTPUT = "invalid_output"
    SKIPPED = "skipped"


class ContextCompactionStatus(StrEnum):
    """Durable compaction lifecycle status."""

    STARTED = "started"
    ENDED = "ended"
    FAILED = "failed"


@dataclass(frozen=True)
class ContextSource:
    """Stable, permission-filtered context source descriptor.

    The source records identity, refs, hashes, and projection policy. It does
    not contain the source body or rendered provider text.
    """

    source_key: str
    kind: ContextSourceKind
    source_refs: list[str] = field(default_factory=list)
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    projection_ref: str | None = None
    projection_hash: str | None = None
    permission_manifest_ref: str | None = None
    cache_policy: ContextCachePolicy = ContextCachePolicy.VOLATILE
    inline_policy: ContextInlinePolicy = ContextInlinePolicy.REF_ONLY
    required: bool = False
    token_estimate: int = 0
    priority: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_SOURCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextSource":
        data = _refs_only_mapping(payload, "context_source")
        source = cls(
            source_key=validate_ref(data.get("source_key"), "context_source.source_key"),
            kind=require_enum(data.get("kind"), ContextSourceKind, "context_source.kind"),
            source_refs=_unique_refs(data.get("source_refs", []), "context_source.source_refs"),
            source_hashes=_hash_mapping(data.get("source_hashes", {}), "context_source.source_hashes"),
            projection_ref=_optional_ref(data.get("projection_ref"), "context_source.projection_ref"),
            projection_hash=_optional_hash(data.get("projection_hash"), "context_source.projection_hash"),
            permission_manifest_ref=_optional_ref(
                data.get("permission_manifest_ref"),
                "context_source.permission_manifest_ref",
            ),
            cache_policy=require_enum(
                data.get("cache_policy", ContextCachePolicy.VOLATILE.value),
                ContextCachePolicy,
                "context_source.cache_policy",
            ),
            inline_policy=require_enum(
                data.get("inline_policy", ContextInlinePolicy.REF_ONLY.value),
                ContextInlinePolicy,
                "context_source.inline_policy",
            ),
            required=require_bool(data.get("required", False), "context_source.required"),
            token_estimate=require_int_at_least(data.get("token_estimate", 0), "context_source.token_estimate", 0),
            priority=require_int_at_least(data.get("priority", 0), "context_source.priority", 0),
            metadata=_metadata(data.get("metadata", {}), "context_source.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_SOURCE_SCHEMA_VERSION),
                "context_source.schema_version",
            ),
        )
        source.validate()
        return source

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_SOURCE_SCHEMA_VERSION, "context_source.schema_version")
        validate_ref(self.source_key, "context_source.source_key")
        require_enum(self.kind, ContextSourceKind, "context_source.kind")
        _unique_refs(self.source_refs, "context_source.source_refs")
        hashes = _hash_mapping(self.source_hashes, "context_source.source_hashes")
        for ref in hashes:
            if ref not in self.source_refs:
                raise ContractValidationError("context_source.source_hashes keys must appear in source_refs")
        _optional_ref(self.projection_ref, "context_source.projection_ref")
        _optional_hash(self.projection_hash, "context_source.projection_hash")
        _optional_ref(self.permission_manifest_ref, "context_source.permission_manifest_ref")
        require_enum(self.cache_policy, ContextCachePolicy, "context_source.cache_policy")
        require_enum(self.inline_policy, ContextInlinePolicy, "context_source.inline_policy")
        require_bool(self.required, "context_source.required")
        require_int_at_least(self.token_estimate, "context_source.token_estimate", 0)
        require_int_at_least(self.priority, "context_source.priority", 0)
        _metadata(self.metadata, "context_source.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "source_key": self.source_key,
            "kind": self.kind.value,
            "source_refs": list(self.source_refs),
            "source_hashes": dict(self.source_hashes),
            "projection_ref": self.projection_ref,
            "projection_hash": self.projection_hash,
            "permission_manifest_ref": self.permission_manifest_ref,
            "cache_policy": self.cache_policy.value,
            "inline_policy": self.inline_policy.value,
            "required": self.required,
            "token_estimate": self.token_estimate,
            "priority": self.priority,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextSourceSnapshot:
    """Durable comparison state for one admitted context source."""

    source_key: str
    source_refs: list[str] = field(default_factory=list)
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    projection_ref: str | None = None
    projection_hash: str | None = None
    token_estimate: int = 0
    sequence: int = 0
    removal_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_SOURCE_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_source(cls, source: ContextSource, *, sequence: int = 0) -> "ContextSourceSnapshot":
        source.validate()
        return cls(
            source_key=source.source_key,
            source_refs=list(source.source_refs),
            source_hashes=dict(source.source_hashes),
            projection_ref=source.projection_ref,
            projection_hash=source.projection_hash,
            token_estimate=source.token_estimate,
            sequence=sequence,
            metadata={"source_kind": source.kind.value},
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextSourceSnapshot":
        data = _refs_only_mapping(payload, "context_source_snapshot")
        snapshot = cls(
            source_key=validate_ref(data.get("source_key"), "context_source_snapshot.source_key"),
            source_refs=_unique_refs(data.get("source_refs", []), "context_source_snapshot.source_refs"),
            source_hashes=_hash_mapping(
                data.get("source_hashes", {}),
                "context_source_snapshot.source_hashes",
            ),
            projection_ref=_optional_ref(data.get("projection_ref"), "context_source_snapshot.projection_ref"),
            projection_hash=_optional_hash(data.get("projection_hash"), "context_source_snapshot.projection_hash"),
            token_estimate=require_int_at_least(
                data.get("token_estimate", 0),
                "context_source_snapshot.token_estimate",
                0,
            ),
            sequence=require_int_at_least(data.get("sequence", 0), "context_source_snapshot.sequence", 0),
            removal_ref=_optional_ref(data.get("removal_ref"), "context_source_snapshot.removal_ref"),
            metadata=_metadata(data.get("metadata", {}), "context_source_snapshot.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_SOURCE_SNAPSHOT_SCHEMA_VERSION),
                "context_source_snapshot.schema_version",
            ),
        )
        snapshot.validate()
        return snapshot

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            CONTEXT_SOURCE_SNAPSHOT_SCHEMA_VERSION,
            "context_source_snapshot.schema_version",
        )
        validate_ref(self.source_key, "context_source_snapshot.source_key")
        _unique_refs(self.source_refs, "context_source_snapshot.source_refs")
        hashes = _hash_mapping(self.source_hashes, "context_source_snapshot.source_hashes")
        for ref in hashes:
            if ref not in self.source_refs:
                raise ContractValidationError("context_source_snapshot.source_hashes keys must appear in source_refs")
        _optional_ref(self.projection_ref, "context_source_snapshot.projection_ref")
        _optional_hash(self.projection_hash, "context_source_snapshot.projection_hash")
        require_int_at_least(self.token_estimate, "context_source_snapshot.token_estimate", 0)
        require_int_at_least(self.sequence, "context_source_snapshot.sequence", 0)
        _optional_ref(self.removal_ref, "context_source_snapshot.removal_ref")
        _metadata(self.metadata, "context_source_snapshot.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "source_key": self.source_key,
            "source_refs": list(self.source_refs),
            "source_hashes": dict(self.source_hashes),
            "projection_ref": self.projection_ref,
            "projection_hash": self.projection_hash,
            "token_estimate": self.token_estimate,
            "sequence": self.sequence,
            "removal_ref": self.removal_ref,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextEpoch:
    """Cache-friendly baseline generation for one role boundary."""

    epoch_id: str
    role: str
    contract_hash: str
    permission_manifest_ref: str
    baseline_ref: str
    baseline_hash: str
    source_snapshot_ref: str
    baseline_seq: int = 0
    provider_cache_profile: Mapping[str, Any] = field(default_factory=dict)
    context_view_ref: str | None = None
    parent_epoch_ref: str | None = None
    created_at: str = ""
    schema_version: str = CONTEXT_EPOCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextEpoch":
        data = _refs_only_mapping(payload, "context_epoch")
        epoch = cls(
            epoch_id=_safe_id(data.get("epoch_id"), "context_epoch.epoch_id"),
            role=require_non_empty_str(data.get("role"), "context_epoch.role"),
            contract_hash=_hash(data.get("contract_hash"), "context_epoch.contract_hash"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_epoch.permission_manifest_ref",
            ),
            baseline_ref=validate_ref(data.get("baseline_ref"), "context_epoch.baseline_ref"),
            baseline_hash=_hash(data.get("baseline_hash"), "context_epoch.baseline_hash"),
            source_snapshot_ref=validate_ref(data.get("source_snapshot_ref"), "context_epoch.source_snapshot_ref"),
            baseline_seq=require_int_at_least(data.get("baseline_seq", 0), "context_epoch.baseline_seq", 0),
            provider_cache_profile=_metadata(
                data.get("provider_cache_profile", {}),
                "context_epoch.provider_cache_profile",
            ),
            context_view_ref=_optional_ref(data.get("context_view_ref"), "context_epoch.context_view_ref"),
            parent_epoch_ref=_optional_ref(data.get("parent_epoch_ref"), "context_epoch.parent_epoch_ref"),
            created_at=require_non_empty_str(data.get("created_at"), "context_epoch.created_at"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_EPOCH_SCHEMA_VERSION),
                "context_epoch.schema_version",
            ),
        )
        epoch.validate()
        if "epoch_hash" in data and require_non_empty_str(data["epoch_hash"], "context_epoch.epoch_hash") != epoch.epoch_hash:
            raise ContractValidationError("context_epoch.epoch_hash does not match content")
        return epoch

    @property
    def epoch_hash(self) -> str:
        return stable_json_hash(self._content_dict(include_hash=False))

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_EPOCH_SCHEMA_VERSION, "context_epoch.schema_version")
        _safe_id(self.epoch_id, "context_epoch.epoch_id")
        require_non_empty_str(self.role, "context_epoch.role")
        _hash(self.contract_hash, "context_epoch.contract_hash")
        validate_ref(self.permission_manifest_ref, "context_epoch.permission_manifest_ref")
        validate_ref(self.baseline_ref, "context_epoch.baseline_ref")
        _hash(self.baseline_hash, "context_epoch.baseline_hash")
        validate_ref(self.source_snapshot_ref, "context_epoch.source_snapshot_ref")
        require_int_at_least(self.baseline_seq, "context_epoch.baseline_seq", 0)
        _metadata(self.provider_cache_profile, "context_epoch.provider_cache_profile")
        _optional_ref(self.context_view_ref, "context_epoch.context_view_ref")
        _optional_ref(self.parent_epoch_ref, "context_epoch.parent_epoch_ref")
        require_non_empty_str(self.created_at, "context_epoch.created_at")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self._content_dict(include_hash=True)

    def _content_dict(self, *, include_hash: bool) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "epoch_id": self.epoch_id,
            "role": self.role,
            "contract_hash": self.contract_hash,
            "permission_manifest_ref": self.permission_manifest_ref,
            "baseline_ref": self.baseline_ref,
            "baseline_hash": self.baseline_hash,
            "source_snapshot_ref": self.source_snapshot_ref,
            "baseline_seq": self.baseline_seq,
            "provider_cache_profile": dict(self.provider_cache_profile),
            "context_view_ref": self.context_view_ref,
            "parent_epoch_ref": self.parent_epoch_ref,
            "created_at": self.created_at,
        }
        if include_hash:
            payload["epoch_hash"] = self.epoch_hash
        return payload


@dataclass(frozen=True)
class ContextWorkingSetEntry:
    """One bounded piece of active model-visible work memory."""

    entry_id: str
    source_ref: str
    source_hash: str
    projection_ref: str
    projection_hash: str
    phase_label: str
    token_estimate: int
    token_cap: int
    pin_policy: ContextWorkingSetPinPolicy = ContextWorkingSetPinPolicy.EVICTABLE
    freshness: ContextWorkingSetFreshness = ContextWorkingSetFreshness.ACTIVE_PHASE
    source_range: Mapping[str, int] = field(default_factory=dict)
    why_ref: str | None = None
    claim_link_refs: list[str] = field(default_factory=list)
    producing_observation_ids: list[str] = field(default_factory=list)
    eviction_reason: str = ""
    permission_manifest_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_WORKING_SET_ENTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextWorkingSetEntry":
        data = _refs_only_mapping(payload, "context_working_set_entry")
        entry = cls(
            entry_id=_safe_id(data.get("entry_id"), "context_working_set_entry.entry_id"),
            source_ref=validate_ref(data.get("source_ref"), "context_working_set_entry.source_ref"),
            source_hash=_hash(data.get("source_hash"), "context_working_set_entry.source_hash"),
            projection_ref=validate_ref(data.get("projection_ref"), "context_working_set_entry.projection_ref"),
            projection_hash=_hash(data.get("projection_hash"), "context_working_set_entry.projection_hash"),
            phase_label=_safe_id(data.get("phase_label"), "context_working_set_entry.phase_label"),
            token_estimate=require_int_at_least(
                data.get("token_estimate"),
                "context_working_set_entry.token_estimate",
                0,
            ),
            token_cap=require_int_at_least(data.get("token_cap"), "context_working_set_entry.token_cap", 1),
            pin_policy=require_enum(
                data.get("pin_policy", ContextWorkingSetPinPolicy.EVICTABLE.value),
                ContextWorkingSetPinPolicy,
                "context_working_set_entry.pin_policy",
            ),
            freshness=require_enum(
                data.get("freshness", ContextWorkingSetFreshness.ACTIVE_PHASE.value),
                ContextWorkingSetFreshness,
                "context_working_set_entry.freshness",
            ),
            source_range=_source_range(data.get("source_range", {}), "context_working_set_entry.source_range"),
            why_ref=_optional_ref(data.get("why_ref"), "context_working_set_entry.why_ref"),
            claim_link_refs=_unique_refs(
                data.get("claim_link_refs", []),
                "context_working_set_entry.claim_link_refs",
            ),
            producing_observation_ids=_unique_strings(
                data.get("producing_observation_ids", []),
                "context_working_set_entry.producing_observation_ids",
            ),
            eviction_reason=_optional_safe_label(
                data.get("eviction_reason", ""),
                "context_working_set_entry.eviction_reason",
            ),
            permission_manifest_ref=_optional_ref(
                data.get("permission_manifest_ref"),
                "context_working_set_entry.permission_manifest_ref",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_working_set_entry.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_WORKING_SET_ENTRY_SCHEMA_VERSION),
                "context_working_set_entry.schema_version",
            ),
        )
        entry.validate()
        return entry

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            CONTEXT_WORKING_SET_ENTRY_SCHEMA_VERSION,
            "context_working_set_entry.schema_version",
        )
        _safe_id(self.entry_id, "context_working_set_entry.entry_id")
        validate_ref(self.source_ref, "context_working_set_entry.source_ref")
        _hash(self.source_hash, "context_working_set_entry.source_hash")
        validate_ref(self.projection_ref, "context_working_set_entry.projection_ref")
        _hash(self.projection_hash, "context_working_set_entry.projection_hash")
        _safe_id(self.phase_label, "context_working_set_entry.phase_label")
        require_int_at_least(self.token_estimate, "context_working_set_entry.token_estimate", 0)
        require_int_at_least(self.token_cap, "context_working_set_entry.token_cap", 1)
        if self.token_estimate > self.token_cap:
            raise ContractValidationError("context_working_set_entry.token_estimate must not exceed token_cap")
        require_enum(self.pin_policy, ContextWorkingSetPinPolicy, "context_working_set_entry.pin_policy")
        require_enum(self.freshness, ContextWorkingSetFreshness, "context_working_set_entry.freshness")
        _source_range(self.source_range, "context_working_set_entry.source_range")
        _optional_ref(self.why_ref, "context_working_set_entry.why_ref")
        _unique_refs(self.claim_link_refs, "context_working_set_entry.claim_link_refs")
        _unique_strings(self.producing_observation_ids, "context_working_set_entry.producing_observation_ids")
        _optional_safe_label(self.eviction_reason, "context_working_set_entry.eviction_reason")
        _optional_ref(self.permission_manifest_ref, "context_working_set_entry.permission_manifest_ref")
        _metadata(self.metadata, "context_working_set_entry.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "entry_id": self.entry_id,
            "source_ref": self.source_ref,
            "source_hash": self.source_hash,
            "projection_ref": self.projection_ref,
            "projection_hash": self.projection_hash,
            "phase_label": self.phase_label,
            "token_estimate": self.token_estimate,
            "token_cap": self.token_cap,
            "pin_policy": self.pin_policy.value,
            "freshness": self.freshness.value,
            "source_range": dict(self.source_range),
            "why_ref": self.why_ref,
            "claim_link_refs": list(self.claim_link_refs),
            "producing_observation_ids": list(self.producing_observation_ids),
            "eviction_reason": self.eviction_reason,
            "permission_manifest_ref": self.permission_manifest_ref,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextWorkingSet:
    """Bounded active work memory for one role/phase."""

    working_set_id: str
    role: str
    phase_label: str
    entries: list[ContextWorkingSetEntry] = field(default_factory=list)
    token_estimate: int = 0
    token_cap: int = 1
    entry_ordering_policy: str = "priority_then_entry_id"
    omitted_entry_ids: list[str] = field(default_factory=list)
    permission_manifest_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_WORKING_SET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextWorkingSet":
        data = _refs_only_mapping(payload, "context_working_set")
        working_set = cls(
            working_set_id=_safe_id(data.get("working_set_id"), "context_working_set.working_set_id"),
            role=require_non_empty_str(data.get("role"), "context_working_set.role"),
            phase_label=_safe_id(data.get("phase_label"), "context_working_set.phase_label"),
            entries=[
                ContextWorkingSetEntry.from_dict(require_mapping(item, "context_working_set.entries[]"))
                for item in _list(data.get("entries", []), "context_working_set.entries")
            ],
            token_estimate=require_int_at_least(
                data.get("token_estimate", 0),
                "context_working_set.token_estimate",
                0,
            ),
            token_cap=require_int_at_least(data.get("token_cap", 1), "context_working_set.token_cap", 1),
            entry_ordering_policy=_safe_id(
                data.get("entry_ordering_policy", "priority_then_entry_id"),
                "context_working_set.entry_ordering_policy",
            ),
            omitted_entry_ids=_unique_strings(data.get("omitted_entry_ids", []), "context_working_set.omitted_entry_ids"),
            permission_manifest_ref=_optional_ref(
                data.get("permission_manifest_ref"),
                "context_working_set.permission_manifest_ref",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_working_set.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_WORKING_SET_SCHEMA_VERSION),
                "context_working_set.schema_version",
            ),
        )
        working_set.validate()
        if "working_set_hash" in data and require_non_empty_str(data["working_set_hash"], "context_working_set.working_set_hash") != working_set.working_set_hash:
            raise ContractValidationError("context_working_set.working_set_hash does not match content")
        return working_set

    @property
    def working_set_hash(self) -> str:
        return stable_json_hash(self._content_dict(include_hash=False))

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_WORKING_SET_SCHEMA_VERSION, "context_working_set.schema_version")
        _safe_id(self.working_set_id, "context_working_set.working_set_id")
        require_non_empty_str(self.role, "context_working_set.role")
        _safe_id(self.phase_label, "context_working_set.phase_label")
        entry_ids: list[str] = []
        estimate = 0
        for entry in self.entries:
            if not isinstance(entry, ContextWorkingSetEntry):
                raise ContractValidationError("context_working_set.entries must contain ContextWorkingSetEntry values")
            entry.validate()
            entry_ids.append(entry.entry_id)
            estimate += entry.token_estimate
        if len(entry_ids) != len(set(entry_ids)):
            raise ContractValidationError("context_working_set.entries entry_id values must be unique")
        require_int_at_least(self.token_estimate, "context_working_set.token_estimate", 0)
        require_int_at_least(self.token_cap, "context_working_set.token_cap", 1)
        if self.token_estimate > self.token_cap:
            raise ContractValidationError("context_working_set.token_estimate must not exceed token_cap")
        if self.token_estimate < estimate:
            raise ContractValidationError("context_working_set.token_estimate must include entry estimates")
        _safe_id(self.entry_ordering_policy, "context_working_set.entry_ordering_policy")
        _unique_strings(self.omitted_entry_ids, "context_working_set.omitted_entry_ids")
        _optional_ref(self.permission_manifest_ref, "context_working_set.permission_manifest_ref")
        _metadata(self.metadata, "context_working_set.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self._content_dict(include_hash=True)

    def _content_dict(self, *, include_hash: bool) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "working_set_id": self.working_set_id,
            "role": self.role,
            "phase_label": self.phase_label,
            "entries": [entry.to_dict() for entry in self.entries],
            "token_estimate": self.token_estimate,
            "token_cap": self.token_cap,
            "entry_ordering_policy": self.entry_ordering_policy,
            "omitted_entry_ids": list(self.omitted_entry_ids),
            "permission_manifest_ref": self.permission_manifest_ref,
            "metadata": dict(self.metadata),
        }
        if include_hash:
            payload["working_set_hash"] = self.working_set_hash
        return payload


@dataclass(frozen=True)
class ContextCacheLayout:
    """Provider-neutral cache layout diagnostics for one ContextView."""

    layout_id: str
    view_ref: str
    context_hash: str
    stable_strata_hash: str
    semi_stable_strata_hash: str
    volatile_strata_hash: str
    omitted_strata_hash: str
    rendered_prefix_hash: str
    stable_token_estimate: int = 0
    semi_stable_token_estimate: int = 0
    volatile_token_estimate: int = 0
    omitted_token_estimate: int = 0
    epoch_invalidation_refs: list[str] = field(default_factory=list)
    provider_cache_profile: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_CACHE_LAYOUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextCacheLayout":
        data = _refs_only_mapping(payload, "context_cache_layout")
        layout = cls(
            layout_id=_safe_id(data.get("layout_id"), "context_cache_layout.layout_id"),
            view_ref=validate_ref(data.get("view_ref"), "context_cache_layout.view_ref"),
            context_hash=_hash(data.get("context_hash"), "context_cache_layout.context_hash"),
            stable_strata_hash=_hash(data.get("stable_strata_hash"), "context_cache_layout.stable_strata_hash"),
            semi_stable_strata_hash=_hash(
                data.get("semi_stable_strata_hash"),
                "context_cache_layout.semi_stable_strata_hash",
            ),
            volatile_strata_hash=_hash(data.get("volatile_strata_hash"), "context_cache_layout.volatile_strata_hash"),
            omitted_strata_hash=_hash(data.get("omitted_strata_hash"), "context_cache_layout.omitted_strata_hash"),
            rendered_prefix_hash=_hash(data.get("rendered_prefix_hash"), "context_cache_layout.rendered_prefix_hash"),
            stable_token_estimate=require_int_at_least(
                data.get("stable_token_estimate", 0),
                "context_cache_layout.stable_token_estimate",
                0,
            ),
            semi_stable_token_estimate=require_int_at_least(
                data.get("semi_stable_token_estimate", 0),
                "context_cache_layout.semi_stable_token_estimate",
                0,
            ),
            volatile_token_estimate=require_int_at_least(
                data.get("volatile_token_estimate", 0),
                "context_cache_layout.volatile_token_estimate",
                0,
            ),
            omitted_token_estimate=require_int_at_least(
                data.get("omitted_token_estimate", 0),
                "context_cache_layout.omitted_token_estimate",
                0,
            ),
            epoch_invalidation_refs=_unique_refs(
                data.get("epoch_invalidation_refs", []),
                "context_cache_layout.epoch_invalidation_refs",
            ),
            provider_cache_profile=_metadata(
                data.get("provider_cache_profile", {}),
                "context_cache_layout.provider_cache_profile",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_cache_layout.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_CACHE_LAYOUT_SCHEMA_VERSION),
                "context_cache_layout.schema_version",
            ),
        )
        layout.validate()
        return layout

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_CACHE_LAYOUT_SCHEMA_VERSION, "context_cache_layout.schema_version")
        _safe_id(self.layout_id, "context_cache_layout.layout_id")
        validate_ref(self.view_ref, "context_cache_layout.view_ref")
        _hash(self.context_hash, "context_cache_layout.context_hash")
        _hash(self.stable_strata_hash, "context_cache_layout.stable_strata_hash")
        _hash(self.semi_stable_strata_hash, "context_cache_layout.semi_stable_strata_hash")
        _hash(self.volatile_strata_hash, "context_cache_layout.volatile_strata_hash")
        _hash(self.omitted_strata_hash, "context_cache_layout.omitted_strata_hash")
        _hash(self.rendered_prefix_hash, "context_cache_layout.rendered_prefix_hash")
        require_int_at_least(self.stable_token_estimate, "context_cache_layout.stable_token_estimate", 0)
        require_int_at_least(self.semi_stable_token_estimate, "context_cache_layout.semi_stable_token_estimate", 0)
        require_int_at_least(self.volatile_token_estimate, "context_cache_layout.volatile_token_estimate", 0)
        require_int_at_least(self.omitted_token_estimate, "context_cache_layout.omitted_token_estimate", 0)
        _unique_refs(self.epoch_invalidation_refs, "context_cache_layout.epoch_invalidation_refs")
        _metadata(self.provider_cache_profile, "context_cache_layout.provider_cache_profile")
        _metadata(self.metadata, "context_cache_layout.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "layout_id": self.layout_id,
            "view_ref": self.view_ref,
            "context_hash": self.context_hash,
            "stable_strata_hash": self.stable_strata_hash,
            "semi_stable_strata_hash": self.semi_stable_strata_hash,
            "volatile_strata_hash": self.volatile_strata_hash,
            "omitted_strata_hash": self.omitted_strata_hash,
            "rendered_prefix_hash": self.rendered_prefix_hash,
            "stable_token_estimate": self.stable_token_estimate,
            "semi_stable_token_estimate": self.semi_stable_token_estimate,
            "volatile_token_estimate": self.volatile_token_estimate,
            "omitted_token_estimate": self.omitted_token_estimate,
            "epoch_invalidation_refs": list(self.epoch_invalidation_refs),
            "provider_cache_profile": dict(self.provider_cache_profile),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextCompileRequest:
    """Host-to-context-compiler request."""

    request_id: str
    role: str
    contract_ref: str
    contract_hash: str
    permission_manifest_ref: str
    context_sources: list[ContextSource] = field(default_factory=list)
    working_set_ref: str | None = None
    recent_user_event_refs: list[str] = field(default_factory=list)
    tool_observation_refs: list[str] = field(default_factory=list)
    summary_refs: list[str] = field(default_factory=list)
    checkpoint_refs: list[str] = field(default_factory=list)
    token_budget: int | None = None
    provider_cache_profile: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_COMPILE_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextCompileRequest":
        data = _refs_only_mapping(payload, "context_compile_request")
        request = cls(
            request_id=_safe_id(data.get("request_id"), "context_compile_request.request_id"),
            role=require_non_empty_str(data.get("role"), "context_compile_request.role"),
            contract_ref=validate_ref(data.get("contract_ref"), "context_compile_request.contract_ref"),
            contract_hash=_hash(data.get("contract_hash"), "context_compile_request.contract_hash"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_compile_request.permission_manifest_ref",
            ),
            context_sources=[
                ContextSource.from_dict(require_mapping(item, "context_compile_request.context_sources[]"))
                for item in _list(data.get("context_sources", []), "context_compile_request.context_sources")
            ],
            working_set_ref=_optional_ref(data.get("working_set_ref"), "context_compile_request.working_set_ref"),
            recent_user_event_refs=_unique_refs(
                data.get("recent_user_event_refs", []),
                "context_compile_request.recent_user_event_refs",
            ),
            tool_observation_refs=_unique_refs(
                data.get("tool_observation_refs", []),
                "context_compile_request.tool_observation_refs",
            ),
            summary_refs=_unique_refs(data.get("summary_refs", []), "context_compile_request.summary_refs"),
            checkpoint_refs=_unique_refs(data.get("checkpoint_refs", []), "context_compile_request.checkpoint_refs"),
            token_budget=_optional_int_at_least(data.get("token_budget"), "context_compile_request.token_budget", 1),
            provider_cache_profile=_metadata(
                data.get("provider_cache_profile", {}),
                "context_compile_request.provider_cache_profile",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_compile_request.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_COMPILE_REQUEST_SCHEMA_VERSION),
                "context_compile_request.schema_version",
            ),
        )
        request.validate()
        return request

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            CONTEXT_COMPILE_REQUEST_SCHEMA_VERSION,
            "context_compile_request.schema_version",
        )
        _safe_id(self.request_id, "context_compile_request.request_id")
        require_non_empty_str(self.role, "context_compile_request.role")
        validate_ref(self.contract_ref, "context_compile_request.contract_ref")
        _hash(self.contract_hash, "context_compile_request.contract_hash")
        validate_ref(self.permission_manifest_ref, "context_compile_request.permission_manifest_ref")
        keys: list[str] = []
        for source in self.context_sources:
            if not isinstance(source, ContextSource):
                raise ContractValidationError("context_compile_request.context_sources must contain ContextSource values")
            source.validate()
            keys.append(source.source_key)
        if len(keys) != len(set(keys)):
            raise ContractValidationError("context_compile_request.context_sources source_key values must be unique")
        _optional_ref(self.working_set_ref, "context_compile_request.working_set_ref")
        _unique_refs(self.recent_user_event_refs, "context_compile_request.recent_user_event_refs")
        _unique_refs(self.tool_observation_refs, "context_compile_request.tool_observation_refs")
        _unique_refs(self.summary_refs, "context_compile_request.summary_refs")
        _unique_refs(self.checkpoint_refs, "context_compile_request.checkpoint_refs")
        _optional_int_at_least(self.token_budget, "context_compile_request.token_budget", 1)
        _metadata(self.provider_cache_profile, "context_compile_request.provider_cache_profile")
        _metadata(self.metadata, "context_compile_request.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "role": self.role,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "permission_manifest_ref": self.permission_manifest_ref,
            "context_sources": [source.to_dict() for source in self.context_sources],
            "working_set_ref": self.working_set_ref,
            "recent_user_event_refs": list(self.recent_user_event_refs),
            "tool_observation_refs": list(self.tool_observation_refs),
            "summary_refs": list(self.summary_refs),
            "checkpoint_refs": list(self.checkpoint_refs),
            "token_budget": self.token_budget,
            "provider_cache_profile": dict(self.provider_cache_profile),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextCompileResult:
    """Refs-first result of a context compile boundary."""

    result_id: str
    view_ref: str
    context_hash: str
    action: ContextCompileAction
    epoch_ref: str | None = None
    pressure_ref: str | None = None
    working_set_ref: str | None = None
    cache_layout_ref: str | None = None
    admitted_update_refs: list[str] = field(default_factory=list)
    omitted_refs: list[str] = field(default_factory=list)
    demoted_refs: list[str] = field(default_factory=list)
    denied_source_refs: list[str] = field(default_factory=list)
    diagnostics_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_COMPILE_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextCompileResult":
        data = _refs_only_mapping(payload, "context_compile_result")
        result = cls(
            result_id=_safe_id(data.get("result_id"), "context_compile_result.result_id"),
            view_ref=validate_ref(data.get("view_ref"), "context_compile_result.view_ref"),
            context_hash=_hash(data.get("context_hash"), "context_compile_result.context_hash"),
            action=require_enum(data.get("action"), ContextCompileAction, "context_compile_result.action"),
            epoch_ref=_optional_ref(data.get("epoch_ref"), "context_compile_result.epoch_ref"),
            pressure_ref=_optional_ref(data.get("pressure_ref"), "context_compile_result.pressure_ref"),
            working_set_ref=_optional_ref(data.get("working_set_ref"), "context_compile_result.working_set_ref"),
            cache_layout_ref=_optional_ref(data.get("cache_layout_ref"), "context_compile_result.cache_layout_ref"),
            admitted_update_refs=_unique_refs(
                data.get("admitted_update_refs", []),
                "context_compile_result.admitted_update_refs",
            ),
            omitted_refs=_unique_refs(data.get("omitted_refs", []), "context_compile_result.omitted_refs"),
            demoted_refs=_unique_refs(data.get("demoted_refs", []), "context_compile_result.demoted_refs"),
            denied_source_refs=_unique_refs(
                data.get("denied_source_refs", []),
                "context_compile_result.denied_source_refs",
            ),
            diagnostics_refs=_unique_refs(data.get("diagnostics_refs", []), "context_compile_result.diagnostics_refs"),
            metadata=_metadata(data.get("metadata", {}), "context_compile_result.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_COMPILE_RESULT_SCHEMA_VERSION),
                "context_compile_result.schema_version",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            CONTEXT_COMPILE_RESULT_SCHEMA_VERSION,
            "context_compile_result.schema_version",
        )
        _safe_id(self.result_id, "context_compile_result.result_id")
        validate_ref(self.view_ref, "context_compile_result.view_ref")
        _hash(self.context_hash, "context_compile_result.context_hash")
        require_enum(self.action, ContextCompileAction, "context_compile_result.action")
        _optional_ref(self.epoch_ref, "context_compile_result.epoch_ref")
        _optional_ref(self.pressure_ref, "context_compile_result.pressure_ref")
        _optional_ref(self.working_set_ref, "context_compile_result.working_set_ref")
        _optional_ref(self.cache_layout_ref, "context_compile_result.cache_layout_ref")
        _unique_refs(self.admitted_update_refs, "context_compile_result.admitted_update_refs")
        _unique_refs(self.omitted_refs, "context_compile_result.omitted_refs")
        _unique_refs(self.demoted_refs, "context_compile_result.demoted_refs")
        _unique_refs(self.denied_source_refs, "context_compile_result.denied_source_refs")
        _unique_refs(self.diagnostics_refs, "context_compile_result.diagnostics_refs")
        _metadata(self.metadata, "context_compile_result.metadata")
        if self.action is ContextCompileAction.BLOCKED_BY_DENIED_REQUIRED_SOURCE and not self.denied_source_refs:
            raise ContractValidationError("context_compile_result denied required source action requires denied_source_refs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "view_ref": self.view_ref,
            "context_hash": self.context_hash,
            "action": self.action.value,
            "epoch_ref": self.epoch_ref,
            "pressure_ref": self.pressure_ref,
            "working_set_ref": self.working_set_ref,
            "cache_layout_ref": self.cache_layout_ref,
            "admitted_update_refs": list(self.admitted_update_refs),
            "omitted_refs": list(self.omitted_refs),
            "demoted_refs": list(self.demoted_refs),
            "denied_source_refs": list(self.denied_source_refs),
            "diagnostics_refs": list(self.diagnostics_refs),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextTurnBoundary:
    """One safe provider-turn boundary record."""

    boundary_id: str
    run_id: str
    call_id: str
    turn_id: str
    role: str
    safe_point_ref: str
    pre_view_ref: str
    status: ContextTurnBoundaryStatus
    post_view_ref: str | None = None
    admitted_user_event_refs: list[str] = field(default_factory=list)
    settled_tool_observation_refs: list[str] = field(default_factory=list)
    context_epoch_ref: str | None = None
    checkpoint_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_TURN_BOUNDARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextTurnBoundary":
        data = _refs_only_mapping(payload, "context_turn_boundary")
        boundary = cls(
            boundary_id=_safe_id(data.get("boundary_id"), "context_turn_boundary.boundary_id"),
            run_id=_safe_id(data.get("run_id"), "context_turn_boundary.run_id"),
            call_id=require_non_empty_str(data.get("call_id"), "context_turn_boundary.call_id"),
            turn_id=_safe_id(data.get("turn_id"), "context_turn_boundary.turn_id"),
            role=require_non_empty_str(data.get("role"), "context_turn_boundary.role"),
            safe_point_ref=validate_ref(data.get("safe_point_ref"), "context_turn_boundary.safe_point_ref"),
            pre_view_ref=validate_ref(data.get("pre_view_ref"), "context_turn_boundary.pre_view_ref"),
            status=require_enum(data.get("status"), ContextTurnBoundaryStatus, "context_turn_boundary.status"),
            post_view_ref=_optional_ref(data.get("post_view_ref"), "context_turn_boundary.post_view_ref"),
            admitted_user_event_refs=_unique_refs(
                data.get("admitted_user_event_refs", []),
                "context_turn_boundary.admitted_user_event_refs",
            ),
            settled_tool_observation_refs=_unique_refs(
                data.get("settled_tool_observation_refs", []),
                "context_turn_boundary.settled_tool_observation_refs",
            ),
            context_epoch_ref=_optional_ref(data.get("context_epoch_ref"), "context_turn_boundary.context_epoch_ref"),
            checkpoint_ref=_optional_ref(data.get("checkpoint_ref"), "context_turn_boundary.checkpoint_ref"),
            metadata=_metadata(data.get("metadata", {}), "context_turn_boundary.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_TURN_BOUNDARY_SCHEMA_VERSION),
                "context_turn_boundary.schema_version",
            ),
        )
        boundary.validate()
        return boundary

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_TURN_BOUNDARY_SCHEMA_VERSION, "context_turn_boundary.schema_version")
        _safe_id(self.boundary_id, "context_turn_boundary.boundary_id")
        _safe_id(self.run_id, "context_turn_boundary.run_id")
        require_non_empty_str(self.call_id, "context_turn_boundary.call_id")
        _safe_id(self.turn_id, "context_turn_boundary.turn_id")
        require_non_empty_str(self.role, "context_turn_boundary.role")
        validate_ref(self.safe_point_ref, "context_turn_boundary.safe_point_ref")
        validate_ref(self.pre_view_ref, "context_turn_boundary.pre_view_ref")
        require_enum(self.status, ContextTurnBoundaryStatus, "context_turn_boundary.status")
        _optional_ref(self.post_view_ref, "context_turn_boundary.post_view_ref")
        _unique_refs(self.admitted_user_event_refs, "context_turn_boundary.admitted_user_event_refs")
        _unique_refs(self.settled_tool_observation_refs, "context_turn_boundary.settled_tool_observation_refs")
        _optional_ref(self.context_epoch_ref, "context_turn_boundary.context_epoch_ref")
        _optional_ref(self.checkpoint_ref, "context_turn_boundary.checkpoint_ref")
        _metadata(self.metadata, "context_turn_boundary.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "boundary_id": self.boundary_id,
            "run_id": self.run_id,
            "call_id": self.call_id,
            "turn_id": self.turn_id,
            "role": self.role,
            "safe_point_ref": self.safe_point_ref,
            "pre_view_ref": self.pre_view_ref,
            "post_view_ref": self.post_view_ref,
            "admitted_user_event_refs": list(self.admitted_user_event_refs),
            "settled_tool_observation_refs": list(self.settled_tool_observation_refs),
            "context_epoch_ref": self.context_epoch_ref,
            "checkpoint_ref": self.checkpoint_ref,
            "status": self.status.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextCheckpoint:
    """Durable refs-only recovery point for one safe context boundary."""

    checkpoint_id: str
    reason_code: str
    role: str
    run_id: str
    call_id: str
    source_snapshot_ref: str
    context_view_ref: str
    context_hash: str
    permission_manifest_ref: str
    created_by: ContextCheckpointCreator = ContextCheckpointCreator.RUNTIME
    summary_refs: list[str] = field(default_factory=list)
    recent_refs: list[str] = field(default_factory=list)
    tool_observation_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""
    schema_version: str = CONTEXT_CHECKPOINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextCheckpoint":
        data = _refs_only_mapping(payload, "context_checkpoint")
        checkpoint = cls(
            checkpoint_id=_safe_id(data.get("checkpoint_id"), "context_checkpoint.checkpoint_id"),
            reason_code=_safe_id(data.get("reason_code"), "context_checkpoint.reason_code"),
            role=require_non_empty_str(data.get("role"), "context_checkpoint.role"),
            run_id=_safe_id(data.get("run_id"), "context_checkpoint.run_id"),
            call_id=require_non_empty_str(data.get("call_id"), "context_checkpoint.call_id"),
            source_snapshot_ref=validate_ref(
                data.get("source_snapshot_ref"),
                "context_checkpoint.source_snapshot_ref",
            ),
            context_view_ref=validate_ref(data.get("context_view_ref"), "context_checkpoint.context_view_ref"),
            context_hash=_hash(data.get("context_hash"), "context_checkpoint.context_hash"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_checkpoint.permission_manifest_ref",
            ),
            created_by=require_enum(
                data.get("created_by", ContextCheckpointCreator.RUNTIME.value),
                ContextCheckpointCreator,
                "context_checkpoint.created_by",
            ),
            summary_refs=_unique_refs(data.get("summary_refs", []), "context_checkpoint.summary_refs"),
            recent_refs=_unique_refs(data.get("recent_refs", []), "context_checkpoint.recent_refs"),
            tool_observation_refs=_unique_refs(
                data.get("tool_observation_refs", []),
                "context_checkpoint.tool_observation_refs",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_checkpoint.metadata"),
            created_at=require_non_empty_str(data.get("created_at"), "context_checkpoint.created_at"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_CHECKPOINT_SCHEMA_VERSION),
                "context_checkpoint.schema_version",
            ),
        )
        checkpoint.validate()
        if (
            "checkpoint_hash" in data
            and require_non_empty_str(data["checkpoint_hash"], "context_checkpoint.checkpoint_hash")
            != checkpoint.checkpoint_hash
        ):
            raise ContractValidationError("context_checkpoint.checkpoint_hash does not match content")
        return checkpoint

    @property
    def checkpoint_hash(self) -> str:
        return stable_json_hash(self._content_dict(include_hash=False))

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_CHECKPOINT_SCHEMA_VERSION, "context_checkpoint.schema_version")
        _safe_id(self.checkpoint_id, "context_checkpoint.checkpoint_id")
        _safe_id(self.reason_code, "context_checkpoint.reason_code")
        require_non_empty_str(self.role, "context_checkpoint.role")
        _safe_id(self.run_id, "context_checkpoint.run_id")
        require_non_empty_str(self.call_id, "context_checkpoint.call_id")
        validate_ref(self.source_snapshot_ref, "context_checkpoint.source_snapshot_ref")
        validate_ref(self.context_view_ref, "context_checkpoint.context_view_ref")
        _hash(self.context_hash, "context_checkpoint.context_hash")
        validate_ref(self.permission_manifest_ref, "context_checkpoint.permission_manifest_ref")
        require_enum(self.created_by, ContextCheckpointCreator, "context_checkpoint.created_by")
        _unique_refs(self.summary_refs, "context_checkpoint.summary_refs")
        _unique_refs(self.recent_refs, "context_checkpoint.recent_refs")
        _unique_refs(self.tool_observation_refs, "context_checkpoint.tool_observation_refs")
        _metadata(self.metadata, "context_checkpoint.metadata")
        require_non_empty_str(self.created_at, "context_checkpoint.created_at")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self._content_dict(include_hash=True)

    def _content_dict(self, *, include_hash: bool) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "checkpoint_id": self.checkpoint_id,
            "reason_code": self.reason_code,
            "role": self.role,
            "run_id": self.run_id,
            "call_id": self.call_id,
            "source_snapshot_ref": self.source_snapshot_ref,
            "context_view_ref": self.context_view_ref,
            "context_hash": self.context_hash,
            "summary_refs": list(self.summary_refs),
            "recent_refs": list(self.recent_refs),
            "tool_observation_refs": list(self.tool_observation_refs),
            "permission_manifest_ref": self.permission_manifest_ref,
            "created_by": self.created_by.value,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }
        if include_hash:
            payload["checkpoint_hash"] = self.checkpoint_hash
        return payload


@dataclass(frozen=True)
class ContextPackage:
    """Opaque ContextEngine package for one resumable provider-turn boundary.

    A ContextPackage indexes the core-owned context records that were active for
    a role at a safe point. It is refs-only: it does not embed rendered provider
    messages, prompts, transcripts, artifact bodies, stdout/stderr, or secrets.
    """

    package_id: str
    role: str
    run_id: str
    step_id: str
    call_id: str
    contract_ref: str
    contract_hash: str
    permission_manifest_ref: str
    permission_manifest_hash: str
    context_view_ref: str
    context_hash: str
    policy_ref: str
    policy_hash: str
    compile_request_ref: str
    compile_result_ref: str
    source_snapshot_ref: str
    epoch_ref: str
    baseline_ref: str
    cache_layout_ref: str
    pressure_ref: str
    turn_safe_point_ref: str
    turn_boundary_ref: str
    step_spec_ref: str | None = None
    step_spec_hash: str | None = None
    tool_schema_hash: str | None = None
    checkpoint_ref: str | None = None
    working_set_ref: str | None = None
    visible_refs: list[str] = field(default_factory=list)
    visible_ref_hashes: Mapping[str, str] = field(default_factory=dict)
    context_record_refs: list[str] = field(default_factory=list)
    context_record_hashes: Mapping[str, str] = field(default_factory=dict)
    context_feed_refs: list[str] = field(default_factory=list)
    diagnostics_refs: list[str] = field(default_factory=list)
    context_compiler_version: str = "missionforge.context_runtime.v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""
    schema_version: str = CONTEXT_PACKAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextPackage":
        data = _refs_only_mapping(payload, "context_package")
        _reject_unknown_fields(data, _CONTEXT_PACKAGE_FIELDS, "context_package")
        package = cls(
            package_id=_safe_id(data.get("package_id"), "context_package.package_id"),
            role=require_non_empty_str(data.get("role"), "context_package.role"),
            run_id=_safe_id(data.get("run_id"), "context_package.run_id"),
            step_id=_safe_id(data.get("step_id"), "context_package.step_id"),
            call_id=require_non_empty_str(data.get("call_id"), "context_package.call_id"),
            contract_ref=validate_ref(data.get("contract_ref"), "context_package.contract_ref"),
            contract_hash=_hash(data.get("contract_hash"), "context_package.contract_hash"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_package.permission_manifest_ref",
            ),
            permission_manifest_hash=_hash(
                data.get("permission_manifest_hash"),
                "context_package.permission_manifest_hash",
            ),
            context_view_ref=validate_ref(data.get("context_view_ref"), "context_package.context_view_ref"),
            context_hash=_hash(data.get("context_hash"), "context_package.context_hash"),
            policy_ref=validate_ref(data.get("policy_ref"), "context_package.policy_ref"),
            policy_hash=_hash(data.get("policy_hash"), "context_package.policy_hash"),
            compile_request_ref=validate_ref(
                data.get("compile_request_ref"),
                "context_package.compile_request_ref",
            ),
            compile_result_ref=validate_ref(
                data.get("compile_result_ref"),
                "context_package.compile_result_ref",
            ),
            source_snapshot_ref=validate_ref(
                data.get("source_snapshot_ref"),
                "context_package.source_snapshot_ref",
            ),
            epoch_ref=validate_ref(data.get("epoch_ref"), "context_package.epoch_ref"),
            baseline_ref=validate_ref(data.get("baseline_ref"), "context_package.baseline_ref"),
            cache_layout_ref=validate_ref(data.get("cache_layout_ref"), "context_package.cache_layout_ref"),
            pressure_ref=validate_ref(data.get("pressure_ref"), "context_package.pressure_ref"),
            turn_safe_point_ref=validate_ref(
                data.get("turn_safe_point_ref"),
                "context_package.turn_safe_point_ref",
            ),
            turn_boundary_ref=validate_ref(data.get("turn_boundary_ref"), "context_package.turn_boundary_ref"),
            step_spec_ref=_optional_ref(data.get("step_spec_ref"), "context_package.step_spec_ref"),
            step_spec_hash=_optional_hash(data.get("step_spec_hash"), "context_package.step_spec_hash"),
            tool_schema_hash=_optional_hash(data.get("tool_schema_hash"), "context_package.tool_schema_hash"),
            checkpoint_ref=_optional_ref(data.get("checkpoint_ref"), "context_package.checkpoint_ref"),
            working_set_ref=_optional_ref(data.get("working_set_ref"), "context_package.working_set_ref"),
            visible_refs=_unique_refs(data.get("visible_refs", []), "context_package.visible_refs"),
            visible_ref_hashes=_hash_mapping(
                data.get("visible_ref_hashes", {}),
                "context_package.visible_ref_hashes",
            ),
            context_record_refs=_unique_refs(
                data.get("context_record_refs", []),
                "context_package.context_record_refs",
            ),
            context_record_hashes=_hash_mapping(
                data.get("context_record_hashes", {}),
                "context_package.context_record_hashes",
            ),
            context_feed_refs=_unique_refs(data.get("context_feed_refs", []), "context_package.context_feed_refs"),
            diagnostics_refs=_unique_refs(data.get("diagnostics_refs", []), "context_package.diagnostics_refs"),
            context_compiler_version=require_non_empty_str(
                data.get("context_compiler_version", "missionforge.context_runtime.v1"),
                "context_package.context_compiler_version",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_package.metadata"),
            created_at=require_non_empty_str(data.get("created_at"), "context_package.created_at"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_PACKAGE_SCHEMA_VERSION),
                "context_package.schema_version",
            ),
        )
        package.validate()
        if (
            "context_package_hash" in data
            and require_non_empty_str(data["context_package_hash"], "context_package.context_package_hash")
            != package.context_package_hash
        ):
            raise ContractValidationError("context_package.context_package_hash does not match content")
        return package

    @property
    def context_package_hash(self) -> str:
        return stable_json_hash(self._content_dict(include_hash=False))

    def validate(self) -> None:
        _require_schema(self.schema_version, CONTEXT_PACKAGE_SCHEMA_VERSION, "context_package.schema_version")
        _safe_id(self.package_id, "context_package.package_id")
        require_non_empty_str(self.role, "context_package.role")
        _safe_id(self.run_id, "context_package.run_id")
        _safe_id(self.step_id, "context_package.step_id")
        require_non_empty_str(self.call_id, "context_package.call_id")
        validate_ref(self.contract_ref, "context_package.contract_ref")
        _hash(self.contract_hash, "context_package.contract_hash")
        validate_ref(self.permission_manifest_ref, "context_package.permission_manifest_ref")
        _hash(self.permission_manifest_hash, "context_package.permission_manifest_hash")
        validate_ref(self.context_view_ref, "context_package.context_view_ref")
        _hash(self.context_hash, "context_package.context_hash")
        validate_ref(self.policy_ref, "context_package.policy_ref")
        _hash(self.policy_hash, "context_package.policy_hash")
        validate_ref(self.compile_request_ref, "context_package.compile_request_ref")
        validate_ref(self.compile_result_ref, "context_package.compile_result_ref")
        validate_ref(self.source_snapshot_ref, "context_package.source_snapshot_ref")
        validate_ref(self.epoch_ref, "context_package.epoch_ref")
        validate_ref(self.baseline_ref, "context_package.baseline_ref")
        validate_ref(self.cache_layout_ref, "context_package.cache_layout_ref")
        validate_ref(self.pressure_ref, "context_package.pressure_ref")
        validate_ref(self.turn_safe_point_ref, "context_package.turn_safe_point_ref")
        validate_ref(self.turn_boundary_ref, "context_package.turn_boundary_ref")
        _optional_ref(self.step_spec_ref, "context_package.step_spec_ref")
        _optional_hash(self.step_spec_hash, "context_package.step_spec_hash")
        _optional_hash(self.tool_schema_hash, "context_package.tool_schema_hash")
        _optional_ref(self.checkpoint_ref, "context_package.checkpoint_ref")
        _optional_ref(self.working_set_ref, "context_package.working_set_ref")
        visible_refs = _unique_refs(self.visible_refs, "context_package.visible_refs")
        visible_hashes = _hash_mapping(self.visible_ref_hashes, "context_package.visible_ref_hashes")
        for ref in visible_hashes:
            if ref not in visible_refs:
                raise ContractValidationError("context_package.visible_ref_hashes keys must appear in visible_refs")
        record_refs = _unique_refs(self.context_record_refs, "context_package.context_record_refs")
        record_hashes = _hash_mapping(self.context_record_hashes, "context_package.context_record_hashes")
        required_record_refs = {
            self.context_view_ref,
            self.policy_ref,
            self.compile_request_ref,
            self.compile_result_ref,
            self.source_snapshot_ref,
            self.epoch_ref,
            self.baseline_ref,
            self.cache_layout_ref,
            self.pressure_ref,
            self.turn_safe_point_ref,
            self.turn_boundary_ref,
        }
        if self.checkpoint_ref:
            required_record_refs.add(self.checkpoint_ref)
        if not required_record_refs.issubset(set(record_refs)):
            raise ContractValidationError("context_package.context_record_refs must include core ContextEngine refs")
        for ref in record_hashes:
            if ref not in record_refs:
                raise ContractValidationError("context_package.context_record_hashes keys must appear in context_record_refs")
        _unique_refs(self.context_feed_refs, "context_package.context_feed_refs")
        _unique_refs(self.diagnostics_refs, "context_package.diagnostics_refs")
        require_non_empty_str(self.context_compiler_version, "context_package.context_compiler_version")
        _metadata(self.metadata, "context_package.metadata")
        require_non_empty_str(self.created_at, "context_package.created_at")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self._content_dict(include_hash=True)

    def _content_dict(self, *, include_hash: bool) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "role": self.role,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "call_id": self.call_id,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "permission_manifest_ref": self.permission_manifest_ref,
            "permission_manifest_hash": self.permission_manifest_hash,
            "context_view_ref": self.context_view_ref,
            "context_hash": self.context_hash,
            "policy_ref": self.policy_ref,
            "policy_hash": self.policy_hash,
            "compile_request_ref": self.compile_request_ref,
            "compile_result_ref": self.compile_result_ref,
            "source_snapshot_ref": self.source_snapshot_ref,
            "epoch_ref": self.epoch_ref,
            "baseline_ref": self.baseline_ref,
            "cache_layout_ref": self.cache_layout_ref,
            "pressure_ref": self.pressure_ref,
            "turn_safe_point_ref": self.turn_safe_point_ref,
            "turn_boundary_ref": self.turn_boundary_ref,
            "step_spec_ref": self.step_spec_ref,
            "step_spec_hash": self.step_spec_hash,
            "tool_schema_hash": self.tool_schema_hash,
            "checkpoint_ref": self.checkpoint_ref,
            "working_set_ref": self.working_set_ref,
            "visible_refs": list(self.visible_refs),
            "visible_ref_hashes": dict(self.visible_ref_hashes),
            "context_record_refs": list(self.context_record_refs),
            "context_record_hashes": dict(self.context_record_hashes),
            "context_feed_refs": list(self.context_feed_refs),
            "diagnostics_refs": list(self.diagnostics_refs),
            "context_compiler_version": self.context_compiler_version,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }
        if include_hash:
            payload["context_package_hash"] = self.context_package_hash
        return payload


@dataclass(frozen=True)
class ContextReductionRequest:
    """MissionForge-managed request for an internal context reducer PiWorker."""

    reduction_id: str
    reason: ContextReductionReason
    role: str
    contract_ref: str
    contract_hash: str
    permission_manifest_ref: str
    context_view_ref: str
    context_hash: str
    source_snapshot_ref: str
    expected_output_refs: list[str]
    worker_brief_ref: str | None = None
    judge_rubric_ref: str | None = None
    pressure_ref: str | None = None
    current_working_set_ref: str | None = None
    thrash_diagnostics_refs: list[str] = field(default_factory=list)
    recent_projection_refs: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    tool_observation_refs: list[str] = field(default_factory=list)
    checkpoint_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_REDUCTION_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextReductionRequest":
        data = _refs_only_mapping(payload, "context_reduction_request")
        request = cls(
            reduction_id=_safe_id(data.get("reduction_id"), "context_reduction_request.reduction_id"),
            reason=require_enum(data.get("reason"), ContextReductionReason, "context_reduction_request.reason"),
            role=require_non_empty_str(data.get("role"), "context_reduction_request.role"),
            contract_ref=validate_ref(data.get("contract_ref"), "context_reduction_request.contract_ref"),
            contract_hash=_hash(data.get("contract_hash"), "context_reduction_request.contract_hash"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_reduction_request.permission_manifest_ref",
            ),
            context_view_ref=validate_ref(
                data.get("context_view_ref"),
                "context_reduction_request.context_view_ref",
            ),
            context_hash=_hash(data.get("context_hash"), "context_reduction_request.context_hash"),
            source_snapshot_ref=validate_ref(
                data.get("source_snapshot_ref"),
                "context_reduction_request.source_snapshot_ref",
            ),
            expected_output_refs=_unique_refs(
                data.get("expected_output_refs", []),
                "context_reduction_request.expected_output_refs",
            ),
            worker_brief_ref=_optional_ref(data.get("worker_brief_ref"), "context_reduction_request.worker_brief_ref"),
            judge_rubric_ref=_optional_ref(data.get("judge_rubric_ref"), "context_reduction_request.judge_rubric_ref"),
            pressure_ref=_optional_ref(data.get("pressure_ref"), "context_reduction_request.pressure_ref"),
            current_working_set_ref=_optional_ref(
                data.get("current_working_set_ref"),
                "context_reduction_request.current_working_set_ref",
            ),
            thrash_diagnostics_refs=_unique_refs(
                data.get("thrash_diagnostics_refs", []),
                "context_reduction_request.thrash_diagnostics_refs",
            ),
            recent_projection_refs=_unique_refs(
                data.get("recent_projection_refs", []),
                "context_reduction_request.recent_projection_refs",
            ),
            source_refs=_unique_refs(
                data.get("source_refs", []),
                "context_reduction_request.source_refs",
            ),
            tool_observation_refs=_unique_refs(
                data.get("tool_observation_refs", []),
                "context_reduction_request.tool_observation_refs",
            ),
            checkpoint_refs=_unique_refs(
                data.get("checkpoint_refs", []),
                "context_reduction_request.checkpoint_refs",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_reduction_request.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_REDUCTION_REQUEST_SCHEMA_VERSION),
                "context_reduction_request.schema_version",
            ),
        )
        request.validate()
        if (
            "reduction_request_hash" in data
            and require_non_empty_str(
                data["reduction_request_hash"],
                "context_reduction_request.reduction_request_hash",
            )
            != request.reduction_request_hash
        ):
            raise ContractValidationError("context_reduction_request.reduction_request_hash does not match content")
        return request

    @property
    def reduction_request_hash(self) -> str:
        return stable_json_hash(self._content_dict(include_hash=False))

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            CONTEXT_REDUCTION_REQUEST_SCHEMA_VERSION,
            "context_reduction_request.schema_version",
        )
        _safe_id(self.reduction_id, "context_reduction_request.reduction_id")
        require_enum(self.reason, ContextReductionReason, "context_reduction_request.reason")
        require_non_empty_str(self.role, "context_reduction_request.role")
        validate_ref(self.contract_ref, "context_reduction_request.contract_ref")
        _hash(self.contract_hash, "context_reduction_request.contract_hash")
        validate_ref(self.permission_manifest_ref, "context_reduction_request.permission_manifest_ref")
        validate_ref(self.context_view_ref, "context_reduction_request.context_view_ref")
        _hash(self.context_hash, "context_reduction_request.context_hash")
        validate_ref(self.source_snapshot_ref, "context_reduction_request.source_snapshot_ref")
        if not self.expected_output_refs:
            raise ContractValidationError("context_reduction_request.expected_output_refs must not be empty")
        _unique_refs(self.expected_output_refs, "context_reduction_request.expected_output_refs")
        _optional_ref(self.worker_brief_ref, "context_reduction_request.worker_brief_ref")
        _optional_ref(self.judge_rubric_ref, "context_reduction_request.judge_rubric_ref")
        _optional_ref(self.pressure_ref, "context_reduction_request.pressure_ref")
        _optional_ref(self.current_working_set_ref, "context_reduction_request.current_working_set_ref")
        _unique_refs(self.thrash_diagnostics_refs, "context_reduction_request.thrash_diagnostics_refs")
        _unique_refs(self.recent_projection_refs, "context_reduction_request.recent_projection_refs")
        _unique_refs(self.source_refs, "context_reduction_request.source_refs")
        _unique_refs(self.tool_observation_refs, "context_reduction_request.tool_observation_refs")
        _unique_refs(self.checkpoint_refs, "context_reduction_request.checkpoint_refs")
        _metadata(self.metadata, "context_reduction_request.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self._content_dict(include_hash=True)

    def _content_dict(self, *, include_hash: bool) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "reduction_id": self.reduction_id,
            "reason": self.reason.value,
            "role": self.role,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "permission_manifest_ref": self.permission_manifest_ref,
            "context_view_ref": self.context_view_ref,
            "context_hash": self.context_hash,
            "source_snapshot_ref": self.source_snapshot_ref,
            "expected_output_refs": list(self.expected_output_refs),
            "worker_brief_ref": self.worker_brief_ref,
            "judge_rubric_ref": self.judge_rubric_ref,
            "pressure_ref": self.pressure_ref,
            "current_working_set_ref": self.current_working_set_ref,
            "thrash_diagnostics_refs": list(self.thrash_diagnostics_refs),
            "recent_projection_refs": list(self.recent_projection_refs),
            "source_refs": list(self.source_refs),
            "tool_observation_refs": list(self.tool_observation_refs),
            "checkpoint_refs": list(self.checkpoint_refs),
            "metadata": dict(self.metadata),
        }
        if include_hash:
            payload["reduction_request_hash"] = self.reduction_request_hash
        return payload


@dataclass(frozen=True)
class ContextReductionResult:
    """Refs-only result from a managed context reducer PiWorker."""

    reduction_id: str
    status: ContextReductionStatus
    request_ref: str
    permission_manifest_ref: str
    checkpoint_ref: str | None = None
    working_set_ref: str | None = None
    summary_refs: list[str] = field(default_factory=list)
    pinned_refs: list[str] = field(default_factory=list)
    evicted_refs: list[str] = field(default_factory=list)
    omitted_refs: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    denied_source_refs: list[str] = field(default_factory=list)
    compaction_record_ref: str | None = None
    validation_report_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_REDUCTION_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextReductionResult":
        data = _refs_only_mapping(payload, "context_reduction_result")
        result = cls(
            reduction_id=_safe_id(data.get("reduction_id"), "context_reduction_result.reduction_id"),
            status=require_enum(data.get("status"), ContextReductionStatus, "context_reduction_result.status"),
            request_ref=validate_ref(data.get("request_ref"), "context_reduction_result.request_ref"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_reduction_result.permission_manifest_ref",
            ),
            checkpoint_ref=_optional_ref(data.get("checkpoint_ref"), "context_reduction_result.checkpoint_ref"),
            working_set_ref=_optional_ref(data.get("working_set_ref"), "context_reduction_result.working_set_ref"),
            summary_refs=_unique_refs(data.get("summary_refs", []), "context_reduction_result.summary_refs"),
            pinned_refs=_unique_refs(data.get("pinned_refs", []), "context_reduction_result.pinned_refs"),
            evicted_refs=_unique_refs(data.get("evicted_refs", []), "context_reduction_result.evicted_refs"),
            omitted_refs=_unique_refs(data.get("omitted_refs", []), "context_reduction_result.omitted_refs"),
            source_refs=_unique_refs(data.get("source_refs", []), "context_reduction_result.source_refs"),
            denied_source_refs=_unique_refs(
                data.get("denied_source_refs", []),
                "context_reduction_result.denied_source_refs",
            ),
            compaction_record_ref=_optional_ref(
                data.get("compaction_record_ref"),
                "context_reduction_result.compaction_record_ref",
            ),
            validation_report_ref=_optional_ref(
                data.get("validation_report_ref"),
                "context_reduction_result.validation_report_ref",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_reduction_result.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_REDUCTION_RESULT_SCHEMA_VERSION),
                "context_reduction_result.schema_version",
            ),
        )
        result.validate()
        if (
            "reduction_result_hash" in data
            and require_non_empty_str(data["reduction_result_hash"], "context_reduction_result.reduction_result_hash")
            != result.reduction_result_hash
        ):
            raise ContractValidationError("context_reduction_result.reduction_result_hash does not match content")
        return result

    @property
    def reduction_result_hash(self) -> str:
        return stable_json_hash(self._content_dict(include_hash=False))

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            CONTEXT_REDUCTION_RESULT_SCHEMA_VERSION,
            "context_reduction_result.schema_version",
        )
        _safe_id(self.reduction_id, "context_reduction_result.reduction_id")
        require_enum(self.status, ContextReductionStatus, "context_reduction_result.status")
        validate_ref(self.request_ref, "context_reduction_result.request_ref")
        validate_ref(self.permission_manifest_ref, "context_reduction_result.permission_manifest_ref")
        _optional_ref(self.checkpoint_ref, "context_reduction_result.checkpoint_ref")
        _optional_ref(self.working_set_ref, "context_reduction_result.working_set_ref")
        _unique_refs(self.summary_refs, "context_reduction_result.summary_refs")
        _unique_refs(self.pinned_refs, "context_reduction_result.pinned_refs")
        _unique_refs(self.evicted_refs, "context_reduction_result.evicted_refs")
        _unique_refs(self.omitted_refs, "context_reduction_result.omitted_refs")
        _unique_refs(self.source_refs, "context_reduction_result.source_refs")
        _unique_refs(self.denied_source_refs, "context_reduction_result.denied_source_refs")
        _optional_ref(self.compaction_record_ref, "context_reduction_result.compaction_record_ref")
        _optional_ref(self.validation_report_ref, "context_reduction_result.validation_report_ref")
        _metadata(self.metadata, "context_reduction_result.metadata")
        if self.status is ContextReductionStatus.COMPLETED and not (
            self.checkpoint_ref or self.working_set_ref or self.summary_refs
        ):
            raise ContractValidationError("completed context_reduction_result requires state output refs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self._content_dict(include_hash=True)

    def _content_dict(self, *, include_hash: bool) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "reduction_id": self.reduction_id,
            "status": self.status.value,
            "request_ref": self.request_ref,
            "permission_manifest_ref": self.permission_manifest_ref,
            "checkpoint_ref": self.checkpoint_ref,
            "working_set_ref": self.working_set_ref,
            "summary_refs": list(self.summary_refs),
            "pinned_refs": list(self.pinned_refs),
            "evicted_refs": list(self.evicted_refs),
            "omitted_refs": list(self.omitted_refs),
            "source_refs": list(self.source_refs),
            "denied_source_refs": list(self.denied_source_refs),
            "compaction_record_ref": self.compaction_record_ref,
            "validation_report_ref": self.validation_report_ref,
            "metadata": dict(self.metadata),
        }
        if include_hash:
            payload["reduction_result_hash"] = self.reduction_result_hash
        return payload


@dataclass(frozen=True)
class ContextCompactionRecord:
    """Durable lifecycle record for a compaction attempt."""

    record_id: str
    status: ContextCompactionStatus
    reason_code: str
    input_epoch_ref: str
    input_context_view_ref: str
    checkpoint_ref: str
    producing_role: str
    permission_manifest_ref: str
    output_epoch_ref: str | None = None
    output_context_view_ref: str | None = None
    summary_artifact_refs: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    denied_source_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_COMPACTION_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextCompactionRecord":
        data = _refs_only_mapping(payload, "context_compaction_record")
        record = cls(
            record_id=_safe_id(data.get("record_id"), "context_compaction_record.record_id"),
            status=require_enum(data.get("status"), ContextCompactionStatus, "context_compaction_record.status"),
            reason_code=_safe_id(data.get("reason_code"), "context_compaction_record.reason_code"),
            input_epoch_ref=validate_ref(data.get("input_epoch_ref"), "context_compaction_record.input_epoch_ref"),
            input_context_view_ref=validate_ref(
                data.get("input_context_view_ref"),
                "context_compaction_record.input_context_view_ref",
            ),
            checkpoint_ref=validate_ref(data.get("checkpoint_ref"), "context_compaction_record.checkpoint_ref"),
            producing_role=require_non_empty_str(data.get("producing_role"), "context_compaction_record.producing_role"),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "context_compaction_record.permission_manifest_ref",
            ),
            output_epoch_ref=_optional_ref(data.get("output_epoch_ref"), "context_compaction_record.output_epoch_ref"),
            output_context_view_ref=_optional_ref(
                data.get("output_context_view_ref"),
                "context_compaction_record.output_context_view_ref",
            ),
            summary_artifact_refs=_unique_refs(
                data.get("summary_artifact_refs", []),
                "context_compaction_record.summary_artifact_refs",
            ),
            source_refs=_unique_refs(data.get("source_refs", []), "context_compaction_record.source_refs"),
            denied_source_refs=_unique_refs(
                data.get("denied_source_refs", []),
                "context_compaction_record.denied_source_refs",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_compaction_record.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_COMPACTION_RECORD_SCHEMA_VERSION),
                "context_compaction_record.schema_version",
            ),
        )
        record.validate()
        return record

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            CONTEXT_COMPACTION_RECORD_SCHEMA_VERSION,
            "context_compaction_record.schema_version",
        )
        _safe_id(self.record_id, "context_compaction_record.record_id")
        require_enum(self.status, ContextCompactionStatus, "context_compaction_record.status")
        _safe_id(self.reason_code, "context_compaction_record.reason_code")
        validate_ref(self.input_epoch_ref, "context_compaction_record.input_epoch_ref")
        validate_ref(self.input_context_view_ref, "context_compaction_record.input_context_view_ref")
        validate_ref(self.checkpoint_ref, "context_compaction_record.checkpoint_ref")
        require_non_empty_str(self.producing_role, "context_compaction_record.producing_role")
        validate_ref(self.permission_manifest_ref, "context_compaction_record.permission_manifest_ref")
        _optional_ref(self.output_epoch_ref, "context_compaction_record.output_epoch_ref")
        _optional_ref(self.output_context_view_ref, "context_compaction_record.output_context_view_ref")
        _unique_refs(self.summary_artifact_refs, "context_compaction_record.summary_artifact_refs")
        _unique_refs(self.source_refs, "context_compaction_record.source_refs")
        _unique_refs(self.denied_source_refs, "context_compaction_record.denied_source_refs")
        _metadata(self.metadata, "context_compaction_record.metadata")
        if self.status is ContextCompactionStatus.ENDED and (not self.output_epoch_ref or not self.output_context_view_ref):
            raise ContractValidationError("ended context_compaction_record requires output epoch and view refs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "input_epoch_ref": self.input_epoch_ref,
            "output_epoch_ref": self.output_epoch_ref,
            "input_context_view_ref": self.input_context_view_ref,
            "output_context_view_ref": self.output_context_view_ref,
            "checkpoint_ref": self.checkpoint_ref,
            "summary_artifact_refs": list(self.summary_artifact_refs),
            "source_refs": list(self.source_refs),
            "denied_source_refs": list(self.denied_source_refs),
            "producing_role": self.producing_role,
            "permission_manifest_ref": self.permission_manifest_ref,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextReadObservation:
    """Refs-only read/query identity for repeated-read diagnostics."""

    observation_id: str
    source_ref: str | None = None
    source_hash: str | None = None
    source_range: Mapping[str, int] = field(default_factory=dict)
    query_ref: str | None = None
    query_hash: str | None = None
    tool_name: str = ""
    count: int = 1
    normalized_metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_READ_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextReadObservation":
        data = _refs_only_mapping(payload, "context_read_observation")
        observation = cls(
            observation_id=_safe_id(data.get("observation_id"), "context_read_observation.observation_id"),
            source_ref=_optional_ref(data.get("source_ref"), "context_read_observation.source_ref"),
            source_hash=_optional_hash(data.get("source_hash"), "context_read_observation.source_hash"),
            source_range=_source_range(data.get("source_range", {}), "context_read_observation.source_range"),
            query_ref=_optional_ref(data.get("query_ref"), "context_read_observation.query_ref"),
            query_hash=_optional_hash(data.get("query_hash"), "context_read_observation.query_hash"),
            tool_name=_optional_safe_label(data.get("tool_name", ""), "context_read_observation.tool_name"),
            count=require_int_at_least(data.get("count", 1), "context_read_observation.count", 1),
            normalized_metadata=_normalized_query_metadata(
                data.get("normalized_metadata", {}),
                "context_read_observation.normalized_metadata",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_READ_OBSERVATION_SCHEMA_VERSION),
                "context_read_observation.schema_version",
            ),
        )
        observation.validate()
        return observation

    @property
    def identity_hash(self) -> str:
        return stable_json_hash(
            {
                "source_ref": self.source_ref,
                "source_hash": self.source_hash,
                "source_range": dict(self.source_range),
                "query_ref": self.query_ref,
                "query_hash": self.query_hash,
                "tool_name": self.tool_name,
                "normalized_metadata": dict(self.normalized_metadata),
            }
        )

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            CONTEXT_READ_OBSERVATION_SCHEMA_VERSION,
            "context_read_observation.schema_version",
        )
        _safe_id(self.observation_id, "context_read_observation.observation_id")
        _optional_ref(self.source_ref, "context_read_observation.source_ref")
        _optional_hash(self.source_hash, "context_read_observation.source_hash")
        _source_range(self.source_range, "context_read_observation.source_range")
        _optional_ref(self.query_ref, "context_read_observation.query_ref")
        _optional_hash(self.query_hash, "context_read_observation.query_hash")
        _optional_safe_label(self.tool_name, "context_read_observation.tool_name")
        require_int_at_least(self.count, "context_read_observation.count", 1)
        _normalized_query_metadata(self.normalized_metadata, "context_read_observation.normalized_metadata")
        if self.source_ref is None and self.query_ref is None:
            raise ContractValidationError("context_read_observation requires source_ref or query_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "source_ref": self.source_ref,
            "source_hash": self.source_hash,
            "source_range": dict(self.source_range),
            "query_ref": self.query_ref,
            "query_hash": self.query_hash,
            "tool_name": self.tool_name,
            "count": self.count,
            "normalized_metadata": dict(self.normalized_metadata),
            "identity_hash": self.identity_hash,
        }


@dataclass(frozen=True)
class ContextThrashDiagnostics:
    """Refs-only diagnostics for repeated unchanged reads."""

    diagnostics_id: str
    phase_label: str
    observations: list[ContextReadObservation] = field(default_factory=list)
    repeated_observation_ids: list[str] = field(default_factory=list)
    expected_reread_observation_ids: list[str] = field(default_factory=list)
    recommended_action: ContextPressureAction = ContextPressureAction.CONTINUE
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_THRASH_DIAGNOSTICS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContextThrashDiagnostics":
        data = _refs_only_mapping(payload, "context_thrash_diagnostics")
        diagnostics = cls(
            diagnostics_id=_safe_id(data.get("diagnostics_id"), "context_thrash_diagnostics.diagnostics_id"),
            phase_label=_safe_id(data.get("phase_label"), "context_thrash_diagnostics.phase_label"),
            observations=[
                ContextReadObservation.from_dict(require_mapping(item, "context_thrash_diagnostics.observations[]"))
                for item in _list(data.get("observations", []), "context_thrash_diagnostics.observations")
            ],
            repeated_observation_ids=_unique_strings(
                data.get("repeated_observation_ids", []),
                "context_thrash_diagnostics.repeated_observation_ids",
            ),
            expected_reread_observation_ids=_unique_strings(
                data.get("expected_reread_observation_ids", []),
                "context_thrash_diagnostics.expected_reread_observation_ids",
            ),
            recommended_action=require_enum(
                data.get("recommended_action", ContextPressureAction.CONTINUE.value),
                ContextPressureAction,
                "context_thrash_diagnostics.recommended_action",
            ),
            metadata=_metadata(data.get("metadata", {}), "context_thrash_diagnostics.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", CONTEXT_THRASH_DIAGNOSTICS_SCHEMA_VERSION),
                "context_thrash_diagnostics.schema_version",
            ),
        )
        diagnostics.validate()
        return diagnostics

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            CONTEXT_THRASH_DIAGNOSTICS_SCHEMA_VERSION,
            "context_thrash_diagnostics.schema_version",
        )
        _safe_id(self.diagnostics_id, "context_thrash_diagnostics.diagnostics_id")
        _safe_id(self.phase_label, "context_thrash_diagnostics.phase_label")
        ids: list[str] = []
        for observation in self.observations:
            if not isinstance(observation, ContextReadObservation):
                raise ContractValidationError("context_thrash_diagnostics.observations must contain read observations")
            observation.validate()
            ids.append(observation.observation_id)
        if len(ids) != len(set(ids)):
            raise ContractValidationError("context_thrash_diagnostics observation ids must be unique")
        _unique_strings(self.repeated_observation_ids, "context_thrash_diagnostics.repeated_observation_ids")
        _unique_strings(
            self.expected_reread_observation_ids,
            "context_thrash_diagnostics.expected_reread_observation_ids",
        )
        unknown = (set(self.repeated_observation_ids) | set(self.expected_reread_observation_ids)) - set(ids)
        if unknown:
            raise ContractValidationError("context_thrash_diagnostics references unknown observation ids")
        require_enum(self.recommended_action, ContextPressureAction, "context_thrash_diagnostics.recommended_action")
        _metadata(self.metadata, "context_thrash_diagnostics.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "diagnostics_id": self.diagnostics_id,
            "phase_label": self.phase_label,
            "observations": [observation.to_dict() for observation in self.observations],
            "repeated_observation_ids": list(self.repeated_observation_ids),
            "expected_reread_observation_ids": list(self.expected_reread_observation_ids),
            "recommended_action": self.recommended_action.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextSourceFilterResult:
    """Permission-filter result for context source selection."""

    allowed_sources: list[ContextSource]
    denied_source_keys: list[str] = field(default_factory=list)
    denied_required_source_keys: list[str] = field(default_factory=list)
    denied_source_refs: list[str] = field(default_factory=list)
    unavailable_source_keys: list[str] = field(default_factory=list)
    unavailable_required_source_keys: list[str] = field(default_factory=list)
    unavailable_source_refs: list[str] = field(default_factory=list)

    @property
    def has_denied_required_source(self) -> bool:
        return bool(self.denied_required_source_keys)

    @property
    def has_unavailable_required_source(self) -> bool:
        return bool(self.unavailable_required_source_keys)


@dataclass(frozen=True)
class CompiledContext:
    """Product-neutral context compile output for one provider-turn boundary."""

    request: ContextCompileRequest
    view: ContextView
    result: ContextCompileResult
    cache_layout: ContextCacheLayout
    pressure: ContextPressureDiagnostics
    source_snapshots: list[ContextSourceSnapshot] = field(default_factory=list)
    filter_result: ContextSourceFilterResult | None = None

    def __post_init__(self) -> None:
        self.request.validate()
        self.view.validate()
        self.result.validate()
        self.cache_layout.validate()
        self.pressure.validate()
        for snapshot in self.source_snapshots:
            if not isinstance(snapshot, ContextSourceSnapshot):
                raise ContractValidationError("compiled_context.source_snapshots must contain ContextSourceSnapshot values")
            snapshot.validate()
        if self.filter_result is not None and not isinstance(self.filter_result, ContextSourceFilterResult):
            raise ContractValidationError("compiled_context.filter_result must be a ContextSourceFilterResult")


def filter_context_sources(sources: list[ContextSource], read_gate: ReadGate) -> ContextSourceFilterResult:
    """Filter sources through ReadGate before any projection or rendering."""

    allowed: list[ContextSource] = []
    denied_keys: list[str] = []
    denied_required_keys: list[str] = []
    denied_refs: list[str] = []
    unavailable_keys: list[str] = []
    unavailable_required_keys: list[str] = []
    unavailable_refs: list[str] = []
    for source in sources:
        source.validate()
        refs = _refs_for_source_permission(source)
        if source.metadata.get("unavailable") is True:
            unavailable_keys.append(source.source_key)
            if source.required:
                unavailable_required_keys.append(source.source_key)
            unavailable_refs.extend(refs)
            continue
        denied_for_source = [ref for ref in refs if not read_gate.check(ref).allowed]
        if denied_for_source:
            denied_keys.append(source.source_key)
            if source.required:
                denied_required_keys.append(source.source_key)
            denied_refs.extend(denied_for_source)
            continue
        allowed.append(source)
    return ContextSourceFilterResult(
        allowed_sources=allowed,
        denied_source_keys=_unique_ordered(denied_keys),
        denied_required_source_keys=_unique_ordered(denied_required_keys),
        denied_source_refs=_unique_ordered_refs(denied_refs),
        unavailable_source_keys=_unique_ordered(unavailable_keys),
        unavailable_required_source_keys=_unique_ordered(unavailable_required_keys),
        unavailable_source_refs=_unique_ordered_refs(unavailable_refs),
    )


def compile_context_request(
    *,
    request: ContextCompileRequest,
    read_gate: ReadGate,
    view_ref: str,
    pressure_ref: str,
    cache_layout_ref: str,
    result_id: str,
    layout_id: str,
    pressure_id: str = "",
    checkpoint_ref: str | None = None,
    soft_ratio: float = 0.70,
    hard_ratio: float = 0.90,
) -> CompiledContext:
    """Compile a ContextCompileRequest into a refs-only ContextView boundary.

    This helper performs product-neutral source admission, deterministic bucket
    placement, cache-layout diagnostics, and pressure recommendation. It does
    not render provider messages or infer semantic importance.
    """

    request.validate()
    view_ref = validate_ref(view_ref, "context_compile.view_ref")
    pressure_ref = validate_ref(pressure_ref, "context_compile.pressure_ref")
    cache_layout_ref = validate_ref(cache_layout_ref, "context_compile.cache_layout_ref")
    result_id = _safe_id(result_id, "context_compile.result_id")
    layout_id = _safe_id(layout_id, "context_compile.layout_id")
    if pressure_id:
        _safe_id(pressure_id, "context_compile.pressure_id")
    filter_result = filter_context_sources(list(request.context_sources), read_gate)
    snapshots = [
        ContextSourceSnapshot.from_source(source, sequence=index)
        for index, source in enumerate(filter_result.allowed_sources)
    ]
    view = _context_view_from_request(
        request=request,
        allowed_sources=filter_result.allowed_sources,
        denied_source_refs=filter_result.denied_source_refs,
        diagnostics_ref=view_ref,
    )
    layout = build_context_cache_layout(
        layout_id=layout_id,
        view_ref=view_ref,
        view=view,
        provider_cache_profile=request.provider_cache_profile,
    )
    estimated_tokens = sum(segment.token_estimate for segment in view.all_segments)
    effective_token_budget = request.token_budget if request.token_budget is not None else max(1, estimated_tokens * 2)
    pressure = build_context_pressure_diagnostics(
        view_ref=view_ref,
        view=view,
        estimated_input_tokens=estimated_tokens,
        token_budget=effective_token_budget,
        soft_ratio=soft_ratio,
        hard_ratio=hard_ratio,
        checkpoint_ref=checkpoint_ref,
    )
    action = _compile_action_from_filter_and_pressure(filter_result, pressure.recommended_action)
    result = ContextCompileResult(
        result_id=result_id,
        view_ref=view_ref,
        context_hash=view.context_hash,
        action=action,
        pressure_ref=pressure_ref,
        working_set_ref=request.working_set_ref,
        cache_layout_ref=cache_layout_ref,
        admitted_update_refs=_admitted_update_refs(filter_result.allowed_sources),
        omitted_refs=_omitted_refs(filter_result.allowed_sources, filter_result.denied_source_refs),
        demoted_refs=_demoted_refs(filter_result.allowed_sources),
        denied_source_refs=list(filter_result.denied_source_refs),
        diagnostics_refs=[],
        metadata={
            "request_id": request.request_id,
            "denied_source_keys": list(filter_result.denied_source_keys),
            "denied_required_source_keys": list(filter_result.denied_required_source_keys),
            "unavailable_source_keys": list(filter_result.unavailable_source_keys),
            "unavailable_required_source_keys": list(filter_result.unavailable_required_source_keys),
            "unavailable_source_refs": list(filter_result.unavailable_source_refs),
            "pressure_action": pressure.recommended_action.value,
            "pressure_id": pressure_id,
            "source_snapshot_count": len(snapshots),
        },
    )
    return CompiledContext(
        request=request,
        view=view,
        result=result,
        cache_layout=layout,
        pressure=pressure,
        source_snapshots=snapshots,
        filter_result=filter_result,
    )


def build_context_epoch(
    *,
    epoch_id: str,
    role: str,
    contract_hash: str,
    permission_manifest_ref: str,
    baseline_ref: str,
    baseline_hash: str,
    source_snapshot_ref: str,
    baseline_seq: int = 0,
    provider_cache_profile: Mapping[str, Any] | None = None,
    context_view_ref: str | None = None,
    parent_epoch_ref: str | None = None,
    created_at: str | None = None,
) -> ContextEpoch:
    """Build a validated cache epoch record."""

    return ContextEpoch(
        epoch_id=epoch_id,
        role=role,
        contract_hash=contract_hash,
        permission_manifest_ref=permission_manifest_ref,
        baseline_ref=baseline_ref,
        baseline_hash=baseline_hash,
        source_snapshot_ref=source_snapshot_ref,
        baseline_seq=baseline_seq,
        provider_cache_profile={} if provider_cache_profile is None else provider_cache_profile,
        context_view_ref=context_view_ref,
        parent_epoch_ref=parent_epoch_ref,
        created_at=created_at or _utc_now(),
    )


def reconcile_context_epoch(
    *,
    epoch_id: str,
    request: ContextCompileRequest,
    view: ContextView,
    baseline_ref: str,
    source_snapshot_ref: str,
    previous_epoch: ContextEpoch | None = None,
    provider_cache_profile: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> ContextEpoch:
    """Return a cache epoch, preserving the previous baseline when compatible."""

    request.validate()
    view.validate()
    baseline_ref = validate_ref(baseline_ref, "context_epoch.baseline_ref")
    source_snapshot_ref = validate_ref(source_snapshot_ref, "context_epoch.source_snapshot_ref")
    profile = request.provider_cache_profile if provider_cache_profile is None else provider_cache_profile
    stable_baseline_hash = stable_json_hash(
        [segment.to_dict() for segment in sorted(view.stable_prefix, key=_segment_sort_key)]
    )
    if (
        previous_epoch is not None
        and previous_epoch.role == request.role
        and previous_epoch.contract_hash == request.contract_hash
        and previous_epoch.permission_manifest_ref == request.permission_manifest_ref
        and previous_epoch.baseline_hash == stable_baseline_hash
    ):
        return previous_epoch
    return build_context_epoch(
        epoch_id=epoch_id,
        role=request.role,
        contract_hash=request.contract_hash,
        permission_manifest_ref=request.permission_manifest_ref,
        baseline_ref=baseline_ref,
        baseline_hash=stable_baseline_hash,
        source_snapshot_ref=source_snapshot_ref,
        baseline_seq=(previous_epoch.baseline_seq + 1) if previous_epoch is not None else 0,
        provider_cache_profile=profile,
        context_view_ref=baseline_ref,
        parent_epoch_ref=None,
        created_at=created_at,
    )


def build_context_cache_layout(
    *,
    layout_id: str,
    view_ref: str,
    view: ContextView,
    provider_cache_profile: Mapping[str, Any] | None = None,
    rendered_prefix_hash: str | None = None,
) -> ContextCacheLayout:
    """Build provider-neutral cache layout diagnostics from a ContextView."""

    view.validate()
    stable = [segment.to_dict() for segment in sorted(view.stable_prefix, key=_segment_sort_key)]
    semi = [segment.to_dict() for segment in sorted(view.semi_stable_context, key=_segment_sort_key)]
    volatile = [segment.to_dict() for segment in sorted(view.volatile_tail, key=_segment_sort_key)]
    omitted = [segment.to_dict() for segment in sorted(view.omitted_segments, key=_segment_sort_key)]
    prefix_hash = rendered_prefix_hash or stable_json_hash({"stable_prefix": stable, "semi_stable_context": semi})
    invalidation_refs = _unique_ordered_refs(
        [
            view.contract_ref,
            view.permission_manifest_ref,
            *[ref for segment in view.stable_prefix for ref in segment.source_refs],
        ]
    )
    return ContextCacheLayout(
        layout_id=layout_id,
        view_ref=view_ref,
        context_hash=view.context_hash,
        stable_strata_hash=stable_json_hash(stable),
        semi_stable_strata_hash=stable_json_hash(semi),
        volatile_strata_hash=stable_json_hash(volatile),
        omitted_strata_hash=stable_json_hash(omitted),
        rendered_prefix_hash=prefix_hash,
        stable_token_estimate=sum(segment.token_estimate for segment in view.stable_prefix),
        semi_stable_token_estimate=sum(segment.token_estimate for segment in view.semi_stable_context),
        volatile_token_estimate=sum(segment.token_estimate for segment in view.volatile_tail),
        omitted_token_estimate=sum(segment.token_estimate for segment in view.omitted_segments),
        epoch_invalidation_refs=invalidation_refs,
        provider_cache_profile={} if provider_cache_profile is None else provider_cache_profile,
    )


def _context_view_from_request(
    *,
    request: ContextCompileRequest,
    allowed_sources: list[ContextSource],
    denied_source_refs: list[str],
    diagnostics_ref: str,
) -> ContextView:
    stable: list[ContextSegment] = []
    semi_stable: list[ContextSegment] = []
    volatile: list[ContextSegment] = []
    omitted: list[ContextSegment] = []
    for index, source in enumerate(sorted(allowed_sources, key=_source_sort_key)):
        segment = _segment_from_source(source, role=request.role, index=index)
        if source.inline_policy is ContextInlinePolicy.OMITTED:
            omitted.append(segment)
        elif source.cache_policy is ContextCachePolicy.STABLE:
            stable.append(segment)
        elif source.cache_policy is ContextCachePolicy.SEMI_STABLE:
            semi_stable.append(segment)
        else:
            volatile.append(segment)
    return ContextView(
        view_id=request.request_id,
        role=request.role,
        contract_ref=request.contract_ref,
        contract_hash=request.contract_hash,
        permission_manifest_ref=request.permission_manifest_ref,
        stable_prefix=stable,
        semi_stable_context=semi_stable,
        volatile_tail=volatile,
        omitted_segments=omitted,
        token_budget=request.token_budget,
        diagnostics_ref=diagnostics_ref,
    )


def _segment_from_source(source: ContextSource, *, role: str, index: int) -> ContextSegment:
    body_ref = source.projection_ref
    if body_ref is None and source.inline_policy is ContextInlinePolicy.INLINE and source.source_refs:
        body_ref = source.source_refs[0]
    return ContextSegment(
        segment_id=f"src_{index:03d}_{_safe_segment_suffix(source.source_key)}",
        kind=_segment_kind_from_source_kind(source.kind),
        source_refs=list(source.source_refs),
        source_hashes=dict(source.source_hashes),
        cache_policy=source.cache_policy,
        inline_policy=source.inline_policy,
        token_estimate=source.token_estimate,
        priority=source.priority,
        role_scope=[role],
        body_ref=body_ref,
        metadata={
            "source_key": source.source_key,
            "source_kind": source.kind.value,
            "permission_manifest_ref": source.permission_manifest_ref or "",
            **dict(source.metadata),
        },
    )


def _segment_kind_from_source_kind(kind: ContextSourceKind) -> ContextSegmentKind:
    if kind is ContextSourceKind.AUTHORITY:
        return ContextSegmentKind.AUTHORITY
    if kind is ContextSourceKind.INSTRUCTION:
        return ContextSegmentKind.INSTRUCTION
    if kind is ContextSourceKind.TOOL_OBSERVATION:
        return ContextSegmentKind.TOOL_OBSERVATION
    if kind is ContextSourceKind.SUMMARY:
        return ContextSegmentKind.SEMANTIC_SUMMARY
    if kind is ContextSourceKind.RUNTIME_DIAGNOSTIC:
        return ContextSegmentKind.RUNTIME_DIAGNOSTIC
    if kind is ContextSourceKind.USER_EVENT:
        return ContextSegmentKind.ARTIFACT_REF
    if kind is ContextSourceKind.WORKING_SET:
        return ContextSegmentKind.ARTIFACT_PREVIEW
    return ContextSegmentKind.ARTIFACT_REF


def _compile_action_from_filter_and_pressure(
    filter_result: ContextSourceFilterResult,
    pressure_action: ContextPressureAction,
) -> ContextCompileAction:
    if filter_result.has_denied_required_source:
        return ContextCompileAction.BLOCKED_BY_DENIED_REQUIRED_SOURCE
    if filter_result.has_unavailable_required_source:
        return ContextCompileAction.BLOCKED_BY_UNAVAILABLE_AUTHORITY
    if pressure_action is ContextPressureAction.CHECKPOINT_BEFORE_NEXT_TURN:
        return ContextCompileAction.CHECKPOINT_BEFORE_NEXT_TURN
    if pressure_action is ContextPressureAction.PREPARE_CHECKPOINT:
        return ContextCompileAction.PREPARE_CHECKPOINT
    return ContextCompileAction.CONTINUE


def _admitted_update_refs(sources: list[ContextSource]) -> list[str]:
    return _unique_ordered_refs(
        [
            ref
            for source in sources
            if source.cache_policy in {ContextCachePolicy.SEMI_STABLE, ContextCachePolicy.VOLATILE, ContextCachePolicy.NO_CACHE}
            for ref in _refs_for_source_permission(source)
        ]
    )


def _omitted_refs(sources: list[ContextSource], denied_source_refs: list[str]) -> list[str]:
    return _unique_ordered_refs(
        [
            *[
                ref
                for source in sources
                if source.inline_policy is ContextInlinePolicy.OMITTED
                for ref in _refs_for_source_permission(source)
            ],
        ]
    )


def _demoted_refs(sources: list[ContextSource]) -> list[str]:
    return _unique_ordered_refs(
        [
            ref
            for source in sources
            if source.inline_policy in {ContextInlinePolicy.REF_ONLY, ContextInlinePolicy.OMITTED}
            for ref in _refs_for_source_permission(source)
        ]
    )


def _source_sort_key(source: ContextSource) -> tuple[int, str]:
    return (-int(source.priority), source.source_key)


def _safe_segment_suffix(value: str) -> str:
    suffix = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    suffix = suffix.strip("_") or "source"
    return suffix[:80]


def build_thrash_diagnostics(
    *,
    diagnostics_id: str,
    phase_label: str,
    observations: list[ContextReadObservation],
    repeat_threshold: int = 2,
    expected_reread_observation_ids: list[str] | None = None,
) -> ContextThrashDiagnostics:
    """Detect repeated read identities without exposing raw query text."""

    expected = set(expected_reread_observation_ids or [])
    repeated = [
        observation.observation_id
        for observation in observations
        if observation.count >= repeat_threshold and observation.observation_id not in expected
    ]
    action = ContextPressureAction.PREPARE_CHECKPOINT if repeated else ContextPressureAction.CONTINUE
    return ContextThrashDiagnostics(
        diagnostics_id=diagnostics_id,
        phase_label=phase_label,
        observations=observations,
        repeated_observation_ids=repeated,
        expected_reread_observation_ids=list(expected),
        recommended_action=action,
    )


def _refs_for_source_permission(source: ContextSource) -> list[str]:
    refs = list(source.source_refs)
    if source.projection_ref:
        refs.append(source.projection_ref)
    return _unique_ordered_refs(refs)


def _segment_sort_key(segment: Any) -> tuple[int, str]:
    return (-int(segment.priority), str(segment.segment_id))


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(payload, field_name), field_name))


def _metadata(value: Any, field_name: str) -> dict[str, Any]:
    return dict(ensure_json_value(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name))


def _normalized_query_metadata(value: Any, field_name: str) -> dict[str, Any]:
    data = _metadata(value, field_name)
    forbidden = {"query", "raw_query", "user_text", "text", "provider_payload", "tool_body"}
    unknown = sorted(set(key.lower() for key in data) & forbidden)
    if unknown:
        raise ContractValidationError(f"{field_name} must not contain raw query fields: {unknown}")
    return data


def _list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    return list(value)


def _unique_strings(value: Any, field_name: str) -> list[str]:
    items = require_str_list(value, field_name)
    if len(items) != len(set(items)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")
    return items


def _unique_refs(value: Any, field_name: str) -> list[str]:
    refs = [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")
    return refs


def _unique_ordered(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _unique_ordered_refs(values: list[str]) -> list[str]:
    return _unique_ordered([validate_ref(value, "context_engine.ref") for value in values])


def _hash_mapping(value: Any, field_name: str) -> dict[str, str]:
    data = require_mapping(value, field_name)
    return {validate_ref(key, f"{field_name}.key"): _hash(item, f"{field_name}.{key}") for key, item in data.items()}


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
    allowed = {"offset", "limit", "line_start", "line_end"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unknown fields: {unknown}")
    return {key: require_int_at_least(item, f"{field_name}.{key}", 0) for key, item in data.items()}


def _safe_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a single safe id segment")
    validate_ref(text, field_name)
    return text


def _optional_safe_label(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return ""
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text:
        raise ContractValidationError(f"{field_name} must not contain path separators")
    ensure_json_value(text, field_name)
    return text


def _require_schema(value: str, expected: str, field_name: str) -> None:
    if require_non_empty_str(value, field_name) != expected:
        raise ContractValidationError(f"{field_name} must be {expected}")


def _reject_unknown_fields(data: Mapping[str, Any], allowed_fields: set[str], field_name: str) -> None:
    unknown = sorted(set(data) - allowed_fields)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unknown fields: {unknown}")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
