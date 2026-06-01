"""TaskContract-native flow assembly helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ..agentic_flow import AgenticFlowRefs, AgenticFlowRunner
from ..agentic_flow import AgentExecutorNode, AgentJudgeNode
from .pi_agent_runtime import PiAgentExecutorNode, PiAgentJudgeNode, PiAgentRuntimeAdapter


@dataclass(frozen=True)
class TaskContractFlowPreset:
    """Convenience assembly for the TaskContract-native executor/judge lane."""

    runner: AgenticFlowRunner
    executor: AgentExecutorNode
    judge: AgentJudgeNode


def create_default_task_contract_flow(
    root: str | Path,
    *,
    piworker_config: Any | None = None,
    refs: AgenticFlowRefs | Mapping[str, Any] | None = None,
    now: Callable[[], str] | None = None,
) -> TaskContractFlowPreset:
    """Assemble the default TaskContract-native runtime lane."""

    if refs is None:
        flow_refs = AgenticFlowRefs()
    elif isinstance(refs, AgenticFlowRefs):
        flow_refs = refs
    else:
        flow_refs = AgenticFlowRefs.from_dict(refs)
    adapter = PiAgentRuntimeAdapter(piworker_config)
    return TaskContractFlowPreset(
        runner=AgenticFlowRunner(root, refs=flow_refs, now=now or _utc_now),
        executor=PiAgentExecutorNode(workspace_root=root, adapter=adapter),
        judge=PiAgentJudgeNode(workspace_root=root, adapter=adapter),
    )


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
