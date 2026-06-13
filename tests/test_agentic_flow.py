from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.agent_packets import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    HardCheckStatus,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
)
from missionforge.agentic_flow import (
    AgentWorkspace,
    AgenticFlowRefs,
    AgenticFlowRunner,
    AgenticFlowStatus,
)
from missionforge.agentic_ledger import RunReplayStatus, replay_decision_ledger
from missionforge.agentic_repair import RepairBrief, TaskRevisionRequest
from missionforge.contracts import ContractValidationError, stable_json_hash
from missionforge.task_contract import (
    PermissionManifest,
    TaskContract,
    WorkspacePolicy,
)
from missionforge.adapters.pi_agent_provider_config import load_codex_current_provider
from missionforge.adapters.pi_agent_runtime import PiAgentExecutorNode, PiAgentJudgeNode, PiAgentRuntimeConfig
from missionforge.adapters.task_contract_runtime import TaskContractFlowPreset, create_default_task_contract_flow


def sample_contract() -> TaskContract:
    return TaskContract.from_dict(
        {
            "schema_version": "task_contract.v1",
            "contract_id": "contract-001",
            "product_id": "product.generic",
            "objective": "Produce the requested deliverable inside the declared workspace.",
            "background": "Compiled from a FrontDesk intent bundle by product integration.",
            "users_or_audience": ["operator"],
            "non_goals": ["Do not change unrelated files."],
            "assumptions": ["Inputs are available by ref."],
            "required_outputs": [
                {
                    "output_id": "out-001",
                    "description": "Write the declared final artifact.",
                    "artifact_refs": ["artifacts/final.md"],
                }
            ],
            "hard_constraints": [
                {
                    "constraint_id": "hc-001",
                    "statement": "Stay inside the declared writable roots.",
                    "source_refs": ["policy/permission_manifest.json"],
                }
            ],
            "semantic_acceptance": [
                {
                    "criterion_id": "acc-001",
                    "statement": "The artifact satisfies the frozen task objective.",
                    "evidence_refs": ["reports/execution_report.json"],
                }
            ],
            "risk_notes": ["Ask for explicit revision if the contract is wrong."],
            "source_refs": ["frontdesk/intent_bundle.json"],
            "workspace_policy_ref": "policy/workspace_policy.json",
            "permission_manifest_ref": "policy/permission_manifest.json",
            "judge_rubric_ref": "projections/judge_rubric.json",
            "revision_policy": {"mode": "explicit_revision_required"},
            "created_by": "product.integration",
            "created_at": "2026-05-31T00:00:00Z",
        }
    )


def sample_workspace_policy() -> WorkspacePolicy:
    return WorkspacePolicy.from_dict(
        {
            "policy_id": "workspace-001",
            "workspace_root_ref": "runs/run-001",
            "input_refs": ["frontdesk"],
            "artifact_root_refs": ["artifacts"],
            "scratch_root_refs": ["scratch"],
            "denied_refs": ["secrets"],
        }
    )


def sample_permission_manifest(writable_refs: list[str] | None = None) -> PermissionManifest:
    return PermissionManifest.from_dict(
        {
            "manifest_id": "perm-001",
            "workspace_policy_ref": "policy/workspace_policy.json",
            "readable_refs": ["frontdesk", "policy", "contract"],
            "writable_refs": writable_refs or ["artifacts", "reports", "ledgers"],
            "denied_refs": ["secrets"],
            "network_policy": "disabled",
        }
    )


def sample_permission_manifest_with_unsupported_policy() -> PermissionManifest:
    return PermissionManifest.from_dict(
        {
            "manifest_id": "perm-001",
            "workspace_policy_ref": "policy/workspace_policy.json",
            "readable_refs": ["frontdesk", "policy", "contract"],
            "writable_refs": ["artifacts", "reports"],
            "unsupported_hard_policies": ["shell_command_sandbox"],
        }
    )


class CompletingExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        workspace.write_text("artifacts/final.md", "deliverable")
        workspace.write_text("reports/executor_evidence.md", "execution evidence")
        return AgentExecutionReport(
            report_id="execution-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.COMPLETED,
            produced_artifact_refs=["artifacts/final.md"],
            changed_refs=["artifacts/final.md"],
            evidence_refs=["reports/executor_evidence.md"],
            metric_refs=["ledgers/executor_metrics.jsonl"],
        )


class OutsideArtifactExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        return AgentExecutionReport(
            report_id="execution-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.COMPLETED,
            produced_artifact_refs=["secrets/final.md"],
            changed_refs=["secrets/final.md"],
        )


class EmptyArtifactExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        return AgentExecutionReport(
            report_id="execution-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.COMPLETED,
        )


class UnwrittenArtifactExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        return AgentExecutionReport(
            report_id="execution-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.COMPLETED,
            produced_artifact_refs=["artifacts/final.md"],
            changed_refs=["artifacts/final.md"],
        )


class LedgerWritingExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        workspace.write_text("ledgers/decision_ledger.jsonl", "forged")
        raise AssertionError("control write should fail before executor returns")


class HardCheckWritingExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        workspace.write_text("reports/hard_checks.json", '{"status": "mutated"}')
        raise AssertionError("hard-check write should fail before executor returns")


class RuntimeProjectionWritingExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        workspace.write_text("reports/piworker_runtime/forged.json", "{}")
        raise AssertionError("runtime projection write should fail before executor returns")


class BlockedExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        return AgentExecutionReport(
            report_id="execution-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.BLOCKED,
        )


class AcceptingJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        workspace.write_text("reports/judge_rationale.md", "judge rationale")
        return JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.ACCEPTED,
            hard_check_status=packet.hard_check_status,
            rationale_refs=["reports/judge_rationale.md"],
            evidence_refs=[packet.execution_report_ref],
            accepted_artifact_refs=list(packet.artifact_refs),
        )


class BadArtifactJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        return JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.ACCEPTED,
            hard_check_status=packet.hard_check_status,
            evidence_refs=[packet.execution_report_ref],
            accepted_artifact_refs=["artifacts/not-produced.md"],
        )


class RepairJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        repair_brief_ref = "projections/repair_brief.json"
        workspace.write_json(
            repair_brief_ref,
            RepairBrief(
                brief_id="repair-brief-001",
                run_id="run-repair",
                contract_id=packet.contract_id,
                contract_hash=packet.contract_hash,
                contract_ref=packet.contract_ref,
                judge_packet_ref=packet_ref,
                judge_report_ref=packet.report_ref,
                execution_report_ref=packet.execution_report_ref,
                reason="Artifact needs a targeted repair while preserving the frozen contract.",
                repair_steps=["Update the produced artifact to satisfy the judge rubric."],
                target_artifact_refs=list(packet.artifact_refs),
                evidence_refs=[packet.execution_report_ref],
            ).to_dict(),
        )
        return JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.REPAIR,
            hard_check_status=packet.hard_check_status,
            evidence_refs=[packet.execution_report_ref],
            repair_brief_ref=repair_brief_ref,
        )


class RevisionJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        revision_request_ref = "revisions/request.json"
        workspace.write_json(
            revision_request_ref,
            TaskRevisionRequest(
                request_id="revision-request-001",
                run_id="run-revision",
                contract_id=packet.contract_id,
                contract_hash=packet.contract_hash,
                contract_ref=packet.contract_ref,
                judge_packet_ref=packet_ref,
                judge_report_ref=packet.report_ref,
                execution_report_ref=packet.execution_report_ref,
                reason="The frozen contract appears incomplete; repair alone is insufficient.",
                proposed_contract_changes=["Clarify the semantic acceptance clause before continuing."],
                evidence_refs=[packet.execution_report_ref],
            ).to_dict(),
        )
        return JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.REVISION_REQUIRED,
            hard_check_status=packet.hard_check_status,
            evidence_refs=[packet.execution_report_ref],
            revision_request_ref=revision_request_ref,
        )


class InvalidRepairBriefJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        workspace.write_json("projections/repair_brief.json", {})
        return JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.REPAIR,
            hard_check_status=packet.hard_check_status,
            evidence_refs=[packet.execution_report_ref],
            repair_brief_ref="projections/repair_brief.json",
        )


class WrongRevisionRequestJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        workspace.write_json(
            "revisions/request.json",
            {
                "schema_version": "task_revision_request.v1",
                "request_id": "revision-request-001",
                "run_id": "run-revision",
                "contract_id": packet.contract_id,
                "contract_hash": "sha256:" + ("0" * 64),
                "contract_ref": packet.contract_ref,
                "judge_packet_ref": packet_ref,
                "judge_report_ref": packet.report_ref,
                "execution_report_ref": packet.execution_report_ref,
                "reason": "Bad request with mismatched contract hash.",
                "proposed_contract_changes": ["Clarify acceptance."],
                "authority_required": "product_integration",
                "evidence_refs": [packet.execution_report_ref],
            },
        )
        return JudgeReport(
            report_id="judge-report-001",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.REVISION_REQUIRED,
            hard_check_status=packet.hard_check_status,
            evidence_refs=[packet.execution_report_ref],
            revision_request_ref="revisions/request.json",
        )


class ExecutionReportWritingJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        workspace.write_text("reports/execution_report.json", "{}")
        raise AssertionError("control write should fail before judge returns")


class HardCheckWritingJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        workspace.write_text("reports/hard_checks.json", '{"status": "mutated"}')
        raise AssertionError("hard-check write should fail before judge returns")


