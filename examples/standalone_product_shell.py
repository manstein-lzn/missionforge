"""Standalone product shell built from MissionForge public primitives.

Run from the repository root:

    PYTHONPATH=src python3 examples/standalone_product_shell.py /tmp/mf-standalone-demo

The example intentionally keeps product meaning outside ``src/missionforge``.
It compiles a tiny product request into TaskContract-native primitives, runs a
deterministic executor and independent judge, and prints refs a caller can
inspect.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile

from missionforge import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    AgentWorkspace,
    AgenticFlowStatus,
    HardCheckStatus,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
    PermissionManifest,
    TaskContract,
    WorkspacePolicy,
    create_default_task_contract_flow,
    replay_decision_ledger,
)
from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeConfig


@dataclass(frozen=True)
class MiniDocRequest:
    product_id: str
    title: str
    audience: str
    required_topic: str


def compile_request(request: MiniDocRequest) -> tuple[TaskContract, WorkspacePolicy, PermissionManifest]:
    """Compile product meaning into MissionForge contracts."""

    contract = TaskContract.from_dict(
        {
            "schema_version": "task_contract.v1",
            "contract_id": f"{request.product_id}-contract",
            "product_id": request.product_id,
            "objective": f"Write a short README titled {request.title}.",
            "background": f"The README is for {request.audience}.",
            "users_or_audience": [request.audience],
            "non_goals": ["Do not modify files outside the declared package refs."],
            "assumptions": ["The product integration already chose the package shape."],
            "required_outputs": [
                {
                    "output_id": "readme",
                    "description": "Product README artifact.",
                    "artifact_refs": ["package/README.md"],
                }
            ],
            "hard_constraints": [
                {
                    "constraint_id": "workspace",
                    "statement": "Write only under package/ and reports/.",
                    "source_refs": ["policy/permission_manifest.json"],
                }
            ],
            "semantic_acceptance": [
                {
                    "criterion_id": "topic",
                    "statement": f"The README explains {request.required_topic}.",
                    "evidence_refs": ["package/README.md"],
                }
            ],
            "risk_notes": ["Request explicit revision if the topic is wrong."],
            "source_refs": ["product/request.json"],
            "workspace_policy_ref": "policy/workspace_policy.json",
            "permission_manifest_ref": "policy/permission_manifest.json",
            "judge_rubric_ref": "projections/judge_rubric.json",
            "revision_policy": {"mode": "explicit_revision_required"},
            "created_by": "examples.standalone_product_shell",
            "created_at": "2026-06-12T00:00:00Z",
        }
    )
    workspace_policy = WorkspacePolicy.from_dict(
        {
            "policy_id": f"{request.product_id}-workspace",
            "workspace_root_ref": "runs/mini-doc",
            "input_refs": ["product", "policy", "contract", "projections"],
            "artifact_root_refs": ["package"],
            "scratch_root_refs": ["scratch"],
            "denied_refs": ["secrets"],
        }
    )
    permission_manifest = PermissionManifest.from_dict(
        {
            "manifest_id": f"{request.product_id}-permissions",
            "workspace_policy_ref": "policy/workspace_policy.json",
            "readable_refs": ["product", "policy", "contract", "projections", "package", "reports"],
            "writable_refs": ["package", "reports", "ledgers"],
            "denied_refs": ["secrets"],
            "network_policy": "disabled",
        }
    )
    return contract, workspace_policy, permission_manifest


class MiniDocExecutor:
    def __init__(self, request: MiniDocRequest) -> None:
        self.request = request

    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        content = (
            f"# {self.request.title}\n\n"
            f"Audience: {self.request.audience}\n\n"
            f"This README explains {self.request.required_topic}.\n"
        )
        workspace.write_text("package/README.md", content)
        workspace.write_json(
            "reports/executor_evidence.json",
            {"status": "completed", "artifact_refs": ["package/README.md"]},
        )
        return AgentExecutionReport(
            report_id="mini-doc-execution-report",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.COMPLETED,
            produced_artifact_refs=["package/README.md"],
            changed_refs=["package/README.md"],
            evidence_refs=["reports/executor_evidence.json"],
        )


class MiniDocJudge:
    def __init__(self, request: MiniDocRequest) -> None:
        self.request = request

    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        content = workspace.read_text("package/README.md")
        accepted = self.request.required_topic in content and content.startswith(f"# {self.request.title}")
        return JudgeReport(
            report_id="mini-doc-judge-report",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            role=packet.role,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.ACCEPTED if accepted else JudgeReportDecision.REJECTED,
            hard_check_status=packet.hard_check_status,
            accepted_artifact_refs=["package/README.md"] if accepted else [],
            evidence_refs=["package/README.md", "reports/execution_report.json"],
        )


def run(workspace_root: str | Path | None = None) -> dict[str, object]:
    root = Path(workspace_root) if workspace_root is not None else Path(tempfile.mkdtemp(prefix="mf-standalone-"))
    request = MiniDocRequest(
        product_id="mini-doc",
        title="MiniDoc Product Shell",
        audience="MissionForge programmers",
        required_topic="TaskContract-native product integration",
    )
    contract, workspace_policy, permission_manifest = compile_request(request)

    run_root = root / workspace_policy.workspace_root_ref
    (run_root / "product").mkdir(parents=True, exist_ok=True)
    (run_root / "reports").mkdir(parents=True, exist_ok=True)
    (run_root / "product/request.json").write_text(
        '{"request_ref":"product/request.json"}\n',
        encoding="utf-8",
    )
    (run_root / "reports/hard_checks.json").write_text(
        '{"status":"passed","checked_refs":["policy/permission_manifest.json"]}\n',
        encoding="utf-8",
    )

    preset = create_default_task_contract_flow(
        root,
        piworker_config=PiAgentRuntimeConfig(provider_mode="faux"),
    )
    result = preset.runner.run(
        run_id="mini-doc",
        contract=contract,
        workspace_policy=workspace_policy,
        permission_manifest=permission_manifest,
        executor=MiniDocExecutor(request),
        judge=MiniDocJudge(request),
        hard_check_status=HardCheckStatus.PASSED,
        hard_check_refs=["reports/hard_checks.json"],
    )
    replay = replay_decision_ledger(run_root, decision_ledger_ref="ledgers/decision_ledger.jsonl")
    return {
        "workspace": str(root),
        "status": result.status.value,
        "replay_status": replay.status.value,
        "final_package_ref": result.refs.final_package_ref,
        "accepted_artifact_refs": list(result.accepted_artifact_refs),
    }


def main(argv: list[str]) -> int:
    summary = run(argv[1] if len(argv) > 1 else None)
    for key, value in summary.items():
        print(f"{key}={value}")
    return 0 if summary["status"] == AgenticFlowStatus.ACCEPTED.value else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
