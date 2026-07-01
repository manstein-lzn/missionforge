"""Source-acquisition artifact helpers for DeepResearch.

This module owns mechanical artifact shapes for search planning and coverage
reporting. It does not rank papers semantically or decide research sufficiency.
"""

from __future__ import annotations

from collections import Counter
import json
from typing import Any, Iterable, Mapping


SEARCH_PLAN_SCHEMA_VERSION = "missionforge_deepresearch.search_plan.v1"
PROVIDER_HIT_SCHEMA_VERSION = "missionforge_deepresearch.provider_hit.v1"
COVERAGE_REPORT_SCHEMA_VERSION = "missionforge_deepresearch.coverage_report.v1"

DEFAULT_NO_KEY_PROVIDER_IDS = ["semantic_scholar", "arxiv", "crossref", "dblp", "pubmed"]
REFERENCE_SOURCE_BASELINE = 50


def build_fixture_provider_capabilities(*, request_id: str, provider_policy: str) -> dict[str, Any]:
    """Return a no-key provider-capability fixture for structural tests."""

    return {
        "schema_version": "missionforge.pi_academic_sources.provider_capabilities.v1",
        "request_id": request_id,
        "provider_policy": provider_policy,
        "default_search_provider_ids": list(DEFAULT_NO_KEY_PROVIDER_IDS),
        "providers": [
            {
                "provider": provider,
                "status": "enabled",
                "requires_secret": False,
                "missing_secret": False,
                "role": "default_no_key",
            }
            for provider in DEFAULT_NO_KEY_PROVIDER_IDS
        ],
        "diagnostics": [
            {
                "provider": "openalex",
                "code": "optional_provider_disabled_in_fixture",
                "severity": "info",
            }
        ],
    }


def build_fixture_search_plan(
    *,
    request_id: str,
    topic: str,
    provider_policy: str,
    target_source_count: int,
    max_source_count: int,
) -> dict[str, Any]:
    """Return a source-mapper-authored fixture search plan."""

    return {
        "schema_version": SEARCH_PLAN_SCHEMA_VERSION,
        "request_id": request_id,
        "provider_policy": provider_policy,
        "source_count_budget": {
            "reference_source_baseline": REFERENCE_SOURCE_BASELINE,
            "target_source_count": target_source_count,
            "max_source_count": max_source_count,
            "adaptive_expansion_allowed": True,
            "budget_semantics": "coverage_guidance_not_acceptance_rule",
        },
        "provider_plan": [
            {
                "provider": provider,
                "role": "default_no_key",
                "enabled_condition": "provider_capabilities.status == enabled",
            }
            for provider in DEFAULT_NO_KEY_PROVIDER_IDS
        ],
        "waves": [
            {
                "wave_id": "wave-1",
                "goal": "establish broad initial scholarly coverage",
                "query_ids": ["Q1"],
                "stopping_criteria": [
                    "source_packet contains a usable initial evidence base",
                    "coverage gaps are explicit",
                ],
            }
        ],
        "query_families": [
            {
                "family_id": "core_topic",
                "label": "Core topic",
                "intent": "Find representative papers, surveys, systems, and recent work for the user's topic.",
                "wave_id": "wave-1",
                "queries": [
                    {
                        "query_id": "Q1",
                        "query": topic,
                        "providers": list(DEFAULT_NO_KEY_PROVIDER_IDS),
                        "limit_per_provider": 10,
                    }
                ],
            }
        ],
        "expected_evidence_classes": ["metadata", "abstract", "full_text_or_pdf_when_accessible"],
        "stopping_criteria": [
            "major research lines have enough candidate sources for synthesis",
            "missing providers, inaccessible sources, and weak evidence classes are recorded",
            "additional broad search would mostly duplicate known results",
        ],
    }


