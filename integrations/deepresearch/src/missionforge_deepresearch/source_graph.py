"""Mechanical source graph projection for DeepResearch.

This module normalizes source records and deduplicates exact identifiers. It
does not judge semantic relevance or decide which papers are important.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Mapping

import missionforge as mf


SOURCE_GRAPH_SCHEMA_VERSION = "missionforge_deepresearch.source_graph.v1"
CANONICAL_SOURCES_SCHEMA_VERSION = "missionforge_deepresearch.canonical_sources.v1"
DEDUPE_MAP_SCHEMA_VERSION = "missionforge_deepresearch.dedupe_map.v1"


@dataclass(frozen=True)
class CanonicalSource:
    """Mechanical canonical source record derived from provider/source hits."""

    source_id: str
    canonical_key: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    identifiers: dict[str, str] = field(default_factory=dict)
    locators: list[dict[str, str]] = field(default_factory=list)
    provider_provenance: list[str] = field(default_factory=list)
    abstract_ref: str = ""
    fulltext_ref: str = ""
    evidence_strength: str = "metadata"
    inclusion_status: str = "candidate"
    inclusion_reason: str = ""
    source_record_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "canonical_key": self.canonical_key,
            "title": self.title,
            "title_hash": _title_hash(self.title),
            "authors": list(self.authors),
            "year": self.year,
            "venue": self.venue,
            "identifiers": dict(self.identifiers),
            "locators": [dict(item) for item in self.locators],
            "provider_provenance": list(self.provider_provenance),
            "abstract_ref": self.abstract_ref,
            "fulltext_ref": self.fulltext_ref,
            "evidence_strength": self.evidence_strength,
            "inclusion_status": self.inclusion_status,
            "inclusion_reason": self.inclusion_reason,
            "source_record_ids": list(self.source_record_ids),
        }


def project_source_graph(source_packet: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical source, dedupe map, and source graph payloads."""

    records = source_packet.get("source_records", [])
    if not isinstance(records, list):
        raise mf.ContractValidationError("source_packet.source_records must be a list")
    buckets: dict[str, dict[str, Any]] = {}
    dedupe_entries: list[dict[str, Any]] = []
    for index, raw_record in enumerate(records):
        if not isinstance(raw_record, Mapping):
            raise mf.ContractValidationError(f"source_packet.source_records[{index}] must be an object")
        normalized = _normalize_source_record(raw_record, index)
        bucket_key = normalized["canonical_key"]
        bucket = buckets.setdefault(bucket_key, _new_bucket(bucket_key))
        _merge_bucket(bucket, normalized)
        dedupe_entries.append(
            {
                "input_source_id": normalized["input_source_id"],
                "canonical_key": bucket_key,
                "dedupe_reason": normalized["canonical_reason"],
            }
        )
    canonical_sources = []
    used_source_ids: set[str] = set()
    for number, bucket in enumerate(buckets.values(), start=1):
        source_id = _canonical_source_id(bucket, number, used_source_ids)
        used_source_ids.add(source_id)
        for entry in dedupe_entries:
            if entry["canonical_key"] == bucket["canonical_key"]:
                entry["canonical_source_id"] = source_id
        canonical_sources.append(_bucket_to_source(source_id, bucket).to_dict())
    request_id = str(source_packet.get("request_id") or "")
    canonical_payload = {
        "schema_version": CANONICAL_SOURCES_SCHEMA_VERSION,
        "request_id": request_id,
        "sources": canonical_sources,
    }
    dedupe_payload = {
        "schema_version": DEDUPE_MAP_SCHEMA_VERSION,
        "request_id": request_id,
        "entries": dedupe_entries,
    }
    source_graph_payload = {
        "schema_version": SOURCE_GRAPH_SCHEMA_VERSION,
        "request_id": request_id,
        "canonical_sources_ref": "sources/canonical_sources.json",
        "dedupe_map_ref": "sources/dedupe_map.json",
        "source_packet_ref": "sources/source_packet.json",
        "canonical_source_count": len(canonical_sources),
        "input_source_count": len(records),
        "sources": canonical_sources,
    }
    return {
        "canonical_sources": canonical_payload,
        "dedupe_map": dedupe_payload,
        "source_graph": source_graph_payload,
    }


def _normalize_source_record(record: Mapping[str, Any], index: int) -> dict[str, Any]:
    source_id = _clean(record.get("source_id")) or f"input-{index + 1}"
    title = _clean(record.get("title"))
    provider = _clean(record.get("provider")) or _clean(record.get("source_type")) or "source_packet"
    identifiers = _identifiers(record)
    locator = _clean(record.get("locator")) or _clean(record.get("url"))
    locators = _locators(record, locator)
    canonical_key, reason = _canonical_key(title, identifiers, source_id)
    return {
        "input_source_id": source_id,
        "canonical_key": canonical_key,
        "canonical_reason": reason,
        "title": title,
        "authors": _string_list(record.get("authors")),
        "year": _optional_int(record.get("year")),
        "venue": _clean(record.get("venue")),
        "identifiers": identifiers,
        "locators": locators,
        "provider": provider,
        "evidence_strength": _clean(record.get("evidence_strength")) or "metadata",
        "inclusion_reason": _clean(record.get("evidence_note")),
    }


def _new_bucket(canonical_key: str) -> dict[str, Any]:
    return {
        "canonical_key": canonical_key,
        "titles": [],
        "authors": [],
        "year": None,
        "venue": "",
        "identifiers": {},
        "locators": [],
        "provider_provenance": [],
        "evidence_strengths": [],
        "inclusion_reasons": [],
        "source_record_ids": [],
    }


