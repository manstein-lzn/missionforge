"""Store protocol boundaries for durable MissionForge state."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .state import MissionRun, RuntimeAttempt


@runtime_checkable
class RunStore(Protocol):
    """Store MissionRun snapshots and attempt ledgers."""

    def write_mission_run(self, run: MissionRun) -> str:
        ...

    def load_mission_run(self, mission_run_id: str | None = None) -> MissionRun:
        ...

    def write_attempts(self, mission_run_id: str, attempts: list[RuntimeAttempt]) -> str:
        ...

    def load_attempts(self, mission_run_id: str) -> list[RuntimeAttempt]:
        ...


@runtime_checkable
class ArtifactStore(Protocol):
    """Store workspace-relative JSON/text artifacts."""

    def write_json(self, ref: str, payload: dict[str, Any]) -> str:
        ...

    def read_json(self, ref: str) -> dict[str, Any]:
        ...

    def write_text(self, ref: str, text: str) -> str:
        ...

    def read_text(self, ref: str) -> str:
        ...

    def exists(self, ref: str) -> bool:
        ...


@runtime_checkable
class EventLogStore(Protocol):
    """Store append-only JSONL event ledgers."""

    def write_jsonl(self, ref: str, payloads: list[dict[str, Any]], *, append: bool = False) -> str:
        ...

    def read_jsonl(self, ref: str) -> list[dict[str, Any]]:
        ...
