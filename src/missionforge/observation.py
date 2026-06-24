"""Product-neutral observation and safe-point control primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from .interaction import FileInteractionPort, InteractionDelivery, UserEvent, UserEventKind


RUN_EVENTS_REF = "observation/run_events.jsonl"
RUN_SNAPSHOT_REF = "observation/run_snapshot.json"
RUN_EVENT_SCHEMA_VERSION = "missionforge.run_event.v1"
RUN_SNAPSHOT_SCHEMA_VERSION = "missionforge.run_snapshot.v1"


class RunEventKind(StrEnum):
    """Product-neutral runtime boundary event kinds."""

    RUN_STARTED = "run_started"
    CONTRACT_FROZEN = "contract_frozen"
    STEP_COMPILED = "step_compiled"
    CONTEXT_PROJECTED = "context_projected"
    SANDBOX_STARTED = "sandbox_started"
    TOOL_REQUESTED = "tool_requested"
    TOOL_ALLOWED = "tool_allowed"
    TOOL_DENIED = "tool_denied"
    ARTIFACT_COMMITTED = "artifact_committed"
    ROUTE_DECIDED = "route_decided"
    SAFE_POINT_REACHED = "safe_point_reached"
    USER_INTERVENTION_RECEIVED = "user_intervention_received"
    STEP_COMPLETED = "step_completed"
    JUDGE_ACCEPTED = "judge_accepted"
    JUDGE_REJECTED = "judge_rejected"
    RUN_STOPPED = "run_stopped"


class RunSnapshotStatus(StrEnum):
    """Generic inspectable run status values."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RunEvent:
    """One refs-first runtime boundary event."""

    event_id: str
    run_id: str
    kind: RunEventKind
    status: str = ""
    step_id: str = ""
    role: str = ""
    refs: list[str] = field(default_factory=list)
    created_at: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = RUN_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        run_id: str,
        kind: RunEventKind | str,
        status: str = "",
        step_id: str = "",
        role: str = "",
        refs: list[str] | None = None,
        created_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "RunEvent":
        return cls(
            event_id=_safe_id(event_id, "run_event.event_id"),
            run_id=_safe_id(run_id, "run_event.run_id"),
            kind=require_enum(kind, RunEventKind, "run_event.kind"),
            status=_optional_safe_id(status, "run_event.status"),
            step_id=_optional_safe_target(step_id, "run_event.step_id"),
            role=_optional_safe_target(role, "run_event.role"),
            refs=_ref_list([] if refs is None else refs, "run_event.refs"),
            created_at=created_at or _utc_now(),
            metadata=_metadata({} if metadata is None else metadata, "run_event.metadata"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunEvent":
        data = _refs_only_mapping(payload, "run_event")
        event = cls(
            event_id=_safe_id(data.get("event_id"), "run_event.event_id"),
            run_id=_safe_id(data.get("run_id"), "run_event.run_id"),
            kind=require_enum(data.get("kind"), RunEventKind, "run_event.kind"),
            status=_optional_safe_id(data.get("status", ""), "run_event.status"),
            step_id=_optional_safe_target(data.get("step_id", ""), "run_event.step_id"),
            role=_optional_safe_target(data.get("role", ""), "run_event.role"),
            refs=_ref_list(data.get("refs", []), "run_event.refs"),
            created_at=require_non_empty_str(data.get("created_at"), "run_event.created_at"),
            metadata=_metadata(data.get("metadata", {}), "run_event.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", RUN_EVENT_SCHEMA_VERSION),
                "run_event.schema_version",
            ),
        )
        event.validate()
        return event

    def validate(self) -> None:
        _require_schema(self.schema_version, RUN_EVENT_SCHEMA_VERSION, "run_event.schema_version")
        _safe_id(self.event_id, "run_event.event_id")
        _safe_id(self.run_id, "run_event.run_id")
        require_enum(self.kind, RunEventKind, "run_event.kind")
        _optional_safe_id(self.status, "run_event.status")
        _optional_safe_target(self.step_id, "run_event.step_id")
        _optional_safe_target(self.role, "run_event.role")
        _unique_refs(self.refs, "run_event.refs")
        require_non_empty_str(self.created_at, "run_event.created_at")
        _metadata(self.metadata, "run_event.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "kind": self.kind.value,
            "status": self.status,
            "step_id": self.step_id,
            "role": self.role,
            "refs": list(self.refs),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RunSnapshot:
    """Refs-first inspectable run state for host UIs and debuggers."""

    run_id: str
    status: RunSnapshotStatus | str
    current_step_id: str = ""
    current_role: str = ""
    latest_event_id: str = ""
    latest_event_ref: str = RUN_EVENTS_REF
    flow_ledger_ref: str = ""
    flow_result_ref: str = ""
    progress_ref: str = ""
    last_safe_point_ref: str = ""
    pending_user_event_count: int = 0
    step_record_refs: list[str] = field(default_factory=list)
    context_projection_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = RUN_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunSnapshot":
        data = _refs_only_mapping(payload, "run_snapshot")
        snapshot = cls(
            run_id=_safe_id(data.get("run_id"), "run_snapshot.run_id"),
            status=require_enum(data.get("status"), RunSnapshotStatus, "run_snapshot.status"),
            current_step_id=_optional_safe_target(data.get("current_step_id", ""), "run_snapshot.current_step_id"),
            current_role=_optional_safe_target(data.get("current_role", ""), "run_snapshot.current_role"),
            latest_event_id=_optional_safe_id(data.get("latest_event_id", ""), "run_snapshot.latest_event_id"),
            latest_event_ref=_optional_ref_or_default(data.get("latest_event_ref", RUN_EVENTS_REF), "run_snapshot.latest_event_ref"),
            flow_ledger_ref=_optional_ref(data.get("flow_ledger_ref", ""), "run_snapshot.flow_ledger_ref"),
            flow_result_ref=_optional_ref(data.get("flow_result_ref", ""), "run_snapshot.flow_result_ref"),
            progress_ref=_optional_ref(data.get("progress_ref", ""), "run_snapshot.progress_ref"),
            last_safe_point_ref=_optional_ref(data.get("last_safe_point_ref", ""), "run_snapshot.last_safe_point_ref"),
            pending_user_event_count=_non_negative_int(
                data.get("pending_user_event_count", 0),
                "run_snapshot.pending_user_event_count",
            ),
            step_record_refs=_ref_list(data.get("step_record_refs", []), "run_snapshot.step_record_refs"),
            context_projection_refs=_ref_list(
                data.get("context_projection_refs", []),
                "run_snapshot.context_projection_refs",
            ),
            artifact_refs=_ref_list(data.get("artifact_refs", []), "run_snapshot.artifact_refs"),
            metric_refs=_ref_list(data.get("metric_refs", []), "run_snapshot.metric_refs"),
            metadata=_metadata(data.get("metadata", {}), "run_snapshot.metadata"),
            schema_version=require_non_empty_str(
                data.get("schema_version", RUN_SNAPSHOT_SCHEMA_VERSION),
                "run_snapshot.schema_version",
            ),
        )
        snapshot.validate()
        return snapshot

    def validate(self) -> None:
        _require_schema(self.schema_version, RUN_SNAPSHOT_SCHEMA_VERSION, "run_snapshot.schema_version")
        _safe_id(self.run_id, "run_snapshot.run_id")
        require_enum(self.status, RunSnapshotStatus, "run_snapshot.status")
        _optional_safe_target(self.current_step_id, "run_snapshot.current_step_id")
        _optional_safe_target(self.current_role, "run_snapshot.current_role")
        _optional_safe_id(self.latest_event_id, "run_snapshot.latest_event_id")
        _optional_ref_or_default(self.latest_event_ref, "run_snapshot.latest_event_ref")
        _optional_ref(self.flow_ledger_ref, "run_snapshot.flow_ledger_ref")
        _optional_ref(self.flow_result_ref, "run_snapshot.flow_result_ref")
        _optional_ref(self.progress_ref, "run_snapshot.progress_ref")
        _optional_ref(self.last_safe_point_ref, "run_snapshot.last_safe_point_ref")
        _non_negative_int(self.pending_user_event_count, "run_snapshot.pending_user_event_count")
        _unique_refs(self.step_record_refs, "run_snapshot.step_record_refs")
        _unique_refs(self.context_projection_refs, "run_snapshot.context_projection_refs")
        _unique_refs(self.artifact_refs, "run_snapshot.artifact_refs")
        _unique_refs(self.metric_refs, "run_snapshot.metric_refs")
        _metadata(self.metadata, "run_snapshot.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        status = self.status if isinstance(self.status, RunSnapshotStatus) else RunSnapshotStatus(self.status)
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "status": status.value,
            "current_step_id": self.current_step_id,
            "current_role": self.current_role,
            "latest_event_id": self.latest_event_id,
            "latest_event_ref": self.latest_event_ref,
            "flow_ledger_ref": self.flow_ledger_ref,
            "flow_result_ref": self.flow_result_ref,
            "progress_ref": self.progress_ref,
            "last_safe_point_ref": self.last_safe_point_ref,
            "pending_user_event_count": self.pending_user_event_count,
            "step_record_refs": list(self.step_record_refs),
            "context_projection_refs": list(self.context_projection_refs),
            "artifact_refs": list(self.artifact_refs),
            "metric_refs": list(self.metric_refs),
            "metadata": dict(self.metadata),
        }


class ControlPort(Protocol):
    """Safe-point control interface for host applications."""

    def inject_message(self, *, run_id: str, text: str, target: str = "flow") -> UserEvent:
        """Queue user guidance for the next safe point."""

    def pause(self, *, run_id: str, target: str = "flow") -> UserEvent:
        """Request pause at the next safe point."""

    def cancel(self, *, run_id: str, target: str = "flow") -> UserEvent:
        """Request cancellation at the next safe point."""

    def request_revision(self, *, run_id: str, text: str, target: str = "flow") -> UserEvent:
        """Request an explicit contract revision."""

    def resume(self, *, run_id: str, target: str = "flow") -> UserEvent:
        """Record a host-level resume request."""

    def stop_after_current_turn(self, *, run_id: str, target: str = "flow") -> UserEvent:
        """Request stop at the next safe point after the active turn."""

    def force_checkpoint(self, *, run_id: str, target: str = "flow") -> UserEvent:
        """Request checkpoint at a safe point."""


class FileControlPort:
    """ControlPort implementation backed by FileInteractionPort."""

    def __init__(self, interaction_port: FileInteractionPort) -> None:
        self.interaction_port = interaction_port

    def inject_message(self, *, run_id: str, text: str, target: str = "flow") -> UserEvent:
        return self.interaction_port.submit_text(
            text,
            run_id=run_id,
            target=target,
            kind=UserEventKind.MESSAGE,
            delivery=InteractionDelivery.NEXT_SAFE_POINT,
        )

    def pause(self, *, run_id: str, target: str = "flow") -> UserEvent:
        return self.interaction_port.submit_text(
            "pause requested",
            run_id=run_id,
            target=target,
            kind=UserEventKind.PAUSE_REQUEST,
            delivery=InteractionDelivery.NEXT_SAFE_POINT,
            metadata={"control_ref": "interaction/user_events.jsonl"},
        )

    def cancel(self, *, run_id: str, target: str = "flow") -> UserEvent:
        return self.interaction_port.submit_text(
            "cancel requested",
            run_id=run_id,
            target=target,
            kind=UserEventKind.CANCEL_REQUEST,
            delivery=InteractionDelivery.NEXT_SAFE_POINT,
            metadata={"control_ref": "interaction/user_events.jsonl"},
        )

    def request_revision(self, *, run_id: str, text: str, target: str = "flow") -> UserEvent:
        return self.interaction_port.submit_text(
            text,
            run_id=run_id,
            target=target,
            kind=UserEventKind.CONTRACT_REVISION_REQUEST,
            delivery=InteractionDelivery.NEXT_SAFE_POINT,
        )

    def resume(self, *, run_id: str, target: str = "flow") -> UserEvent:
        return self.interaction_port.submit_text(
            "resume requested",
            run_id=run_id,
            target=target,
            kind=UserEventKind.RESUME_REQUEST,
            delivery=InteractionDelivery.NEXT_SAFE_POINT,
            metadata={"control_ref": "interaction/user_events.jsonl"},
        )

    def stop_after_current_turn(self, *, run_id: str, target: str = "flow") -> UserEvent:
        return self.interaction_port.submit_text(
            "stop after current turn requested",
            run_id=run_id,
            target=target,
            kind=UserEventKind.STOP_AFTER_CURRENT_TURN,
            delivery=InteractionDelivery.AFTER_CURRENT_TURN,
            metadata={"control_ref": "interaction/user_events.jsonl"},
        )

    def force_checkpoint(self, *, run_id: str, target: str = "flow") -> UserEvent:
        return self.interaction_port.submit_text(
            "checkpoint requested",
            run_id=run_id,
            target=target,
            kind=UserEventKind.CHECKPOINT_REQUEST,
            delivery=InteractionDelivery.NEXT_SAFE_POINT,
            metadata={"control_ref": "interaction/user_events.jsonl"},
        )


def append_run_event(workspace: str | Path, event: RunEvent, *, events_ref: str = RUN_EVENTS_REF) -> None:
    """Append one refs-first run event."""

    event.validate()
    _append_jsonl(Path(workspace).resolve(), events_ref, event.to_dict())


def read_run_events(workspace: str | Path, *, run_id: str | None = None, events_ref: str = RUN_EVENTS_REF) -> list[RunEvent]:
    """Read refs-first run events."""

    safe_run_id = _safe_id(run_id, "run_event.run_id") if run_id else None
    events = [RunEvent.from_dict(item) for item in _read_jsonl(Path(workspace).resolve(), events_ref)]
    if safe_run_id is None:
        return events
    return [event for event in events if event.run_id == safe_run_id]


def write_run_snapshot(workspace: str | Path, snapshot: RunSnapshot, *, snapshot_ref: str = RUN_SNAPSHOT_REF) -> str:
    """Persist one refs-first run snapshot and return its ref."""

    snapshot.validate()
    _write_json(Path(workspace).resolve(), snapshot_ref, snapshot.to_dict())
    return validate_ref(snapshot_ref, "run_snapshot.ref")


def read_run_snapshot(workspace: str | Path, *, snapshot_ref: str = RUN_SNAPSHOT_REF) -> RunSnapshot:
    """Read one refs-first run snapshot."""

    payload = _read_json(Path(workspace).resolve(), snapshot_ref)
    return RunSnapshot.from_dict(payload)


def latest_run_snapshot(
    *,
    run_id: str,
    status: RunSnapshotStatus | str,
    workspace: str | Path,
    events_ref: str = RUN_EVENTS_REF,
    current_step_id: str = "",
    current_role: str = "",
    interaction_port: FileInteractionPort | None = None,
    target: str = "flow",
    flow_ledger_ref: str = "",
    flow_result_ref: str = "",
    progress_ref: str = "",
    last_safe_point_ref: str = "",
    step_record_refs: list[str] | None = None,
    context_projection_refs: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    metric_refs: list[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RunSnapshot:
    """Build a conservative snapshot from known refs and pending user events."""

    safe_events_ref = validate_ref(events_ref, "run_snapshot.events_ref")
    events = read_run_events(workspace, run_id=run_id, events_ref=safe_events_ref)
    latest_event_id = events[-1].event_id if events else ""
    pending_count = 0
    if interaction_port is not None:
        pending_count = len(interaction_port.pending_user_events(run_id=run_id, target=target))
    return RunSnapshot(
        run_id=run_id,
        status=status,
        current_step_id=current_step_id,
        current_role=current_role,
        latest_event_id=latest_event_id,
        latest_event_ref=safe_events_ref,
        flow_ledger_ref=flow_ledger_ref,
        flow_result_ref=flow_result_ref,
        progress_ref=progress_ref,
        last_safe_point_ref=last_safe_point_ref,
        pending_user_event_count=pending_count,
        step_record_refs=list(step_record_refs or []),
        context_projection_refs=list(context_projection_refs or []),
        artifact_refs=list(artifact_refs or []),
        metric_refs=list(metric_refs or []),
        metadata=dict(metadata or {}),
    )


def _append_jsonl(root: Path, ref: str, payload: Mapping[str, Any]) -> None:
    path = _resolve_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(ensure_json_value(payload, "observation.payload"), ensure_ascii=True, sort_keys=True) + "\n")


def _read_jsonl(root: Path, ref: str) -> list[Mapping[str, Any]]:
    path = _resolve_ref(root, ref)
    if not path.exists():
        return []
    result: list[Mapping[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, Mapping):
            raise ContractValidationError("observation JSONL record must be an object")
        result.append(payload)
    return result


def _write_json(root: Path, ref: str, payload: Mapping[str, Any]) -> None:
    path = _resolve_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ensure_json_value(payload, "observation.payload"), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(root: Path, ref: str) -> Mapping[str, Any]:
    path = _resolve_ref(root, ref)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ContractValidationError("observation JSON record must be an object")
    return payload


def _resolve_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "observation.ref")
    path = (root / safe_ref).resolve()
    if path != root and root not in path.parents:
        raise ContractValidationError("observation ref escapes workspace")
    return path


def _refs_only_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return dict(assert_refs_only_payload(require_mapping(payload, field_name), field_name))


def _metadata(value: Any, field_name: str) -> dict[str, Any]:
    return dict(ensure_json_value(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name))


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _unique_refs(values: list[str], field_name: str) -> list[str]:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")
    return refs


def _safe_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    validate_ref(text, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a single safe id segment")
    return text


def _optional_safe_id(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return ""
    return _safe_id(value, field_name)


def _optional_safe_target(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return ""
    text = require_non_empty_str(value, field_name)
    validate_ref(text, field_name)
    return text


def _optional_ref(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return ""
    return validate_ref(value, field_name)


def _optional_ref_or_default(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return RUN_EVENTS_REF
    return validate_ref(value, field_name)


def _non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContractValidationError(f"{field_name} must be a non-negative integer")
    return value


def _require_schema(value: str, expected: str, field_name: str) -> None:
    actual = require_non_empty_str(value, field_name)
    if actual != expected:
        raise ContractValidationError(f"{field_name} must be {expected}")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
