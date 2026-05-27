"""Minimal MissionForge runtime boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MissionRuntime:
    """Top-level runtime facade.

    The initial skeleton validates Mission IR and returns an accepted result.
    Execution, harness, verifier, and adaptive repair will be added behind this
    stable boundary.
    """

    def run(self, mission: MissionIR) -> MissionResult:
        mission.validate()
        return MissionResult(
            mission_id=mission.mission_id,
            status="accepted",
            metrics={
                "constraint_count": len(mission.constraints),
                "profile_count": len(mission.capability_profiles),
            },
        )
