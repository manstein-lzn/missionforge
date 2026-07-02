"""Read-only DeepResearch project snapshot projection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import missionforge as mf

from .attempt_outputs import CURRENT_OUTPUT_POINTER_REF, read_current_output_pointer
from .frontdesk import (
    FRONTDESK_ASSISTANT_TURN_REF,
    FRONTDESK_CONTROL_REF,
    FRONTDESK_DIALOGUE_REF,
    FRONTDESK_REQUIREMENTS_REF,
)
from .kernel_refs import (
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
from .web_artifacts import ARTIFACT_PREVIEW_MAX_CHARS, artifact_access_policy
from .web_seeds import seed_snapshot
from .web_tasks import WEB_TASK_STATE_REF, read_web_task_state
from .web_timeline import PROGRESS_TIMELINE_REF, build_project_timeline, build_timeline_attempt_groups
from .workspace import resolve_workspace_ref


WEB_CONSOLE_SCHEMA_VERSION = "missionforge_deepresearch.web_console.project_snapshot.v1"


def build_project_snapshot(workspace: str | Path, request_id: str) -> dict[str, Any]:
    """Build a read-only project snapshot from persisted refs."""

    workspace_root = Path(workspace).resolve()
    run_workspace_ref = run_ref(request_id)
    run_root = resolve_workspace_ref(workspace_root, run_workspace_ref)
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
        "run_workspace_ref": run_workspace_ref,
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


def run_ref(request_id: str) -> str:
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
        **artifact_access_policy(safe_ref),
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
