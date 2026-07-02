"""Read-only DeepResearch project web console.

The web console is a presentation layer over existing project refs. It does
not write product truth, mutate lifecycle state, or reinterpret research
semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, TextIO
from urllib.parse import parse_qs, quote, urlparse

import missionforge as mf

from .frontdesk import (
    FRONTDESK_ASSISTANT_TURN_REF,
    FRONTDESK_CONTROL_REF,
    FRONTDESK_INITIAL_INPUT_REF,
    FRONTDESK_REQUIREMENTS_REF,
    run_deepresearch_frontdesk_turn,
)
from .kernel_v2 import (
    KERNEL_V2_ACCEPTANCE_GATE_REF,
    KERNEL_V2_CANONICAL_SOURCES_REF,
    KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF,
    KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
    KERNEL_V2_CITATION_REGISTRY_REF,
    KERNEL_V2_CLAIM_INDEX_REF,
    KERNEL_V2_CLAIM_INDEX_VALIDATION_REF,
    KERNEL_V2_CLAIM_SUPPORT_REVIEW_REF,
    KERNEL_V2_CLAIM_SUPPORT_REVIEW_VALIDATION_REF,
    KERNEL_V2_COVERAGE_REPORT_REF,
    KERNEL_V2_EVIDENCE_INDEX_REF,
    KERNEL_V2_FINAL_REPORT_REF,
    KERNEL_V2_INSIGHT_MAP_REF,
    KERNEL_V2_JUDGE_REPORT_REF,
    KERNEL_V2_PROVIDER_HITS_REF,
    KERNEL_V2_REPORT_HTML_REF,
    KERNEL_V2_RESEARCH_STATE_REF,
    KERNEL_V2_RESULT_REF,
    KERNEL_V2_REVISION_REQUEST_REF,
    KERNEL_V2_RUN_STATUS_REF,
    KERNEL_V2_SEARCH_PLAN_REF,
    KERNEL_V2_SOURCE_GAPS_REF,
    KERNEL_V2_SOURCE_GRAPH_REF,
    KERNEL_V2_SOURCE_PACKET_REF,
    KERNEL_V2_USAGE_SUMMARY_REF,
)
from .project_lifecycle import (
    PROJECT_LIFECYCLE_STATE_REF,
    PROJECT_MANIFEST_REF,
    PROJECT_RESUME_DIAGNOSTICS_REF,
    PROJECT_RUN_INDEX_REF,
)
from .product_contract import ResearchIntensity
from .workspace import resolve_workspace_ref


WEB_CONSOLE_SCHEMA_VERSION = "missionforge_deepresearch.web_console.project_snapshot.v1"
ARTIFACT_PREVIEW_MAX_CHARS = 60000
ARTIFACT_READ_MAX_BYTES = 2_000_000
WEB_POST_MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class WebConsoleResponse:
    """Pure response object used by the stdlib HTTP adapter."""

    status: int
    content_type: str
    body: str


@dataclass(frozen=True)
class WebFrontDeskConfig:
    """Server-owned FrontDesk execution settings for web messages."""

    adapter_factory: Callable[[], mf.PiWorkerCallAdapter]
    audience: str = "R&D team"
    language: str = "zh"
    research_intensity: ResearchIntensity | str = ResearchIntensity.STANDARD
    live_extension_mode: bool = False


def build_project_snapshot(workspace: str | Path, request_id: str) -> dict[str, Any]:
    """Build a read-only project snapshot from persisted refs."""

    workspace_root = Path(workspace).resolve()
    run_ref = _run_ref(request_id)
    run_root = resolve_workspace_ref(workspace_root, run_ref)
    manifest = _read_json_if_exists(run_root, PROJECT_MANIFEST_REF)
    lifecycle = _read_json_if_exists(run_root, PROJECT_LIFECYCLE_STATE_REF)
    run_index = _read_json_if_exists(run_root, PROJECT_RUN_INDEX_REF)
    resume_diagnostics = _read_json_if_exists(run_root, _resume_ref(lifecycle))
    run_status = _read_json_if_exists(run_root, _run_status_ref(lifecycle))
    coverage_report = _read_json_if_exists(run_root, KERNEL_V2_COVERAGE_REPORT_REF)
    source_packet = _read_json_if_exists(run_root, KERNEL_V2_SOURCE_PACKET_REF)
    canonical_sources = _read_json_if_exists(run_root, KERNEL_V2_CANONICAL_SOURCES_REF)
    citation_registry = _read_json_if_exists(run_root, KERNEL_V2_CITATION_REGISTRY_REF)
    claim_support_review = _read_json_if_exists(run_root, KERNEL_V2_CLAIM_SUPPORT_REVIEW_REF)
    acceptance_gate = _read_json_if_exists(run_root, KERNEL_V2_ACCEPTANCE_GATE_REF)
    judge_report = _read_json_if_exists(run_root, KERNEL_V2_JUDGE_REPORT_REF)
    usage_summary = _read_json_if_exists(run_root, KERNEL_V2_USAGE_SUMMARY_REF)
    report_ref = _preferred_report_ref(run_root, lifecycle, run_status)
    report_preview = _read_text_preview_if_exists(run_root, report_ref)
    artifacts = _artifact_entries(
        run_root,
        lifecycle=lifecycle,
        run_status=run_status,
        report_ref=report_ref,
    )
    return {
        "schema_version": WEB_CONSOLE_SCHEMA_VERSION,
        "request_id": request_id,
        "run_workspace_ref": run_ref,
        "project_exists": run_root.exists(),
        "project": {
            "manifest": manifest or {},
            "lifecycle": lifecycle or {},
            "run_index": _run_index_summary(run_index),
            "resume_diagnostics": resume_diagnostics or {},
        },
        "status_cards": _status_cards(
            lifecycle=lifecycle,
            run_status=run_status,
            coverage_report=coverage_report,
            resume_diagnostics=resume_diagnostics,
            claim_support_review=claim_support_review,
            acceptance_gate=acceptance_gate,
            judge_report=judge_report,
            usage_summary=usage_summary,
        ),
        "frontdesk": _frontdesk_summary(run_root, lifecycle),
        "frontdesk_dialogue": _frontdesk_dialogue(run_root),
        "source_summary": _source_summary(source_packet, canonical_sources, coverage_report),
        "sources": _source_rows(source_packet, canonical_sources),
        "citations": _citation_rows(citation_registry),
        "claim_support": _claim_support_summary(claim_support_review),
        "judge": _judge_summary(judge_report),
        "report_preview": {
            "ref": report_ref,
            "available": bool(report_preview),
            "markdown": report_preview,
            "truncated": len(report_preview) >= ARTIFACT_PREVIEW_MAX_CHARS,
        },
        "artifacts": artifacts,
    }


def read_project_artifact(
    workspace: str | Path,
    request_id: str,
    ref: str,
    *,
    max_bytes: int = ARTIFACT_READ_MAX_BYTES,
) -> dict[str, Any]:
    """Read one project artifact as a safe text preview."""

    workspace_root = Path(workspace).resolve()
    run_root = resolve_workspace_ref(workspace_root, _run_ref(request_id))
    safe_ref = mf.validate_ref(ref, "deepresearch_web.artifact_ref")
    path = resolve_workspace_ref(run_root, safe_ref)
    if not path.is_file():
        raise FileNotFoundError(safe_ref)
    byte_size = path.stat().st_size
    data = path.read_bytes()[:max_bytes]
    truncated = byte_size > max_bytes
    content = ""
    binary = False
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        binary = True
    if not binary and _looks_like_json_ref(safe_ref):
        content = _pretty_json_text(content)
    return {
        "ref": safe_ref,
        "byte_size": byte_size,
        "truncated": truncated,
        "binary": binary,
        "content": content,
        "content_type": _artifact_content_type(safe_ref, binary=binary),
    }


def render_project_dashboard(snapshot: Mapping[str, Any]) -> str:
    """Render the project snapshot as a self-contained HTML dashboard."""

    status_cards = _list(snapshot.get("status_cards"))
    artifacts = _list(snapshot.get("artifacts"))
    source_rows = _list(snapshot.get("sources"))[:100]
    citation_rows = _list(snapshot.get("citations"))[:100]
    frontdesk = _mapping(snapshot.get("frontdesk"))
    dialogue = _list(snapshot.get("frontdesk_dialogue"))[-30:]
    claim_support = _mapping(snapshot.get("claim_support"))
    judge = _mapping(snapshot.get("judge"))
    report_preview = _mapping(snapshot.get("report_preview"))
    source_summary = _mapping(snapshot.get("source_summary"))
    return _page(
        "DeepResearch Project",
        "\n".join(
            [
                _header(snapshot),
                _status_grid(status_cards),
                _frontdesk_chat_panel(frontdesk, dialogue),
                _two_column(
                    _frontdesk_panel(frontdesk),
                    _source_summary_panel(source_summary),
                ),
                _two_column(
                    _claim_support_panel(claim_support),
                    _judge_panel(judge),
                ),
                _artifact_panel(artifacts),
                _source_table(source_rows),
                _citation_table(citation_rows),
                _report_panel(report_preview),
            ]
        ),
    )


def render_artifact_page(artifact: Mapping[str, Any]) -> str:
    """Render one artifact as escaped text."""

    ref = _clean(artifact.get("ref"))
    content = _clean(artifact.get("content"))
    binary = artifact.get("binary") is True
    if binary:
        content = "Binary artifact preview omitted."
    if artifact.get("truncated") is True:
        content += "\n\n[preview truncated]"
    body = (
        '<section class="panel">'
        f"<h2>{_e(ref)}</h2>"
        f'<p class="muted">{_e(str(artifact.get("byte_size", 0)))} bytes</p>'
        f"<pre>{_e(content)}</pre>"
        "</section>"
    )
    return _page("DeepResearch Artifact", body)


def create_web_console_server(
    *,
    workspace: str | Path,
    request_id: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    frontdesk_config: WebFrontDeskConfig | None = None,
) -> ThreadingHTTPServer:
    """Create an HTTP server for one DeepResearch project.

    GET routes are read-only. POST FrontDesk routes only submit user messages
    through the configured FrontDesk PiWorker boundary.
    """

    workspace_root = Path(workspace).resolve()

    class WebConsoleHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            response = web_console_response(workspace=workspace_root, request_id=request_id, method="GET", path=self.path)
            self._write_response(response)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            body = self.rfile.read(_content_length(self.headers.get("Content-Length")))
            response = web_console_response(
                workspace=workspace_root,
                request_id=request_id,
                method="POST",
                path=self.path,
                body=body,
                frontdesk_config=frontdesk_config,
            )
            self._write_response(response)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _write_response(self, response: WebConsoleResponse) -> None:
            data = response.body.encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer((host, port), WebConsoleHandler)


def web_console_response(
    *,
    workspace: str | Path,
    request_id: str,
    path: str,
    method: str = "GET",
    body: bytes | str = b"",
    frontdesk_config: WebFrontDeskConfig | None = None,
) -> WebConsoleResponse:
    """Return the web-console response for one request path."""

    workspace_root = Path(workspace).resolve()
    method = method.upper()
    parsed = urlparse(path)
    if method == "GET" and parsed.path in {"/", "/index.html"}:
        snapshot = build_project_snapshot(workspace_root, request_id)
        return _html_response(200, render_project_dashboard(snapshot))
    if method == "GET" and parsed.path == "/api/project":
        snapshot = build_project_snapshot(workspace_root, request_id)
        return _json_response(200, snapshot)
    if method == "GET" and parsed.path in {"/artifact", "/api/artifact"}:
        ref = _single_query_value(parsed.query, "ref")
        if not ref:
            return _json_response(400, {"status": "error", "message": "missing ref"})
        try:
            artifact = read_project_artifact(workspace_root, request_id, ref)
        except (FileNotFoundError, mf.ContractValidationError, OSError) as exc:
            return _json_response(404, {"status": "error", "message": str(exc)})
        if parsed.path == "/api/artifact":
            return _json_response(200, artifact)
        return _html_response(200, render_artifact_page(artifact))
    if method == "POST" and parsed.path == "/api/frontdesk/message":
        if frontdesk_config is None:
            return _json_response(409, {"status": "error", "message": "frontdesk_not_configured"})
        return _frontdesk_message_response(
            workspace=workspace_root,
            request_id=request_id,
            body=body,
            config=frontdesk_config,
        )
    return _json_response(404, {"status": "error", "message": "not found"})


def serve_web_console(
    *,
    workspace: str | Path,
    request_id: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    frontdesk_config: WebFrontDeskConfig | None = None,
    output_stream: TextIO | None = None,
) -> int:
    """Serve the web console until interrupted."""

    stream = output_stream or sys.stderr
    server = create_web_console_server(
        workspace=workspace,
        request_id=request_id,
        host=host,
        port=port,
        frontdesk_config=frontdesk_config,
    )
    actual_host, actual_port = server.server_address[:2]
    stream.write(f"DeepResearch web console: http://{actual_host}:{actual_port}/\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


def _run_ref(request_id: str) -> str:
    if not isinstance(request_id, str) or not request_id.strip():
        raise mf.ContractValidationError("DeepResearch request_id is required")
    return mf.validate_ref(f"runs/{request_id.strip()}", "deepresearch_web.run_ref")


def _frontdesk_message_response(
    *,
    workspace: Path,
    request_id: str,
    body: bytes | str,
    config: WebFrontDeskConfig,
) -> WebConsoleResponse:
    try:
        payload = _json_body(body)
        message = _clean(payload.get("message"))
        initial_input = _clean(payload.get("initial_input"))
        if not message and not initial_input:
            return _json_response(400, {"status": "error", "message": "message_required"})
        run_root = resolve_workspace_ref(workspace, _run_ref(request_id))
        has_initial_input = _ref_is_file(run_root, FRONTDESK_INITIAL_INPUT_REF)
        result = run_deepresearch_frontdesk_turn(
            initial_input=initial_input or message if not has_initial_input else None,
            user_message=message or initial_input,
            request_id=request_id,
            workspace=workspace,
            adapter=config.adapter_factory(),
            audience=config.audience,
            language=config.language,
            research_intensity=config.research_intensity,
            live_extension_mode=config.live_extension_mode,
        )
        return _json_response(
            200,
            {
                "schema_version": "missionforge_deepresearch.web_console.frontdesk_message_result.v1",
                "status": result.status,
                "result": result.to_dict(),
                "snapshot": build_project_snapshot(workspace, request_id),
            },
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _json_response(400, {"status": "error", "message": "invalid_json_body"})
    except mf.ContractValidationError as exc:
        return _json_response(400, {"status": "error", "message": str(exc)})


def _json_body(body: bytes | str) -> dict[str, Any]:
    if isinstance(body, bytes):
        if len(body) > WEB_POST_MAX_BYTES:
            raise mf.ContractValidationError("web console request body is too large")
        text = body.decode("utf-8")
    else:
        if len(body.encode("utf-8")) > WEB_POST_MAX_BYTES:
            raise mf.ContractValidationError("web console request body is too large")
        text = body
    payload = json.loads(text or "{}")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _content_length(value: str | None) -> int:
    try:
        parsed = int(value or "0")
    except ValueError:
        return 0
    if parsed < 0:
        return 0
    return min(parsed, WEB_POST_MAX_BYTES)


def _read_json_if_exists(run_root: Path, ref: str) -> dict[str, Any] | None:
    if not ref:
        return None
    try:
        path = resolve_workspace_ref(run_root, ref)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, mf.ContractValidationError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def _read_text_preview_if_exists(run_root: Path, ref: str) -> str:
    if not ref:
        return ""
    try:
        path = resolve_workspace_ref(run_root, ref)
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")[:ARTIFACT_PREVIEW_MAX_CHARS]
    except (OSError, UnicodeDecodeError, mf.ContractValidationError):
        return ""


def _resume_ref(lifecycle: Mapping[str, Any] | None) -> str:
    value = _clean((lifecycle or {}).get("resume_diagnostics_ref"))
    return value or PROJECT_RESUME_DIAGNOSTICS_REF


def _run_status_ref(lifecycle: Mapping[str, Any] | None) -> str:
    value = _clean((lifecycle or {}).get("latest_run_status_ref"))
    return value or KERNEL_V2_RUN_STATUS_REF


def _preferred_report_ref(run_root: Path, lifecycle: Mapping[str, Any] | None, run_status: Mapping[str, Any] | None) -> str:
    candidates = [
        _clean((run_status or {}).get("citation_projected_report_ref")),
        KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
        _clean((lifecycle or {}).get("final_report_ref")),
        _clean((run_status or {}).get("final_report_ref")),
        KERNEL_V2_FINAL_REPORT_REF,
    ]
    for ref in candidates:
        if ref and _ref_is_file(run_root, ref):
            return ref
    return KERNEL_V2_FINAL_REPORT_REF


def _ref_is_file(run_root: Path, ref: str) -> bool:
    try:
        return resolve_workspace_ref(run_root, ref).is_file()
    except mf.ContractValidationError:
        return False


def _artifact_entries(
    run_root: Path,
    *,
    lifecycle: Mapping[str, Any] | None,
    run_status: Mapping[str, Any] | None,
    report_ref: str,
) -> list[dict[str, Any]]:
    specs = [
        ("Project Manifest", PROJECT_MANIFEST_REF, "project"),
        ("Lifecycle State", PROJECT_LIFECYCLE_STATE_REF, "project"),
        ("Run Index", PROJECT_RUN_INDEX_REF, "project"),
        ("Resume Diagnostics", _resume_ref(lifecycle), "project"),
        ("FrontDesk Requirements", _clean((lifecycle or {}).get("frontdesk_requirements_ref")) or FRONTDESK_REQUIREMENTS_REF, "frontdesk"),
        ("FrontDesk Control", _clean((lifecycle or {}).get("frontdesk_control_ref")) or FRONTDESK_CONTROL_REF, "frontdesk"),
        ("FrontDesk Assistant Turn", _clean((lifecycle or {}).get("frontdesk_assistant_turn_ref")) or FRONTDESK_ASSISTANT_TURN_REF, "frontdesk"),
        ("Search Plan", KERNEL_V2_SEARCH_PLAN_REF, "sources"),
        ("Provider Hits", KERNEL_V2_PROVIDER_HITS_REF, "sources"),
        ("Source Packet", KERNEL_V2_SOURCE_PACKET_REF, "sources"),
        ("Source Graph", KERNEL_V2_SOURCE_GRAPH_REF, "sources"),
        ("Canonical Sources", KERNEL_V2_CANONICAL_SOURCES_REF, "sources"),
        ("Coverage Report", KERNEL_V2_COVERAGE_REPORT_REF, "sources"),
        ("Research State", KERNEL_V2_RESEARCH_STATE_REF, "state"),
        ("Insight Map", KERNEL_V2_INSIGHT_MAP_REF, "analysis"),
        ("Evidence Index", KERNEL_V2_EVIDENCE_INDEX_REF, "reports"),
        ("Source Gaps", KERNEL_V2_SOURCE_GAPS_REF, "reports"),
        ("Final Report", report_ref, "reports"),
        ("HTML Export", KERNEL_V2_REPORT_HTML_REF, "reports"),
        ("Citation Registry", KERNEL_V2_CITATION_REGISTRY_REF, "citations"),
        ("Citation Validation", KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF, "citations"),
        ("Claim Index", KERNEL_V2_CLAIM_INDEX_REF, "claims"),
        ("Claim Index Validation", KERNEL_V2_CLAIM_INDEX_VALIDATION_REF, "claims"),
        ("Claim Support Review", KERNEL_V2_CLAIM_SUPPORT_REVIEW_REF, "reviews"),
        ("Claim Support Validation", KERNEL_V2_CLAIM_SUPPORT_REVIEW_VALIDATION_REF, "reviews"),
        ("Acceptance Gate", KERNEL_V2_ACCEPTANCE_GATE_REF, "state"),
        ("Judge Report", KERNEL_V2_JUDGE_REPORT_REF, "judge"),
        ("Revision Request", KERNEL_V2_REVISION_REQUEST_REF, "revisions"),
        ("Run Status", _run_status_ref(lifecycle), "state"),
        ("Usage Summary", KERNEL_V2_USAGE_SUMMARY_REF, "metrics"),
        ("Result Package", _clean((run_status or {}).get("result_ref")) or KERNEL_V2_RESULT_REF, "packages"),
    ]
    entries = []
    seen: set[str] = set()
    for label, ref, group in specs:
        if not ref or ref in seen:
            continue
        seen.add(ref)
        entries.append(_artifact_entry(run_root, label=label, ref=ref, group=group))
    return entries


def _artifact_entry(run_root: Path, *, label: str, ref: str, group: str) -> dict[str, Any]:
    try:
        safe_ref = mf.validate_ref(ref, "deepresearch_web.artifact_ref")
        path = resolve_workspace_ref(run_root, safe_ref)
        exists = path.is_file()
        byte_size = path.stat().st_size if exists else 0
    except (OSError, mf.ContractValidationError):
        safe_ref = ref
        exists = False
        byte_size = 0
    return {
        "label": label,
        "ref": safe_ref,
        "group": group,
        "exists": exists,
        "byte_size": byte_size,
    }


def _status_cards(
    *,
    lifecycle: Mapping[str, Any] | None,
    run_status: Mapping[str, Any] | None,
    coverage_report: Mapping[str, Any] | None,
    resume_diagnostics: Mapping[str, Any] | None,
    claim_support_review: Mapping[str, Any] | None,
    acceptance_gate: Mapping[str, Any] | None,
    judge_report: Mapping[str, Any] | None,
    usage_summary: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    source_count = _source_count_label(coverage_report)
    totals = _mapping((usage_summary or {}).get("totals"))
    return [
        _card("phase", _clean((lifecycle or {}).get("phase")) or "unknown", "Project lifecycle phase"),
        _card("active agent", _clean((lifecycle or {}).get("active_agent")) or "unknown", "Latest active role"),
        _card("run status", _clean((run_status or {}).get("status")) or "unknown", _clean((run_status or {}).get("failure_summary"))),
        _card("resume", _clean((resume_diagnostics or {}).get("status")) or "missing", "ContextPackage restore diagnostics"),
        _card("sources", source_count, _clean((coverage_report or {}).get("mechanical_coverage_status"))),
        _card("citations", _clean((run_status or {}).get("citation_projection_validation_status")) or "unknown", "Mechanical citation projection"),
        _card("claims", _clean((claim_support_review or {}).get("overall_status")) or _clean((run_status or {}).get("claim_support_review_status")) or "unknown", "Reviewer-authored claim support"),
        _card("acceptance gate", _clean((acceptance_gate or {}).get("status")) or _clean((run_status or {}).get("acceptance_gate_status")) or "unknown", "Mechanical acceptance consistency"),
        _card("judge", _clean((judge_report or {}).get("decision")) or "unknown", "Independent Judge decision"),
        _card("tokens", _format_int(totals.get("total_tokens")), "Total recorded tokens"),
    ]


def _card(label: str, value: str, detail: str) -> dict[str, str]:
    return {"label": label, "value": value or "unknown", "detail": detail or ""}


def _source_count_label(coverage_report: Mapping[str, Any] | None) -> str:
    if not coverage_report:
        return "0"
    count = coverage_report.get("source_record_count")
    target = coverage_report.get("target_source_count")
    if isinstance(count, int) and isinstance(target, int):
        return f"{count}/{target}"
    return _format_int(count)


def _frontdesk_summary(run_root: Path, lifecycle: Mapping[str, Any] | None) -> dict[str, Any]:
    assistant = _read_json_if_exists(
        run_root,
        _clean((lifecycle or {}).get("frontdesk_assistant_turn_ref")) or FRONTDESK_ASSISTANT_TURN_REF,
    )
    control = _read_json_if_exists(
        run_root,
        _clean((lifecycle or {}).get("frontdesk_control_ref")) or FRONTDESK_CONTROL_REF,
    )
    requirements_ref = _clean((lifecycle or {}).get("frontdesk_requirements_ref")) or FRONTDESK_REQUIREMENTS_REF
    return {
        "status": _clean((control or {}).get("status")) or _clean((control or {}).get("decision")) or _clean((lifecycle or {}).get("phase")),
        "message": _clean((assistant or {}).get("message")),
        "question_count": len(_list((assistant or {}).get("questions"))),
        "requirements_ref": requirements_ref if _ref_is_file(run_root, requirements_ref) else "",
    }


def _frontdesk_dialogue(run_root: Path) -> list[dict[str, str]]:
    dialogue_ref = "frontdesk/dialogue.jsonl"
    try:
        path = resolve_workspace_ref(run_root, dialogue_ref)
        if not path.is_file():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, Mapping):
                continue
            rows.append(
                {
                    "role": _clean(payload.get("role")) or "unknown",
                    "content": _clean(payload.get("content")),
                    "created_at": _clean(payload.get("created_at")),
                }
            )
        return rows
    except (OSError, json.JSONDecodeError, mf.ContractValidationError):
        return []


def _source_summary(
    source_packet: Mapping[str, Any] | None,
    canonical_sources: Mapping[str, Any] | None,
    coverage_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    records = _list((source_packet or {}).get("source_records"))
    canonical = _list((canonical_sources or {}).get("sources"))
    return {
        "source_records": len(records),
        "canonical_sources": len(canonical),
        "coverage_status": _clean((coverage_report or {}).get("mechanical_coverage_status")),
        "target_source_count": _format_int((coverage_report or {}).get("target_source_count")),
        "provider_record_counts": _mapping((coverage_report or {}).get("provider_record_counts")),
        "evidence_strength_counts": _mapping((coverage_report or {}).get("evidence_strength_counts")),
        "coverage_limits": _list((coverage_report or {}).get("coverage_limits")),
    }


def _source_rows(source_packet: Mapping[str, Any] | None, canonical_sources: Mapping[str, Any] | None) -> list[dict[str, str]]:
    canonical = _list((canonical_sources or {}).get("sources"))
    if canonical:
        return [_canonical_source_row(item) for item in canonical if isinstance(item, Mapping)]
    return [_source_packet_row(item) for item in _list((source_packet or {}).get("source_records")) if isinstance(item, Mapping)]


def _canonical_source_row(source: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source_id": _clean(source.get("source_id")),
        "title": _clean(source.get("title")),
        "year": _format_int(source.get("year")),
        "provider": ", ".join(_string_list(source.get("provider_provenance"))),
        "evidence_strength": _clean(source.get("evidence_strength")),
        "locator": _first_locator(source),
    }


def _source_packet_row(source: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source_id": _clean(source.get("source_id")),
        "title": _clean(source.get("title")),
        "year": _format_int(source.get("year")),
        "provider": _clean(source.get("provider")) or _clean(source.get("source_type")),
        "evidence_strength": _clean(source.get("evidence_strength")),
        "locator": _clean(source.get("locator")) or _clean(source.get("url")),
    }


def _citation_rows(citation_registry: Mapping[str, Any] | None) -> list[dict[str, str]]:
    rows = []
    for entry in _list((citation_registry or {}).get("entries")):
        if not isinstance(entry, Mapping):
            continue
        rows.append(
            {
                "number": _format_int(entry.get("citation_number")),
                "source_id": _clean(entry.get("source_id")),
                "primary_url": _clean(entry.get("primary_url")),
                "reference": _clean(entry.get("reference_markdown")),
            }
        )
    return rows


def _claim_support_summary(claim_support_review: Mapping[str, Any] | None) -> dict[str, Any]:
    reviews = _list((claim_support_review or {}).get("claim_reviews"))
    counts: dict[str, int] = {}
    for review in reviews:
        if not isinstance(review, Mapping):
            continue
        status = _clean(review.get("support_status")) or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return {
        "overall_status": _clean((claim_support_review or {}).get("overall_status")),
        "review_count": len(reviews),
        "support_status_counts": counts,
        "repair_directive": _clean((claim_support_review or {}).get("repair_directive")),
    }


def _judge_summary(judge_report: Mapping[str, Any] | None) -> dict[str, str]:
    return {
        "decision": _clean((judge_report or {}).get("decision")),
        "summary": _clean((judge_report or {}).get("summary")) or _clean((judge_report or {}).get("rationale")),
        "revision_reason": _clean((judge_report or {}).get("revision_reason")) or _clean((judge_report or {}).get("reason")),
    }


def _run_index_summary(run_index: Mapping[str, Any] | None) -> dict[str, Any]:
    runs = _list((run_index or {}).get("runs"))
    latest = runs[-1] if runs and isinstance(runs[-1], Mapping) else {}
    return {
        "run_count": len(runs),
        "latest": dict(latest) if isinstance(latest, Mapping) else {},
    }


def _first_locator(source: Mapping[str, Any]) -> str:
    locators = source.get("locators")
    if isinstance(locators, list):
        for locator in locators:
            if isinstance(locator, Mapping):
                value = _clean(locator.get("url"))
                if value:
                    return value
    return _clean(source.get("locator")) or _clean(source.get("url"))


def _artifact_content_type(ref: str, *, binary: bool) -> str:
    if binary:
        return "application/octet-stream"
    if _looks_like_json_ref(ref):
        return "application/json; charset=utf-8"
    return "text/plain; charset=utf-8"


def _looks_like_json_ref(ref: str) -> bool:
    return ref.endswith(".json") or ref.endswith(".jsonl")


def _pretty_json_text(content: str) -> str:
    if not content.strip():
        return content
    if "\n" in content.strip() and not content.lstrip().startswith("{"):
        rows = []
        for line in content.splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.dumps(json.loads(line), ensure_ascii=False, sort_keys=True, indent=2))
            except json.JSONDecodeError:
                return content
        return "\n".join(rows)
    try:
        return json.dumps(json.loads(content), ensure_ascii=False, sort_keys=True, indent=2)
    except json.JSONDecodeError:
        return content


def _header(snapshot: Mapping[str, Any]) -> str:
    project = _mapping(snapshot.get("project"))
    lifecycle = _mapping(project.get("lifecycle"))
    updated = _clean(lifecycle.get("updated_at"))
    generated = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return (
        '<header class="topbar">'
        "<div>"
        "<h1>DeepResearch Project</h1>"
        f'<p class="muted">{_e(_clean(snapshot.get("run_workspace_ref")))}</p>'
        "</div>"
        "<div class=\"meta\">"
        f"<span>request {_e(_clean(snapshot.get('request_id')))}</span>"
        f"<span>updated {_e(updated or 'unknown')}</span>"
        f"<span>view {_e(generated)}</span>"
        "</div>"
        "</header>"
    )


def _status_grid(cards: list[Any]) -> str:
    rows = []
    for item in cards:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            '<div class="status-cell">'
            f'<span class="label">{_e(_clean(item.get("label")))}</span>'
            f'<strong>{_e(_clean(item.get("value")))}</strong>'
            f'<span class="detail">{_e(_clean(item.get("detail")))}</span>'
            "</div>"
        )
    return '<section class="status-grid">' + "".join(rows) + "</section>"


def _two_column(left: str, right: str) -> str:
    return f'<div class="two-column">{left}{right}</div>'


def _frontdesk_panel(frontdesk: Mapping[str, Any]) -> str:
    requirements_ref = _clean(frontdesk.get("requirements_ref"))
    requirements = _artifact_link(requirements_ref, "requirements") if requirements_ref else ""
    return (
        '<section class="panel">'
        "<h2>FrontDesk</h2>"
        f'<dl>{_row("status", _clean(frontdesk.get("status")))}'
        f'{_row("questions", _format_int(frontdesk.get("question_count")))}'
        f'{_row("requirements", requirements, raw=True)}</dl>'
        f'<p class="message">{_e(_clean(frontdesk.get("message")))}</p>'
        "</section>"
    )


def _frontdesk_chat_panel(frontdesk: Mapping[str, Any], dialogue: list[Any]) -> str:
    rows = []
    for item in dialogue:
        if not isinstance(item, Mapping):
            continue
        role = _clean(item.get("role")) or "unknown"
        content = _clean(item.get("content"))
        if not content:
            continue
        rows.append(
            '<div class="chat-row">'
            f'<span class="chat-role">{_e(role)}</span>'
            f'<p>{_e(content)}</p>'
            "</div>"
        )
    if not rows:
        rows.append('<p class="muted">No FrontDesk dialogue yet.</p>')
    return (
        '<section class="panel chat-panel">'
        "<h2>FrontDesk Chat</h2>"
        f'<p class="muted">status: {_e(_clean(frontdesk.get("status")) or "unknown")}</p>'
        '<div class="chat-log">'
        f"{''.join(rows)}"
        "</div>"
        '<form id="frontdesk-form" class="chat-form">'
        '<textarea id="frontdesk-message" name="message" rows="4" placeholder="Send a FrontDesk message"></textarea>'
        '<button type="submit">Send</button>'
        "</form>"
        f"<script>{_CHAT_SCRIPT}</script>"
        "</section>"
    )


def _source_summary_panel(summary: Mapping[str, Any]) -> str:
    provider_counts = _compact_mapping(_mapping(summary.get("provider_record_counts")))
    evidence_counts = _compact_mapping(_mapping(summary.get("evidence_strength_counts")))
    limits = ", ".join(_clean(item) for item in _list(summary.get("coverage_limits")) if _clean(item))
    return (
        '<section class="panel">'
        "<h2>Sources</h2>"
        "<dl>"
        f'{_row("records", _format_int(summary.get("source_records")))}'
        f'{_row("canonical", _format_int(summary.get("canonical_sources")))}'
        f'{_row("target", _clean(summary.get("target_source_count")))}'
        f'{_row("coverage", _clean(summary.get("coverage_status")))}'
        f'{_row("providers", provider_counts)}'
        f'{_row("evidence", evidence_counts)}'
        f'{_row("limits", limits)}'
        "</dl>"
        "</section>"
    )


def _claim_support_panel(summary: Mapping[str, Any]) -> str:
    return (
        '<section class="panel">'
        "<h2>Claim Support</h2>"
        "<dl>"
        f'{_row("overall", _clean(summary.get("overall_status")))}'
        f'{_row("reviews", _format_int(summary.get("review_count")))}'
        f'{_row("statuses", _compact_mapping(_mapping(summary.get("support_status_counts"))))}'
        f'{_row("repair", _clean(summary.get("repair_directive")))}'
        "</dl>"
        "</section>"
    )


def _judge_panel(summary: Mapping[str, Any]) -> str:
    return (
        '<section class="panel">'
        "<h2>Judge</h2>"
        "<dl>"
        f'{_row("decision", _clean(summary.get("decision")))}'
        f'{_row("summary", _clean(summary.get("summary")))}'
        f'{_row("revision", _clean(summary.get("revision_reason")))}'
        "</dl>"
        "</section>"
    )


def _artifact_panel(artifacts: list[Any]) -> str:
    rows = []
    for item in artifacts:
        if not isinstance(item, Mapping):
            continue
        ref = _clean(item.get("ref"))
        exists = item.get("exists") is True
        rows.append(
            "<tr>"
            f"<td>{_e(_clean(item.get('group')))}</td>"
            f"<td>{_artifact_link(ref, _clean(item.get('label'))) if exists else _e(_clean(item.get('label')))}</td>"
            f"<td>{_e(ref)}</td>"
            f"<td>{'present' if exists else 'missing'}</td>"
            f"<td>{_e(_format_int(item.get('byte_size')))}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Artifacts</h2>"
        '<table><thead><tr><th>group</th><th>artifact</th><th>ref</th><th>state</th><th>bytes</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</section>"
    )


def _source_table(rows: list[Any]) -> str:
    body = []
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        locator = _clean(item.get("locator"))
        locator_html = f'<a href="{_e(locator)}" rel="noreferrer">{_e(locator)}</a>' if locator.startswith(("http://", "https://")) else _e(locator)
        body.append(
            "<tr>"
            f"<td>{_e(_clean(item.get('source_id')))}</td>"
            f"<td>{_e(_clean(item.get('title')))}</td>"
            f"<td>{_e(_clean(item.get('year')))}</td>"
            f"<td>{_e(_clean(item.get('provider')))}</td>"
            f"<td>{_e(_clean(item.get('evidence_strength')))}</td>"
            f"<td>{locator_html}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Source Table</h2>"
        '<table><thead><tr><th>id</th><th>title</th><th>year</th><th>provider</th><th>evidence</th><th>locator</th></tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table>"
        "</section>"
    )


def _citation_table(rows: list[Any]) -> str:
    body = []
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        url = _clean(item.get("primary_url"))
        url_html = f'<a href="{_e(url)}" rel="noreferrer">{_e(url)}</a>' if url.startswith(("http://", "https://")) else _e(url)
        body.append(
            "<tr>"
            f"<td>{_e(_clean(item.get('number')))}</td>"
            f"<td>{_e(_clean(item.get('source_id')))}</td>"
            f"<td>{url_html}</td>"
            f"<td>{_e(_clean(item.get('reference')))}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Citations</h2>"
        '<table><thead><tr><th>cite</th><th>source</th><th>url</th><th>reference</th></tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table>"
        "</section>"
    )


def _report_panel(report_preview: Mapping[str, Any]) -> str:
    ref = _clean(report_preview.get("ref"))
    markdown = _clean(report_preview.get("markdown")) or "No report artifact found."
    suffix = "\n\n[preview truncated]" if report_preview.get("truncated") is True else ""
    return (
        '<section class="panel report-panel">'
        "<h2>Report Preview</h2>"
        f'<p class="muted">{_artifact_link(ref, ref) if ref else ""}</p>'
        f"<pre>{_e(markdown + suffix)}</pre>"
        "</section>"
    )


def _row(label: str, value: str, *, raw: bool = False) -> str:
    rendered = value if raw else _e(value)
    return f"<dt>{_e(label)}</dt><dd>{rendered}</dd>"


def _artifact_link(ref: str, label: str) -> str:
    if not ref:
        return ""
    return f'<a href="/artifact?ref={quote(ref)}">{_e(label or ref)}</a>'


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title>"
        f"<style>{_CSS}</style>"
        "</head><body>"
        f"{body}"
        "</body></html>"
    )


def _single_query_value(query: str, key: str) -> str:
    values = parse_qs(query).get(key, [])
    return values[0] if values else ""


def _html_response(status: int, body: str) -> WebConsoleResponse:
    return WebConsoleResponse(status=status, content_type="text/html; charset=utf-8", body=body)


def _json_response(status: int, payload: Mapping[str, Any]) -> WebConsoleResponse:
    return WebConsoleResponse(
        status=status,
        content_type="application/json; charset=utf-8",
        body=json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
    )


def _compact_mapping(value: Mapping[str, Any]) -> str:
    parts = [f"{key}={value[key]}" for key in sorted(value)]
    return ", ".join(parts)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _format_int(value: Any) -> str:
    if isinstance(value, bool):
        return "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str) and value:
        return value
    return "0"


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _e(value: str) -> str:
    return html.escape(value, quote=True)


_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --ink: #20242a;
  --muted: #68717d;
  --line: #d7dde5;
  --panel: #ffffff;
  --accent: #216e5b;
  --warn: #9a5b13;
  --link: #1f5fbf;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
.topbar {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 32px 16px;
  border-bottom: 1px solid var(--line);
  background: #ffffff;
}
h1, h2 { margin: 0; font-weight: 650; letter-spacing: 0; }
h1 { font-size: 28px; }
h2 { font-size: 16px; margin-bottom: 14px; }
.muted, .detail { color: var(--muted); }
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  align-content: flex-start;
  color: var(--muted);
}
.meta span {
  border: 1px solid var(--line);
  padding: 4px 8px;
  background: #fdfefe;
}
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 1px;
  margin: 18px 32px;
  border: 1px solid var(--line);
  background: var(--line);
}
.status-cell {
  min-height: 96px;
  padding: 14px;
  background: var(--panel);
}
.status-cell .label {
  display: block;
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
}
.status-cell strong {
  display: block;
  margin-top: 4px;
  font-size: 18px;
  color: var(--accent);
  overflow-wrap: anywhere;
}
.status-cell .detail {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.two-column {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 18px;
  margin: 18px 32px;
}
.panel {
  margin: 18px 32px;
  padding: 18px;
  background: var(--panel);
  border: 1px solid var(--line);
}
.two-column .panel { margin: 0; }
dl {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  gap: 8px 14px;
  margin: 0;
}
dt { color: var(--muted); }
dd { margin: 0; overflow-wrap: anywhere; }
.message {
  margin: 14px 0 0;
  color: var(--ink);
}
.chat-panel { margin-top: 18px; }
.chat-log {
  display: grid;
  gap: 10px;
  max-height: 360px;
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--line);
  background: #fbfcfd;
}
.chat-row {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr);
  gap: 12px;
}
.chat-row p { margin: 0; overflow-wrap: anywhere; }
.chat-role {
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
}
.chat-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 96px;
  gap: 10px;
  margin-top: 12px;
}
textarea {
  width: 100%;
  min-height: 92px;
  resize: vertical;
  padding: 10px;
  border: 1px solid var(--line);
  background: #ffffff;
  color: var(--ink);
  font: inherit;
}
button {
  align-self: stretch;
  border: 1px solid #1b5a49;
  background: var(--accent);
  color: #ffffff;
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}
button:disabled {
  cursor: wait;
  opacity: 0.65;
}
table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
th, td {
  padding: 9px 8px;
  border-top: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th {
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}
pre {
  max-height: 560px;
  margin: 0;
  padding: 14px;
  overflow: auto;
  border: 1px solid var(--line);
  background: #fbfcfd;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: 13px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
}
.report-panel pre { max-height: 760px; }
@media (max-width: 760px) {
  .topbar, .two-column { display: block; }
  .topbar, .panel, .status-grid { margin-left: 12px; margin-right: 12px; padding-left: 14px; padding-right: 14px; }
  .topbar { margin: 0; padding-top: 18px; }
  .meta { justify-content: flex-start; margin-top: 12px; }
  .two-column { margin: 12px; }
  .two-column .panel { margin-bottom: 12px; }
  dl { grid-template-columns: 110px minmax(0, 1fr); }
  .chat-row { grid-template-columns: 1fr; }
  .chat-form { grid-template-columns: 1fr; }
  button { min-height: 44px; }
}
"""


_CHAT_SCRIPT = """
(() => {
  const form = document.getElementById("frontdesk-form");
  const textarea = document.getElementById("frontdesk-message");
  if (!form || !textarea) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = textarea.value.trim();
    if (!message) return;
    const button = form.querySelector("button");
    if (button) button.disabled = true;
    try {
      const response = await fetch("/api/frontdesk/message", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message})
      });
      const payload = await response.json();
      if (!response.ok) {
        alert(payload.message || "FrontDesk message failed.");
        return;
      }
      window.location.reload();
    } catch (error) {
      alert(String(error));
    } finally {
      if (button) button.disabled = false;
    }
  });
})();
"""
