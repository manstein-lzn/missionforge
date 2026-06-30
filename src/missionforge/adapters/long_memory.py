"""Optional long-memory provider adapters.

MissionForge core accepts only provider-neutral LongMemoryPacket artifacts.
This module lives in the adapter package so provider SDK details, including
Mem0, do not enter runtime core contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)


LONG_MEMORY_PACKET_SCHEMA_VERSION = "missionforge.long_memory_packet.v1"
LONG_MEMORY_PROVIDER_ID = "missionforge.long_memory_provider.v1"
LONG_MEMORY_CONFIDENCE = {"low", "medium", "high"}
LONG_MEMORY_STATUS = {"active", "superseded", "conflicting"}
PIWORKER_ROLE_VALUES = {
    "frontdesk_author_piworker",
    "executor_piworker",
    "judge_piworker",
    "context_reducer_piworker",
    "repair_piworker",
    "revision_drafter_piworker",
}


@dataclass(frozen=True)
class LongMemoryScope:
    mission_id: str
    role: str
    project_id: str | None = None
    user_id: str | None = None

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "long_memory_scope.mission_id")
        role = require_non_empty_str(self.role, "long_memory_scope.role")
        if role not in PIWORKER_ROLE_VALUES:
            raise ContractValidationError("long_memory_scope.role is not a supported PiWorker role")
        if self.project_id is not None:
            require_non_empty_str(self.project_id, "long_memory_scope.project_id")
        if self.user_id is not None:
            require_non_empty_str(self.user_id, "long_memory_scope.user_id")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LongMemoryScope":
        data = require_mapping(payload, "long_memory_scope")
        scope = cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "long_memory_scope.mission_id"),
            role=require_non_empty_str(data.get("role"), "long_memory_scope.role"),
            project_id=_optional_non_empty_str(data.get("project_id"), "long_memory_scope.project_id"),
            user_id=_optional_non_empty_str(data.get("user_id"), "long_memory_scope.user_id"),
        )
        scope.validate()
        return scope

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload: dict[str, Any] = {
            "mission_id": self.mission_id,
            "role": self.role,
        }
        if self.project_id is not None:
            payload["project_id"] = self.project_id
        if self.user_id is not None:
            payload["user_id"] = self.user_id
        return payload


@dataclass(frozen=True)
class LongMemoryRecord:
    memory_id: str
    statement: str
    why_relevant: str
    source_refs: tuple[str, ...]
    confidence: str = "medium"
    status: str = "active"
    created_at: str | None = None
    supersedes: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        require_non_empty_str(self.memory_id, "long_memory_record.memory_id")
        _reject_authority_override(
            require_non_empty_str(self.statement, "long_memory_record.statement"),
            "long_memory_record.statement",
        )
        require_non_empty_str(self.why_relevant, "long_memory_record.why_relevant")
        if self.confidence not in LONG_MEMORY_CONFIDENCE:
            raise ContractValidationError("long_memory_record.confidence is invalid")
        if self.status not in LONG_MEMORY_STATUS:
            raise ContractValidationError("long_memory_record.status is invalid")
        if not self.source_refs:
            raise ContractValidationError("long_memory_record.source_refs must not be empty")
        for ref in self.source_refs:
            validate_ref(ref, "long_memory_record.source_refs[]")
        if self.created_at is not None:
            require_non_empty_str(self.created_at, "long_memory_record.created_at")
        for ref in self.supersedes:
            require_non_empty_str(ref, "long_memory_record.supersedes[]")
        for ref in self.conflicts_with:
            require_non_empty_str(ref, "long_memory_record.conflicts_with[]")
        assert_refs_only_payload(dict(self.metadata), "long_memory_record.metadata")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LongMemoryRecord":
        data = require_mapping(payload, "long_memory_record")
        record = cls(
            memory_id=require_non_empty_str(data.get("memory_id"), "long_memory_record.memory_id"),
            statement=require_non_empty_str(data.get("statement"), "long_memory_record.statement"),
            why_relevant=require_non_empty_str(data.get("why_relevant"), "long_memory_record.why_relevant"),
            source_refs=tuple(require_str_list(data.get("source_refs"), "long_memory_record.source_refs")),
            confidence=require_non_empty_str(data.get("confidence", "medium"), "long_memory_record.confidence"),
            status=require_non_empty_str(data.get("status", "active"), "long_memory_record.status"),
            created_at=_optional_non_empty_str(data.get("created_at"), "long_memory_record.created_at"),
            supersedes=tuple(require_str_list(data.get("supersedes", []), "long_memory_record.supersedes")),
            conflicts_with=tuple(require_str_list(data.get("conflicts_with", []), "long_memory_record.conflicts_with")),
            metadata=require_mapping(data.get("metadata", {}), "long_memory_record.metadata"),
        )
        record.validate()
        return record

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload: dict[str, Any] = {
            "memory_id": self.memory_id,
            "statement": self.statement,
            "why_relevant": self.why_relevant,
            "source_refs": list(self.source_refs),
            "confidence": self.confidence,
            "status": self.status,
        }
        if self.created_at is not None:
            payload["created_at"] = self.created_at
        if self.supersedes:
            payload["supersedes"] = list(self.supersedes)
        if self.conflicts_with:
            payload["conflicts_with"] = list(self.conflicts_with)
        if self.metadata:
            payload["metadata"] = ensure_json_value(dict(self.metadata), "long_memory_record.metadata")
        return payload


@dataclass(frozen=True)
class LongMemoryCatalogHit:
    segment_ref: str
    turn_range: tuple[int, int] | None = None
    topics: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    hash: str | None = None

    def validate(self) -> None:
        validate_ref(self.segment_ref, "long_memory_catalog_hit.segment_ref")
        if self.turn_range is not None:
            start, end = self.turn_range
            require_int_at_least(start, "long_memory_catalog_hit.turn_range[0]", 0)
            require_int_at_least(end, "long_memory_catalog_hit.turn_range[1]", 0)
            if end < start:
                raise ContractValidationError("long_memory_catalog_hit.turn_range end must be >= start")
        require_str_list(list(self.topics), "long_memory_catalog_hit.topics")
        for ref in self.artifact_refs:
            validate_ref(ref, "long_memory_catalog_hit.artifact_refs[]")
        if self.hash is not None and not _is_sha256(self.hash):
            raise ContractValidationError("long_memory_catalog_hit.hash must be a sha256 hash")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LongMemoryCatalogHit":
        data = require_mapping(payload, "long_memory_catalog_hit")
        turn_range = data.get("turn_range")
        if turn_range is not None:
            if not isinstance(turn_range, list) or len(turn_range) != 2:
                raise ContractValidationError("long_memory_catalog_hit.turn_range must contain two integers")
            parsed_range = (
                require_int_at_least(turn_range[0], "long_memory_catalog_hit.turn_range[0]", 0),
                require_int_at_least(turn_range[1], "long_memory_catalog_hit.turn_range[1]", 0),
            )
        else:
            parsed_range = None
        hit = cls(
            segment_ref=validate_ref(data.get("segment_ref"), "long_memory_catalog_hit.segment_ref"),
            turn_range=parsed_range,
            topics=tuple(require_str_list(data.get("topics", []), "long_memory_catalog_hit.topics")),
            artifact_refs=tuple(require_str_list(data.get("artifact_refs", []), "long_memory_catalog_hit.artifact_refs")),
            hash=_optional_non_empty_str(data.get("hash"), "long_memory_catalog_hit.hash"),
        )
        hit.validate()
        return hit

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload: dict[str, Any] = {"segment_ref": self.segment_ref}
        if self.turn_range is not None:
            payload["turn_range"] = [self.turn_range[0], self.turn_range[1]]
        if self.topics:
            payload["topics"] = list(self.topics)
        if self.artifact_refs:
            payload["artifact_refs"] = list(self.artifact_refs)
        if self.hash is not None:
            payload["hash"] = self.hash
        return payload


@dataclass(frozen=True)
class LongMemoryPacket:
    provider: str
    budget_tokens: int
    scope: LongMemoryScope
    memories: tuple[LongMemoryRecord, ...] = ()
    catalog_hits: tuple[LongMemoryCatalogHit, ...] = ()
    packet_ref: str | None = None
    advisory_only: bool = True
    schema_version: str = LONG_MEMORY_PACKET_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != LONG_MEMORY_PACKET_SCHEMA_VERSION:
            raise ContractValidationError("long_memory_packet.schema_version is unsupported")
        require_non_empty_str(self.provider, "long_memory_packet.provider")
        if self.packet_ref is not None:
            validate_ref(self.packet_ref, "long_memory_packet.packet_ref")
        if self.advisory_only is not True:
            raise ContractValidationError("long_memory_packet.advisory_only must be true")
        require_int_at_least(self.budget_tokens, "long_memory_packet.budget_tokens", 1)
        self.scope.validate()
        if not self.memories and not self.catalog_hits:
            raise ContractValidationError("long_memory_packet requires memories or catalog hits")
        for memory in self.memories:
            memory.validate()
        for hit in self.catalog_hits:
            hit.validate()
        assert_refs_only_payload(self.to_dict(validate=False), "long_memory_packet")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LongMemoryPacket":
        data = require_mapping(payload, "long_memory_packet")
        packet = cls(
            provider=require_non_empty_str(data.get("provider"), "long_memory_packet.provider"),
            budget_tokens=require_int_at_least(data.get("budget_tokens"), "long_memory_packet.budget_tokens", 1),
            scope=LongMemoryScope.from_dict(require_mapping(data.get("scope"), "long_memory_packet.scope")),
            memories=tuple(
                LongMemoryRecord.from_dict(require_mapping(item, "long_memory_packet.memories[]"))
                for item in data.get("memories", [])
            ),
            catalog_hits=tuple(
                LongMemoryCatalogHit.from_dict(require_mapping(item, "long_memory_packet.catalog_hits[]"))
                for item in data.get("catalog_hits", [])
            ),
            packet_ref=_optional_ref(data.get("packet_ref"), "long_memory_packet.packet_ref"),
            advisory_only=data.get("advisory_only", True),
            schema_version=require_non_empty_str(data.get("schema_version"), "long_memory_packet.schema_version"),
        )
        packet.validate()
        return packet

    def to_dict(self, *, validate: bool = True) -> dict[str, Any]:
        if validate:
            self.validate()
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "advisory_only": self.advisory_only,
            "budget_tokens": self.budget_tokens,
            "scope": self.scope.to_dict(),
            "memories": [memory.to_dict() for memory in self.memories],
        }
        if self.packet_ref is not None:
            payload["packet_ref"] = self.packet_ref
        if self.catalog_hits:
            payload["catalog_hits"] = [hit.to_dict() for hit in self.catalog_hits]
        return ensure_json_value(payload, "long_memory_packet")


@dataclass(frozen=True)
class LongMemoryAddRecord:
    statement: str
    scope: LongMemoryScope
    source_refs: tuple[str, ...]
    why_relevant: str
    memory_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    infer: bool = False

    def validate(self) -> None:
        require_non_empty_str(self.statement, "long_memory_add_record.statement")
        self.scope.validate()
        if not self.source_refs:
            raise ContractValidationError("long_memory_add_record.source_refs must not be empty")
        for ref in self.source_refs:
            validate_ref(ref, "long_memory_add_record.source_refs[]")
        require_non_empty_str(self.why_relevant, "long_memory_add_record.why_relevant")
        if self.memory_id is not None:
            require_non_empty_str(self.memory_id, "long_memory_add_record.memory_id")
        if not isinstance(self.infer, bool):
            raise ContractValidationError("long_memory_add_record.infer must be a boolean")
        assert_refs_only_payload(dict(self.metadata), "long_memory_add_record.metadata")


@dataclass(frozen=True)
class LongMemorySearchRequest:
    query: str
    scope: LongMemoryScope
    packet_ref: str
    budget_tokens: int = 2000
    limit: int = 8
    min_score: float = 0.0
    catalog_hits: tuple[LongMemoryCatalogHit, ...] = ()

    def validate(self) -> None:
        require_non_empty_str(self.query, "long_memory_search_request.query")
        self.scope.validate()
        validate_ref(self.packet_ref, "long_memory_search_request.packet_ref")
        require_int_at_least(self.budget_tokens, "long_memory_search_request.budget_tokens", 1)
        require_int_at_least(self.limit, "long_memory_search_request.limit", 1)
        if not isinstance(self.min_score, (int, float)) or not 0.0 <= float(self.min_score) <= 1.0:
            raise ContractValidationError("long_memory_search_request.min_score must be in [0, 1]")
        for hit in self.catalog_hits:
            hit.validate()


@dataclass(frozen=True)
class MemoryWriteResult:
    provider: str
    status: str
    memory_ids: tuple[str, ...] = ()
    provider_event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": require_non_empty_str(self.provider, "memory_write_result.provider"),
            "status": require_non_empty_str(self.status, "memory_write_result.status"),
            "memory_ids": list(self.memory_ids),
        }
        if self.provider_event_id is not None:
            payload["provider_event_id"] = require_non_empty_str(
                self.provider_event_id,
                "memory_write_result.provider_event_id",
            )
        return ensure_json_value(payload, "memory_write_result")


@dataclass(frozen=True)
class MemorySearchResult:
    provider: str
    memories: tuple[LongMemoryRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        for memory in self.memories:
            memory.validate()
        return ensure_json_value(
            {
                "provider": require_non_empty_str(self.provider, "memory_search_result.provider"),
                "memories": [memory.to_dict() for memory in self.memories],
            },
            "memory_search_result",
        )


class LongMemoryProvider(Protocol):
    provider_id: str

    def add(self, record: LongMemoryAddRecord) -> MemoryWriteResult:
        ...

    def search(self, request: LongMemorySearchRequest) -> MemorySearchResult:
        ...

    def get(self, memory_id: str, scope: LongMemoryScope) -> LongMemoryRecord:
        ...

    def build_packet(self, request: LongMemorySearchRequest) -> LongMemoryPacket:
        ...


@dataclass(frozen=True)
class Mem0LongMemoryProvider:
    """Map Mem0 client results into MissionForge LongMemoryPacket contracts."""

    client: Any
    provider_id: str = "mem0"

    @classmethod
    def from_environment(
        cls,
        *,
        api_key: str | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "Mem0LongMemoryProvider":
        current_env = dict(os.environ if environ is None else environ)
        resolved_key = api_key or current_env.get("MISSIONFORGE_MEM0_API_KEY") or current_env.get("MEM0_API_KEY")
        if not resolved_key:
            raise ContractValidationError("Mem0 long-memory provider requires MISSIONFORGE_MEM0_API_KEY or MEM0_API_KEY")
        try:
            from mem0 import MemoryClient  # type: ignore
        except ImportError as exc:
            raise ContractValidationError("Mem0 long-memory provider requires optional package mem0ai") from exc
        return cls(MemoryClient(api_key=resolved_key))

    def add(self, record: LongMemoryAddRecord) -> MemoryWriteResult:
        record.validate()
        metadata = _mem0_metadata(record.scope, record.source_refs, record.why_relevant, record.metadata)
        payload = {
            "messages": [{"role": "user", "content": record.statement}],
            **_mem0_entity_kwargs(record.scope),
            "metadata": metadata,
            "infer": record.infer,
        }
        result = self.client.add(**payload)
        result_data = _mapping_or_empty(result)
        return MemoryWriteResult(
            provider=self.provider_id,
            status=str(result_data.get("status") or result_data.get("message") or "submitted"),
            memory_ids=tuple(_extract_memory_ids(result_data)),
            provider_event_id=_optional_non_empty_str(result_data.get("event_id"), "mem0.event_id"),
        )

    def search(self, request: LongMemorySearchRequest) -> MemorySearchResult:
        request.validate()
        result = _call_mem0_search(
            self.client,
            query=request.query,
            filters=_mem0_filters(request.scope),
            limit=request.limit,
            min_score=float(request.min_score),
        )
        records = tuple(
            _mem0_result_to_record(item, default_why_relevant=f"Matched long-memory query: {request.query}")
            for item in _iter_mem0_results(result)
        )
        return MemorySearchResult(provider=self.provider_id, memories=records)

    def get(self, memory_id: str, scope: LongMemoryScope) -> LongMemoryRecord:
        safe_memory_id = require_non_empty_str(memory_id, "long_memory.memory_id")
        scope.validate()
        try:
            result = self.client.get(safe_memory_id)
        except TypeError:
            result = self.client.get(memory_id=safe_memory_id)
        return _mem0_result_to_record(result, default_why_relevant="Fetched by memory id")

    def build_packet(self, request: LongMemorySearchRequest) -> LongMemoryPacket:
        request.validate()
        search_result = self.search(request)
        packet = LongMemoryPacket(
            provider=self.provider_id,
            packet_ref=request.packet_ref,
            advisory_only=True,
            budget_tokens=request.budget_tokens,
            scope=request.scope,
            memories=search_result.memories,
            catalog_hits=request.catalog_hits,
        )
        packet.validate()
        return packet


def write_long_memory_packet(workspace_root: str | Path, packet: LongMemoryPacket, packet_ref: str | None = None) -> str:
    ref = validate_ref(packet_ref or packet.packet_ref, "long_memory_packet_ref")
    packet_to_write = packet if packet.packet_ref == ref else LongMemoryPacket(
        provider=packet.provider,
        budget_tokens=packet.budget_tokens,
        scope=packet.scope,
        memories=packet.memories,
        catalog_hits=packet.catalog_hits,
        packet_ref=ref,
        advisory_only=packet.advisory_only,
        schema_version=packet.schema_version,
    )
    payload = packet_to_write.to_dict()
    root = Path(workspace_root).resolve()
    path = (root / ref).resolve()
    if path != root and root not in path.parents:
        raise ContractValidationError("long_memory_packet_ref escapes workspace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return ref


def long_memory_packet_hash(packet: LongMemoryPacket) -> str:
    return stable_json_hash(packet.to_dict())


def _mem0_entity_kwargs(scope: LongMemoryScope) -> dict[str, str]:
    kwargs: dict[str, str] = {
        "run_id": scope.mission_id,
        "agent_id": scope.role,
    }
    if scope.project_id:
        kwargs["app_id"] = scope.project_id
    if scope.user_id:
        kwargs["user_id"] = scope.user_id
    return kwargs


def _mem0_filters(scope: LongMemoryScope) -> dict[str, str]:
    return _mem0_entity_kwargs(scope)


def _mem0_metadata(
    scope: LongMemoryScope,
    source_refs: Sequence[str],
    why_relevant: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        **dict(metadata),
        "source_refs": [validate_ref(ref, "long_memory.source_refs[]") for ref in source_refs],
        "why_relevant": why_relevant,
        "missionforge_scope": scope.to_dict(),
    }
    return assert_refs_only_payload(payload, "long_memory.mem0_metadata")


def _call_mem0_search(client: Any, *, query: str, filters: Mapping[str, str], limit: int, min_score: float) -> Any:
    attempts = (
        lambda: client.search(query, filters=dict(filters), top_k=limit, threshold=min_score),
        lambda: client.search(query=query, filters=dict(filters), top_k=limit, threshold=min_score),
        lambda: client.search(query, filters=dict(filters), limit=limit, threshold=min_score),
        lambda: client.search(query=query, filters=dict(filters), limit=limit, threshold=min_score),
        lambda: client.search(query, filters=dict(filters)),
        lambda: client.search(query=query, filters=dict(filters)),
    )
    last_error: TypeError | None = None
    for attempt in attempts:
        try:
            return attempt()
        except TypeError as exc:
            last_error = exc
    raise ContractValidationError(f"Mem0 search call is not compatible: {last_error}") from last_error


def _iter_mem0_results(result: Any) -> list[Any]:
    if isinstance(result, Mapping):
        for key in ("results", "memories", "data"):
            value = result.get(key)
            if isinstance(value, list):
                return value
        if "id" in result or "memory" in result or "text" in result:
            return [result]
        return []
    if isinstance(result, list):
        return result
    return []


def _mem0_result_to_record(item: Any, *, default_why_relevant: str) -> LongMemoryRecord:
    if not isinstance(item, Mapping):
        raise ContractValidationError("Mem0 memory result must be a mapping")
    metadata = _extract_metadata(item)
    source_refs = _extract_source_refs(metadata)
    if not source_refs:
        raise ContractValidationError("Mem0 memory result missing MissionForge source_refs")
    score = _optional_number(item.get("score"))
    record = LongMemoryRecord(
        memory_id=require_non_empty_str(
            item.get("id") or item.get("memory_id") or item.get("memoryId"),
            "mem0.memory_id",
        ),
        statement=require_non_empty_str(
            item.get("memory") or item.get("text") or item.get("content") or item.get("new_memory"),
            "mem0.memory",
        ),
        why_relevant=require_non_empty_str(
            metadata.get("why_relevant") or default_why_relevant,
            "mem0.why_relevant",
        ),
        source_refs=tuple(source_refs),
        confidence=_confidence_from_score(score, metadata.get("confidence")),
        status=_status_from_metadata(metadata.get("status")),
        created_at=_optional_non_empty_str(item.get("created_at") or item.get("createdAt"), "mem0.created_at"),
        metadata={
            key: value
            for key, value in {
                "mem0_score": score,
                "categories": metadata.get("categories"),
                "missionforge_scope": metadata.get("missionforge_scope"),
            }.items()
            if value is not None
        },
    )
    record.validate()
    return record


def _extract_metadata(item: Mapping[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata", {})
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise ContractValidationError("Mem0 memory metadata must be a mapping")
    return dict(metadata)


def _extract_source_refs(metadata: Mapping[str, Any]) -> list[str]:
    value = metadata.get("source_refs")
    if value is None and metadata.get("source_ref") is not None:
        value = [metadata.get("source_ref")]
    return [validate_ref(ref, "mem0.metadata.source_refs[]") for ref in require_str_list(value or [], "mem0.metadata.source_refs")]


def _confidence_from_score(score: float | None, explicit: Any) -> str:
    if isinstance(explicit, str) and explicit in LONG_MEMORY_CONFIDENCE:
        return explicit
    if score is None:
        return "medium"
    if score >= 0.75:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _status_from_metadata(value: Any) -> str:
    if isinstance(value, str) and value in LONG_MEMORY_STATUS:
        return value
    return "active"


def _extract_memory_ids(result: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("id", "memory_id", "memoryId"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            ids.append(value.strip())
    for item in _iter_mem0_results(result):
        if isinstance(item, Mapping):
            for key in ("id", "memory_id", "memoryId"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    ids.append(value.strip())
    return sorted(set(ids))


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_non_empty_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return require_non_empty_str(value, field_name)


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return validate_ref(value, field_name)


def _optional_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _is_sha256(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == len("sha256:") + 64 and all(
        char in "0123456789abcdef" for char in value[len("sha256:") :]
    )


def _reject_authority_override(text: str, field_name: str) -> None:
    lowered = text.lower()
    forbidden = (
        "memory overrides the frozen contract",
        "memory overrides frozen contract",
        "memory replaces the frozen contract",
        "memory replaces frozen contract",
        "memory can override the frozen contract",
        "memory can replace the frozen contract",
        "ignore the frozen contract",
        "ignore contract requirements",
    )
    if any(fragment in lowered for fragment in forbidden):
        raise ContractValidationError(f"{field_name} must not claim authority over the frozen contract")
