"""Refs-first progress timeline for the DeepResearch web console.

The timeline is an operator projection. It summarizes persisted refs and
append-only ledgers; it does not become product truth or semantic authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import missionforge as mf

from .lifecycle_actions import LIFECYCLE_ACTION_INDEX_REF
from .research_attempts import ATTEMPT_INDEX_REF, read_attempt_index
from .research_requests import CONTRACT_REVISION_INDEX_REF, read_contract_revision_index
from .web_tasks import WEB_TASK_STATE_REF, read_web_task_state
from .workspace import read_json_ref, ref_exists, resolve_workspace_ref


PROGRESS_TIMELINE_REF = "web/progress_timeline.jsonl"
TIMELINE_SCHEMA_VERSION = "missionforge_deepresearch.web_progress_timeline_event.v1"
TIMELINE_GROUP_SCHEMA_VERSION = "missionforge_deepresearch.web_progress_timeline_group.v1"
TIMELINE_MAX_ROWS = 240


def append_runtime_progress_event(
    run_root: str | Path,
    *,
    source: str,
    stage: str,
    refs: list[str] | None = None,
) -> dict[str, Any]:
    """Append a sanitized runtime progress marker.

    The incoming adapter progress payload is intentionally not persisted here;
    callers pass only product-controlled source/stage labels and refs.
    """

    payload = _event(
        source=source,
        source_kind="runtime_progress",
        source_ref=PROGRESS_TIMELINE_REF,
        stage=_safe_label(stage) or "runtime",
        state="running",
        summary="Runtime progress update",
        refs=refs or [],
    )
    _append_jsonl(run_root, PROGRESS_TIMELINE_REF, payload)
    return payload


def append_flow_ledger_event(run_root: str | Path, event: mf.FlowLedgerEvent) -> dict[str, Any]:
    """Append a sanitized live flow-ledger marker emitted by Kernel run_flow."""

    refs = [
        ref
        for ref in [
            event.step_record_ref or "",
            event.decision_ref or "",
            *list(event.refs),
        ]
        if ref
    ]
    payload = _event(
        source="flow_ledger",
        source_kind="flow_ledger",
        stage=_safe_label(event.step_id or "flow"),
        state=_state_for_flow_event(event),
        summary=_summary_for_flow_event(event),
        refs=refs,
        source_event_id=event.event_id,
        event_kind=event.kind.value,
        route_value=_safe_label(event.route_value or ""),
        route_target=_safe_label(event.route_target or ""),
        stop_reason=_safe_label(event.stop_reason or ""),
    )
    _append_jsonl(run_root, PROGRESS_TIMELINE_REF, payload)
    return payload


def runtime_progress_sink(
    run_root: str | Path,
    *,
    source: str,
    default_stage: str = "runtime",
    allow_payload_stage: bool = False,
):
    """Return a PiWorker progress sink that records sanitized timeline events."""

    def sink(payload: Mapping[str, Any] | Any) -> None:
        stage = default_stage
        refs: list[str] = []
        if isinstance(payload, Mapping):
            candidate_stage = payload.get("stage") or payload.get("step_id") or payload.get("phase")
            if allow_payload_stage and isinstance(candidate_stage, str) and candidate_stage.strip():
                stage = candidate_stage
            refs = _valid_refs(payload.get("refs", []))
        append_runtime_progress_event(run_root, source=source, stage=stage, refs=refs)

    return sink


def build_project_timeline(
    run_root: str | Path,
    *,
    lifecycle: Mapping[str, Any] | None = None,
    run_status: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build a sanitized timeline from web, lifecycle, interaction, and flow refs."""

    root = Path(run_root).resolve()
    rows: list[dict[str, Any]] = []
    rows.extend(_read_persisted_timeline(root))
    rows.extend(_runtime_event_rows(root))
    rows.extend(_lifecycle_action_rows(root))
    rows.extend(_attempt_rows(root))
    rows.extend(_revision_rows(root))
    rows.extend(_flow_rows_for_lifecycle(root, lifecycle or {}, run_status or {}))
    rows.append(_web_task_row(root))
    return _dedupe_rows(rows)[-TIMELINE_MAX_ROWS:]