class MinimalPiRuntimeRunner:
    def run(self, command, *, input_path: Path, cwd: Path, timeout_seconds: int, env):
        from missionforge.adapters.pi_agent_runtime import PI_AGENT_OUTPUT_SCHEMA_VERSION, PiAgentCommandResult

        runtime_input = json.loads(input_path.read_text(encoding="utf-8"))
        role = runtime_input["piworker_call"]["role"]
        output_ref = str(runtime_input["output_ref"])
        session_ref = str(runtime_input["session_ref"])
        events_ref = str(runtime_input["events_ref"])
        metrics_ref = str(runtime_input["metrics_ref"])
        savepoints_ref = str(runtime_input["savepoints_ref"])
        metrics = {"tool_call_count": 1, "total_tokens": 3, "tool_error_count": 0}

        _write_file(cwd / session_ref, "{}\n")
        _write_file(cwd / events_ref, "{}\n")
        _write_file(cwd / metrics_ref, json.dumps(metrics, sort_keys=True) + "\n")
        _write_file(cwd / savepoints_ref, '{"schema_version": "missionforge.pi_agent_runtime_savepoint.v1"}\n')

        if role == "judge_piworker":
            spec_ref = str(runtime_input["call_spec"]["visible_refs"][0])
            spec = json.loads((cwd / spec_ref).read_text(encoding="utf-8"))
            report_ref = str(spec["report_ref"])
            _write_file(
                cwd / report_ref,
                json.dumps(
                    {
                        "schema_version": "judge_report.v1",
                        "report_id": "judge-report-001",
                        "packet_id": runtime_input["call_id"],
                        "packet_ref": spec["packet_ref"],
                        "packet_hash": spec["packet_hash"],
                        "contract_id": runtime_input["mission_id"],
                        "contract_hash": runtime_input["piworker_call"]["contract_hash"],
                        "contract_ref": spec["contract_ref"],
                        "decision": "accepted",
                        "hard_check_status": spec["hard_check_status"],
                        "rationale_refs": ["reports/judge_rationale.md"],
                        "evidence_refs": [spec["execution_report_ref"]],
                        "accepted_artifact_refs": spec["artifact_refs"],
                    },
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
            )
            _write_file(cwd / "reports/judge_rationale.md", "accepted\n")
            produced_artifacts = [report_ref]
            changed_refs = [report_ref]
            verifier_evidence = [report_ref]
        else:
            produced_artifacts = [str(ref) for ref in runtime_input["piworker_call"]["expected_output_refs"]]
            for ref in produced_artifacts:
                _write_file(cwd / ref, "MissionForge FrontDesk live smoke passed\n")
            changed_refs = list(produced_artifacts)
            verifier_evidence = list(produced_artifacts)

        _write_file(
            cwd / output_ref,
            json.dumps(
                {
                    "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
                    "call_id": runtime_input["call_id"],
                    "status": "completed",
                    "produced_artifacts": produced_artifacts,
                    "changed_refs": changed_refs,
                    "commands_run": [],
                    "tests_run": [],
                    "failures": [],
                    "worker_claims": ["assistant_final_text_present:length=20"],
                    "verifier_evidence": verifier_evidence,
                    "new_unknowns": [],
                    "recommended_next_steps": [],
                    "verification_status": "not_run",
                    "input_ref": runtime_input["input_ref"],
                    "output_ref": output_ref,
                    "session_ref": session_ref,
                    "events_ref": events_ref,
                    "metrics_ref": metrics_ref,
                    "savepoints_ref": savepoints_ref,
                    "duration_ms": 1,
                    "metrics": metrics,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
        )
        return PiAgentCommandResult(returncode=0)


class AgenticFlowTests(unittest.TestCase):
    def test_offline_accepted_flow_writes_refs_only_artifacts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            result = AgenticFlowRunner(tmpdir, now=lambda: "2026-05-31T00:00:00Z").run(
                run_id="run-001",
                contract=sample_contract(),
                workspace_policy=sample_workspace_policy(),
                permission_manifest=sample_permission_manifest(),
                executor=CompletingExecutor(),
                judge=AcceptingJudge(),
                hard_check_status=HardCheckStatus.PASSED,
                hard_check_refs=["reports/hard_checks.json"],
            )

            self.assertEqual(result.status, AgenticFlowStatus.ACCEPTED)
            self.assertEqual(result.judge_decision, JudgeReportDecision.ACCEPTED)
            self.assertEqual(result.accepted_artifact_refs, ["artifacts/final.md"])
            self.assertIn("ref_map", result.to_dict())
            self.assertNotIn("refs", result.to_dict())

            root = sample_workspace_policy().workspace_root_ref
            base = f"{tmpdir}/{root}"
            self.assertTrue(_exists(f"{base}/contract/task_contract.json"))
            self.assertTrue(_exists(f"{base}/projections/worker_brief.json"))
            self.assertTrue(_exists(f"{base}/projections/judge_rubric.json"))
            self.assertTrue(_exists(f"{base}/packets/execution_packet.json"))
            self.assertTrue(_exists(f"{base}/packets/judge_packet.json"))
            self.assertTrue(_exists(f"{base}/reports/execution_report.json"))
            self.assertTrue(_exists(f"{base}/reports/judge_report.json"))
            execution_packet = json.loads(Path(f"{base}/packets/execution_packet.json").read_text(encoding="utf-8"))
            execution_report = json.loads(Path(f"{base}/reports/execution_report.json").read_text(encoding="utf-8"))
            judge_packet = json.loads(Path(f"{base}/packets/judge_packet.json").read_text(encoding="utf-8"))
            judge_report = json.loads(Path(f"{base}/reports/judge_report.json").read_text(encoding="utf-8"))
            self.assertEqual(execution_report["packet_hash"], stable_json_hash(execution_packet))
            self.assertEqual(judge_packet["execution_packet_hash"], stable_json_hash(execution_packet))
            self.assertEqual(judge_packet["execution_report_hash"], stable_json_hash(execution_report))
            self.assertEqual(judge_report["packet_hash"], stable_json_hash(judge_packet))
            self.assertTrue(_exists(f"{base}/checkpoints/latest.json"))
            self.assertTrue(_exists(f"{base}/packages/final_package.json"))
            self.assertEqual(_line_count(f"{base}/ledgers/decision_ledger.jsonl"), 8)
            entries = [
                json.loads(line)
                for line in Path(f"{base}/ledgers/decision_ledger.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [entry["event_kind"] for entry in entries],
                [
                    "contract_frozen",
                    "projection_written",
                    "hard_checks_recorded",
                    "execution_packet_issued",
                    "execution_report_recorded",
                    "judge_packet_issued",
                    "judge_report_recorded",
                    "final_package_emitted",
                ],
            )
            self.assertTrue(all(entry["contract_hash"] == result.contract_hash for entry in entries))
            self.assertTrue(all("ref_map" in entry for entry in entries))
            ledger_text = json.dumps(entries, sort_keys=True)
            for forbidden in ["raw_transcript", "provider_payload", "stdout", "stderr", "deliverable"]:
                self.assertNotIn(forbidden, ledger_text)

            final_package = json.loads(Path(f"{base}/packages/final_package.json").read_text(encoding="utf-8"))
            self.assertEqual(final_package["contract_hash"], result.contract_hash)
            self.assertEqual(final_package["judge_report_ref"], "reports/judge_report.json")
            self.assertEqual(final_package["accepted_artifact_refs"], ["artifacts/final.md"])
            self.assertEqual(final_package["hard_check_refs"], ["reports/hard_checks.json"])
            self.assertEqual(final_package["metric_refs"], ["ledgers/executor_metrics.jsonl"])

            replay = replay_decision_ledger(base, decision_ledger_ref="ledgers/decision_ledger.jsonl")
            self.assertEqual(replay.status, RunReplayStatus.ACCEPTED)
            self.assertEqual(replay.final_package_ref, "packages/final_package.json")
            self.assertEqual(replay.accepted_artifact_refs, ["artifacts/final.md"])

            checkpoint = json.loads(Path(f"{base}/checkpoints/latest.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["status"], "accepted")
            self.assertEqual(checkpoint["ref_map"]["judge_report_ref"], "reports/judge_report.json")


    def test_default_task_contract_flow_preset_assembles_piworker_nodes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            preset = create_default_task_contract_flow(
                tmpdir,
                piworker_config=PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
            )
            self.assertIsInstance(preset, TaskContractFlowPreset)
            self.assertIsInstance(preset.runner, AgenticFlowRunner)
            self.assertIsInstance(preset.executor, PiAgentExecutorNode)
            self.assertIsInstance(preset.judge, PiAgentJudgeNode)
            self.assertEqual(Path(preset.runner.root), Path(tmpdir))

    def test_default_piworker_flow_does_not_require_worker_attempts_permission(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            root = Path(tmpdir)
            run_root = root / sample_workspace_policy().workspace_root_ref
            (run_root / "contract").mkdir(parents=True, exist_ok=True)
            (run_root / "projections").mkdir(parents=True, exist_ok=True)
            (run_root / "policy").mkdir(parents=True, exist_ok=True)
            (run_root / "frontdesk").mkdir(parents=True, exist_ok=True)
            (run_root / "frontdesk/intent_bundle.json").write_text('{"summary_ref":"frontdesk/intent_bundle.json"}\n', encoding="utf-8")

            preset = create_default_task_contract_flow(
                tmpdir,
                piworker_config=PiAgentRuntimeConfig(command=("pi-agent-runtime",)),
                piworker_runner=MinimalPiRuntimeRunner(),
            )

            result = preset.runner.run(
                run_id="run-001",
                contract=sample_contract(),
                workspace_policy=sample_workspace_policy(),
                permission_manifest=sample_permission_manifest(writable_refs=["artifacts", "reports", "ledgers"]),
                executor=preset.executor,
                judge=preset.judge,
                hard_check_status=HardCheckStatus.PASSED,
                hard_check_refs=["reports/hard_checks.json"],
            )

            execution_report = json.loads((run_root / "reports/execution_report.json").read_text(encoding="utf-8"))
            judge_packet = json.loads((run_root / "packets/judge_packet.json").read_text(encoding="utf-8"))

            self.assertEqual(result.status, AgenticFlowStatus.ACCEPTED)
            self.assertTrue((run_root / "attempts/run-001-execution-packet/pi_agent_input.json").exists())
            self.assertTrue((run_root / "attempts/run-001-execution-packet/piworker_call_result.json").exists())
            self.assertNotIn("attempts", json.dumps(execution_report, sort_keys=True))
            self.assertNotIn("attempts", json.dumps(judge_packet, sort_keys=True))
            self.assertTrue(all(ref.startswith("reports/") for ref in execution_report["evidence_refs"]))

    @unittest.skipUnless(
        os.environ.get("MISSIONFORGE_PI_AGENT_LIVE_SMOKE") == "1",
        "set MISSIONFORGE_PI_AGENT_LIVE_SMOKE=1 to run the live TaskContract smoke",
    )
    def test_live_codex_current_default_task_contract_flow_accepts(self) -> None:
        config = PiAgentRuntimeConfig(
            timeout_seconds=int(os.environ.get("MISSIONFORGE_PI_AGENT_LIVE_TIMEOUT_SECONDS", "180")),
            provider_mode="live",
            provider_config_source="codex_current",
            metadata={"phase": "task_contract_live_smoke"},
        )

        with TemporaryDirectory() as tmpdir:
            provider = load_codex_current_provider()
            root = Path(tmpdir)
            (root / "runs/run-001/reports").mkdir(parents=True, exist_ok=True)
            (root / "runs/run-001/frontdesk").mkdir(parents=True, exist_ok=True)
            (root / "runs/run-001/policy").mkdir(parents=True, exist_ok=True)
            (root / "runs/run-001/projections").mkdir(parents=True, exist_ok=True)
            (root / "runs/run-001/contract").mkdir(parents=True, exist_ok=True)
            (root / "runs/run-001/frontdesk/intent_bundle.json").write_text(
                '{"summary_ref":"frontdesk/intent_bundle.json"}\n',
                encoding="utf-8",
            )
            _write_hard_check(tmpdir)
            preset = create_default_task_contract_flow(
                tmpdir,
                piworker_config=config,
            )

            result = preset.runner.run(
                run_id="run-001",
                contract=sample_contract(),
                workspace_policy=sample_workspace_policy(),
                permission_manifest=sample_permission_manifest(),
                executor=preset.executor,
                judge=preset.judge,
                hard_check_status=HardCheckStatus.PASSED,
                hard_check_refs=["reports/hard_checks.json"],
            )

            root_text = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in Path(tmpdir).rglob("*")
                if path.is_file()
            )

        self.assertEqual(result.status, AgenticFlowStatus.ACCEPTED)
        self.assertFalse(provider["api_key"] in root_text, "live API key leaked into workspace artifacts")
        self.assertNotIn("OPENAI_API_KEY", root_text)

    def test_passed_hard_checks_require_explicit_refs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=CompletingExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                )

        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=CompletingExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_unsupported_hard_policies_fail_closed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest_with_unsupported_policy(),
                    executor=CompletingExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_executor_report_refs_must_stay_inside_worker_permissions(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=OutsideArtifactExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_executor_and_judge_cannot_write_runtime_owned_control_refs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=LedgerWritingExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=RuntimeProjectionWritingExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=CompletingExecutor(),
                    judge=ExecutionReportWritingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=HardCheckWritingExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=CompletingExecutor(),
                    judge=HardCheckWritingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_required_artifacts_must_be_worker_writable(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(writable_refs=["reports"]),
                    executor=CompletingExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_accepted_runs_require_required_artifacts_to_be_produced_and_existing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=EmptyArtifactExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=UnwrittenArtifactExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_judge_cannot_accept_failed_hard_checks_or_incomplete_execution(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=CompletingExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.FAILED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=BlockedExecutor(),
                    judge=AcceptingJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_judge_cannot_accept_artifacts_not_in_judge_packet(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-001",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=CompletingExecutor(),
                    judge=BadArtifactJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_repair_and_revision_decisions_route_refs_without_acceptance(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            repair = AgenticFlowRunner(tmpdir).run(
                run_id="run-repair",
                contract=sample_contract(),
                workspace_policy=sample_workspace_policy(),
                permission_manifest=sample_permission_manifest(),
                executor=CompletingExecutor(),
                judge=RepairJudge(),
                hard_check_status=HardCheckStatus.PASSED,
                hard_check_refs=["reports/hard_checks.json"],
            )
            self.assertEqual(repair.status, AgenticFlowStatus.REPAIR)
            self.assertEqual(repair.repair_brief_ref, "projections/repair_brief.json")
            self.assertEqual(repair.accepted_artifact_refs, [])

        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            revision = AgenticFlowRunner(tmpdir).run(
                run_id="run-revision",
                contract=sample_contract(),
                workspace_policy=sample_workspace_policy(),
                permission_manifest=sample_permission_manifest(),
                executor=CompletingExecutor(),
                judge=RevisionJudge(),
                hard_check_status=HardCheckStatus.PASSED,
                hard_check_refs=["reports/hard_checks.json"],
            )
            self.assertEqual(revision.status, AgenticFlowStatus.REVISION_REQUIRED)
            self.assertEqual(revision.revision_request_ref, "revisions/request.json")
            self.assertEqual(revision.accepted_artifact_refs, [])

    def test_repair_decision_requires_structured_repair_brief(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-repair",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=CompletingExecutor(),
                    judge=InvalidRepairBriefJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_revision_decision_requires_structured_request_for_same_contract(self) -> None:
        with TemporaryDirectory() as tmpdir:
            _write_hard_check(tmpdir)
            with self.assertRaises(ContractValidationError):
                AgenticFlowRunner(tmpdir).run(
                    run_id="run-revision",
                    contract=sample_contract(),
                    workspace_policy=sample_workspace_policy(),
                    permission_manifest=sample_permission_manifest(),
                    executor=CompletingExecutor(),
                    judge=WrongRevisionRequestJudge(),
                    hard_check_status=HardCheckStatus.PASSED,
                    hard_check_refs=["reports/hard_checks.json"],
                )

    def test_result_payload_uses_ref_map_without_raw_body_fields(self) -> None:
        result = AgenticFlowRunner("/tmp")._build_result(
            "run-001",
            sample_contract(),
            AgentExecutionReport(
                report_id="execution-report-001",
                packet_id="execution-packet-001",
                packet_ref="packets/execution_packet.json",
                contract_id=sample_contract().contract_id,
                contract_hash=sample_contract().contract_hash,
                contract_ref="contract/task_contract.json",
                status=AgentExecutionStatus.COMPLETED,
                produced_artifact_refs=["artifacts/final.md"],
            ),
            JudgeReport(
                report_id="judge-report-001",
                packet_id="judge-packet-001",
                packet_ref="packets/judge_packet.json",
                contract_id=sample_contract().contract_id,
                contract_hash=sample_contract().contract_hash,
                contract_ref="contract/task_contract.json",
                decision=JudgeReportDecision.ACCEPTED,
                hard_check_status=HardCheckStatus.PASSED,
                accepted_artifact_refs=["artifacts/final.md"],
            ),
        )
        payload = result.to_dict()

        self.assertIn("ref_map", payload)
        self.assertNotIn("refs", payload)
        self.assertNotIn("raw_transcript", payload)


def _exists(path: str) -> bool:
    return Path(path).exists()


def _line_count(path: str) -> int:
    return len(Path(path).read_text(encoding="utf-8").splitlines())


def _write_hard_check(tmpdir: str) -> None:
    path = Path(tmpdir) / "runs/run-001/reports/hard_checks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"status": "passed"}\n', encoding="utf-8")


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
