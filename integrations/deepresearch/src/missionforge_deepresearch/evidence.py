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
    source_record_count: int = 0
    distinct_source_types: list[str] = field(default_factory=list)
    recent_source_record_count: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "passed" if self.passed else "failed",
            "source_ids": list(self.source_ids),
            "source_record_count": self.source_record_count,
            "distinct_source_types": list(self.distinct_source_types),
            "recent_source_record_count": self.recent_source_record_count,
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


@dataclass(frozen=True)
class QualityContractAudit:
    """Mechanical validation against the product quality contract."""

    status: str
    required_report_sections: list[str] = field(default_factory=list)
    present_report_sections: list[str] = field(default_factory=list)
    required_section_ids: list[str] = field(default_factory=list)
    present_section_ids: list[str] = field(default_factory=list)
    source_record_count: int = 0
    distinct_source_type_count: int = 0
    recent_source_record_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status in {"passed", "skipped"} and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "required_report_sections": list(self.required_report_sections),
            "present_report_sections": list(self.present_report_sections),
            "required_section_ids": list(self.required_section_ids),
            "present_section_ids": list(self.present_section_ids),
            "source_record_count": self.source_record_count,
            "distinct_source_type_count": self.distinct_source_type_count,
            "recent_source_record_count": self.recent_source_record_count,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
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
    source_types: list[str] = []
    recent_count = 0
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
        source_type = str(record.get("source_type", "")).strip()
        if source_type and source_type not in source_types:
            source_types.append(source_type)
        year = record.get("year", record.get("publication_year"))
        if isinstance(year, int) and not isinstance(year, bool) and year >= 2023:
            recent_count += 1
        _validate_source_record_shape(record, source_id, errors)
    return SourcePacketAudit(
        source_ids=source_ids,
        source_record_count=len(source_ids),
        distinct_source_types=source_types,
        recent_source_record_count=recent_count,
        errors=errors,
    )


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


def audit_quality_contract(
    *,
    output_contract: Mapping[str, Any] | None,
    source_packet: Mapping[str, Any],
    final_report_text: str,
) -> QualityContractAudit:
    """Mechanically check the high-quality DeepResearch contract shape."""

    if not output_contract:
        return QualityContractAudit(
            status="skipped",
            warnings=["quality_contract_missing"],
        )
    quality_contract = output_contract.get("quality_contract")
    if not isinstance(quality_contract, Mapping):
        return QualityContractAudit(
            status="skipped",
            warnings=["quality_contract_missing"],
        )
    section_specs = _report_section_specs(quality_contract)
    required_sections = [section["title"] for section in section_specs]
    required_section_ids = [section["section_id"] for section in section_specs]
    minimums = quality_contract.get("source_packet_minimums")
    if not isinstance(minimums, Mapping):
        minimums = {}
    required_source_fields = _str_list(minimums.get("required_source_record_fields", []))
    min_source_records = _int_at_least(minimums.get("min_source_records"), 0)
    min_distinct_source_types = _int_at_least(minimums.get("min_distinct_source_types"), 0)
    min_recent_source_records = _int_at_least(minimums.get("min_recent_source_records"), 0)
    recent_year_min = _int_at_least(minimums.get("recent_year_min"), 0)

    errors: list[str] = []
    warnings: list[str] = []
    present_section_ids = _present_section_ids(final_report_text, section_specs)
    present_sections = [
        section["title"] for section in section_specs if section["section_id"] in present_section_ids
    ]
    missing_section_ids = [section_id for section_id in required_section_ids if section_id not in present_section_ids]
    if missing_section_ids:
        errors.append(f"final_report_missing_quality_sections:{','.join(missing_section_ids)}")

    records = source_packet.get("source_records", [])
    source_records = [record for record in records if isinstance(record, Mapping)] if isinstance(records, list) else []
    source_types = _dedupe([
        str(record.get("source_type", "")).strip()
        for record in source_records
        if str(record.get("source_type", "")).strip()
    ])
    recent_count = 0
    for record in source_records:
        year = record.get("year", record.get("publication_year"))
        if isinstance(year, int) and not isinstance(year, bool) and year >= recent_year_min:
            recent_count += 1

    fixture_only = source_records and all("fixture" in str(record.get("source_type", "")).lower() for record in source_records)
    if fixture_only:
        warnings.append("source_quality_thresholds_skipped_for_fixture_records")
    else:
        if len(source_records) < min_source_records:
            errors.append(f"source_packet_below_min_source_records:{len(source_records)}<{min_source_records}")
        if len(source_types) < min_distinct_source_types:
            errors.append(
                f"source_packet_below_min_distinct_source_types:{len(source_types)}<{min_distinct_source_types}"
            )
        if recent_count < min_recent_source_records:
            errors.append(f"source_packet_below_min_recent_sources:{recent_count}<{min_recent_source_records}")
        for record in source_records:
            source_id = str(record.get("source_id", "unknown")).strip() or "unknown"
            for field_name in required_source_fields:
                value = record.get(field_name)
                if value is None or (isinstance(value, str) and not value.strip()):
                    errors.append(f"source_record_{source_id}_missing_quality_field:{field_name}")

    return QualityContractAudit(
        status="passed" if not errors else "failed",
        required_report_sections=required_sections,
        present_report_sections=present_sections,
        required_section_ids=required_section_ids,
        present_section_ids=present_section_ids,
        source_record_count=len(source_records),
        distinct_source_type_count=len(source_types),
        recent_source_record_count=recent_count,
        errors=errors,
        warnings=warnings,
    )