def _merge_bucket(bucket: dict[str, Any], normalized: Mapping[str, Any]) -> None:
    _append_unique(bucket["titles"], normalized["title"])
    for author in normalized["authors"]:
        _append_unique(bucket["authors"], author)
    if bucket["year"] is None and normalized["year"] is not None:
        bucket["year"] = normalized["year"]
    if not bucket["venue"] and normalized["venue"]:
        bucket["venue"] = normalized["venue"]
    for key, value in normalized["identifiers"].items():
        if value and not bucket["identifiers"].get(key):
            bucket["identifiers"][key] = value
    for locator in normalized["locators"]:
        if locator not in bucket["locators"]:
            bucket["locators"].append(locator)
    _append_unique(bucket["provider_provenance"], normalized["provider"])
    _append_unique(bucket["evidence_strengths"], normalized["evidence_strength"])
    _append_unique(bucket["inclusion_reasons"], normalized["inclusion_reason"])
    _append_unique(bucket["source_record_ids"], normalized["input_source_id"])


def _bucket_to_source(source_id: str, bucket: Mapping[str, Any]) -> CanonicalSource:
    title = next((item for item in bucket["titles"] if item), "")
    evidence_strength = _strongest_evidence(bucket["evidence_strengths"])
    locators = bucket["locators"]
    return CanonicalSource(
        source_id=source_id,
        canonical_key=str(bucket["canonical_key"]),
        title=title,
        authors=list(bucket["authors"])[:20],
        year=bucket["year"],
        venue=str(bucket["venue"]),
        identifiers=dict(bucket["identifiers"]),
        locators=list(locators),
        provider_provenance=list(bucket["provider_provenance"]),
        evidence_strength=evidence_strength,
        inclusion_status="candidate",
        inclusion_reason="; ".join([item for item in bucket["inclusion_reasons"] if item]),
        source_record_ids=list(bucket["source_record_ids"]),
    )


def _canonical_source_id(bucket: Mapping[str, Any], number: int, used: set[str]) -> str:
    for value in bucket["source_record_ids"]:
        text = str(value)
        if re.fullmatch(r"S\d+", text) and text not in used:
            return text
    return f"S{number:04d}"


def _identifiers(record: Mapping[str, Any]) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    doi = _strip_doi(_clean(record.get("doi")))
    arxiv = _clean(record.get("arxiv_id")) or _arxiv_from_locator(_clean(record.get("locator")) or _clean(record.get("url")))
    semantic_scholar = _clean(record.get("semantic_scholar_id")) or _clean(record.get("paperId"))
    openalex = _clean(record.get("openalex_id"))
    if not openalex:
        locator = _clean(record.get("locator")) or _clean(record.get("url"))
        if locator.lower().startswith("https://openalex.org/"):
            openalex = locator.rsplit("/", 1)[-1]
    for key, value in {
        "doi": doi,
        "arxiv": arxiv,
        "semantic_scholar": semantic_scholar,
        "openalex": openalex,
    }.items():
        if value:
            identifiers[key] = value
    return identifiers


def _locators(record: Mapping[str, Any], fallback: str) -> list[dict[str, str]]:
    locators = []
    for value in [
        fallback,
        _clean(record.get("url")),
        _clean(record.get("open_access_url")),
        _clean(record.get("pdf_url")),
    ]:
        if not value:
            continue
        kind = "url"
        if value.lower().startswith("doi:") or value.lower().startswith("https://doi.org/"):
            kind = "doi"
        elif "arxiv.org" in value.lower() or value.lower().startswith("arxiv:"):
            kind = "arxiv"
        elif "openalex.org" in value.lower():
            kind = "openalex"
        elif value.lower().endswith(".pdf"):
            kind = "pdf"
        item = {"kind": kind, "url": value, "access_status": "unchecked"}
        if item not in locators:
            locators.append(item)
    return locators


def _canonical_key(title: str, identifiers: Mapping[str, str], source_id: str) -> tuple[str, str]:
    for key in ("doi", "arxiv", "semantic_scholar", "openalex"):
        value = identifiers.get(key)
        if value:
            return f"{key}:{value.lower()}", key
    normalized_title = _normalize_title(title)
    if normalized_title:
        return f"title:{_title_hash(normalized_title)}", "normalized_title"
    fallback = source_id or title
    return f"unknown:{hashlib.sha256(fallback.encode('utf-8')).hexdigest()[:16]}", "unknown_record"


def _title_hash(title: str) -> str:
    return "sha256:" + hashlib.sha256(_normalize_title(title).encode("utf-8")).hexdigest()


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _strip_doi(value: str) -> str:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.IGNORECASE).lower()


def _arxiv_from_locator(value: str) -> str:
    if value.lower().startswith("arxiv:"):
        return value.split(":", 1)[1]
    match = re.search(r"arxiv\.org/abs/([^?#\s]+)", value, re.IGNORECASE)
    return match.group(1) if match else ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _append_unique(values: list[Any], value: Any) -> None:
    if value and value not in values:
        values.append(value)


def _strongest_evidence(values: list[str]) -> str:
    order = ["metadata", "abstract", "full_text", "pdf_text", "repo_docs", "fixture"]
    ranked = {name: index for index, name in enumerate(order)}
    best = "metadata"
    for value in values:
        if ranked.get(value, -1) > ranked.get(best, -1):
            best = value
    return best


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""
