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

    def __init__(
        self,
        *,
        workspace: str | Path = ".",
        max_attempts: int = 1,
        pi_agent_config: Any | None = None,
        steering_provider: Any | None = None,
        observation_interpreter: Any | None = None,
        reviewer_provider: Any | None = None,
        steering_mode: str = "deterministic",
    ) -> None:
        self.workspace = workspace
        self.max_attempts = max_attempts
        self.pi_agent_config = pi_agent_config
        self.steering_provider = steering_provider
        self.observation_interpreter = observation_interpreter
        self.reviewer_provider = reviewer_provider
        self.steering_mode = steering_mode

    def run(self, mission: MissionIR) -> MissionResult:
        from .adapters.pi_agent_runtime import PiAgentRuntimeAdapter

        worker = PiAgentRuntimeAdapter(self.pi_agent_config)
        from .runtime import RuntimeEngine

        return RuntimeEngine(
            workspace=self.workspace,
            max_attempts=self.max_attempts,
            worker=worker,
            steering_provider=self.steering_provider,
            observation_interpreter=self.observation_interpreter,
            reviewer_provider=self.reviewer_provider,
            steering_mode=self.steering_mode,
        ).run(mission)

    def inspect(self, mission_run_id: str | None = None) -> dict[str, Any]:
        from .state import inspect_runtime

        return inspect_runtime(self.workspace, mission_run_id)

    def resume(self, mission: MissionIR, *, follow_up_prompt: str = "Resume from the latest completed turn.") -> MissionResult:
        from .adapters.pi_agent_runtime import PiAgentRuntimeAdapter
        from .runtime import RuntimeEngine

        worker = PiAgentRuntimeAdapter(self.pi_agent_config)
        return RuntimeEngine(
            workspace=self.workspace,
            max_attempts=self.max_attempts,
            worker=worker,
            steering_provider=self.steering_provider,
            observation_interpreter=self.observation_interpreter,
            reviewer_provider=self.reviewer_provider,
            steering_mode=self.steering_mode,
        ).resume(
            mission,
            follow_up_prompt=follow_up_prompt,
        )
