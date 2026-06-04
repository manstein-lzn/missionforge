"""PiWorker runtime construction boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agentic_repair_controller import RepairExecutionDirective
from .agentic_revision_controller import RevisionPendingRecord
from .agentic_flow import AgenticFlowRefs, AgenticFlowRunner
from .agentic_flow import AgentExecutorNode, AgentJudgeNode
from .contracts import validate_ref
from .piworker_call import PiWorkerCall, PiWorkerCallResult
from .workers import WorkerAdapter


@dataclass(frozen=True)
class PiWorkerRuntimeFactory:
    """Create the single supported LLM worker runtime."""

    config: Any | None = None
    runner: Any | None = None

    def create_default_worker(self) -> WorkerAdapter:
        from .adapters.pi_agent_runtime import PiAgentRuntimeAdapter

        if self.runner is None:
            return PiAgentRuntimeAdapter(self.config)
        return PiAgentRuntimeAdapter(self.config, runner=self.runner)

    def run_repair_directive(
        self,
        directive: RepairExecutionDirective,
        *,
        workspace: str | Path,
        contract_ref: str,
        permission_manifest_ref: str,
        writable_refs: list[str],
        repair_execution_directive_ref: str | None = None,
    ) -> PiWorkerCallResult:
        """Execute a same-contract repair directive through the PiWorkerCall boundary."""

        directive.validate()
        directive_ref = repair_execution_directive_ref or _repair_directive_ref_from_ticket_ref(directive.repair_ticket_ref)
        call = PiWorkerCall.from_repair_directive(
            directive,
            directive_ref=directive_ref,
            contract_ref=contract_ref,
            permission_manifest_ref=permission_manifest_ref,
            writable_refs=writable_refs,
        )
        from .adapters.pi_agent_runtime import PiAgentRuntimeAdapter
        from .evidence_store import InMemoryEvidenceStore

        if self.runner is None:
            adapter = PiAgentRuntimeAdapter(self.config)
        else:
            adapter = PiAgentRuntimeAdapter(self.config, runner=self.runner)
        result = adapter.run_call(call, workspace=workspace, evidence_store=InMemoryEvidenceStore())
        call_result = PiWorkerCallResult.from_worker_adapter_result(call, result)
        call_result.validate_against_call(call)
        return call_result

    def run_revision_draft(
        self,
        pending: RevisionPendingRecord,
        *,
        workspace: str | Path,
        permission_manifest_ref: str,
        writable_refs: list[str],
        expected_output_ref: str,
        revision_pending_ref: str | None = None,
    ) -> PiWorkerCallResult:
        """Draft a revised contract proposal through the PiWorkerCall boundary."""

        pending.validate()
        call = PiWorkerCall.from_revision_pending_record(
            pending,
            pending_ref=revision_pending_ref or _revision_pending_ref(pending.request_id),
            permission_manifest_ref=permission_manifest_ref,
            writable_refs=writable_refs,
            expected_output_ref=expected_output_ref,
        )
        from .adapters.pi_agent_runtime import PiAgentRuntimeAdapter
        from .evidence_store import InMemoryEvidenceStore

        if self.runner is None:
            adapter = PiAgentRuntimeAdapter(self.config)
        else:
            adapter = PiAgentRuntimeAdapter(self.config, runner=self.runner)
        result = adapter.run_call(call, workspace=workspace, evidence_store=InMemoryEvidenceStore())
        call_result = PiWorkerCallResult.from_worker_adapter_result(call, result)
        call_result.validate_against_call(call)
        return call_result


def create_default_piworker_adapter(config: Any | None = None, *, runner: Any | None = None) -> WorkerAdapter:
    """Return the default PI Agent/PiWorker-compatible runtime adapter."""

    return PiWorkerRuntimeFactory(config=config, runner=runner).create_default_worker()


def run_repair_directive_with_default_piworker(
    directive: RepairExecutionDirective,
    *,
    workspace: str | Path,
    contract_ref: str,
    permission_manifest_ref: str,
    writable_refs: list[str],
    piworker_config: Any | None = None,
    runner: Any | None = None,
    repair_execution_directive_ref: str | None = None,
) -> PiWorkerCallResult:
    """Run a repair directive with the default Pi-backed runtime."""

    return PiWorkerRuntimeFactory(config=piworker_config, runner=runner).run_repair_directive(
        directive,
        workspace=workspace,
        contract_ref=contract_ref,
        permission_manifest_ref=permission_manifest_ref,
        writable_refs=writable_refs,
        repair_execution_directive_ref=repair_execution_directive_ref,
    )


def run_revision_draft_with_default_piworker(
    pending: RevisionPendingRecord,
    *,
    workspace: str | Path,
    permission_manifest_ref: str,
    writable_refs: list[str],
    expected_output_ref: str,
    piworker_config: Any | None = None,
    runner: Any | None = None,
    revision_pending_ref: str | None = None,
) -> PiWorkerCallResult:
    """Run a revision drafting call with the default Pi-backed runtime."""

    return PiWorkerRuntimeFactory(config=piworker_config, runner=runner).run_revision_draft(
        pending,
        workspace=workspace,
        permission_manifest_ref=permission_manifest_ref,
        writable_refs=writable_refs,
        expected_output_ref=expected_output_ref,
        revision_pending_ref=revision_pending_ref,
    )


@dataclass(frozen=True)
class TaskContractFlowPreset:
    """Default TaskContract-native runtime lane with Pi-backed nodes."""

    runner: AgenticFlowRunner
    executor: AgentExecutorNode
    judge: AgentJudgeNode


def create_default_task_contract_flow(
    root: str | Path,
    *,
    piworker_config: Any | None = None,
    refs: AgenticFlowRefs | dict[str, Any] | None = None,
) -> TaskContractFlowPreset:
    """Assemble the default TaskContract-native PiWorker executor/judge flow."""

    from .adapters.pi_agent_runtime import PiAgentExecutorNode, PiAgentJudgeNode, PiAgentRuntimeAdapter

    if refs is None:
        flow_refs = AgenticFlowRefs()
    elif isinstance(refs, AgenticFlowRefs):
        flow_refs = refs
    else:
        flow_refs = AgenticFlowRefs.from_dict(refs)
    adapter = PiAgentRuntimeAdapter(piworker_config)
    return TaskContractFlowPreset(
        runner=AgenticFlowRunner(root, refs=flow_refs),
        executor=PiAgentExecutorNode(workspace_root=root, adapter=adapter),
        judge=PiAgentJudgeNode(workspace_root=root, adapter=adapter),
    )


def _repair_directive_ref_from_ticket_ref(ticket_ref: str) -> str:
    safe_ref = validate_ref(ticket_ref, "repair_ticket_ref")
    if not safe_ref.endswith("/repair_ticket.json"):
        return f"{safe_ref}/repair_execution_directive.json"
    return f"{safe_ref.removesuffix('/repair_ticket.json')}/repair_execution_directive.json"


def _revision_pending_ref(request_id: str) -> str:
    safe_request_id = validate_ref(f"revisions/{request_id}", "revision_request_id").split("/", 1)[1]
    return f"revisions/{safe_request_id}/revision_pending.json"
