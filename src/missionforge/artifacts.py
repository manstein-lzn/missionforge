"""Ref-addressed artifact records and minimal versioned storage."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_dumps,
    validate_ref,
)


class ArtifactMaterializationState(StrEnum):
    """Storage/materialization state for a committed artifact version."""

    VOLATILE = "volatile"
    DURABLE = "durable"
    MATERIALIZED = "materialized"
    DIRTY = "dirty"


@dataclass(frozen=True)
class ArtifactVersionRef:
    """A stable logical artifact ref pinned to one immutable version."""

    ref: str
    version: int

    def __post_init__(self) -> None:
        validate_ref(self.ref, "artifact_version_ref.ref")
        require_int_at_least(self.version, "artifact_version_ref.version", 1)

    @property
    def value(self) -> str:
        return f"{self.ref}@v{self.version}"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactVersionRef":
        data = require_mapping(payload, "artifact_version_ref")
        version_ref = cls(
            ref=validate_ref(data.get("ref"), "artifact_version_ref.ref"),
            version=require_int_at_least(data.get("version"), "artifact_version_ref.version", 1),
        )
        if (
            "value" in data
            and require_non_empty_str(data["value"], "artifact_version_ref.value") != version_ref.value
        ):
            raise ContractValidationError("artifact_version_ref.value does not match ref/version")
        return version_ref

    @classmethod
    def from_value(cls, value: str) -> "ArtifactVersionRef":
        text = require_non_empty_str(value, "artifact_version_ref.value")
        ref, separator, version_text = text.rpartition("@v")
        if not separator or not version_text.isdecimal():
            raise ContractValidationError("artifact_version_ref.value must end with @vN")
        return cls(ref=validate_ref(ref, "artifact_version_ref.ref"), version=int(version_text))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": validate_ref(self.ref, "artifact_version_ref.ref"),
            "version": require_int_at_least(self.version, "artifact_version_ref.version", 1),
            "value": self.value,
        }


@dataclass(frozen=True)
class ArtifactRecord:
    """Authoritative metadata for one committed logical ref version."""

    ref: str
    version: int
    content_hash: str
    size_bytes: int
    media_type: str = "application/octet-stream"
    materialization_state: ArtifactMaterializationState = ArtifactMaterializationState.DURABLE
    body_ref: str = ""
    source_refs: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_refs",
            _freeze_source_refs(self.source_refs, "artifact_record.source_refs"),
        )
        object.__setattr__(
            self,
            "metadata",
            _freeze_metadata(self.metadata, "artifact_record.metadata"),
        )

    @classmethod
    def create(
        cls,
        *,
        ref: str,
        version: int,
        body: bytes,
        body_ref: str,
        media_type: str = "application/octet-stream",
        materialization_state: ArtifactMaterializationState | str = ArtifactMaterializationState.DURABLE,
        source_refs: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: str | None = None,
    ) -> "ArtifactRecord":
        if not isinstance(body, bytes):
            raise ContractValidationError("artifact_record.body must be bytes")
        record = cls(
            ref=validate_ref(ref, "artifact_record.ref"),
            version=require_int_at_least(version, "artifact_record.version", 1),
            content_hash=_hash_bytes(body),
            size_bytes=len(body),
            media_type=require_non_empty_str(media_type, "artifact_record.media_type"),
            materialization_state=require_enum(
                materialization_state,
                ArtifactMaterializationState,
                "artifact_record.materialization_state",
            ),
            body_ref=validate_ref(body_ref, "artifact_record.body_ref"),
            source_refs=require_str_list(
                [] if source_refs is None else source_refs,
                "artifact_record.source_refs",
            ),
            metadata=_freeze_metadata({} if metadata is None else metadata, "artifact_record.metadata"),
            created_at=created_at or _utc_now(),
        )
        record.validate()
        return record

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactRecord":
        data = require_mapping(payload, "artifact_record")
        record = cls(
            ref=validate_ref(data.get("ref"), "artifact_record.ref"),
            version=require_int_at_least(data.get("version"), "artifact_record.version", 1),
            content_hash=require_non_empty_str(data.get("content_hash"), "artifact_record.content_hash"),
            size_bytes=require_int_at_least(data.get("size_bytes"), "artifact_record.size_bytes", 0),
            media_type=require_non_empty_str(
                data.get("media_type", "application/octet-stream"),
                "artifact_record.media_type",
            ),
            materialization_state=require_enum(
                data.get("materialization_state", ArtifactMaterializationState.DURABLE.value),
                ArtifactMaterializationState,
                "artifact_record.materialization_state",
            ),
            body_ref=validate_ref(data.get("body_ref"), "artifact_record.body_ref"),
            source_refs=_freeze_source_refs(data.get("source_refs", []), "artifact_record.source_refs"),
            metadata=_freeze_metadata(data.get("metadata", {}), "artifact_record.metadata"),
            created_at=require_non_empty_str(data.get("created_at"), "artifact_record.created_at"),
        )
        record.validate()
        version_ref = ArtifactVersionRef.from_dict(require_mapping(data.get("version_ref"), "artifact_record.version_ref"))
        if version_ref != record.version_ref:
            raise ContractValidationError("artifact_record.version_ref does not match ref/version")
        return record

    @property
    def version_ref(self) -> ArtifactVersionRef:
        return ArtifactVersionRef(ref=self.ref, version=self.version)

    def validate(self) -> None:
        validate_ref(self.ref, "artifact_record.ref")
        require_int_at_least(self.version, "artifact_record.version", 1)
        _validate_sha256(self.content_hash, "artifact_record.content_hash")
        require_int_at_least(self.size_bytes, "artifact_record.size_bytes", 0)
        require_non_empty_str(self.media_type, "artifact_record.media_type")
        require_enum(self.materialization_state, ArtifactMaterializationState, "artifact_record.materialization_state")
        validate_ref(self.body_ref, "artifact_record.body_ref")
        _freeze_source_refs(self.source_refs, "artifact_record.source_refs")
        assert_refs_only_payload(_thaw_json_value(self.metadata), "artifact_record.metadata")
        require_non_empty_str(self.created_at, "artifact_record.created_at")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "ref": self.ref,
            "version": self.version,
            "version_ref": self.version_ref.to_dict(),
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "materialization_state": self.materialization_state.value,
            "body_ref": self.body_ref,
            "source_refs": list(self.source_refs),
            "metadata": ensure_json_value(_thaw_json_value(self.metadata), "artifact_record.metadata"),
            "created_at": self.created_at,
        }


class ArtifactStore(Protocol):
    """Minimal protocol for committed artifact versions."""

    def put_bytes(
        self,
        ref: str,
        body: bytes,
        *,
        media_type: str = "application/octet-stream",
        source_refs: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ArtifactRecord:
        """Commit a new immutable version for a logical artifact ref."""

    def get(self, ref: str, *, version: int | None = None) -> ArtifactRecord:
        """Return a record for a logical ref, defaulting to latest."""

    def read_bytes(self, ref: str, *, version: int | None = None) -> bytes:
        """Return committed bytes for a logical ref/version."""


class InMemoryArtifactStore:
    """Small non-authoritative in-memory implementation for tests and transient state."""

    def __init__(self) -> None:
        self._records: list[ArtifactRecord] = []
        self._by_ref_version: dict[tuple[str, int], ArtifactRecord] = {}
        self._bodies: dict[tuple[str, int], bytes] = {}

    def put_bytes(
        self,
        ref: str,
        body: bytes,
        *,
        media_type: str = "application/octet-stream",
        source_refs: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ArtifactRecord:
        safe_ref = validate_ref(ref, "artifact_store.ref")
        if not isinstance(body, bytes):
            raise ContractValidationError("artifact_store.body must be bytes")
        version = self._next_version(safe_ref)
        record = ArtifactRecord.create(
            ref=safe_ref,
            version=version,
            body=body,
            body_ref=f"memory/artifacts/{hashlib.sha256(safe_ref.encode('utf-8')).hexdigest()}/v{version:06d}",
            media_type=media_type,
            materialization_state=ArtifactMaterializationState.VOLATILE,
            source_refs=source_refs,
            metadata=metadata,
        )
        self._append_record(record, body)
        return record

    def put_text(
        self,
        ref: str,
        text: str,
        *,
        media_type: str = "text/plain",
        source_refs: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ArtifactRecord:
        if not isinstance(text, str):
            raise ContractValidationError("artifact_store.text must be a string")
        return self.put_bytes(
            ref,
            text.encode("utf-8"),
            media_type=media_type,
            source_refs=source_refs,
            metadata=metadata,
        )

    def get(self, ref: str, *, version: int | None = None) -> ArtifactRecord:
        safe_ref = validate_ref(ref, "artifact_store.ref")
        target_version = version if version is not None else self.latest(safe_ref).version
        key = (safe_ref, require_int_at_least(target_version, "artifact_store.version", 1))
        try:
            return self._by_ref_version[key]
        except KeyError as exc:
            raise ContractValidationError(f"unknown artifact version: {safe_ref}@v{key[1]}") from exc

    def latest(self, ref: str) -> ArtifactRecord:
        safe_ref = validate_ref(ref, "artifact_store.ref")
        candidates = [record for record in self._records if record.ref == safe_ref]
        if not candidates:
            raise ContractValidationError(f"unknown artifact ref: {safe_ref}")
        return max(candidates, key=lambda record: record.version)

    def read_bytes(self, ref: str, *, version: int | None = None) -> bytes:
        record = self.get(ref, version=version)
        try:
            body = self._bodies[(record.ref, record.version)]
        except KeyError as exc:
            raise ContractValidationError(f"unknown artifact body: {record.version_ref.value}") from exc
        if _hash_bytes(body) != record.content_hash:
            raise ContractValidationError(f"artifact body hash mismatch: {record.version_ref.value}")
        if len(body) != record.size_bytes:
            raise ContractValidationError(f"artifact body size mismatch: {record.version_ref.value}")
        return body

    def records(self, ref: str | None = None) -> list[ArtifactRecord]:
        if ref is None:
            return list(self._records)
        safe_ref = validate_ref(ref, "artifact_store.ref")
        return [record for record in self._records if record.ref == safe_ref]

    def _append_record(self, record: ArtifactRecord, body: bytes) -> None:
        record.validate()
        key = (record.ref, record.version)
        if key in self._by_ref_version:
            raise ContractValidationError(f"duplicate artifact version: {record.version_ref.value}")
        self._records.append(record)
        self._by_ref_version[key] = record
        self._bodies[key] = bytes(body)

    def _next_version(self, ref: str) -> int:
        versions = [record.version for record in self._records if record.ref == ref]
        if not versions:
            return 1
        return max(versions) + 1


class FileArtifactStore:
    """Small filesystem-backed implementation of ArtifactStore."""

    INDEX_REF = ".missionforge/artifacts/index.json"
    BODY_ROOT_REF = ".missionforge/artifacts/bodies"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._records: list[ArtifactRecord] = []
        self._by_ref_version: dict[tuple[str, int], ArtifactRecord] = {}
        self._load_existing()

    def put_bytes(
        self,
        ref: str,
        body: bytes,
        *,
        media_type: str = "application/octet-stream",
        source_refs: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ArtifactRecord:
        safe_ref = validate_ref(ref, "artifact_store.ref")
        if not isinstance(body, bytes):
            raise ContractValidationError("artifact_store.body must be bytes")
        version = self._next_version(safe_ref)
        body_ref = self._body_ref(safe_ref, version)
        body_path = self._path_for_ref(body_ref)
        record = ArtifactRecord.create(
            ref=safe_ref,
            version=version,
            body=body,
            body_ref=body_ref,
            media_type=media_type,
            source_refs=source_refs,
            metadata=metadata,
        )
        if body_path.exists():
            raise ContractValidationError(f"artifact body already exists for {safe_ref}@v{version}")

        body_written = False
        record_appended = False
        try:
            body_path.parent.mkdir(parents=True, exist_ok=True)
            body_path.write_bytes(body)
            body_written = True
            self._append_record(record)
            record_appended = True
            self._write_index()
        except Exception:
            if record_appended:
                self._remove_record(record)
            if body_written:
                body_path.unlink(missing_ok=True)
            raise
        return record

    def put_text(
        self,
        ref: str,
        text: str,
        *,
        media_type: str = "text/plain",
        source_refs: list[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ArtifactRecord:
        if not isinstance(text, str):
            raise ContractValidationError("artifact_store.text must be a string")
        return self.put_bytes(
            ref,
            text.encode("utf-8"),
            media_type=media_type,
            source_refs=source_refs,
            metadata=metadata,
        )

    def get(self, ref: str, *, version: int | None = None) -> ArtifactRecord:
        safe_ref = validate_ref(ref, "artifact_store.ref")
        target_version = version if version is not None else self.latest(safe_ref).version
        key = (safe_ref, require_int_at_least(target_version, "artifact_store.version", 1))
        try:
            return self._by_ref_version[key]
        except KeyError as exc:
            raise ContractValidationError(f"unknown artifact version: {safe_ref}@v{key[1]}") from exc

    def latest(self, ref: str) -> ArtifactRecord:
        safe_ref = validate_ref(ref, "artifact_store.ref")
        candidates = [record for record in self._records if record.ref == safe_ref]
        if not candidates:
            raise ContractValidationError(f"unknown artifact ref: {safe_ref}")
        return max(candidates, key=lambda record: record.version)

    def read_bytes(self, ref: str, *, version: int | None = None) -> bytes:
        record = self.get(ref, version=version)
        body = self._path_for_ref(record.body_ref).read_bytes()
        if _hash_bytes(body) != record.content_hash:
            raise ContractValidationError(f"artifact body hash mismatch: {record.version_ref.value}")
        if len(body) != record.size_bytes:
            raise ContractValidationError(f"artifact body size mismatch: {record.version_ref.value}")
        return body

    def records(self, ref: str | None = None) -> list[ArtifactRecord]:
        if ref is None:
            return list(self._records)
        safe_ref = validate_ref(ref, "artifact_store.ref")
        return [record for record in self._records if record.ref == safe_ref]

    def materialized_path(self, record: ArtifactRecord) -> Path:
        record.validate()
        return self._path_for_ref(record.body_ref)

    def _append_record(self, record: ArtifactRecord) -> None:
        record.validate()
        key = (record.ref, record.version)
        if key in self._by_ref_version:
            raise ContractValidationError(f"duplicate artifact version: {record.version_ref.value}")
        self._records.append(record)
        self._by_ref_version[key] = record

    def _remove_record(self, record: ArtifactRecord) -> None:
        key = (record.ref, record.version)
        self._by_ref_version.pop(key, None)
        self._records = [item for item in self._records if item.version_ref != record.version_ref]

    def _load_existing(self) -> None:
        index_path = self._path_for_ref(self.INDEX_REF)
        if not index_path.exists():
            return
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        data = require_mapping(payload, "artifact_store.index")
        if data.get("schema_version") != 1:
            raise ContractValidationError("artifact_store.index schema_version must be 1")
        records = data.get("records")
        if not isinstance(records, list):
            raise ContractValidationError("artifact_store.index.records must be a list")
        for item in records:
            record = ArtifactRecord.from_dict(require_mapping(item, "artifact_store.index.records[]"))
            body = self._path_for_ref(record.body_ref).read_bytes()
            if _hash_bytes(body) != record.content_hash:
                raise ContractValidationError(f"artifact body hash mismatch: {record.version_ref.value}")
            if len(body) != record.size_bytes:
                raise ContractValidationError(f"artifact body size mismatch: {record.version_ref.value}")
            self._append_record(record)

    def _write_index(self) -> None:
        index_path = self._path_for_ref(self.INDEX_REF)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "records": [record.to_dict() for record in self._records],
        }
        index_path.write_text(stable_json_dumps(payload) + "\n", encoding="utf-8")

    def _next_version(self, ref: str) -> int:
        versions = [record.version for record in self._records if record.ref == ref]
        if not versions:
            return 1
        return max(versions) + 1

    def _body_ref(self, ref: str, version: int) -> str:
        ref_hash = hashlib.sha256(ref.encode("utf-8")).hexdigest()
        return f"{self.BODY_ROOT_REF}/{ref_hash}/v{version:06d}/body"

    def _path_for_ref(self, ref: str) -> Path:
        safe_ref = validate_ref(ref, "artifact_store.path_ref")
        path = self._root / safe_ref
        root = self._root.resolve()
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            raise ContractValidationError("artifact_store path escaped root")
        return path


def _hash_bytes(body: bytes) -> str:
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


def _freeze_source_refs(value: Any, field_name: str) -> tuple[str, ...]:
    raw_refs = list(value) if isinstance(value, tuple) else value
    return tuple(
        validate_ref(item, f"{field_name}[]")
        for item in require_str_list(raw_refs, field_name)
    )


def _freeze_metadata(value: Any, field_name: str) -> Mapping[str, Any]:
    metadata = require_mapping(_thaw_json_value(value), field_name)
    normalized = assert_refs_only_payload(metadata, field_name)
    frozen = _freeze_json_value(normalized)
    if not isinstance(frozen, MappingABC):
        raise ContractValidationError(f"{field_name} must be a mapping")
    return frozen


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return MappingProxyType({
            key: _freeze_json_value(item)
            for key, item in value.items()
        })
    if isinstance(value, list):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _thaw_json_value(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return {
            key: _thaw_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_thaw_json_value(item) for item in value]
    if isinstance(value, list):
        return [_thaw_json_value(item) for item in value]
    return value


def _validate_sha256(value: str, field_name: str) -> None:
    digest = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not digest.startswith(prefix) or len(digest) != len(prefix) + 64:
        raise ContractValidationError(f"{field_name} must be a sha256 digest")
    hex_part = digest[len(prefix):]
    if any(char not in "0123456789abcdef" for char in hex_part):
        raise ContractValidationError(f"{field_name} must be a lowercase sha256 digest")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
