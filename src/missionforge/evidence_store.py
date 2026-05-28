"""Append-only evidence ledger implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from .contracts import (
    ContractValidationError,
    EvidenceTrustLevel,
    ensure_json_value,
    require_enum,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from .evidence import EvidenceRef


@dataclass(frozen=True)
class EvidenceRecord:
    """One immutable evidence ledger record."""

    sequence: int
    evidence_ref: EvidenceRef
    payload: dict[str, Any] = field(default_factory=dict)
    payload_hash: str = ""

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        evidence_id: str,
        ref: str,
        trust_level: EvidenceTrustLevel | str,
        kind: str,
        payload: Mapping[str, Any],
        source_refs: list[str] | None = None,
    ) -> "EvidenceRecord":
        payload_data = ensure_json_value(require_mapping(payload, "evidence_record.payload"), "evidence_record.payload")
        record = cls(
            sequence=require_int_at_least(sequence, "evidence_record.sequence", 1),
            evidence_ref=EvidenceRef(
                evidence_id=require_non_empty_str(evidence_id, "evidence_record.evidence_id"),
                ref=validate_ref(ref, "evidence_record.ref"),
                trust_level=require_enum(trust_level, EvidenceTrustLevel, "evidence_record.trust_level"),
                kind=require_non_empty_str(kind, "evidence_record.kind"),
                source_refs=source_refs or [],
            ),
            payload=payload_data,
            payload_hash=stable_json_hash(payload_data),
        )
        record.validate()
        return record

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceRecord":
        data = require_mapping(payload, "evidence_record")
        record = cls(
            sequence=require_int_at_least(data.get("sequence"), "evidence_record.sequence", 1),
            evidence_ref=EvidenceRef.from_dict(require_mapping(data.get("evidence_ref"), "evidence_record.evidence_ref")),
            payload=ensure_json_value(
                require_mapping(data.get("payload", {}), "evidence_record.payload"),
                "evidence_record.payload",
            ),
            payload_hash=require_non_empty_str(data.get("payload_hash"), "evidence_record.payload_hash"),
        )
        record.validate()
        if record.payload_hash != stable_json_hash(record.payload):
            raise ContractValidationError("evidence_record.payload_hash does not match payload")
        return record

    @property
    def evidence_id(self) -> str:
        return self.evidence_ref.evidence_id

    def validate(self) -> None:
        require_int_at_least(self.sequence, "evidence_record.sequence", 1)
        self.evidence_ref.validate()
        ensure_json_value(require_mapping(self.payload, "evidence_record.payload"), "evidence_record.payload")
        require_non_empty_str(self.payload_hash, "evidence_record.payload_hash")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "sequence": self.sequence,
            "evidence_ref": self.evidence_ref.to_dict(),
            "payload": ensure_json_value(self.payload, "evidence_record.payload"),
            "payload_hash": self.payload_hash,
        }


@dataclass(frozen=True)
class EvidenceSnapshot:
    """Deterministic snapshot of an evidence ledger."""

    records: list[EvidenceRecord] = field(default_factory=list)

    @property
    def ledger_hash(self) -> str:
        return stable_json_hash([record.to_dict() for record in self.records])

    def to_dict(self) -> dict[str, Any]:
        return {
            "ledger_hash": self.ledger_hash,
            "records": [record.to_dict() for record in self.records],
        }


class EvidenceLedger(Protocol):
    """Minimal append-only evidence ledger protocol."""

    def append(
        self,
        *,
        payload: Mapping[str, Any],
        trust_level: EvidenceTrustLevel | str,
        kind: str,
        source_refs: list[str] | None = None,
        evidence_id: str | None = None,
        ref: str | None = None,
    ) -> EvidenceRef:
        """Append one evidence record and return its ref."""

    def get(self, evidence_id: str) -> EvidenceRecord:
        """Return an evidence record by id."""

    def snapshot(self) -> EvidenceSnapshot:
        """Return a deterministic ledger snapshot."""


class InMemoryEvidenceStore:
    """Append-only in-memory evidence ledger."""

    def __init__(self, *, ref_prefix: str = "evidence") -> None:
        self._records: list[EvidenceRecord] = []
        self._by_id: dict[str, EvidenceRecord] = {}
        self._ref_prefix = validate_ref(ref_prefix, "evidence_store.ref_prefix")

    def append(
        self,
        *,
        payload: Mapping[str, Any],
        trust_level: EvidenceTrustLevel | str,
        kind: str,
        source_refs: list[str] | None = None,
        evidence_id: str | None = None,
        ref: str | None = None,
    ) -> EvidenceRef:
        sequence = len(self._records) + 1
        next_id = evidence_id or f"E-{sequence:06d}"
        if next_id in self._by_id:
            raise ContractValidationError(f"duplicate evidence_id: {next_id}")
        record_ref = ref or f"{self._ref_prefix}/{next_id}.json"
        record = EvidenceRecord.create(
            sequence=sequence,
            evidence_id=next_id,
            ref=record_ref,
            trust_level=trust_level,
            kind=kind,
            payload=payload,
            source_refs=source_refs,
        )
        self._records.append(record)
        self._by_id[record.evidence_id] = record
        return record.evidence_ref

    def get(self, evidence_id: str) -> EvidenceRecord:
        try:
            return self._by_id[require_non_empty_str(evidence_id, "evidence_id")]
        except KeyError as exc:
            raise ContractValidationError(f"unknown evidence_id: {evidence_id}") from exc

    def snapshot(self) -> EvidenceSnapshot:
        return EvidenceSnapshot(records=list(self._records))


class FileEvidenceStore(InMemoryEvidenceStore):
    """Append-only JSON file backed evidence ledger."""

    def __init__(self, root: str | Path, *, ref_prefix: str = "evidence") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        super().__init__(ref_prefix=ref_prefix)
        self._load_existing()

    def append(
        self,
        *,
        payload: Mapping[str, Any],
        trust_level: EvidenceTrustLevel | str,
        kind: str,
        source_refs: list[str] | None = None,
        evidence_id: str | None = None,
        ref: str | None = None,
    ) -> EvidenceRef:
        evidence_ref = super().append(
            payload=payload,
            trust_level=trust_level,
            kind=kind,
            source_refs=source_refs,
            evidence_id=evidence_id,
            ref=ref,
        )
        record = self.get(evidence_ref.evidence_id)
        path = self._record_path(record.evidence_id)
        if path.exists():
            self._records.pop()
            self._by_id.pop(record.evidence_id, None)
            raise ContractValidationError(f"evidence record already exists on disk: {record.evidence_id}")
        path.write_text(json.dumps(record.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return evidence_ref

    def _load_existing(self) -> None:
        for path in sorted(self._root.glob("*.json")):
            record = EvidenceRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if record.evidence_id in self._by_id:
                raise ContractValidationError(f"duplicate evidence_id on disk: {record.evidence_id}")
            expected_sequence = len(self._records) + 1
            if record.sequence != expected_sequence:
                raise ContractValidationError("file evidence store records must have contiguous sequences")
            self._records.append(record)
            self._by_id[record.evidence_id] = record

    def _record_path(self, evidence_id: str) -> Path:
        safe_id = require_non_empty_str(evidence_id, "evidence_id")
        if "/" in safe_id or "\\" in safe_id:
            raise ContractValidationError("evidence_id must not contain path separators")
        return self._root / f"{safe_id}.json"
