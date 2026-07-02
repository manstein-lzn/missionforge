"""Read-only DeepResearch project web console.

The web console is a presentation layer over existing project refs. It does
not write product truth, mutate lifecycle state, or reinterpret research
semantics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
from pathlib import Path
import sys
from typing import Any, Mapping, TextIO
from urllib.parse import parse_qs, quote, urlparse

import missionforge as mf

from .attempt_outputs import CURRENT_OUTPUT_POINTER_REF, read_current_output_pointer
from .frontdesk import (
    FRONTDESK_ASSISTANT_TURN_REF,
    FRONTDESK_CONTROL_REF,
    FRONTDESK_DIALOGUE_REF,
    FRONTDESK_REQUIREMENTS_REF,
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
from .lifecycle_actions import (
    LATEST_LOCK_RECOVERY_REQUEST_REF,
    LATEST_RETRY_REQUEST_REF,
    LATEST_REVISE_REQUEST_REF,
    read_latest_lifecycle_actions,
)
from .project_lifecycle import (
    PROJECT_LIFECYCLE_STATE_REF,
    PROJECT_MANIFEST_REF,
    PROJECT_RESUME_DIAGNOSTICS_REF,
    PROJECT_RUN_INDEX_REF,
)
from .project_seeds import PROJECT_SEED_INPUTS_REF
from .research_attempts import ATTEMPT_INDEX_REF, read_attempt_index
from .research_requests import CONTRACT_REVISION_INDEX_REF, read_contract_revision_index
from .web_actions import (
    content_length,
    frontdesk_approve_response,
    frontdesk_message_response,
    lifecycle_action_response,
    research_attempt_start_response,
    research_revision_start_response,
    research_start_response,
)
from .web_common import WEB_POST_MAX_BYTES, WebConsoleResponse, WebFrontDeskConfig, WebKernelConfig, html_response, json_response
from .web_controls import runtime_control_response
from .web_seeds import WEB_SEED_PDF_POST_MAX_BYTES, seed_paper_response, seed_pdf_response, seed_snapshot
from .web_tasks import WEB_TASK_STATE_REF, read_web_task_state
from .web_timeline import PROGRESS_TIMELINE_REF, build_project_timeline, build_timeline_attempt_groups
from .workspace import resolve_workspace_ref


WEB_CONSOLE_SCHEMA_VERSION = "missionforge_deepresearch.web_console.project_snapshot.v1"
ARTIFACT_PREVIEW_MAX_CHARS = 60000
ARTIFACT_READ_MAX_BYTES = 2_000_000
_SENSITIVE_ARTIFACT_REFS = {
    PROJECT_SEED_INPUTS_REF,
    FRONTDESK_DIALOGUE_REF,
    mf.USER_EVENTS_REF,
}
_SENSITIVE_ARTIFACT_PREFIXES = (
    "context/",
    "inputs/seeds/",
    "project/lifecycle/action_text/",
    "sources/seed_pdfs/",
)


def build_project_snapshot(workspace: str | Path, request_id: str) -> dict[str, Any]:
    """Build a read-only project snapshot from persisted refs."""

    workspace_root = Path(workspace).resolve()
    run_ref = _run_ref(request_id)
    run_root = resolve_workspace_ref(workspace_root, run_ref)
    manifest = _read_json_if_exists(run_root, PROJECT_MANIFEST_REF)
    lifecycle = _read_json_if_exists(run_root, PROJECT_LIFECYCLE_STATE_REF)
    run_index = _read_json_if_exists(run_root, PROJECT_RUN_INDEX_REF)
    attempt_index = read_attempt_index(run_root)
    revision_index = read_contract_revision_index(run_root)
    current_outputs = read_current_output_pointer(run_root)
    resume_diagnostics = _read_json_if_exists(run_root, _resume_ref(lifecycle))
    run_status = _read_json_if_exists(run_root, _current_or_stable_ref(current_outputs, _run_status_ref(lifecycle)))
    coverage_report = _read_json_if_exists(run_root, _current_or_stable_ref(current_outputs, KERNEL_V2_COVERAGE_REPORT_REF))
    source_packet = _read_json_if_exists(run_root, _current_or_stable_ref(current_outputs, KERNEL_V2_SOURCE_PACKET_REF))
    canonical_sources = _read_json_if_exists(run_root, _current_or_stable_ref(current_outputs, KERNEL_V2_CANONICAL_SOURCES_REF))
    citation_registry = _read_json_if_exists(run_root, _current_or_stable_ref(current_outputs, KERNEL_V2_CITATION_REGISTRY_REF))
    claim_support_review = _read_json_if_exists(run_root, _current_or_stable_ref(current_outputs, KERNEL_V2_CLAIM_SUPPORT_REVIEW_REF))
    acceptance_gate = _read_json_if_exists(run_root, _current_or_stable_ref(current_outputs, KERNEL_V2_ACCEPTANCE_GATE_REF))
    judge_report = _read_json_if_exists(run_root, _current_or_stable_ref(current_outputs, KERNEL_V2_JUDGE_REPORT_REF))
    usage_summary = _read_json_if_exists(run_root, _current_or_stable_ref(current_outputs, KERNEL_V2_USAGE_SUMMARY_REF))
    web_task = read_web_task_state(run_root)
    lifecycle_actions = read_latest_lifecycle_actions(run_root)
    seeds = seed_snapshot(run_root)
    runtime_events = _runtime_event_rows(run_root)
    progress_timeline = build_project_timeline(run_root, lifecycle=lifecycle, run_status=run_status)
    progress_timeline_groups = build_timeline_attempt_groups(
        run_root,
        progress_timeline,
        current_outputs=current_outputs,
    )
    report_ref = _preferred_report_ref(run_root, lifecycle, run_status, current_outputs)
    report_preview = _read_text_preview_if_exists(run_root, report_ref)
    artifacts = _artifact_entries(
        run_root,
        lifecycle=lifecycle,
        run_status=run_status,
        report_ref=report_ref,
        current_outputs=current_outputs,
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
            "attempt_index": _attempt_index_summary(attempt_index),
            "revision_index": _revision_index_summary(revision_index),
            "current_outputs": _current_output_summary(current_outputs),
            "resume_diagnostics": resume_diagnostics or {},
        },
        "web_task": web_task,
        "lifecycle_actions": lifecycle_actions,
        "seeds": seeds,
        "runtime_events": runtime_events,
        "progress_timeline": progress_timeline,
        "progress_timeline_groups": progress_timeline_groups,
        "status_cards": _status_cards(
            lifecycle=lifecycle,
            run_status=run_status,
            coverage_report=coverage_report,
            resume_diagnostics=resume_diagnostics,
            claim_support_review=claim_support_review,
            acceptance_gate=acceptance_gate,
            judge_report=judge_report,
            usage_summary=usage_summary,
            web_task=web_task,
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
    policy = _artifact_access_policy(safe_ref)
    if policy["redacted"]:
        return {
            "ref": safe_ref,
            "byte_size": byte_size,
            "truncated": False,
            "binary": False,
            "content": "",
            "content_type": "text/plain; charset=utf-8",
            **policy,
        }
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
        **policy,
    }


def render_project_dashboard(snapshot: Mapping[str, Any]) -> str:
    """Render the project snapshot as a self-contained HTML dashboard."""

    status_cards = _list(snapshot.get("status_cards"))
    artifacts = _list(snapshot.get("artifacts"))
    source_rows = _list(snapshot.get("sources"))[:100]
    citation_rows = _list(snapshot.get("citations"))[:100]
    frontdesk = _mapping(snapshot.get("frontdesk"))
    dialogue = _list(snapshot.get("frontdesk_dialogue"))[-30:]
    web_task = _mapping(snapshot.get("web_task"))
    seeds = _mapping(snapshot.get("seeds"))
    runtime_events = _list(snapshot.get("runtime_events"))[-12:]
    progress_timeline = _list(snapshot.get("progress_timeline"))[-80:]
    progress_timeline_groups = _list(snapshot.get("progress_timeline_groups"))
    claim_support = _mapping(snapshot.get("claim_support"))
    judge = _mapping(snapshot.get("judge"))
    report_preview = _mapping(snapshot.get("report_preview"))
    source_summary = _mapping(snapshot.get("source_summary"))
    project = _mapping(snapshot.get("project"))
    return _page(
        "DeepResearch Project",
        "\n".join(
            [
                _header(snapshot),
                _status_grid(status_cards),
                _frontdesk_chat_panel(frontdesk, dialogue, web_task),
                _seed_input_panel(seeds),
                _runtime_controls_panel(
                    runtime_events,
                    _mapping(snapshot.get("lifecycle_actions")),
                    _mapping(project.get("attempt_index")),
                    _mapping(project.get("revision_index")),
                    _mapping(project.get("current_outputs")),
                ),
                _timeline_panel(progress_timeline, progress_timeline_groups),
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
    redacted = artifact.get("redacted") is True
    binary = artifact.get("binary") is True
    if redacted:
        content = (
            "Content preview restricted by DeepResearch artifact access policy.\n"
            f"Reason: {_clean(artifact.get('redaction_reason')) or 'sensitive artifact'}"
        )
    elif binary:
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
    kernel_config: WebKernelConfig | None = None,
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
            max_bytes = WEB_SEED_PDF_POST_MAX_BYTES if self.path.split("?", 1)[0] == "/api/seeds/pdfs" else WEB_POST_MAX_BYTES
            body = self.rfile.read(content_length(self.headers.get("Content-Length"), max_bytes=max_bytes))
            response = web_console_response(
                workspace=workspace_root,
                request_id=request_id,
                method="POST",
                path=self.path,
                body=body,
                frontdesk_config=frontdesk_config,
                kernel_config=kernel_config,
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
    kernel_config: WebKernelConfig | None = None,
) -> WebConsoleResponse:
    """Return the web-console response for one request path."""

    workspace_root = Path(workspace).resolve()
    method = method.upper()
    parsed = urlparse(path)
    if method == "GET" and parsed.path in {"/", "/index.html"}:
        snapshot = build_project_snapshot(workspace_root, request_id)
        return html_response(200, render_project_dashboard(snapshot))
    if method == "GET" and parsed.path == "/api/project":
        snapshot = build_project_snapshot(workspace_root, request_id)
        return json_response(200, snapshot)
    if method == "GET" and parsed.path in {"/artifact", "/api/artifact"}:
        ref = _single_query_value(parsed.query, "ref")
        if not ref:
            return json_response(400, {"status": "error", "message": "missing ref"})
        try:
            artifact = read_project_artifact(workspace_root, request_id, ref)
        except (FileNotFoundError, mf.ContractValidationError, OSError) as exc:
            return json_response(404, {"status": "error", "message": str(exc)})
        if parsed.path == "/api/artifact":
            return json_response(200, artifact)
        return html_response(200, render_artifact_page(artifact))
    if method == "POST" and parsed.path == "/api/frontdesk/message":
        if frontdesk_config is None:
            return json_response(409, {"status": "error", "message": "frontdesk_not_configured"})
        return frontdesk_message_response(
            workspace=workspace_root,
            request_id=request_id,
            body=body,
            config=frontdesk_config,
            snapshot_factory=build_project_snapshot,
        )
    if method == "POST" and parsed.path == "/api/frontdesk/approve":
        return frontdesk_approve_response(
            workspace=workspace_root,
            request_id=request_id,
            snapshot_factory=build_project_snapshot,
        )
    if method == "POST" and parsed.path == "/api/seeds/papers":
        return seed_paper_response(
            workspace=workspace_root,
            request_id=request_id,
            body=body,
            snapshot_factory=build_project_snapshot,
        )
    if method == "POST" and parsed.path == "/api/seeds/pdfs":
        return seed_pdf_response(
            workspace=workspace_root,
            request_id=request_id,
            body=body,
            snapshot_factory=build_project_snapshot,
        )
    if method == "POST" and parsed.path == "/api/research/start":
        if kernel_config is None:
            return json_response(409, {"status": "error", "message": "kernel_not_configured"})
        return research_start_response(
            workspace=workspace_root,
            request_id=request_id,
            config=kernel_config,
        )
    if method == "POST" and parsed.path == "/api/research/attempt/start":
        if kernel_config is None:
            return json_response(409, {"status": "error", "message": "kernel_not_configured"})
        return research_attempt_start_response(
            workspace=workspace_root,
            request_id=request_id,
            config=kernel_config,
        )
    if method == "POST" and parsed.path == "/api/research/revision/start":
        if kernel_config is None:
            return json_response(409, {"status": "error", "message": "kernel_not_configured"})
        return research_revision_start_response(
            workspace=workspace_root,
            request_id=request_id,
            config=kernel_config,
        )
    if method == "POST" and parsed.path == "/api/runtime/control":
        return runtime_control_response(
            workspace=workspace_root,
            request_id=request_id,
            body=body,
        )
    if method == "POST" and parsed.path == "/api/lifecycle/action":
        return lifecycle_action_response(
            workspace=workspace_root,
            request_id=request_id,
            body=body,
        )
    if method == "GET" and parsed.path == "/api/task":
        run_root = resolve_workspace_ref(workspace_root, _run_ref(request_id))
        return json_response(200, read_web_task_state(run_root))
    return json_response(404, {"status": "error", "message": "not found"})


def serve_web_console(
    *,
    workspace: str | Path,
    request_id: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    frontdesk_config: WebFrontDeskConfig | None = None,
    kernel_config: WebKernelConfig | None = None,
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
        kernel_config=kernel_config,
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


def _preferred_report_ref(
    run_root: Path,
    lifecycle: Mapping[str, Any] | None,
    run_status: Mapping[str, Any] | None,
    current_outputs: Mapping[str, Any] | None = None,
) -> str:
    if _current_outputs_active(current_outputs):
        candidates = [
            _current_output_ref(current_outputs, KERNEL_V2_CITATION_PROJECTED_REPORT_REF),
            _current_output_ref(current_outputs, KERNEL_V2_FINAL_REPORT_REF),
        ]
        for ref in candidates:
            if ref and _ref_is_file(run_root, ref):
                return ref
        return candidates[0] or candidates[1] or ""
    candidates = [
        _current_output_ref(current_outputs, KERNEL_V2_CITATION_PROJECTED_REPORT_REF),
        _current_output_ref(current_outputs, KERNEL_V2_FINAL_REPORT_REF),
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


def _current_or_stable_ref(current_outputs: Mapping[str, Any] | None, stable_ref: str) -> str:
    current_ref = _current_output_ref(current_outputs, stable_ref)
    if current_ref:
        return current_ref
    if _current_outputs_active(current_outputs):
        return ""
    return stable_ref


def _current_output_ref(current_outputs: Mapping[str, Any] | None, stable_ref: str) -> str:
    safe_stable_ref = _clean(stable_ref)
    for entry in _list((current_outputs or {}).get("entries")):
        if not isinstance(entry, Mapping):
            continue
        if _clean(entry.get("source_ref")) == safe_stable_ref:
            return _clean(entry.get("output_ref"))
    return ""


def _current_outputs_active(current_outputs: Mapping[str, Any] | None) -> bool:
    return bool(
        _clean((current_outputs or {}).get("status")) == "current"
        and _clean((current_outputs or {}).get("output_manifest_ref"))
    )


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
    current_outputs: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    specs = [
        ("Project Manifest", PROJECT_MANIFEST_REF, "project"),
        ("Lifecycle State", PROJECT_LIFECYCLE_STATE_REF, "project"),
        ("Run Index", PROJECT_RUN_INDEX_REF, "project"),
        ("Resume Diagnostics", _resume_ref(lifecycle), "project"),
        ("Lifecycle Actions", "project/lifecycle_actions.jsonl", "project"),
        ("Attempt Index", ATTEMPT_INDEX_REF, "project"),
        ("Revision Index", CONTRACT_REVISION_INDEX_REF, "project"),
        ("Current Output Pointer", CURRENT_OUTPUT_POINTER_REF, "project"),
        ("Seed Inputs", PROJECT_SEED_INPUTS_REF, "project"),
        (
            "Current Output Manifest",
            _clean((current_outputs or {}).get("output_manifest_ref")),
            "project",
        ),
        ("Progress Timeline", PROGRESS_TIMELINE_REF, "web"),
        ("Retry Request", LATEST_RETRY_REQUEST_REF, "project"),
        ("Revise Request", LATEST_REVISE_REQUEST_REF, "project"),
        ("Lock Recovery Request", LATEST_LOCK_RECOVERY_REQUEST_REF, "project"),
        ("FrontDesk Dialogue", FRONTDESK_DIALOGUE_REF, "frontdesk"),
        ("FrontDesk Requirements", _clean((lifecycle or {}).get("frontdesk_requirements_ref")) or FRONTDESK_REQUIREMENTS_REF, "frontdesk"),
        ("FrontDesk Control", _clean((lifecycle or {}).get("frontdesk_control_ref")) or FRONTDESK_CONTROL_REF, "frontdesk"),
        ("FrontDesk Assistant Turn", _clean((lifecycle or {}).get("frontdesk_assistant_turn_ref")) or FRONTDESK_ASSISTANT_TURN_REF, "frontdesk"),
        ("Search Plan", _current_or_stable_ref(current_outputs, KERNEL_V2_SEARCH_PLAN_REF), "sources"),
        ("Provider Hits", _current_or_stable_ref(current_outputs, KERNEL_V2_PROVIDER_HITS_REF), "sources"),
        ("Source Packet", _current_or_stable_ref(current_outputs, KERNEL_V2_SOURCE_PACKET_REF), "sources"),
        ("Source Graph", _current_or_stable_ref(current_outputs, KERNEL_V2_SOURCE_GRAPH_REF), "sources"),
        ("Canonical Sources", _current_or_stable_ref(current_outputs, KERNEL_V2_CANONICAL_SOURCES_REF), "sources"),
        ("Coverage Report", _current_or_stable_ref(current_outputs, KERNEL_V2_COVERAGE_REPORT_REF), "sources"),
        ("Research State", _current_or_stable_ref(current_outputs, KERNEL_V2_RESEARCH_STATE_REF), "state"),
        ("Insight Map", _current_or_stable_ref(current_outputs, KERNEL_V2_INSIGHT_MAP_REF), "analysis"),
        ("Evidence Index", _current_or_stable_ref(current_outputs, KERNEL_V2_EVIDENCE_INDEX_REF), "reports"),
        ("Source Gaps", _current_or_stable_ref(current_outputs, KERNEL_V2_SOURCE_GAPS_REF), "reports"),
        ("Final Report", report_ref, "reports"),
        ("HTML Export", _current_or_stable_ref(current_outputs, KERNEL_V2_REPORT_HTML_REF), "reports"),
        ("Citation Registry", _current_or_stable_ref(current_outputs, KERNEL_V2_CITATION_REGISTRY_REF), "citations"),
        ("Citation Validation", _current_or_stable_ref(current_outputs, KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF), "citations"),
        ("Claim Index", _current_or_stable_ref(current_outputs, KERNEL_V2_CLAIM_INDEX_REF), "claims"),
        ("Claim Index Validation", _current_or_stable_ref(current_outputs, KERNEL_V2_CLAIM_INDEX_VALIDATION_REF), "claims"),
        ("Claim Support Review", _current_or_stable_ref(current_outputs, KERNEL_V2_CLAIM_SUPPORT_REVIEW_REF), "reviews"),
        ("Claim Support Validation", _current_or_stable_ref(current_outputs, KERNEL_V2_CLAIM_SUPPORT_REVIEW_VALIDATION_REF), "reviews"),
        ("Acceptance Gate", _current_or_stable_ref(current_outputs, KERNEL_V2_ACCEPTANCE_GATE_REF), "state"),
        ("Judge Report", _current_or_stable_ref(current_outputs, KERNEL_V2_JUDGE_REPORT_REF), "judge"),
        ("Revision Request", KERNEL_V2_REVISION_REQUEST_REF, "revisions"),
        ("Run Status", _current_or_stable_ref(current_outputs, _run_status_ref(lifecycle)), "state"),
        ("Usage Summary", _current_or_stable_ref(current_outputs, KERNEL_V2_USAGE_SUMMARY_REF), "metrics"),
        ("Web Task State", WEB_TASK_STATE_REF, "web"),
        (
            "Result Package",
            _current_or_stable_ref(current_outputs, _clean((run_status or {}).get("result_ref")) or KERNEL_V2_RESULT_REF),
            "packages",
        ),
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
        **_artifact_access_policy(safe_ref),
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
    web_task: Mapping[str, Any] | None,
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
        _card("web task", _clean((web_task or {}).get("status")) or "idle", _clean((web_task or {}).get("task_kind"))),
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
    assistant_turn_ref = _clean((lifecycle or {}).get("frontdesk_assistant_turn_ref")) or FRONTDESK_ASSISTANT_TURN_REF
    control_ref = _clean((lifecycle or {}).get("frontdesk_control_ref")) or FRONTDESK_CONTROL_REF
    return {
        "status": _clean((control or {}).get("status")) or _clean((control or {}).get("decision")) or _clean((lifecycle or {}).get("phase")),
        "message": "Assistant turn recorded." if assistant else "",
        "question_count": len(_list((assistant or {}).get("questions"))),
        "requirements_ref": requirements_ref if _ref_is_file(run_root, requirements_ref) else "",
        "assistant_turn_ref": assistant_turn_ref if _ref_is_file(run_root, assistant_turn_ref) else "",
        "control_ref": control_ref if _ref_is_file(run_root, control_ref) else "",
        "dialogue_ref": FRONTDESK_DIALOGUE_REF if _ref_is_file(run_root, FRONTDESK_DIALOGUE_REF) else "",
    }


def _frontdesk_dialogue(run_root: Path) -> list[dict[str, str]]:
    dialogue_ref = "frontdesk/dialogue.jsonl"
    try:
        path = resolve_workspace_ref(run_root, dialogue_ref)
        if not path.is_file():
            return []
        rows = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, Mapping):
                continue
            rows.append(
                {
                    "turn_index": str(index),
                    "role": _clean(payload.get("role")) or "unknown",
                    "summary": "Dialogue turn recorded.",
                    "dialogue_ref": FRONTDESK_DIALOGUE_REF,
                    "created_at": _clean(payload.get("created_at")),
                }
            )
        return rows
    except (OSError, json.JSONDecodeError, mf.ContractValidationError):
        return []


def _runtime_event_rows(run_root: Path) -> list[dict[str, str]]:
    try:
        path = resolve_workspace_ref(run_root, mf.USER_EVENTS_REF)
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
                    "event_id": _clean(payload.get("event_id")),
                    "kind": _clean(payload.get("kind")),
                    "delivery": _clean(payload.get("delivery")),
                    "target": _clean(payload.get("target")),
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


def _attempt_index_summary(attempt_index: Mapping[str, Any] | None) -> dict[str, Any]:
    attempts = _list((attempt_index or {}).get("attempts"))
    latest = attempts[-1] if attempts and isinstance(attempts[-1], Mapping) else {}
    return {
        "attempt_count": len(attempts),
        "latest_attempt_ref": _clean((attempt_index or {}).get("latest_attempt_ref")),
        "latest": dict(latest) if isinstance(latest, Mapping) else {},
    }


def _revision_index_summary(revision_index: Mapping[str, Any] | None) -> dict[str, Any]:
    revisions = _list((revision_index or {}).get("revisions"))
    latest = revisions[-1] if revisions and isinstance(revisions[-1], Mapping) else {}
    return {
        "revision_count": len(revisions),
        "latest_revision_ref": _clean((revision_index or {}).get("latest_revision_ref")),
        "latest_revised_request_ref": _clean((revision_index or {}).get("latest_revised_request_ref")),
        "latest": dict(latest) if isinstance(latest, Mapping) else {},
    }


def _current_output_summary(current_outputs: Mapping[str, Any] | None) -> dict[str, Any]:
    entries = _list((current_outputs or {}).get("entries"))
    return {
        "status": _clean((current_outputs or {}).get("status")),
        "attempt_id": _clean((current_outputs or {}).get("attempt_id")),
        "attempt_ref": _clean((current_outputs or {}).get("attempt_ref")),
        "attempt_kind": _clean((current_outputs or {}).get("attempt_kind")),
        "output_manifest_ref": _clean((current_outputs or {}).get("output_manifest_ref")),
        "output_count": len(entries),
        "updated_at": _clean((current_outputs or {}).get("updated_at")),
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


def _artifact_access_policy(ref: str) -> dict[str, Any]:
    safe_ref = _clean(ref)
    if safe_ref in _SENSITIVE_ARTIFACT_REFS or any(
        safe_ref.startswith(prefix)
        for prefix in _SENSITIVE_ARTIFACT_PREFIXES
    ):
        return {
            "access_level": "sensitive",
            "preview_policy": "metadata_only",
            "redacted": True,
            "redaction_reason": "raw user input, uploaded file, context package, or lifecycle directive",
        }
    return {
        "access_level": "standard",
        "preview_policy": "text_preview",
        "redacted": False,
        "redaction_reason": "",
    }


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
    assistant_ref = _clean(frontdesk.get("assistant_turn_ref"))
    dialogue_ref = _clean(frontdesk.get("dialogue_ref"))
    return (
        '<section class="panel">'
        "<h2>FrontDesk</h2>"
        f'<dl>{_row("status", _clean(frontdesk.get("status")))}'
        f'{_row("questions", _format_int(frontdesk.get("question_count")))}'
        f'{_row("assistant", _artifact_link(assistant_ref, "assistant turn"), raw=True)}'
        f'{_row("dialogue", _artifact_link(dialogue_ref, "dialogue"), raw=True)}'
        f'{_row("requirements", requirements, raw=True)}</dl>'
        f'<p class="message">{_e(_clean(frontdesk.get("message")))}</p>'
        "</section>"
    )


def _frontdesk_chat_panel(frontdesk: Mapping[str, Any], dialogue: list[Any], web_task: Mapping[str, Any]) -> str:
    rows = []
    for item in dialogue:
        if not isinstance(item, Mapping):
            continue
        role = _clean(item.get("role")) or "unknown"
        turn_index = _clean(item.get("turn_index"))
        dialogue_ref = _clean(item.get("dialogue_ref"))
        summary = _clean(item.get("summary")) or "Dialogue turn recorded."
        content = _artifact_link(dialogue_ref, f"turn {turn_index or '?'}") if dialogue_ref else _e(summary)
        rows.append(
            '<div class="chat-row">'
            f'<span class="chat-role">{_e(role)}</span>'
            f'<p>{content} <span class="detail">{_e(summary)}</span></p>'
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
        '<form id="frontdesk-approve-form" class="approve-form">'
        '<button type="submit">Approve Requirements</button>'
        "</form>"
        '<form id="research-start-form" class="approve-form">'
        '<button type="submit">Start Research</button>'
        "</form>"
        '<div class="task-state">'
        f'{_row("task", _clean(web_task.get("status")) or "idle")}'
        f'{_row("kind", _clean(web_task.get("task_kind")))}'
        f'{_row("error", _clean(web_task.get("error_summary")))}'
        "</div>"
        f"<script>{_CHAT_SCRIPT}</script>"
        "</section>"
    )


def _seed_input_panel(seeds: Mapping[str, Any]) -> str:
    seed_inputs_ref = _clean(seeds.get("seed_inputs_ref"))
    pdf_refs = [
        _artifact_link(ref, Path(ref).name or ref)
        for ref in _string_list(seeds.get("seed_pdf_refs"))[:10]
    ]
    return (
        '<section class="panel seed-panel">'
        "<h2>Seed Inputs</h2>"
        "<dl>"
        f'{_row("seed papers", _format_int(seeds.get("seed_paper_count")))}'
        f'{_row("seed PDFs", _format_int(seeds.get("seed_pdf_count")))}'
        f'{_row("seed inputs", _artifact_link(seed_inputs_ref, "open"), raw=True)}'
        f'{_row("pdf refs", ", ".join(pdf_refs), raw=True)}'
        f'{_row("updated", _clean(seeds.get("updated_at")))}'
        "</dl>"
        '<form id="seed-paper-form" class="seed-form">'
        '<select id="seed-paper-kind" name="kind">'
        '<option value="doi">DOI</option>'
        '<option value="arxiv">arXiv</option>'
        '<option value="title">Title</option>'
        '<option value="url">URL</option>'
        "</select>"
        '<input id="seed-paper-value" name="value" type="text" placeholder="Seed paper identifier">'
        '<input id="seed-paper-note" name="note" type="text" placeholder="Optional note">'
        '<button type="submit">Add Paper</button>'
        "</form>"
        '<form id="seed-pdf-form" class="seed-form">'
        '<input id="seed-pdf-file" name="pdf" type="file" accept="application/pdf,.pdf">'
        '<button type="submit">Upload PDF</button>'
        "</form>"
        "</section>"
    )


def _runtime_controls_panel(
    runtime_events: list[Any],
    lifecycle_actions: Mapping[str, Any],
    attempt_index: Mapping[str, Any],
    revision_index: Mapping[str, Any],
    current_outputs: Mapping[str, Any],
) -> str:
    rows = []
    for item in runtime_events:
        if not isinstance(item, Mapping):
            continue
        event_id = _clean(item.get("event_id"))
        kind = _clean(item.get("kind"))
        if not event_id and not kind:
            continue
        rows.append(
            '<div class="event-row">'
            f'<span>{_e(kind or "event")}</span>'
            f'<code>{_e(event_id)}</code>'
            f'<span class="detail">{_e(_clean(item.get("delivery")))}</span>'
            "</div>"
        )
    if not rows:
        rows.append('<p class="muted">No runtime interventions yet.</p>')
    buttons = "".join(
        f'<button type="button" data-runtime-action="{_e(action)}">{_e(label)}</button>'
        for action, label in (
            ("pause", "Pause"),
            ("resume", "Resume"),
            ("checkpoint", "Checkpoint"),
            ("stop_after_current_turn", "Stop Turn"),
            ("cancel", "Cancel"),
        )
    )
    retry = _mapping(lifecycle_actions.get("retry"))
    revise = _mapping(lifecycle_actions.get("revise"))
    recover = _mapping(lifecycle_actions.get("recover_lock"))
    latest_attempt = _mapping(attempt_index.get("latest"))
    latest_revision = _mapping(revision_index.get("latest"))
    return (
        '<section class="panel runtime-panel">'
        "<h2>Runtime Controls</h2>"
        f'<div class="control-buttons">{buttons}</div>'
        '<form id="runtime-message-form" class="chat-form">'
        '<textarea id="runtime-message" name="message" rows="3" placeholder="Runtime intervention or revision request"></textarea>'
        '<button type="submit" data-runtime-submit="message">Send</button>'
        '<button type="button" data-runtime-submit="revise">Revise</button>'
        "</form>"
        '<div class="control-buttons lifecycle-buttons">'
        '<button type="button" data-lifecycle-action="retry">Request Retry</button>'
        '<button type="button" data-attempt-start="retry">Start Retry Attempt</button>'
        '<button type="button" data-lifecycle-action="revise">Request Revision</button>'
        '<button type="button" data-revision-start="contract">Start Revision Attempt</button>'
        '<button type="button" data-lifecycle-action="recover_lock">Recover Lock</button>'
        "</div>"
        '<div class="task-state">'
        f'{_row("retry", _clean(retry.get("status")))}'
        f'{_row("revision", _clean(revise.get("status")))}'
        f'{_row("lock recovery", _clean(recover.get("status")))}'
        f'{_row("attempts", _format_int(attempt_index.get("attempt_count")))}'
        f'{_row("latest attempt", _clean(latest_attempt.get("status")))}'
        f'{_row("attempt ref", _artifact_link(_clean(attempt_index.get("latest_attempt_ref")), "open"), raw=True)}'
        f'{_row("revisions", _format_int(revision_index.get("revision_count")))}'
        f'{_row("latest revision", _clean(latest_revision.get("status")))}'
        f'{_row("revision ref", _artifact_link(_clean(revision_index.get("latest_revision_ref")), "open"), raw=True)}'
        f'{_row("current output", _artifact_link(_clean(current_outputs.get("output_manifest_ref")), "open"), raw=True)}'
        f'{_row("output attempt", _artifact_link(_clean(current_outputs.get("attempt_ref")), _clean(current_outputs.get("attempt_kind")) or "attempt"), raw=True)}'
        f'{_row("output refs", _format_int(current_outputs.get("output_count")))}'
        "</div>"
        '<div class="event-log">'
        f"{''.join(rows)}"
        "</div>"
        "</section>"
    )


def _timeline_panel(rows: list[Any], groups: list[Any]) -> str:
    grouped = []
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        group_rows = _list(group.get("rows"))[-40:]
        status = _clean(group.get("status")) or _clean(group.get("latest_state")) or "unknown"
        output_manifest_ref = _clean(group.get("output_manifest_ref"))
        refs = [
            _artifact_link(ref, "ref")
            for ref in _string_list(group.get("refs"))[:4]
            if ref
        ]
        if output_manifest_ref and output_manifest_ref not in _string_list(group.get("refs")):
            refs.append(_artifact_link(output_manifest_ref, "outputs"))
        badge = '<span class="current-output">current output</span>' if group.get("is_current_output") is True else ""
        grouped.append(
            '<details class="timeline-group" open>'
            "<summary>"
            f'<span>{_e(_clean(group.get("title")) or "Timeline group")}</span>'
            f'<code>{_e(status)}</code>'
            f'<span class="detail">{_format_int(group.get("row_count"))} rows</span>'
            f"{badge}"
            "</summary>"
            f'<div class="timeline-group-refs">{", ".join(refs)}</div>'
            f'<div class="event-log">{_timeline_rows(group_rows)}</div>'
            "</details>"
        )
    if not grouped:
        grouped.append('<p class="muted">No grouped timeline yet.</p>')
    flat_items = _timeline_rows(rows)
    if not flat_items:
        flat_items = '<p class="muted">No progress timeline yet.</p>'
    return (
        '<section class="panel timeline-panel">'
        "<h2>Progress Timeline</h2>"
        '<div class="timeline-groups">'
        f"{''.join(grouped)}"
        "</div>"
        "<details>"
        "<summary>Flat timeline</summary>"
        '<div class="event-log">'
        f"{flat_items}"
        "</div>"
        "</details>"
        "</section>"
    )


def _timeline_rows(rows: list[Any]) -> str:
    items = []
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        source = _clean(item.get("source"))
        stage = _clean(item.get("stage"))
        state = _clean(item.get("state"))
        summary = _clean(item.get("summary"))
        refs = [
            _artifact_link(ref, "ref")
            for ref in _string_list(item.get("refs"))[:3]
            if ref
        ]
        ref_html = ", ".join(refs)
        items.append(
            '<div class="event-row timeline-row">'
            f'<span>{_e(source or "timeline")}</span>'
            f'<code>{_e(stage or "unknown")}</code>'
            f'<span class="detail">{_e(state or "unknown")}</span>'
            f'<span>{_e(summary)}</span>'
            f'<span>{ref_html}</span>'
            "</div>"
        )
    return "".join(items)


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
        redacted = item.get("redacted") is True
        access_level = _clean(item.get("access_level")) or "standard"
        rows.append(
            "<tr>"
            f"<td>{_e(_clean(item.get('group')))}</td>"
            f"<td>{_artifact_link(ref, _clean(item.get('label'))) if exists else _e(_clean(item.get('label')))}</td>"
            f"<td>{_e(ref)}</td>"
            f"<td>{'restricted' if redacted and exists else 'present' if exists else 'missing'}</td>"
            f"<td>{_e(access_level)}</td>"
            f"<td>{_e(_format_int(item.get('byte_size')))}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Artifacts</h2>"
        '<table><thead><tr><th>group</th><th>artifact</th><th>ref</th><th>state</th><th>access</th><th>bytes</th></tr></thead>'
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
.approve-form {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}
.approve-form button {
  min-height: 40px;
  padding: 0 14px;
}
.runtime-panel .chat-form {
  grid-template-columns: minmax(0, 1fr) 96px 96px;
}
.seed-form {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr) minmax(0, 1fr) 110px;
  gap: 10px;
  margin-top: 12px;
}
.seed-form input, .seed-form select {
  min-height: 40px;
  padding: 0 10px;
  border: 1px solid var(--line);
  background: #ffffff;
  color: var(--ink);
  font: inherit;
  min-width: 0;
}
.seed-form input[type="file"] {
  padding-top: 8px;
}
.control-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.control-buttons button {
  min-height: 38px;
  padding: 0 12px;
}
.event-log {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}
.event-row {
  display: grid;
  grid-template-columns: 170px minmax(0, 1fr) 150px;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  background: #fbfcfd;
}
.event-row code {
  overflow-wrap: anywhere;
}
.timeline-groups {
  display: grid;
  gap: 12px;
}
.timeline-group {
  border: 1px solid var(--line);
  background: #fbfcfd;
}
.timeline-group summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px 90px auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
}
.timeline-group .event-log {
  margin: 0;
  padding: 0 10px 10px;
}
.timeline-group-refs {
  padding: 0 12px 10px;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.current-output {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid #1b5a49;
  color: #1b5a49;
  background: #eef8f4;
  font-size: 12px;
  font-weight: 650;
}
.task-state {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr);
  gap: 6px 12px;
  margin-top: 12px;
  padding: 10px;
  border: 1px solid var(--line);
  background: #fbfcfd;
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
  .seed-form { grid-template-columns: 1fr; }
  .runtime-panel .chat-form { grid-template-columns: 1fr; }
  .event-row { grid-template-columns: 1fr; }
  .timeline-group summary { grid-template-columns: 1fr; }
  .approve-form { display: grid; }
  button { min-height: 44px; }
}
"""


