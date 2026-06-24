"""Product-neutral user/agent interaction primitives.

The interaction plane is intentionally small. It lets hosts append user
interventions, expose them to workers at safe points, and record user-visible
agent events without making raw chat the task authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .contracts import ContractValidationError, assert_refs_only_payload, ensure_json_value, require_non_empty_str, validate_ref


USER_EVENTS_REF = "interaction/user_events.jsonl"
AGENT_EVENTS_REF = "interaction/agent_events.jsonl"
ACKS_REF = "interaction/user_event_acks.jsonl"


class UserEventKind(StrEnum):
    """Product-neutral user intervention kinds."""

    MESSAGE = "message"
    CLARIFICATION = "clarification"
    PAUSE_REQUEST = "pause_request"
    CANCEL_REQUEST = "cancel_request"
    RESUME_REQUEST = "resume_request"
    CHECKPOINT_REQUEST = "checkpoint_request"
    STOP_AFTER_CURRENT_TURN = "stop_after_current_turn"
    APPROVAL_DECISION = "approval_decision"
    CORRECTION = "correction"
    CONTRACT_REVISION_REQUEST = "contract_revision_request"


class AgentEventKind(StrEnum):
    """Product-neutral user-visible agent event kinds."""

    MESSAGE = "message"
    QUESTION = "question"
    PROGRESS = "progress"
    APPROVAL_REQUEST = "approval_request"
    NOTICE = "notice"


class InteractionDelivery(StrEnum):
    """When a user event may affect execution."""

    AFTER_CURRENT_TURN = "after_current_turn"
    NEXT_SAFE_POINT = "next_safe_point"
    IMMEDIATE_CANCEL = "immediate_cancel"
    QUEUE_FOR_REVIEWER = "queue_for_reviewer"


class InteractionVisibility(StrEnum):
    """Who may see an agent event."""

    USER = "user"
    OPERATOR = "operator"
    INTERNAL = "internal"


@dataclass(frozen=True)
class UserEvent:
    """A user intervention submitted to a running MissionForge flow."""

    event_id: str
    run_id: str
    target: str
    kind: UserEventKind
    delivery: InteractionDelivery = InteractionDelivery.NEXT_SAFE_POINT
    text: str = ""
    payload_ref: str = ""
    actor: str = "user"
    created_at: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "missionforge.interaction.user_event.v1"

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        target: str,
        kind: UserEventKind | str = UserEventKind.MESSAGE,
        text: str = "",
        delivery: InteractionDelivery | str = InteractionDelivery.NEXT_SAFE_POINT,
        payload_ref: str = "",
        actor: str = "user",
        created_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "UserEvent":
        return cls(
            event_id=f"UE-{uuid4().hex}",
            run_id=_safe_token(run_id, "user_event.run_id"),
            target=_safe_target(target, "user_event.target"),
            kind=_user_event_kind(kind),
            delivery=_interaction_delivery(delivery),
            text=_text(text, "user_event.text"),
            payload_ref=validate_ref(payload_ref, "user_event.payload_ref") if payload_ref else "",
            actor=_safe_target(actor, "user_event.actor"),
            created_at=_text(created_at, "user_event.created_at"),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UserEvent":
        data = _mapping(payload, "user_event")
        event = cls(
            event_id=_event_id(data.get("event_id"), "user_event.event_id"),
            run_id=_safe_token(data.get("run_id"), "user_event.run_id"),
            target=_safe_target(data.get("target"), "user_event.target"),
            kind=_user_event_kind(data.get("kind")),
            delivery=_interaction_delivery(data.get("delivery", InteractionDelivery.NEXT_SAFE_POINT.value)),
            text=_text(data.get("text", ""), "user_event.text"),
            payload_ref=validate_ref(data.get("payload_ref"), "user_event.payload_ref") if data.get("payload_ref") else "",
            actor=_safe_target(data.get("actor", "user"), "user_event.actor"),
            created_at=_text(data.get("created_at", ""), "user_event.created_at"),
            metadata=_json_metadata(data.get("metadata", {}), "user_event.metadata"),
            schema_version=require_non_empty_str(data.get("schema_version", "missionforge.interaction.user_event.v1"), "user_event.schema_version"),
        )
        event.validate()
        return event

    def validate(self) -> None:
        if self.schema_version != "missionforge.interaction.user_event.v1":
            raise ContractValidationError("user_event.schema_version is unsupported")
        _event_id(self.event_id, "user_event.event_id")
        _safe_token(self.run_id, "user_event.run_id")
        _safe_target(self.target, "user_event.target")
        _user_event_kind(self.kind)
        _interaction_delivery(self.delivery)
        _text(self.text, "user_event.text")
        if self.payload_ref:
            validate_ref(self.payload_ref, "user_event.payload_ref")
        _safe_target(self.actor, "user_event.actor")
        _text(self.created_at, "user_event.created_at")
        _json_metadata(self.metadata, "user_event.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "target": self.target,
            "kind": self.kind.value,
            "delivery": self.delivery.value,
            "text": self.text,
            "payload_ref": self.payload_ref,
            "actor": self.actor,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AgentEvent:
    """A user-visible event emitted by a worker or runtime."""

    event_id: str
    run_id: str
    source: str
    kind: AgentEventKind
    visibility: InteractionVisibility = InteractionVisibility.USER
    text: str = ""
    payload_ref: str = ""
    created_at: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "missionforge.interaction.agent_event.v1"

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        source: str,
        kind: AgentEventKind | str = AgentEventKind.MESSAGE,
        text: str = "",
        visibility: InteractionVisibility | str = InteractionVisibility.USER,
        payload_ref: str = "",
        created_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "AgentEvent":
        return cls(
            event_id=f"AE-{uuid4().hex}",
            run_id=_safe_token(run_id, "agent_event.run_id"),
            source=_safe_target(source, "agent_event.source"),
            kind=_agent_event_kind(kind),
            visibility=_interaction_visibility(visibility),
            text=_text(text, "agent_event.text"),
            payload_ref=validate_ref(payload_ref, "agent_event.payload_ref") if payload_ref else "",
            created_at=_text(created_at, "agent_event.created_at"),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgentEvent":
        data = _mapping(payload, "agent_event")
        event = cls(
            event_id=_event_id(data.get("event_id"), "agent_event.event_id"),
            run_id=_safe_token(data.get("run_id"), "agent_event.run_id"),
            source=_safe_target(data.get("source"), "agent_event.source"),
            kind=_agent_event_kind(data.get("kind")),
            visibility=_interaction_visibility(data.get("visibility", InteractionVisibility.USER.value)),
            text=_text(data.get("text", ""), "agent_event.text"),
            payload_ref=validate_ref(data.get("payload_ref"), "agent_event.payload_ref") if data.get("payload_ref") else "",
            created_at=_text(data.get("created_at", ""), "agent_event.created_at"),
            metadata=_json_metadata(data.get("metadata", {}), "agent_event.metadata"),
            schema_version=require_non_empty_str(data.get("schema_version", "missionforge.interaction.agent_event.v1"), "agent_event.schema_version"),
        )
        event.validate()
        return event

    def validate(self) -> None:
        if self.schema_version != "missionforge.interaction.agent_event.v1":
            raise ContractValidationError("agent_event.schema_version is unsupported")
        _event_id(self.event_id, "agent_event.event_id")
        _safe_token(self.run_id, "agent_event.run_id")
        _safe_target(self.source, "agent_event.source")
        _agent_event_kind(self.kind)
        _interaction_visibility(self.visibility)
        _text(self.text, "agent_event.text")
        if self.payload_ref:
            validate_ref(self.payload_ref, "agent_event.payload_ref")
        _text(self.created_at, "agent_event.created_at")
        _json_metadata(self.metadata, "agent_event.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "source": self.source,
            "kind": self.kind.value,
            "visibility": self.visibility.value,
            "text": self.text,
            "payload_ref": self.payload_ref,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class UserEventAck:
    """A refs-first delivery record that a user event reached a safe point."""

    event_id: str
    run_id: str
    consumed_by: str
    consumed_at: str = ""
    snapshot_ref: str = ""
    step_record_ref: str = ""
    schema_version: str = "missionforge.interaction.user_event_ack.v1"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UserEventAck":
        data = _mapping(payload, "user_event_ack")
        ack = cls(
            event_id=_event_id(data.get("event_id"), "user_event_ack.event_id"),
            run_id=_safe_token(data.get("run_id"), "user_event_ack.run_id"),
            consumed_by=_safe_target(data.get("consumed_by"), "user_event_ack.consumed_by"),
            consumed_at=_text(data.get("consumed_at", ""), "user_event_ack.consumed_at"),
            snapshot_ref=validate_ref(data.get("snapshot_ref"), "user_event_ack.snapshot_ref") if data.get("snapshot_ref") else "",
            step_record_ref=validate_ref(data.get("step_record_ref"), "user_event_ack.step_record_ref") if data.get("step_record_ref") else "",
            schema_version=require_non_empty_str(data.get("schema_version", "missionforge.interaction.user_event_ack.v1"), "user_event_ack.schema_version"),
        )
        ack.validate()
        return ack

    def validate(self) -> None:
        if self.schema_version != "missionforge.interaction.user_event_ack.v1":
            raise ContractValidationError("user_event_ack.schema_version is unsupported")
        _event_id(self.event_id, "user_event_ack.event_id")
        _safe_token(self.run_id, "user_event_ack.run_id")
        _safe_target(self.consumed_by, "user_event_ack.consumed_by")
        _text(self.consumed_at, "user_event_ack.consumed_at")
        if self.snapshot_ref:
            validate_ref(self.snapshot_ref, "user_event_ack.snapshot_ref")
        if self.step_record_ref:
            validate_ref(self.step_record_ref, "user_event_ack.step_record_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "consumed_by": self.consumed_by,
            "consumed_at": self.consumed_at,
            "snapshot_ref": self.snapshot_ref,
            "step_record_ref": self.step_record_ref,
        }


class FileInteractionPort:
    """Append-only workspace-backed interaction port.

    The port is deliberately file-backed because MissionForge workers consume
    refs today. Hosts can still use it as a tiny API instead of manipulating
    files directly.
    """

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def submit_user_event(self, event: UserEvent) -> UserEvent:
        event.validate()
        _append_jsonl(self.workspace, USER_EVENTS_REF, event.to_dict())
        return event

    def submit_text(
        self,
        text: str,
        *,
        run_id: str,
        target: str = "flow",
        kind: UserEventKind | str = UserEventKind.MESSAGE,
        delivery: InteractionDelivery | str = InteractionDelivery.NEXT_SAFE_POINT,
        actor: str = "user",
        created_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> UserEvent:
        event = UserEvent.create(
            run_id=run_id,
            target=target,
            kind=kind,
            delivery=delivery,
            text=text,
            actor=actor,
            created_at=created_at,
            metadata=metadata,
        )
        return self.submit_user_event(event)

    def emit_agent_event(self, event: AgentEvent) -> AgentEvent:
        event.validate()
        _append_jsonl(self.workspace, AGENT_EVENTS_REF, event.to_dict())
        return event

    def pending_user_events(self, *, run_id: str, target: str | None = None) -> list[UserEvent]:
        safe_run_id = _safe_token(run_id, "interaction.run_id")
        safe_target = _safe_target(target, "interaction.target") if target else None
        acknowledged = {ack.event_id for ack in self.read_acks(run_id=safe_run_id)}
        pending = []
        for event in self.read_user_events(run_id=safe_run_id):
            if event.event_id in acknowledged:
                continue
            if safe_target is not None and event.target not in {safe_target, "flow", "all"}:
                continue
            pending.append(event)
        return pending

    def write_pending_projection(
        self,
        *,
        run_id: str,
        target: str,
        ref: str,
        step_id: str = "",
    ) -> str:
        safe_ref = validate_ref(ref, "interaction.pending_projection.ref")
        events = self.pending_user_events(run_id=run_id, target=target)
        payload = {
            "schema_version": "missionforge.interaction.pending_user_events.v1",
            "run_id": _safe_token(run_id, "interaction.run_id"),
            "target": _safe_target(target, "interaction.target"),
            "step_id": _safe_target(step_id, "interaction.step_id") if step_id else "",
            "events_ref": USER_EVENTS_REF,
            "ack_ref": ACKS_REF,
            "event_count": len(events),
            "events": [event.to_dict() for event in events],
            "authority_note": (
                "User events are interventions, not task authority. Contract changes "
                "require an explicit revision record."
            ),
        }
        _write_json(self.workspace, safe_ref, payload)
        return safe_ref

    def acknowledge(
        self,
        events: list[UserEvent],
        *,
        consumed_by: str,
        consumed_at: str = "",
        snapshot_ref: str = "",
        step_record_ref: str = "",
    ) -> None:
        safe_consumed_by = _safe_target(consumed_by, "interaction.consumed_by")
        safe_snapshot_ref = validate_ref(snapshot_ref, "interaction.snapshot_ref") if snapshot_ref else ""
        safe_step_record_ref = validate_ref(step_record_ref, "interaction.step_record_ref") if step_record_ref else ""
        for event in events:
            event.validate()
            ack = UserEventAck(
                event_id=event.event_id,
                run_id=event.run_id,
                consumed_by=safe_consumed_by,
                consumed_at=_text(consumed_at, "interaction.consumed_at"),
                snapshot_ref=safe_snapshot_ref,
                step_record_ref=safe_step_record_ref,
            )
            _append_jsonl(self.workspace, ACKS_REF, ack.to_dict())

    def read_user_events(self, *, run_id: str | None = None) -> list[UserEvent]:
        safe_run_id = _safe_token(run_id, "interaction.run_id") if run_id else None
        events = [UserEvent.from_dict(item) for item in _read_jsonl(self.workspace, USER_EVENTS_REF)]
        if safe_run_id is None:
            return events
        return [event for event in events if event.run_id == safe_run_id]

    def read_agent_events(self, *, run_id: str | None = None) -> list[AgentEvent]:
        safe_run_id = _safe_token(run_id, "interaction.run_id") if run_id else None
        events = [AgentEvent.from_dict(item) for item in _read_jsonl(self.workspace, AGENT_EVENTS_REF)]
        if safe_run_id is None:
            return events
        return [event for event in events if event.run_id == safe_run_id]

    def read_acks(self, *, run_id: str | None = None) -> list[UserEventAck]:
        safe_run_id = _safe_token(run_id, "interaction.run_id") if run_id else None
        acks = [UserEventAck.from_dict(item) for item in _read_jsonl(self.workspace, ACKS_REF)]
        if safe_run_id is None:
            return acks
        return [ack for ack in acks if ack.run_id == safe_run_id]


def _append_jsonl(root: Path, ref: str, payload: Mapping[str, Any]) -> None:
    path = _resolve_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(ensure_json_value(payload, "interaction.payload"), ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(root: Path, ref: str) -> list[Mapping[str, Any]]:
    path = _resolve_ref(root, ref)
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, Mapping):
            raise ContractValidationError("interaction JSONL record must be an object")
        result.append(payload)
    return result


def _write_json(root: Path, ref: str, payload: Mapping[str, Any]) -> None:
    path = _resolve_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ensure_json_value(payload, "interaction.payload"), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _resolve_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "interaction.ref")
    path = (root / safe_ref).resolve()
    if path != root and root not in path.parents:
        raise ContractValidationError("interaction ref escapes workspace")
    return path


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} must be an object")
    return value


def _event_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if not text.startswith(("UE-", "AE-")) and field_name.endswith("event_id"):
        raise ContractValidationError(f"{field_name} must start with UE- or AE-")
    return text


def _safe_token(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    validate_ref(text, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a single safe token")
    return text


def _safe_target(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    validate_ref(text, field_name)
    return text


def _text(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ContractValidationError(f"{field_name} must be a string")
    return value


def _json_metadata(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} must be an object")
    assert_refs_only_payload(value, field_name)
    return dict(value)


def _user_event_kind(value: Any) -> UserEventKind:
    try:
        return value if isinstance(value, UserEventKind) else UserEventKind(str(value))
    except ValueError as exc:
        raise ContractValidationError("user_event.kind is unsupported") from exc


def _agent_event_kind(value: Any) -> AgentEventKind:
    try:
        return value if isinstance(value, AgentEventKind) else AgentEventKind(str(value))
    except ValueError as exc:
        raise ContractValidationError("agent_event.kind is unsupported") from exc


def _interaction_delivery(value: Any) -> InteractionDelivery:
    try:
        return value if isinstance(value, InteractionDelivery) else InteractionDelivery(str(value))
    except ValueError as exc:
        raise ContractValidationError("interaction.delivery is unsupported") from exc


def _interaction_visibility(value: Any) -> InteractionVisibility:
    try:
        return value if isinstance(value, InteractionVisibility) else InteractionVisibility(str(value))
    except ValueError as exc:
        raise ContractValidationError("interaction.visibility is unsupported") from exc
