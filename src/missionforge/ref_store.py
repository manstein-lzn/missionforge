"""Ref-addressed runtime record stores.

This module owns runtime record transport. It intentionally does not replace
versioned ArtifactStore semantics; RefStore is for Kernel records, context
views, ledgers, and small package-managed refs.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from threading import RLock
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
    stable_json_dumps,
    stable_json_hash,
    validate_ref,
)


class RefMaterializationState(StrEnum):
    """Storage/materialization state for one runtime ref record."""

    VOLATILE = "volatile"
    DURABLE = "durable"
    MATERIALIZED = "materialized"
    DIRTY = "dirty"


@dataclass(frozen=True)
class RefRecord:
    """Refs-first metadata for one runtime store write."""

    ref: str
    content_hash: str
    size_bytes: int
    media_type: str = "application/octet-stream"
    materialization_state: RefMaterializationState = RefMaterializationState.VOLATILE
    store_id: str = "memory"
    created_at: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metadata",
            _freeze_metadata(self.metadata, "ref_record.metadata"),
        )

    @classmethod
    def create(
        cls,
        *,
        ref: str,
        body: bytes,
        media_type: str = "application/octet-stream",
        materialization_state: RefMaterializationState | str = RefMaterializationState.VOLATILE,
        store_id: str = "memory",
        metadata: Mapping[str, Any] | None = None,
        created_at: str | None = None,
    ) -> "RefRecord":
        if not isinstance(body, bytes):
            raise ContractValidationError("ref_record.body must be bytes")
        record = cls(
            ref=validate_ref(ref, "ref_record.ref"),
            content_hash=_hash_bytes(body),
            size_bytes=len(body),
            media_type=require_non_empty_str(media_type, "ref_record.media_type"),
            materialization_state=require_enum(
                materialization_state,
                RefMaterializationState,
                "ref_record.materialization_state",
            ),
            store_id=require_non_empty_str(store_id, "ref_record.store_id"),
            created_at=created_at or _utc_now(),
            metadata={} if metadata is None else metadata,
        )
        record.validate()
        return record

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RefRecord":
        data = require_mapping(payload, "ref_record")
        record = cls(
            ref=validate_ref(data.get("ref"), "ref_record.ref"),
            content_hash=require_non_empty_str(data.get("content_hash"), "ref_record.content_hash"),
            size_bytes=require_int_at_least(data.get("size_bytes"), "ref_record.size_bytes", 0),
            media_type=require_non_empty_str(
                data.get("media_type", "application/octet-stream"),
                "ref_record.media_type",
            ),
            materialization_state=require_enum(
                data.get("materialization_state", RefMaterializationState.VOLATILE.value),
                RefMaterializationState,
                "ref_record.materialization_state",
            ),
            store_id=require_non_empty_str(data.get("store_id", "memory"), "ref_record.store_id"),
            created_at=require_non_empty_str(data.get("created_at"), "ref_record.created_at"),
            metadata=data.get("metadata", {}),
        )
        record.validate()
        return record

    def validate(self) -> None:
        validate_ref(self.ref, "ref_record.ref")
        _validate_sha256(self.content_hash, "ref_record.content_hash")
        require_int_at_least(self.size_bytes, "ref_record.size_bytes", 0)
        require_non_empty_str(self.media_type, "ref_record.media_type")
        require_enum(self.materialization_state, RefMaterializationState, "ref_record.materialization_state")
        require_non_empty_str(self.store_id, "ref_record.store_id")
        require_non_empty_str(self.created_at, "ref_record.created_at")
        assert_refs_only_payload(_thaw_json_value(self.metadata), "ref_record.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "ref": self.ref,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "materialization_state": self.materialization_state.value,
            "store_id": self.store_id,
            "created_at": self.created_at,
            "metadata": ensure_json_value(_thaw_json_value(self.metadata), "ref_record.metadata"),
        }


class RefStore(Protocol):
    """Small runtime ref store protocol."""

    store_id: str

    def exists(self, ref: str) -> bool:
        """Return whether a ref has a current body."""

    def read_bytes(self, ref: str) -> bytes:
        """Read the current bytes for a ref."""

    def read_text(self, ref: str) -> str:
        """Read UTF-8 text for a ref."""

    def read_json(self, ref: str) -> Any:
        """Read a JSON-compatible value for a ref."""

    def read_jsonl(self, ref: str) -> list[Any]:
        """Read JSONL records for a ref."""

    def write_bytes(
        self,
        ref: str,
        body: bytes,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        """Write or replace one runtime ref body."""

    def write_text(
        self,
        ref: str,
        text: str,
        *,
        media_type: str = "text/plain",
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        """Write UTF-8 text to one runtime ref."""

    def write_json(
        self,
        ref: str,
        value: Any,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        """Write a canonical JSON value to one runtime ref."""

    def append_jsonl(
        self,
        ref: str,
        item: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        """Append one JSON-compatible item to a JSONL ref."""

    def hash_ref(self, ref: str) -> str:
        """Return the sha256 hash for a ref body, or a stable missing-ref hash."""

    def list_refs(self, prefix: str = "") -> list[str]:
        """List known refs with an optional prefix."""


class MemoryRefStore:
    """Volatile runtime ref store with no filesystem side effects."""

    def __init__(self, *, store_id: str = "memory") -> None:
        self.store_id = require_non_empty_str(store_id, "memory_ref_store.store_id")
        self._bodies: dict[str, bytes] = {}
        self._records: dict[str, RefRecord] = {}
        self._lock = RLock()

    def exists(self, ref: str) -> bool:
        safe_ref = validate_ref(ref, "ref_store.ref")
        with self._lock:
            return safe_ref in self._bodies

    def read_bytes(self, ref: str) -> bytes:
        safe_ref = validate_ref(ref, "ref_store.ref")
        with self._lock:
            try:
                body = self._bodies[safe_ref]
                record = self._records[safe_ref]
            except KeyError as exc:
                raise ContractValidationError(f"unknown ref: {safe_ref}") from exc
            _validate_body_against_record(body, record)
            return body

    def read_text(self, ref: str) -> str:
        return self.read_bytes(ref).decode("utf-8")

    def read_json(self, ref: str) -> Any:
        return json.loads(self.read_text(ref))

    def read_jsonl(self, ref: str) -> list[Any]:
        text = self.read_text(ref)
        if not text:
            return []
        return [json.loads(line) for line in text.splitlines()]

    def write_bytes(
        self,
        ref: str,
        body: bytes,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        safe_ref = validate_ref(ref, "ref_store.ref")
        if not isinstance(body, bytes):
            raise ContractValidationError("ref_store.body must be bytes")
        record = RefRecord.create(
            ref=safe_ref,
            body=body,
            media_type=media_type,
            materialization_state=RefMaterializationState.VOLATILE,
            store_id=self.store_id,
            metadata=metadata,
        )
        with self._lock:
            self._bodies[safe_ref] = bytes(body)
            self._records[safe_ref] = record
        return record

    def write_text(
        self,
        ref: str,
        text: str,
        *,
        media_type: str = "text/plain",
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        if not isinstance(text, str):
            raise ContractValidationError("ref_store.text must be a string")
        return self.write_bytes(ref, text.encode("utf-8"), media_type=media_type, metadata=metadata)

    def write_json(
        self,
        ref: str,
        value: Any,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        body = _canonical_json_bytes(value, field_name=ref)
        return self.write_bytes(ref, body, media_type="application/json", metadata=metadata)

    def append_jsonl(
        self,
        ref: str,
        item: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        safe_ref = validate_ref(ref, "ref_store.ref")
        line = _canonical_json_line(item, field_name=f"{safe_ref}[]")
        with self._lock:
            body = self._bodies.get(safe_ref, b"") + line
            return self.write_bytes(safe_ref, body, media_type="application/jsonl", metadata=metadata)

    def get_record(self, ref: str) -> RefRecord:
        safe_ref = validate_ref(ref, "ref_store.ref")
        with self._lock:
            try:
                return self._records[safe_ref]
            except KeyError as exc:
                raise ContractValidationError(f"unknown ref record: {safe_ref}") from exc

    def hash_ref(self, ref: str) -> str:
        safe_ref = validate_ref(ref, "ref_store.ref")
        with self._lock:
            body = self._bodies.get(safe_ref)
        if body is None:
            return _missing_ref_hash(safe_ref)
        return _hash_bytes(body)

    def list_refs(self, prefix: str = "") -> list[str]:
        with self._lock:
            if prefix:
                safe_prefix = validate_ref(prefix, "ref_store.prefix")
                return sorted(ref for ref in self._bodies if ref == safe_prefix or ref.startswith(f"{safe_prefix}/"))
            return sorted(self._bodies)


class FileRefStore:
    """Explicit filesystem-backed runtime ref store."""

    def __init__(self, root: str | Path, *, store_id: str = "file") -> None:
        self.store_id = require_non_empty_str(store_id, "file_ref_store.store_id")
        self._root = Path(root).resolve()
        self._records: dict[str, RefRecord] = {}
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def exists(self, ref: str) -> bool:
        with self._lock:
            return self._path_for_ref(ref).is_file()

    def read_bytes(self, ref: str) -> bytes:
        safe_ref = validate_ref(ref, "ref_store.ref")
        path = self._path_for_ref(safe_ref)
        with self._lock:
            if not path.is_file():
                raise ContractValidationError(f"unknown ref: {safe_ref}")
            body = path.read_bytes()
            record = self._records.get(safe_ref)
            if record is not None:
                _validate_body_against_record(body, record)
            return body

    def read_text(self, ref: str) -> str:
        return self.read_bytes(ref).decode("utf-8")

    def read_json(self, ref: str) -> Any:
        return json.loads(self.read_text(ref))

    def read_jsonl(self, ref: str) -> list[Any]:
        text = self.read_text(ref)
        if not text:
            return []
        return [json.loads(line) for line in text.splitlines()]

    def write_bytes(
        self,
        ref: str,
        body: bytes,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        safe_ref = validate_ref(ref, "ref_store.ref")
        if not isinstance(body, bytes):
            raise ContractValidationError("ref_store.body must be bytes")
        record = RefRecord.create(
            ref=safe_ref,
            body=body,
            media_type=media_type,
            materialization_state=RefMaterializationState.DURABLE,
            store_id=self.store_id,
            metadata=metadata,
        )
        path = self._path_for_ref(safe_ref)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            self._records[safe_ref] = record
        return record

    def write_text(
        self,
        ref: str,
        text: str,
        *,
        media_type: str = "text/plain",
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        if not isinstance(text, str):
            raise ContractValidationError("ref_store.text must be a string")
        return self.write_bytes(ref, text.encode("utf-8"), media_type=media_type, metadata=metadata)

    def write_json(
        self,
        ref: str,
        value: Any,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        body = _canonical_json_bytes(value, field_name=ref)
        return self.write_bytes(ref, body, media_type="application/json", metadata=metadata)

    def append_jsonl(
        self,
        ref: str,
        item: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> RefRecord:
        safe_ref = validate_ref(ref, "ref_store.ref")
        line = _canonical_json_line(item, field_name=f"{safe_ref}[]")
        path = self._path_for_ref(safe_ref)
        with self._lock:
            current = path.read_bytes() if path.is_file() else b""
            return self.write_bytes(safe_ref, current + line, media_type="application/jsonl", metadata=metadata)

    def get_record(self, ref: str) -> RefRecord:
        safe_ref = validate_ref(ref, "ref_store.ref")
        with self._lock:
            record = self._records.get(safe_ref)
            if record is not None:
                return record
            if not self._path_for_ref(safe_ref).is_file():
                raise ContractValidationError(f"unknown ref record: {safe_ref}")
            body = self.read_bytes(safe_ref)
            record = RefRecord.create(
                ref=safe_ref,
                body=body,
                materialization_state=RefMaterializationState.DURABLE,
                store_id=self.store_id,
                metadata={},
            )
            self._records[safe_ref] = record
            return record

    def hash_ref(self, ref: str) -> str:
        safe_ref = validate_ref(ref, "ref_store.ref")
        path = self._path_for_ref(safe_ref)
        with self._lock:
            if not path.is_file():
                return _missing_ref_hash(safe_ref)
            return _hash_bytes(path.read_bytes())

    def list_refs(self, prefix: str = "") -> list[str]:
        safe_prefix = validate_ref(prefix, "ref_store.prefix") if prefix else ""
        with self._lock:
            if not self._root.is_dir():
                return []
            refs: list[str] = []
            for path in self._root.rglob("*"):
                if not path.is_file():
                    continue
                ref = path.relative_to(self._root).as_posix()
                validate_ref(ref, "ref_store.discovered_ref")
                if safe_prefix and ref != safe_prefix and not ref.startswith(f"{safe_prefix}/"):
                    continue
                refs.append(ref)
            return sorted(refs)

    def _path_for_ref(self, ref: str) -> Path:
        safe_ref = validate_ref(ref, "ref_store.ref")
        path = (self._root / safe_ref).resolve()
        if path != self._root and self._root not in path.parents:
            raise ContractValidationError("ref_store path escaped root")
        return path


def _canonical_json_bytes(value: Any, *, field_name: str) -> bytes:
    compatible = ensure_json_value(value, field_name)
    return (stable_json_dumps(compatible) + "\n").encode("utf-8")


def _canonical_json_line(value: Mapping[str, Any], *, field_name: str) -> bytes:
    compatible = ensure_json_value(require_mapping(value, field_name), field_name)
    return (stable_json_dumps(compatible) + "\n").encode("utf-8")


def _hash_bytes(body: bytes) -> str:
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


def _missing_ref_hash(ref: str) -> str:
    return stable_json_hash({"missing_ref": validate_ref(ref, "ref_store.missing_ref")})


def _validate_body_against_record(body: bytes, record: RefRecord) -> None:
    record.validate()
    if _hash_bytes(body) != record.content_hash:
        raise ContractValidationError(f"ref body hash mismatch: {record.ref}")
    if len(body) != record.size_bytes:
        raise ContractValidationError(f"ref body size mismatch: {record.ref}")


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
