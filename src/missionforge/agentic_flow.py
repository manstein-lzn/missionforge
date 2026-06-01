"""Minimal offline agentic flow for TaskContract-based execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, cast

from .agent_packets import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    HardCheckStatus,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
    validate_execution_report_for_packet,
    validate_judge_packet_for_execution,
    validate_judge_report_for_packet,
)
from .agentic_repair import (
    RepairBrief,
    TaskRevisionRequest,
    validate_repair_brief_for_judge,
    validate_revision_request_for_judge,
)
from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from .permissions import ref_is_under
from .task_contract import PermissionManifest, TaskContract, WorkspacePolicy
from .task_projection import project_judge_rubric, project_worker_brief
from .workspace_runtime import RunWorkspace


class AgenticFlowStatus(StrEnum):
    """Observable status for the minimal TaskContract runtime path."""

    ACCEPTED = "accepted"
    REPAIR = "repair"
    REVISION_REQUIRED = "revision_required"
    REJECTED = "rejected"


class AgentExecutorNode(Protocol):
    """Executor node boundary used by the offline flow."""

    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        """Produce artifacts and an executor report without acceptance authority."""
        ...


class AgentJudgeNode(Protocol):
    """Judge node boundary used by the offline flow."""

    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        """Return an independent judge decision over refs and evidence."""
        ...


class AgentWorkspace(Protocol):
    """Workspace capability exposed to executor and judge nodes."""

    def ensure_read_ref(self, ref: str) -> str:
        """Return a readable ref or fail closed."""
        ...

    def ensure_write_ref(self, ref: str) -> str:
        """Return a writable ref or fail closed."""
        ...

    def read_text(self, ref: str) -> str:
        """Read a permitted text ref."""
        ...

    def write_text(self, ref: str, text: str) -> str:
        """Write a permitted text ref."""
        ...

    def read_json(self, ref: str) -> dict[str, object]:
        """Read a permitted JSON ref."""
        ...

    def write_json(self, ref: str, payload: dict[str, object]) -> str:
        """Write a permitted JSON ref."""
        ...


@dataclass(frozen=True)
class ScopedAgentWorkspace:
    """Write-scoped facade over RunWorkspace for in-process offline nodes."""

    workspace: RunWorkspace
    denied_write_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for ref in self.denied_write_refs:
            validate_ref(ref, "scoped_agent_workspace.denied_write_refs[]")

    def ensure_read_ref(self, ref: str) -> str:
        return self.workspace.ensure_read_ref(ref)

    def ensure_write_ref(self, ref: str) -> str:
        safe_ref = validate_ref(ref, "scoped_agent_workspace.write_ref")
        for denied_ref in self.denied_write_refs:
            if ref_is_under(safe_ref, denied_ref):
                raise ContractValidationError(f"permission denied for {safe_ref}: runtime-owned ref")
        return self.workspace.ensure_write_ref(safe_ref)

    def read_text(self, ref: str) -> str:
        return self.workspace.read_text(self.ensure_read_ref(ref))

    def write_text(self, ref: str, text: str) -> str:
        safe_ref = self.ensure_write_ref(ref)
        return self.workspace.write_text(safe_ref, text)

    def read_json(self, ref: str) -> dict[str, object]:
        return self.workspace.read_json(self.ensure_read_ref(ref))

    def write_json(self, ref: str, payload: dict[str, object]) -> str:
        safe_ref = self.ensure_write_ref(ref)
        return self.workspace.write_json(safe_ref, payload)


@dataclass(frozen=True)
class AgenticFlowRefs:
    """Stable refs emitted by the minimal offline flow."""

    contract_ref: str = "contract/task_contract.json"
    worker_brief_ref: str = "projections/worker_brief.json"
    execution_packet_ref: str = "packets/execution_packet.json"
    execution_report_ref: str = "reports/execution_report.json"
    judge_packet_ref: str = "packets/judge_packet.json"
    judge_report_ref: str = "reports/judge_report.json"
    decision_ledger_ref: str = "ledgers/decision_ledger.jsonl"
    checkpoint_ref: str = "checkpoints/latest.json"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgenticFlowRefs":
        data = require_mapping(payload, "agentic_flow_refs")
        allowed = {
            "contract_ref",
            "worker_brief_ref",
            "execution_packet_ref",
            "execution_report_ref",
            "judge_packet_ref",
            "judge_report_ref",
            "decision_ledger_ref",
            "checkpoint_ref",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ContractValidationError(f"agentic_flow_refs contains unknown fields: {unknown}")
        refs = cls(
            contract_ref=validate_ref(data.get("contract_ref", cls.contract_ref), "agentic_flow_refs.contract_ref"),
            worker_brief_ref=validate_ref(
                data.get("worker_brief_ref", cls.worker_brief_ref),
                "agentic_flow_refs.worker_brief_ref",
            ),
            execution_packet_ref=validate_ref(
                data.get("execution_packet_ref", cls.execution_packet_ref),
                "agentic_flow_refs.execution_packet_ref",
            ),
            execution_report_ref=validate_ref(
                data.get("execution_report_ref", cls.execution_report_ref),
                "agentic_flow_refs.execution_report_ref",
            ),
            judge_packet_ref=validate_ref(
                data.get("judge_packet_ref", cls.judge_packet_ref),
                "agentic_flow_refs.judge_packet_ref",
            ),
            judge_report_ref=validate_ref(
                data.get("judge_report_ref", cls.judge_report_ref),
                "agentic_flow_refs.judge_report_ref",
            ),
            decision_ledger_ref=validate_ref(
                data.get("decision_ledger_ref", cls.decision_ledger_ref),
                "agentic_flow_refs.decision_ledger_ref",
            ),
            checkpoint_ref=validate_ref(
                data.get("checkpoint_ref", cls.checkpoint_ref),
                "agentic_flow_refs.checkpoint_ref",
            ),
        )
        refs.validate()
        return refs

    def validate(self) -> None:
        validate_ref(self.contract_ref, "agentic_flow_refs.contract_ref")
        validate_ref(self.worker_brief_ref, "agentic_flow_refs.worker_brief_ref")
        validate_ref(self.execution_packet_ref, "agentic_flow_refs.execution_packet_ref")
        validate_ref(self.execution_report_ref, "agentic_flow_refs.execution_report_ref")
        validate_ref(self.judge_packet_ref, "agentic_flow_refs.judge_packet_ref")
        validate_ref(self.judge_report_ref, "agentic_flow_refs.judge_report_ref")
        validate_ref(self.decision_ledger_ref, "agentic_flow_refs.decision_ledger_ref")
        validate_ref(self.checkpoint_ref, "agentic_flow_refs.checkpoint_ref")

    def to_dict(self) -> dict[str, str]:
        self.validate()
        return {
            "contract_ref": self.contract_ref,
            "worker_brief_ref": self.worker_brief_ref,
            "execution_packet_ref": self.execution_packet_ref,
            "execution_report_ref": self.execution_report_ref,
            "judge_packet_ref": self.judge_packet_ref,
            "judge_report_ref": self.judge_report_ref,
            "decision_ledger_ref": self.decision_ledger_ref,
            "checkpoint_ref": self.checkpoint_ref,
        }


@dataclass(frozen=True)
class AgenticFlowResult:
    """Refs-only result returned by the minimal offline agentic flow."""

    run_id: str
    contract_id: str
    contract_hash: str
    status: AgenticFlowStatus
    execution_status: AgentExecutionStatus
    refs: AgenticFlowRefs
    judge_decision: JudgeReportDecision | None = None
    accepted_artifact_refs: list[str] = field(default_factory=list)
    repair_brief_ref: str | None = None
    revision_request_ref: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgenticFlowResult":
        data = require_mapping(payload, "agentic_flow_result")
        allowed = {
            "run_id",
            "contract_id",
            "contract_hash",
            "status",
            "execution_status",
            "judge_decision",
            "accepted_artifact_refs",
            "repair_brief_ref",
            "revision_request_ref",
            "ref_map",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ContractValidationError(f"agentic_flow_result contains unknown fields: {unknown}")
        judge_decision = data.get("judge_decision")
        result = cls(
            run_id=require_non_empty_str(data.get("run_id"), "agentic_flow_result.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "agentic_flow_result.contract_id"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "agentic_flow_result.contract_hash"),
            status=require_enum(data.get("status"), AgenticFlowStatus, "agentic_flow_result.status"),
            execution_status=require_enum(
                data.get("execution_status"),
                AgentExecutionStatus,
                "agentic_flow_result.execution_status",
            ),
            judge_decision=(
                None
                if judge_decision is None
                else require_enum(judge_decision, JudgeReportDecision, "agentic_flow_result.judge_decision")
            ),
            accepted_artifact_refs=_unique_refs(
                require_str_list(data.get("accepted_artifact_refs", []), "agentic_flow_result.accepted_artifact_refs"),
            ),
            repair_brief_ref=_optional_ref(data.get("repair_brief_ref"), "agentic_flow_result.repair_brief_ref"),
            revision_request_ref=_optional_ref(
                data.get("revision_request_ref"),
                "agentic_flow_result.revision_request_ref",
            ),
            refs=AgenticFlowRefs.from_dict(data.get("ref_map", {})),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if not isinstance(self.status, AgenticFlowStatus):
            raise ContractValidationError("agentic_flow_result.status must be an AgenticFlowStatus")
        if not isinstance(self.execution_status, AgentExecutionStatus):
            raise ContractValidationError("agentic_flow_result.execution_status must be an AgentExecutionStatus")
        if self.judge_decision is not None and not isinstance(self.judge_decision, JudgeReportDecision):
            raise ContractValidationError("agentic_flow_result.judge_decision must be a JudgeReportDecision")
        if self.status is AgenticFlowStatus.ACCEPTED and self.judge_decision is not JudgeReportDecision.ACCEPTED:
            raise ContractValidationError("agentic_flow_result.accepted requires an accepted judge decision")
        if self.status is AgenticFlowStatus.ACCEPTED and self.execution_status is not AgentExecutionStatus.COMPLETED:
            raise ContractValidationError("agentic_flow_result.accepted requires completed execution")
        for ref in self.accepted_artifact_refs:
            validate_ref(ref, "agentic_flow_result.accepted_artifact_refs[]")
        if self.repair_brief_ref is not None:
            validate_ref(self.repair_brief_ref, "agentic_flow_result.repair_brief_ref")
        if self.revision_request_ref is not None:
            validate_ref(self.revision_request_ref, "agentic_flow_result.revision_request_ref")
        require_non_empty_str(self.run_id, "agentic_flow_result.run_id")
        require_non_empty_str(self.contract_id, "agentic_flow_result.contract_id")
        require_non_empty_str(self.contract_hash, "agentic_flow_result.contract_hash")
        self.refs.validate()

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return dict(
            assert_refs_only_payload(
                {
                    "run_id": self.run_id,
                    "contract_id": self.contract_id,
                    "contract_hash": self.contract_hash,
                    "status": self.status.value,
                    "execution_status": self.execution_status.value,
                    "judge_decision": self.judge_decision.value if self.judge_decision else None,
                    "accepted_artifact_refs": list(self.accepted_artifact_refs),
                    "repair_brief_ref": self.repair_brief_ref,
                    "revision_request_ref": self.revision_request_ref,
                    "ref_map": self.refs.to_dict(),
                },
                "agentic_flow_result",
            )
        )


@dataclass(frozen=True)
class AgenticFlowRunner:
    """Compose contract, workspace, packet, executor, and judge boundaries."""

    root: Path | str
    refs: AgenticFlowRefs = field(default_factory=AgenticFlowRefs)
    now: Callable[[], str] = field(default_factory=lambda: _utc_now)

    def run(
        self,
        *,
        run_id: str,
        contract: TaskContract,
        workspace_policy: WorkspacePolicy,
        permission_manifest: PermissionManifest,
        executor: AgentExecutorNode,
        judge: AgentJudgeNode,
        hard_check_status: HardCheckStatus | str = HardCheckStatus.MISSING,
        hard_check_refs: list[str] | None = None,
    ) -> AgenticFlowResult:
        """Run one offline executor-then-judge cycle over refs-only packets."""

        contract.to_dict()
        workspace_policy.validate()
        permission_manifest.validate()
        if permission_manifest.unsupported_hard_policies:
            raise ContractValidationError("agentic_flow cannot run with unsupported hard policies")
        self.refs.validate()
        hard_status = require_enum(hard_check_status, HardCheckStatus, "hard_check_status")
        hard_refs = _unique_refs(hard_check_refs or [])
        if hard_status is HardCheckStatus.PASSED and not hard_refs:
            raise ContractValidationError("hard_check_status passed requires hard_check_refs")

        runtime_workspace = RunWorkspace(
            self.root,
            workspace_policy,
            _runtime_permission_manifest(
                workspace_policy,
                permission_manifest,
                self.refs,
                contract,
                hard_refs,
            ),
        )
        runtime_workspace.materialize()
        executor_workspace = ScopedAgentWorkspace(
            RunWorkspace(self.root, workspace_policy, permission_manifest),
            denied_write_refs=_executor_denied_write_refs(self.refs, contract, hard_refs),
        )
        judge_workspace = RunWorkspace(
            self.root,
            workspace_policy,
            _judge_permission_manifest(self.refs, workspace_policy, hard_refs),
        )
        scoped_judge_workspace = ScopedAgentWorkspace(
            judge_workspace,
            denied_write_refs=_judge_denied_write_refs(self.refs, contract, hard_refs),
        )

        contract_payload = contract.to_dict()
        workspace_policy_payload = workspace_policy.to_dict()
        permission_manifest_payload = permission_manifest.to_dict()
        runtime_workspace.write_json(self.refs.contract_ref, contract_payload)
        runtime_workspace.write_text(f"{_without_json_suffix(self.refs.contract_ref)}.hash", contract.contract_hash + "\n")
        runtime_workspace.write_json(contract.workspace_policy_ref, workspace_policy_payload)
        runtime_workspace.write_json(contract.permission_manifest_ref, permission_manifest_payload)

        worker_brief = project_worker_brief(
            contract,
            workspace_policy,
            permission_manifest,
            brief_id=f"{run_id}-worker-brief",
            contract_ref=self.refs.contract_ref,
            completion_report_ref=self.refs.execution_report_ref,
        )
        judge_rubric = project_judge_rubric(
            contract,
            workspace_policy,
            rubric_id=f"{run_id}-judge-rubric",
            contract_ref=self.refs.contract_ref,
            evidence_refs=[self.refs.execution_report_ref],
            hard_check_refs=hard_refs,
        )
        worker_brief_payload = worker_brief.to_dict()
        judge_rubric_payload = judge_rubric.to_dict()
        runtime_workspace.write_json(self.refs.worker_brief_ref, worker_brief_payload)
        runtime_workspace.write_json(contract.judge_rubric_ref, judge_rubric_payload)
        _ensure_existing_refs(runtime_workspace, hard_refs, "hard_check_refs")

        expected_artifact_refs = _expected_artifact_refs(contract)
        _ensure_refs_under_artifact_roots(expected_artifact_refs, workspace_policy.artifact_root_refs)
        execution_packet = AgentExecutionPacket(
            packet_id=f"{run_id}-execution-packet",
            contract_id=contract.contract_id,
            contract_hash=contract.contract_hash,
            contract_ref=self.refs.contract_ref,
            worker_brief_ref=self.refs.worker_brief_ref,
            workspace_policy_ref=contract.workspace_policy_ref,
            permission_manifest_ref=contract.permission_manifest_ref,
            report_ref=self.refs.execution_report_ref,
            worker_brief_hash=stable_json_hash(worker_brief_payload),
            workspace_policy_hash=stable_json_hash(workspace_policy_payload),
            permission_manifest_hash=stable_json_hash(permission_manifest_payload),
            expected_artifact_refs=expected_artifact_refs,
            allowed_input_refs=worker_brief.allowed_input_refs,
            writable_refs=worker_brief.writable_refs,
        )
        execution_packet_payload = execution_packet.to_dict()
        execution_packet_hash = stable_json_hash(execution_packet_payload)
        runtime_workspace.write_json(self.refs.execution_packet_ref, execution_packet_payload)
        self._append_ledger(
            runtime_workspace,
            run_id,
            contract,
            "execution_packet_issued",
            refs={"execution_packet_ref": self.refs.execution_packet_ref},
        )

        execution_report = executor.execute(
            execution_packet,
            packet_ref=self.refs.execution_packet_ref,
            workspace=executor_workspace,
        )
        if execution_report.packet_hash is None:
            execution_report = replace(execution_report, packet_hash=execution_packet_hash)
        validate_execution_report_for_packet(
            execution_report,
            execution_packet,
            packet_ref=self.refs.execution_packet_ref,
            packet_hash=execution_packet_hash,
        )
        _ensure_executor_report_authorized(execution_report, executor_workspace, runtime_workspace, workspace_policy)
        execution_report_payload = execution_report.to_dict()
        execution_report_hash = stable_json_hash(execution_report_payload)
        runtime_workspace.write_json(self.refs.execution_report_ref, execution_report_payload)
        self._append_ledger(
            runtime_workspace,
            run_id,
            contract,
            "execution_report_recorded",
            refs={"execution_report_ref": self.refs.execution_report_ref},
            status=execution_report.status.value,
        )

        judge_packet = JudgePacket(
            packet_id=f"{run_id}-judge-packet",
            contract_id=contract.contract_id,
            contract_hash=contract.contract_hash,
            contract_ref=self.refs.contract_ref,
            judge_rubric_ref=contract.judge_rubric_ref,
            execution_packet_ref=self.refs.execution_packet_ref,
            execution_report_ref=self.refs.execution_report_ref,
            report_ref=self.refs.judge_report_ref,
            hard_check_status=hard_status,
            judge_rubric_hash=stable_json_hash(judge_rubric_payload),
            execution_packet_hash=execution_packet_hash,
            execution_report_hash=execution_report_hash,
            artifact_refs=list(execution_report.produced_artifact_refs),
            evidence_refs=_unique_refs([self.refs.execution_report_ref, *execution_report.evidence_refs]),
            hard_check_refs=hard_refs,
        )
        validate_judge_packet_for_execution(
            judge_packet,
            execution_packet,
            execution_report,
            execution_packet_ref=self.refs.execution_packet_ref,
            execution_report_ref=self.refs.execution_report_ref,
            execution_packet_hash=execution_packet_hash,
            execution_report_hash=execution_report_hash,
        )
        judge_packet_payload = judge_packet.to_dict()
        judge_packet_hash = stable_json_hash(judge_packet_payload)
        runtime_workspace.write_json(self.refs.judge_packet_ref, judge_packet_payload)
        self._append_ledger(
            runtime_workspace,
            run_id,
            contract,
            "judge_packet_issued",
            refs={"judge_packet_ref": self.refs.judge_packet_ref},
        )

        judge_report = judge.judge(
            judge_packet,
            packet_ref=self.refs.judge_packet_ref,
            workspace=scoped_judge_workspace,
        )
        if judge_report.packet_hash is None:
            judge_report = replace(judge_report, packet_hash=judge_packet_hash)
        validate_judge_report_for_packet(
            judge_report,
            judge_packet,
            packet_ref=self.refs.judge_packet_ref,
            packet_hash=judge_packet_hash,
        )
        if (
            judge_report.decision is JudgeReportDecision.ACCEPTED
            and execution_report.status is not AgentExecutionStatus.COMPLETED
        ):
            raise ContractValidationError("judge_report.accepted requires completed execution")
        if judge_report.decision is JudgeReportDecision.ACCEPTED:
            _ensure_expected_artifacts_accepted(
                expected_artifact_refs,
                execution_report,
                judge_report,
                runtime_workspace,
            )
        _ensure_judge_report_authorized(judge_report, scoped_judge_workspace)
        _ensure_judge_decision_artifact(run_id, judge_report, judge_packet, scoped_judge_workspace)
        runtime_workspace.write_json(self.refs.judge_report_ref, judge_report.to_dict())

        result = self._build_result(run_id, contract, execution_report, judge_report)
        runtime_workspace.write_json(self.refs.checkpoint_ref, self._checkpoint_payload(result))
        self._append_ledger(
            runtime_workspace,
            run_id,
            contract,
            "judge_report_recorded",
            refs={
                "judge_report_ref": self.refs.judge_report_ref,
                "checkpoint_ref": self.refs.checkpoint_ref,
            },
            status=result.status.value,
        )
        return result

    def _build_result(
        self,
        run_id: str,
        contract: TaskContract,
        execution_report: AgentExecutionReport,
        judge_report: JudgeReport,
    ) -> AgenticFlowResult:
        if judge_report.decision is JudgeReportDecision.ACCEPTED:
            status = AgenticFlowStatus.ACCEPTED
        elif judge_report.decision is JudgeReportDecision.REPAIR:
            status = AgenticFlowStatus.REPAIR
        elif judge_report.decision is JudgeReportDecision.REVISION_REQUIRED:
            status = AgenticFlowStatus.REVISION_REQUIRED
        else:
            status = AgenticFlowStatus.REJECTED
        result = AgenticFlowResult(
            run_id=run_id,
            contract_id=contract.contract_id,
            contract_hash=contract.contract_hash,
            status=status,
            execution_status=execution_report.status,
            judge_decision=judge_report.decision,
            accepted_artifact_refs=list(judge_report.accepted_artifact_refs),
            repair_brief_ref=judge_report.repair_brief_ref,
            revision_request_ref=judge_report.revision_request_ref,
            refs=self.refs,
        )
        result.validate()
        return result

    def _checkpoint_payload(self, result: AgenticFlowResult) -> dict[str, object]:
        return dict(assert_refs_only_payload(result.to_dict(), "agentic_flow_checkpoint"))

    def _append_ledger(
        self,
        workspace: RunWorkspace,
        run_id: str,
        contract: TaskContract,
        event_kind: str,
        *,
        refs: dict[str, str],
        status: str | None = None,
    ) -> None:
        payload = assert_refs_only_payload(
            {
                "created_at": self.now(),
                "run_id": run_id,
                "event_kind": event_kind,
                "contract_id": contract.contract_id,
                "contract_hash": contract.contract_hash,
                "status": status,
                "ref_map": refs,
            },
            "agentic_flow_ledger_entry",
        )
        path = workspace.resolve_ref(workspace.ensure_write_ref(self.refs.decision_ledger_ref))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _runtime_permission_manifest(
    workspace_policy: WorkspacePolicy,
    worker_manifest: PermissionManifest,
    refs: AgenticFlowRefs,
    contract: TaskContract,
    hard_check_refs: list[str],
) -> PermissionManifest:
    control_refs = [
        refs.contract_ref,
        f"{_without_json_suffix(refs.contract_ref)}.hash",
        contract.workspace_policy_ref,
        contract.permission_manifest_ref,
        contract.judge_rubric_ref,
        refs.worker_brief_ref,
        refs.execution_packet_ref,
        refs.execution_report_ref,
        refs.judge_packet_ref,
        refs.judge_report_ref,
        refs.decision_ledger_ref,
        refs.checkpoint_ref,
        *hard_check_refs,
    ]
    control_roots = _unique_refs([_root_ref(ref) for ref in control_refs])
    worker_roots = _unique_refs(
        [
            *workspace_policy.input_refs,
            *workspace_policy.artifact_root_refs,
            *workspace_policy.scratch_root_refs,
            *worker_manifest.readable_refs,
            *worker_manifest.writable_refs,
        ]
    )
    return PermissionManifest(
        manifest_id=f"{worker_manifest.manifest_id}-runtime",
        readable_refs=_unique_refs([*control_roots, *worker_roots]),
        writable_refs=_unique_refs([*control_roots, *worker_manifest.writable_refs]),
        denied_refs=list(worker_manifest.denied_refs),
        allowed_commands=[],
        network_policy=worker_manifest.network_policy,
        env_allowlist=[],
        unsupported_hard_policies=list(worker_manifest.unsupported_hard_policies),
    )


def _judge_permission_manifest(
    refs: AgenticFlowRefs,
    workspace_policy: WorkspacePolicy,
    hard_check_refs: list[str],
) -> PermissionManifest:
    readable = _unique_refs(
        [
            _root_ref(refs.contract_ref),
            _root_ref(refs.worker_brief_ref),
            _root_ref(refs.execution_packet_ref),
            _root_ref(refs.execution_report_ref),
            _root_ref(refs.judge_packet_ref),
            _root_ref(refs.judge_report_ref),
            _root_ref(refs.decision_ledger_ref),
            *(_root_ref(ref) for ref in hard_check_refs),
            *workspace_policy.artifact_root_refs,
            "reports",
            "contract",
            "projections",
            "policy",
            "packets",
            "revisions",
        ]
    )
    writable = _unique_refs(["reports", "projections", "revisions"])
    return PermissionManifest(
        manifest_id="judge-piworker-permissions",
        readable_refs=readable,
        writable_refs=writable,
        denied_refs=[],
    )


def _executor_denied_write_refs(
    refs: AgenticFlowRefs,
    contract: TaskContract,
    hard_check_refs: list[str],
) -> list[str]:
    return _unique_refs(
        [
            _root_ref(refs.contract_ref),
            _root_ref(contract.workspace_policy_ref),
            _root_ref(contract.permission_manifest_ref),
            _root_ref(contract.judge_rubric_ref),
            _root_ref(refs.worker_brief_ref),
            _root_ref(refs.execution_packet_ref),
            refs.execution_report_ref,
            refs.judge_packet_ref,
            refs.judge_report_ref,
            refs.decision_ledger_ref,
            _root_ref(refs.checkpoint_ref),
            *hard_check_refs,
        ]
    )


def _judge_denied_write_refs(
    refs: AgenticFlowRefs,
    contract: TaskContract,
    hard_check_refs: list[str],
) -> list[str]:
    return _unique_refs(
        [
            _root_ref(refs.contract_ref),
            _root_ref(contract.workspace_policy_ref),
            _root_ref(contract.permission_manifest_ref),
            refs.worker_brief_ref,
            contract.judge_rubric_ref,
            _root_ref(refs.execution_packet_ref),
            refs.execution_report_ref,
            refs.judge_packet_ref,
            refs.judge_report_ref,
            refs.decision_ledger_ref,
            _root_ref(refs.checkpoint_ref),
            *hard_check_refs,
        ]
    )


def _expected_artifact_refs(contract: TaskContract) -> list[str]:
    return _unique_refs([ref for output in contract.required_outputs for ref in output.refs])


def _ensure_refs_under_artifact_roots(refs: list[str], artifact_root_refs: list[str]) -> None:
    roots = _unique_refs(artifact_root_refs)
    for ref in refs:
        if not any(ref_is_under(ref, root) for root in roots):
            raise ContractValidationError(f"artifact ref is outside artifact roots: {ref}")


def _ensure_executor_report_authorized(
    report: AgentExecutionReport,
    agent_workspace: AgentWorkspace,
    runtime_workspace: RunWorkspace,
    workspace_policy: WorkspacePolicy,
) -> None:
    _ensure_refs_under_artifact_roots(report.produced_artifact_refs, workspace_policy.artifact_root_refs)
    for ref in [
        *report.produced_artifact_refs,
        *report.changed_refs,
        *report.evidence_refs,
        *report.metric_refs,
        *([report.repair_request_ref] if report.repair_request_ref else []),
        *([report.revision_request_ref] if report.revision_request_ref else []),
    ]:
        agent_workspace.ensure_write_ref(ref)
    _ensure_existing_refs(runtime_workspace, report.produced_artifact_refs, "produced_artifact_refs")


def _ensure_judge_report_authorized(report: JudgeReport, workspace: AgentWorkspace) -> None:
    for ref in [*report.evidence_refs, *report.accepted_artifact_refs]:
        workspace.ensure_read_ref(ref)
    for ref in [
        *report.rationale_refs,
        *([report.repair_brief_ref] if report.repair_brief_ref else []),
        *([report.revision_request_ref] if report.revision_request_ref else []),
    ]:
        workspace.ensure_write_ref(ref)


def _ensure_judge_decision_artifact(
    run_id: str,
    report: JudgeReport,
    packet: JudgePacket,
    workspace: AgentWorkspace,
) -> None:
    if report.decision is JudgeReportDecision.REPAIR:
        if report.repair_brief_ref is None:
            raise ContractValidationError("judge_report.repair requires repair_brief_ref")
        brief = cast(RepairBrief, _read_decision_artifact(workspace, report.repair_brief_ref, RepairBrief, "repair_brief"))
        validate_repair_brief_for_judge(brief, packet, report, run_id=run_id)
    elif report.decision is JudgeReportDecision.REVISION_REQUIRED:
        if report.revision_request_ref is None:
            raise ContractValidationError("judge_report.revision_required requires revision_request_ref")
        request = cast(
            TaskRevisionRequest,
            _read_decision_artifact(
                workspace,
                report.revision_request_ref,
                TaskRevisionRequest,
                "task_revision_request",
            ),
        )
        validate_revision_request_for_judge(request, packet, report, run_id=run_id)


def _read_decision_artifact(
    workspace: AgentWorkspace,
    ref: str,
    artifact_type: type[RepairBrief] | type[TaskRevisionRequest],
    field_name: str,
) -> RepairBrief | TaskRevisionRequest:
    try:
        payload = workspace.read_json(ref)
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"{field_name} ref is missing or unreadable: {ref}") from exc
    return artifact_type.from_dict(payload)


def _ensure_expected_artifacts_accepted(
    expected_artifact_refs: list[str],
    execution_report: AgentExecutionReport,
    judge_report: JudgeReport,
    workspace: RunWorkspace,
) -> None:
    for ref in expected_artifact_refs:
        if ref not in execution_report.produced_artifact_refs:
            raise ContractValidationError(f"accepted run missing produced artifact ref: {ref}")
        if ref not in judge_report.accepted_artifact_refs:
            raise ContractValidationError(f"accepted run missing accepted artifact ref: {ref}")
    _ensure_existing_refs(workspace, expected_artifact_refs, "expected_artifact_refs")


def _ensure_existing_refs(workspace: RunWorkspace, refs: list[str], field_name: str) -> None:
    for ref in refs:
        safe_ref = workspace.ensure_read_ref(ref)
        path = workspace.resolve_ref(safe_ref)
        if not path.exists() or not path.is_file():
            raise ContractValidationError(f"{field_name} does not exist: {safe_ref}")


def _unique_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        safe_ref = validate_ref(ref, "agentic_flow.ref")
        if safe_ref not in result:
            result.append(safe_ref)
    return result


def _root_ref(ref: str) -> str:
    return validate_ref(ref, "agentic_flow.ref").split("/", 1)[0]


def _without_json_suffix(ref: str) -> str:
    safe_ref = validate_ref(ref, "agentic_flow.ref")
    if safe_ref.endswith(".json"):
        return safe_ref[:-5]
    return safe_ref


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return validate_ref(value, field_name)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
