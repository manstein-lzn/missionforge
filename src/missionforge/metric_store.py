"""Run-local JSONL storage for diagnostic metric events."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .contracts import ContractValidationError, validate_ref
from .json_store import JsonWorkspaceStore
from .metrics import MetricEvent, MetricProjection, project_metric_events


class MetricStore:
    """Workspace-relative metric event and projection store."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace)
        self.store = JsonWorkspaceStore(self.workspace)

    def events_ref(self, mission_run_id: str) -> str:
        run_id = validate_ref(mission_run_id, "metric_store.mission_run_id")
        return f"runs/{run_id}/metrics/events.jsonl"

    def projection_ref(self, mission_run_id: str) -> str:
        run_id = validate_ref(mission_run_id, "metric_store.mission_run_id")
        return f"runs/{run_id}/metrics/projection.json"

    def write_events(self, mission_run_id: str, events: Iterable[MetricEvent], *, append: bool = False) -> str:
        event_ref = self.events_ref(mission_run_id)
        payloads: list[dict] = []
        for event in events:
            event.validate()
            if event.mission_run_id != mission_run_id:
                raise ContractValidationError("metric event mission_run_id does not match store mission_run_id")
            payloads.append(event.to_dict())
        self.store.write_jsonl(event_ref, payloads, append=append)
        return event_ref

    def load_events(self, mission_run_id: str) -> list[MetricEvent]:
        return [MetricEvent.from_dict(payload) for payload in self.store.read_jsonl(self.events_ref(mission_run_id))]

    def rebuild_projection(self, mission_run_id: str) -> MetricProjection:
        event_ref = self.events_ref(mission_run_id)
        events = self.load_events(mission_run_id)
        refs = [event_ref] if events else []
        return project_metric_events(mission_run_id=mission_run_id, events=events, metric_event_refs=refs)

    def write_projection(self, projection: MetricProjection) -> str:
        projection.validate()
        projection_ref = self.projection_ref(projection.mission_run_id)
        self.store.write_json(projection_ref, projection.to_dict())
        return projection_ref

    def load_projection(self, mission_run_id: str) -> MetricProjection:
        return MetricProjection.from_dict(self.store.read_json(self.projection_ref(mission_run_id)))
