"""Live tool health checks for DeepResearch source acquisition."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from missionforge.contracts import require_mapping

from .compiler import _live_extension_grants
from .product_contract import AcademicResearchRequest
from .search_intent import AcademicSearchIntent, SEARCH_INTENT_REF
from .source_collector import AcademicSourceCollectionConfig, SourceCollectionError, collect_live_academic_sources
from .workspace import write_json_ref, write_text_ref


TOOL_HEALTHCHECK_SCHEMA_VERSION = "missionforge_deepresearch.tool_healthcheck.v1"
TOOL_HEALTHCHECK_RESULT_REF = "health/tool_healthcheck.json"
TOOL_HEALTHCHECK_REPORT_REF = "health/tool_healthcheck.md"
DEFAULT_ACADEMIC_PROVIDERS = ("semantic_scholar", "crossref", "openalex", "arxiv")
FetchJson = Callable[[str, float], Mapping[str, Any]]
FetchText = Callable[[str, float], str]


def run_deepresearch_tool_healthcheck(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    source_config: AcademicSourceCollectionConfig | None = None,
    academic_providers: tuple[str, ...] = DEFAULT_ACADEMIC_PROVIDERS,
    github_query: str | None = None,
    search_intent: AcademicSearchIntent | None = None,
    fetch_json: FetchJson | None = None,
    fetch_text: FetchText | None = None,
    fetch_github_json: FetchJson | None = None,
    fetch_npm_json: FetchJson | None = None,
) -> dict[str, Any]:
    """Run a thin live health check over source acquisition surfaces."""

    request.validate()
    cfg = source_config or AcademicSourceCollectionConfig(max_records=5, max_search_queries=2)
    cfg.validate()
    root = Path(workspace).resolve()
    run_ref = f"runs/{request.request_id}"
    run_root = root / run_ref
    run_root.mkdir(parents=True, exist_ok=True)
    effective_search_intent = search_intent or AcademicSearchIntent.from_queries(
        request,
        [request.topic],
        created_by="external",
        notes=["Healthcheck used the original topic because no search intent was supplied."],
    )
    effective_search_intent.validate_for_request(request)
    write_json_ref(run_root, SEARCH_INTENT_REF, effective_search_intent.to_dict())
    started_at = datetime.now(timezone.utc).isoformat()
    academic_records = [
        _check_academic_provider(
            request,
            provider=provider,
            config=cfg,
            search_intent=effective_search_intent,
            fetch_json=fetch_json,
            fetch_text=fetch_text,
        )
        for provider in academic_providers
    ]
    github_record = _check_github_search(
        github_query or request.topic,
        timeout=cfg.provider_timeout_seconds,
        fetch_json=fetch_github_json or _fetch_json,
    )
    npm_records = [
        _check_npm_package(
            grant.package,
            grant.version_spec,
            timeout=cfg.provider_timeout_seconds,
            fetch_json=fetch_npm_json or _fetch_json,
        )
        for grant in _live_extension_grants(request)
    ]
    scholar_record = {
        "surface": "google_scholar",
        "status": "unsupported",
        "reason": "Google Scholar has no stable official API; direct scraping is not treated as a product-grade hand.",
        "recommendation": "Prefer Semantic Scholar, OpenAlex, Crossref, arXiv, and publisher/arXiv URLs.",
    }
    result = {
        "schema_version": TOOL_HEALTHCHECK_SCHEMA_VERSION,
        "request_id": request.request_id,
        "topic": request.topic,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "search_intent_ref": f"{run_ref}/{SEARCH_INTENT_REF}",
        "search_queries": list(effective_search_intent.queries),
        "result_ref": f"{run_ref}/{TOOL_HEALTHCHECK_RESULT_REF}",
        "report_ref": f"{run_ref}/{TOOL_HEALTHCHECK_REPORT_REF}",
        "status": _overall_status([*academic_records, github_record, *npm_records, scholar_record]),
        "academic_provider_checks": academic_records,
        "github_check": github_record,
        "npm_extension_package_checks": npm_records,
        "scholar_check": scholar_record,
        "notes": [
            "This health check measures reachability and structured source-record production, not research quality.",
            "Provider failures are recorded as source-tool constraints, not silently repaired with domain-specific code.",
        ],
    }
    write_json_ref(run_root, TOOL_HEALTHCHECK_RESULT_REF, result)
    write_text_ref(run_root, TOOL_HEALTHCHECK_REPORT_REF, _healthcheck_markdown(result))
    return result


def _check_academic_provider(
    request: AcademicResearchRequest,
    *,
    provider: str,
    config: AcademicSourceCollectionConfig,
    search_intent: AcademicSearchIntent,
    fetch_json: FetchJson | None,
    fetch_text: FetchText | None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        provider_config = AcademicSourceCollectionConfig(
            max_records=min(config.max_records, 5),
            provider_timeout_seconds=config.provider_timeout_seconds,
            since_year=config.since_year,
            providers=(provider,),
            user_agent=config.user_agent,
            max_search_queries=config.max_search_queries,
            max_concurrent_requests=1,
        )
        result = collect_live_academic_sources(
            request,
            config=provider_config,
            search_intent=search_intent,
            fetch_json=fetch_json,
            fetch_text=fetch_text,
        )
        records = result.source_packet.get("source_records", [])
        source_records = records if isinstance(records, list) else []
        provider_reports = result.collection_report.get("provider_reports", [])
        return {
            "surface": f"academic_provider:{provider}",
            "provider": provider,
            "status": "passed" if source_records else "failed",
            "duration_ms": _duration_ms(started),
            "selected_count": len(source_records),
            "candidate_count": result.collection_report.get("candidate_count", 0),
            "sample_titles": [
                str(record.get("title"))
                for record in source_records[:3]
                if isinstance(record, Mapping) and record.get("title")
            ],
            "provider_reports": provider_reports if isinstance(provider_reports, list) else [],
        }
    except Exception as exc:
        collection_report = exc.collection_report if isinstance(exc, SourceCollectionError) else {}
        provider_reports = (
            collection_report.get("provider_reports", [])
            if isinstance(collection_report, Mapping)
            else []
        )
        candidate_count = (
            collection_report.get("candidate_count", 0)
            if isinstance(collection_report, Mapping)
            else 0
        )
        return {
            "surface": f"academic_provider:{provider}",
            "provider": provider,
            "status": "failed",
            "duration_ms": _duration_ms(started),
            "error_type": type(exc).__name__,
            "message": str(exc)[:500],
            "selected_count": 0,
            "candidate_count": candidate_count,
            "provider_reports": provider_reports if isinstance(provider_reports, list) else [],
        }


def _check_github_search(query: str, *, timeout: float, fetch_json: FetchJson) -> dict[str, Any]:
    started = time.monotonic()
    try:
        payload = require_mapping(
            fetch_json(
                "https://api.github.com/search/repositories?"
                + urlencode({"q": query, "sort": "stars", "order": "desc", "per_page": "5"}),
                timeout,
            ),
            "github_search_response",
        )
        items = payload.get("items", [])
        repositories = items if isinstance(items, list) else []
        return {
            "surface": "github_public_search_api",
            "status": "passed" if repositories else "failed",
            "duration_ms": _duration_ms(started),
            "selected_count": len(repositories),
            "rate_limit_remaining": _first_text(payload.get("rate_limit_remaining")),
            "sample_repositories": [
                {
                    "full_name": str(item.get("full_name", "")),
                    "url": str(item.get("html_url", "")),
                    "stars": item.get("stargazers_count"),
                }
                for item in repositories[:3]
                if isinstance(item, Mapping)
            ],
        }
    except Exception as exc:
        return {
            "surface": "github_public_search_api",
            "status": "failed",
            "duration_ms": _duration_ms(started),
            "error_type": type(exc).__name__,
            "message": str(exc)[:500],
            "selected_count": 0,
        }


def _check_npm_package(package: str, version: str, *, timeout: float, fetch_json: FetchJson) -> dict[str, Any]:
    started = time.monotonic()
    package_name = package.split(":", 1)[1] if ":" in package else package
    url = f"https://registry.npmjs.org/{quote(package_name, safe='@')}/{quote(version, safe='')}"
    try:
        payload = require_mapping(fetch_json(url, timeout), "npm_registry_response")
        return {
            "surface": "npm_registry_package",
            "package": package,
            "version_spec": version,
            "status": "passed",
            "duration_ms": _duration_ms(started),
            "resolved_name": payload.get("name"),
            "resolved_version": payload.get("version"),
        }
    except Exception as exc:
        return {
            "surface": "npm_registry_package",
            "package": package,
            "version_spec": version,
            "status": "failed",
            "duration_ms": _duration_ms(started),
            "error_type": type(exc).__name__,
            "message": str(exc)[:500],
        }


def _fetch_json(url: str, timeout: float) -> Mapping[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "MissionForge-DeepResearch-Healthcheck/0.1",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _overall_status(records: list[Mapping[str, Any]]) -> str:
    if any(record.get("status") == "failed" for record in records):
        return "degraded"
    if any(record.get("status") == "unsupported" for record in records):
        return "degraded"
    return "passed"


def _healthcheck_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# DeepResearch Tool Healthcheck",
        "",
        f"- status: `{result.get('status')}`",
        f"- topic: {result.get('topic')}",
        f"- finished_at: {result.get('finished_at')}",
        f"- search_intent_ref: `{result.get('search_intent_ref')}`",
        "",
        "## Search Queries",
        "",
        *[
            f"- {query}"
            for query in result.get("search_queries", [])
            if isinstance(query, str)
        ],
        "",
        "## Academic Providers",
        "",
    ]
    for record in result.get("academic_provider_checks", []):
        if not isinstance(record, Mapping):
            continue
        lines.append(
            f"- {record.get('provider')}: `{record.get('status')}`; "
            f"selected={record.get('selected_count', 0)}; "
            f"duration_ms={record.get('duration_ms', 0)}"
        )
        if record.get("message"):
            lines.append(f"  - {record.get('error_type')}: {record.get('message')}")
        for provider_report in record.get("provider_reports", []):
            if not isinstance(provider_report, Mapping) or provider_report.get("status") != "failed":
                continue
            lines.append(
                f"  - query `{provider_report.get('query')}` failed: "
                f"{provider_report.get('error_type')}: {provider_report.get('message')}"
            )
    lines.extend(["", "## GitHub", ""])
    github = result.get("github_check", {})
    if isinstance(github, Mapping):
        lines.append(f"- status: `{github.get('status')}`; selected={github.get('selected_count', 0)}")
        for repo in github.get("sample_repositories", []):
            if isinstance(repo, Mapping):
                lines.append(f"  - {repo.get('full_name')}: {repo.get('url')}")
        if github.get("message"):
            lines.append(f"  - {github.get('error_type')}: {github.get('message')}")
    lines.extend(["", "## Pi Extension Packages", ""])
    for record in result.get("npm_extension_package_checks", []):
        if isinstance(record, Mapping):
            lines.append(f"- {record.get('package')}@{record.get('version_spec')}: `{record.get('status')}`")
            if record.get("message"):
                lines.append(f"  - {record.get('error_type')}: {record.get('message')}")
    scholar = result.get("scholar_check", {})
    lines.extend(["", "## Google Scholar", ""])
    if isinstance(scholar, Mapping):
        lines.append(f"- status: `{scholar.get('status')}`")
        lines.append(f"- reason: {scholar.get('reason')}")
        lines.append(f"- recommendation: {scholar.get('recommendation')}")
    lines.append("")
    return "\n".join(lines)


def _duration_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _first_text(value: Any) -> str:
    return value if isinstance(value, str) else ""
