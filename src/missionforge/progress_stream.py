"""User-visible progress streams for MissionForge runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence

from .contracts import ContractValidationError, require_mapping, require_non_empty_str, validate_ref


PROGRESS_STREAM_MOUNT_SCHEMA_VERSION = "missionforge.progress_stream_mount.v1"
PROGRESS_EVENT_SCHEMA_VERSION = "missionforge.progress_event.v1"
PROGRESS_STATES = {"pending", "running", "completed", "failed", "blocked"}
DEFAULT_PROGRESS_REF = "progress/progress.jsonl"


@dataclass(frozen=True)
class ProgressStreamMount:
    """Declaration that a run exposes a user-visible progress stream ref."""

    stream_ref: str = DEFAULT_PROGRESS_REF
    audience: str = "user"
    renderer: str = "plain"
    schema_version: str = PROGRESS_STREAM_MOUNT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProgressStreamMount":
        data = require_mapping(payload, "progress_stream_mount")
        mount = cls(
            stream_ref=validate_ref(data.get("stream_ref", DEFAULT_PROGRESS_REF), "progress_stream_mount.stream_ref"),
            audience=require_non_empty_str(data.get("audience", "user"), "progress_stream_mount.audience"),
            renderer=require_non_empty_str(data.get("renderer", "plain"), "progress_stream_mount.renderer"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PROGRESS_STREAM_MOUNT_SCHEMA_VERSION),
                "progress_stream_mount.schema_version",
            ),
        )
        mount.validate()
        return mount

    def validate(self) -> None:
        if self.schema_version != PROGRESS_STREAM_MOUNT_SCHEMA_VERSION:
            raise ContractValidationError("progress_stream_mount.schema_version is unsupported")
        validate_ref(self.stream_ref, "progress_stream_mount.stream_ref")
        require_non_empty_str(self.audience, "progress_stream_mount.audience")
        require_non_empty_str(self.renderer, "progress_stream_mount.renderer")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "stream_ref": self.stream_ref,
            "audience": self.audience,
            "renderer": self.renderer,
        }


@dataclass(frozen=True)
class ProgressEvent:
    """One safe, user-visible progress update."""

    event_id: str
    stage: str
    state: str
    message: str
    detail: str = ""
    progress_hint: str = ""
    created_at: str = ""
    refs: list[str] = field(default_factory=list)
    schema_version: str = PROGRESS_EVENT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProgressEvent":
        data = require_mapping(payload, "progress_event")
        event = cls(
            event_id=require_non_empty_str(data.get("event_id"), "progress_event.event_id"),
            stage=require_non_empty_str(data.get("stage"), "progress_event.stage"),
            state=_require_progress_state(data.get("state"), "progress_event.state"),
            message=require_non_empty_str(data.get("message"), "progress_event.message"),
            detail=_optional_str(data.get("detail", ""), "progress_event.detail"),
            progress_hint=_optional_str(data.get("progress_hint", ""), "progress_event.progress_hint"),
            created_at=require_non_empty_str(data.get("created_at", ""), "progress_event.created_at"),
            refs=_ref_list(data.get("refs", []), "progress_event.refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PROGRESS_EVENT_SCHEMA_VERSION),
                "progress_event.schema_version",
            ),
        )
        event.validate()
        return event

    def validate(self) -> None:
        if self.schema_version != PROGRESS_EVENT_SCHEMA_VERSION:
            raise ContractValidationError("progress_event.schema_version is unsupported")
        require_non_empty_str(self.event_id, "progress_event.event_id")
        require_non_empty_str(self.stage, "progress_event.stage")
        _require_progress_state(self.state, "progress_event.state")
        require_non_empty_str(self.message, "progress_event.message")
        _optional_str(self.detail, "progress_event.detail")
        _optional_str(self.progress_hint, "progress_event.progress_hint")
        require_non_empty_str(self.created_at, "progress_event.created_at")
        _ref_list(self.refs, "progress_event.refs")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "stage": self.stage,
            "state": self.state,
            "message": self.message,
            "detail": self.detail,
            "progress_hint": self.progress_hint,
            "created_at": self.created_at,
            "refs": list(self.refs),
        }


class ProgressStreamWriter:
    """Append-only writer for a declared progress stream."""

    def __init__(self, workspace: str | Path, *, stream_ref: str = DEFAULT_PROGRESS_REF) -> None:
        self.workspace = Path(workspace).resolve()
        self.stream_ref = validate_ref(stream_ref, "progress_stream.stream_ref")
        self._counter = 0

    def emit(
        self,
        *,
        stage: str,
        state: str,
        message: str,
        detail: str = "",
        progress_hint: str = "",
        refs: Sequence[str] = (),
    ) -> ProgressEvent:
        self._counter += 1
        event = ProgressEvent(
            event_id=f"progress-{self._counter:06d}",
            stage=stage,
            state=state,
            message=message,
            detail=detail,
            progress_hint=progress_hint,
            created_at=datetime.now(timezone.utc).isoformat(),
            refs=list(refs),
        )
        append_progress_event(self.workspace, self.stream_ref, event)
        return event


def append_progress_event(workspace: str | Path, stream_ref: str, event: ProgressEvent) -> None:
    event.validate()
    target = _resolve_workspace_ref(Path(workspace).resolve(), stream_ref)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")


def read_progress_events(workspace: str | Path, stream_ref: str) -> list[ProgressEvent]:
    path = _resolve_workspace_ref(Path(workspace).resolve(), stream_ref)
    if not path.exists():
        return []
    events: list[ProgressEvent] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            events.append(ProgressEvent.from_dict(json.loads(line)))
    return events


def stream_progress(
    runner: Callable[[], Any],
    *,
    workspace: str | Path,
    stream_ref: str = DEFAULT_PROGRESS_REF,
    interval_seconds: float = 0.5,
    output: Any = None,
) -> Any:
    """Run callable while rendering newly appended user-visible progress events."""

    import threading

    stream = output or sys.stderr
    outcome: dict[str, Any] = {}
    rendered_count = _progress_event_count(workspace, stream_ref)

    def target() -> None:
        try:
            outcome["result"] = runner()
        except BaseException as exc:
            outcome["exception"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    while thread.is_alive():
        rendered_count = _render_new_events(
            workspace,
            stream_ref,
            start_index=rendered_count,
            output=stream,
        )
        stream.flush()
        thread.join(timeout=max(interval_seconds, 0.1))
    thread.join()
    _render_new_events(workspace, stream_ref, start_index=rendered_count, output=stream)
    stream.flush()
    if "exception" in outcome:
        raise outcome["exception"]
    return outcome.get("result")


def _progress_event_count(workspace: str | Path, stream_ref: str) -> int:
    try:
        return len(read_progress_events(workspace, stream_ref))
    except (OSError, json.JSONDecodeError, ContractValidationError):
        return 0


def render_progress_event(event: ProgressEvent) -> str:
    prefix = f"[{event.progress_hint}] " if event.progress_hint else ""
    line = f"{prefix}{event.message}"
    if event.detail:
        return f"{line}\n      {event.detail}"
    return line


def _render_new_events(
    workspace: str | Path,
    stream_ref: str,
    *,
    start_index: int,
    output: Any,
) -> int:
    try:
        events = read_progress_events(workspace, stream_ref)
    except (OSError, json.JSONDecodeError, ContractValidationError):
        return start_index
    for event in events[start_index:]:
        output.write(render_progress_event(event) + "\n")
    return len(events)


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "progress_stream.ref")
    path = (root / safe_ref).resolve()
    if path != root and root not in path.parents:
        raise ContractValidationError("progress stream ref escapes workspace")
    return path


def _require_progress_state(value: Any, field_name: str) -> str:
    state = require_non_empty_str(value, field_name)
    if state not in PROGRESS_STATES:
        raise ContractValidationError(f"{field_name} must be one of {sorted(PROGRESS_STATES)}")
    return state


def _optional_str(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ContractValidationError(f"{field_name} must be a string")
    return value


def _ref_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    return [validate_ref(item, f"{field_name}[]") for item in value]
