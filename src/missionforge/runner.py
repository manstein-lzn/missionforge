"""Minimal MissionForge runtime boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .contracts import require_mapping, require_non_empty_str, require_str_list
from .ir import MissionIR


@dataclass(frozen=True)
class MissionResult:
    """Refs-only result envelope returned by MissionRuntime."""

    mission_id: str
    status: str
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionResult":
        data = require_mapping(payload, "mission_result")
        return cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "mission_result.mission_id"),
            status=require_non_empty_str(data.get("status"), "mission_result.status"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_result.evidence_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "mission_result.artifact_refs"),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "mission_result.failed_constraint_ids",
            ),
            metrics=require_mapping(data.get("metrics", {}), "mission_result.metrics"),
        )

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "mission_result.mission_id")
        require_non_empty_str(self.status, "mission_result.status")
        require_str_list(self.evidence_refs, "mission_result.evidence_refs")
        require_str_list(self.artifact_refs, "mission_result.artifact_refs")
        require_str_list(self.failed_constraint_ids, "mission_result.failed_constraint_ids")
        require_mapping(self.metrics, "mission_result.metrics")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


class MissionRuntime:
    """Top-level runtime facade."""

    def __init__(self, *, workspace: str | Path = ".", max_attempts: int = 1) -> None:
        self.workspace = workspace
        self.max_attempts = max_attempts

    def run(self, mission: MissionIR) -> MissionResult:
        from .runtime import RuntimeEngine

        return RuntimeEngine(workspace=self.workspace, max_attempts=self.max_attempts).run(mission)