_CHAT_SCRIPT = """
(() => {
  const form = document.getElementById("frontdesk-form");
  const approveForm = document.getElementById("frontdesk-approve-form");
  const startForm = document.getElementById("research-start-form");
  const runtimeForm = document.getElementById("runtime-message-form");
  const runtimeTextarea = document.getElementById("runtime-message");
  const seedPaperForm = document.getElementById("seed-paper-form");
  const seedPdfForm = document.getElementById("seed-pdf-form");
  const textarea = document.getElementById("frontdesk-message");
  const postJson = async (path, payload) => {
    const response = await fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload || {})
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || "Request failed.");
    }
    return data;
  };
  if (form && textarea) form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = textarea.value.trim();
    if (!message) return;
    const button = form.querySelector("button");
    if (button) button.disabled = true;
    try {
      await postJson("/api/frontdesk/message", {message});
      window.location.reload();
    } catch (error) {
      alert(String(error));
    } finally {
      if (button) button.disabled = false;
    }
  });
  if (approveForm) approveForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = approveForm.querySelector("button");
    if (button) button.disabled = true;
    try {
      await postJson("/api/frontdesk/approve", {});
      window.location.reload();
    } catch (error) {
      alert(String(error));
    } finally {
      if (button) button.disabled = false;
    }
  });
  if (startForm) startForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = startForm.querySelector("button");
    if (button) button.disabled = true;
    try {
      await postJson("/api/research/start", {});
      window.location.reload();
    } catch (error) {
      alert(String(error));
    } finally {
      if (button) button.disabled = false;
    }
  });
  if (seedPaperForm) seedPaperForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const kind = document.getElementById("seed-paper-kind");
    const value = document.getElementById("seed-paper-value");
    const note = document.getElementById("seed-paper-note");
    const button = seedPaperForm.querySelector("button");
    const payload = {
      kind: kind ? kind.value : "doi",
      value: value ? value.value.trim() : "",
      note: note ? note.value.trim() : ""
    };
    if (!payload.value) return;
    if (button) button.disabled = true;
    try {
      await postJson("/api/seeds/papers", payload);
      window.location.reload();
    } catch (error) {
      alert(String(error));
    } finally {
      if (button) button.disabled = false;
    }
  });
  const fileToBase64 = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      resolve(dataUrl.includes(",") ? dataUrl.split(",", 2)[1] : dataUrl);
    };
    reader.onerror = () => reject(reader.error || new Error("File read failed."));
    reader.readAsDataURL(file);
  });
  if (seedPdfForm) seedPdfForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("seed-pdf-file");
    const file = input && input.files && input.files[0] ? input.files[0] : null;
    if (!file) return;
    const button = seedPdfForm.querySelector("button");
    if (button) button.disabled = true;
    try {
      const content_base64 = await fileToBase64(file);
      await postJson("/api/seeds/pdfs", {filename: file.name, content_base64});
      window.location.reload();
    } catch (error) {
      alert(String(error));
    } finally {
      if (button) button.disabled = false;
    }
  });
  document.querySelectorAll("[data-runtime-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.getAttribute("data-runtime-action");
      button.disabled = true;
      try {
        await postJson("/api/runtime/control", {action});
        window.location.reload();
      } catch (error) {
        alert(String(error));
      } finally {
        button.disabled = false;
      }
    });
  });
  const sendRuntime = async (action, button) => {
    const text = runtimeTextarea ? runtimeTextarea.value.trim() : "";
    if (!text) return;
    if (button) button.disabled = true;
    try {
      await postJson("/api/runtime/control", {action, text});
      window.location.reload();
    } catch (error) {
      alert(String(error));
    } finally {
      if (button) button.disabled = false;
    }
  };
  if (runtimeForm) runtimeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendRuntime("message", runtimeForm.querySelector("[data-runtime-submit='message']"));
  });
  document.querySelectorAll("[data-runtime-submit='revise']").forEach((button) => {
    button.addEventListener("click", async () => {
      await sendRuntime("revise", button);
    });
  });
  document.querySelectorAll("[data-lifecycle-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.getAttribute("data-lifecycle-action");
      const text = runtimeTextarea ? runtimeTextarea.value.trim() : "";
      button.disabled = true;
      try {
        await postJson("/api/lifecycle/action", {action, text});
        window.location.reload();
      } catch (error) {
        alert(String(error));
      } finally {
        button.disabled = false;
      }
    });
  });
  document.querySelectorAll("[data-attempt-start]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await postJson("/api/research/attempt/start", {});
        window.location.reload();
      } catch (error) {
        alert(String(error));
      } finally {
        button.disabled = false;
      }
    });
  });
  document.querySelectorAll("[data-revision-start]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await postJson("/api/research/revision/start", {});
        window.location.reload();
      } catch (error) {
        alert(String(error));
      } finally {
        button.disabled = false;
      }
    });
  });
})();
"""
