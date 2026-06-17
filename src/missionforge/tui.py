"""Read-only terminal observer for MissionForge workspaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Mapping, Sequence

from .contracts import ContractValidationError, require_mapping, validate_ref


TUI_SNAPSHOT_SCHEMA_VERSION = "missionforge.tui_snapshot.v1"
DEFAULT_EVENT_PATTERNS = (
    "**/*events*.jsonl",
    "**/*event*.jsonl",
    "**/*ledger*.jsonl",
    "**/*observations*.jsonl",
)
DEFAULT_REPORT_PATTERNS = (
    "**/*execution_report.json",
    "**/*run_result.json",
    "**/*result.json",
    "**/*boundary_validation.json",
    "**/*extension_load_report.json",
    "**/*metrics.json",
)


@dataclass(frozen=True)
class TuiFileSummary:
    """Metadata-only summary of a workspace file."""

    ref: str
    kind: str
    exists: bool
    size_bytes: int = 0
    modified_at: str = ""
    line_count: int = 0
    status: str | None = None
    event_type: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "kind": self.kind,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "line_count": self.line_count,
            "status": self.status,
            "event_type": self.event_type,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class TuiSnapshot:
    """Read-only status snapshot for a MissionForge workspace/run ref."""

    workspace_scope: str
    run_ref: str
    generated_at: str
    status: str
    event_files: list[TuiFileSummary] = field(default_factory=list)
    report_files: list[TuiFileSummary] = field(default_factory=list)
    artifact_files: list[TuiFileSummary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema_version: str = TUI_SNAPSHOT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workspace_scope": self.workspace_scope,
            "run_scope": self.run_ref,
            "generated_at": self.generated_at,
            "status": self.status,
            "event_files": [item.to_dict() for item in self.event_files],
            "report_files": [item.to_dict() for item in self.report_files],
            "artifact_files": [item.to_dict() for item in self.artifact_files],
            "warnings": list(self.warnings),
        }


def build_tui_snapshot(
    workspace: str | Path = ".",
    *,
    run_ref: str = ".",
    max_files: int = 60,
    event_tail: int = 8,
) -> TuiSnapshot:
    """Build a refs-first terminal observer snapshot without mutating state."""

    root = Path(workspace).resolve()
    safe_run_ref = "." if run_ref == "." else validate_ref(run_ref, "tui.run_ref")
    run_root = root if safe_run_ref == "." else _resolve_workspace_ref(root, safe_run_ref)
    generated_at = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []
    if not run_root.exists():
        warnings.append(f"run ref is missing: {safe_run_ref}")
        return TuiSnapshot(
            workspace_scope=".",
            run_ref=safe_run_ref,
            generated_at=generated_at,
            status="missing",
            warnings=warnings,
        )
    event_files = _event_file_summaries(root, run_root, max_files=max_files, event_tail=event_tail)
    report_files = _report_file_summaries(root, run_root, max_files=max_files)
    artifact_files = _artifact_file_summaries(root, run_root, max_files=max_files)
    status = _snapshot_status(event_files, report_files, warnings)
    return TuiSnapshot(
        workspace_scope=".",
        run_ref=safe_run_ref,
        generated_at=generated_at,
        status=status,
        event_files=event_files,
        report_files=report_files,
        artifact_files=artifact_files,
        warnings=warnings,
    )


def render_tui_snapshot(snapshot: TuiSnapshot, *, width: int | None = None) -> str:
    """Render a snapshot as plain terminal text."""

    terminal_width = width or shutil.get_terminal_size((100, 24)).columns
    line_width = max(72, min(terminal_width, 140))
    lines = [
        _rule("MissionForge TUI", line_width),
        f"workspace:     {snapshot.workspace_scope}",
        f"run_ref:       {snapshot.run_ref}",
        f"status:        {snapshot.status}",
        f"updated:       {snapshot.generated_at}",
    ]
    if snapshot.warnings:
        lines.extend(["", _section("Warnings")])
        lines.extend(f"- {warning}" for warning in snapshot.warnings)
    lines.extend(["", _section("Events")])
    lines.extend(_render_event_files(snapshot.event_files) or ["- no event files found"])
    lines.extend(["", _section("Reports")])
    lines.extend(_render_report_files(snapshot.report_files) or ["- no report files found"])
    lines.extend(["", _section("Artifacts")])
    lines.extend(_render_artifact_files(snapshot.artifact_files) or ["- no artifact files found"])
    return "\n".join(_truncate_line(line, line_width) for line in lines) + "\n"


def watch_tui(
    workspace: str | Path = ".",
    *,
    run_ref: str = ".",
    interval_seconds: float = 2.0,
    max_files: int = 60,
    event_tail: int = 8,
    output: Any = None,
) -> int:
    """Refresh a read-only terminal dashboard until interrupted."""

    stream = output or sys.stdout
    try:
        while True:
            snapshot = build_tui_snapshot(
                workspace,
                run_ref=run_ref,
                max_files=max_files,
                event_tail=event_tail,
            )
            stream.write("\x1b[2J\x1b[H")
            stream.write(render_tui_snapshot(snapshot))
            stream.flush()
            time.sleep(max(interval_seconds, 0.2))
    except KeyboardInterrupt:
        stream.write("\n")
        stream.flush()
        return 0


def _event_file_summaries(root: Path, run_root: Path, *, max_files: int, event_tail: int) -> list[TuiFileSummary]:
    files = _matching_files(run_root, DEFAULT_EVENT_PATTERNS, max_files=max_files)
    return [_summarize_jsonl(root, path, event_tail=event_tail, kind="event_log") for path in files]


def _report_file_summaries(root: Path, run_root: Path, *, max_files: int) -> list[TuiFileSummary]:
    files = _matching_files(run_root, DEFAULT_REPORT_PATTERNS, max_files=max_files)
    return [_summarize_json(root, path, kind=_report_kind(path)) for path in files]


def _artifact_file_summaries(root: Path, run_root: Path, *, max_files: int) -> list[TuiFileSummary]:
    artifact_dirs = [run_root / name for name in ("reports", "sources", "packages", "compiled", "reviews")]
    files: list[Path] = []
    for directory in artifact_dirs:
        if directory.is_dir():
            files.extend(path for path in directory.rglob("*") if path.is_file())
    return [_summarize_file(root, path, kind="artifact") for path in _recent(files, max_files)]


def _matching_files(root: Path, patterns: Sequence[str], *, max_files: int) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                files.append(path)
    return _recent(files, max_files)


def _recent(files: Sequence[Path], max_files: int) -> list[Path]:
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)[: max(max_files, 0)]


def _summarize_file(root: Path, path: Path, *, kind: str) -> TuiFileSummary:
    stat = path.stat()
    return TuiFileSummary(
        ref=_relative_ref(root, path),
        kind=kind,
        exists=True,
        size_bytes=stat.st_size,
        modified_at=_mtime_iso(stat.st_mtime),
    )


def _summarize_json(root: Path, path: Path, *, kind: str) -> TuiFileSummary:
    base = _summarize_file(root, path, kind=kind)
    details: dict[str, Any] = {}
    status: str | None = None
    try:
        payload = require_mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
        status = _optional_str(payload.get("status") or payload.get("boundary_status") or payload.get("worker_status"))
        details = _json_status_details(payload)
    except Exception as exc:
        status = "unreadable"
        details = {"error_type": type(exc).__name__}
    return TuiFileSummary(
        **{**base.to_dict(), "status": status, "details": details},
    )


def _summarize_jsonl(root: Path, path: Path, *, event_tail: int, kind: str) -> TuiFileSummary:
    base = _summarize_file(root, path, kind=kind)
    line_count = 0
    tail: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                line_count += 1
                try:
                    record = require_mapping(json.loads(line), f"{path}[]")
                except Exception:
                    record = {"event_type": "invalid_jsonl_line"}
                tail.append(_event_tail_record(record))
                if len(tail) > event_tail:
                    tail.pop(0)
    except OSError as exc:
        tail = [{"event_type": "unreadable", "message": type(exc).__name__}]
    latest = tail[-1] if tail else {}
    return TuiFileSummary(
        **{
            **base.to_dict(),
            "line_count": line_count,
            "status": _optional_str(latest.get("status")),
            "event_type": _optional_str(latest.get("event_type") or latest.get("event_kind") or latest.get("type")),
            "details": {"tail": tail},
        },
    )


def _event_tail_record(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = record.get("payload") if isinstance(record.get("payload"), Mapping) else {}
    return {
        "event_type": _optional_str(record.get("event_type") or record.get("event_kind") or record.get("type")),
        "status": _optional_str(record.get("status") or payload.get("status")),
        "call_id": _optional_str(record.get("call_id") or payload.get("call_id")),
        "created_at": _optional_str(record.get("created_at") or record.get("timestamp") or record.get("recorded_at")),
        "refs": _short_refs(record),
    }


def _short_refs(record: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("ref", "refs", "source_refs", "evidence_refs", "artifact_refs"):
        value = record.get(key)
        if isinstance(value, str):
            refs.append(value)
        elif isinstance(value, list):
            refs.extend(item for item in value if isinstance(item, str))
    payload = record.get("payload")
    if isinstance(payload, Mapping):
        for key in ("output_ref", "events_ref", "metrics_ref", "extension_load_report_ref", "context_observations_ref"):
            value = payload.get(key)
            if isinstance(value, str):
                refs.append(value)
    return _valid_refs(refs)[:5]


def _json_status_details(payload: Mapping[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    for key in (
        "request_id",
        "call_id",
        "review_decision",
        "worker_status",
        "boundary_status",
        "extension_count",
        "loadable_count",
        "rejected_count",
    ):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            details[key] = value
    metrics = payload.get("metrics")
    if isinstance(metrics, Mapping):
        for key in ("duration_ms", "tool_call_count", "total_tokens", "token_count", "turn_count"):
            value = metrics.get(key)
            if isinstance(value, (int, float, str)):
                details[key] = value
    if isinstance(payload.get("loaded_extensions"), list):
        details["loaded_extensions"] = len(payload["loaded_extensions"])
    if isinstance(payload.get("rejected_extensions"), list):
        details["rejected_extensions"] = len(payload["rejected_extensions"])
    return details


def _valid_refs(refs: Sequence[str]) -> list[str]:
    safe_refs: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        try:
            safe_ref = validate_ref(ref, "tui.ref")
        except ContractValidationError:
            continue
        if safe_ref not in seen:
            seen.add(safe_ref)
            safe_refs.append(safe_ref)
    return safe_refs


def _snapshot_status(
    event_files: Sequence[TuiFileSummary],
    report_files: Sequence[TuiFileSummary],
    warnings: Sequence[str],
) -> str:
    if warnings:
        return "warning"
    statuses = [item.status for item in [*event_files, *report_files] if item.status]
    if any(status in {"failed", "rejected", "unreadable"} for status in statuses):
        return "failed"
    if any(status in {"running", "started", "in_progress"} for status in statuses):
        return "running"
    if any(status in {"completed", "accepted", "draft_ready", "passed"} for status in statuses):
        return "active"
    return "observing"


def _render_event_files(files: Sequence[TuiFileSummary]) -> list[str]:
    lines: list[str] = []
    for item in files[:8]:
        lines.append(
            f"- {item.ref} lines={item.line_count} latest={item.event_type or '-'} "
            f"status={item.status or '-'}"
        )
        tail = item.details.get("tail") if isinstance(item.details, Mapping) else None
        if isinstance(tail, list):
            for record in tail[-3:]:
                if isinstance(record, Mapping):
                    lines.append(
                        "  "
                        f"* {record.get('event_type') or '-'} "
                        f"status={record.get('status') or '-'} "
                        f"call={record.get('call_id') or '-'}"
                    )
    return lines


def _render_report_files(files: Sequence[TuiFileSummary]) -> list[str]:
    lines: list[str] = []
    for item in files[:12]:
        details = _compact_details(item.details)
        lines.append(f"- {item.ref} status={item.status or '-'} size={item.size_bytes}B {details}")
    return lines


def _render_artifact_files(files: Sequence[TuiFileSummary]) -> list[str]:
    return [f"- {item.ref} size={item.size_bytes}B modified={item.modified_at}" for item in files[:16]]


def _compact_details(details: Mapping[str, Any]) -> str:
    parts = [f"{key}={value}" for key, value in details.items() if value not in (None, "", [])]
    return " ".join(parts[:8])


def _report_kind(path: Path) -> str:
    name = path.name
    if "metrics" in name:
        return "metrics"
    if "extension_load_report" in name:
        return "extension_load_report"
    if "boundary" in name:
        return "boundary_validation"
    if "execution_report" in name:
        return "execution_report"
    return "report"


def _relative_ref(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ContractValidationError("tui file escapes workspace") from exc


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    path = (root / ref).resolve()
    if path != root and root not in path.parents:
        raise ContractValidationError("tui ref escapes workspace")
    return path


def _mtime_iso(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _rule(title: str, width: int) -> str:
    text = f" {title} "
    if len(text) >= width:
        return text.strip()
    left = (width - len(text)) // 2
    right = width - len(text) - left
    return f"{'=' * left}{text}{'=' * right}"


def _section(title: str) -> str:
    return f"[{title}]"


def _truncate_line(line: str, width: int) -> str:
    if len(line) <= width:
        return line
    return line[: max(0, width - 3)] + "..."