def _validate_source_record_shape(record: Mapping[str, Any], source_id: str, errors: list[str]) -> None:
    for field_name in ("title", "source_type"):
        value = record.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"source_record_{source_id}_missing_{field_name}")
    if not _has_locator(record):
        errors.append(f"source_record_{source_id}_missing_locator")
    source_ref = record.get("source_ref")
    if isinstance(source_ref, str) and source_ref.strip():
        if not _valid_source_ref_locator(source_ref):
            errors.append(f"source_record_{source_id}_invalid_source_ref")
    year = record.get("year", record.get("publication_year"))
    if year is not None and (not isinstance(year, int) or isinstance(year, bool)):
        errors.append(f"source_record_{source_id}_invalid_year")


def _valid_source_ref_locator(value: str) -> bool:
    source_ref = value.strip()
    if not source_ref or any(char in source_ref for char in "\r\n\t"):
        return False
    if "://" in source_ref:
        return True
    try:
        validate_ref(source_ref, "source_ref")
        return True
    except Exception:
        pass
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}:.+$", source_ref))


def _has_locator(record: Mapping[str, Any]) -> bool:
    if any(isinstance(record.get(field_name), str) and record.get(field_name, "").strip() for field_name in _LOCATOR_FIELDS):
        return True
    locator = record.get("locator")
    if isinstance(locator, str) and locator.strip():
        return True
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


def _present_section_ids(text: str, section_specs: list[dict[str, Any]]) -> list[str]:
    headings = {
        _normalize_heading(match.group(1))
        for match in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    }
    present: list[str] = []
    for section in section_specs:
        aliases = section.get("aliases", [])
        if any(_normalize_heading(alias) in headings for alias in aliases):
            present.append(section["section_id"])
    return present


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _int_at_least(value: Any, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return default


def _report_section_specs(quality_contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    specs = quality_contract.get("report_sections")
    if isinstance(specs, list):
        normalized_specs: list[dict[str, Any]] = []
        for index, item in enumerate(specs):
            if not isinstance(item, Mapping):
                continue
            section_id = str(item.get("section_id", "")).strip()
            title = str(item.get("title", "")).strip()
            canonical_title = str(item.get("canonical_title", "")).strip()
            if not section_id:
                section_id = f"section_{index + 1}"
            if not title:
                title = canonical_title or section_id
            aliases = _dedupe([
                title,
                canonical_title,
                *_str_list(item.get("aliases", [])),
            ])
            normalized_specs.append(
                {
                    "section_id": section_id,
                    "title": title,
                    "aliases": aliases,
                }
            )
        if normalized_specs:
            return normalized_specs
    return [
        {
            "section_id": _normalize_heading(section).replace(" ", "_"),
            "title": section,
            "aliases": [section],
        }
        for section in _str_list(quality_contract.get("required_report_sections", []))
    ]
