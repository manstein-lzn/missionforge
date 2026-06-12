"""PiWorker runtime construction boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .agentic_repair_controller import RepairExecutionDirective
from .agentic_revision_controller import RevisionPendingRecord
from .agentic_flow import AgenticFlowRefs, AgenticFlowRunner
from .agentic_flow import AgentExecutorNode, AgentJudgeNode
from .agentic_ledger import (
    DecisionLedgerEventKind,
    TaskContractDecisionLedgerEntry,
    append_decision_ledger_entry,
    next_ledger_entry_id,
    read_decision_ledger,
)
from .contracts import ContractValidationError, stable_json_hash, validate_ref
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
        decision_ledger_ref: str | None = None,
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
        call_result_ref = _write_piworker_call_result(workspace, call_result)
        if decision_ledger_ref is not None:
            _append_piworker_continuation_ledger_entry(
                workspace=workspace,
                decision_ledger_ref=decision_ledger_ref,
                event_kind=DecisionLedgerEventKind.REPAIR_EXECUTION_RECORDED,
                run_id=directive.run_id,
                contract_id=directive.contract_id,
                contract_hash=directive.contract_hash,
                status=call_result.status.value,
                refs={
                    "repair_execution_directive_ref": directive_ref,
                    "repair_execution_report_ref": directive.execution_report_ref,
                    "piworker_call_result_ref": call_result_ref,
                },
                content_hashes={call_result_ref: stable_json_hash(call_result.to_dict())},
            )
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
        decision_ledger_ref: str | None = None,
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
        call_result_ref = _write_piworker_call_result(workspace, call_result)
        if decision_ledger_ref is not None:
            pending_ref = revision_pending_ref or _revision_pending_ref(pending.request_id)
            _append_piworker_continuation_ledger_entry(
                workspace=workspace,
                decision_ledger_ref=decision_ledger_ref,
                event_kind=DecisionLedgerEventKind.REVISION_DRAFT_RECORDED,
                run_id=pending.run_id,
                contract_id=pending.contract_id,
                contract_hash=pending.contract_hash,
                status=call_result.status.value,
                refs={
                    "revision_pending_ref": pending_ref,
                    "revision_draft_ref": expected_output_ref,
                    "piworker_call_result_ref": call_result_ref,
                },
                content_hashes={call_result_ref: stable_json_hash(call_result.to_dict())},
            )
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
    decision_ledger_ref: str | None = None,
) -> PiWorkerCallResult:
    """Run a repair directive with the default Pi-backed runtime."""

    return PiWorkerRuntimeFactory(config=piworker_config, runner=runner).run_repair_directive(
        directive,
        workspace=workspace,
        contract_ref=contract_ref,
        permission_manifest_ref=permission_manifest_ref,
        writable_refs=writable_refs,
        repair_execution_directive_ref=repair_execution_directive_ref,
        decision_ledger_ref=decision_ledger_ref,
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
    decision_ledger_ref: str | None = None,
) -> PiWorkerCallResult:
    """Run a revision drafting call with the default Pi-backed runtime."""

    return PiWorkerRuntimeFactory(config=piworker_config, runner=runner).run_revision_draft(
        pending,
        workspace=workspace,
        permission_manifest_ref=permission_manifest_ref,
        writable_refs=writable_refs,
        expected_output_ref=expected_output_ref,
        revision_pending_ref=revision_pending_ref,
        decision_ledger_ref=decision_ledger_ref,
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
    piworker_runner: Any | None = None,
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
    if piworker_runner is None:
        adapter = PiAgentRuntimeAdapter(piworker_config)
    else:
        adapter = PiAgentRuntimeAdapter(piworker_config, runner=piworker_runner)
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


def _write_piworker_call_result(workspace: str | Path, result: PiWorkerCallResult) -> str:
    result.validate()
    ref = _piworker_call_result_ref(result.call_id)
    root = Path(workspace).resolve()
    path = _resolve_workspace_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return ref


def _piworker_call_result_ref(call_id: str) -> str:
    safe_call_id = validate_ref(call_id, "piworker_call.call_id")
    return f"attempts/{safe_call_id}/piworker_call_result.json"


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("PiWorker runtime ref escapes workspace")
    return path


def _append_piworker_continuation_ledger_entry(
    *,
    workspace: str | Path,
    decision_ledger_ref: str,
    event_kind: DecisionLedgerEventKind,
    run_id: str,
    contract_id: str,
    contract_hash: str,
    status: str,
    refs: dict[str, str],
    content_hashes: dict[str, str],
) -> None:
    entries = read_decision_ledger(workspace, decision_ledger_ref=decision_ledger_ref)
    entry = TaskContractDecisionLedgerEntry(
        entry_id=next_ledger_entry_id(entries),
        run_id=run_id,
        event_kind=event_kind,
        contract_id=contract_id,
        contract_hash=contract_hash,
        status=status,
        ref_map=refs,
        content_hashes=content_hashes,
    )
    append_decision_ledger_entry(workspace, decision_ledger_ref, entry)