def provider_hits_jsonl_from_source_packet(
    *,
    request_id: str,
    source_packet: Mapping[str, Any],
    query: str,
    provider: str = "fixture",
) -> str:
    """Return provider-hit JSONL lines that point at source packet records."""

    lines = []
    for index, record in enumerate(_source_records(source_packet), start=1):
        source_id = _clean(record.get("source_id")) or f"S{index}"
        lines.append(
            json.dumps(
                {
                    "schema_version": PROVIDER_HIT_SCHEMA_VERSION,
                    "request_id": request_id,
                    "hit_id": f"H{index}",
                    "wave_id": "wave-1",
                    "query_family_id": "core_topic",
                    "query_id": "Q1",
                    "query": query,
                    "provider": provider,
                    "status": "completed",
                    "source_record_ids": [source_id],
                    "record_count": 1,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        )
    return "\n".join(lines) + ("\n" if lines else "")


def project_coverage_report(
    *,
    request_id: str,
    source_packet: Mapping[str, Any],
    search_plan: Mapping[str, Any] | None = None,
    provider_capabilities: Mapping[str, Any] | None = None,
    provider_hits: Iterable[Mapping[str, Any]] | None = None,
    target_source_count: int,
) -> dict[str, Any]:
    """Project a mechanical coverage report from source artifacts."""

    records = _source_records(source_packet)
    hits = list(provider_hits or [])
    years = [_optional_int(record.get("year")) for record in records]
    known_years = [year for year in years if year is not None]
    provider_counts = Counter(_provider(record) for record in records)
    evidence_counts = Counter(_clean(record.get("evidence_strength")) or "metadata" for record in records)
    hit_provider_counts = Counter(_clean(hit.get("provider")) or "unknown" for hit in hits)
    query_family_counts = Counter(_clean(hit.get("query_family_id")) or "unknown" for hit in hits)
    provider_status = _provider_status(provider_capabilities)
    source_count = len(records)
    limits: list[str] = []
    if source_count < target_source_count:
        limits.append("source_record_count_below_target")
    if not hits:
        limits.append("provider_hits_not_recorded")
    if not provider_status:
        limits.append("provider_capabilities_not_recorded")
    unavailable = [
        item["provider"]
        for item in provider_status
        if item.get("status") not in {"enabled", "completed", "available"}
    ]
    if unavailable:
        limits.append("provider_unavailable:" + ",".join(unavailable))
    return {
        "schema_version": COVERAGE_REPORT_SCHEMA_VERSION,
        "request_id": request_id,
        "source_packet_ref": "sources/source_packet.json",
        "search_plan_ref": "sources/search_plan.json",
        "provider_hits_ref": "sources/provider_hits.jsonl",
        "provider_capabilities_ref": "sources/provider_capabilities.json",
        "target_source_count": target_source_count,
        "reference_source_baseline": REFERENCE_SOURCE_BASELINE,
        "source_record_count": source_count,
        "mechanical_coverage_status": "target_met" if source_count >= target_source_count else "below_target",
        "semantic_sufficiency": "piworker_judge_required",
        "provider_record_counts": dict(sorted(provider_counts.items())),
        "provider_hit_counts": dict(sorted(hit_provider_counts.items())),
        "query_family_hit_counts": dict(sorted(query_family_counts.items())),
        "evidence_strength_counts": dict(sorted(evidence_counts.items())),
        "year_coverage": {
            "min_year": min(known_years) if known_years else None,
            "max_year": max(known_years) if known_years else None,
            "unknown_year_count": len([year for year in years if year is None]),
        },
        "provider_status": provider_status,
        "planned_query_family_count": len(_query_families(search_plan or {})),
        "coverage_limits": limits,
    }


def parse_provider_hits_jsonl(text: str) -> list[dict[str, Any]]:
    """Parse provider hit JSONL into dictionaries, ignoring blank lines."""

    hits = []
    for line in text.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            hits.append(payload)
    return hits


def _source_records(source_packet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = source_packet.get("source_records")
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, Mapping)]


def _provider(record: Mapping[str, Any]) -> str:
    return _clean(record.get("provider")) or _clean(record.get("source_type")) or "unknown"


def _provider_status(provider_capabilities: Mapping[str, Any] | None) -> list[dict[str, str]]:
    providers = (provider_capabilities or {}).get("providers")
    if not isinstance(providers, list):
        return []
    result = []
    for item in providers:
        if not isinstance(item, Mapping):
            continue
        provider = _clean(item.get("provider"))
        if not provider:
            continue
        result.append(
            {
                "provider": provider,
                "status": _clean(item.get("status")) or "unknown",
                "role": _clean(item.get("role")),
            }
        )
    return result


def _query_families(search_plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    families = search_plan.get("query_families")
    if not isinstance(families, list):
        return []
    return [family for family in families if isinstance(family, Mapping)]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""
