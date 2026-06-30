"""Safe user-visible progress projection for PiWorker runtime events."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from .contracts import ContractValidationError, validate_ref
from .ref_store import RefStore


PiWorkerProgressSink = Callable[[dict[str, Any]], None]
PiWorkerProgressStoreTarget = RefStore | str | Path


@dataclass(frozen=True)
class PiWorkerProgressBridgeConfig:
    """Runtime progress projection tuning."""

    poll_interval_seconds: float = 0.5
    min_emit_interval_seconds: float = 2.0
    heartbeat_interval_seconds: float = 30.0
    stream_delta_chars: int = 2048
    artifact_delta_bytes: int = 4096


@dataclass(frozen=True)
class _ProgressSummary:
    key: str
    message: str
    detail: str = ""
    refs: tuple[str, ...] = ()
    progress_value: int | None = None
    force: bool = False


class PiWorkerProgressBridge:
    """Tail PiWorker runtime evidence and emit safe, throttled progress events.

    The bridge is intentionally observational. It does not decide semantic
    status and it never emits raw prompt text, model output, stdout, stderr, or
    tool result bodies.
    """

    def __init__(
        self,
        *,
        workspace: PiWorkerProgressStoreTarget,
        call_id: str,
        events_ref: str,
        expected_output_refs: Sequence[str] = (),
        progress_sink: PiWorkerProgressSink | None = None,
        worker_label: str | None = None,
        stage: str = "piworker_runtime",
        progress_hint: str = "piworker",
        config: PiWorkerProgressBridgeConfig | None = None,
    ) -> None:
        self.workspace: PiWorkerProgressStoreTarget = Path(workspace).resolve() if isinstance(workspace, (str, Path)) else workspace
        self.call_id = call_id
        self.worker_label = worker_label or call_id
        self.events_ref = validate_ref(events_ref, "piworker_progress.events_ref")
        self.expected_output_refs = [validate_ref(ref, "piworker_progress.expected_output_refs[]") for ref in expected_output_refs]
        self.progress_sink = progress_sink
        self.stage = stage
        self.progress_hint = progress_hint
        self.config = config or PiWorkerProgressBridgeConfig()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._offset = 0
        self._pending = b""
        self._last_emit_monotonic = 0.0
        self._last_heartbeat_monotonic = 0.0
        self._last_event_monotonic = 0.0
        self._last_key: str | None = None
        self._last_progress_by_key: dict[str, int] = {}
        self._artifact_sizes: dict[str, int] = {}

    def start(self) -> None:
        if self.progress_sink is None or self._thread is not None:
            return
        self._emit(
            _ProgressSummary(
                key="runtime-started",
                message=f"PiWorker runtime started: {self.worker_label}.",
                detail=f"Watching runtime events at {self.events_ref}.",
                refs=(self.events_ref,),
                force=True,
            )
        )
        self._thread = threading.Thread(target=self._run, name=f"piworker-progress-{self.call_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=max(self.config.poll_interval_seconds * 2, 0.2))
        self.poll_once()

    def poll_once(self) -> int:
        emitted = 0
        for event in self._read_new_events():
            summary = _summarize_runtime_event(self.worker_label, event)
            if summary is None:
                continue
            self._last_event_monotonic = time.monotonic()
            if self._emit(summary):
                emitted += 1
        for summary in self._artifact_summaries():
            if self._emit(summary):
                emitted += 1
        if emitted == 0:
            emitted += self._emit_heartbeat()
        return emitted

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(max(self.config.poll_interval_seconds, 0.05))

    def _read_new_events(self) -> list[Mapping[str, Any]]:
        safe_events_ref = validate_ref(self.events_ref, "piworker_progress.events_ref")
        if isinstance(self.workspace, (str, Path)):
            path = _resolve_workspace_ref(Path(self.workspace).resolve(), safe_events_ref)
            if not path.is_file():
                return []
            with path.open("rb") as handle:
                handle.seek(self._offset)
                chunk = handle.read()
                self._offset = handle.tell()
        else:
            if not self.workspace.exists(safe_events_ref):
                return []
            body = self.workspace.read_bytes(safe_events_ref)
            if self._offset > len(body):
                self._offset = 0
                self._pending = b""
            chunk = body[self._offset:]
            self._offset = len(body)
        if not chunk:
            return []
        data = self._pending + chunk
        lines = data.split(b"\n")
        self._pending = lines.pop() if data and not data.endswith(b"\n") else b""
        events: list[Mapping[str, Any]] = []
        for raw in lines:
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, Mapping):
                events.append(payload)
        return events

    def _artifact_summaries(self) -> list[_ProgressSummary]:
        summaries: list[_ProgressSummary] = []
        for ref in self.expected_output_refs:
            size = _artifact_size(self.workspace, ref)
            if size is None:
                continue
            previous = self._artifact_sizes.get(ref)
            self._artifact_sizes[ref] = size
            if previous is None:
                summaries.append(
                    _ProgressSummary(
                        key=f"artifact:{ref}",
                        message=f"PiWorker wrote artifact {ref}.",
                        detail=f"Artifact size is {_format_bytes(size)}.",
                        refs=(ref,),
                        progress_value=size,
                        force=True,
                    )
                )
            elif size >= previous + self.config.artifact_delta_bytes:
                summaries.append(
                    _ProgressSummary(
                        key=f"artifact:{ref}",
                        message=f"PiWorker is updating artifact {ref}.",
                        detail=f"Artifact size is {_format_bytes(size)}.",
                        refs=(ref,),
                        progress_value=size,
                    )
                )
        return summaries

    def _emit_heartbeat(self) -> int:
        now = time.monotonic()
        if self.config.heartbeat_interval_seconds <= 0:
            return 0
        if now - self._last_heartbeat_monotonic < self.config.heartbeat_interval_seconds:
            return 0
        if self._last_emit_monotonic == 0:
            return 0
        latest = "no runtime event yet" if self._last_event_monotonic == 0 else f"latest runtime event {_format_seconds(now - self._last_event_monotonic)} ago"
        if self._emit(
            _ProgressSummary(
                key="heartbeat",
                message=f"PiWorker runtime is still running: {self.worker_label}.",
                detail=latest,
                refs=(self.events_ref,),
                force=True,
            )
        ):
            self._last_heartbeat_monotonic = now
            return 1
        return 0

    def _emit(self, summary: _ProgressSummary) -> bool:
        if self.progress_sink is None:
            return False
        now = time.monotonic()
        if not summary.force and now - self._last_emit_monotonic < self.config.min_emit_interval_seconds:
            return False
        if not summary.force and summary.key == self._last_key:
            previous_value = self._last_progress_by_key.get(summary.key)
            if summary.progress_value is None:
                return False
            if previous_value is not None and summary.progress_value - previous_value < self.config.stream_delta_chars:
                return False
        refs = [ref for ref in summary.refs if _is_safe_ref(ref)]
        payload = {
            "stage": self.stage,
            "state": "running",
            "message": summary.message,
            "detail": summary.detail,
            "progress_hint": self.progress_hint,
            "refs": refs,
        }
        try:
            self.progress_sink(payload)
        except Exception:
            return False
        self._last_emit_monotonic = now
        self._last_key = summary.key
        if summary.progress_value is not None:
            self._last_progress_by_key[summary.key] = summary.progress_value
        return True


def _summarize_runtime_event(worker_label: str, event: Mapping[str, Any]) -> _ProgressSummary | None:
    event_type = _event_type(event)
    payload = event.get("payload")
    payload_map = payload if isinstance(payload, Mapping) else {}
    if event_type in {"message_update", "message_end", "message_start"}:
        message = payload_map.get("message")
        if isinstance(message, Mapping):
            return _summarize_message(worker_label, message)
    if event_type in {"tool_execution_start", "tool_execution_update", "tool_execution_end"}:
        return _summarize_tool_execution(worker_label, payload_map, event_type)
    if event_type == "tool_observation":
        return _summarize_tool_observation(worker_label, payload_map)
    return None


def _event_type(event: Mapping[str, Any]) -> str:
    value = event.get("event_type")
    if isinstance(value, str) and value:
        return value
    payload = event.get("payload")
    if isinstance(payload, Mapping):
        nested = payload.get("type")
        if isinstance(nested, str):
            return nested
    return ""


def _summarize_message(worker_label: str, message: Mapping[str, Any]) -> _ProgressSummary | None:
    content = message.get("content")
    if not isinstance(content, list):
        return None
    for block in reversed(content):
        if not isinstance(block, Mapping):
            continue
        tool_name = block.get("name")
        if not isinstance(tool_name, str):
            continue
        args = block.get("arguments")
        args_map = args if isinstance(args, Mapping) else {}
        return _tool_summary(worker_label, tool_name, args_map, "tool-call")
    return None


def _summarize_tool_execution(worker_label: str, payload: Mapping[str, Any], event_type: str) -> _ProgressSummary | None:
    tool_name = payload.get("toolName") or payload.get("tool_name")
    if not isinstance(tool_name, str):
        return None
    args = payload.get("args")
    args_map = args if isinstance(args, Mapping) else {}
    phase = {
        "tool_execution_start": "started",
        "tool_execution_update": "running",
        "tool_execution_end": "finished",
    }.get(event_type, "running")
    return _tool_summary(worker_label, tool_name, args_map, phase)


def _summarize_tool_observation(worker_label: str, payload: Mapping[str, Any]) -> _ProgressSummary | None:
    source_ref = payload.get("source_ref") or payload.get("ref")
    tool_name = payload.get("tool_name") or payload.get("toolName") or "tool"
    status = payload.get("status") if isinstance(payload.get("status"), str) else "recorded"
    if isinstance(source_ref, str) and _is_safe_ref(source_ref):
        details = []
        if isinstance(payload.get("content_lines"), int):
            details.append(f"{payload['content_lines']} lines")
        if isinstance(payload.get("content_bytes"), int):
            details.append(_format_bytes(payload["content_bytes"]))
        return _ProgressSummary(
            key=f"observation:{tool_name}:{source_ref}:{status}",
            message=f"PiWorker {worker_label} recorded {tool_name} observation for {source_ref}.",
            detail=", ".join(details) if details else f"status={status}",
            refs=(source_ref,),
        )
    return None


def _tool_summary(worker_label: str, tool_name: str, args: Mapping[str, Any], phase: str) -> _ProgressSummary:
    ref = _tool_ref(args)
    safe_ref = ref if ref and _is_safe_ref(ref) else None
    content_len = _content_length(args.get("content"))
    if tool_name == "read" and safe_ref:
        return _ProgressSummary(
            key=f"tool:{tool_name}:{safe_ref}:{phase}",
            message=f"PiWorker {worker_label} is reading {safe_ref}.",
            detail=f"Runtime tool phase: {phase}.",
            refs=(safe_ref,),
        )
    if tool_name in {"write", "edit"} and safe_ref:
        detail_parts = [f"Runtime tool phase: {phase}."]
        if content_len is not None:
            detail_parts.append(f"Received {_format_count(content_len, 'char')} for the pending write.")
        return _ProgressSummary(
            key=f"tool:{tool_name}:{safe_ref}",
            message=f"PiWorker {worker_label} is {_tool_verb(tool_name)} {safe_ref}.",
            detail=" ".join(detail_parts),
            refs=(safe_ref,),
            progress_value=content_len,
        )
    if tool_name == "bash":
        return _ProgressSummary(
            key=f"tool:bash:{phase}",
            message=f"PiWorker {worker_label} is running a bash tool call.",
            detail=f"Runtime tool phase: {phase}. Command text is not shown in user progress.",
        )
    return _ProgressSummary(
        key=f"tool:{tool_name}:{phase}",
        message=f"PiWorker {worker_label} is using tool {tool_name}.",
        detail=f"Runtime tool phase: {phase}.",
        refs=(safe_ref,) if safe_ref else (),
    )


def _tool_ref(args: Mapping[str, Any]) -> str | None:
    for key in ("path", "ref", "source_ref", "target_ref"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _content_length(value: Any) -> int | None:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, Mapping):
        length = value.get("length")
        if isinstance(length, int) and length >= 0:
            return length
    return None


def _tool_verb(tool_name: str) -> str:
    if tool_name == "write":
        return "writing"
    if tool_name == "edit":
        return "editing"
    return f"using {tool_name} on"


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "piworker_progress.ref")
    path = (root / safe_ref).resolve()
    if path != root and root not in path.parents:
        raise ContractValidationError("piworker progress ref escapes workspace")
    return path


def _artifact_size(workspace: PiWorkerProgressStoreTarget, ref: str) -> int | None:
    safe_ref = validate_ref(ref, "piworker_progress.ref")
    if isinstance(workspace, (str, Path)):
        path = _resolve_workspace_ref(Path(workspace).resolve(), safe_ref)
        if not path.is_file():
            return None
        return path.stat().st_size
    if not workspace.exists(safe_ref):
        return None
    return len(workspace.read_bytes(safe_ref))


def _is_safe_ref(value: str) -> bool:
    try:
        validate_ref(value, "piworker_progress.ref")
    except ContractValidationError:
        return False
    return True


def _format_count(value: int, unit: str) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}K {unit}s"
    return f"{value} {unit}s"


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f}MB"
    if value >= 1024:
        return f"{value / 1024:.1f}KB"
    return f"{value}B"


def _format_seconds(value: float) -> str:
    seconds = max(0, int(value))
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m{seconds % 60}s"