def build_timeline_attempt_groups(
    run_root: str | Path,
    rows: list[Mapping[str, Any]] | None = None,
    *,
    current_outputs: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Group sanitized timeline rows by project/attempt execution boundary."""

    root = Path(run_root).resolve()
    safe_rows = [_timeline_row(item) for item in rows or [] if isinstance(item, Mapping)]
    contexts = _attempt_group_contexts(root, current_outputs or {})
    groups: dict[str, dict[str, Any]] = {
        "project": _timeline_group(
            group_id="project",
            group_kind="project",
            title="Project timeline",
            refs=[],
        )
    }
    related_ref_to_group: dict[str, str] = {}
    for context in contexts:
        group_id = _safe_label(context.get("group_id"))
        if not group_id:
            continue
        groups[group_id] = _timeline_group(**context)
        for ref in _valid_refs(context.get("related_refs", [])):
            related_ref_to_group[ref] = group_id

    for row in safe_rows:
        group_id = _group_id_for_row(row, related_ref_to_group)
        groups.setdefault(
            group_id,
            _timeline_group(
                group_id=group_id,
                group_kind="project",
                title="Project timeline",
                refs=[],
            ),
        )
        groups[group_id]["rows"].append(row)

    ordered: list[dict[str, Any]] = []
    if groups["project"]["rows"]:
        ordered.append(_finalize_group(groups["project"]))
    attempt_groups = [
        group
        for group_id, group in groups.items()
        if group_id != "project" and (group.get("rows") or group.get("attempt_ref"))
    ]
    attempt_groups.sort(key=lambda group: _safe_int(group.get("generation")))
    ordered.extend(_finalize_group(group) for group in attempt_groups)
    return ordered


def _read_persisted_timeline(run_root: Path) -> list[dict[str, Any]]:
    rows = []
    path = resolve_workspace_ref(run_root, PROGRESS_TIMELINE_REF)
    if not path.is_file():
        return rows
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, Mapping) and payload.get("schema_version") == TIMELINE_SCHEMA_VERSION:
                rows.append(_sanitize_event(payload))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        return []
    return rows


def _runtime_event_rows(run_root: Path) -> list[dict[str, Any]]:
    path = resolve_workspace_ref(run_root, mf.USER_EVENTS_REF)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for item in _read_jsonl(path):
            if not isinstance(item, Mapping):
                continue
            kind = _safe_label(item.get("kind"))
            rows.append(
                _event(
                    source="runtime_control",
                    source_kind="interaction_event",
                    source_ref=mf.USER_EVENTS_REF,
                    stage=kind or "runtime_control",
                    state=_safe_label(item.get("delivery")) or "queued",
                    summary=f"Runtime control: {kind or 'event'}",
                    refs=[mf.USER_EVENTS_REF],
                    source_event_id=_safe_label(item.get("event_id")),
                )
            )
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        return []
    return rows


def _lifecycle_action_rows(run_root: Path) -> list[dict[str, Any]]:
    path = resolve_workspace_ref(run_root, LIFECYCLE_ACTION_INDEX_REF)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for item in _read_jsonl(path):
            if not isinstance(item, Mapping):
                continue
            kind = _safe_label(item.get("kind"))
            refs = [LIFECYCLE_ACTION_INDEX_REF, *_valid_refs([item.get("reason_ref"), item.get("consumed_by_attempt_ref")])]
            rows.append(
                _event(
                    source="lifecycle_action",
                    source_kind="lifecycle_action",
                    source_ref=LIFECYCLE_ACTION_INDEX_REF,
                    stage=kind or "lifecycle_action",
                    state=_safe_label(item.get("status")) or "recorded",
                    summary=f"Lifecycle action: {kind or 'action'}",
                    refs=refs,
                    source_event_id=_safe_label(item.get("action_id")),
                )
            )
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        return []
    return rows


def _attempt_rows(run_root: Path) -> list[dict[str, Any]]:
    index = read_attempt_index(run_root)
    rows = []
    for item in index.get("attempts", []):
        if not isinstance(item, Mapping):
            continue
        attempt_ref = _safe_ref(item.get("attempt_ref"))
        output_manifest_ref = _safe_ref(item.get("output_manifest_ref"))
        refs = [ATTEMPT_INDEX_REF]
        refs.extend(ref for ref in [attempt_ref, output_manifest_ref] if ref)
        rows.append(
            _event(
                source="attempt",
                source_kind="attempt",
                source_ref=ATTEMPT_INDEX_REF,
                stage=_safe_label(item.get("kind")) or "attempt",
                state=_safe_label(item.get("status")) or "unknown",
                summary="Kernel attempt",
                refs=refs,
                source_event_id=_safe_label(item.get("attempt_id")),
                attempt_ref=attempt_ref,
                generation=_safe_int(item.get("generation")),
            )
        )
    return rows


def _attempt_group_contexts(run_root: Path, current_outputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    index = read_attempt_index(run_root)
    current_attempt_ref = _safe_ref(current_outputs.get("attempt_ref"))
    contexts = []
    for item in index.get("attempts", []):
        if not isinstance(item, Mapping):
            continue
        attempt_ref = _safe_ref(item.get("attempt_ref"))
        if not attempt_ref:
            continue
        attempt = _read_json_or_empty(run_root, attempt_ref)
        output_manifest_ref = _safe_ref(item.get("output_manifest_ref")) or _safe_ref(attempt.get("output_manifest_ref"))
        revision_ref = _safe_ref(item.get("revision_record_ref")) or _safe_ref(attempt.get("revision_record_ref"))
        flow_result_ref = _safe_ref(attempt.get("flow_result_ref"))
        related_refs = _valid_refs(
            [
                attempt_ref,
                output_manifest_ref,
                revision_ref,
                _safe_ref(item.get("source_retry_request_ref")),
                _safe_ref(item.get("source_revision_request_ref")),
                _safe_ref(attempt.get("before_snapshot_ref")),
                _safe_ref(attempt.get("result_ref")),
                flow_result_ref,
                _safe_ref(attempt.get("run_status_ref")),
                _safe_ref(attempt.get("task_ref")),
                _safe_ref(attempt.get("lock_ref")),
                *_flow_related_refs(run_root, flow_result_ref),
                *_output_manifest_refs(run_root, output_manifest_ref),
            ]
        )
        attempt_id = _safe_label(item.get("attempt_id")) or _safe_label(attempt.get("attempt_id")) or attempt_ref
        contexts.append(
            {
                "group_id": attempt_id,
                "group_kind": "attempt",
                "title": _attempt_group_title(item, attempt),
                "attempt_id": attempt_id,
                "attempt_ref": attempt_ref,
                "attempt_kind": _safe_label(item.get("kind")) or _safe_label(attempt.get("kind")),
                "generation": _safe_int(item.get("generation") or attempt.get("generation")),
                "status": _safe_label(item.get("status")) or _safe_label(attempt.get("status")),
                "is_current_output": bool(current_attempt_ref and current_attempt_ref == attempt_ref),
                "output_manifest_ref": output_manifest_ref,
                "revision_record_ref": revision_ref,
                "refs": _valid_refs([attempt_ref, output_manifest_ref, revision_ref]),
                "related_refs": related_refs,
            }
        )
    return contexts


def _attempt_group_title(index_item: Mapping[str, Any], attempt: Mapping[str, Any]) -> str:
    kind = _safe_label(index_item.get("kind")) or _safe_label(attempt.get("kind")) or "attempt"
    generation = _safe_int(index_item.get("generation") or attempt.get("generation"))
    if generation:
        return f"Attempt {generation}: {kind}"
    return f"Attempt: {kind}"


def _revision_rows(run_root: Path) -> list[dict[str, Any]]:
    index = read_contract_revision_index(run_root)
    rows = []
    for item in index.get("revisions", []):
        if not isinstance(item, Mapping):
            continue
        revision_ref = _safe_ref(item.get("revision_ref"))
        attempt_ref = _safe_ref(item.get("attempt_ref"))
        refs = [CONTRACT_REVISION_INDEX_REF]
        refs.extend(ref for ref in [revision_ref, attempt_ref, _safe_ref(item.get("revised_request_ref"))] if ref)
        rows.append(
            _event(
                source="contract_revision",
                source_kind="contract_revision",
                source_ref=CONTRACT_REVISION_INDEX_REF,
                stage="contract_revision",
                state=_safe_label(item.get("status")) or "unknown",
                summary="Contract revision attempt",
                refs=refs,
                source_event_id=_safe_label(item.get("revision_id")),
                attempt_ref=attempt_ref,
            )
        )
    return rows


def _flow_rows_for_lifecycle(
    run_root: Path,
    lifecycle: Mapping[str, Any],
    run_status: Mapping[str, Any],
) -> list[dict[str, Any]]:
    refs = [
        _safe_ref(lifecycle.get("latest_frontdesk_flow_result_ref")),
        _safe_ref(lifecycle.get("latest_flow_result_ref")),
        _safe_ref(run_status.get("flow_result_ref")),
    ]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        if not ref or ref in seen:
            continue
        seen.add(ref)
        rows.extend(_flow_rows(run_root, ref))
    return rows


def _flow_rows(run_root: Path, flow_result_ref: str) -> list[dict[str, Any]]:
    if not ref_exists(run_root, flow_result_ref):
        return []
    try:
        flow_result = read_json_ref(run_root, flow_result_ref, "deepresearch_timeline_flow_result")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        return []
    rows: list[dict[str, Any]] = []
    for ledger_ref in _valid_refs(flow_result.get("ledger_refs", [])):
        rows.extend(_flow_ledger_rows(run_root, ledger_ref))
    for step_record_ref in _valid_refs(flow_result.get("step_record_refs", [])):
        rows.append(_step_record_row(run_root, step_record_ref))
    return rows


def _flow_ledger_rows(run_root: Path, ledger_ref: str) -> list[dict[str, Any]]:
    path = resolve_workspace_ref(run_root, ledger_ref)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for item in _read_jsonl(path):
            if not isinstance(item, Mapping):
                continue
            kind = _safe_label(item.get("kind"))
            step_id = _safe_label(item.get("step_id")) or "flow"
            refs = _valid_refs([item.get("step_record_ref"), item.get("decision_ref"), *_as_list(item.get("refs"))])
            rows.append(
                _event(
                    source="flow_ledger",
                    source_kind="flow_ledger",
                    source_ref=ledger_ref,
                    stage=step_id,
                    state=_state_for_flow_kind(kind, _safe_label(item.get("status"))),
                    summary=_summary_for_flow_kind(kind, step_id),
                    refs=[ledger_ref, *refs],
                    source_event_id=_safe_label(item.get("event_id")),
                    event_kind=kind,
                    route_value=_safe_label(item.get("route_value")),
                    route_target=_safe_label(item.get("route_target")),
                    stop_reason=_safe_label(item.get("stop_reason")),
                )
            )
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        return []
    return rows


def _step_record_row(run_root: Path, step_record_ref: str) -> dict[str, Any]:
    refs = [step_record_ref]
    stage = "step"
    state = "recorded"
    try:
        record = read_json_ref(run_root, step_record_ref, "deepresearch_timeline_step_record")
        stage = _safe_label(record.get("step_id")) or stage
        state = _safe_label(record.get("status")) or state
        refs.extend(_valid_refs([record.get("execution_report_ref"), record.get("permission_manifest_ref")]))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        pass
    return _event(
        source="step_record",
        source_kind="step_record",
        source_ref=step_record_ref,
        stage=stage,
        state=state,
        summary=f"Step record: {stage}",
        refs=refs,
        source_event_id=step_record_ref,
    )


def _flow_related_refs(run_root: Path, flow_result_ref: str) -> list[str]:
    if not flow_result_ref or not ref_exists(run_root, flow_result_ref):
        return []
    try:
        flow_result = read_json_ref(run_root, flow_result_ref, "deepresearch_timeline_group_flow_result")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        return []
    return _valid_refs(
        [
            flow_result_ref,
            *_as_list(flow_result.get("ledger_refs")),
            *_as_list(flow_result.get("step_record_refs")),
        ]
    )


def _output_manifest_refs(run_root: Path, output_manifest_ref: str) -> list[str]:
    if not output_manifest_ref or not ref_exists(run_root, output_manifest_ref):
        return []
    try:
        manifest = read_json_ref(run_root, output_manifest_ref, "deepresearch_timeline_group_output_manifest")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        return []
    refs = [output_manifest_ref]
    for item in _as_list(manifest.get("entries")):
        if isinstance(item, Mapping):
            refs.append(_safe_ref(item.get("output_ref")))
    return _valid_refs(refs)


def _read_json_or_empty(run_root: Path, ref: str) -> dict[str, Any]:
    if not ref or not ref_exists(run_root, ref):
        return {}
    try:
        payload = read_json_ref(run_root, ref, "deepresearch_timeline_group_json")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, mf.ContractValidationError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _timeline_group(
    *,
    group_id: str,
    group_kind: str,
    title: str,
    refs: list[str],
    attempt_id: str = "",
    attempt_ref: str = "",
    attempt_kind: str = "",
    generation: int = 0,
    status: str = "",
    is_current_output: bool = False,
    output_manifest_ref: str = "",
    revision_record_ref: str = "",
    related_refs: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": TIMELINE_GROUP_SCHEMA_VERSION,
        "group_id": _safe_label(group_id) or "project",
        "group_kind": _safe_label(group_kind) or "project",
        "title": _safe_summary(title),
        "attempt_id": _safe_label(attempt_id),
        "attempt_ref": _safe_ref(attempt_ref),
        "attempt_kind": _safe_label(attempt_kind),
        "generation": generation if generation >= 0 else 0,
        "status": _safe_label(status),
        "is_current_output": bool(is_current_output),
        "output_manifest_ref": _safe_ref(output_manifest_ref),
        "revision_record_ref": _safe_ref(revision_record_ref),
        "refs": _valid_refs(refs),
        "related_refs": _valid_refs(related_refs or []),
        "row_count": 0,
        "latest_stage": "",
        "latest_state": "",
        "rows": [],
    }
    mf.assert_refs_only_payload(payload, "deepresearch_progress_timeline_group")
    return payload


def _finalize_group(group: Mapping[str, Any]) -> dict[str, Any]:
    rows = [row for row in _as_list(group.get("rows")) if isinstance(row, Mapping)]
    latest = rows[-1] if rows else {}
    payload = {
        "schema_version": TIMELINE_GROUP_SCHEMA_VERSION,
        "group_id": _safe_label(group.get("group_id")) or "project",
        "group_kind": _safe_label(group.get("group_kind")) or "project",
        "title": _safe_summary(group.get("title")),
        "attempt_id": _safe_label(group.get("attempt_id")),
        "attempt_ref": _safe_ref(group.get("attempt_ref")),
        "attempt_kind": _safe_label(group.get("attempt_kind")),
        "generation": _safe_int(group.get("generation")),
        "status": _safe_label(group.get("status")) or _safe_label(latest.get("state")),
        "is_current_output": group.get("is_current_output") is True,
        "output_manifest_ref": _safe_ref(group.get("output_manifest_ref")),
        "revision_record_ref": _safe_ref(group.get("revision_record_ref")),
        "refs": _valid_refs(group.get("refs", [])),
        "row_count": len(rows),
        "latest_stage": _safe_label(latest.get("stage")),
        "latest_state": _safe_label(latest.get("state")),
        "rows": [_timeline_row(row) for row in rows],
    }
    mf.assert_refs_only_payload(payload, "deepresearch_progress_timeline_group")
    return payload


def _timeline_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "event_id": _safe_label(row.get("event_id")),
        "source": _safe_label(row.get("source")) or "unknown",
        "source_kind": _safe_label(row.get("source_kind")) or _safe_label(row.get("source")) or "unknown",
        "source_ref": _safe_ref(row.get("source_ref")),
        "source_event_id": _safe_label(row.get("source_event_id")),
        "event_kind": _safe_label(row.get("event_kind")),
        "stage": _safe_label(row.get("stage")) or "unknown",
        "state": _safe_label(row.get("state")) or "unknown",
        "summary": _safe_summary(row.get("summary")),
        "route_value": _safe_label(row.get("route_value")),
        "route_target": _safe_label(row.get("route_target")),
        "stop_reason": _safe_label(row.get("stop_reason")),
        "attempt_ref": _safe_ref(row.get("attempt_ref")),
        "generation": _safe_int(row.get("generation")),
        "refs": _valid_refs(row.get("refs", [])),
        "created_at": _safe_label(row.get("created_at")),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_progress_timeline_group_row")
    return payload


def _group_id_for_row(row: Mapping[str, Any], related_ref_to_group: Mapping[str, str]) -> str:
    attempt_ref = _safe_ref(row.get("attempt_ref"))
    refs = _valid_refs([attempt_ref, row.get("source_ref"), *_as_list(row.get("refs"))])
    for ref in refs:
        group_id = _safe_label(related_ref_to_group.get(ref))
        if group_id:
            return group_id
    return "project"


def _web_task_row(run_root: Path) -> dict[str, Any]:
    state = read_web_task_state(run_root)
    status = _safe_label(state.get("status")) or "idle"
    task_kind = _safe_label(state.get("task_kind")) or "web_task"
    return _event(
        source="web_task",
        source_kind="web_task",
        source_ref=WEB_TASK_STATE_REF if ref_exists(run_root, WEB_TASK_STATE_REF) else "",
        stage=task_kind,
        state=status,
        summary=f"Web task: {status}",
        refs=[WEB_TASK_STATE_REF] if ref_exists(run_root, WEB_TASK_STATE_REF) else [],
        source_event_id=_safe_label(state.get("task_id")),
    )


def _event(
    *,
    source: str,
    stage: str,
    state: str,
    summary: str,
    refs: list[str] | None = None,
    source_kind: str = "",
    source_ref: str = "",
    source_event_id: str = "",
    event_kind: str = "",
    route_value: str = "",
    route_target: str = "",
    stop_reason: str = "",
    attempt_ref: str = "",
    generation: int = 0,
) -> dict[str, Any]:
    payload = {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "event_id": f"TL-{uuid4().hex}",
        "source": _safe_label(source) or "unknown",
        "source_kind": _safe_label(source_kind) or _safe_label(source) or "unknown",
        "source_ref": _safe_ref(source_ref),
        "source_event_id": _safe_label(source_event_id),
        "event_kind": _safe_label(event_kind),
        "stage": _safe_label(stage) or "unknown",
        "state": _safe_label(state) or "unknown",
        "summary": _safe_summary(summary),
        "route_value": _safe_label(route_value),
        "route_target": _safe_label(route_target),
        "stop_reason": _safe_label(stop_reason),
        "attempt_ref": _safe_ref(attempt_ref),
        "generation": generation if generation >= 0 else 0,
        "refs": _valid_refs(refs or []),
        "created_at": _utc_now(),
    }
    mf.assert_refs_only_payload(payload, "deepresearch_progress_timeline_event")
    return payload


def _sanitize_event(payload: Mapping[str, Any]) -> dict[str, Any]:
    return _event(
        source=_safe_label(payload.get("source")),
        source_kind=_safe_label(payload.get("source_kind")),
        source_ref=_safe_ref(payload.get("source_ref")),
        source_event_id=_safe_label(payload.get("source_event_id")),
        event_kind=_safe_label(payload.get("event_kind")),
        stage=_safe_label(payload.get("stage")),
        state=_safe_label(payload.get("state")),
        summary=_safe_summary(payload.get("summary")),
        route_value=_safe_label(payload.get("route_value")),
        route_target=_safe_label(payload.get("route_target")),
        stop_reason=_safe_label(payload.get("stop_reason")),
        attempt_ref=_safe_ref(payload.get("attempt_ref")),
        generation=_safe_int(payload.get("generation")),
        refs=_valid_refs(payload.get("refs", [])),
    )


def _append_jsonl(run_root: str | Path, ref: str, payload: Mapping[str, Any]) -> None:
    path = resolve_workspace_ref(run_root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), sort_keys=True, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[Any]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        key = (
            _safe_label(row.get("source")),
            _safe_label(row.get("source_event_id")),
            _safe_label(row.get("event_kind")),
            _safe_label(row.get("stage")),
            _safe_label(row.get("state")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _state_for_flow_event(event: mf.FlowLedgerEvent) -> str:
    if event.status:
        return _safe_label(event.status)
    return _state_for_flow_kind(event.kind.value, "")


def _state_for_flow_kind(kind: str, status: str) -> str:
    if status:
        return status
    if kind in {"started", "step_started", "interaction_recorded", "projections_recorded"}:
        return "running"
    if kind in {"step_recorded", "routed"}:
        return "recorded"
    if kind == "stopped":
        return "completed"
    return "recorded"


def _summary_for_flow_event(event: mf.FlowLedgerEvent) -> str:
    return _summary_for_flow_kind(event.kind.value, _safe_label(event.step_id or "flow"))


def _summary_for_flow_kind(kind: str, step_id: str) -> str:
    labels = {
        "started": "Flow started",
        "step_started": f"Step started: {step_id}",
        "step_recorded": f"Step recorded: {step_id}",
        "interaction_recorded": f"Interaction safe point: {step_id}",
        "routed": f"Route recorded: {step_id}",
        "projections_recorded": "Projections recorded",
        "stopped": "Flow stopped",
    }
    return labels.get(kind, f"Flow event: {kind or 'unknown'}")


def _valid_refs(value: Any) -> list[str]:
    candidates = value if isinstance(value, list) else [value]
    refs = []
    for item in candidates:
        ref = _safe_ref(item)
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_ref(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        return mf.validate_ref(value.strip(), "deepresearch_timeline.ref")
    except mf.ContractValidationError:
        return ""


def _safe_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _safe_label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return "".join(char for char in text if char.isalnum() or char in {"_", "-", ".", ":"})[:120]


def _safe_summary(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "Timeline event"
    text = value.strip()
    allowed = []
    for char in text:
        if char.isalnum() or char in {" ", "_", "-", ".", ":", "/"}:
            allowed.append(char)
    return "".join(allowed)[:160] or "Timeline event"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
