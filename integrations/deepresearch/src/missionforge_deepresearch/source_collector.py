"""Live academic source collection for the DeepResearch integration.

This module is intentionally mechanical. It executes declared search-intent
queries against general academic indexes and records source refs. It does not
expand domain queries with product-specific knowledge or rank sources
semantically.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import json
import re

from missionforge.contracts import ContractValidationError, require_mapping, require_non_empty_str

from .product_contract import AcademicResearchRequest
from .search_intent import AcademicSearchIntent, SEARCH_INTENT_REF


SOURCE_COLLECTION_REPORT_REF = "sources/source_collection_report.json"

FetchJson = Callable[[str, float], Mapping[str, Any]]
FetchText = Callable[[str, float], str]


class SourceCollectionError(RuntimeError):
    """Raised when live source collection cannot produce usable records."""

    def __init__(self, message: str, *, collection_report: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.collection_report = dict(collection_report or {})


@dataclass(frozen=True)
class AcademicSourceCollectionConfig:
    """Configuration for bounded live academic collection."""

    max_records: int = 24
    provider_timeout_seconds: float = 20.0
    since_year: int | None = None
    providers: tuple[str, ...] = ("semantic_scholar", "crossref", "openalex", "arxiv")
    user_agent: str = "MissionForge-DeepResearch/0.1"
    max_search_queries: int = 6
    max_concurrent_requests: int = 8

    def validate(self) -> None:
        if self.max_records < 1:
            raise ContractValidationError("academic_source_collection.max_records must be positive")
        if self.provider_timeout_seconds <= 0:
            raise ContractValidationError("academic_source_collection.provider_timeout_seconds must be positive")
        if self.max_search_queries < 1:
            raise ContractValidationError("academic_source_collection.max_search_queries must be positive")
        if self.max_concurrent_requests < 1:
            raise ContractValidationError("academic_source_collection.max_concurrent_requests must be positive")
        if self.since_year is not None and (self.since_year < 1900 or self.since_year > 2200):
            raise ContractValidationError("academic_source_collection.since_year is out of range")
        unknown = sorted(set(self.providers) - {"semantic_scholar", "crossref", "openalex", "arxiv"})
        if unknown:
            raise ContractValidationError(f"academic_source_collection.providers contains unknown providers: {unknown}")
        require_non_empty_str(self.user_agent, "academic_source_collection.user_agent")


@dataclass(frozen=True)
class AcademicSourceCollectionResult:
    """Refs and payloads produced by live academic source collection."""

    source_packet: dict[str, Any]
    source_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    collection_report: dict[str, Any] = field(default_factory=dict)
    search_intent: AcademicSearchIntent | None = None


def collect_live_academic_sources(
    request: AcademicResearchRequest,
    *,
    config: AcademicSourceCollectionConfig | None = None,
    search_intent: AcademicSearchIntent | None = None,
    fetch_json: FetchJson | None = None,
    fetch_text: FetchText | None = None,
) -> AcademicSourceCollectionResult:
    """Collect live academic source records for a research request."""

    request.validate()
    cfg = config or AcademicSourceCollectionConfig()
    cfg.validate()
    effective_intent = search_intent or AcademicSearchIntent.from_queries(
        request,
        [request.topic],
        created_by="external",
        notes=["No search intent was supplied; the collector used the original topic only."],
    )
    effective_intent.validate_for_request(request)
    queries = list(effective_intent.queries[: cfg.max_search_queries])
    json_fetcher = fetch_json or _fetch_json
    text_fetcher = fetch_text or _fetch_text
    retrieved_at = datetime.now(timezone.utc).isoformat()
    candidates: list[dict[str, Any]] = []
    provider_reports: list[dict[str, Any]] = []
    collection_tasks = [(query, provider) for query in queries for provider in cfg.providers]

    def collect_task(query: str, provider: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            if provider == "openalex":
                provider_candidates = _collect_openalex(query, cfg, json_fetcher)
            elif provider == "semantic_scholar":
                provider_candidates = _collect_semantic_scholar(query, cfg, json_fetcher)
            elif provider == "crossref":
                provider_candidates = _collect_crossref(query, cfg, json_fetcher)
            elif provider == "arxiv":
                provider_candidates = _collect_arxiv(query, cfg, text_fetcher)
            else:
                raise ContractValidationError(f"unsupported academic source provider: {provider}")
            tagged_candidates = [{**candidate, "query": query} for candidate in provider_candidates]
            return tagged_candidates, (
                {
                    "provider": provider,
                    "query": query,
                    "status": "completed",
                    "candidate_count": len(provider_candidates),
                }
            )
        except Exception as exc:
            return [], (
                {
                    "provider": provider,
                    "query": query,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:300],
                }
            )

    if collection_tasks:
        with ThreadPoolExecutor(max_workers=min(len(collection_tasks), cfg.max_concurrent_requests)) as executor:
            futures = [executor.submit(collect_task, query, provider) for query, provider in collection_tasks]
            for future in futures:
                provider_candidates, report = future.result()
                candidates.extend(provider_candidates)
                provider_reports.append(report)

    selected = _dedupe_candidates(candidates)[: cfg.max_records]
    if not selected:
        raise SourceCollectionError(
            "live academic source collection produced no source records",
            collection_report=_collection_report_payload(
                request=request,
                mode="live",
                query=request.topic,
                search_intent=effective_intent,
                search_intent_supplied=search_intent is not None,
                config=cfg,
                retrieved_at=retrieved_at,
                provider_reports=provider_reports,
                candidate_count=len(candidates),
                source_record_refs=[],
            ),
        )

    source_records: list[dict[str, Any]] = []
    source_payloads: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(selected, start=1):
        source_id = f"S{index:03d}"
        source_ref = f"sources/live/{source_id}.json"
        record = _source_record_from_candidate(
            source_id=source_id,
            source_ref=source_ref,
            candidate=candidate,
            accessed_at=retrieved_at,
        )
        source_records.append(record)
        source_payloads[source_ref] = {
            "schema_version": "missionforge_deepresearch.live_source_record.v1",
            "source_id": source_id,
            "request_id": request.request_id,
            "retrieved_at": retrieved_at,
            "query": candidate.get("query", request.topic),
            "provider": candidate["provider"],
            "source_record": record,
            "raw_provider_payload": candidate.get("raw_provider_payload", {}),
        }

    source_packet = {
        "schema_version": "missionforge_deepresearch.source_packet.v1",
        "request_id": request.request_id,
        "mode": "live",
        "query": request.topic,
        "search_intent_ref": SEARCH_INTENT_REF,
        "search_queries": queries,
        "retrieved_at": retrieved_at,
        "previous_run_refs": list(request.previous_run_refs),
        "collection_policy": {
            "providers": list(cfg.providers),
            "max_records": cfg.max_records,
            "since_year": cfg.since_year,
            "max_search_queries": cfg.max_search_queries,
            "query_expansion": "search_intent" if search_intent is not None else "none",
            "ranking_authority": "provider_order_then_exact_deduplication",
        },
        "source_records": source_records,
        "limitations": [
            "Live collection is bounded by public index coverage and provider availability.",
            "Collectors execute declared search intent queries; they do not add domain-specific fallback terms.",
            "The researcher must report gaps instead of inventing missing evidence.",
        ],
    }
    collection_report = _collection_report_payload(
        request=request,
        mode="live",
        query=request.topic,
        search_intent=effective_intent,
        search_intent_supplied=search_intent is not None,
        config=cfg,
        retrieved_at=retrieved_at,
        provider_reports=provider_reports,
        candidate_count=len(candidates),
        source_record_refs=[record["source_ref"] for record in source_records],
    )
    return AcademicSourceCollectionResult(
        source_packet=source_packet,
        source_payloads={SEARCH_INTENT_REF: effective_intent.to_dict(), **source_payloads},
        collection_report=collection_report,
        search_intent=effective_intent,
    )


def fixture_source_collection_report(request: AcademicResearchRequest) -> dict[str, Any]:
    """Return a refs-first diagnostic report for fixture source mode."""

    request.validate()
    return {
        "schema_version": "missionforge_deepresearch.source_collection_report.v1",
        "request_id": request.request_id,
        "mode": "fixture",
        "query": request.topic,
        "search_intent_ref": SEARCH_INTENT_REF,
        "provider_reports": [],
        "candidate_count": 3,
        "selected_count": 3,
        "source_packet_ref": "sources/source_packet.json",
        "source_record_refs": [
            "sources/fixtures/compiler_autotuning_seed.json",
            "sources/fixtures/kernel_generation_seed.json",
            "sources/fixtures/harness_engineering_seed.json",
        ],
    }


def _collection_report_payload(
    *,
    request: AcademicResearchRequest,
    mode: str,
    query: str,
    search_intent: AcademicSearchIntent,
    search_intent_supplied: bool,
    config: AcademicSourceCollectionConfig,
    retrieved_at: str,
    provider_reports: list[dict[str, Any]],
    candidate_count: int,
    source_record_refs: list[str],
) -> dict[str, Any]:
    queries = list(search_intent.queries[: config.max_search_queries])
    return {
        "schema_version": "missionforge_deepresearch.source_collection_report.v1",
        "request_id": request.request_id,
        "mode": mode,
        "query": query,
        "search_intent_ref": SEARCH_INTENT_REF,
        "search_intent_created_by": search_intent.created_by,
        "search_queries": queries,
        "search_query_count": len(queries),
        "search_query_limit": config.max_search_queries,
        "retrieved_at": retrieved_at,
        "provider_reports": provider_reports,
        "candidate_count": candidate_count,
        "selected_count": len(source_record_refs),
        "source_packet_ref": "sources/source_packet.json",
        "source_record_refs": list(source_record_refs),
        "collection_policy": {
            "providers": list(config.providers),
            "max_records": config.max_records,
            "since_year": config.since_year,
            "max_search_queries": config.max_search_queries,
            "query_expansion": "search_intent" if search_intent_supplied else "none",
        },
    }


def _collect_openalex(
    query: str,
    cfg: AcademicSourceCollectionConfig,
    fetch_json: FetchJson,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "search": query,
        "per-page": str(min(max(cfg.max_records, 1), 50)),
        "sort": "relevance_score:desc",
    }
    if cfg.since_year is not None:
        params["filter"] = f"from_publication_date:{cfg.since_year}-01-01"
    url = "https://api.openalex.org/works?" + urlencode(params)
    payload = require_mapping(fetch_json(url, cfg.provider_timeout_seconds), "openalex_response")
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise SourceCollectionError("OpenAlex response results must be a list")
    candidates: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        title = _first_text(item.get("display_name"), item.get("title"))
        if not title:
            continue
        primary_location = item.get("primary_location") if isinstance(item.get("primary_location"), Mapping) else {}
        source = primary_location.get("source") if isinstance(primary_location.get("source"), Mapping) else {}
        open_access = item.get("open_access") if isinstance(item.get("open_access"), Mapping) else {}
        candidates.append(
            {
                "provider": "openalex",
                "source_type": "academic_index_work",
                "title": title,
                "url": _first_text(
                    item.get("doi"),
                    item.get("id"),
                    primary_location.get("landing_page_url"),
                    open_access.get("oa_url"),
                ),
                "doi": _normalize_doi(item.get("doi")),
                "publication_year": _optional_int(item.get("publication_year")),
                "published": _first_text(item.get("publication_date")),
                "authors": _openalex_authors(item.get("authorships")),
                "venue": _first_text(source.get("display_name"), source.get("host_organization_name")),
                "citation_count": _optional_int(item.get("cited_by_count")),
                "abstract": _truncate(_openalex_abstract(item.get("abstract_inverted_index")), 5000),
                "raw_provider_payload": item,
            }
        )
    return candidates


def _collect_semantic_scholar(
    query: str,
    cfg: AcademicSourceCollectionConfig,
    fetch_json: FetchJson,
) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "fields": "title,year,authors,venue,citationCount,abstract,url,externalIds,publicationDate",
        "limit": str(min(max(cfg.max_records, 1), 100)),
    }
    if cfg.since_year is not None:
        params["year"] = f"{cfg.since_year}-"
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urlencode(params)
    payload = require_mapping(fetch_json(url, cfg.provider_timeout_seconds), "semantic_scholar_response")
    results = payload.get("data", [])
    if not isinstance(results, list):
        raise SourceCollectionError("Semantic Scholar response data must be a list")
    candidates: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        title = _first_text(item.get("title"))
        if not title:
            continue
        external_ids = item.get("externalIds") if isinstance(item.get("externalIds"), Mapping) else {}
        candidates.append(
            {
                "provider": "semantic_scholar",
                "source_type": "academic_index_work",
                "title": title,
                "url": _first_text(item.get("url")),
                "doi": _normalize_doi(external_ids.get("DOI")),
                "publication_year": _optional_int(item.get("year")),
                "published": _first_text(item.get("publicationDate")),
                "authors": _semantic_scholar_authors(item.get("authors")),
                "venue": _first_text(item.get("venue")),
                "citation_count": _optional_int(item.get("citationCount")),
                "abstract": _truncate(_first_text(item.get("abstract")), 5000),
                "raw_provider_payload": item,
            }
        )
    return candidates


def _collect_crossref(
    query: str,
    cfg: AcademicSourceCollectionConfig,
    fetch_json: FetchJson,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "query.bibliographic": query,
        "rows": str(min(max(cfg.max_records, 1), 100)),
        "sort": "relevance",
        "order": "desc",
    }
    if cfg.since_year is not None:
        params["filter"] = f"from-pub-date:{cfg.since_year}-01-01"
    url = "https://api.crossref.org/works?" + urlencode(params)
    payload = require_mapping(fetch_json(url, cfg.provider_timeout_seconds), "crossref_response")
    message = payload.get("message")
    if not isinstance(message, Mapping):
        raise SourceCollectionError("Crossref response message must be an object")
    items = message.get("items", [])
    if not isinstance(items, list):
        raise SourceCollectionError("Crossref response items must be a list")
    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        title = _first_text_from_list(item.get("title"))
        if not title:
            continue
        year, published = _crossref_publication_date(item)
        candidates.append(
            {
                "provider": "crossref",
                "source_type": "academic_index_work",
                "title": title,
                "url": _first_text(item.get("URL")),
                "doi": _normalize_doi(item.get("DOI")),
                "publication_year": year,
                "published": published,
                "authors": _crossref_authors(item.get("author")),
                "venue": _first_text_from_list(item.get("container-title")),
                "citation_count": _optional_int(item.get("is-referenced-by-count")),
                "abstract": _truncate(_strip_markup(_first_text(item.get("abstract"))), 5000),
                "raw_provider_payload": item,
            }
        )
    return candidates


def _collect_arxiv(
    query: str,
    cfg: AcademicSourceCollectionConfig,
    fetch_text: FetchText,
) -> list[dict[str, Any]]:
    params = {
        "search_query": _arxiv_query(query),
        "start": "0",
        "max_results": str(min(max(cfg.max_records, 1), 50)),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = "https://export.arxiv.org/api/query?" + urlencode(params)
    xml_text = fetch_text(url, cfg.provider_timeout_seconds)
    root = ElementTree.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    candidates: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        title = _xml_text(entry, "atom:title", ns)
        published = _xml_text(entry, "atom:published", ns)
        if cfg.since_year is not None and published[:4].isdigit() and int(published[:4]) < cfg.since_year:
            continue
        arxiv_id = _xml_text(entry, "atom:id", ns)
        authors = [
            _xml_text(author, "atom:name", ns)
            for author in entry.findall("atom:author", ns)
            if _xml_text(author, "atom:name", ns)
        ]
        doi = _xml_text(entry, "arxiv:doi", ns)
        categories = [
            category.attrib.get("term", "")
            for category in entry.findall("atom:category", ns)
            if category.attrib.get("term")
        ]
        candidates.append(
            {
                "provider": "arxiv",
                "source_type": "preprint_index_record",
                "title": _clean_space(title),
                "url": arxiv_id,
                "doi": _normalize_doi(doi),
                "publication_year": int(published[:4]) if published[:4].isdigit() else None,
                "published": published,
                "authors": authors[:12],
                "venue": "arXiv",
                "citation_count": None,
                "abstract": _truncate(_clean_space(_xml_text(entry, "atom:summary", ns)), 5000),
                "raw_provider_payload": {
                    "id": arxiv_id,
                    "title": title,
                    "published": published,
                    "updated": _xml_text(entry, "atom:updated", ns),
                    "authors": authors,
                    "doi": doi,
                    "categories": categories,
                    "summary": _xml_text(entry, "atom:summary", ns),
                },
            }
        )
    return [candidate for candidate in candidates if candidate["title"]]


def _source_record_from_candidate(
    *,
    source_id: str,
    source_ref: str,
    candidate: Mapping[str, Any],
    accessed_at: str,
) -> dict[str, Any]:
    publication_year = candidate.get("publication_year")
    return {
        "source_id": source_id,
        "title": require_non_empty_str(candidate.get("title"), "source_candidate.title"),
        "source_type": require_non_empty_str(candidate.get("source_type"), "source_candidate.source_type"),
        "source_ref": source_ref,
        "provider": require_non_empty_str(candidate.get("provider"), "source_candidate.provider"),
        "query": _first_text(candidate.get("query")),
        "url": _first_text(candidate.get("url")),
        "doi": _first_text(candidate.get("doi")),
        "year": publication_year,
        "publication_year": publication_year,
        "published": _first_text(candidate.get("published")),
        "authors": list(candidate.get("authors", []))[:12] if isinstance(candidate.get("authors"), list) else [],
        "venue": _first_text(candidate.get("venue")),
        "citation_count": candidate.get("citation_count"),
        "abstract": _first_text(candidate.get("abstract")),
        "accessed_at": accessed_at,
        "evidence_note": _source_evidence_note(candidate),
        "evidence_strength": _source_evidence_strength(candidate),
    }


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        key = _dedupe_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
    return selected


def _dedupe_key(candidate: Mapping[str, Any]) -> str:
    doi = _normalize_doi(candidate.get("doi"))
    if doi:
        return f"doi:{doi}"
    url = _first_text(candidate.get("url")).lower()
    if "arxiv.org/abs/" in url:
        return "arxiv:" + url.rsplit("/", 1)[-1]
    title = _clean_space(_first_text(candidate.get("title"))).lower()
    return "title:" + title if title else ""


def _fetch_json(url: str, timeout: float) -> Mapping[str, Any]:
    request = Request(url, headers={"User-Agent": "MissionForge-DeepResearch/0.1"})
    with urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, Mapping):
        raise SourceCollectionError("JSON response must be an object")
    return data


def _fetch_text(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": "MissionForge-DeepResearch/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _openalex_authors(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for item in value[:12]:
        if not isinstance(item, Mapping):
            continue
        author = item.get("author")
        if isinstance(author, Mapping):
            name = _first_text(author.get("display_name"))
            if name:
                authors.append(name)
    return authors


def _semantic_scholar_authors(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for item in value[:12]:
        if not isinstance(item, Mapping):
            continue
        name = _first_text(item.get("name"))
        if name:
            authors.append(name)
    return authors


def _crossref_authors(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for item in value[:12]:
        if not isinstance(item, Mapping):
            continue
        given = _first_text(item.get("given"))
        family = _first_text(item.get("family"))
        name = _clean_space(f"{given} {family}") if given or family else _first_text(item.get("name"))
        if name:
            authors.append(name)
    return authors


def _crossref_publication_date(item: Mapping[str, Any]) -> tuple[int | None, str]:
    for key in ("published-print", "published-online", "published", "issued"):
        value = item.get(key)
        if not isinstance(value, Mapping):
            continue
        date_parts = value.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts:
            continue
        first = date_parts[0]
        if not isinstance(first, list) or not first:
            continue
        parts = [part for part in first if isinstance(part, int)]
        if not parts:
            continue
        year = parts[0]
        padded = [str(year), *(f"{part:02d}" for part in parts[1:3])]
        return year, "-".join(padded)
    return None, ""


def _arxiv_query(topic: str) -> str:
    terms = [term for term in re.findall(r"[A-Za-z0-9_+-]+", topic) if term]
    if not terms:
        return f"all:{topic}"
    return " AND ".join(f"all:{term}" for term in terms[:12])


def _openalex_abstract(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned.append((position, word))
    return " ".join(word for _position, word in sorted(positioned))


def _xml_text(element: ElementTree.Element, path: str, ns: Mapping[str, str]) -> str:
    child = element.find(path, ns)
    return child.text.strip() if child is not None and child.text else ""


def _normalize_doi(value: Any) -> str:
    text = _first_text(value).strip().lower()
    if not text:
        return ""
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    return text


def _first_text_from_list(value: Any) -> str:
    if isinstance(value, list):
        return _first_text(*value)
    return _first_text(value)


def _strip_markup(value: str) -> str:
    return _clean_space(re.sub(r"<[^>]+>", " ", value))


def _optional_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return _clean_space(value)
    return ""


def _clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _truncate(value: str, limit: int) -> str:
    text = _clean_space(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _source_evidence_note(candidate: Mapping[str, Any]) -> str:
    provider = _first_text(candidate.get("provider")) or "unknown provider"
    source_type = _first_text(candidate.get("source_type")) or "source"
    title = _first_text(candidate.get("title")) or "untitled source"
    return f"{source_type} discovered through {provider}: {title}"


def _source_evidence_strength(candidate: Mapping[str, Any]) -> str:
    source_type = _first_text(candidate.get("source_type")).lower()
    provider = _first_text(candidate.get("provider")).lower()
    if "official" in source_type or provider in {"openalex", "semantic_scholar", "crossref"}:
        return "index_record"
    if "preprint" in source_type or provider == "arxiv":
        return "preprint_index_record"
    return "source_record"
