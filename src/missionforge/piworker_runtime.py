"""PiWorker runtime construction boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .workers import WorkerAdapter


@dataclass(frozen=True)
class PiWorkerRuntimeFactory:
    """Create the single supported LLM worker runtime."""

    config: Any | None = None

    def create_default_worker(self) -> WorkerAdapter:
        from .adapters.pi_agent_runtime import PiAgentRuntimeAdapter

        return PiAgentRuntimeAdapter(self.config)


def create_default_piworker_adapter(config: Any | None = None) -> WorkerAdapter:
    """Return the default PI Agent/PiWorker-compatible runtime adapter."""

    return PiWorkerRuntimeFactory(config=config).create_default_worker()
