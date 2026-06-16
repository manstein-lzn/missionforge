"""Mechanical evidence and citation checks for DeepResearch artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from missionforge.contracts import require_mapping, require_non_empty_str, validate_ref


SOURCE_PACKET_SCHEMA_VERSION = "missionforge_deepresearch.source_packet.v1"
SOURCE_ID_RE = re.compile(r"^S[0-9]+$")
_CITATION_GROUP_RE = re.compile(r"\[((?:S[0-9]+)(?:\s*,\s*S[0-9]+)*)\]")
_REFERENCES_HEADING_RE = re.compile(r"^##\s+(References|参考文献)\s*$", re.IGNORECASE | re.MULTILINE)
_LOCATOR_FIELDS = ("url", "doi", "source_ref", "github_repo", "arxiv_id")


@dataclass(frozen=True)
class SourcePacketAudit:
    """Mechanical source packet validation result."""

    source_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "passed" if self.passed else "failed",
            "source_ids": list(self.source_ids),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class CitationAudit:
    """Mechanical citation validation result for report artifacts."""

    cited_source_ids: list[str] = field(default_factory=list)
    reference_source_ids: list[str] = field(default_factory=list)
    evidence_index_source_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "passed" if self.passed else "failed",
            "cited_source_ids": list(self.cited_source_ids),
            "reference_source_ids": list(self.reference_source_ids),
            "evidence_index_source_ids": list(self.evidence_index_source_ids),
            "errors": list(self.errors),
        }


def audit_source_packet(payload: Mapping[str, Any], *, request_id: str | None = None) -> SourcePacketAudit:
    """Validate that source_packet.json is a usable structured evidence sink."""

    errors: list[str] = []
    try:
        data = require_mapping(payload, "deepresearch_source_packet")
        schema_version = require_non_empty_str(
            data.get("schema_version"),
            "deepresearch_source_packet.schema_version",
        )
        if schema_version != SOURCE_PACKET_SCHEMA_VERSION:
            errors.append("source_packet_schema_version_unsupported")
        if request_id is not None and data.get("request_id") != request_id:
            errors.append("source_packet_request_id_mismatch")
        records = data.get("source_records", [])
        if not isinstance(records, list) or not records:
            errors.append("source_packet_source_records_empty")
            return SourcePacketAudit(errors=errors)
    except Exception as exc:
        return SourcePacketAudit(errors=[f"source_packet_invalid:{type(exc).__name__}"])

    source_ids: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(records):
        if not isinstance(item, Mapping):
            errors.append(f"source_record_{index + 1}_not_mapping")
            continue
        record = dict(item)
        source_id = str(record.get("source_id", "")).strip()
        if not SOURCE_ID_RE.match(source_id):
            errors.append(f"source_record_{index + 1}_source_id_invalid")
            continue
        if source_id in seen:
            errors.append(f"source_record_{source_id}_duplicate")
        seen.add(source_id)
        source_ids.append(source_id)
        _validate_source_record_shape(record, source_id, errors)
    return SourcePacketAudit(source_ids=source_ids, errors=errors)


def audit_report_citations(
    *,
    final_report_text: str,
    evidence_index_text: str,
    source_ids: list[str],
) -> CitationAudit:
    """Validate that report citations are backed by source_packet source ids."""

    known_ids = set(source_ids)
    cited_ids = _dedupe(extract_source_ids(final_report_text))
    references_text = _references_section(final_report_text)
    reference_ids = _dedupe(extract_source_ids(references_text)) if references_text else []
    evidence_index_ids = _dedupe(extract_source_ids(evidence_index_text))
    errors: list[str] = []

    if not cited_ids:
        errors.append("final_report_missing_source_citations")
    unknown_citations = sorted(set(cited_ids) - known_ids)
    if unknown_citations:
        errors.append(f"final_report_unknown_source_ids:{','.join(unknown_citations)}")
    if references_text == "":
        errors.append("final_report_missing_references_section")
    missing_reference_ids = sorted(set(cited_ids) - set(reference_ids))
    if missing_reference_ids:
        errors.append(f"references_missing_cited_source_ids:{','.join(missing_reference_ids)}")
    unknown_reference_ids = sorted(set(reference_ids) - known_ids)
    if unknown_reference_ids:
        errors.append(f"references_unknown_source_ids:{','.join(unknown_reference_ids)}")
    missing_index_ids = sorted(known_ids - set(evidence_index_ids))
    if missing_index_ids:
        errors.append(f"evidence_index_missing_source_ids:{','.join(missing_index_ids)}")

    return CitationAudit(
        cited_source_ids=cited_ids,
        reference_source_ids=reference_ids,
        evidence_index_source_ids=evidence_index_ids,
        errors=errors,
    )


def extract_source_ids(text: str) -> list[str]:
    """Extract `[S1]` or `[S1, S2]` style source ids from markdown text."""

    source_ids: list[str] = []
    for match in _CITATION_GROUP_RE.finditer(text):
        for item in match.group(1).split(","):
            source_ids.append(item.strip())
    return source_ids


def _validate_source_record_shape(record: Mapping[str, Any], source_id: str, errors: list[str]) -> None:
    for field_name in ("title", "source_type"):
        value = record.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"source_record_{source_id}_missing_{field_name}")
    if not _has_locator(record):
        errors.append(f"source_record_{source_id}_missing_locator")
    source_ref = record.get("source_ref")
    if isinstance(source_ref, str) and source_ref.strip():
        try:
            validate_ref(source_ref, f"source_record_{source_id}.source_ref")
        except Exception:
            errors.append(f"source_record_{source_id}_invalid_source_ref")
    year = record.get("year", record.get("publication_year"))
    if year is not None and (not isinstance(year, int) or isinstance(year, bool)):
        errors.append(f"source_record_{source_id}_invalid_year")


def _has_locator(record: Mapping[str, Any]) -> bool:
    if any(isinstance(record.get(field_name), str) and record.get(field_name, "").strip() for field_name in _LOCATOR_FIELDS):
        return True
    locator = record.get("locator")
    if not isinstance(locator, Mapping):
        return False
    return any(isinstance(locator.get(field_name), str) and locator.get(field_name, "").strip() for field_name in _LOCATOR_FIELDS)


def _references_section(text: str) -> str:
    match = _REFERENCES_HEADING_RE.search(text)
    if not match:
        return ""
    return text[match.end():]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
